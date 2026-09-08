import functools
import hashlib
import inspect
import json
import logging
import os
import sys
import threading
import time
import traceback
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Dict, Optional, TypeVar

import requests
from django.core.cache import cache
from django.utils.deprecation import MiddlewareMixin

T = TypeVar("T", bound=Callable[..., object])

SKIP_DISCORD_BRIDGE_ATTR = "discord_bridge_skip"
DISCORD_DEDUPE_TTL_SECONDS = 5 * 60  # 5 minutes
DISCORD_MAX_CONTENT_LENGTH = 1900
REDACTED_VALUE = "<redacted>"

DISCORD_LEVEL_COLORS = {
    "DEBUG": 0x95A5A6,  # Gray
    "INFO": 0x2ECC71,  # Green
    "WARNING": 0xF1C40F,  # Yellow
    "ERROR": 0xE74C3C,  # Red
    "CRITICAL": 0x992D22,  # Dark Red
}

_DEFAULT_REDACT_KEYS = {
    "authorization",
    "cookie",
    "current_password",
    "new_password",
    "password",
    "refresh",
    "secret",
    "token",
    "x-api-key",
}

__all__ = [
    "CustomLogger",
    "DiscordForwardingHandler",
    "RequestLoggingMiddleware",
    "SKIP_DISCORD_BRIDGE_ATTR",
    "dispatch_stdlib_record_to_discord",
    "get_logger",
    "log_exceptions",
    "skip_request_logging",
]


def _get_environment_label() -> str:
    env = os.getenv("ENVIRONMENT")
    if not env:
        try:
            from django.conf import settings

            env = getattr(settings, "ENVIRONMENT", None)
            if not env:
                env = (
                    "DEVELOPMENT" if getattr(settings, "DEBUG", False) else "PRODUCTION"
                )
        except Exception:
            env = "PRODUCTION"
    return str(env).upper()


def _get_redact_keys() -> set[str]:
    try:
        from django.conf import settings

        configured = str(getattr(settings, "CUSTOM_LOG_REDACT_KEYS", "")).strip()
        configured_keys = {
            key.strip().lower() for key in configured.split(",") if key.strip()
        }
        return _DEFAULT_REDACT_KEYS | configured_keys
    except Exception:
        return set(_DEFAULT_REDACT_KEYS)


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        try:
            from django.conf import settings

            if getattr(settings, "DEBUG", False):
                logger.setLevel(logging.DEBUG)
            else:
                logger.setLevel(logging.INFO)
        except Exception:
            logger.setLevel(logging.INFO)
        logger.propagate = False

    return logger


def log_exceptions(func_or_logger: Any = None):
    """Decorator to log any exception raised by the wrapped function.

    The original exception is re-raised after logging.
    Supports both @log_exceptions and @log_exceptions().
    """

    def decorator(func: T) -> T:
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception:
                CustomLogger.exception(
                    func.__module__, f"Unhandled exception in {func.__qualname__}"
                )
                raise

        return wrapper  # type: ignore

    if callable(func_or_logger) and not isinstance(func_or_logger, logging.Logger):
        return decorator(func_or_logger)

    return decorator


def _sanitize_value(value: Any, redact_keys: set[str], depth: int = 0) -> Any:
    if depth > 6:
        return "<max-depth>"

    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for key, nested_value in value.items():
            key_str = str(key)
            if key_str.lower() in redact_keys:
                sanitized[key_str] = REDACTED_VALUE
            else:
                sanitized[key_str] = _sanitize_value(
                    nested_value, redact_keys=redact_keys, depth=depth + 1
                )
        return sanitized

    if isinstance(value, (list, tuple, set)):
        return [
            _sanitize_value(item, redact_keys=redact_keys, depth=depth + 1)
            for item in value
        ]

    if isinstance(value, (str, int, float, bool)) or value is None:
        return value

    if isinstance(value, bytes):
        return "<bytes>"

    return str(value)


def _sanitize_extra(extra: dict[str, Any] | None) -> dict[str, Any]:
    if not extra:
        return {}

    sanitized = _sanitize_value(extra, redact_keys=_get_redact_keys())
    if isinstance(sanitized, dict):
        return sanitized
    return {"extra": str(sanitized)}


def _normalize_message(message: Any) -> str:
    if isinstance(message, str):
        return message

    sanitized = _sanitize_value(message, redact_keys=_get_redact_keys())
    if isinstance(sanitized, (dict, list)):
        return json.dumps(sanitized, sort_keys=True, default=str)
    return str(sanitized)


def _is_incident_error(level: str, extra: dict[str, Any]) -> bool:
    if level.upper() not in {"ERROR", "CRITICAL"}:
        return False
    if extra.get("status_code") == 500 or extra.get("http_status") == 500:
        return True
    if extra.get("path") and extra.get("method"):
        return True
    return False


def _build_fingerprint(
    level: str, source: str, message: str, extra: dict[str, Any]
) -> str:
    if _is_incident_error(level=level, extra=extra):
        payload = {
            "kind": "incident-error",
            "level": level.upper(),
            "path": str(extra.get("path", "")).strip(),
            "method": str(extra.get("method", "")).upper().strip(),
            "exception_type": str(extra.get("exception_type", "")).strip(),
            "environment": _get_environment_label(),
        }
    else:
        payload = {
            "kind": "generic-log",
            "level": level.upper(),
            "source": source,
            "message": str(message)[:300],
            "environment": _get_environment_label(),
        }
    serialized = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:20]


def _extract_exception_details(
    exc_type: Any, exc_value: Any, exc_tb: Any
) -> dict[str, Any]:
    details: dict[str, Any] = {}
    if exc_type:
        details["exception_type"] = (
            exc_type.__name__ if hasattr(exc_type, "__name__") else str(exc_type)
        )
    if exc_value:
        details["exception"] = str(exc_value)

    if exc_tb:
        try:
            formatted_tb = "".join(
                traceback.format_exception(exc_type, exc_value, exc_tb)
            )
            details["traceback"] = formatted_tb

            frames = traceback.extract_tb(exc_tb)
            if frames:
                last_frame = frames[-1]
                filename = last_frame.filename
                try:
                    rel_path = os.path.relpath(filename)
                    display_file = (
                        rel_path
                        if not rel_path.startswith("..")
                        else os.path.basename(filename)
                    )
                except Exception:
                    display_file = os.path.basename(filename)

                details["error_file"] = display_file.replace("\\", "/")
                details["error_line"] = last_frame.lineno
                details["error_func"] = last_frame.name
                if last_frame.line:
                    details["error_code"] = last_frame.line.strip()
        except Exception:
            pass

    return details


def _write_local_log(
    source: str,
    level: str,
    message: str,
    extra: dict[str, Any],
    exc_info: Any = None,
) -> None:
    level_number = getattr(logging, level.upper(), logging.INFO)
    logger = get_logger(source)
    log_extra = dict(extra)
    # Don't duplicate raw multi-line traceback inside the single-line JSON extra if exc_info is provided,
    # because logger.log(..., exc_info=exc_info) outputs the formatted traceback directly.
    if exc_info:
        log_extra.pop("traceback", None)
    if log_extra:
        message = (
            f"{message} | extra={json.dumps(log_extra, sort_keys=True, default=str)}"
        )
    logger.log(
        level_number,
        message,
        exc_info=exc_info,
        extra={SKIP_DISCORD_BRIDGE_ATTR: True},
    )


def _send_to_discord_async(
    *,
    source: str,
    level: str,
    message: str,
    extra: dict[str, Any],
    mention_here: bool | None = None,
) -> None:
    webhook_url = os.getenv("DISCORD_LOG_WEBHOOK_URL") or os.getenv(
        "DISCORD_WEBHOOK_URL"
    )
    if not webhook_url:
        return

    # Check minimum log level (default: INFO)
    min_level_str = os.getenv("DISCORD_LOG_LEVEL", "INFO").upper()
    min_level = getattr(logging, min_level_str, logging.INFO)
    current_level = getattr(logging, level.upper(), logging.INFO)

    if current_level < min_level:
        return

    fingerprint = _build_fingerprint(
        level=level, source=source, message=message, extra=extra
    )
    env_label = _get_environment_label()

    # Deduplication via Django cache (Redis)
    try:
        dedupe_key = f"discord-log:{env_label}:{fingerprint}"
        is_new_event = cache.add(dedupe_key, 1, timeout=DISCORD_DEDUPE_TTL_SECONDS)
        if is_new_event is False:
            return
    except Exception:
        pass  # If cache is unavailable, proceed with sending

    fields = [
        {"name": "Environment", "value": f"`{env_label}`", "inline": True},
        {"name": "Fingerprint", "value": f"`{fingerprint}`", "inline": True},
        {
            "name": "Timestamp",
            "value": f"`{datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}`",
            "inline": True,
        },
    ]

    for k, v in list(extra.items()):
        if k in ("source", "environment", "fingerprint", "traceback"):
            continue
        if len(fields) >= 24:
            break
        val_str = str(v)
        if len(val_str) > 300:
            val_str = val_str[:297] + "..."
        fields.append({"name": str(k), "value": f"`{val_str}`", "inline": True})

    tb_str = extra.get("traceback")
    if tb_str:
        tb_trimmed = str(tb_str).strip()
        if len(tb_trimmed) > 1200:
            tb_trimmed = "..." + tb_trimmed[-1197:]
        desc = f"**{message}**\n```py\n{tb_trimmed}\n```"
    else:
        desc = f"```{message[:1700]}```" if message else "(No message content)"

    embed = {
        "title": f"[{level}] [{env_label}] {source}",
        "description": desc,
        "color": DISCORD_LEVEL_COLORS.get(level, 0x3498DB),
        "fields": fields,
    }

    payload: dict[str, Any] = {"embeds": [embed]}
    if mention_here or (mention_here is None and level in ("CRITICAL",)):
        payload["content"] = "@here"

    def _post():
        try:
            requests.post(webhook_url, json=payload, timeout=4)
        except Exception:
            pass

    threading.Thread(target=_post, daemon=True).start()


def _dispatch_log_event(
    *,
    source: str,
    level: str,
    message: Any,
    extra: dict[str, Any] | None = None,
    emit_local: bool,
    emit_discord: bool,
    mention_here: bool | None = None,
    exc_info: Any = None,
) -> None:
    normalized_source = str(source)
    normalized_level = str(level).upper()
    normalized_message = _normalize_message(message)
    sanitized_extra = _sanitize_extra(extra)

    if "source" not in sanitized_extra:
        sanitized_extra["source"] = normalized_source

    if emit_local:
        _write_local_log(
            source=normalized_source,
            level=normalized_level,
            message=normalized_message,
            extra=sanitized_extra,
            exc_info=exc_info,
        )

    if emit_discord:
        _send_to_discord_async(
            source=normalized_source,
            level=normalized_level,
            message=normalized_message,
            extra=sanitized_extra,
            mention_here=mention_here,
        )


class CustomLogger:
    """Logger facade supporting both instance-style and class-style calls,
    with auto-caller inspection, data sanitization, and Discord forwarding.

    Examples:
        CustomLogger.info("Created user", {"user_id": 1})
        CustomLogger.info("users.services.user_service", "Created user", {"user_id": 1})
        logger = CustomLogger("users.services.user_service")
        logger.info("Created user", {"user_id": 1})
    """

    def __init__(self, source: str | None = None):
        self.source = source or self._infer_caller_module(skip=2)

    @staticmethod
    def _infer_caller_module(skip: int = 2) -> str:
        frame = inspect.currentframe()
        try:
            caller = frame
            for _ in range(skip):
                caller = caller.f_back if caller else None
            module = inspect.getmodule(caller) if caller else None
            return (
                module.__name__
                if module and hasattr(module, "__name__")
                else "__main__"
            )
        finally:
            del frame

    @staticmethod
    def _resolve_call(
        first_arg: "CustomLogger | str",
        args: tuple[Any, ...],
        default_message: Any = "",
    ) -> tuple[str, Any, dict[str, Any] | None]:
        extra = None
        if isinstance(first_arg, CustomLogger):
            source = first_arg.source
            resolved_message = args[0] if args else default_message
            if len(args) > 1 and isinstance(args[1], dict):
                extra = args[1]
        else:
            if args:
                source = str(first_arg)
                resolved_message = args[0]
                if len(args) > 1 and isinstance(args[1], dict):
                    extra = args[1]
            else:
                source = CustomLogger._infer_caller_module(skip=3)
                resolved_message = first_arg

        return source, resolved_message, extra

    def debug(
        self: "CustomLogger | str", *args: Any, extra: dict[str, Any] | None = None
    ) -> None:
        source, resolved_message, positional_extra = CustomLogger._resolve_call(
            self, args
        )
        _dispatch_log_event(
            source=source,
            level="DEBUG",
            message=resolved_message,
            extra=extra or positional_extra,
            emit_local=True,
            emit_discord=True,
        )

    def info(
        self: "CustomLogger | str", *args: Any, extra: dict[str, Any] | None = None
    ) -> None:
        source, resolved_message, positional_extra = CustomLogger._resolve_call(
            self, args
        )
        _dispatch_log_event(
            source=source,
            level="INFO",
            message=resolved_message,
            extra=extra or positional_extra,
            emit_local=True,
            emit_discord=True,
        )

    def warning(
        self: "CustomLogger | str", *args: Any, extra: dict[str, Any] | None = None
    ) -> None:
        source, resolved_message, positional_extra = CustomLogger._resolve_call(
            self, args
        )
        _dispatch_log_event(
            source=source,
            level="WARNING",
            message=resolved_message,
            extra=extra or positional_extra,
            emit_local=True,
            emit_discord=True,
        )

    def error(
        self: "CustomLogger | str",
        *args: Any,
        extra: dict[str, Any] | None = None,
        exc_info: Any = None,
    ) -> None:
        source, resolved_message, positional_extra = CustomLogger._resolve_call(
            self, args
        )
        merged_extra = dict(extra or positional_extra or {})
        passed_exc = None
        if exc_info is True:
            passed_exc = sys.exc_info()
        elif isinstance(exc_info, tuple):
            passed_exc = exc_info

        if passed_exc and passed_exc[0]:
            exc_details = _extract_exception_details(*passed_exc)
            for k, v in exc_details.items():
                merged_extra.setdefault(k, v)

        _dispatch_log_event(
            source=source,
            level="ERROR",
            message=resolved_message,
            extra=merged_extra,
            emit_local=True,
            emit_discord=True,
            exc_info=passed_exc if passed_exc and passed_exc[0] else None,
        )

    def critical(
        self: "CustomLogger | str",
        *args: Any,
        extra: dict[str, Any] | None = None,
        exc_info: Any = None,
    ) -> None:
        source, resolved_message, positional_extra = CustomLogger._resolve_call(
            self, args
        )
        merged_extra = dict(extra or positional_extra or {})
        passed_exc = None
        if exc_info is True:
            passed_exc = sys.exc_info()
        elif isinstance(exc_info, tuple):
            passed_exc = exc_info

        if passed_exc and passed_exc[0]:
            exc_details = _extract_exception_details(*passed_exc)
            for k, v in exc_details.items():
                merged_extra.setdefault(k, v)

        _dispatch_log_event(
            source=source,
            level="CRITICAL",
            message=resolved_message,
            extra=merged_extra,
            emit_local=True,
            emit_discord=True,
            exc_info=passed_exc if passed_exc and passed_exc[0] else None,
        )

    def exception(
        self: "CustomLogger | str", *args: Any, extra: dict[str, Any] | None = None
    ) -> None:
        source, resolved_message, positional_extra = CustomLogger._resolve_call(
            self, args, default_message="Unhandled exception"
        )
        exc_info = sys.exc_info()
        exc_type, exc_value, exc_tb = exc_info
        merged_extra = dict(extra or positional_extra or {})

        exc_details = _extract_exception_details(exc_type, exc_value, exc_tb)
        for k, v in exc_details.items():
            merged_extra.setdefault(k, v)

        _dispatch_log_event(
            source=source,
            level="ERROR",
            message=resolved_message,
            extra=merged_extra,
            emit_local=True,
            emit_discord=True,
            exc_info=exc_info if exc_type else True,
        )

    def __getattr__(self, item):
        return getattr(get_logger(self.source), item)


# ---------------------------------------------------------------------------
# Standard library Django 500 error forwarding handler
# ---------------------------------------------------------------------------


def dispatch_stdlib_record_to_discord(record: logging.LogRecord) -> None:
    """Forward stdlib error/critical records (like django.request 500s) to Discord."""
    if getattr(record, SKIP_DISCORD_BRIDGE_ATTR, False):
        return

    if record.levelno < logging.ERROR:
        return

    extra: dict[str, Any] = {"module": record.module, "line": record.lineno}
    extra["source_logger"] = record.name
    if record.exc_info:
        exc_type, exc_value, exc_tb = record.exc_info
        exc_details = _extract_exception_details(exc_type, exc_value, exc_tb)
        for k, v in exc_details.items():
            extra.setdefault(k, v)

    rendered_message = record.getMessage()
    if record.name == "django.request":
        request = getattr(record, "request", None)
        if request is not None:
            extra["method"] = str(getattr(request, "method", "")).upper().strip()
            extra["path"] = str(getattr(request, "path", "")).strip()
        if not extra.get("path"):
            extra["path"] = rendered_message.rsplit(":", 1)[-1].strip()
        extra["status_code"] = 500
    elif record.name == "django.server":
        if '" ' in rendered_message:
            request_part = rendered_message.split('"', 2)[1]
            request_tokens = request_part.split(" ")
            if len(request_tokens) >= 2:
                extra["method"] = request_tokens[0].strip()
                extra["path"] = request_tokens[1].strip()
        extra["status_code"] = 500

    _dispatch_log_event(
        source=record.name,
        level=record.levelname,
        message=rendered_message,
        extra=extra,
        emit_local=False,
        emit_discord=True,
    )


class DiscordForwardingHandler(logging.Handler):
    """Logging handler that forwards standard library ERROR/CRITICAL logs to Discord."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            dispatch_stdlib_record_to_discord(record)
        except Exception:
            self.handleError(record)


# ---------------------------------------------------------------------------
# Request logging middleware
# ---------------------------------------------------------------------------

_REQUEST_LOGGING_EXEMPT_PATHS: frozenset[str] = frozenset(
    {
        "/admin/",
        "/api/docs",
        "/api/docs/",
        "/api/schema/",
        "/static/",
        "/health/",
        "/favicon.ico",
    }
)
_MAX_RESPONSE_BODY_LOG_LENGTH: int = 5000
_SKIP_REQUEST_LOGGING_ATTR = "skip_request_logging"


def skip_request_logging(func):
    """Decorator to mark a view to skip detailed request body logging."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)

    wrapper.skip_request_logging = True  # type: ignore[attr-defined]
    return wrapper


def _parse_request_body(raw_body: bytes) -> Any:
    if not raw_body:
        return None
    try:
        return json.loads(raw_body)
    except (json.JSONDecodeError, ValueError):
        try:
            return raw_body.decode("utf-8", errors="replace")[:500]
        except Exception:
            return "<unreadable>"


def _sanitize_headers(
    headers: Mapping[str, str], redact_keys: set[str]
) -> dict[str, str]:
    sanitized: dict[str, str] = {}
    for key, value in headers.items():
        if key.lower() in redact_keys:
            sanitized[key] = REDACTED_VALUE
        else:
            sanitized[key] = value
    return sanitized


def _parse_response_body(response) -> Any:
    content_type = response.get("Content-Type", "")
    if "application/json" not in content_type and "+json" not in content_type:
        return None

    try:
        raw = response.content
    except Exception:
        return None

    if not raw:
        return None

    try:
        body = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None

    body_str = json.dumps(body, default=str)
    if len(body_str) > _MAX_RESPONSE_BODY_LOG_LENGTH:
        return {
            "_truncated": True,
            "_preview": body_str[:_MAX_RESPONSE_BODY_LOG_LENGTH],
        }

    return body


class RequestLoggingMiddleware(MiddlewareMixin):
    """Logs API requests and responses with latency, status codes, and sensitive data redaction."""

    def __init__(self, get_response=None):
        super().__init__(get_response)
        try:
            from django.conf import settings

            self._enabled = bool(getattr(settings, "REQUEST_LOGGING_ENABLED", False))
            self._exempt_paths = getattr(
                settings,
                "REQUEST_LOGGING_EXEMPT_PATHS",
                _REQUEST_LOGGING_EXEMPT_PATHS,
            )
        except Exception:
            self._enabled = False
            self._exempt_paths = _REQUEST_LOGGING_EXEMPT_PATHS

        self._logger = logging.getLogger("utils.request_logging")
        self._redact_keys = _get_redact_keys()

    def process_request(self, request):
        if not self._enabled:
            return None

        path = request.path
        if any(path.startswith(p) for p in self._exempt_paths):
            return None

        request._log_start = time.monotonic()
        try:
            request._log_body = request.body
        except Exception:
            request._log_body = b""

    def process_response(self, request, response):
        start = getattr(request, "_log_start", None)
        if start is None:
            return response

        duration_ms = round((time.monotonic() - start) * 1000, 2)
        cached_body = getattr(request, "_log_body", b"")

        status_code = response.status_code
        if status_code >= 500:
            log_level = logging.ERROR
        elif status_code >= 400:
            log_level = logging.WARNING
        else:
            log_level = logging.INFO

        log_entry: dict[str, Any] = {
            "method": request.method,
            "path": request.get_full_path(),
            "status_code": status_code,
            "duration_ms": duration_ms,
        }

        if hasattr(request, "user") and getattr(
            request.user, "is_authenticated", False
        ):
            log_entry["user_id"] = str(request.user.pk)

        raw_headers = {k: v for k, v in request.headers.items()}
        log_entry["request_headers"] = _sanitize_headers(raw_headers, self._redact_keys)

        body = _parse_request_body(cached_body)
        if body is not None:
            log_entry["request_body"] = _sanitize_value(
                body, redact_keys=self._redact_keys
            )

        response_body = _parse_response_body(response)
        if response_body is not None:
            log_entry["response_body"] = _sanitize_value(
                response_body, redact_keys=self._redact_keys
            )

        self._logger.log(log_level, "Request processed", extra=log_entry)
        return response

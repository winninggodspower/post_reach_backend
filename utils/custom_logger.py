import inspect
import json
import logging
import sys
from functools import wraps
from typing import Any, Callable, Mapping, Optional, TypeVar


T = TypeVar("T", bound=Callable[..., object])
REDACTED_VALUE = "<redacted>"
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


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        # Default to INFO, but allow Django DEBUG to make dev logs verbose
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


def log_exceptions(logger: Optional[logging.Logger] = None):
    """Decorator to log any exception raised by the wrapped function.

    The original exception is re-raised after logging.
    Usage:
        @log_exceptions()
        def my_service(...):
            ...
    """

    def decorator(func: T) -> T:
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception:
                CustomLogger.exception(func.__module__, f"Unhandled exception in {func.__qualname__}")
                raise

        return wrapper  # type: ignore

    return decorator


def _get_redact_keys() -> set[str]:
    return set(_DEFAULT_REDACT_KEYS)


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


def _sanitize_extra(extra: Optional[dict[str, Any]]) -> dict[str, Any]:
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


def _write_local_log(source: str, level: str, message: str, extra: dict[str, Any]) -> None:
    level_number = getattr(logging, level.upper(), logging.INFO)
    logger = get_logger(source)
    if extra:
        message = f"{message} | extra={json.dumps(extra, sort_keys=True, default=str)}"
    logger.log(level_number, message)


def _dispatch_log_event(
    *,
    source: str,
    level: str,
    message: Any,
    extra: Optional[dict[str, Any]] = None,
    emit_local: bool,
    emit_discord: bool,
    mention_here: Optional[bool] = None,
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
        )

    # Discord forwarding is intentionally not wired here; keep the API stable.
    _ = emit_discord
    _ = mention_here


class CustomLogger:
    """Logger facade that supports both instance-style and class-style calls.

    Examples:
        CustomLogger.info("users.services.user_service", "Created user", {"user_id": 1})
        logger = CustomLogger()
        logger.info("Created user", {"user_id": 1})
    """

    def __init__(self, source: Optional[str] = None):
        self.source = source or self._infer_caller_module(skip=2)

    @staticmethod
    def _infer_caller_module(skip: int = 2) -> str:
        frame = inspect.currentframe()
        try:
            caller = frame
            for _ in range(skip):
                caller = caller.f_back if caller else None
            module = inspect.getmodule(caller) if caller else None
            return module.__name__ if module and hasattr(module, "__name__") else "__main__"
        finally:
            del frame

    @staticmethod
    def _resolve_call(
        first_arg: "CustomLogger | str",
        args: tuple[Any, ...],
        default_message: Any = "",
    ) -> tuple[str, Any, Optional[dict[str, Any]]]:
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

    def debug(self: "CustomLogger | str", *args: Any, extra: Optional[dict[str, Any]] = None) -> None:
        source, resolved_message, positional_extra = CustomLogger._resolve_call(self, args)
        _dispatch_log_event(source=source, level="DEBUG", message=resolved_message, extra=extra or positional_extra, emit_local=True, emit_discord=True)

    def info(self: "CustomLogger | str", *args: Any, extra: Optional[dict[str, Any]] = None) -> None:
        source, resolved_message, positional_extra = CustomLogger._resolve_call(self, args)
        _dispatch_log_event(source=source, level="INFO", message=resolved_message, extra=extra or positional_extra, emit_local=True, emit_discord=True)

    def warning(self: "CustomLogger | str", *args: Any, extra: Optional[dict[str, Any]] = None) -> None:
        source, resolved_message, positional_extra = CustomLogger._resolve_call(self, args)
        _dispatch_log_event(source=source, level="WARNING", message=resolved_message, extra=extra or positional_extra, emit_local=True, emit_discord=True)

    def error(self: "CustomLogger | str", *args: Any, extra: Optional[dict[str, Any]] = None) -> None:
        source, resolved_message, positional_extra = CustomLogger._resolve_call(self, args)
        _dispatch_log_event(source=source, level="ERROR", message=resolved_message, extra=extra or positional_extra, emit_local=True, emit_discord=True)

    def critical(self: "CustomLogger | str", *args: Any, extra: Optional[dict[str, Any]] = None) -> None:
        source, resolved_message, positional_extra = CustomLogger._resolve_call(self, args)
        _dispatch_log_event(source=source, level="CRITICAL", message=resolved_message, extra=extra or positional_extra, emit_local=True, emit_discord=True)

    def exception(self: "CustomLogger | str", *args: Any, extra: Optional[dict[str, Any]] = None) -> None:
        source, resolved_message, positional_extra = CustomLogger._resolve_call(self, args, default_message="Unhandled exception")
        exc_type, exc_value, _ = sys.exc_info()
        merged_extra = dict(extra or positional_extra or {})
        if exc_type:
            merged_extra.setdefault("exception_type", exc_type.__name__)
        if exc_value:
            merged_extra.setdefault("exception", str(exc_value))
        _dispatch_log_event(source=source, level="ERROR", message=resolved_message, extra=merged_extra, emit_local=True, emit_discord=True)

    def __getattr__(self, item):
        return getattr(get_logger(self.source), item)


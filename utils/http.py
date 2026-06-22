"""
HTTP client utilities for shared service code.
"""

import asyncio
import json
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, TypeVar, Union

import httpx

from utils.custom_logger import CustomLogger

T = TypeVar("T")

__all__ = [
    "BaseHTTPClient",
    "HTTPError",
    "APIError",
    "RateLimitError",
    "TimeoutError",
    "ValidationError",
]


class HTTPError(Exception):
    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response_text: str | None = None,
        url: str | None = None,
        method: str | None = None,
        request_id: str | None = None,
    ):
        self.status_code = status_code
        self.response_text = response_text
        self.url = url
        self.method = method
        self.request_id = request_id
        super().__init__(
            f"{message} (Status: {status_code}, URL: {url}, Method: {method})"
        )


class APIError(HTTPError):
    pass


class RateLimitError(HTTPError):
    def __init__(
        self,
        retry_after: float | None = None,
        message: str = "Rate limit exceeded",
        **kwargs,
    ):
        self.retry_after = retry_after
        super().__init__(message, **kwargs)


class TimeoutError(HTTPError):
    pass


class ValidationError(HTTPError):
    pass


class BaseHTTPClient:
    def __init__(
        self,
        base_url: str = "",
        timeout: float = 30.0,
        max_retries: int = 3,
        default_headers: dict[str, str] | None = None,
        raise_for_status: bool = True,
        verify_ssl: bool = True,
        auth: Any | None = None,
    ):
        self.base_url = base_url.rstrip("/") if base_url else ""
        self.timeout = timeout
        self.max_retries = max_retries
        self.default_headers = default_headers or {}
        self.raise_for_status = raise_for_status
        self.verify_ssl = verify_ssl
        self.auth = auth

    def _get_retry_delay(self, attempt: int) -> float:
        return min(0.1 * (2**attempt), 5.0)

    def _parse_response(
        self, response: httpx.Response, expect_json: bool = True
    ) -> dict[str, Any] | str | bytes | T | list[Any]:
        content_type = response.headers.get("content-type", "").lower()
        is_json = "application/json" in content_type

        if not response.content:
            return ""

        if self.raise_for_status and response.is_error:
            error_msg = f"Request failed with status {response.status_code}"
            if is_json:
                try:
                    error_data = response.json()
                    error_msg = error_data.get("message", error_msg)
                    if "errors" in error_data:
                        error_msg += f"\nErrors: {error_data['errors']}"
                except json.JSONDecodeError:
                    pass

            if response.status_code == 400:
                raise ValidationError(
                    error_msg,
                    response.status_code,
                    response.text,
                    str(response.url),
                    response.request.method,
                )
            if response.status_code == 429:
                retry_after = float(response.headers.get("retry-after", "60"))
                raise RateLimitError(
                    retry_after=retry_after,
                    message=error_msg,
                    status_code=response.status_code,
                    response_text=response.text,
                    url=str(response.url),
                    method=response.request.method,
                )
            raise APIError(
                error_msg,
                response.status_code,
                response.text,
                str(response.url),
                response.request.method,
            )

        try:
            if expect_json and is_json:
                return response.json()
            if "text/" in content_type:
                return response.text
            return response.content
        except json.JSONDecodeError as e:
            CustomLogger.error(
                f"Failed to parse JSON response: {e}\nResponse text: {response.text}"
            )
            raise APIError(
                "Failed to parse JSON response",
                response.status_code,
                response.text,
                str(response.url),
                response.request.method,
            ) from e

    def _log_request(
        self,
        method: str,
        url: str,
        params: dict[str, Any] | None = None,
        json_data: Any | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        log_data: dict[str, Any] = {
            "method": method.upper(),
            "url": str(url),
            "timestamp": datetime.utcnow().isoformat(),
        }
        if params:
            log_data["params"] = params
        if headers:
            log_data["headers"] = {
                k: v if k.lower() != "authorization" else "*****"
                for k, v in headers.items()
            }
        if json_data is not None:
            log_data["json"] = json_data
        CustomLogger.debug(f"Outgoing request: {json.dumps(log_data, indent=2)}")

    def _log_response(self, response: httpx.Response, duration: float) -> None:
        log_data = {
            "method": response.request.method,
            "url": str(response.url),
            "status_code": response.status_code,
            "duration_seconds": round(duration, 3),
            "timestamp": datetime.utcnow().isoformat(),
        }
        max_length = 1000
        response_text = response.text
        if response_text and len(response_text) > max_length:
            log_data["response_body"] = response_text[:max_length] + "... (truncated)"
        else:
            log_data["response_body"] = response_text
        CustomLogger.debug(f"Incoming response: {json.dumps(log_data, indent=2)}")

    def _make_request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json_data: Any | None = None,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        expect_json: bool = True,
        **kwargs,
    ) -> dict[str, Any] | str | bytes | list[Any]:
        url = (
            path
            if path.startswith(("http://", "https://"))
            else f"{self.base_url}/{path.lstrip('/')}"
        )
        headers = {**self.default_headers, **(headers or {})}
        last_exception = None
        for attempt in range(self.max_retries + 1):
            try:
                self._log_request(method, url, params, json_data, headers)
                start_time = time.time()
                with httpx.Client(
                    timeout=self.timeout, verify=self.verify_ssl
                ) as client:
                    request_kwargs = {
                        "method": method,
                        "url": url,
                        "params": params,
                        "json": json_data,
                        "data": data,
                        "headers": headers,
                        "auth": self.auth,
                        **kwargs,
                    }
                    response = client.request(
                        **{k: v for k, v in request_kwargs.items() if v is not None}
                    )
                    duration = time.time() - start_time
                    self._log_response(response, duration)
                    return self._parse_response(response, expect_json)
            except (httpx.HTTPStatusError, APIError) as e:
                last_exception = e
                if attempt == self.max_retries or not isinstance(e, APIError):
                    raise
                wait_time = (
                    float(e.retry_after)
                    if isinstance(e, RateLimitError) and e.retry_after is not None
                    else self._get_retry_delay(attempt)
                )
                CustomLogger.warning(
                    f"Request failed (attempt {attempt + 1}/{self.max_retries}), retrying in {wait_time:.1f}s..."
                )
                time.sleep(wait_time)
            except (httpx.TimeoutException, TimeoutError):
                last_exception = TimeoutError(
                    f"Request timed out after {self.timeout} seconds",
                    url=url,
                    method=method,
                )
                if attempt == self.max_retries:
                    raise last_exception
                wait_time = self._get_retry_delay(attempt)
                CustomLogger.warning(
                    f"Request timed out (attempt {attempt + 1}/{self.max_retries}), retrying in {wait_time:.1f}s..."
                )
                time.sleep(wait_time)
            except Exception as e:
                last_exception = (
                    e
                    if isinstance(e, HTTPError)
                    else HTTPError(str(e), url=url, method=method)
                )
                if attempt == self.max_retries:
                    raise last_exception
                wait_time = (
                    float(last_exception.retry_after)
                    if isinstance(last_exception, RateLimitError)
                    and last_exception.retry_after is not None
                    else self._get_retry_delay(attempt)
                )
                CustomLogger.warning(
                    f"Request failed (attempt {attempt + 1}/{self.max_retries}), retrying in {wait_time:.1f}s..."
                )
                time.sleep(wait_time)
        raise last_exception or RuntimeError("Unexpected error in _make_request")

    async def _make_async_request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json_data: Any | None = None,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        expect_json: bool = True,
        **kwargs,
    ) -> dict[str, Any] | str | bytes | list[Any]:
        url = (
            path
            if path.startswith(("http://", "https://"))
            else f"{self.base_url}/{path.lstrip('/')}"
        )
        headers = {**self.default_headers, **(headers or {})}
        last_exception = None
        for attempt in range(self.max_retries + 1):
            try:
                self._log_request(method, url, params, json_data, headers)
                start_time = time.time()
                async with httpx.AsyncClient(
                    timeout=self.timeout, verify=self.verify_ssl
                ) as client:
                    request_kwargs = {
                        "method": method,
                        "url": url,
                        "params": params,
                        "json": json_data,
                        "data": data,
                        "headers": headers,
                        "auth": self.auth,
                        **kwargs,
                    }
                    response = await client.request(
                        **{k: v for k, v in request_kwargs.items() if v is not None}
                    )
                    duration = time.time() - start_time
                    self._log_response(response, duration)
                    return self._parse_response(response, expect_json)
            except (httpx.HTTPStatusError, APIError) as e:
                last_exception = e
                if attempt == self.max_retries or not isinstance(e, APIError):
                    raise
                wait_time = (
                    float(e.retry_after)
                    if isinstance(e, RateLimitError) and e.retry_after is not None
                    else self._get_retry_delay(attempt)
                )
                CustomLogger.warning(
                    f"Request failed (attempt {attempt + 1}/{self.max_retries}), retrying in {wait_time:.1f}s..."
                )
                await asyncio.sleep(wait_time)
            except (httpx.TimeoutException, TimeoutError):
                last_exception = TimeoutError(
                    f"Request timed out after {self.timeout} seconds",
                    url=url,
                    method=method,
                )
                if attempt == self.max_retries:
                    raise last_exception
                wait_time = self._get_retry_delay(attempt)
                CustomLogger.warning(
                    f"Request timed out (attempt {attempt + 1}/{self.max_retries}), retrying in {wait_time:.1f}s..."
                )
                await asyncio.sleep(wait_time)
            except Exception as e:
                last_exception = (
                    e
                    if isinstance(e, HTTPError)
                    else HTTPError(str(e), url=url, method=method)
                )
                if attempt == self.max_retries:
                    raise last_exception
                wait_time = (
                    float(last_exception.retry_after)
                    if isinstance(last_exception, RateLimitError)
                    and last_exception.retry_after is not None
                    else self._get_retry_delay(attempt)
                )
                CustomLogger.warning(
                    f"Request failed (attempt {attempt + 1}/{self.max_retries}), retrying in {wait_time:.1f}s..."
                )
                await asyncio.sleep(wait_time)
        raise last_exception or RuntimeError("Unexpected error in _make_async_request")

    def get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        **kwargs,
    ) -> dict[str, Any] | str | bytes | list[Any]:
        return self._make_request("GET", path, params=params, headers=headers, **kwargs)

    def post(
        self,
        path: str,
        json_data: Any | None = None,
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        **kwargs,
    ) -> dict[str, Any] | str | bytes | list[Any]:
        return self._make_request(
            "POST",
            path,
            json_data=json_data,
            data=data,
            params=params,
            headers=headers,
            **kwargs,
        )

    def put(
        self,
        path: str,
        json_data: Any | None = None,
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        **kwargs,
    ) -> dict[str, Any] | str | bytes | list[Any]:
        return self._make_request(
            "PUT",
            path,
            json_data=json_data,
            data=data,
            params=params,
            headers=headers,
            **kwargs,
        )

    def patch(
        self,
        path: str,
        json_data: Any | None = None,
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        **kwargs,
    ) -> dict[str, Any] | str | bytes | list[Any]:
        return self._make_request(
            "PATCH",
            path,
            json_data=json_data,
            data=data,
            params=params,
            headers=headers,
            **kwargs,
        )

    def delete(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        **kwargs,
    ) -> dict[str, Any] | str | bytes | list[Any]:
        return self._make_request(
            "DELETE", path, params=params, headers=headers, **kwargs
        )

    async def get_async(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        **kwargs,
    ) -> dict[str, Any] | str | bytes | list[Any]:
        return await self._make_async_request(
            "GET", path, params=params, headers=headers, **kwargs
        )

    async def post_async(
        self,
        path: str,
        json_data: Any | None = None,
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        **kwargs,
    ) -> dict[str, Any] | str | bytes | list[Any]:
        return await self._make_async_request(
            "POST",
            path,
            json_data=json_data,
            data=data,
            params=params,
            headers=headers,
            **kwargs,
        )

    async def put_async(
        self,
        path: str,
        json_data: Any | None = None,
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        **kwargs,
    ) -> dict[str, Any] | str | bytes | list[Any]:
        return await self._make_async_request(
            "PUT",
            path,
            json_data=json_data,
            data=data,
            params=params,
            headers=headers,
            **kwargs,
        )

    async def patch_async(
        self,
        path: str,
        json_data: Any | None = None,
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        **kwargs,
    ) -> dict[str, Any] | str | bytes | list[Any]:
        return await self._make_async_request(
            "PATCH",
            path,
            json_data=json_data,
            data=data,
            params=params,
            headers=headers,
            **kwargs,
        )

    async def delete_async(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        **kwargs,
    ) -> dict[str, Any] | str | bytes | list[Any]:
        return await self._make_async_request(
            "DELETE", path, params=params, headers=headers, **kwargs
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

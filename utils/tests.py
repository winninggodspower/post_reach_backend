from rest_framework import status

from utils.responses import CustomErrorResponse, CustomSuccessResponse


def test_success_response_shape():
    response = CustomSuccessResponse(
        data={"id": "123"},
        message="Created.",
        status=status.HTTP_201_CREATED,
    )

    assert response.status_code == 201
    assert response.data == {
        "success": True,
        "message": "Created.",
        "data": {"id": "123"},
    }


def test_error_response_shape():
    response = CustomErrorResponse(
        message="Invalid request.",
        errors={"field": ["This field is required."]},
    )

    assert response.status_code == 400
    assert response.data == {
        "success": False,
        "message": "Invalid request.",
        "errors": {"field": ["This field is required."]},
    }


def test_sanitize_value_redacts_sensitive_keys():
    from utils.custom_logger import REDACTED_VALUE, _sanitize_value

    payload = {
        "fields": "permalink",
        "access_token": "sensitive_access_token_123",
        "refresh_token": "sensitive_refresh_token_456",
        "client_secret": "my_secret",
        "password": "my_password",
        "total_tokens": 150,  # should NOT be redacted (token metric)
        "nested": {
            "token": "inner_token",
            "safe_key": "safe_value",
        },
    }

    sanitized = _sanitize_value(payload)
    assert sanitized["fields"] == "permalink"
    assert sanitized["access_token"] == REDACTED_VALUE
    assert sanitized["refresh_token"] == REDACTED_VALUE
    assert sanitized["client_secret"] == REDACTED_VALUE
    assert sanitized["password"] == REDACTED_VALUE
    assert sanitized["total_tokens"] == 150
    assert sanitized["nested"]["token"] == REDACTED_VALUE
    assert sanitized["nested"]["safe_key"] == "safe_value"


def test_sanitize_url_redacts_query_tokens():
    from utils.http import _sanitize_url

    url = "https://graph.threads.net/v1.0/18636276097046957?fields=permalink&access_token=THAAS0O0l7zntBYmFlUWExVGVz"
    sanitized = _sanitize_url(url)
    assert (
        "access_token=%2A%2A%2A%2A%2A" in sanitized or "access_token=*****" in sanitized
    )
    assert "THAAS0O0l7zntBYmFlUWExVGVz" not in sanitized
    assert "fields=permalink" in sanitized


def test_http_error_sanitizes_url():
    from utils.http import HTTPError

    err = HTTPError(
        "Request failed",
        status_code=400,
        url="https://graph.threads.net/v1.0/123?access_token=secret_val",
        method="GET",
    )
    err_str = str(err)
    assert "secret_val" not in err_str
    assert "secret_val" not in err.url
    assert "access_token=" in err_str


def test_base_http_client_log_request_redacts_tokens(mocker):
    import json

    from utils.custom_logger import CustomLogger
    from utils.http import BaseHTTPClient

    debug_mock = mocker.patch.object(CustomLogger, "debug")
    client = BaseHTTPClient(base_url="https://api.example.com")

    client._log_request(
        method="GET",
        url="https://graph.threads.net/v1.0/18636276097046957",
        params={
            "fields": "permalink",
            "access_token": "super_secret_token_abc",
        },
        headers={
            "Authorization": "Bearer raw_token",
            "Content-Type": "application/json",
        },
    )

    debug_mock.assert_called_once()
    logged_msg = debug_mock.call_args[0][0]
    assert "super_secret_token_abc" not in logged_msg
    assert "raw_token" not in logged_msg
    # Verify JSON structure was logged with redacted values
    assert "Outgoing request:" in logged_msg
    json_str = logged_msg.replace("Outgoing request: ", "", 1)
    parsed = json.loads(json_str)
    assert parsed["params"]["fields"] == "permalink"
    assert parsed["params"]["access_token"] == "<redacted>"
    assert parsed["headers"]["Authorization"] == "<redacted>"

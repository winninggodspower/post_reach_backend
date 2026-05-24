from rest_framework import status

from social_ploadify_backend.responses import CustomErrorResponse, CustomSuccessResponse
from utils.responses import ErrorResponse, SuccessResponse


def test_success_response_shape():
    response = SuccessResponse(
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
    response = ErrorResponse(
        message="Invalid request.",
        errors={"field": ["This field is required."]},
    )

    assert response.status_code == 400
    assert response.data == {
        "success": False,
        "message": "Invalid request.",
        "errors": {"field": ["This field is required."]},
    }


def test_legacy_success_response_wrapper_shape():
    response = CustomSuccessResponse({"message": "OK"})

    assert response.status_code == 200
    assert response.data == {
        "success": True,
        "data": {"message": "OK"},
    }


def test_legacy_error_response_wrapper_shape():
    response = CustomErrorResponse({"message": "Failed"})

    assert response.status_code == 400
    assert response.data == {
        "success": False,
        "errors": {"message": "Failed"},
    }

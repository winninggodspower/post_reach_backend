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



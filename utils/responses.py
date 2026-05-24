from rest_framework.response import Response


class APIResponse(Response):
    def __init__(
        self,
        *,
        success,
        message=None,
        data=None,
        errors=None,
        status=None,
        **kwargs,
    ):
        body = {
            "success": success,
            "message": message,
            "data": data,
            "errors": errors,
        }
        body = {key: value for key, value in body.items() if value is not None}
        super().__init__(data=body, status=status, **kwargs)


class CustomSuccessResponse(APIResponse):
    def __init__(self, data=None, message=None, status=200, **kwargs):
        super().__init__(
            success=True,
            message=message,
            data=data,
            status=status,
            **kwargs,
        )


class CustomErrorResponse(APIResponse):
    def __init__(self, message=None, errors=None, status=400, **kwargs):
        super().__init__(
            success=False,
            message=message,
            errors=errors,
            status=status,
            **kwargs,
        )

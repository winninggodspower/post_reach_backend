from utils.responses import ErrorResponse, SuccessResponse


class CustomSuccessResponse(SuccessResponse):
    def __init__(self, data, status=200, **kwargs):
        super().__init__(data=data, status=status, **kwargs)


class CustomErrorResponse(ErrorResponse):
    def __init__(self, data, status=400, **kwargs):
        super().__init__(errors=data, status=status, **kwargs)

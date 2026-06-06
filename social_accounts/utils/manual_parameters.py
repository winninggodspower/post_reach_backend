from drf_yasg import openapi


# --- YouTube Parameters ---
redirect_uri_param = openapi.Parameter(
    "redirect_uri",
    openapi.IN_QUERY,
    description="The URI Google will redirect to after authorization (the frontend's callback URL).",
    type=openapi.TYPE_STRING,
    required=True,
)

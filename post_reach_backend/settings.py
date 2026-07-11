import os
import sys
from datetime import timedelta
from pathlib import Path

import environ

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    # set casting, default value
    DEBUG=(bool, False)
)

# Take environment variables from .env file
environ.Env.read_env(os.path.join(BASE_DIR, ".env"))


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.1/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env("SECRET_KEY")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env("DEBUG")

ALLOWED_HOSTS = env.list(
    "ALLOWED_HOSTS",
    default=[
        "postreachbackend.pxxl.run",
        "postreach-backend-a052732af4b0.herokuapp.com",
        "10.88.0.11",
        "localhost",
        "127.0.0.1",
    ],
)


# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Custom user app
    "users.apps.UsersConfig",
    "social_accounts.apps.SocialAccountsConfig",
    "integrations",
    "content.apps.ContentConfig",
    # Third-party apps
    "rest_framework",
    "corsheaders",
    "querycount",
    "drf_yasg",
    "django_celery_beat",
    "django_celery_results",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "querycount.middleware.QueryCountMiddleware",
]

CORS_ALLOW_CREDENTIALS = True
CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://localhost:3000",
    "http://localhost:3001",
    "https://postreach.winningtech.xyz",
    "https://postreach.app",
]

# User settings
AUTH_USER_MODEL = "users.User"

# Django rest framework settings
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    )
}

SIMPLE_JWT = {
    # Refresh is rolled every time we issue a fresh access token
    # 'ROTATE_REFRESH_TOKENS': True,
    # An old refresh token is black-listed the moment it is replaced
    # 'BLACKLIST_AFTER_ROTATION': True,
    # 35 minutes is short enough to limit damage, long enough for a SPA
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=35),
    # Three days keeps the user logged in through normal work hours
    "REFRESH_TOKEN_LIFETIME": timedelta(days=3),
    # 'AUTH_COOKIE':    'access_token',
    # 'REFRESH_COOKIE': 'refresh_token',
    # 'AUTH_COOKIE_HTTP_ONLY': True,     # JavaScript cannot peek inside
    # 'AUTH_COOKIE_SECURE':    False,    # switch to True on production HTTPS
    # 'AUTH_COOKIE_SAMESITE': 'Strict'   # cookie travels only to our own origin
}


ROOT_URLCONF = "post_reach_backend.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "post_reach_backend.wsgi.application"


# Database
# https://docs.djangoproject.com/en/5.1/ref/settings/#databases

if DEBUG:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
else:
    DATABASES = {
        "default": env.db("DATABASE_URL"),
    }


# Password validation
# https://docs.djangoproject.com/en/5.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.1/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.1/howto/static-files/

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [
    BASE_DIR / "static",
]

# Default primary key field type
# https://docs.djangoproject.com/en/5.1/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

SWAGGER_USE_COMPAT_RENDERERS = False

# SOCIAL AUTHENTICATION SETTINGS
GOOGLE_CLIENT_ID = env("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = env("GOOGLE_CLIENT_SECRET")

FACEBOOK_APP_ID = env("FACEBOOK_APP_ID")
FACEBOOK_APP_SECRET = env("FACEBOOK_APP_SECRET")

INSTAGRAM_APP_ID = env("INSTAGRAM_APP_ID")
INSTAGRAM_APP_SECRET = env("INSTAGRAM_APP_SECRET")

TIKTOK_CLIENT_KEY = env("TIKTOK_CLIENT_KEY")
TIKTOK_CLIENT_SECRET = env("TIKTOK_CLIENT_SECRET")

LINKEDIN_CLIENT_ID = env("LINKEDIN_CLIENT_ID")
LINKEDIN_CLIENT_SECRET = env("LINKEDIN_CLIENT_SECRET")

# OAuth Redirect URI configuration
# Dev base uses the frontend dev server; prod base is read from environment
# _REDIRECT_BASE_DEV = "http://localhost:3000"
_REDIRECT_BASE_DEV = "https://postreach.winningtech.xyz"
_REDIRECT_BASE_PROD = env("REDIRECT_BASE_URL", default="https://postreach.app")
_REDIRECT_BASE = _REDIRECT_BASE_DEV if DEBUG else _REDIRECT_BASE_PROD

REDIRECT_URI = {
    "youtube": f"{_REDIRECT_BASE}/social/oauth/youtube/callback",
    "instagram": f"{_REDIRECT_BASE}/social/oauth/instagram/callback",
    "tiktok": f"{_REDIRECT_BASE}/social/oauth/tiktok/callback",
    "facebook": f"{_REDIRECT_BASE}/social/oauth/facebook/callback",
    "linkedin": f"{_REDIRECT_BASE}/social/oauth/linkedin/callback",
}

# Email configuration (ZeptoMail via SMTP)
EMAIL_BACKEND = env(
    "EMAIL_BACKEND", default="django.core.mail.backends.smtp.EmailBackend"
)
EMAIL_HOST = env("EMAIL_HOST", default="smtp.zeptomail.com")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="noreply@postreach.app")

# Ensure the Fernet key is 32 bytes long
FERNET_SECRET_KEY = env("FERNET_SECRET_KEY").encode()


# Cache Settings (using Redis)
# Reads from env var eg REDIS_URL=redis://:password@host:6379/0
# Falls back to localhost for dev
REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")

TESTING = "pytest" in sys.modules or "test" in sys.argv

if DEBUG:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "test-cache",
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
        }
    }

# Cloudflare R2 Storage
CLOUDFLARE_R2_ACCESS_KEY = env("CLOUDFLARE_R2_ACCESS_KEY")
CLOUDFLARE_R2_SECRET = env("CLOUDFLARE_R2_SECRET")
CLOUDFLARE_R2_BUCKET = env("CLOUDFLARE_R2_BUCKET")
CLOUDFLARE_R2_ENDPOINT = (
    f"https://{env('CLOUDFLARE_ACCOUNT_ID')}.r2.cloudflarestorage.com"
)
CLOUDFLARE_R2_PUBLIC_DOMAIN = "https://postreach.media.winningtech.xyz"

# Celery Settings
# Uses the same Redis instance as the cache
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = "django-db"
CELERY_RESULT_EXTENDED = True

# 1. Disable worker-to-worker chatter and heartbeat broadcasts
CELERY_WORKER_ENABLE_REMOTE_CONTROL = False
CELERY_WORKER_GOSSIP = False

# 2. Slow down the queue polling interval
# Instead of hammering Redis constantly, wait 5 seconds between checks when idle
CELERY_BROKER_TRANSPORT_OPTIONS = {
    "polling_interval": 5.0,  # seconds
}

# 4. Limit local worker concurrency to save connection pools
CELERY_WORKER_CONCURRENCY = 2

CELERY_BEAT_SCHEDULE = {
    "refresh_social_tokens": {
        "task": "social_accounts.tasks.refresh_expiring_tokens",
        "schedule": 1800,  # 30 minutes in seconds
    },
}

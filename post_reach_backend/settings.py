from datetime import timedelta
from pathlib import Path
import environ
import os

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    # set casting, default value
    DEBUG=(bool, False)
)

# Take environment variables from .env file
environ.Env.read_env(os.path.join(BASE_DIR, '.env'))


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.1/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env('SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env('DEBUG')

ALLOWED_HOSTS = []


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Custom user app
    'users.apps.UsersConfig',
    'social_accounts.apps.SocialAccountsConfig',
    'integrations',

    # Third-party apps
    'rest_framework',
    "corsheaders",
    'querycount',
    'drf_yasg',
    'django_celery_beat',
    'django_celery_results',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    "corsheaders.middleware.CorsMiddleware",
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    "querycount.middleware.QueryCountMiddleware"
]

CORS_ALLOW_CREDENTIALS = True
CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:8080",
    "http://localhost:3000",
    "https://localhost:3000",
    "https://f8ab-2a09-bac1-27c0-1b08-00-21a-6a.ngrok-free.app"
]

# User settings
AUTH_USER_MODEL = 'users.User'

# Django rest framework settings
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    )
}

# SIMPLE_JWT = {
#     # Refresh is rolled every time we issue a fresh access token
#     # 'ROTATE_REFRESH_TOKENS': True,
#     # An old refresh token is black-listed the moment it is replaced
#     # 'BLACKLIST_AFTER_ROTATION': True,

#     # Five minutes is short enough to limit damage, long enough for a SPA
#     # 'ACCESS_TOKEN_LIFETIME': timedelta(minutes=5),
#     # One day keeps the user logged in through normal work hours
#     # 'REFRESH_TOKEN_LIFETIME': timedelta(days=1),

#     'AUTH_COOKIE':    'access_token',
#     'REFRESH_COOKIE': 'refresh_token',

#     'AUTH_COOKIE_HTTP_ONLY': True,     # JavaScript cannot peek inside
#     'AUTH_COOKIE_SECURE':    False,    # switch to True on production HTTPS
#     'AUTH_COOKIE_SAMESITE': 'Strict'   # cookie travels only to our own origin
# }


ROOT_URLCONF = 'post_reach_backend.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'post_reach_backend.wsgi.application'


# Database
# https://docs.djangoproject.com/en/5.1/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}


# Password validation
# https://docs.djangoproject.com/en/5.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.1/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.1/howto/static-files/

STATIC_URL = 'static/'

# Default primary key field type
# https://docs.djangoproject.com/en/5.1/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

SWAGGER_USE_COMPAT_RENDERERS=False

# SOCIAL AUTHENTICATION SETTINGS
GOOGLE_CLIENT_ID = env('GOOGLE_CLIENT_ID')
GOOGLE_CLIENT_SECRET = env('GOOGLE_CLIENT_SECRET')

FACEBOOK_APP_ID = env('FACEBOOK_APP_ID')
FACEBOOK_APP_SECRET = env('FACEBOOK_APP_SECRET')

INSTAGRAM_APP_ID = env('INSTAGRAM_APP_ID')
INSTAGRAM_APP_SECRET = env('INSTAGRAM_APP_SECRET')

TIKTOK_CLIENT_KEY = env('TIKTOK_CLIENT_KEY')
TIKTOK_CLIENT_SECRET = env('TIKTOK_CLIENT_SECRET')

LINKEDIN_CLIENT_ID = env('LINKEDIN_CLIENT_ID')
LINKEDIN_CLIENT_SECRET = env('LINKEDIN_CLIENT_SECRET')

# OAuth Redirect URI configuration
# Dev base uses the frontend dev server; prod base is read from environment
# _REDIRECT_BASE_DEV = "http://localhost:3000"
_REDIRECT_BASE_DEV = "https://f8ab-2a09-bac1-27c0-1b08-00-21a-6a.ngrok-free.app"
_REDIRECT_BASE_PROD = env('REDIRECT_BASE_URL', default='https://postreach.app')
_REDIRECT_BASE = _REDIRECT_BASE_DEV if DEBUG else _REDIRECT_BASE_PROD

REDIRECT_URI = {
    "youtube":   f"{_REDIRECT_BASE}/social/oauth/youtube/callback",
    "instagram": f"{_REDIRECT_BASE}/social/oauth/instagram/callback",
    "tiktok":    f"{_REDIRECT_BASE}/social/oauth/tiktok/callback",
    "facebook":  f"{_REDIRECT_BASE}/social/oauth/facebook/callback",
    "linkedin":  f"{_REDIRECT_BASE}/social/oauth/linkedin/callback",
}

# Ensure the Fernet key is 32 bytes long
FERNET_SECRET_KEY = env('FERNET_SECRET_KEY').encode()


# Cache Settings (using Redis)
# CACHES = {
#     "default": {
#         "BACKEND": "django.core.cache.backends.redis.RedisCache",
#         "LOCATION": "redis://localhost:6379/1",
#     }
# }

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
        "LOCATION": "c:/foo/bar",
    }
}

# Celery Settings
CELERY_BROKER_URL = "redis://localhost:6379"
CELERY_RESULT_BACKEND = 'django-db'
CELERY_RESULT_EXTENDED = True

CELERY_BEAT_SCHEDULE = {
    "refresh_social_tokens": {
        "task": "social_accounts.tasks.refresh_expiring_tokens",
        "schedule": 1800,  # 30 minutes in seconds
    },
}

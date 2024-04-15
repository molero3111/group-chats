import os
from pathlib import Path

from decouple import Config

config = Config('.env')

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/4.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config('SECRET_KEY', default='insecure-39472947', cast=str)

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = config('DEBUG', default=False, cast=bool)

ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='').split(' ')
CSRF_TRUSTED_ORIGINS = config('CSRF_TRUSTED_ORIGINS', default='').split(' ')

URL_PREFIX = config('URL_PREFIX', default='chat-app', cast=str)
if URL_PREFIX:
    FORCE_SCRIPT_NAME = f'/{URL_PREFIX}'
URL_PREFIX_FORWARD_SLASH = f'{URL_PREFIX}/' if URL_PREFIX else ''
LOGOUT_REDIRECT_URL = f'/{URL_PREFIX_FORWARD_SLASH}'
LOGIN_REDIRECT_URL = f'/{URL_PREFIX_FORWARD_SLASH}rooms/'
LOGIN_URL = f'/{URL_PREFIX_FORWARD_SLASH}login/'

# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'daphne',
    'django.contrib.staticfiles',
    'channels',
    'core',
    'room',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'djangochat.urls'

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

WSGI_APPLICATION = 'djangochat.wsgi.application'
ASGI_APPLICATION = 'djangochat.asgi.application'  # for the chat, long-running connections

# Define Redis connection details using environment variables
REDIS_HOST = config('REDIS_HOST', default='redis', cast=str)
REDIS_PORT = config('REDIS_PORT', default=6379, cast=int)
REDIS_DEFAULT_DB = config('REDIS_DEFAULT_DB', default=0, cast=int)
REDIS_APP_DB = config('REDIS_APP_DB', default=0, cast=int)
REDIS_DEFAULT_KEY_EXPIRATION = config('REDIS_DEFAULT_KEY_EXPIRATION', default=3600, cast=int)
REDIS_PASSWORD = config('REDIS_PASSWORD', default='1234', cast=str)

CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        "CONFIG": {
            'hosts': [f'redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/{REDIS_DEFAULT_DB}'],
            'expiry': REDIS_DEFAULT_KEY_EXPIRATION,
        },
    },
}

DATABASES = {
    'default': {
        'ENGINE': 'django.contrib.gis.db.backends.postgis',
        'HOST': config('POSTGRES_HOST', default='db', cast=str),
        'PORT': config('POSTGRES_PORT', default='5432', cast=str),
        'NAME': config('POSTGRES_DB', default='chat_db', cast=str),
        'USER': config('POSTGRES_USER', default='chat_admin', cast=str),
        'PASSWORD': config('POSTGRES_PASSWORD', default='9287532461', cast=str),
    }
}

# Password validation
# https://docs.djangoproject.com/en/4.2/ref/settings/#auth-password-validators

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
# https://docs.djangoproject.com/en/4.2/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.2/howto/static-files/

STATIC_URL = 'static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

# Default primary key field type
# https://docs.djangoproject.com/en/4.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': f'redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DEFAULT_DB}',
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            'PASSWORD': REDIS_PASSWORD,
        }
    },
    'system': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': f'redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_APP_DB}',
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            'PASSWORD': REDIS_PASSWORD,
        }
    }
}

AUTHENTICATION_BACKENDS = [
    'core.authentication_backends.CustomAuthenticationBackend',
]

import os

# Keep tests hermetic: never read a developer's .env.
os.environ['ENV_FILE'] = os.devnull

# Production settings require these; set test-only values before importing them.
os.environ.setdefault('SECRET_KEY', 'test-only-secret-key')
os.environ.setdefault('DEBUG', 'False')
os.environ.setdefault('POSTGRES_PASSWORD', 'unused')
os.environ.setdefault('REDIS_PASSWORD', 'unused')

from .settings import *  # noqa: E402,F403

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

CHANNEL_LAYERS = {'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}}

CACHES = {
    'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'default'},
    'system': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'system'},
}

PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']

STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}

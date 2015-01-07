import os
from settings import *

SITE_NAME = os.environ['SITE_NAME']


PRODUCTION_SITES = ['live', 'staging']

DEBUG = (os.environ.get('DEBUG', False) == 'True')

ALLOWED_HOSTS = [
    'localhost',
]

SECRET_KEY = os.environ['DJANGO_SECRET_KEY']

DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'qa22@trapeze.com')


# Uncomment on local development if debug is False.
# This will overwrite the common setting that points to the alert mailbox.
#ADMINS = (('Django Alerts', '<email>'))
try:
    CONN_MAX_AGE = int(os.environ.get('CONN_MAX_AGE', 0))
except ValueError:
    CONN_MAX_AGE = 0


DATABASES = {
    'default': {
        # This changes based on driver used
        'ENGINE': 'django.contrib.gis.db.backends.postgis',
        'NAME': os.environ['RDS_DB_NAME'],
        'USER': os.environ['RDS_USERNAME'],
        'PASSWORD': os.environ['RDS_PASSWORD'],
        'HOST': os.environ['RDS_HOSTNAME'],
        'PORT': os.environ['RDS_PORT'],
        'CONN_MAX_AGE': CONN_MAX_AGE,
        'OPTIONS': {
            'autocommit': True,
        },
    }
}

try:
    CACHE_TIMEOUT = int(os.environ.get('CACHE_TIMEOUT', 300))
except ValueError:
    CACHE_TIMEOUT = 300

CACHE_LOCATION = os.environ.get('CACHE_LOCATION')

if CACHE_LOCATION:
    CACHES = {
        'default': {
            'BACKEND': 'calm_cache.backends.CalmCache',
            'LOCATION': 'base',
            'KEY_FUNCTION': 'calm_cache.contrib.sha1_key_func',
            'KEY_PREFIX': '%s:%s' % (SITE_NAME, RELEASE),
            'OPTIONS': {
                'MINT_PERIOD': '10',        # Allow stale results for this many seconds. Default: 0 (Off)
                'GRACE_PERIOD': '120',      # Serve stale value once during this period. Default: 0 (Off)
                'JITTER': '10',             # Upper bound on the random jitter in seconds. Default: 0 (Off)
            },
        },
        'base': {
            'BACKEND': 'django_elasticache.memcached.ElastiCache',
            'LOCATION': CACHE_LOCATION,
        },
    }

else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
        }

    }

# Django needs to know the version number, otherwise it tries to make an
# initial connection to postgres before running management commands.
POSTGIS_VERSION = (2, 0, 1)

STATIC_URL = os.environ['DJANGO_STATIC_URL']
MEDIA_URL = os.environ['DJANGO_MEDIA_URL']

if SITE_NAME == 'live':
    TEMPLATE_LOADERS = (
        ('django.template.loaders.cached.Loader', (
            'django.template.loaders.filesystem.Loader',
            'django.template.loaders.app_directories.Loader',
        )),
    )

TEMPLATE_DEBUG = DEBUG

SERVER_EMAIL = 'alerts@trapeze.com'

DEFAULT_HEADERS_EMAIL = {
    'From': DEFAULT_FROM_EMAIL,
    'Sender': DEFAULT_FROM_EMAIL,
}


EMAIL_BACKEND = 'django_ses.SESBackend'
DEFAULT_FILE_STORAGE = 'aws_tasks.storage_backends.MediaS3Storage'
STATICFILES_STORAGE = 'aws_tasks.storage_backends.StaticS3Storage'
THUMBNAIL_DEFAULT_STORAGE = DEFAULT_FILE_STORAGE

DEBUG_TOOLBAR_PATCH_SETTINGS = False # Required for toolbar not to adjust your settings, by default same as debug

AWS_ACCESS_KEY_ID = os.environ['AWS_ACCESS_KEY_ID']
AWS_SECRET_ACCESS_KEY = os.environ['AWS_SECRET_KEY']
AWS_STORAGE_BUCKET_NAME = os.environ['AWS_STORAGE_BUCKET_NAME']

SESSION_ENGINE = 'django.contrib.sessions.backends.signed_cookies'

NOMINATIONS_ENABLED = (os.environ.get('NOMINATIONS_ENABLED', False) == 'True')

FACEBOOK_APP_ID = os.environ.get('FACEBOOK_APP_ID', '')
FACEBOOK_APP_SECRET = os.environ.get('FACEBOOK_APP_SECRET', '')

RECAPTCHA_PUBLIC_KEY = os.environ.get('RECAPTCHA_PUBLIC_KEY', '')
RECAPTCHA_PRIVATE_KEY = os.environ.get('RECAPTCHA_PRIVATE_KEY', '')



AWS_QUERYSTRING_AUTH = False  # Don't include auth in every url
# Environment-driven settings for container deployment.
import os

DEBUG = os.environ.get('DJANGO_DEBUG', '').lower() in ('1', 'true', 'yes')
SECRET_KEY = os.environ['SECRET_KEY']
ALLOWED_HOSTS = [h.strip() for h in os.environ.get('ALLOWED_HOSTS', '').split(',') if h.strip()]
CSRF_TRUSTED_ORIGINS = [h for h in ALLOWED_HOSTS]
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('POSTGRES_DB', 'gw2raidar'),
        'USER': os.environ.get('POSTGRES_USER', 'gw2raidar'),
        'PASSWORD': os.environ['POSTGRES_PASSWORD'],
        'HOST': os.environ.get('POSTGRES_HOST', 'db'),
        'PORT': os.environ.get('POSTGRES_PORT', '5432'),
    }
}

DEFAULT_FROM_EMAIL = SERVER_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'gw2raidar@localhost')
EMAIL_SUBJECT_PREFIX = '[gw2raidar] '
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'localhost')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '25'))
if not os.environ.get('EMAIL_HOST'):
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

STATIC_URL = '/static/'
STATIC_ROOT = '/data/static'
UPLOAD_DIR = '/data/uploads'

if os.environ.get('GA_PROPERTY_ID'):
    GA_PROPERTY_ID = os.environ['GA_PROPERTY_ID']

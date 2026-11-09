from whitenoise import WhiteNoise
from django.conf import settings
from gw2raidar.wsgi import application as _app

application = WhiteNoise(_app, root=settings.STATIC_ROOT, prefix=settings.STATIC_URL)

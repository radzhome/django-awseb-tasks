import os
from os.path import abspath, dirname
import sys

SITE_ROOT = dirname(abspath(__file__))
sys.path.insert(0, SITE_ROOT)

LIB = abspath(os.path.join(SITE_ROOT, '../lib'))
sys.path.append(LIB)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings_prod")

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
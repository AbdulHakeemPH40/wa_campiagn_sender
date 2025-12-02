import os
import sys

path = '/home/Abdul40/wa_campiagn_sender'
if path not in sys.path:
    sys.path.insert(0, path)

os.environ['DJANGO_SETTINGS_MODULE'] = 'wa_campiagn_sender.pythonanywhere_settings'

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()

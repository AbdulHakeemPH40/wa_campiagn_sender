"""
WSGI config for wa_campiagn_sender project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'wa_campiagn_sender.settings')

# Note: Moderation settings are configured in settings.py
# No need to set environment variables here - Django settings take precedence

application = get_wsgi_application()

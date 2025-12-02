"""
WSGI config for wa_campiagn_sender project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'wa_campiagn_sender.settings')

# Default moderation environment values (can be overridden by real env vars)
for _k, _v in {
    'STRICT_POLICY': 'false',
    'USE_AI_MODERATION': 'true',
    'AI_PROVIDER': 'openai',
    'AI_FORCE_ALL': 'true',
    'OPENAI_MODERATION_MODEL': 'omni-moderation-latest',
    'OPENAI_PROJECT_ID': 'proj_flBAHQ0ao0k8ppxFFwHMWdnp',
    'AI_TIMEOUT': '10',
    'AI_RETRIES': '2',
    'AI_BACKOFF': '0.75',
}.items():
    os.environ.setdefault(_k, _v)

application = get_wsgi_application()

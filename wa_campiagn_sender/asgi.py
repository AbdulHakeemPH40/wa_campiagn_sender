import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

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

# Standard Django ASGI app for HTTP
django_asgi_app = get_asgi_application()

# Import websocket routes
try:
    from whatsappapi.routing import websocket_urlpatterns
except Exception:
    websocket_urlpatterns = []

# Compose application supporting both HTTP and WebSocket
application = ProtocolTypeRouter({
    'http': django_asgi_app,
    'websocket': AuthMiddlewareStack(
        URLRouter(websocket_urlpatterns)
    ),
})
from django.http import FileResponse, Http404
from django.conf import settings
import os

def favicon_view(request):
    """Serve favicon.ico from static files"""
    favicon_path = os.path.join(settings.BASE_DIR, 'static', 'image', 'favicon.ico')
    if os.path.exists(favicon_path):
        return FileResponse(open(favicon_path, 'rb'), content_type='image/x-icon')
    raise Http404("Favicon not found")
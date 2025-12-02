import asyncio
from django.http import HttpResponse, HttpResponsePermanentRedirect
from django.conf import settings

class CanonicalDomainMiddleware:
    """
    Middleware to redirect www to non-www domain for canonical URLs
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not settings.DEBUG:
            host = request.get_host()
            if host.startswith('www.'):
                # Redirect www to non-www
                canonical_host = host[4:]  # Remove 'www.'
                canonical_url = f"https://{canonical_host}{request.get_full_path()}"
                return HttpResponsePermanentRedirect(canonical_url)

        try:
            response = self.get_response(request)
        except asyncio.CancelledError:
            # Client disconnected/cancelled during redirect or processing
            return HttpResponse(status=204)
        return response
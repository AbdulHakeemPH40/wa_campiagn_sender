class SEOMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            response = self.get_response(request)
        except asyncio.CancelledError:
            # Client disconnected/cancelled; avoid logging noisy stacktrace
            return HttpResponse(status=204)
        
        # Add noindex header for admin and user panels
        if (request.path.startswith('/adminpanel/') or 
            request.path.startswith('/userpanel/') or 
            request.path.startswith('/admin/') or
            request.path.startswith('/login/') or
            request.path.startswith('/signup/') or
            request.path.startswith('/logout/')):
            response['X-Robots-Tag'] = 'noindex, nofollow'
        
        # Add performance headers for static content
        if request.path.startswith('/static/') or request.path.startswith('/media/'):
            if request.path.endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg')):
                response['Cache-Control'] = 'public, max-age=31536000, immutable'  # 1 year for images
            else:
                response['Cache-Control'] = 'public, max-age=86400'  # 1 day for other static files
            response['Expires'] = 'Thu, 31 Dec 2025 23:59:59 GMT'
        
        # Add security headers
        if not request.path.startswith('/admin/'):
            response['X-Content-Type-Options'] = 'nosniff'
            response['X-Frame-Options'] = 'DENY'
            response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
            
        return response
import asyncio
from django.http import HttpResponse
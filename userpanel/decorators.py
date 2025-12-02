from functools import wraps
from django.views.decorators.cache import never_cache
from django.views.decorators.vary import vary_on_headers

def no_cache_sensitive_data(view_func):
    """
    Decorator to prevent caching of sensitive user data pages like cart, pricing, etc.
    This prevents users from seeing stale pricing or cart information.
    """
    @wraps(view_func)
    @never_cache
    @vary_on_headers('User-Agent', 'Cookie')
    def _wrapped_view(request, *args, **kwargs):
        response = view_func(request, *args, **kwargs)
        
        # Add additional cache control headers
        response['Cache-Control'] = 'no-cache, no-store, must-revalidate, private'
        response['Pragma'] = 'no-cache'
        response['Expires'] = '0'
        response['X-Accel-Expires'] = '0'  # For nginx
        
        return response
    return _wrapped_view
class SEOMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        
        # Add noindex header for admin and user panels
        if (request.path.startswith('/adminpanel/') or 
            request.path.startswith('/userpanel/') or 
            request.path.startswith('/admin/') or
            request.path.startswith('/login/') or
            request.path.startswith('/signup/') or
            request.path.startswith('/logout/')):
            response['X-Robots-Tag'] = 'noindex, nofollow'
            
        return response
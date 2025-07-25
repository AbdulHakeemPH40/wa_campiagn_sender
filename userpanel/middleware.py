import pytz
from django.utils import timezone

class TimezoneMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Try to get timezone from cookie
        tzname = request.COOKIES.get('user_timezone')
        
        if tzname:
            try:
                # Activate the user's timezone
                timezone.activate(pytz.timezone(tzname))
            except pytz.exceptions.UnknownTimeZoneError:
                # If timezone is invalid, use UTC
                timezone.activate(pytz.UTC)
        else:
            # Default to UTC if no timezone cookie
            timezone.activate(pytz.UTC)
            
        response = self.get_response(request)
        
        # Reset to default timezone
        timezone.deactivate()
        
        return response
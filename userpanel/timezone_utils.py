import pytz
from django.utils import timezone

def convert_to_user_timezone(datetime_obj, user_timezone=None):
    """
    Convert a datetime object to the user's timezone
    
    Args:
        datetime_obj: A datetime object (assumed to be in UTC if timezone-aware)
        user_timezone: String representing the user's timezone (default: None, uses active timezone)
        
    Returns:
        A datetime object converted to the user's timezone
    """
    if not datetime_obj:
        return None
        
    # Ensure the datetime is timezone-aware
    if timezone.is_naive(datetime_obj):
        datetime_obj = timezone.make_aware(datetime_obj, pytz.UTC)
    
    # If no specific timezone provided, use the active timezone
    if not user_timezone:
        return timezone.localtime(datetime_obj)
    
    # Convert to specified timezone
    user_tz = pytz.timezone(user_timezone)
    return datetime_obj.astimezone(user_tz)

def get_current_time_in_user_timezone(user_timezone=None):
    """
    Get the current time in the user's timezone
    
    Args:
        user_timezone: String representing the user's timezone (default: None, uses active timezone)
        
    Returns:
        Current datetime in the user's timezone
    """
    now = timezone.now()
    return convert_to_user_timezone(now, user_timezone)

def get_user_local_date(user_timezone=None):
    """
    Get the current date in the user's timezone
    
    Args:
        user_timezone: String representing the user's timezone (default: None, uses active timezone)
        
    Returns:
        Current date in the user's timezone
    """
    if user_timezone:
        user_tz = pytz.timezone(user_timezone)
        return timezone.now().astimezone(user_tz).date()
    else:
        return timezone.localdate()
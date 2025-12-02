from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.conf import settings
from .paypal_utils import PayPalAPI
import logging

logger = logging.getLogger(__name__)

@login_required
def test_paypal_connection(request):
    """Debug view to test PayPal API connection"""
    if not (request.user.is_staff or request.user.is_superuser):
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    try:
        paypal_api = PayPalAPI()
        
        # Test access token
        token = paypal_api.get_access_token()
        
        result = {
            'paypal_mode': settings.PAYPAL_MODE,
            'base_url': paypal_api.base_url,
            'client_id': settings.PAYPAL_CLIENT_ID[:10] + '...',  # Partial for security
            'token_obtained': bool(token),
            'return_url': settings.PAYPAL_RETURN_URL,
            'cancel_url': settings.PAYPAL_CANCEL_URL,
        }
        
        if token:
            result['token_preview'] = token[:20] + '...'
        
        return JsonResponse(result)
        
    except Exception as e:
        logger.error(f"PayPal connection test failed: {e}", exc_info=True)
        return JsonResponse({
            'error': str(e),
            'paypal_mode': settings.PAYPAL_MODE,
            'base_url': getattr(paypal_api, 'base_url', 'Unknown')
        }, status=500)
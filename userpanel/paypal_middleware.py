from django.utils.deprecation import MiddlewareMixin
from django.contrib.auth import login
from django.contrib.auth.models import AnonymousUser
from .models import Order
import logging

logger = logging.getLogger(__name__)

class PayPalSessionMiddleware(MiddlewareMixin):
    """
    Middleware to handle session restoration for PayPal return URLs
    when the user session might be lost during external redirects
    """
    
    def process_request(self, request):
        # Only process PayPal return URLs
        if not request.path.startswith('/userpanel/paypal/'):
            return None
            
        # Skip if user is already authenticated
        if request.user.is_authenticated:
            return None
            
        # Try to find user from URL parameters first, then PayPal parameters
        url_user_id = request.GET.get('user_id')
        payment_id = request.GET.get('paymentId')
        token = request.GET.get('token')
        tx = request.GET.get('tx')
        
        if not (url_user_id or payment_id or token or tx):
            return None
            
        try:
            user = None
            
            # Method 1: Direct user ID from URL
            if url_user_id:
                from django.contrib.auth import get_user_model
                User = get_user_model()
                try:
                    user = User.objects.get(id=int(url_user_id))
                except (ValueError, User.DoesNotExist):
                    pass
            
            # Method 2: Find user via PayPal identifiers
            if not user and (payment_id or token or tx):
                order = None
                if payment_id:
                    order = Order.objects.filter(
                        paypal_payment_id=payment_id,
                        status='pending'
                    ).first()
                elif token:
                    order = Order.objects.filter(
                        paypal_txn_id=token,
                        status='pending'
                    ).first()
                elif tx:
                    order = Order.objects.filter(
                        paypal_txn_id=tx,
                        status='pending'
                    ).first()
                    
                if order:
                    user = order.user
                
            if user:
                # Restore user session
                login(request, user, backend='django.contrib.auth.backends.ModelBackend')
                logger.info(f"PayPal middleware: Restored session for user {user.email}")
                
        except Exception as e:
            logger.error(f"PayPal middleware error: {e}")
            
        return None
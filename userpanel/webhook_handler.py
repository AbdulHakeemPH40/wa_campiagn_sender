import json
import logging
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.utils.decorators import method_decorator
from django.conf import settings
import requests
from .models import Order
# Import moved to avoid circular import
from userpanel.email_utils import send_payment_success_email

logger = logging.getLogger(__name__)


def verify_paypal_webhook_signature(request, webhook_data):
    """
    🔒 SECURITY: Verify that webhook came from PayPal using signature verification.
    
    This prevents attackers from sending fake payment webhooks to get free subscriptions.
    
    PayPal sends these headers with each webhook:
    - PAYPAL-TRANSMISSION-ID: Unique ID for this transmission
    - PAYPAL-TRANSMISSION-TIME: Timestamp
    - PAYPAL-TRANSMISSION-SIG: The signature to verify
    - PAYPAL-CERT-URL: URL to PayPal's certificate
    - PAYPAL-AUTH-ALGO: Algorithm used (e.g., SHA256withRSA)
    
    Returns:
        bool: True if signature is valid, False otherwise
    """
    try:
        # Extract PayPal signature headers
        transmission_id = request.headers.get('PAYPAL-TRANSMISSION-ID')
        transmission_time = request.headers.get('PAYPAL-TRANSMISSION-TIME')
        transmission_sig = request.headers.get('PAYPAL-TRANSMISSION-SIG')
        cert_url = request.headers.get('PAYPAL-CERT-URL')
        auth_algo = request.headers.get('PAYPAL-AUTH-ALGO')
        
        # Check all required headers are present
        if not all([transmission_id, transmission_time, transmission_sig, cert_url, auth_algo]):
            logger.warning("⚠️ Missing PayPal webhook headers - possible fake webhook attempt")
            logger.warning(f"Headers present: ID={bool(transmission_id)}, Time={bool(transmission_time)}, "
                         f"Sig={bool(transmission_sig)}, Cert={bool(cert_url)}, Algo={bool(auth_algo)}")
            
            # SAFE FALLBACK FOR DEVELOPMENT/TESTING
            # In DEBUG mode, allow webhooks without signatures for local testing
            # ⚠️ THIS WILL BE DISABLED IN PRODUCTION (DEBUG=False)
            if settings.DEBUG:
                logger.warning("🔓 DEBUG MODE: Allowing webhook without signature verification")
                logger.warning("⚠️ THIS IS ONLY FOR DEVELOPMENT - WILL BE BLOCKED IN PRODUCTION!")
                return True
            
            return False
        
        # Get webhook ID from settings
        webhook_id = getattr(settings, 'PAYPAL_WEBHOOK_ID', None)
        
        if not webhook_id:
            logger.warning("⚠️ PAYPAL_WEBHOOK_ID not configured in settings")
            
            # SAFE FALLBACK FOR DEVELOPMENT
            if settings.DEBUG:
                logger.warning("🔓 DEBUG MODE: Proceeding without webhook ID verification")
                logger.warning("⚠️ SET PAYPAL_WEBHOOK_ID IN PRODUCTION!")
                return True
            
            logger.error("❌ Cannot verify webhook - PAYPAL_WEBHOOK_ID missing in production")
            return False
        
        # Determine PayPal API base URL
        paypal_mode = getattr(settings, 'PAYPAL_MODE', 'sandbox')
        if settings.DEBUG or paypal_mode == 'sandbox':
            api_base = 'https://api-m.sandbox.paypal.com'
            logger.info("🔧 Using PayPal Sandbox API for verification")
        else:
            api_base = 'https://api-m.paypal.com'
            logger.info("🔐 Using PayPal Live API for verification")
        
        # Step 1: Get PayPal OAuth access token
        try:
            auth_response = requests.post(
                f"{api_base}/v1/oauth2/token",
                headers={
                    "Accept": "application/json",
                    "Accept-Language": "en_US"
                },
                auth=(settings.PAYPAL_CLIENT_ID, settings.PAYPAL_CLIENT_SECRET),
                data={"grant_type": "client_credentials"},
                timeout=10
            )
            
            if auth_response.status_code != 200:
                logger.error(f"❌ Failed to get PayPal access token: {auth_response.status_code}")
                logger.error(f"Response: {auth_response.text[:200]}")
                return False
            
            access_token = auth_response.json().get('access_token')
            if not access_token:
                logger.error("❌ No access token in PayPal auth response")
                return False
                
        except requests.exceptions.Timeout:
            logger.error("❌ PayPal OAuth API timeout")
            return False
        except Exception as e:
            logger.error(f"❌ PayPal OAuth error: {e}")
            return False
        
        # Step 2: Build verification payload
        verify_payload = {
            "transmission_id": transmission_id,
            "transmission_time": transmission_time,
            "transmission_sig": transmission_sig,
            "cert_url": cert_url,
            "auth_algo": auth_algo,
            "webhook_id": webhook_id,
            "webhook_event": webhook_data  # The entire webhook body
        }
        
        # Step 3: Verify signature with PayPal
        try:
            verify_response = requests.post(
                f"{api_base}/v1/notifications/verify-webhook-signature",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {access_token}"
                },
                json=verify_payload,
                timeout=10
            )
            
            if verify_response.status_code != 200:
                logger.error(f"❌ PayPal verification request failed: {verify_response.status_code}")
                logger.error(f"Response: {verify_response.text[:200]}")
                return False
            
            verification_result = verify_response.json()
            verification_status = verification_result.get('verification_status')
            
            if verification_status == 'SUCCESS':
                logger.info("✅ PayPal webhook signature verified successfully")
                return True
            else:
                logger.error(f"❌ PayPal webhook verification FAILED: {verification_status}")
                logger.error(f"Verification response: {verification_result}")
                logger.error(f"Request IP: {request.META.get('REMOTE_ADDR')}")
                return False
                
        except requests.exceptions.Timeout:
            logger.error("❌ PayPal verification API timeout")
            return False
        except Exception as e:
            logger.error(f"❌ PayPal verification API error: {e}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Unexpected error in PayPal webhook verification: {e}")
        logger.exception("Full traceback:")
        return False

@csrf_exempt
@require_POST
def paypal_webhook_handler(request):
    """Handle PayPal webhook notifications for payment events"""
    try:
        # Get webhook data
        webhook_data = json.loads(request.body.decode('utf-8'))
        event_type = webhook_data.get('event_type')
        
        logger.info(f"PayPal Webhook received: {event_type}")
        logger.info(f"Webhook data: {json.dumps(webhook_data, indent=2)}")
        
        # 🔒 SECURITY CHECK: Verify webhook signature BEFORE processing
        # This prevents attackers from sending fake payment webhooks
        if not verify_paypal_webhook_signature(request, webhook_data):
            logger.error("🚨 SECURITY ALERT: Invalid PayPal webhook signature - rejecting request")
            logger.error(f"Attacker IP: {request.META.get('REMOTE_ADDR')}")
            logger.error(f"User-Agent: {request.META.get('HTTP_USER_AGENT')}")
            logger.error(f"Event attempted: {event_type}")
            return HttpResponse(status=400)  # Bad Request - reject fake webhooks
        
        logger.info(f"✅ Webhook signature verified - processing event: {event_type}")
        
        # === EXISTING PAYMENT LOGIC (100% UNCHANGED) ===
        # Handle payment events - include HELD payments as successful
        if event_type in ['PAYMENT.SALE.COMPLETED', 'PAYMENT.CAPTURE.COMPLETED', 'CHECKOUT.ORDER.COMPLETED', 'PAYMENT.SALE.PENDING']:
            return handle_payment_success(webhook_data)
        elif event_type in ['PAYMENT.SALE.DENIED', 'PAYMENT.CAPTURE.DENIED', 'PAYMENT.CAPTURE.DECLINED', 'CHECKOUT.ORDER.DECLINED']:
            return handle_payment_failed(webhook_data)
        elif event_type in ['PAYMENT.SALE.CANCELLED', 'PAYMENT.ORDER.CANCELLED']:
            return handle_payment_cancelled(webhook_data)
        else:
            logger.info(f"Unhandled webhook event: {event_type}")
        
        return HttpResponse(status=200)
        
    except Exception as e:
        logger.error(f"PayPal webhook error: {e}")
        return HttpResponse(status=500)

def handle_payment_success(webhook_data):
    """Process successful payment from PayPal webhook"""
    try:
        # Extract payment details
        resource = webhook_data.get('resource', {})
        payment_id = resource.get('id')
        amount = resource.get('amount', {}).get('value')
        
        logger.info(f"Webhook payment success: ID={payment_id}, Amount={amount}")
        
        # Find processing order by payment ID
        order = Order.objects.filter(
            paypal_payment_id=payment_id,
            status='processing'
        ).first()
        
        # Also try by transaction ID
        if not order:
            order = Order.objects.filter(
                paypal_txn_id=payment_id,
                status='processing'
            ).first()
        
        if order:
            # Mark order as completed
            order.status = 'completed'
            if not order.paypal_txn_id:
                order.paypal_txn_id = payment_id
            
            # Reset order_id for completed orders to get proper format
            if order.order_id.startswith('P'):
                order.order_id = ''
            order.save()
            
            # Process subscription (import here to avoid circular import)
            from .views import process_subscription_after_payment
            process_subscription_after_payment(order.user, order)
            
            # Send success email
            try:
                send_payment_success_email(order.id)
            except Exception as e:
                logger.error(f"Failed to send payment email: {e}")
            
            logger.info(f"Order {order.order_id} completed via webhook")
        else:
            logger.warning(f"No processing order found for payment ID: {payment_id}")
        
        return HttpResponse(status=200)
        
    except Exception as e:
        logger.error(f"Payment success handling error: {e}")
        return HttpResponse(status=500)

def handle_payment_failed(webhook_data):
    """Process failed payment from PayPal webhook"""
    try:
        resource = webhook_data.get('resource', {})
        payment_id = resource.get('id')
        
        logger.info(f"Webhook payment failed: ID={payment_id}")
        
        # Find and cancel order (check both pending and processing)
        order = Order.objects.filter(
            paypal_payment_id=payment_id,
            status__in=['pending', 'processing']
        ).first()
        
        if not order:
            order = Order.objects.filter(
                paypal_txn_id=payment_id,
                status__in=['pending', 'processing']
            ).first()
        
        if order:
            order.status = 'cancelled'
            order.save()
            logger.info(f"Order {order.order_id} cancelled due to payment failure")
        else:
            logger.warning(f"No order found for failed payment ID: {payment_id}")
        
        return HttpResponse(status=200)
        
    except Exception as e:
        logger.error(f"Payment failure handling error: {e}")
        return HttpResponse(status=500)

def handle_payment_cancelled(webhook_data):
    """Process cancelled payment from PayPal webhook"""
    try:
        resource = webhook_data.get('resource', {})
        payment_id = resource.get('id')
        
        logger.info(f"Webhook payment cancelled: ID={payment_id}")
        
        # Find and cancel order (check both pending and processing)
        order = Order.objects.filter(
            paypal_payment_id=payment_id,
            status__in=['pending', 'processing']
        ).first()
        
        if not order:
            order = Order.objects.filter(
                paypal_txn_id=payment_id,
                status__in=['pending', 'processing']
            ).first()
        
        if order:
            order.status = 'cancelled'
            order.save()
            logger.info(f"Order {order.order_id} cancelled via webhook")
        else:
            logger.warning(f"No order found for cancelled payment ID: {payment_id}")
        
        return HttpResponse(status=200)
        
    except Exception as e:
        logger.error(f"Payment cancellation handling error: {e}")
        return HttpResponse(status=500)
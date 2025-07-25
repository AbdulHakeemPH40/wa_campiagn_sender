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
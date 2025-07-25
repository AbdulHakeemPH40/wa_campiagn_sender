#!/usr/bin/env python
"""
Process the latest PayPal payment (6:22 AM, 25/07/2025)
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'wa_campiagn_sender.settings')
django.setup()

from userpanel.models import Order
from userpanel.views import process_subscription_after_payment
from userpanel.email_utils import send_payment_success_email
import logging

logger = logging.getLogger(__name__)

def process_latest_payment():
    """Process the latest PayPal payment"""
    
    payer_email = "abdulhakeemph@gmail.com"
    amount = 5.99
    
    print(f"Processing latest payment for {payer_email}")
    
    try:
        # Find the latest processing order for this user
        from sitevisitor.models import CustomUser
        user = CustomUser.objects.get(email=payer_email)
        
        # Find the latest pending order (from the 6:22 AM payment)
        order = Order.objects.filter(
            user=user,
            status='pending',
            total=amount
        ).order_by('-created_at').first()
        
        if not order:
            print("No pending order found! Available orders:")
            for o in Order.objects.filter(user=user).order_by('-created_at')[:5]:
                print(f"  Order {o.order_id}: ${o.total}, {o.status}, {o.created_at}")
            return
            
        print(f"Found order: {order.order_id} (Status: {order.status})")
        
        # Update order to completed and add transaction ID
        order.status = 'completed'
        order.paypal_txn_id = f"latest-{order.created_at.strftime('%Y%m%d%H%M%S')}"
        if order.order_id.startswith('P'):
            order.order_id = ''  # Reset for proper numbering
        order.save()
        
        print(f"Order updated: {order.order_id}")
        
        # Process subscription
        process_subscription_after_payment(order.user, order)
        print("Subscription processed")
        
        # Send success email
        try:
            send_payment_success_email(order.id)
            print("Success email sent")
        except Exception as e:
            print(f"Email failed: {e}")
            
        print("✅ Latest payment processed successfully!")
        
    except Exception as e:
        print(f"❌ Error processing payment: {e}")
        logger.error(f"Latest payment processing error: {e}")

if __name__ == "__main__":
    process_latest_payment()
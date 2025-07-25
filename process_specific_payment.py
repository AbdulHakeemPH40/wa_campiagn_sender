#!/usr/bin/env python
"""
Process specific PayPal payment: 0HU62431WC662344T
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

def process_specific_payment():
    """Process the specific PayPal transaction"""
    
    # PayPal transaction details
    transaction_id = "0HU62431WC662344T"
    payment_id = "PAYID-NCBZB4Y28J27710K4386280T"
    payer_email = "abdulhakeemph@gmail.com"
    amount = 5.99
    
    print(f"Processing PayPal transaction: {transaction_id}")
    
    try:
        from sitevisitor.models import CustomUser
        user = CustomUser.objects.get(email=payer_email)
        
        # Find the order - try multiple approaches
        order = None
        
        # Method 1: Find by payment ID
        order = Order.objects.filter(
            user=user,
            paypal_payment_id=payment_id,
            status__in=['pending', 'processing']
        ).first()
        
        # Method 2: Find latest pending/processing order with matching amount
        if not order:
            order = Order.objects.filter(
                user=user,
                total=amount,
                status__in=['pending', 'processing']
            ).order_by('-created_at').first()
        
        if not order:
            print("No matching order found! Available orders:")
            for o in Order.objects.filter(user=user).order_by('-created_at')[:5]:
                print(f"  Order {o.order_id}: ${o.total}, {o.status}, PayPal ID: {o.paypal_payment_id}")
            return
            
        print(f"Found order: {order.order_id} (Status: {order.status})")
        
        # Update order to completed
        order.status = 'completed'
        order.paypal_txn_id = transaction_id
        order.paypal_payment_id = payment_id
        
        # Reset order_id for proper numbering if it starts with P
        if order.order_id.startswith('P'):
            order.order_id = ''
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
            
        print("✅ Payment processed successfully!")
        print(f"Customer should now have PRO access!")
        
    except Exception as e:
        print(f"❌ Error processing payment: {e}")
        logger.error(f"Payment processing error: {e}")

if __name__ == "__main__":
    process_specific_payment()
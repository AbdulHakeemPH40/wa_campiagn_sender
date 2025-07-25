#!/usr/bin/env python
"""
Manual script to process held PayPal payment
Run this once to process the current held payment: 96A24009AX3522927
"""

import os
import sys
import django

# Setup Django - use development settings for local testing
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'wa_campiagn_sender.settings')
django.setup()

from userpanel.models import Order
from userpanel.views import process_subscription_after_payment
from userpanel.email_utils import send_payment_success_email
import logging

logger = logging.getLogger(__name__)

def process_held_payment():
    """Process the held PayPal payment manually"""
    
    # PayPal transaction details from your message
    transaction_id = "96A24009AX3522927"
    payment_id = "PAYID-NCBXL7I2WR069603N3533200"
    payer_email = "abdulhakeemph@gmail.com"
    amount = 5.99
    
    print(f"Processing held payment: {transaction_id}")
    
    try:
        # Find the order by PayPal payment ID or transaction ID
        order = Order.objects.filter(
            paypal_payment_id=payment_id,
            status='processing'
        ).first()
        
        if not order:
            order = Order.objects.filter(
                paypal_txn_id=transaction_id,
                status='processing'
            ).first()
            
        if not order:
            # Try to find by user email and pending status
            from sitevisitor.models import CustomUser
            try:
                user = CustomUser.objects.get(email=payer_email)
                order = Order.objects.filter(
                    user=user,
                    status__in=['pending', 'processing'],
                    total=amount
                ).order_by('-created_at').first()
            except CustomUser.DoesNotExist:
                print(f"User not found: {payer_email}")
                return
        
        if not order:
            print("No matching order found!")
            print("Available orders:")
            for o in Order.objects.filter(status__in=['pending', 'processing']).order_by('-created_at')[:5]:
                print(f"  Order {o.order_id}: {o.user.email}, ${o.total}, {o.status}")
            return
            
        print(f"Found order: {order.order_id} for {order.user.email}")
        
        # Update order status
        order.status = 'completed'
        order.paypal_txn_id = transaction_id
        if not order.paypal_payment_id:
            order.paypal_payment_id = payment_id
            
        # Reset order_id for completed orders
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
        
    except Exception as e:
        print(f"❌ Error processing payment: {e}")
        logger.error(f"Manual payment processing error: {e}")

if __name__ == "__main__":
    process_held_payment()
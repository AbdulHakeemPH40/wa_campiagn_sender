#!/usr/bin/env python
"""
Process specific PayPal payment - Python 2.7 compatible
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'wa_campiagn_sender.setting_pythonanywhere')
django.setup()

from userpanel.models import Order
from userpanel.views import process_subscription_after_payment

def process_specific_payment():
    """Process the specific PayPal transaction"""
    
    # PayPal transaction details
    transaction_id = "0HU62431WC662344T"
    payment_id = "PAYID-NCBZB4Y28J27710K4386280T"
    payer_email = "abdulhakeemph@gmail.com"
    amount = 5.99
    
    print("Processing PayPal transaction: " + transaction_id)
    
    try:
        from sitevisitor.models import CustomUser
        user = CustomUser.objects.get(email=payer_email)
        
        # Find latest processing order
        order = Order.objects.filter(
            user=user,
            total=amount,
            status__in=['pending', 'processing']
        ).order_by('-created_at').first()
        
        if not order:
            print("No matching order found! Available orders:")
            for o in Order.objects.filter(user=user).order_by('-created_at')[:5]:
                print("  Order {}: ${}, {}, PayPal ID: {}".format(
                    o.order_id, o.total, o.status, o.paypal_payment_id or 'None'))
            return
            
        print("Found order: {} (Status: {})".format(order.order_id, order.status))
        
        # Update order to completed
        order.status = 'completed'
        order.paypal_txn_id = transaction_id
        order.paypal_payment_id = payment_id
        
        # Reset order_id for proper numbering if it starts with P
        if order.order_id.startswith('P'):
            order.order_id = ''
        order.save()
        
        print("Order updated: " + order.order_id)
        
        # Process subscription
        process_subscription_after_payment(order.user, order)
        print("Subscription processed")
        
        print("Payment processed successfully!")
        print("Customer should now have PRO access!")
        
    except Exception as e:
        print("Error processing payment: " + str(e))

if __name__ == "__main__":
    process_specific_payment()
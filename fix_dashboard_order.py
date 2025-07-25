#!/usr/bin/env python
"""
Fix the specific order showing on dashboard: PBC725DDB
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

def fix_dashboard_order():
    """Fix the order showing on dashboard"""
    
    payer_email = "abdulhakeemph@gmail.com"
    dashboard_order_id = "PBC725DDB"
    
    print(f"Looking for order: {dashboard_order_id}")
    
    try:
        from sitevisitor.models import CustomUser
        user = CustomUser.objects.get(email=payer_email)
        
        # Find the specific order showing on dashboard
        order = Order.objects.filter(
            user=user,
            order_id=dashboard_order_id
        ).first()
        
        if not order:
            print(f"Order {dashboard_order_id} not found! Available orders:")
            for o in Order.objects.filter(user=user).order_by('-created_at')[:10]:
                print(f"  Order {o.order_id}: ${o.total}, {o.status}, Created: {o.created_at}")
            return
            
        print(f"Found order: {order.order_id} (Status: {order.status})")
        
        # Update order to completed
        order.status = 'completed'
        order.paypal_txn_id = "0HU62431WC662344T"  # Use the PayPal transaction ID
        order.save()
        
        print(f"Order {order.order_id} updated to: {order.status}")
        
        # Process subscription
        process_subscription_after_payment(order.user, order)
        print("Subscription processed")
        
        print("✅ Dashboard order fixed!")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    fix_dashboard_order()
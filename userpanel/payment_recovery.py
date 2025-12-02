"""
PayPal Payment Recovery System
Handles cases where payments succeed but subscription creation fails
"""

import logging
from django.utils import timezone
from django.db import transaction
from datetime import timedelta
from .models import Order, User
from adminpanel.models import Subscription

logger = logging.getLogger(__name__)

def recover_failed_subscriptions():
    """
    Recover payments that succeeded but didn't create subscriptions
    This function should be run periodically (e.g., via cron job or management command)
    """
    logger.info("Starting payment recovery process...")
    
    # Find completed orders without subscriptions from the last 24 hours
    cutoff_time = timezone.now() - timedelta(hours=24)
    
    orphaned_orders = Order.objects.filter(
        status='completed',
        created_at__gte=cutoff_time,
        payment_method='PayPal'
    ).exclude(
        user__subscription__isnull=False,
        user__subscription__status='active',
        user__subscription__end_date__gt=timezone.now()
    )
    
    recovery_count = 0
    error_count = 0
    
    for order in orphaned_orders:
        try:
            with transaction.atomic():
                # Check if user already has an active subscription (double-check)
                existing_subscription = Subscription.objects.filter(
                    user=order.user,
                    status='active',
                    end_date__gt=timezone.now()
                ).exists()
                
                if existing_subscription:
                    logger.info(f"User {order.user.email} already has active subscription, skipping order {order.order_id}")
                    continue
                
                # Attempt to process subscription
                from .views import process_subscription_after_payment
                process_subscription_after_payment(order.user, order)
                
                logger.info(f"Successfully recovered subscription for order {order.order_id} - User: {order.user.email}")
                recovery_count += 1
                
                # Send recovery notification email
                try:
                    from .email_utils import send_payment_success_email
                    send_payment_success_email(order.user, order)
                    logger.info(f"Recovery notification email sent to {order.user.email}")
                except Exception as e:
                    logger.error(f"Failed to send recovery email to {order.user.email}: {e}")
                
        except Exception as e:
            logger.error(f"Failed to recover subscription for order {order.order_id}: {e}", exc_info=True)
            error_count += 1
    
    logger.info(f"Payment recovery completed - Recovered: {recovery_count}, Errors: {error_count}")
    return {
        'recovered': recovery_count,
        'errors': error_count,
        'total_checked': len(orphaned_orders)
    }

def verify_paypal_payment_integrity():
    """
    Verify PayPal payment integrity by checking with PayPal API
    This helps detect any discrepancies between local records and PayPal
    """
    logger.info("Starting PayPal payment integrity verification...")
    
    from .paypal_utils import PayPalAPI
    paypal_api = PayPalAPI()
    
    # Check recent completed orders with PayPal payments
    cutoff_time = timezone.now() - timedelta(hours=72)  # Check last 3 days
    
    recent_paypal_orders = Order.objects.filter(
        status='completed',
        payment_method='PayPal',
        created_at__gte=cutoff_time,
        paypal_payment_id__isnull=False
    )
    
    verified_count = 0
    discrepancy_count = 0
    
    for order in recent_paypal_orders:
        try:
            # Verify with PayPal API
            if order.paypal_payment_id:
                order_details = paypal_api.get_order_details(order.paypal_payment_id)
                
                if order_details:
                    paypal_status = order_details.get('status')
                    paypal_amount = float(order_details['purchase_units'][0]['amount']['value'])
                    
                    # Check for discrepancies
                    if paypal_status != 'COMPLETED':
                        logger.warning(f"PayPal status mismatch - Order: {order.order_id}, Local: completed, PayPal: {paypal_status}")
                        discrepancy_count += 1
                    elif abs(float(order.total) - paypal_amount) > 0.01:
                        logger.warning(f"Amount mismatch - Order: {order.order_id}, Local: {order.total}, PayPal: {paypal_amount}")
                        discrepancy_count += 1
                    else:
                        verified_count += 1
                else:
                    logger.error(f"Could not verify PayPal order: {order.paypal_payment_id}")
                    discrepancy_count += 1
                    
        except Exception as e:
            logger.error(f"Error verifying PayPal payment for order {order.order_id}: {e}")
            discrepancy_count += 1
    
    logger.info(f"PayPal integrity verification completed - Verified: {verified_count}, Discrepancies: {discrepancy_count}")
    return {
        'verified': verified_count,
        'discrepancies': discrepancy_count,
        'total_checked': len(recent_paypal_orders)
    }

def cleanup_stale_pending_orders():
    """
    Clean up pending orders that are older than 24 hours
    These are likely abandoned payment attempts
    """
    logger.info("Starting cleanup of stale pending orders...")
    
    cutoff_time = timezone.now() - timedelta(hours=24)
    
    stale_orders = Order.objects.filter(
        status='pending',
        created_at__lt=cutoff_time
    )
    
    cleanup_count = stale_orders.count()
    
    # Update status to cancelled instead of deleting
    stale_orders.update(
        status='cancelled',
        updated_at=timezone.now()
    )
    
    logger.info(f"Cleaned up {cleanup_count} stale pending orders")
    return cleanup_count

def generate_payment_recovery_report():
    """
    Generate a comprehensive report of payment recovery activities
    """
    logger.info("Generating payment recovery report...")
    
    # Run all recovery functions
    subscription_recovery = recover_failed_subscriptions()
    integrity_check = verify_paypal_payment_integrity()
    cleanup_count = cleanup_stale_pending_orders()
    
    # Generate summary statistics
    cutoff_time = timezone.now() - timedelta(hours=24)
    
    stats = {
        'timestamp': timezone.now(),
        'subscription_recovery': subscription_recovery,
        'integrity_verification': integrity_check,
        'stale_orders_cleaned': cleanup_count,
        'recent_stats': {
            'completed_orders': Order.objects.filter(
                status='completed',
                created_at__gte=cutoff_time
            ).count(),
            'pending_orders': Order.objects.filter(
                status='pending',
                created_at__gte=cutoff_time
            ).count(),
            'active_subscriptions': Subscription.objects.filter(
                status='active',
                end_date__gt=timezone.now()
            ).count(),
        }
    }
    
    logger.info(f"Payment recovery report generated: {stats}")
    return stats

# Utility functions for manual recovery operations

def recover_specific_order(order_id):
    """
    Manually recover a specific order by order ID
    """
    try:
        order = Order.objects.get(order_id=order_id, status='completed')
        
        # Check if user already has subscription
        existing_subscription = Subscription.objects.filter(
            user=order.user,
            status='active',
            end_date__gt=timezone.now()
        ).exists()
        
        if existing_subscription:
            return {'success': False, 'error': 'User already has active subscription'}
        
        # Process subscription
        from .views import process_subscription_after_payment
        process_subscription_after_payment(order.user, order)
        
        logger.info(f"Manually recovered subscription for order {order_id}")
        return {'success': True, 'message': f'Successfully recovered subscription for order {order_id}'}
        
    except Order.DoesNotExist:
        return {'success': False, 'error': 'Order not found or not completed'}
    except Exception as e:
        logger.error(f"Manual recovery failed for order {order_id}: {e}")
        return {'success': False, 'error': str(e)}

def check_user_payment_status(user_email):
    """
    Check payment and subscription status for a specific user
    """
    try:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user = User.objects.get(email=user_email)
        
        # Get user's orders
        orders = Order.objects.filter(user=user).order_by('-created_at')
        
        # Get user's subscriptions
        subscriptions = Subscription.objects.filter(user=user).order_by('-created_at')
        
        status = {
            'user_email': user_email,
            'orders': [
                {
                    'order_id': order.order_id,
                    'status': order.status,
                    'total': str(order.total),
                    'payment_method': order.payment_method,
                    'created_at': order.created_at,
                    'paypal_payment_id': order.paypal_payment_id
                }
                for order in orders[:5]  # Last 5 orders
            ],
            'subscriptions': [
                {
                    'status': sub.status,
                    'created_at': sub.created_at,
                    'end_date': sub.end_date,
                    'plan': sub.plan.name if sub.plan else 'No Plan'
                }
                for sub in subscriptions[:3]  # Last 3 subscriptions
            ],
            'has_active_subscription': subscriptions.filter(
                status='active',
                end_date__gt=timezone.now()
            ).exists()
        }
        
        return status
        
    except User.DoesNotExist:
        return {'error': 'User not found'}
    except Exception as e:
        logger.error(f"Error checking user payment status for {user_email}: {e}")
        return {'error': str(e)}

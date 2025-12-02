from paypal.standard.models import ST_PP_COMPLETED
from paypal.standard.ipn.signals import valid_ipn_received
from django.dispatch import receiver
from .models import Order
import logging
from django.utils import timezone
from datetime import timedelta
from adminpanel.models import Subscription, Payment
from .email_utils import send_payment_success_email, send_payment_failure_email # Import synchronous email functions

logger = logging.getLogger(__name__)

@receiver(valid_ipn_received)
def paypal_payment_received(sender, **kwargs):
    ipn_obj = sender
    logger.info(f"IPN received. Status: {ipn_obj.payment_status}, Invoice: {ipn_obj.invoice}")

    if ipn_obj.payment_status == ST_PP_COMPLETED:
        invoice_id = ipn_obj.invoice
        try:
            order = Order.objects.get(order_id=invoice_id)
            order_items = order.items.all()

            # --- Security and Duplication Checks ---
            if order.status == 'completed':
                logger.warning(f"IPN for already completed order {invoice_id} received. Ignoring.")
                return

            if str(order.total) != str(ipn_obj.mc_gross):
                logger.error(f"Payment amount mismatch for order {invoice_id}. Expected {order.total}, got {ipn_obj.mc_gross}")
                order.status = 'failed'
                order.save()
                return

            if ipn_obj.mc_currency != 'USD':
                logger.error(f"Invalid currency for order {invoice_id}. Expected USD, got {ipn_obj.mc_currency}")
                order.status = 'failed'
                order.save()
                return

            # --- Process the successful payment ---
            order.status = 'completed'
            order.paypal_txn_id = ipn_obj.txn_id
            order.save()

            # --- Process Subscription ---
            # This assumes the first item in the order defines the subscription
            order_item = order.items.first()
            if order_item:
                product_name = order_item.product_name.lower()
                duration_days = None
                if "1 month" in product_name:
                    duration_days = 30
                elif "6 months" in product_name:
                    duration_days = 180
                elif "1 year" in product_name:
                    duration_days = 365

                if duration_days:
                    # Deactivate any existing subscriptions for the user before creating a new one
                    Subscription.objects.filter(user=order.user, is_active=True).update(is_active=False)
                    
                    # Create the new subscription
                    start_date = timezone.now()
                    end_date = start_date + timedelta(days=duration_days)
                    
                    Subscription.objects.create(
                        user=order.user,
                        order=order,
                        start_date=start_date,
                        end_date=end_date,
                        is_active=True
                    )
                    logger.info(f"Subscription for {duration_days} days created for user {order.user.email}")
                else:
                    logger.warning(f"Could not determine subscription duration for order {invoice_id} with product '{order_item.product_name}'")
            else:
                logger.error(f"Order {invoice_id} has no items, cannot create subscription.")

            # Create a formal payment record for admin tracking
            Payment.objects.create(
                user=order.user,
                order=order,
                amount=order.total,
                payment_method='paypal',
                transaction_id=ipn_obj.txn_id,
                status='completed'
            )

            # Send a success email to the user
            try:
                send_payment_success_email(order.user, order)
            except Exception as e:
                logger.error(f"Failed to send success email for order {invoice_id}: {e}")

            logger.info(f"Successfully processed order {invoice_id}.")

        except Order.DoesNotExist:
            logger.error(f"CRITICAL: Received IPN for non-existent order with invoice ID {invoice_id}.")
        except Exception as e:
            logger.error(f"An unexpected error occurred while processing order {invoice_id}: {e}")

    else:
        logger.warning(f"IPN received with non-completed status: {ipn_obj.payment_status}")
        # Call Celery task to send failure/issue email
        # Ensure ipn_obj.payer_email is available and valid
        user_email_for_failure = ipn_obj.payer_email or (Order.objects.get(order_id=ipn_obj.invoice).user.email if Order.objects.filter(order_id=ipn_obj.invoice).exists() else None)
        if user_email_for_failure:
            send_payment_failure_email(
                user_email=user_email_for_failure,
                order_invoice_id=ipn_obj.invoice,
                payment_status=ipn_obj.payment_status,
                reason=ipn_obj.pending_reason or ""
            )
        else:
            logger.error(f"Could not determine user email for failed payment IPN: {ipn_obj.invoice}")


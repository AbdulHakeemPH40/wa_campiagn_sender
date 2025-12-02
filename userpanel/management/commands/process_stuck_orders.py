from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from userpanel.models import Order
from userpanel.views import process_subscription_after_payment
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Process orders stuck in processing status for more than 10 minutes'

    def handle(self, *args, **options):
        # Find orders stuck in processing for more than 10 minutes
        cutoff_time = timezone.now() - timedelta(minutes=10)
        stuck_orders = Order.objects.filter(
            status='processing',
            updated_at__lt=cutoff_time,
            paypal_txn_id__isnull=False  # Has PayPal transaction
        )

        processed_count = 0
        for order in stuck_orders:
            try:
                # Update to completed
                order.status = 'completed'
                if order.order_id.startswith('P'):
                    order.order_id = ''  # Reset for proper numbering
                order.save()

                # Process subscription
                process_subscription_after_payment(order.user, order)
                
                processed_count += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        'Processed stuck order: {} for {}'.format(
                            order.order_id, order.user.email
                        )
                    )
                )
                logger.info('Auto-processed stuck order: {} for {}'.format(
                    order.order_id, order.user.email
                ))
                
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        'Failed to process order {}: {}'.format(order.order_id, e)
                    )
                )
                logger.error('Failed to auto-process order {}: {}'.format(
                    order.order_id, e
                ))

        if processed_count > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    'Successfully processed {} stuck orders'.format(processed_count)
                )
            )
        else:
            self.stdout.write('No stuck orders found')
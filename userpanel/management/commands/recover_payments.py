"""
Django management command for PayPal payment recovery
Usage: python manage.py recover_payments [--full-report] [--verify-integrity] [--cleanup-only]
"""

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Recover failed PayPal payments and subscriptions'

    def add_arguments(self, parser):
        parser.add_argument(
            '--full-report',
            action='store_true',
            help='Generate full payment recovery report',
        )
        parser.add_argument(
            '--verify-integrity',
            action='store_true',
            help='Verify PayPal payment integrity with API',
        )
        parser.add_argument(
            '--cleanup-only',
            action='store_true',
            help='Only cleanup stale pending orders',
        )
        parser.add_argument(
            '--order-id',
            type=str,
            help='Recover specific order by ID',
        )
        parser.add_argument(
            '--user-email',
            type=str,
            help='Check payment status for specific user',
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS(f'Starting PayPal payment recovery at {timezone.now()}')
        )

        try:
            from userpanel.payment_recovery import (
                recover_failed_subscriptions,
                verify_paypal_payment_integrity,
                cleanup_stale_pending_orders,
                generate_payment_recovery_report,
                recover_specific_order,
                check_user_payment_status
            )

            # Handle specific order recovery
            if options['order_id']:
                result = recover_specific_order(options['order_id'])
                if result['success']:
                    self.stdout.write(
                        self.style.SUCCESS(f"✅ {result['message']}")
                    )
                else:
                    self.stdout.write(
                        self.style.ERROR(f"❌ {result['error']}")
                    )
                return

            # Handle user status check
            if options['user_email']:
                status = check_user_payment_status(options['user_email'])
                if 'error' in status:
                    self.stdout.write(
                        self.style.ERROR(f"❌ {status['error']}")
                    )
                else:
                    self.stdout.write(
                        self.style.SUCCESS(f"📊 User Status for {status['user_email']}:")
                    )
                    self.stdout.write(f"  Active Subscription: {status['has_active_subscription']}")
                    self.stdout.write(f"  Recent Orders: {len(status['orders'])}")
                    self.stdout.write(f"  Recent Subscriptions: {len(status['subscriptions'])}")
                    
                    for order in status['orders'][:3]:
                        self.stdout.write(f"    Order {order['order_id']}: {order['status']} - ${order['total']}")
                return

            # Handle cleanup only
            if options['cleanup_only']:
                cleanup_count = cleanup_stale_pending_orders()
                self.stdout.write(
                    self.style.SUCCESS(f"🧹 Cleaned up {cleanup_count} stale pending orders")
                )
                return

            # Handle full report
            if options['full_report']:
                report = generate_payment_recovery_report()
                self.stdout.write(
                    self.style.SUCCESS('📈 Full Payment Recovery Report:')
                )
                self.stdout.write(f"  Subscription Recovery:")
                self.stdout.write(f"    ✅ Recovered: {report['subscription_recovery']['recovered']}")
                self.stdout.write(f"    ❌ Errors: {report['subscription_recovery']['errors']}")
                self.stdout.write(f"    📊 Total Checked: {report['subscription_recovery']['total_checked']}")
                
                self.stdout.write(f"  Integrity Verification:")
                self.stdout.write(f"    ✅ Verified: {report['integrity_verification']['verified']}")
                self.stdout.write(f"    ⚠️ Discrepancies: {report['integrity_verification']['discrepancies']}")
                
                self.stdout.write(f"  Cleanup:")
                self.stdout.write(f"    🧹 Stale Orders Cleaned: {report['stale_orders_cleaned']}")
                
                self.stdout.write(f"  Recent Statistics:")
                self.stdout.write(f"    📦 Completed Orders (24h): {report['recent_stats']['completed_orders']}")
                self.stdout.write(f"    ⏳ Pending Orders (24h): {report['recent_stats']['pending_orders']}")
                self.stdout.write(f"    🎯 Active Subscriptions: {report['recent_stats']['active_subscriptions']}")
                return

            # Handle integrity verification only
            if options['verify_integrity']:
                result = verify_paypal_payment_integrity()
                self.stdout.write(
                    self.style.SUCCESS(f"🔍 PayPal Integrity Verification:")
                )
                self.stdout.write(f"  ✅ Verified: {result['verified']}")
                self.stdout.write(f"  ⚠️ Discrepancies: {result['discrepancies']}")
                self.stdout.write(f"  📊 Total Checked: {result['total_checked']}")
                return

            # Default: Run subscription recovery only
            result = recover_failed_subscriptions()
            self.stdout.write(
                self.style.SUCCESS(f"🔄 Subscription Recovery Results:")
            )
            self.stdout.write(f"  ✅ Recovered: {result['recovered']}")
            self.stdout.write(f"  ❌ Errors: {result['errors']}")
            self.stdout.write(f"  📊 Total Checked: {result['total_checked']}")

            if result['recovered'] > 0:
                self.stdout.write(
                    self.style.SUCCESS(f"🎉 Successfully recovered {result['recovered']} subscriptions!")
                )
            elif result['total_checked'] == 0:
                self.stdout.write(
                    self.style.SUCCESS("✨ No orphaned payments found - all systems healthy!")
                )
            else:
                self.stdout.write(
                    self.style.WARNING("⚠️ No recoverable payments found, but some orders were checked.")
                )

        except Exception as e:
            logger.error(f"Payment recovery command failed: {e}", exc_info=True)
            raise CommandError(f'Payment recovery failed: {e}')

        self.stdout.write(
            self.style.SUCCESS(f'Payment recovery completed at {timezone.now()}')
        )

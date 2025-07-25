from django.core.management.base import BaseCommand
from adminpanel.models import SubscriptionPlan
from decimal import Decimal

class Command(BaseCommand):
    help = 'Updates subscription plan prices in the database'

    def handle(self, *args, **options):
        # Define the new pricing structure
        pricing_updates = [
            {'duration_days': 30, 'old_price': '19.99', 'new_price': '5.99'},
            {'duration_days': 180, 'old_price': '59.00', 'new_price': '29.95'},
            {'duration_days': 365, 'old_price': '99.00', 'new_price': '59.00'},
        ]
        
        updated_count = 0
        
        for update in pricing_updates:
            duration = update['duration_days']
            new_price = Decimal(update['new_price'])
            
            # Find plans with this duration
            plans = SubscriptionPlan.objects.filter(duration_days=duration, is_active=True)
            
            if plans.exists():
                for plan in plans:
                    old_price = plan.price
                    plan.price = new_price
                    plan.save()
                    updated_count += 1
                    self.stdout.write(self.style.SUCCESS(
                        f'Updated plan "{plan.name}" from ${old_price} to ${new_price}'
                    ))
            else:
                self.stdout.write(self.style.WARNING(
                    f'No active plans found with duration {duration} days'
                ))
        
        if updated_count == 0:
            self.stdout.write(self.style.WARNING('No subscription plans were updated'))
        else:
            self.stdout.write(self.style.SUCCESS(f'Successfully updated {updated_count} subscription plans'))
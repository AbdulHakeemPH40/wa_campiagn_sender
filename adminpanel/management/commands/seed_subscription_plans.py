from decimal import Decimal

from django.core.management.base import BaseCommand

from adminpanel.models import SubscriptionPlan


DEFAULT_PLANS = [
    {
        "name": "1 Month Plan",
        "description": "Full features, billed monthly. Limited Period Offer!",
        "price": Decimal("5.99"),
        "duration_days": 30,
        "features": "3 WhatsApp Accounts\nUnlimited Messages Per Day\nRandom Send Interval\nReal-Time Sending Progress",
    },
    {
        "name": "6 Month Plan",
        "description": "Unlock all features for half a year. Limited Period Offer!",
        "price": Decimal("29.95"),
        "duration_days": 180,
        "features": "6 WhatsApp Accounts\nUnlimited Messages Per Day\nRandom Send Interval\nReal-Time Sending Progress",
    },
    {
        "name": "1 Year Plan",
        "description": "Unlock all features for a full year. Limited Period Offer!",
        "price": Decimal("59.00"),
        "duration_days": 365,
        "features": "10 WhatsApp Accounts\nUnlimited Messages Per Day\nRandom Send Interval\nReal-Time Sending Progress",
    },
]


class Command(BaseCommand):
    """Seed the database with default SubscriptionPlan records.

    Usage::
        python manage.py seed_subscription_plans
    """

    help = "Create or update default subscription plans (1 month, 6 months, 1 year)."

    def handle(self, *args, **options):
        for plan_data in DEFAULT_PLANS:
            obj, created = SubscriptionPlan.objects.update_or_create(
                duration_days=plan_data["duration_days"],
                defaults={
                    "name": plan_data["name"],
                    "description": plan_data["description"],
                    "price": plan_data["price"],
                    "features": plan_data["features"],
                    "is_active": True,
                },
            )
            status = "Created" if created else "Updated"
            self.stdout.write(self.style.SUCCESS(f"{status}: {obj.name} (${obj.price})"))

        self.stdout.write(self.style.SUCCESS("Subscription plans seeding complete."))

import datetime
from django.core.management.base import BaseCommand
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
from django.utils import timezone
from sitevisitor.models import Profile, WhatsAppNumber # Import WhatsAppNumber
from adminpanel.models import Subscription # Import Subscription model
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Sends pro version subscription expiration reminder emails to users one day before their subscription ends and handles expired subscriptions.'

    def handle(self, *args, **options):
        today = timezone.now().date()

        # Guard: if Profile model lacks subscription_end_date, exit gracefully
        # Note: This check might be better placed to check for the Subscription model directly
        if not hasattr(Profile, 'subscription_end_date'):
            self.stdout.write(self.style.WARNING("Profile model has no 'subscription_end_date' field. Pro subscription reminder skipped."))
            # Attempt to check if Subscription model exists and has end_date
            if not hasattr(Subscription, 'end_date'):
                self.stdout.write(self.style.ERROR("Neither Profile.subscription_end_date nor Subscription.end_date found. Cannot process expiration."))
                return
            else:
                self.stdout.write(self.style.WARNING("Using Subscription.end_date for expiration checks."))
        
        # --- Handle subscriptions expiring tomorrow (for reminders) ---
        tomorrow = today + datetime.timedelta(days=1)
        
        # Using Subscription model for more accurate expiration tracking
        expiring_subscriptions_for_reminders = Subscription.objects.filter(
            end_date=tomorrow,
            status='active' # Only send reminders for active subscriptions
        )

        self.stdout.write(f"Checking for pro subscriptions expiring on {tomorrow.strftime('%Y-%m-%d')} for reminders...")

        emails_sent_count = 0
        for subscription in expiring_subscriptions_for_reminders:
            user = subscription.user
            profile = user.profile # Assuming user always has a profile
            
            subject = "Your Pro Version Subscription Ends Tomorrow!"
            from_email = settings.DEFAULT_FROM_EMAIL
            recipient_list = [user.email]

            email_context = {
                'user': user,
                'subscription_end_date': subscription.end_date,
                'current_year': datetime.datetime.now().year,
                'domain': 'www.wacampaignsender.com',
            }
            html_content = render_to_string('userpanel/email/pro_version_reminder.html', email_context)
            text_content = (
                f"Dear {user.full_name},\n\n"
                "This is a friendly reminder that your Pro Version subscription for WA Campaign Sender "
                f"will expire tomorrow, on {subscription.end_date.strftime('%Y-%m-%d')}.\n\n"
                "To ensure uninterrupted access to all premium features, please renew your subscription today!\n\n"
                f"Renew your plan here: https://{email_context['domain']}/userpanel/pricing/\n\n"
                "If you have any questions, feel free to contact our support team.\n\n"
                "Best regards,\n"
                "The WA Campaign Sender Team"
            )

            try:
                msg = EmailMultiAlternatives(subject, text_content, from_email, recipient_list)
                msg.attach_alternative(html_content, "text/html")
                msg.send(fail_silently=False)
                self.stdout.write(self.style.SUCCESS(f"Successfully sent pro reminder email to {user.email}"))
                emails_sent_count += 1
            except Exception as e:
                logger.error(f"Failed to send pro version expiration email to {user.email}: {e}")
                self.stdout.write(self.style.ERROR(f"Failed to send pro reminder email to {user.email}: {e}"))

        self.stdout.write(self.style.SUCCESS(f"Finished sending pro version reminders. Total emails sent: {emails_sent_count}"))

        # --- Handle subscriptions that have expired (for number removal) ---
        # Filter for subscriptions that ended today or in the past and are no longer active
        # We also need to ensure the user's profile has a subscription_end_date for this logic to work correctly
        # or rely solely on the Subscription model's end_date and status.
        
        # Let's use the Subscription model directly for expiration logic
        expired_subscriptions_for_removal = Subscription.objects.filter(
            end_date__lte=today, # Ended today or in the past
            status='active' # Still marked as active, but should be expired. This needs to be handled by a separate process that updates subscription status.
                            # For now, let's assume 'active' means it just expired today.
        ).exclude(
            user__subscription__status='active' # Exclude users who have renewed and have a new active subscription
        )
        # A more robust solution would be to have a separate command or a signal that sets subscription.status to 'expired'
        # when end_date is past. For this task, I'll assume that if end_date <= today and there's no *other* active subscription, it's expired.

        self.stdout.write(f"\nChecking for expired pro subscriptions on {today.strftime('%Y-%m-%d')} for number removal...")

        numbers_removed_count = 0
        for subscription in expired_subscriptions_for_removal:
            user = subscription.user
            profile = user.profile # Get the profile associated with the user
            
            # Check if the user has any *other* active subscriptions. If so, don't remove numbers.
            # This handles cases where a user might have multiple subscriptions or renewed.
            if Subscription.objects.filter(user=user, status='active', end_date__gt=today).exists():
                self.stdout.write(self.style.NOTICE(f"User {user.email} has another active subscription. Skipping number removal."))
                continue

            # Get all non-primary WhatsApp numbers for this user's profile
            non_primary_numbers = WhatsAppNumber.objects.filter(profile=profile, is_primary=False)
            
            if non_primary_numbers.exists():
                self.stdout.write(self.style.WARNING(f"Removing additional WhatsApp numbers for user {user.email} (Profile ID: {profile.id}) due to subscription expiration."))
                for number_obj in non_primary_numbers:
                    number_obj.delete()
                    numbers_removed_count += 1
                    self.stdout.write(self.style.NOTICE(f"  - Removed number: {number_obj.number}"))
            else:
                self.stdout.write(self.style.SUCCESS(f"No additional WhatsApp numbers to remove for user {user.email} (Profile ID: {profile.id})."))

        self.stdout.write(self.style.SUCCESS(f"Finished handling expired subscriptions. Total additional numbers removed: {numbers_removed_count}"))

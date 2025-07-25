import datetime
from django.core.management.base import BaseCommand
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
from django.utils import timezone
from sitevisitor.models import Profile
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Sends free trial expiration reminder emails to users one day before their trial ends.'

    def handle(self, *args, **options):
        today = timezone.now().date()
        tomorrow = today + datetime.timedelta(days=1)

        # Query only by free_trial_end. We will check subscription status in Python because
        # `has_active_subscription` is a computed @property, not a real DB field.
        expiring_trials = Profile.objects.filter(
            free_trial_end=tomorrow
        )

        self.stdout.write(f"Checking for free trials expiring on {tomorrow.strftime('%Y-%m-%d')}...")

        emails_sent_count = 0
        # Further filter in Python to skip users who already converted to paid plans
        expiring_trials = [p for p in expiring_trials if not p.has_active_subscription]

        for profile in expiring_trials:
            user = profile.user
            if profile.on_free_trial:
                subject = "Your Free Trial Ends Tomorrow - Don't Miss Out!"
                from_email = settings.DEFAULT_FROM_EMAIL
                recipient_list = [user.email]

                email_context = {
                    'user': user,
                    'free_trial_end': profile.free_trial_end,
                    'current_year': datetime.datetime.now().year,
                    'domain': 'www.wacampaignsender.com', 
                }

                html_content = render_to_string('userpanel/email/free_trial_reminder.html', email_context)
                text_content = (
                    f"Dear {user.full_name},\n\n"
                    "This is a friendly reminder that your 14-day free trial for WA Campaign Sender "
                    f"will expire tomorrow, on {profile.free_trial_end.strftime('%Y-%m-%d')}.\n\n"
                    "Don't let your access to premium features run out! "
                    "Upgrade to a paid plan today to continue enjoying uninterrupted service and all our powerful tools.\n\n"
                    f"Click here to renew your plan: https://{email_context['domain']}/userpanel/pricing/\n\n"
                    "If you have any questions, please contact our support team.\n\n"
                    "Best regards,\n"
                    "The WA Campaign Sender Team"
                )

                try:
                    msg = EmailMultiAlternatives(subject, text_content, from_email, recipient_list)
                    msg.attach_alternative(html_content, "text/html")
                    msg.send(fail_silently=False)
                    self.stdout.write(self.style.SUCCESS(f"Successfully sent reminder email to {user.email}"))
                    emails_sent_count += 1
                except Exception as e:
                    logger.error(f"Failed to send free trial expiration email to {user.email}: {e}")
                    self.stdout.write(self.style.ERROR(f"Failed to send reminder email to {user.email}: {e}"))
            else:
                self.stdout.write(f"Skipping {user.email}: Not currently on free trial despite free_trial_end date.")

        self.stdout.write(self.style.SUCCESS(f"Finished sending free trial reminders. Total emails sent: {emails_sent_count}"))

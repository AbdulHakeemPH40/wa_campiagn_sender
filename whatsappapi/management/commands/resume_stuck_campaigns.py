"""
Management command to resume stuck campaigns after PythonAnywhere downtime.

Usage:
    python manage.py resume_stuck_campaigns           # Resume all stuck campaigns
    python manage.py resume_stuck_campaigns --dry-run # Preview without resuming
    python manage.py resume_stuck_campaigns --campaign-id=123  # Resume specific campaign
"""

import logging
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction

from userpanel.models import WASenderCampaign, WASenderMessage, WASenderSession
from whatsappapi.models import Contact

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Resume campaigns that were stuck due to server downtime'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview stuck campaigns without resuming them',
        )
        parser.add_argument(
            '--campaign-id',
            type=int,
            help='Resume a specific campaign by ID',
        )
        parser.add_argument(
            '--stuck-threshold-minutes',
            type=int,
            default=15,
            help='Consider campaign stuck if no activity for this many minutes (default: 15)',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force resume even if campaign was recently active',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        campaign_id = options['campaign_id']
        stuck_threshold = options['stuck_threshold_minutes']
        force = options['force']

        self.stdout.write(self.style.NOTICE(f"\n{'='*60}"))
        self.stdout.write(self.style.NOTICE("STUCK CAMPAIGN RESUME TOOL"))
        self.stdout.write(self.style.NOTICE(f"{'='*60}\n"))

        if dry_run:
            self.stdout.write(self.style.WARNING("🔍 DRY RUN MODE - No changes will be made\n"))

        # Find stuck campaigns
        stuck_campaigns = self._find_stuck_campaigns(campaign_id, stuck_threshold, force)

        if not stuck_campaigns:
            self.stdout.write(self.style.SUCCESS("✅ No stuck campaigns found!"))
            return

        self.stdout.write(f"Found {len(stuck_campaigns)} stuck campaign(s):\n")

        for campaign in stuck_campaigns:
            self._analyze_campaign(campaign, dry_run)

    def _find_stuck_campaigns(self, campaign_id, stuck_threshold, force):
        """Find campaigns that appear to be stuck"""
        
        threshold_time = timezone.now() - timedelta(minutes=stuck_threshold)
        
        # Base query: campaigns with status 'running'
        queryset = WASenderCampaign.objects.filter(status='running')
        
        if campaign_id:
            queryset = queryset.filter(id=campaign_id)
        
        if not force:
            # Only get campaigns that haven't been updated recently
            queryset = queryset.filter(updated_at__lt=threshold_time)
        
        return list(queryset.select_related('user', 'session', 'contact_list'))

    def _analyze_campaign(self, campaign, dry_run):
        """Analyze a stuck campaign and optionally resume it"""
        
        self.stdout.write(f"\n{'-'*50}")
        self.stdout.write(f"Campaign: {campaign.name} (ID: {campaign.id})")
        self.stdout.write(f"User: {campaign.user.email}")
        self.stdout.write(f"Status: {campaign.status}")
        self.stdout.write(f"Started: {campaign.started_at}")
        self.stdout.write(f"Last Updated: {campaign.updated_at}")
        self.stdout.write(f"Total Recipients: {campaign.total_recipients}")
        self.stdout.write(f"Messages Sent: {campaign.messages_sent}")
        self.stdout.write(f"Messages Failed: {campaign.messages_failed}")
        
        if campaign.use_advanced_controls:
            self.stdout.write(f"Batch Progress: {campaign.current_batch}/{campaign.total_batches}")
            self.stdout.write(f"Cooldown Status: {campaign.cooldown_status or 'None'}")
        
        # Check session status
        session = campaign.session
        if not session:
            self.stdout.write(self.style.ERROR("❌ No session assigned - cannot resume"))
            return
        
        self.stdout.write(f"Session: {session.session_name} ({session.status})")
        
        # Count messages already sent for this campaign
        sent_messages = WASenderMessage.objects.filter(
            metadata__campaign_id=campaign.id,
            status__in=['sent', 'delivered', 'read']
        )
        sent_phones = set(sent_messages.values_list('recipient', flat=True))
        
        self.stdout.write(f"Already sent to {len(sent_phones)} unique recipients")
        
        # Get total contacts in contact list
        if campaign.contact_list:
            total_contacts = Contact.objects.filter(contact_list=campaign.contact_list).count()
            remaining = total_contacts - len(sent_phones)
            self.stdout.write(f"Remaining contacts: {remaining}/{total_contacts}")
        else:
            remaining = 0
            self.stdout.write(self.style.WARNING("⚠️ No contact list assigned"))
        
        if remaining <= 0:
            self.stdout.write(self.style.SUCCESS("✅ All contacts already processed - marking as completed"))
            if not dry_run:
                campaign.status = 'completed'
                campaign.completed_at = timezone.now()
                campaign.save()
            return
        
        # Resume the campaign
        if dry_run:
            self.stdout.write(self.style.WARNING(f"🔄 WOULD RESUME: {remaining} contacts remaining"))
        else:
            self._resume_campaign(campaign, sent_phones)

    def _resume_campaign(self, campaign, already_sent_phones):
        """Actually resume a stuck campaign"""
        
        self.stdout.write(self.style.NOTICE(f"\n🚀 Resuming campaign {campaign.id}..."))
        
        # Reset campaign to pending so it can be picked up again
        with transaction.atomic():
            campaign.status = 'pending'
            campaign.cooldown_remaining = 0
            campaign.cooldown_status = None
            campaign.save(update_fields=['status', 'cooldown_remaining', 'cooldown_status', 'updated_at'])
        
        self.stdout.write(self.style.SUCCESS(f"✅ Campaign {campaign.id} reset to 'pending'"))
        
        # Queue the campaign task
        try:
            from django_q.tasks import async_task
            from whatsappapi.tasks import send_campaign_async
            
            task_id = async_task(
                send_campaign_async,
                campaign.id,
                task_name=f"resume_campaign_{campaign.id}",
                hook='whatsappapi.tasks.campaign_complete_hook' if hasattr(send_campaign_async, 'campaign_complete_hook') else None
            )
            
            campaign.task_id = task_id
            campaign.save(update_fields=['task_id'])
            
            self.stdout.write(self.style.SUCCESS(f"✅ Campaign queued with task ID: {task_id}"))
            self.stdout.write(self.style.NOTICE(
                f"ℹ️  The task will skip {len(already_sent_phones)} already-sent contacts automatically "
                f"(duplicate prevention in send_campaign_async)"
            ))
            
        except ImportError:
            self.stdout.write(self.style.ERROR(
                "❌ Django-Q not available. Campaign reset to 'pending' but not queued.\n"
                "   Run manually or ensure Django-Q worker is running."
            ))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Failed to queue task: {e}"))

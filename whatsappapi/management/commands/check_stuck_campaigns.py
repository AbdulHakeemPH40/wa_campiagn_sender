"""
Scheduled task to check and resume stuck campaigns.
Run this every 5-10 minutes via PythonAnywhere Scheduled Tasks.

Usage (PythonAnywhere Scheduled Task):
    cd /home/yourusername/wa_campiagn_sender && /home/yourusername/.virtualenvs/your-venv/bin/python manage.py check_stuck_campaigns

This is a lightweight check that:
1. Finds campaigns stuck in 'running' status
2. Resets them to 'pending' 
3. Re-queues them for processing
4. Existing duplicate prevention ensures no messages are re-sent
"""

import logging
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction, close_old_connections

from userpanel.models import WASenderCampaign

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Check for stuck campaigns and resume them (run via scheduled task)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--stuck-minutes',
            type=int,
            default=10,
            help='Consider campaign stuck if no update for this many minutes (default: 10)',
        )
        parser.add_argument(
            '--quiet',
            action='store_true',
            help='Only output if stuck campaigns found',
        )

    def handle(self, *args, **options):
        stuck_minutes = options['stuck_minutes']
        quiet = options['quiet']
        
        # Ensure fresh database connection
        close_old_connections()
        
        threshold = timezone.now() - timedelta(minutes=stuck_minutes)
        
        # Find stuck campaigns
        stuck_campaigns = WASenderCampaign.objects.filter(
            status='running',
            updated_at__lt=threshold
        ).select_related('user', 'session')
        
        count = stuck_campaigns.count()
        
        if count == 0:
            if not quiet:
                self.stdout.write(f"[{timezone.now()}] ✅ No stuck campaigns")
            return
        
        self.stdout.write(self.style.WARNING(
            f"[{timezone.now()}] 🔄 Found {count} stuck campaign(s) - resuming..."
        ))
        
        resumed = 0
        failed = 0
        
        for campaign in stuck_campaigns:
            try:
                # Check if session is still valid
                if not campaign.session:
                    self.stdout.write(self.style.ERROR(
                        f"  ❌ Campaign {campaign.id} has no session - marking as failed"
                    ))
                    campaign.status = 'failed'
                    campaign.save(update_fields=['status'])
                    failed += 1
                    continue
                
                # Log campaign details
                self.stdout.write(f"  📋 Campaign {campaign.id}: {campaign.name}")
                self.stdout.write(f"     User: {campaign.user.email}")
                self.stdout.write(f"     Last update: {campaign.updated_at}")
                self.stdout.write(f"     Progress: {campaign.messages_sent} sent, {campaign.messages_failed} failed")
                
                if campaign.use_advanced_controls:
                    self.stdout.write(f"     Batch: {campaign.current_batch}/{campaign.total_batches}")
                    if campaign.cooldown_status:
                        self.stdout.write(f"     Was in cooldown: {campaign.cooldown_status}")
                
                # Reset campaign to pending
                with transaction.atomic():
                    campaign.status = 'pending'
                    campaign.cooldown_remaining = 0
                    campaign.cooldown_status = None
                    campaign.save(update_fields=['status', 'cooldown_remaining', 'cooldown_status', 'updated_at'])
                
                # Queue for processing
                try:
                    from django_q.tasks import async_task
                    from whatsappapi.tasks import send_campaign_async
                    
                    task_id = async_task(
                        send_campaign_async,
                        campaign.id,
                        task_name=f"resume_stuck_{campaign.id}_{timezone.now().strftime('%H%M%S')}"
                    )
                    
                    campaign.task_id = task_id
                    campaign.save(update_fields=['task_id'])
                    
                    self.stdout.write(self.style.SUCCESS(
                        f"  ✅ Resumed campaign {campaign.id} - Task: {task_id}"
                    ))
                    resumed += 1
                    
                except ImportError:
                    self.stdout.write(self.style.WARNING(
                        f"  ⚠️ Django-Q not available - campaign {campaign.id} reset to pending but not queued"
                    ))
                    resumed += 1
                    
            except Exception as e:
                self.stdout.write(self.style.ERROR(
                    f"  ❌ Failed to resume campaign {campaign.id}: {e}"
                ))
                failed += 1
        
        self.stdout.write(f"\n📊 Summary: {resumed} resumed, {failed} failed")
        
        # Log to file for monitoring
        logger.info(f"STUCK_CHECK: Found {count}, Resumed {resumed}, Failed {failed}")

from django.apps import AppConfig
import logging

logger = logging.getLogger(__name__)


class WhatsappapiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'whatsappapi'

    def ready(self):
        """
        Called when Django starts.
        Auto-resume stuck campaigns after server restart/downtime.
        """
        import os
        
        # Only run in the main process (not in migrations, shell, etc.)
        # Check for RUN_MAIN to avoid running twice in development
        if os.environ.get('RUN_MAIN') == 'true' or not os.environ.get('DJANGO_SETTINGS_MODULE'):
            return
        
        # Don't run during migrations or collectstatic
        import sys
        if any(cmd in sys.argv for cmd in ['migrate', 'makemigrations', 'collectstatic', 'shell', 'test']):
            return
        
        # Schedule auto-resume check (delayed to ensure DB is ready)
        try:
            from django.db import connection
            # Test if database is accessible
            connection.ensure_connection()
            
            # Run auto-resume in a separate thread to not block startup
            import threading
            
            def auto_resume_stuck_campaigns():
                """Background task to resume stuck campaigns on startup"""
                import time
                time.sleep(10)  # Wait 10 seconds for full startup
                
                try:
                    from django.utils import timezone
                    from datetime import timedelta
                    from userpanel.models import WASenderCampaign
                    
                    # Find campaigns stuck in 'running' status for more than 15 minutes
                    threshold = timezone.now() - timedelta(minutes=15)
                    stuck_campaigns = WASenderCampaign.objects.filter(
                        status='running',
                        updated_at__lt=threshold
                    )
                    
                    if stuck_campaigns.exists():
                        logger.warning(f"🔄 AUTO-RESUME: Found {stuck_campaigns.count()} stuck campaign(s) after server restart")
                        
                        for campaign in stuck_campaigns:
                            try:
                                # Reset to pending
                                campaign.status = 'pending'
                                campaign.cooldown_remaining = 0
                                campaign.cooldown_status = None
                                campaign.save(update_fields=['status', 'cooldown_remaining', 'cooldown_status', 'updated_at'])
                                
                                # Queue for processing
                                from django_q.tasks import async_task
                                from whatsappapi.tasks import send_campaign_async
                                
                                task_id = async_task(
                                    send_campaign_async,
                                    campaign.id,
                                    task_name=f"auto_resume_campaign_{campaign.id}"
                                )
                                
                                campaign.task_id = task_id
                                campaign.save(update_fields=['task_id'])
                                
                                logger.info(f"✅ AUTO-RESUMED campaign {campaign.id} ({campaign.name}) - Task: {task_id}")
                                
                            except Exception as e:
                                logger.error(f"❌ Failed to auto-resume campaign {campaign.id}: {e}")
                    else:
                        logger.info("✅ No stuck campaigns found on startup")
                        
                except Exception as e:
                    logger.error(f"❌ Auto-resume check failed: {e}")
            
            # Start background thread
            resume_thread = threading.Thread(target=auto_resume_stuck_campaigns, daemon=True)
            resume_thread.start()
            logger.info("🔄 Scheduled auto-resume check for stuck campaigns...")
            
        except Exception as e:
            logger.debug(f"Skipping auto-resume check: {e}")

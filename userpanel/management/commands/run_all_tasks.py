from django.core.management.base import BaseCommand
from django.core.management import call_command
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Runs all maintenance tasks in sequence (for scheduled tasks)'

    def handle(self, *args, **options):
        current_time = datetime.now()
        hour = current_time.hour
        minute = current_time.minute
        
        self.stdout.write("Starting run_all_tasks at {}:{:02d}".format(hour, minute))
        
        # Always run stuck orders processing (every 15 minutes)
        self.stdout.write("Running process_stuck_orders...")
        try:
            call_command('process_stuck_orders')
            self.stdout.write("process_stuck_orders completed")
        except Exception as e:
            logger.error("Failed to run process_stuck_orders: {}".format(e))
            self.stdout.write("ERROR: process_stuck_orders failed: {}".format(e))
        
        # Run email reminders only once per day (at 9 AM)
        if hour == 9 and minute < 15:  # Run between 9:00-9:15 AM
            self.stdout.write("Running send_pro_reminders...")
            try:
                call_command('send_pro_reminders')
                self.stdout.write("send_pro_reminders completed")
            except Exception as e:
                logger.error("Failed to run send_pro_reminders: {}".format(e))
                self.stdout.write("ERROR: send_pro_reminders failed: {}".format(e))
                
            self.stdout.write("Running send_trial_reminders...")
            try:
                call_command('send_trial_reminders')
                self.stdout.write("send_trial_reminders completed")
            except Exception as e:
                logger.error("Failed to run send_trial_reminders: {}".format(e))
                self.stdout.write("ERROR: send_trial_reminders failed: {}".format(e))
        else:
            self.stdout.write("Skipping email reminders (not 9 AM)")
        
        self.stdout.write("All tasks completed successfully!")

# app/utils/backup_scheduler.py - Integration with existing scheduler

from flask import current_app
from app.models.setting import Setting
from app.routes.backup import get_backup_settings, perform_backup
import json
import threading

def setup_backup_scheduler(app, scheduler):
    """Setup backup scheduler integration"""
    try:
        with app.app_context():
            # Get backup settings
            backup_settings = get_backup_settings()
            
            if backup_settings.get('auto_backup_enabled', False):
                update_backup_scheduler(app, scheduler, backup_settings)
                app.logger.info("Backup scheduler initialized successfully")
            else:
                app.logger.info("Auto backup is disabled")
                
    except Exception as e:
        app.logger.error(f"Error setting up backup scheduler: {str(e)}")

def update_backup_scheduler(app, scheduler, settings):
    """Update backup scheduler with current settings"""
    try:
        # Remove existing backup job if it exists
        if scheduler.running:
            try:
                scheduler.remove_job('database_backup')
                app.logger.info("Removed existing backup job")
            except:
                pass  # Job might not exist
        
        # Only add job if auto backup is enabled
        if not settings.get('auto_backup_enabled', False):
            app.logger.info("Auto backup disabled, no job scheduled")
            return
        
        # Get schedule settings
        schedule_type = settings.get('backup_schedule', 'daily')
        backup_time = settings.get('backup_time', '02:00')
        
        # Parse backup time
        try:
            hour, minute = map(int, backup_time.split(':'))
        except:
            hour, minute = 2, 0  # Default to 2:00 AM
        
        # Create trigger based on schedule type
        if schedule_type == 'hourly':
            trigger_kwargs = {
                'trigger': 'interval',
                'hours': 1,
                'start_date': None
            }
            schedule_desc = "every hour"
        elif schedule_type == 'weekly':
            trigger_kwargs = {
                'trigger': 'cron',
                'day_of_week': 0,  # Monday
                'hour': hour,
                'minute': minute
            }
            schedule_desc = f"weekly on Monday at {backup_time}"
        else:  # daily
            trigger_kwargs = {
                'trigger': 'cron',
                'hour': hour,
                'minute': minute
            }
            schedule_desc = f"daily at {backup_time}"
        
        # Add the backup job
        scheduler.add_job(
            func=run_scheduled_backup,
            id='database_backup',
            name=f"Database Backup ({schedule_desc})",
            replace_existing=True,
            **trigger_kwargs
        )
        
        app.logger.info(f"Backup job scheduled: {schedule_desc}")
        
    except Exception as e:
        app.logger.error(f"Error updating backup scheduler: {str(e)}")

def run_scheduled_backup():
    """Standalone function to run scheduled backup with proper app context"""
    try:
        # Import the Flask app
        from app import create_app
        
        # Create a new app instance for this background task
        app = create_app()
        
        with app.app_context():
            try:
                # Get current backup settings
                backup_settings = get_backup_settings()
                
                # Perform the backup
                app.logger.info("Starting scheduled database backup...")
                perform_backup(backup_settings)
                app.logger.info("Scheduled database backup completed successfully")
                
            except Exception as e:
                app.logger.error(f"Scheduled backup failed: {str(e)}")
                import traceback
                app.logger.error(traceback.format_exc())
                
    except Exception as e:
        # Fallback logging to stdout if Flask logging isn't available
        print(f"CRITICAL ERROR in scheduled backup: {str(e)}")
        import traceback
        print(traceback.format_exc())

# Add this function to your existing app/utils/scheduler.py file
def update_backup_schedule_from_settings():
    """Update backup schedule when settings change"""
    try:
        from app import scheduler
        from flask import current_app
        
        # Get backup settings
        backup_settings = get_backup_settings()
        
        # Update the scheduler
        update_backup_scheduler(current_app, scheduler, backup_settings)
        
    except Exception as e:
        current_app.logger.error(f"Error updating backup schedule: {str(e)}")

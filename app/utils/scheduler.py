# app/utils/scheduler.py - Fixed version with proper Flask context handling

import logging
from flask import current_app
from app import db
from app.models.asset import Asset
from app.models.notification import NotificationSetting, NotificationLog
from app.utils.email import send_warranty_alert
from app.utils.time_utils import today, utcnow
from datetime import timedelta, datetime

def check_warranty_expiry():
    """
    Original warranty expiry check function - maintains existing functionality
    This is the main function that should always work regardless of new features
    """
    try:
        current_app.logger.info("Starting warranty expiry check...")
        
        current_date = today()
        notification_count = 0
        
        # Get all assets that need checking
        assets = Asset.query.filter(
            Asset.notifications_enabled == True,
            Asset.warranty_expiry_date.isnot(None)
        ).all()
        
        current_app.logger.info(f"Checking {len(assets)} assets for warranty expiry")
        
        for asset in assets:
            days_until_expiry = (asset.warranty_expiry_date - current_date).days
            
            # Skip expired assets (they don't need notifications)
            if days_until_expiry < 0:
                continue
            
            # Check if asset is within alert period (default 30 days or asset-specific)
            alert_period = asset.alert_period or 30
            
            if days_until_expiry <= alert_period:
                # Check if we already sent a notification recently
                if should_send_notification(asset):
                    recipient_email = asset.user_email
                    if not recipient_email and asset.assigned_user:
                        recipient_email = asset.assigned_user.email
                    
                    if recipient_email:
                        # Use the original send function or enhanced one if available
                        success = send_warranty_alert(asset, recipient_email)
                        
                        if success:
                            # Log the notification
                            notification_log = NotificationLog(
                                asset_id=asset.id,
                                recipient_email=recipient_email,
                                status='sent',
                                notification_type='standard'  # Default type
                            )
                            db.session.add(notification_log)
                            notification_count += 1
                            
                            current_app.logger.info(f"Sent warranty alert for asset {asset.product_name} to {recipient_email}")
                        else:
                            current_app.logger.error(f"Failed to send warranty alert for asset {asset.product_name}")
                    else:
                        current_app.logger.warning(f"No recipient email found for asset {asset.product_name}")
        
        # Commit all notification logs
        db.session.commit()
        current_app.logger.info(f"Warranty expiry check completed. Sent {notification_count} notifications.")
        
    except Exception as e:
        current_app.logger.error(f"Error in warranty expiry check: {str(e)}")
        import traceback
        current_app.logger.error(traceback.format_exc())
        db.session.rollback()


def should_send_notification(asset):
    """
    Determine if we should send a notification for this asset
    Uses user preferences if available, otherwise uses simple daily logic
    """
    try:
        # Get user's notification settings if they exist
        user_settings = None
        if asset.assigned_user:
            user_settings = NotificationSetting.query.filter_by(user_id=asset.assigned_user.id).first()
        
        # If no user settings, get system defaults
        if not user_settings:
            user_settings = NotificationSetting.query.filter_by(is_system_default=True).first()
        
        # If still no settings, use simple daily logic
        if not user_settings:
            return should_send_simple_daily(asset)
        
        # Use the user's frequency preference
        if user_settings.frequency == 'once':
            return should_send_once_only(asset)
        elif user_settings.frequency == 'daily':
            return should_send_daily(asset, user_settings)
        elif user_settings.frequency == 'twice_daily':
            return should_send_twice_daily(asset, user_settings)
        elif user_settings.frequency == 'weekly':
            return should_send_weekly(asset, user_settings)
        else:
            return should_send_simple_daily(asset)
            
    except Exception as e:
        current_app.logger.error(f"Error determining notification frequency for asset {asset.id}: {str(e)}")
        return should_send_simple_daily(asset)


def should_send_simple_daily(asset):
    """Fallback: Send once per day maximum"""
    today_start = datetime.combine(today(), datetime.min.time())
    today_end = today_start + timedelta(days=1)
    
    recent_notification = NotificationLog.query.filter(
        NotificationLog.asset_id == asset.id,
        NotificationLog.sent_at >= today_start,
        NotificationLog.sent_at < today_end
    ).first()
    
    return not recent_notification


def should_send_once_only(asset):
    """Send only one notification when asset enters alert period"""
    existing_notification = NotificationLog.query.filter_by(asset_id=asset.id).first()
    return not existing_notification


def should_send_daily(asset, settings):
    """Send daily at preferred time"""
    # For simplicity, just check if we sent today already
    return should_send_simple_daily(asset)


def should_send_twice_daily(asset, settings):
    """Send twice daily at preferred times"""
    # For simplicity, allow twice per day maximum
    today_start = datetime.combine(today(), datetime.min.time())
    today_end = today_start + timedelta(days=1)
    
    notifications_today = NotificationLog.query.filter(
        NotificationLog.asset_id == asset.id,
        NotificationLog.sent_at >= today_start,
        NotificationLog.sent_at < today_end
    ).count()
    
    return notifications_today < 2


def should_send_weekly(asset, settings):
    """Send weekly on preferred day"""
    current_date = today()
    
    # Check if today is the configured day
    if hasattr(settings, 'day_of_week') and current_date.weekday() != settings.day_of_week:
        return False
    
    # Check if we sent this week already
    week_start = current_date - timedelta(days=current_date.weekday())
    week_end = week_start + timedelta(days=7)
    
    recent_notification = NotificationLog.query.filter(
        NotificationLog.asset_id == asset.id,
        NotificationLog.sent_at >= datetime.combine(week_start, datetime.min.time()),
        NotificationLog.sent_at < datetime.combine(week_end, datetime.min.time())
    ).first()
    
    return not recent_notification


def check_enhanced_notifications():
    """
    Enhanced notification system with initial/secondary alerts
    This is the NEW function that uses all the advanced features
    """
    try:
        current_app.logger.info("Starting enhanced notification check...")
        
        # Get system-wide notification settings
        system_settings = NotificationSetting.query.filter_by(is_system_default=True).first()
        if not system_settings:
            current_app.logger.info("No enhanced system settings found, falling back to basic check")
            return check_warranty_expiry()
        
        current_date = today()
        notification_count = 0
        
        # Get all assets that might need notifications
        assets = Asset.query.filter(
            Asset.notifications_enabled == True,
            Asset.warranty_expiry_date.isnot(None)
        ).all()
        
        current_app.logger.info(f"Enhanced check: Processing {len(assets)} assets")
        
        for asset in assets:
            days_until_expiry = (asset.warranty_expiry_date - current_date).days
            
            # Skip expired assets
            if days_until_expiry < 0:
                continue
            
            notification_type = None
            should_send = False
            
            # Check for initial alert
            if (hasattr(system_settings, 'initial_alert_enabled') and 
                system_settings.initial_alert_enabled and
                days_until_expiry <= getattr(system_settings, 'initial_alert_days', 30) and
                days_until_expiry > getattr(system_settings, 'secondary_alert_days', 15)):
                
                # Check if initial alert already sent
                existing_initial = NotificationLog.query.filter_by(
                    asset_id=asset.id,
                    notification_type='initial'
                ).first()
                
                if not existing_initial:
                    notification_type = 'initial'
                    should_send = True
            
            # Check for secondary alert
            elif (hasattr(system_settings, 'secondary_alert_enabled') and 
                  system_settings.secondary_alert_enabled and
                  days_until_expiry <= getattr(system_settings, 'secondary_alert_days', 15)):
                
                notification_type = 'secondary'
                should_send = should_send_enhanced_secondary(asset, system_settings)
            
            # Send notification if needed
            if should_send and notification_type:
                recipient_email = asset.user_email
                if not recipient_email and asset.assigned_user:
                    recipient_email = asset.assigned_user.email
                
                if recipient_email:
                    success = send_warranty_alert(asset, recipient_email, notification_type)
                    
                    if success:
                        notification_log = NotificationLog(
                            asset_id=asset.id,
                            recipient_email=recipient_email,
                            notification_type=notification_type,
                            status='sent'
                        )
                        db.session.add(notification_log)
                        notification_count += 1
                        
                        current_app.logger.info(f"Sent {notification_type} notification for {asset.product_name}")
        
        db.session.commit()
        current_app.logger.info(f"Enhanced notification check completed. Sent {notification_count} notifications.")
        
    except Exception as e:
        current_app.logger.error(f"Error in enhanced notification check: {str(e)}")
        # Fall back to basic check
        return check_warranty_expiry()


def should_send_enhanced_secondary(asset, settings):
    """Enhanced secondary alert logic"""
    try:
        frequency = getattr(settings, 'secondary_frequency', 'daily')
        
        if frequency == 'daily':
            return should_send_simple_daily(asset)
        elif frequency == 'weekly':
            return should_send_weekly(asset, settings)
        else:
            return should_send_simple_daily(asset)
    except:
        return should_send_simple_daily(asset)


def run_notification_check():
    """
    Standalone function that runs notification checks with proper app context
    This function is designed to be called by the scheduler
    """
    try:
        # Import the Flask app from the module level
        import sys
        import os
        
        # Add the app directory to the Python path if not already there
        app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if app_dir not in sys.path:
            sys.path.insert(0, app_dir)
        
        # Import the app factory and create an app instance
        from app import create_app
        
        # Create a new app instance for this background task
        app = create_app()
        
        with app.app_context():
            try:
                # Get system settings to determine which function to use
                system_settings = NotificationSetting.query.filter_by(is_system_default=True).first()
                
                if (system_settings and 
                    hasattr(system_settings, 'initial_alert_enabled') and
                    hasattr(system_settings, 'secondary_alert_enabled')):
                    check_enhanced_notifications()
                else:
                    check_warranty_expiry()
                    
            except Exception as e:
                current_app.logger.error(f"Error in notification check: {str(e)}")
                import traceback
                current_app.logger.error(traceback.format_exc())
                
    except Exception as e:
        # Fallback logging to stdout if Flask logging isn't available
        print(f"CRITICAL ERROR in notification job: {str(e)}")
        import traceback
        print(traceback.format_exc())


def update_scheduler_frequency(app, settings):
    """Update the scheduler frequency based on settings"""
    try:
        # Import scheduler from app context
        from app import scheduler
        
        # Remove existing notification job if it exists
        if scheduler.running:
            try:
                scheduler.remove_job('warranty_notifications')
                app.logger.info("Removed existing notification job")
            except:
                pass  # Job might not exist
        
        # Only add job if scheduler is enabled
        if not getattr(settings, 'scheduler_enabled', True):
            app.logger.info("Scheduler disabled by admin settings")
            return
        
        # Determine the notification function to use
        try:
            if (hasattr(settings, 'initial_alert_enabled') and
                hasattr(settings, 'secondary_alert_enabled')):
                job_name = 'Enhanced Warranty Notifications'
            else:
                job_name = 'Basic Warranty Notifications'
        except:
            job_name = 'Basic Warranty Notifications (Fallback)'
        
        # Get frequency settings
        frequency_type = getattr(settings, 'scheduler_frequency_type', 'hours')
        frequency_value = getattr(settings, 'scheduler_frequency_value', 60)
        
        # Create trigger based on frequency type
        if frequency_type == 'minutes':
            trigger_kwargs = {"minutes": frequency_value}
            frequency_desc = f"every {frequency_value} minute{'s' if frequency_value != 1 else ''}"
        else:  # hours
            trigger_kwargs = {"hours": frequency_value}
            frequency_desc = f"every {frequency_value} hour{'s' if frequency_value != 1 else ''}"
        
        # Add the updated job using the standalone function
        scheduler.add_job(
            func=run_notification_check,
            trigger="interval",
            **trigger_kwargs,
            id='warranty_notifications',
            name=f"{job_name} ({frequency_desc})",
            replace_existing=True
        )
        
        app.logger.info(f"Updated scheduler: {job_name} running {frequency_desc}")
        
    except Exception as e:
        app.logger.error(f"Error updating scheduler frequency: {str(e)}")
        import traceback
        app.logger.error(traceback.format_exc())


def setup_scheduler(app, scheduler):
    """Setup notification scheduler with configurable frequency"""
    try:
        # Remove any existing jobs
        if scheduler.running:
            scheduler.remove_all_jobs()
        
        # Try to get scheduler settings from database
        scheduler_settings = None
        try:
            with app.app_context():
                from app.models.notification import NotificationSetting
                scheduler_settings = NotificationSetting.query.filter_by(is_system_default=True).first()
        except Exception as e:
            app.logger.warning(f"Could not load scheduler settings from database: {str(e)}")
        
        # Use default settings if none found
        if not scheduler_settings:
            class DefaultSettings:
                scheduler_frequency_type = 'hours'
                scheduler_frequency_value = 1
                scheduler_enabled = True
                
            scheduler_settings = DefaultSettings()
            app.logger.info("Using default scheduler settings")
        
        # Check if scheduler is enabled
        if not getattr(scheduler_settings, 'scheduler_enabled', True):
            app.logger.info("Scheduler disabled by settings")
            return
        
        # Update scheduler with current settings
        update_scheduler_frequency(app, scheduler_settings)
        
        app.logger.info("Notification scheduler setup completed")
        
    except Exception as e:
        app.logger.error(f"Error setting up notification scheduler: {str(e)}")
        import traceback
        app.logger.error(traceback.format_exc())
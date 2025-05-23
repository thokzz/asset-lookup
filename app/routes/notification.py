# app/routes/notification.py
from datetime import timedelta
from app.utils.time_utils import today, utcnow
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, jsonify
from flask_login import login_required, current_user
from app import db
from app.models.notification import NotificationSetting, NotificationLog
from app.models.asset import Asset
from app.utils.audit import log_activity
from datetime import datetime

# Create the blueprint - this line is critical!
notification = Blueprint('notification', __name__)

# app/routes/notification.py - Updated preferences function

@notification.route('/test')
def test_route():
    """Simple test route to verify blueprint is working"""
    return """
    <html>
    <head><title>Notification Test</title></head>
    <body>
        <h1>Notification blueprint is working!</h1>
        <p>This confirms the blueprint is registered and routes are accessible.</p>
        <p><a href="/debug/routes">View all routes</a></p>
    </body>
    </html>
    """

@notification.route('/test-response')  
def test_response():
    """Test the response functionality"""
    return """
    <html>
    <head><title>Test Response</title></head>
    <body>
        <h1>Test Response Page</h1>
        <p>If you can see this, the notification blueprint is working.</p>
        <p>The issue might be with the specific route parameters.</p>
        <a href="/debug/routes">View all routes</a>
    </body>
    </html>
    """

@notification.route('/debug/scheduler-status')
@login_required
def debug_scheduler_status():
    """Debug page showing scheduler status and allowing manual trigger"""
    if not current_user.is_admin:
        flash('Admin access required', 'danger')
        return redirect(url_for('asset.dashboard'))
    
    try:
        from app import scheduler
        
        # Get scheduler info
        jobs = scheduler.get_jobs()
        scheduler_running = scheduler.running
        
        # Get notification settings
        system_settings = NotificationSetting.query.filter_by(is_system_default=True).first()
        
        # Get recent notification logs
        recent_logs = NotificationLog.query.order_by(NotificationLog.sent_at.desc()).limit(10).all()
        
        # Get assets that might need notifications
        current_date = today()
        
        assets_in_alert_period = Asset.query.filter(
            Asset.notifications_enabled == True,
            Asset.warranty_expiry_date.isnot(None),
            Asset.warranty_expiry_date > current_date,
            Asset.warranty_expiry_date <= current_date + timedelta(days=30)
        ).all()
        
        return render_template('notification/debug_scheduler.html',
            title='Scheduler Debug',
            scheduler_running=scheduler_running,
            jobs=jobs,
            system_settings=system_settings,
            recent_logs=recent_logs,
            assets_in_alert_period=assets_in_alert_period,
            current_time=utcnow()
        )
        
    except Exception as e:
        current_app.logger.error(f"Error in scheduler debug: {str(e)}")
        import traceback
        current_app.logger.error(traceback.format_exc())
        flash(f'Error loading scheduler status: {str(e)}', 'danger')
        return redirect(url_for('admin.admin_dashboard'))


@notification.route('/debug/trigger-notifications')
@login_required
def debug_trigger_notifications():
    """Manually trigger notification check"""
    if not current_user.is_admin:
        flash('Admin access required', 'danger')
        return redirect(url_for('asset.dashboard'))
    
    try:
        # Import and run notification check
        from app.utils.scheduler import check_warranty_expiry, check_enhanced_notifications
        
        # Determine which function to use
        system_settings = NotificationSetting.query.filter_by(is_system_default=True).first()
        
        if (system_settings and 
            hasattr(system_settings, 'initial_alert_enabled') and
            hasattr(system_settings, 'secondary_alert_enabled')):
            check_enhanced_notifications()
            flash('Enhanced notification check triggered manually', 'success')
        else:
            check_warranty_expiry()
            flash('Basic notification check triggered manually', 'success')
            
        current_app.logger.info(f"Manual notification trigger by user {current_user.username}")
        
    except Exception as e:
        current_app.logger.error(f"Error in manual notification trigger: {str(e)}")
        import traceback
        current_app.logger.error(traceback.format_exc())
        flash(f'Error triggering notifications: {str(e)}', 'danger')
    
    return redirect(url_for('notification.debug_scheduler_status'))


@notification.route('/notification/response/<asset_id>/<notification_id>/<action>/debug')
def debug_response_url(asset_id, notification_id, action):
    """Debug route to test URL parsing"""
    return f"""
    <html>
    <head><title>Debug Response URL</title></head>
    <body>
        <h1>Debug Response URL</h1>
        <p><strong>Asset ID:</strong> {asset_id}</p>
        <p><strong>Notification ID:</strong> {notification_id}</p>
        <p><strong>Action:</strong> {action}</p>
        <p><strong>Asset ID Type:</strong> {type(asset_id)}</p>
        <p><strong>Notification ID Type:</strong> {type(notification_id)}</p>
        
        <h2>Try the actual handler:</h2>
        <a href="/notification/response/{asset_id}/{notification_id}/{action}">Process this response</a>
    </body>
    </html>
    """

@notification.route('/debug/restart-scheduler')
@login_required
def debug_restart_scheduler():
    """Restart the scheduler with current settings"""
    if not current_user.is_admin:
        flash('Admin access required', 'danger')
        return redirect(url_for('asset.dashboard'))
    
    try:
        from app import scheduler
        from app.utils.scheduler import setup_scheduler
        
        # Get current settings
        system_settings = NotificationSetting.query.filter_by(is_system_default=True).first()
        
        if system_settings:
            from app.utils.scheduler import update_scheduler_frequency
            update_scheduler_frequency(current_app, system_settings)
            flash('Scheduler restarted with current settings', 'success')
        else:
            # Restart with default settings
            setup_scheduler(current_app, scheduler)
            flash('Scheduler restarted with default settings', 'info')
            
        current_app.logger.info(f"Scheduler restarted by user {current_user.username}")
        
    except Exception as e:
        current_app.logger.error(f"Error restarting scheduler: {str(e)}")
        import traceback
        current_app.logger.error(traceback.format_exc())
        flash(f'Error restarting scheduler: {str(e)}', 'danger')
    
    return redirect(url_for('notification.debug_scheduler_status'))


@notification.route('/debug/send-test-notification/<asset_id>')
@login_required
def debug_send_notification(asset_id):
    """Debug endpoint to force send a notification for an asset"""
    if not current_user.is_admin:
        flash('Admin access required', 'danger')
        return redirect(url_for('asset.dashboard'))
    
    try:
        from app.utils.email import send_warranty_alert
        
        asset = Asset.query.get_or_404(asset_id)
        recipient_email = asset.user_email or current_user.email
        
        if not recipient_email:
            flash('No recipient email found. Please set user_email on the asset.', 'danger')
            return redirect(url_for('notification.debug_scheduler_status'))
        
        current_app.logger.info(f"DEBUG: Forcing notification send for asset {asset_id} to {recipient_email}")
        
        # Try to send notification
        success = send_warranty_alert(asset, recipient_email, 'test')
        
        if success:
            # Log the test notification
            notification_log = NotificationLog(
                asset_id=asset.id,
                recipient_email=recipient_email,
                notification_type='test',
                status='sent'
            )
            db.session.add(notification_log)
            db.session.commit()
            
            flash(f'Test notification sent successfully to {recipient_email}', 'success')
            current_app.logger.info(f"DEBUG: Successfully sent test notification to {recipient_email}")
        else:
            flash(f'Failed to send test notification to {recipient_email}', 'danger')
            current_app.logger.error(f"DEBUG: Failed to send test notification to {recipient_email}")
            
    except Exception as e:
        current_app.logger.error(f"Error in test notification: {str(e)}")
        import traceback
        current_app.logger.error(traceback.format_exc())
        flash(f'Error sending test notification: {str(e)}', 'danger')
    
    return redirect(url_for('notification.debug_scheduler_status'))


@notification.route('/debug/schema-info')
@login_required
def debug_schema_info():
    """Debug route to check database schema"""
    if not current_user.is_admin:
        flash('Admin access required', 'danger')
        return redirect(url_for('asset.dashboard'))
    
    try:
        import sqlite3
        import os
        
        # Get database path
        db_path = current_app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
        if not db_path.startswith('/'):
            db_path = os.path.join(current_app.root_path, db_path)
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        schema_info = {}
        
        # Check notification_settings table
        cursor.execute("PRAGMA table_info(notification_settings)")
        schema_info['notification_settings'] = [
            {
                'name': col[1],
                'type': col[2],
                'notnull': col[3],
                'default': col[4],
                'pk': col[5]
            }
            for col in cursor.fetchall()
        ]
        
        # Check notification_logs table
        cursor.execute("PRAGMA table_info(notification_logs)")
        schema_info['notification_logs'] = [
            {
                'name': col[1],
                'type': col[2],
                'notnull': col[3],
                'default': col[4],
                'pk': col[5]
            }
            for col in cursor.fetchall()
        ]
        
        # Check if system settings exist
        cursor.execute("SELECT COUNT(*) FROM notification_settings WHERE is_system_default = 1")
        system_settings_count = cursor.fetchone()[0]
        
        conn.close()
        
        return f"""
        <html>
        <head><title>Schema Debug</title></head>
        <body style="font-family: monospace; padding: 20px;">
        <h1>Database Schema Information</h1>
        
        <h2>notification_settings table:</h2>
        <table border="1" style="border-collapse: collapse;">
        <tr><th>Column</th><th>Type</th><th>Not Null</th><th>Default</th><th>Primary Key</th></tr>
        {''.join([f"<tr><td>{col['name']}</td><td>{col['type']}</td><td>{col['notnull']}</td><td>{col['default']}</td><td>{col['pk']}</td></tr>" for col in schema_info['notification_settings']])}
        </table>
        
        <h2>notification_logs table:</h2>
        <table border="1" style="border-collapse: collapse;">
        <tr><th>Column</th><th>Type</th><th>Not Null</th><th>Default</th><th>Primary Key</th></tr>
        {''.join([f"<tr><td>{col['name']}</td><td>{col['type']}</td><td>{col['notnull']}</td><td>{col['default']}</td><td>{col['pk']}</td></tr>" for col in schema_info['notification_logs']])}
        </table>
        
        <h2>System Settings:</h2>
        <p>System default settings count: {system_settings_count}</p>
        
        <p><a href="{url_for('notification.debug_scheduler_status')}">Back to Scheduler Debug</a></p>
        
        <h2>Actions:</h2>
        <p><a href="{url_for('notification.debug_run_schema_fix')}">Run Schema Fix</a></p>
        </body>
        </html>
        """
        
    except Exception as e:
        return f"Error checking schema: {str(e)}"


@notification.route('/debug/run-schema-fix')
@login_required
def debug_run_schema_fix():
    """Manually run the schema fix migration"""
    if not current_user.is_admin:
        flash('Admin access required', 'danger')
        return redirect(url_for('asset.dashboard'))
    
    try:
        from app.migrations.fix_notification_schema import run_migration
        run_migration()
        flash('Schema fix migration completed successfully', 'success')
    except Exception as e:
        flash(f'Schema fix failed: {str(e)}', 'danger')
        current_app.logger.error(f"Manual schema fix error: {str(e)}")
    
    return redirect(url_for('notification.debug_schema_info'))
    
    return redirect(url_for('notification.debug_schema_info'))

@notification.route('/notification/preferences', methods=['GET', 'POST'])
@login_required
def preferences():
    """User notification preferences page"""
    # Get user's current preferences
    user_prefs = NotificationSetting.query.filter_by(user_id=current_user.id).first()
    
    # If no preferences exist for this user, create one with system defaults
    if not user_prefs:
        system_default = NotificationSetting.query.filter_by(is_system_default=True).first()
        
        # If no system defaults, create with hardcoded defaults
        if not system_default:
            user_prefs = NotificationSetting(user_id=current_user.id)
        else:
            # Copy system defaults
            user_prefs = NotificationSetting(
                user_id=current_user.id,
                frequency=system_default.frequency,
                day_of_week=system_default.day_of_week,
                preferred_time=system_default.preferred_time,
                preferred_second_time=system_default.preferred_second_time
            )
            
            # Copy any additional attributes
            if hasattr(system_default, 'secondary_custom_days') and hasattr(user_prefs, 'secondary_custom_days'):
                user_prefs.secondary_custom_days = system_default.secondary_custom_days
        
        db.session.add(user_prefs)
        db.session.commit()
    
    if request.method == 'POST':
        try:
            # Update preferences
            user_prefs.frequency = request.form.get('frequency')
            
            # Safe conversion of day_of_week to integer with default value
            day_of_week_str = request.form.get('day_of_week', '1')
            user_prefs.day_of_week = int(day_of_week_str) if day_of_week_str.strip() else 1
            
            user_prefs.preferred_time = request.form.get('preferred_time')
            user_prefs.preferred_second_time = request.form.get('preferred_second_time')
            
            # Handle any other fields with safe conversion
            if hasattr(user_prefs, 'secondary_custom_days'):
                secondary_custom_days_str = request.form.get('secondary_custom_days', '1')
                user_prefs.secondary_custom_days = int(secondary_custom_days_str) if secondary_custom_days_str.strip() else 1
            
            db.session.commit()
            
            # Log change
            log_activity(
                action="UPDATE",
                resource_type="NotificationSettings",
                resource_id=user_prefs.id,
                description=f"User updated notification preferences: {user_prefs.frequency}"
            )
            
            flash('Notification preferences saved!', 'success')
            return redirect(url_for('notification.preferences'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error saving preferences: {str(e)}', 'danger')
            current_app.logger.error(f"Error updating notification preferences: {str(e)}")
            import traceback
            current_app.logger.error(traceback.format_exc())
    
    # Get recent notifications
    recent_notifications = NotificationLog.query.filter_by(
        recipient_email=current_user.email
    ).order_by(NotificationLog.sent_at.desc()).limit(20).all()
    
    return render_template('notification/preferences.html', 
        title='Notification Preferences',
        preferences=user_prefs,
        notifications=recent_notifications,
        days_of_week={
            0: 'Monday',
            1: 'Tuesday',
            2: 'Wednesday',
            3: 'Thursday',
            4: 'Friday',
            5: 'Saturday',
            6: 'Sunday'
        }
    )

# app/routes/notification.py - Updated admin_settings function

# Update the admin_settings function in app/routes/notification.py

@notification.route('/admin/notification/settings', methods=['GET', 'POST'])
@login_required
def admin_settings():
    """Admin page for system-wide notification settings with paginated logs"""
    # Check if user is admin
    if not current_user.is_admin:
        flash('You do not have permission to access this area.', 'danger')
        return redirect(url_for('asset.dashboard'))
    
    # Get system settings
    system_settings = NotificationSetting.query.filter_by(is_system_default=True).first()
    
    # If no system settings exist, create one with comprehensive defaults
    if not system_settings:
        system_settings = NotificationSetting(
            is_system_default=True,
            frequency='once',
            day_of_week=1,
            preferred_time='09:00',
            preferred_second_time='15:00',
            # Initial alert settings
            initial_alert_enabled=True,
            initial_alert_days=30,
            initial_alert_time='09:00',
            # Secondary alert settings
            secondary_alert_enabled=True,
            secondary_alert_days=15,
            secondary_frequency='daily',
            secondary_custom_days=1,
            secondary_day_of_week=1,
            secondary_alert_time='09:00'
        )
        db.session.add(system_settings)
        db.session.commit()
    
    if request.method == 'POST':
        try:
            # Initial Alert Settings
            system_settings.initial_alert_enabled = 'initial_alert_enabled' in request.form
            system_settings.initial_alert_days = int(request.form.get('initial_alert_days', 30))
            system_settings.initial_alert_time = request.form.get('initial_alert_time', '09:00')
            
            # Secondary Alert Settings
            system_settings.secondary_alert_enabled = 'secondary_alert_enabled' in request.form
            system_settings.secondary_alert_days = int(request.form.get('secondary_alert_days', 15))
            system_settings.secondary_frequency = request.form.get('secondary_frequency', 'daily')
            system_settings.secondary_alert_time = request.form.get('secondary_alert_time', '09:00')
            
            # Custom interval settings
            system_settings.secondary_custom_days = int(request.form.get('secondary_custom_days', 1))
            system_settings.secondary_day_of_week = int(request.form.get('secondary_day_of_week', 1))
            
            # Handle second time for twice daily secondary alerts
            if system_settings.secondary_frequency == 'twice_daily':
                system_settings.preferred_second_time = request.form.get('secondary_second_time', '15:00')
            
            # Scheduler Settings
            system_settings.scheduler_frequency_type = request.form.get('scheduler_frequency_type', 'hours')
            system_settings.scheduler_frequency_value = int(request.form.get('scheduler_frequency_value', 60))
            system_settings.scheduler_enabled = 'scheduler_enabled' in request.form
            
            # Validation for scheduler settings
            if system_settings.scheduler_frequency_type == 'minutes':
                if system_settings.scheduler_frequency_value < 1 or system_settings.scheduler_frequency_value > 1440:
                    flash('Scheduler frequency must be between 1 and 1440 minutes.', 'danger')
                    return redirect(url_for('notification.admin_settings'))
            else:  # hours
                if system_settings.scheduler_frequency_value < 1 or system_settings.scheduler_frequency_value > 24:
                    flash('Scheduler frequency must be between 1 and 24 hours.', 'danger')
                    return redirect(url_for('notification.admin_settings'))
            
            # Legacy User Preference Defaults
            system_settings.frequency = request.form.get('frequency', 'once')
            system_settings.day_of_week = int(request.form.get('day_of_week', 1))
            system_settings.preferred_time = request.form.get('preferred_time', '09:00')
            system_settings.preferred_second_time = request.form.get('preferred_second_time', '15:00')
            
            # Validation
            if system_settings.initial_alert_days <= system_settings.secondary_alert_days:
                flash('Initial alert days must be greater than secondary alert days.', 'danger')
                return redirect(url_for('notification.admin_settings'))
            
            if system_settings.secondary_custom_days < 1 or system_settings.secondary_custom_days > 30:
                flash('Custom days interval must be between 1 and 30 days.', 'danger')
                return redirect(url_for('notification.admin_settings'))
            
            # Update timestamp
            system_settings.updated_at = utcnow()
            
            db.session.commit()
            
            # Log change
            log_activity(
                action="UPDATE",
                resource_type="SystemNotificationSettings",
                resource_id=system_settings.id,
                description=f"Admin updated comprehensive system notification settings: "
                           f"Initial alerts {'enabled' if system_settings.initial_alert_enabled else 'disabled'} "
                           f"({system_settings.initial_alert_days} days), "
                           f"Secondary alerts {'enabled' if system_settings.secondary_alert_enabled else 'disabled'} "
                           f"({system_settings.secondary_alert_days} days, {system_settings.secondary_frequency}), "
                           f"Scheduler: every {system_settings.scheduler_frequency_value} {system_settings.scheduler_frequency_type} "
                           f"({'enabled' if system_settings.scheduler_enabled else 'disabled'})"
            )
            
            # Update the scheduler with new settings
            try:
                from app.utils.scheduler import update_scheduler_frequency
                update_scheduler_frequency(current_app, system_settings)
                flash('System notification settings saved and scheduler updated successfully!', 'success')
            except Exception as e:
                current_app.logger.error(f"Error updating scheduler: {str(e)}")
                flash('Settings saved, but scheduler update failed. Please restart the application.', 'warning')
            return redirect(url_for('notification.admin_settings'))
            
        except ValueError as e:
            flash(f'Invalid input: Please check your numeric values.', 'danger')
            current_app.logger.error(f"ValueError updating notification settings: {str(e)}")
        except Exception as e:
            db.session.rollback()
            flash(f'Error saving settings: {str(e)}', 'danger')
            current_app.logger.error(f"Error updating notification settings: {str(e)}")
            import traceback
            current_app.logger.error(traceback.format_exc())
    
    # PAGINATION IMPLEMENTATION FOR NOTIFICATION LOGS
    # Get page number from query parameters, default to 1
    page = request.args.get('page', 1, type=int)
    per_page = 10  # Number of logs per page
    
    # Get paginated notification logs
    notification_logs = NotificationLog.query.order_by(
        NotificationLog.sent_at.desc()
    ).paginate(
        page=page,
        per_page=per_page,
        error_out=False
    )
    
    return render_template('notification/admin_settings.html', 
        title='System Notification Settings',
        settings=system_settings,
        notification_logs=notification_logs,  # Pass pagination object instead of list
        days_of_week={
            0: 'Monday',
            1: 'Tuesday',
            2: 'Wednesday',
            3: 'Thursday',
            4: 'Friday',
            5: 'Saturday',
            6: 'Sunday'
        }
    )

@notification.route('/notification/response/<asset_id>/<notification_id>/<action>', methods=['GET', 'POST'])
def handle_response(asset_id, notification_id, action):
    """Handle user responses to notification emails - Fixed version"""
    
    try:
        current_app.logger.info(f"DEBUG: Received notification response - Asset: {asset_id}, Notification: {notification_id}, Action: {action}")
        
        # Asset ID could be UUID string, handle appropriately
        asset = Asset.query.filter_by(id=asset_id).first()
        if not asset:
            current_app.logger.error(f"DEBUG: Asset not found: {asset_id}")
            flash('Asset not found', 'danger')
            return redirect(url_for('asset.dashboard'))
            
        current_app.logger.info(f"DEBUG: Found asset: {asset.product_name}")
        
        # Handle notification_id - could be UUID (legacy) or integer (new system)
        notification_log = None
        
        # First try as integer (new system)
        try:
            notification_id_int = int(notification_id)
            notification_log = NotificationLog.query.get(notification_id_int)
            current_app.logger.info(f"DEBUG: Found notification log by integer ID: {notification_id_int}")
        except ValueError:
            current_app.logger.info(f"DEBUG: notification_id is not integer, treating as UUID: {notification_id}")
        
        # If not found as integer, handle as legacy UUID
        if not notification_log:
            current_app.logger.info("DEBUG: No notification log found by integer, creating legacy entry")
            
            # Determine recipient email
            recipient_email = None
            if hasattr(asset, 'user_email') and asset.user_email:
                recipient_email = asset.user_email
            elif hasattr(asset, 'assigned_user') and asset.assigned_user and asset.assigned_user.email:
                recipient_email = asset.assigned_user.email
            else:
                # Fallback to current user email if logged in
                from flask_login import current_user
                if current_user.is_authenticated:
                    recipient_email = current_user.email
                else:
                    recipient_email = "unknown@example.com"  # Fallback
            
            current_app.logger.info(f"DEBUG: Using recipient email: {recipient_email}")
            
            # Create legacy notification log entry - only with fields that exist
            notification_log = NotificationLog(
                asset_id=asset.id,
                recipient_email=recipient_email,
                notification_type='legacy_uuid',
                status='sent'
                # Don't set sent_at in constructor, set it after creation
            )
            
            # Set sent_at after creation if the field exists
            from app.utils.time_utils import utcnow
            if hasattr(notification_log, 'sent_at'):
                notification_log.sent_at = utcnow()
            
            db.session.add(notification_log)
            db.session.flush()
            current_app.logger.info(f"DEBUG: Created legacy notification log with ID: {notification_log.id}")
        
        # Validate the notification belongs to this asset (convert both to strings for comparison)
        if str(notification_log.asset_id) != str(asset.id):
            current_app.logger.error(f"DEBUG: Asset ID mismatch - Log: {notification_log.asset_id}, Asset: {asset.id}")
            flash('Invalid notification reference', 'danger')
            return redirect(url_for('asset.dashboard'))
        
        valid_actions = ['renewed', 'will_not_renew', 'pending', 'disable_notifications']
        if action not in valid_actions:
            current_app.logger.error(f"DEBUG: Invalid action: {action}")
            flash('Invalid action', 'danger')
            return redirect(url_for('asset.dashboard'))
        
        current_app.logger.info(f"DEBUG: Processing action: {action}")
        
        # Update notification log
        notification_log.response = action
        if hasattr(notification_log, 'response_date'):
            notification_log.response_date = utcnow()
        notification_log.status = 'acknowledged'
        
        # Handle specific actions
        if action == 'renewed':
            db.session.commit()  # Save the response first
            current_app.logger.info(f"DEBUG: Redirecting to renewal form")
            return redirect(url_for('notification.handle_renewal', asset_id=asset.id, notification_id=notification_log.id))
        
        elif action == 'disable_notifications':
            asset.notifications_enabled = False
            current_app.logger.info(f"DEBUG: Disabled notifications for asset")
            
            # Log the change
            log_activity(
                action="NOTIFICATION_DISABLED",
                resource_type="Asset", 
                resource_id=asset.id,
                description=f"Notifications disabled for asset {asset.product_name}"
            )
        
        db.session.commit()
        current_app.logger.info(f"DEBUG: Successfully processed {action} action")
        
        # Show acknowledgment page
        return render_template('notification/acknowledge.html',
            title='Response Recorded',
            asset=asset,
            action=action
        )
        
    except Exception as e:
        current_app.logger.error(f"ERROR in handle_response: {str(e)}")
        import traceback
        current_app.logger.error(traceback.format_exc())
        
        # Return a simple error page instead of crashing
        return f"""
        <html>
        <head><title>Error Processing Response</title></head>
        <body>
            <h1>Error Processing Response</h1>
            <p>There was an error processing your response: {str(e)}</p>
            <p>Asset ID: {asset_id}</p>
            <p>Notification ID: {notification_id}</p>
            <p>Action: {action}</p>
            <a href="/">Return to Dashboard</a>
        </body>
        </html>
        """, 500

@notification.route('/notification/renewal/<asset_id>/<notification_id>', methods=['GET', 'POST'])
def handle_renewal(asset_id, notification_id):
    """Handle warranty renewal form"""
    asset = Asset.query.get_or_404(asset_id)
    notification_log = NotificationLog.query.get_or_404(notification_id)
    
    if request.method == 'POST':
        try:
            # Get form data
            new_warranty_duration = int(request.form.get('warranty_duration', 12))
            
            # Calculate new warranty expiry date based on today
            from dateutil.relativedelta import relativedelta
            today = datetime.utcnow().date()
            asset.warranty_expiry_date = today + relativedelta(months=new_warranty_duration)
            
            # Update asset
            asset.warranty_duration = new_warranty_duration
            
            # Update notification log
            notification_log.response = 'renewed'
            notification_log.response_date = datetime.utcnow()
            notification_log.status = 'acknowledged'
            
            db.session.commit()
            
            # Log the renewal
            log_activity(
                action="WARRANTY_RENEWED",
                resource_type="Asset",
                resource_id=asset.id,
                description=f"Warranty renewed for asset {asset.product_name} for {new_warranty_duration} months"
            )
            
            flash('Warranty renewal recorded successfully!', 'success')
            return redirect(url_for('notification.acknowledge_renewal', asset_id=asset.id))
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error processing renewal: {str(e)}")
            flash('Error processing renewal. Please try again.', 'danger')
    
    return render_template('notification/renewal_form.html',
        title='Record Warranty Renewal',
        asset=asset
    )

@notification.route('/notification/acknowledge_renewal/<asset_id>')
def acknowledge_renewal(asset_id):
    """Show acknowledgment page after renewal"""
    asset = Asset.query.get_or_404(asset_id)
    
    return render_template('notification/acknowledge_renewal.html',
        title='Warranty Renewal Recorded',
        asset=asset
    )

@notification.route('/assets/<asset_id>/toggle-notifications', methods=['POST'])
@login_required
def toggle_notifications(asset_id):
    asset = Asset.query.get_or_404(asset_id)
    
    # Check permission
    if not current_user.has_permission('EDIT', asset):
        flash('You do not have permission to modify this asset.', 'danger')
        return redirect(url_for('asset.asset_detail', asset_id=asset.id))
    
    # Update notification setting
    asset.notifications_enabled = 'notifications_enabled' in request.form
    
    db.session.commit()
    
    # Log the change
    log_activity(
        action="UPDATE",
        resource_type="Asset",
        resource_id=asset.id,
        description=f"Notifications {'enabled' if asset.notifications_enabled else 'disabled'} for asset {asset.product_name}"
    )
    
    flash(f"Notifications {'enabled' if asset.notifications_enabled else 'disabled'} for this asset.", 'success')
    return redirect(url_for('asset.asset_detail', asset_id=asset.id))

@notification.route('/debug/notification-status')
@login_required  # Ensure only logged-in users can access this
def debug_notification_status():
    """Debug page showing notification status and allowing test emails"""
    from app.models.asset import Asset
    from app.utils.time_utils import today, utcnow
    from datetime import timedelta
    
    current_date = today()
    
    # Get all assets expiring within 30 days
    expiring_assets = Asset.query.filter(
        Asset.warranty_expiry_date > current_date,
        Asset.warranty_expiry_date <= current_date + timedelta(days=30)
    ).all()
    
    # Get all notification settings
    from app.models.notification import NotificationSetting
    notification_settings = NotificationSetting.query.all()
    
    # Get all notification logs
    from app.models.notification import NotificationLog
    notification_logs = NotificationLog.query.order_by(NotificationLog.sent_at.desc()).limit(20).all()
    
    # Get time info
    now = utcnow()
    app_tz = get_app_timezone()
    local_now = now.astimezone(app_tz)
    
    # Create a simple HTML page with the results
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Notification System Debug</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.2.0/dist/css/bootstrap.min.css" rel="stylesheet">
        <style>
            .status-card { margin-bottom: 20px; }
            .table th { position: sticky; top: 0; background: white; }
            .success { color: green; }
            .warning { color: orange; }
            .danger { color: red; }
        </style>
    </head>
    <body>
        <div class="container mt-4">
            <h1>Notification System Debug</h1>
            
            <div class="card status-card">
                <div class="card-header">
                    <h5>System Status</h5>
                </div>
                <div class="card-body">
                    <p><strong>Current Date:</strong> {current_date}</p>
                    <p><strong>Current Time:</strong> {current_time}</p>
                    <p><strong>Timezone:</strong> {timezone}</p>
                </div>
            </div>
            
            <div class="card status-card">
                <div class="card-header">
                    <h5>Expiring Assets ({expiring_count})</h5>
                </div>
                <div class="card-body">
                    <div class="table-responsive" style="max-height: 400px; overflow-y: auto;">
                        <table class="table table-striped">
                            <thead>
                                <tr>
                                    <th>ID</th>
                                    <th>Name</th>
                                    <th>Days Left</th>
                                    <th>Email</th>
                                    <th>Notifications</th>
                                    <th>Action</th>
                                </tr>
                            </thead>
                            <tbody>
                                {expiring_assets_rows}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
            
            <div class="card status-card">
                <div class="card-header">
                    <h5>Notification Settings ({settings_count})</h5>
                </div>
                <div class="card-body">
                    <div class="table-responsive" style="max-height: 400px; overflow-y: auto;">
                        <table class="table table-striped">
                            <thead>
                                <tr>
                                    <th>ID</th>
                                    <th>User</th>
                                    <th>Frequency</th>
                                    <th>Time</th>
                                    <th>Is Default</th>
                                </tr>
                            </thead>
                            <tbody>
                                {settings_rows}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
            
            <div class="card status-card">
                <div class="card-header">
                    <h5>Recent Notification Logs ({logs_count})</h5>
                </div>
                <div class="card-body">
                    <div class="table-responsive" style="max-height: 400px; overflow-y: auto;">
                        <table class="table table-striped">
                            <thead>
                                <tr>
                                    <th>ID</th>
                                    <th>Asset</th>
                                    <th>Recipient</th>
                                    <th>Sent At</th>
                                    <th>Status</th>
                                    <th>Response</th>
                                </tr>
                            </thead>
                            <tbody>
                                {logs_rows}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    
    # Generate table rows for expiring assets
    expiring_assets_rows = ""
    for asset in expiring_assets:
        notification_enabled = "Yes" if asset.notifications_enabled else "No"
        notification_class = "success" if asset.notifications_enabled else "danger"
        
        send_button = f'<a href="/debug/send-test-notification/{asset.id}" class="btn btn-sm btn-primary">Send Test</a>'
        
        expiring_assets_rows += f"""
        <tr>
            <td>{asset.id}</td>
            <td>{asset.product_name}</td>
            <td>{asset.days_remaining}</td>
            <td>{asset.user_email or 'N/A'}</td>
            <td class="{notification_class}">{notification_enabled}</td>
            <td>{send_button}</td>
        </tr>
        """
    
    # Generate table rows for notification settings
    settings_rows = ""
    for setting in notification_settings:
        user = "System Default" if setting.is_system_default else (setting.user.username if setting.user else "N/A")
        settings_rows += f"""
        <tr>
            <td>{setting.id}</td>
            <td>{user}</td>
            <td>{setting.frequency}</td>
            <td>{setting.preferred_time}</td>
            <td>{"Yes" if setting.is_system_default else "No"}</td>
        </tr>
        """
    
    # Generate table rows for notification logs
    logs_rows = ""
    for log in notification_logs:
        asset_name = log.asset.product_name if log.asset else "N/A"
        status_class = "success" if log.status == "sent" else ("warning" if log.status == "pending" else "danger")
        logs_rows += f"""
        <tr>
            <td>{log.id}</td>
            <td>{asset_name}</td>
            <td>{log.recipient_email}</td>
            <td>{log.sent_at}</td>
            <td class="{status_class}">{log.status}</td>
            <td>{log.response or 'N/A'}</td>
        </tr>
        """
    
    # Fill in the template
    html = html.format(
        current_date=current_date,
        current_time=local_now.strftime('%Y-%m-%d %H:%M:%S'),
        timezone=app_tz,
        expiring_count=len(expiring_assets),
        expiring_assets_rows=expiring_assets_rows,
        settings_count=len(notification_settings),
        settings_rows=settings_rows,
        logs_count=len(notification_logs),
        logs_rows=logs_rows
    )
    
    return html

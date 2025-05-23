# app/routes/admin.py - Updated with 2FA settings support
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from app import db, bcrypt
from app.models.user import User
from app.models.group import Group, Permission
from app.models.audit import AuditLog
from app.utils.audit import log_user_change, log_group_change, log_system_event, log_activity
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import os
import json

admin = Blueprint('admin', __name__)

@admin.route('/debug/2fa-config')
@login_required
def debug_2fa_config():
    """Debug route to check 2FA configuration from all sources"""
    if not current_user.is_admin:
        flash('Admin access required', 'danger')
        return redirect(url_for('asset.dashboard'))
    
    import os
    import json
    from app.utils.config_service import ConfigService
    
    debug_info = {}
    
    # Check app config
    debug_info['app_config_2fa'] = current_app.config.get('TWO_FACTOR_ENABLED', 'NOT_SET')
    
    # Check settings file
    try:
        settings_file = os.path.join(current_app.root_path, '..', 'instance', 'settings.json')
        if os.path.exists(settings_file):
            with open(settings_file, 'r') as f:
                settings = json.load(f)
                debug_info['file_2fa'] = settings.get('TWO_FACTOR_ENABLED', 'NOT_SET')
                debug_info['all_file_settings'] = settings
        else:
            debug_info['file_2fa'] = 'FILE_NOT_EXISTS'
            debug_info['all_file_settings'] = {}
    except Exception as e:
        debug_info['file_error'] = str(e)
    
    # Check ConfigService
    debug_info['config_service_2fa'] = ConfigService.get_bool('TWO_FACTOR_ENABLED', 'DEFAULT_FALSE')
    debug_info['config_service_is_2fa_enabled'] = ConfigService.is_2fa_enabled()
    
    # Check database settings
    try:
        from app.models.setting import Setting
        db_setting = Setting.query.filter_by(id='TWO_FACTOR_ENABLED').first()
        if db_setting:
            debug_info['db_2fa'] = db_setting.value
        else:
            debug_info['db_2fa'] = 'NOT_SET_IN_DB'
    except Exception as e:
        debug_info['db_error'] = str(e)
    
    # Check current user's 2FA status
    debug_info['user_needs_2fa_setup'] = current_user.needs_2fa_setup()
    debug_info['user_requires_2fa_verification'] = current_user.requires_2fa_verification()
    debug_info['user_2fa_setup_complete'] = current_user.two_factor_setup_complete
    debug_info['user_2fa_enabled'] = current_user.two_factor_enabled
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>2FA Configuration Debug</title>
        <style>
            body {{ font-family: monospace; margin: 20px; }}
            .good {{ color: green; }}
            .bad {{ color: red; }}
            .neutral {{ color: blue; }}
            pre {{ background: #f5f5f5; padding: 10px; border-radius: 5px; }}
        </style>
    </head>
    <body>
        <h1>2FA Configuration Debug Information</h1>
        
        <h2>Configuration Sources:</h2>
        <ul>
            <li><strong>App Config 2FA:</strong> <span class="{'good' if debug_info['app_config_2fa'] else 'bad'}">{debug_info['app_config_2fa']}</span></li>
            <li><strong>Settings File 2FA:</strong> <span class="{'good' if debug_info.get('file_2fa') else 'bad'}">{debug_info.get('file_2fa', 'ERROR')}</span></li>
            <li><strong>ConfigService get_bool:</strong> <span class="{'good' if debug_info['config_service_2fa'] else 'bad'}">{debug_info['config_service_2fa']}</span></li>
            <li><strong>ConfigService is_2fa_enabled:</strong> <span class="{'good' if debug_info['config_service_is_2fa_enabled'] else 'bad'}">{debug_info['config_service_is_2fa_enabled']}</span></li>
            <li><strong>Database 2FA:</strong> <span class="{'good' if debug_info.get('db_2fa') else 'bad'}">{debug_info.get('db_2fa', 'ERROR')}</span></li>
        </ul>
        
        <h2>User Status:</h2>
        <ul>
            <li><strong>Needs 2FA Setup:</strong> <span class="{'bad' if debug_info['user_needs_2fa_setup'] else 'neutral'}">{debug_info['user_needs_2fa_setup']}</span></li>
            <li><strong>Requires 2FA Verification:</strong> <span class="{'good' if debug_info['user_requires_2fa_verification'] else 'neutral'}">{debug_info['user_requires_2fa_verification']}</span></li>
            <li><strong>2FA Setup Complete:</strong> <span class="{'good' if debug_info['user_2fa_setup_complete'] else 'neutral'}">{debug_info['user_2fa_setup_complete']}</span></li>
            <li><strong>2FA Enabled:</strong> <span class="{'good' if debug_info['user_2fa_enabled'] else 'neutral'}">{debug_info['user_2fa_enabled']}</span></li>
        </ul>
        
        <h2>All Settings File Contents:</h2>
        <pre>{json.dumps(debug_info.get('all_file_settings', {}), indent=2)}</pre>
        
        <h2>Full Debug Data:</h2>
        <pre>{json.dumps(debug_info, indent=2, default=str)}</pre>
        
        <hr>
        <p><a href="{url_for('admin.settings')}">Back to Admin Settings</a></p>
    </body>
    </html>
    """
    
    return html

@admin.route('/admin/audit')
@login_required
def audit_logs():
    page = request.args.get('page', 1, type=int)
    action_filter = request.args.get('action', '')
    resource_filter = request.args.get('resource', '')
    user_filter = request.args.get('user', '')
    status_filter = request.args.get('status', '')
    from_date = request.args.get('from_date', '')
    to_date = request.args.get('to_date', '')
    
    # Start with base query
    query = AuditLog.query
    
    # Apply filters
    if action_filter:
        query = query.filter(AuditLog.action == action_filter)
    
    if resource_filter:
        query = query.filter(AuditLog.resource_type == resource_filter)
    
    if user_filter:
        query = query.filter(AuditLog.username.ilike(f"%{user_filter}%"))
    
    if status_filter:
        query = query.filter(AuditLog.status == status_filter)
    
    if from_date:
        try:
            # Parse date in application timezone and convert to UTC for query
            from app.utils.time_utils import parse_datetime
            from_datetime = parse_datetime(from_date, '%Y-%m-%d')
            query = query.filter(AuditLog.timestamp >= from_datetime)
        except ValueError:
            pass
    
    if to_date:
        try:
            # Parse date in application timezone and convert to UTC for query
            from app.utils.time_utils import parse_datetime
            to_datetime = parse_datetime(to_date, '%Y-%m-%d')
            # Add 23:59:59 to the end date to include the entire day
            to_datetime = to_datetime.replace(hour=23, minute=59, second=59)
            query = query.filter(AuditLog.timestamp <= to_datetime)
        except ValueError:
            pass
    
    # Get distinct values for filter dropdowns
    actions = db.session.query(AuditLog.action).distinct().order_by(AuditLog.action).all()
    resources = db.session.query(AuditLog.resource_type).distinct().order_by(AuditLog.resource_type).all()
    statuses = db.session.query(AuditLog.status).distinct().order_by(AuditLog.status).all()
    
    # Paginate results
    logs = query.order_by(AuditLog.timestamp.desc()).paginate(page=page, per_page=50)
    
    # Get the current time for display
    from app.utils.time_utils import localnow
    now = localnow()
    
    return render_template('admin/audit_logs.html', 
                          title='Audit Logs',
                          logs=logs,
                          actions=[a[0] for a in actions],
                          resources=[r[0] for r in resources],
                          statuses=[s[0] for s in statuses],
                          action_filter=action_filter,
                          resource_filter=resource_filter,
                          user_filter=user_filter,
                          status_filter=status_filter,
                          from_date=from_date,
                          to_date=to_date,
                          now=now)

# Middleware to check admin access
@admin.before_request
def check_admin():
    if not current_user.is_authenticated or not current_user.is_admin:
        flash('You do not have permission to access this area.', 'danger')
        return redirect(url_for('asset.dashboard'))

@admin.route('/admin')
@login_required
def admin_dashboard():
    # System statistics
    user_count = User.query.count()
    active_user_count = User.query.filter_by(is_active=True).count()
    group_count = Group.query.count()
    
    # 2FA statistics
    from app.utils.config_service import ConfigService
    two_factor_enabled = ConfigService.is_2fa_enabled()
    users_with_2fa = User.query.filter_by(two_factor_setup_complete=True).count() if two_factor_enabled else 0
    
    return render_template('admin/dashboard.html', 
        title='Admin Dashboard',
        user_count=user_count,
        active_user_count=active_user_count,
        group_count=group_count,
        two_factor_enabled=two_factor_enabled,
        users_with_2fa=users_with_2fa
    )

# User Management routes remain the same...
@admin.route('/admin/users')
@login_required
def user_list():
    users = User.query.order_by(User.username).all()
    return render_template('admin/users/list.html', title='User Management', users=users)

@admin.route('/admin/users/create', methods=['GET', 'POST'])
@login_required
def create_user():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        is_admin = 'is_admin' in request.form
        is_group_admin = 'is_group_admin' in request.form
        is_active = 'is_active' in request.form
        
        # Check if user already exists
        existing_user = User.query.filter((User.username == username) | (User.email == email)).first()
        if existing_user:
            flash('Username or email already exists.', 'danger')
            return redirect(url_for('admin.create_user'))
        
        new_user = User(
            username=username,
            email=email,
            password=password,
            first_name=request.form.get('first_name'),
            last_name=request.form.get('last_name'),
            is_admin=is_admin,
            is_group_admin=is_group_admin
        )
        new_user.is_active = is_active
        
        # Add to groups
        group_ids = request.form.getlist('groups')
        if group_ids:
            groups = Group.query.filter(Group.id.in_(group_ids)).all()
            new_user.groups = groups
        
        db.session.add(new_user)
        db.session.commit()

        # Log user creation
        log_user_change(new_user, "CREATE", 
                       description=f"Admin created new user: {new_user.username} (Role: {new_user.role_display})")
        
        flash('User created successfully!', 'success')
        return redirect(url_for('admin.user_list'))
        
    groups = Group.query.order_by(Group.name).all()
    return render_template('admin/users/create.html', title='Create User', groups=groups)

@admin.route('/admin/users/<user_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_user(user_id):
    user = User.query.get_or_404(user_id)
    
    if request.method == 'POST':
        # Collect old data for audit
        old_data = {
            'username': user.username,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'is_admin': user.is_admin,
            'is_group_admin': user.is_group_admin,
            'is_active': user.is_active,
            'groups': [g.id for g in user.groups]
        }

        username = request.form.get('username')
        email = request.form.get('email')
        
        # Check if another user has this username or email
        existing_user = User.query.filter(
            ((User.username == username) | (User.email == email)) & 
            (User.id != user_id)
        ).first()
        
        if existing_user:
            flash('Username or email already exists.', 'danger')
            return redirect(url_for('admin.edit_user', user_id=user_id))
        
        user.username = username
        user.email = email
        user.first_name = request.form.get('first_name')
        user.last_name = request.form.get('last_name')
        user.is_admin = 'is_admin' in request.form
        user.is_group_admin = 'is_group_admin' in request.form
        user.is_active = 'is_active' in request.form
        
        # Update password if provided
        if request.form.get('password'):
            user.set_password(request.form.get('password'))
        
        # Update groups
        group_ids = request.form.getlist('groups')
        groups = Group.query.filter(Group.id.in_(group_ids)).all() if group_ids else []
        user.groups = groups

        # Collect new data for audit
        new_data = {
            'username': user.username,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'is_admin': user.is_admin,
            'is_group_admin': user.is_group_admin,
            'is_active': user.is_active,
            'groups': [g.id for g in user.groups]
        }
        
        # If password updated, note it in the audit
        password_updated = bool(request.form.get('password'))
        
        db.session.commit()

        # Log changes
        log_user_change(user, "UPDATE", old_data, new_data,
                       description=f"Admin updated user {user.username} (Role: {user.role_display}){' (including password)' if password_updated else ''}")
        flash('User updated successfully!', 'success')
        return redirect(url_for('admin.user_list'))
    
    groups = Group.query.order_by(Group.name).all()
    return render_template('admin/users/edit.html', title='Edit User', user=user, groups=groups)

@admin.route('/admin/users/<user_id>/delete', methods=['POST'])
@login_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)

    # Store user info for audit before deleting
    username = user.username
    
    # Check if trying to delete self
    if user.id == current_user.id:
        flash('You cannot delete your own account.', 'danger')
        return redirect(url_for('admin.user_list'))    
    db.session.delete(user)
    db.session.commit()
    
    # Log user deletion
    log_activity(
        action="DELETE",
        resource_type="User",
        resource_id=user_id,
        description=f"Admin deleted user: {username}"
    )
    
    flash('User deleted successfully!', 'success')
    return redirect(url_for('admin.user_list'))

# Group Management routes remain the same...
@admin.route('/admin/groups')
@login_required
def group_list():
    groups = Group.query.order_by(Group.name).all()
    return render_template('admin/groups/list.html', title='Group Management', groups=groups)

@admin.route('/admin/groups/create', methods=['GET', 'POST'])
@login_required
def create_group():
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        
        # Check if group already exists
        existing_group = Group.query.filter_by(name=name).first()
        if existing_group:
            flash('A group with this name already exists.', 'danger')
            return redirect(url_for('admin.create_group'))
        
        new_group = Group(name=name, description=description)
        
        # Add permissions
        permission_names = request.form.getlist('permissions')
        if permission_names:
            permissions = Permission.query.filter(Permission.name.in_(permission_names)).all()
            new_group.permissions = permissions
        
        db.session.add(new_group)
        db.session.commit()
        
        flash('Group created successfully!', 'success')
        return redirect(url_for('admin.group_list'))
    
    permissions = Permission.query.order_by(Permission.name).all()
    return render_template('admin/groups/create.html', title='Create Group', permissions=permissions)

@admin.route('/admin/groups/<group_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_group(group_id):
    group = Group.query.get_or_404(group_id)
    
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        
        # Check if another group has this name
        existing_group = Group.query.filter(Group.name == name, Group.id != group_id).first()
        if existing_group:
            flash('A group with this name already exists.', 'danger')
            return redirect(url_for('admin.edit_group', group_id=group_id))
        
        group.name = name
        group.description = description
        
        # Update permissions
        permission_names = request.form.getlist('permissions')
        permissions = Permission.query.filter(Permission.name.in_(permission_names)).all() if permission_names else []
        group.permissions = permissions
        
        db.session.commit()
        flash('Group updated successfully!', 'success')
        return redirect(url_for('admin.group_list'))
    
    permissions = Permission.query.order_by(Permission.name).all()
    return render_template('admin/groups/edit.html', title='Edit Group', group=group, permissions=permissions)

@admin.route('/admin/groups/<group_id>/delete', methods=['POST'])
@login_required
def delete_group(group_id):
    group = Group.query.get_or_404(group_id)
    
    db.session.delete(group)
    db.session.commit()
    
    flash('Group deleted successfully!', 'success')
    return redirect(url_for('admin.group_list'))

# Settings & SMTP Configuration - UPDATED WITH 2FA SUPPORT
@admin.route('/admin/settings', methods=['GET', 'POST'])
@login_required
def settings():
    # Settings file path
    settings_file = os.path.join(current_app.root_path, '..', 'instance', 'settings.json')
    
    # Load settings
    def load_settings():
        if os.path.exists(settings_file):
            with open(settings_file, 'r') as f:
                return json.load(f)
        return {}
    
    # Save settings
    def save_settings(settings):
        os.makedirs(os.path.dirname(settings_file), exist_ok=True)
        with open(settings_file, 'w') as f:
            json.dump(settings, f, indent=2)
    
    if request.method == 'POST':
        # Load current settings
        settings = load_settings()
        
        # Check which form was submitted
        if 'app_timezone' in request.form:  # Application Settings form
            # Update only application settings
            old_2fa_status = settings.get('TWO_FACTOR_ENABLED', False)
            new_2fa_status = 'two_factor_enabled' in request.form
            
            settings['ALLOW_REGISTRATION'] = 'allow_registration' in request.form
            settings['TWO_FACTOR_ENABLED'] = new_2fa_status
            settings['APP_TIMEZONE'] = request.form.get('app_timezone')
            
            # Log 2FA status change if changed
            if old_2fa_status != new_2fa_status:
                log_activity(
                    action="UPDATE",
                    resource_type="SystemSettings",
                    description=f"Two-Factor Authentication {'enabled' if new_2fa_status else 'disabled'} system-wide by admin"
                )
                
                # If enabling 2FA, reset all users' 2FA setup status to force re-setup
                if new_2fa_status:
                    User.query.update({User.two_factor_setup_complete: False})
                    db.session.commit()
                    flash('2FA enabled system-wide. All users will be required to set up 2FA on their next login.', 'info')
                else:
                    # If disabling 2FA, disable it for all users
                    User.query.update({
                        User.two_factor_enabled: False,
                        User.two_factor_setup_complete: False
                    })
                    db.session.commit()
                    flash('2FA disabled system-wide for all users.', 'info')
                    
        else:  # SMTP Settings form
            # Update only SMTP settings
            settings['MAIL_SERVER'] = request.form.get('mail_server')
            settings['MAIL_PORT'] = int(request.form.get('mail_port') or 587)
            settings['MAIL_USE_TLS'] = 'mail_use_tls' in request.form
            settings['MAIL_USERNAME'] = request.form.get('mail_username')
            
            # Only update password if provided
            if request.form.get('mail_password'):
                settings['MAIL_PASSWORD'] = request.form.get('mail_password')
            
            settings['MAIL_DEFAULT_SENDER'] = request.form.get('mail_default_sender')
        
        # Save settings to file
        save_settings(settings)
        
        # Update current app config and refresh configuration
        from app.utils.config_service import ConfigService
        ConfigService.refresh_config()
        
        # Update current app config explicitly
        if 'ALLOW_REGISTRATION' in settings:
            current_app.config['ALLOW_REGISTRATION'] = settings['ALLOW_REGISTRATION']
        if 'TWO_FACTOR_ENABLED' in settings:
            current_app.config['TWO_FACTOR_ENABLED'] = settings['TWO_FACTOR_ENABLED']
        if 'APP_TIMEZONE' in settings:
            current_app.config['APP_TIMEZONE'] = settings['APP_TIMEZONE']
        if 'MAIL_SERVER' in settings:
            current_app.config['MAIL_SERVER'] = settings['MAIL_SERVER']
        if 'MAIL_PORT' in settings:
            current_app.config['MAIL_PORT'] = settings['MAIL_PORT']
        if 'MAIL_USE_TLS' in settings:
            current_app.config['MAIL_USE_TLS'] = settings['MAIL_USE_TLS']
        if 'MAIL_USERNAME' in settings:
            current_app.config['MAIL_USERNAME'] = settings['MAIL_USERNAME']
        if 'MAIL_PASSWORD' in settings:
            current_app.config['MAIL_PASSWORD'] = settings['MAIL_PASSWORD']
        if 'MAIL_DEFAULT_SENDER' in settings:
            current_app.config['MAIL_DEFAULT_SENDER'] = settings['MAIL_DEFAULT_SENDER']
        
        # Log the settings change
        log_activity(
            action="UPDATE",
            resource_type="Settings",
            description=f"Updated application settings. Timezone set to: {settings.get('APP_TIMEZONE', 'UTC')}"
        )
        
        flash('Settings updated successfully!', 'success')
        return redirect(url_for('admin.settings'))
    
    # Load settings for the template
    settings = load_settings()
    
    # Create a config object for the template
    config = {
        'ALLOW_REGISTRATION': settings.get('ALLOW_REGISTRATION', current_app.config.get('ALLOW_REGISTRATION', True)),
        'TWO_FACTOR_ENABLED': settings.get('TWO_FACTOR_ENABLED', current_app.config.get('TWO_FACTOR_ENABLED', False)),
        'APP_TIMEZONE': settings.get('APP_TIMEZONE', current_app.config.get('APP_TIMEZONE', 'UTC')),
        'MAIL_SERVER': settings.get('MAIL_SERVER', current_app.config.get('MAIL_SERVER', '')),
        'MAIL_PORT': settings.get('MAIL_PORT', current_app.config.get('MAIL_PORT', 587)),
        'MAIL_USE_TLS': settings.get('MAIL_USE_TLS', current_app.config.get('MAIL_USE_TLS', True)),
        'MAIL_USERNAME': settings.get('MAIL_USERNAME', current_app.config.get('MAIL_USERNAME', '')),
        'MAIL_PASSWORD': settings.get('MAIL_PASSWORD', current_app.config.get('MAIL_PASSWORD', '')),
        'MAIL_DEFAULT_SENDER': settings.get('MAIL_DEFAULT_SENDER', current_app.config.get('MAIL_DEFAULT_SENDER', ''))
    }
    
    # Get the current time for display
    from app.utils.time_utils import localnow
    now = localnow()
    
    return render_template('admin/settings.html', 
        title='System Settings', 
        config=config,
        now=now
    )

@admin.route('/admin/test-smtp', methods=['POST'])
@login_required
def test_smtp():
    # Import here to avoid circular imports
    import os
    import json
    
    recipient = request.form.get('test_email')
    
    if not recipient:
        flash('Please provide a test email address.', 'danger')
        return redirect(url_for('admin.settings'))
    
    try:
        # Settings file path
        settings_file = os.path.join(current_app.root_path, '..', 'instance', 'settings.json')
        
        # Load settings
        settings = {}
        if os.path.exists(settings_file):
            with open(settings_file, 'r') as f:
                settings = json.load(f)
        
        # Get SMTP settings
        mail_server = settings.get('MAIL_SERVER', current_app.config.get('MAIL_SERVER', ''))
        mail_port = settings.get('MAIL_PORT', current_app.config.get('MAIL_PORT', 587))
        mail_use_tls = settings.get('MAIL_USE_TLS', current_app.config.get('MAIL_USE_TLS', True))
        mail_username = settings.get('MAIL_USERNAME', current_app.config.get('MAIL_USERNAME', ''))
        mail_password = settings.get('MAIL_PASSWORD', current_app.config.get('MAIL_PASSWORD', ''))
        mail_default_sender = settings.get('MAIL_DEFAULT_SENDER', current_app.config.get('MAIL_DEFAULT_SENDER', ''))
        
        # Setup SMTP connection
        server = smtplib.SMTP(mail_server, mail_port)
        if mail_use_tls:
            server.starttls()
        
        if mail_username and mail_password:
            server.login(mail_username, mail_password)
        
        # Create message
        msg = MIMEMultipart()
        msg['From'] = mail_default_sender
        msg['To'] = recipient
        msg['Subject'] = 'Asset Lookup SMTP Test'
        
        body = 'This is a test email from Asset Lookup to verify SMTP settings. If you received this, your configuration is working!'
        msg.attach(MIMEText(body, 'plain'))
        
        # Send email
        server.send_message(msg)
        server.quit()
        
        flash('Test email sent successfully!', 'success')
    except Exception as e:
        flash(f'Error sending test email: {str(e)}', 'danger')
    
    return redirect(url_for('admin.settings'))
# app/routes/oidc_auth.py - OIDC Authentication Routes
from flask import Blueprint, redirect, url_for, flash, request, current_app
from flask_login import login_user, current_user
from app import db
from app.models.user import User
from app.models.group import Group
from app.utils.oidc import oidc_client
from app.utils.audit import log_login, log_user_change, log_activity

oidc_auth = Blueprint('oidc_auth', __name__)

@oidc_auth.route('/auth/oidc/login')
def oidc_login():
    """Initiate OIDC login"""
    if not oidc_client.is_enabled():
        flash('SSO login is not available.', 'warning')
        return redirect(url_for('auth.login'))
    
    if current_user.is_authenticated:
        return redirect(url_for('asset.dashboard'))
    
    try:
        return oidc_client.generate_auth_url()
    except Exception as e:
        current_app.logger.error(f"OIDC login error: {str(e)}")
        flash('SSO login failed. Please try again or use regular login.', 'danger')
        return redirect(url_for('auth.login'))

@oidc_auth.route('/auth/oidc/callback')
def oidc_callback():
    """Handle OIDC callback"""
    if not oidc_client.is_enabled():
        flash('SSO login is not available.', 'warning')
        return redirect(url_for('auth.login'))
    
    # Get authorization code and state
    code = request.args.get('code')
    state = request.args.get('state')
    error = request.args.get('error')
    
    if error:
        current_app.logger.error(f"OIDC callback error: {error}")
        flash(f'SSO login failed: {error}', 'danger')
        return redirect(url_for('auth.login'))
    
    if not code:
        flash('No authorization code received.', 'danger')
        return redirect(url_for('auth.login'))
    
    try:
        # Handle OIDC callback
        user_info = oidc_client.handle_callback(code, state)
        
        # Extract user data
        user_data = oidc_client.extract_user_data(user_info)
        
        if not user_data['email']:
            flash('No email address received from SSO provider.', 'danger')
            return redirect(url_for('auth.login'))
        
        # Find or create user
        user = User.query.filter_by(email=user_data['email']).first()
        
        if not user:
            # Check if auto-creation is enabled
            config = oidc_client._get_oidc_config()
            if not config.get('auto_create_users', True):
                flash('Your account does not exist. Please contact an administrator.', 'danger')
                log_login(None, success=False, username=user_data['email'], 
                         description="SSO login failed - user auto-creation disabled")
                return redirect(url_for('auth.login'))
            
            # Create new user
            user = create_oidc_user(user_data)
            if not user:
                flash('Failed to create user account. Please contact an administrator.', 'danger')
                return redirect(url_for('auth.login'))
        else:
            # Update existing user with SSO data
            update_oidc_user(user, user_data)
        
        # Check if user is active
        if not user.is_active:
            flash('Your account has been deactivated. Please contact an administrator.', 'danger')
            log_login(user, success=False, description="SSO login failed - account deactivated")
            return redirect(url_for('auth.login'))
        
        # Log successful login
        login_user(user, remember=True)
        log_login(user, success=True, description="Successful SSO login")
        
        # Redirect to dashboard or next page
        next_page = request.args.get('next')
        if next_page and not next_page.startswith('/'):
            next_page = None
        
        return redirect(next_page or url_for('asset.dashboard'))
        
    except Exception as e:
        current_app.logger.error(f"OIDC callback processing error: {str(e)}")
        import traceback
        current_app.logger.error(traceback.format_exc())
        flash('SSO login failed. Please try again or use regular login.', 'danger')
        return redirect(url_for('auth.login'))

def create_oidc_user(user_data):
    """Create a new user from OIDC data"""
    try:
        # Determine role
        role_info = oidc_client.determine_user_role(user_data)
        
        # Generate username if not provided
        username = user_data['username']
        if not username:
            username = user_data['email'].split('@')[0]
        
        # Ensure username is unique
        base_username = username
        counter = 1
        while User.query.filter_by(username=username).first():
            username = f"{base_username}_{counter}"
            counter += 1
        
        # Create user
        user = User(
            username=username,
            email=user_data['email'],
            password='',  # No password for SSO users
            first_name=user_data.get('first_name', ''),
            last_name=user_data.get('last_name', ''),
            is_admin=role_info['is_admin'],
            is_group_admin=role_info['is_group_admin']
        )
        
        # Assign to default groups based on role
        assign_default_groups(user, role_info['role'])
        
        db.session.add(user)
        db.session.commit()
        
        # Log user creation
        log_user_change(user, "CREATE", 
                       description=f"SSO user created: {user.username} (Role: {user.role_display})")
        
        current_app.logger.info(f"Created new SSO user: {user.username} ({user.email})")
        return user
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating SSO user: {str(e)}")
        return None

def update_oidc_user(user, user_data):
    """Update existing user with OIDC data"""
    try:
        # Update user information
        old_data = {
            'first_name': user.first_name,
            'last_name': user.last_name,
            'email': user.email
        }
        
        user.first_name = user_data.get('first_name', user.first_name)
        user.last_name = user_data.get('last_name', user.last_name)
        
        # Update role if configured to do so
        config = oidc_client._get_oidc_config()
        if config.get('update_roles_on_login', False):
            role_info = oidc_client.determine_user_role(user_data)
            user.is_admin = role_info['is_admin']
            user.is_group_admin = role_info['is_group_admin']
        
        new_data = {
            'first_name': user.first_name,
            'last_name': user.last_name,
            'email': user.email
        }
        
        db.session.commit()
        
        # Log if anything changed
        if old_data != new_data:
            log_user_change(user, "UPDATE", old_data, new_data,
                           description=f"SSO user updated: {user.username}")
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating SSO user: {str(e)}")

def assign_default_groups(user, role):
    """Assign user to default groups based on role"""
    try:
        if role == 'admin':
            group = Group.query.filter_by(name='Administrators').first()
        elif role == 'group_admin':
            group = Group.query.filter_by(name='Group Administrators').first()
        else:
            group = Group.query.filter_by(name='Users').first()
        
        if group:
            user.groups.append(group)
    except Exception as e:
        current_app.logger.error(f"Error assigning default groups: {str(e)}")

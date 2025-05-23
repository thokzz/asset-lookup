from app import db
from app.models.audit import AuditLog
from flask import request, current_app
from flask_login import current_user
import json
from datetime import datetime
import traceback

def log_activity(action, resource_type, resource_id=None, description=None, details=None,
                user=None, username=None, ip_address=None, user_agent=None, status='success'):
    """
    Log an activity to the audit log
    
    Args:
        action: The action performed (CREATE, UPDATE, DELETE, etc.)
        resource_type: The type of resource (User, Asset, Group, etc.)
        resource_id: ID of the affected resource (optional)
        description: Human-readable description of the action (optional)
        details: JSON string with detailed changes (optional)
        user: User object (optional, defaults to current_user)
        username: Username string (optional, used if user is None)
        ip_address: IP address (optional, defaults to request.remote_addr)
        user_agent: User agent (optional, defaults to request.user_agent.string)
        status: Status of the action (success, failure, warning, etc.)
    """
    try:
        # Get user information
        if user is None:
            if current_user and current_user.is_authenticated:
                user = current_user
                username = current_user.username
            elif username is None:
                username = 'System'
                
        # Get request information
        if ip_address is None and request:
            ip_address = request.remote_addr
            
        if user_agent is None and request and request.user_agent:
            user_agent = request.user_agent.string
            
        # Convert details to JSON if it's a dict
        if isinstance(details, dict):
            details = json.dumps(details)
            
        # Create the audit log entry
        log_entry = AuditLog(
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            description=description,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent,
            status=status
        )
        
        # Set user information if available
        if user:
            log_entry.user = user
            log_entry.user_id = user.id
            log_entry.username = user.username
        elif username:
            log_entry.username = username
            
        db.session.add(log_entry)
        db.session.commit()
        
    except Exception as e:
        # Handle errors gracefully
        if current_app:
            current_app.logger.error(f"Error logging activity: {str(e)}")
            current_app.logger.error(traceback.format_exc())
        db.session.rollback()

def log_login(user, success=True, username=None, description=None):
    """Log a login attempt"""
    action = "LOGIN" if success else "LOGIN_FAILED"
    if description is None:
        description = f"User {'logged in successfully' if success else 'failed to log in'}"
    
    log_activity(
        action=action,
        resource_type="Authentication",
        user=user,
        username=username,
        description=description,
        status="success" if success else "failure"
    )

def log_logout(user):
    """Log a logout"""
    log_activity(
        action="LOGOUT",
        resource_type="Authentication",
        user=user,
        description=f"User logged out"
    )

def log_user_change(user, action, old_data=None, new_data=None, description=None):
    """Log a user change (create, update, delete)"""
    details = None
    if old_data and new_data:
        details = {
            'old': old_data,
            'new': new_data
        }
        
    log_activity(
        action=action,
        resource_type="User",
        resource_id=user.id,
        description=description or f"User {user.username} {action.lower()}d",
        details=details
    )

def log_asset_change(asset, action, old_data=None, new_data=None, description=None):
    """Log an asset change (create, update, delete)"""
    details = None
    if old_data and new_data:
        details = {
            'old': old_data,
            'new': new_data
        }
        
    log_activity(
        action=action,
        resource_type="Asset",
        resource_id=asset.id,
        description=description or f"Asset {asset.product_name} {action.lower()}d",
        details=details
    )

def log_group_change(group, action, old_data=None, new_data=None, description=None):
    """Log a group change (create, update, delete)"""
    details = None
    if old_data and new_data:
        details = {
            'old': old_data,
            'new': new_data
        }
        
    log_activity(
        action=action,
        resource_type="Group",
        resource_id=group.id,
        description=description or f"Group {group.name} {action.lower()}d",
        details=details
    )

def log_system_event(event_type, description, details=None):
    """Log a system event"""
    log_activity(
        action="SYSTEM",
        resource_type=event_type,
        description=description,
        details=details,
        username="System"
    )

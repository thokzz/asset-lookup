# app/utils/email.py - Simplified to use only /email/ directory

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import current_app, url_for, render_template
from app.utils.time_utils import format_datetime, utcnow

def send_warranty_alert(asset, recipient_email, notification_type='standard'):
    """
    Send warranty expiration alert - backward compatible with enhanced features
    
    Args:
        asset: Asset object
        recipient_email: Email address to send to
        notification_type: 'standard', 'initial', or 'secondary'
    """
    try:
        # Get email configuration
        mail_server = current_app.config.get('MAIL_SERVER')
        mail_port = current_app.config.get('MAIL_PORT', 587)
        mail_use_tls = current_app.config.get('MAIL_USE_TLS', True)
        mail_username = current_app.config.get('MAIL_USERNAME')
        mail_password = current_app.config.get('MAIL_PASSWORD')
        mail_default_sender = current_app.config.get('MAIL_DEFAULT_SENDER')
        
        if not all([mail_server, mail_username, mail_password, mail_default_sender]):
            current_app.logger.error("Email configuration incomplete")
            return False
        
        # Calculate days remaining
        from app.utils.time_utils import today
        current_date = today()
        days_remaining = (asset.warranty_expiry_date - current_date).days
        
        # Create the notification log record FIRST
        from app.models.notification import NotificationLog
        from app import db
        
        notification_log = NotificationLog(
            asset_id=asset.id,
            recipient_email=recipient_email,
            notification_type=notification_type,
            status='pending'  # Will be updated to 'sent' if successful
        )
        db.session.add(notification_log)
        db.session.flush()  # This assigns an ID without committing
        
        # Use the actual notification log ID
        notification_id = str(notification_log.id)
        
        # Create subject based on notification type
        if notification_type == 'initial':
            subject_prefix = "[INITIAL NOTICE]"
        elif notification_type == 'secondary':
            subject_prefix = "[URGENT REMINDER]"
        else:
            subject_prefix = "[WARRANTY ALERT]"
        
        if days_remaining <= 0:
            subject_prefix = "[EXPIRED]"
        elif days_remaining <= 7:
            subject_prefix = "[CRITICAL]"
        
        subject = f"{subject_prefix} Warranty Alert: {asset.product_name} - {days_remaining} days remaining"
        
        # Try to use enhanced template if available, otherwise use basic template
        try:
            # Use the email directory templates with enhanced context
            html_content = render_enhanced_email(asset, recipient_email, notification_type, days_remaining, notification_id)
            text_content = render_enhanced_text_email(asset, recipient_email, notification_type, days_remaining, notification_id)
        except Exception as template_error:
            current_app.logger.warning(f"Enhanced template failed: {str(template_error)}, falling back to basic template")
            # Fall back to basic template
            html_content = render_basic_email(asset, recipient_email, days_remaining)
            text_content = render_basic_text_email(asset, recipient_email, days_remaining)
        
        # Setup SMTP connection
        server = smtplib.SMTP(mail_server, mail_port)
        if mail_use_tls:
            server.starttls()
        
        if mail_username and mail_password:
            server.login(mail_username, mail_password)
        
        # Create message
        msg = MIMEMultipart('alternative')
        msg['From'] = mail_default_sender
        msg['To'] = recipient_email
        msg['Subject'] = subject
        
        # Set priority for critical notifications
        if days_remaining <= 7 or notification_type == 'secondary':
            msg['X-Priority'] = '1'
            msg['X-MSMail-Priority'] = 'High'
        
        # Add both plain text and HTML versions
        text_part = MIMEText(text_content, 'plain')
        html_part = MIMEText(html_content, 'html')
        
        msg.attach(text_part)
        msg.attach(html_part)
        
        # Send email
        server.send_message(msg)
        server.quit()
        
        # Update notification log to 'sent'
        notification_log.status = 'sent'
        notification_log.sent_at = utcnow()
        db.session.commit()
        
        current_app.logger.info(f"Sent {notification_type} warranty alert for {asset.product_name} to {recipient_email}")
        return True
        
    except Exception as e:
        # Rollback the notification log if email failed
        if 'notification_log' in locals():
            db.session.rollback()
        current_app.logger.error(f"Error sending warranty alert: {str(e)}")
        import traceback
        current_app.logger.error(traceback.format_exc())
        return False


def render_enhanced_email(asset, recipient_email, notification_type, days_remaining, notification_id):
    """Render enhanced HTML email template using /email/ directory"""
    # Generate unique URLs for response tracking
    base_url = current_app.config.get('EXTERNAL_URL', 'http://localhost:5000')
    
    response_urls = {
        'renewed': f"{base_url}/notification/response/{asset.id}/{notification_id}/renewed",
        'will_not_renew': f"{base_url}/notification/response/{asset.id}/{notification_id}/will_not_renew",
        'pending': f"{base_url}/notification/response/{asset.id}/{notification_id}/pending",
        'disable_notifications': f"{base_url}/notification/response/{asset.id}/{notification_id}/disable_notifications"
    }
    
    # Determine urgency level
    if notification_type == 'initial':
        urgency = "INITIAL NOTICE"
        priority = "Normal"
    elif notification_type == 'secondary':
        urgency = "URGENT REMINDER"
        priority = "High"
    else:
        urgency = "WARRANTY ALERT"
        priority = "Normal"
        
    if days_remaining <= 0:
        urgency = "EXPIRED"
        priority = "High"
    elif days_remaining <= 7:
        urgency = "CRITICAL"
        priority = "High"
    
    email_context = {
        'asset': asset,
        'days_remaining': days_remaining,
        'notification_type': notification_type,
        'urgency': urgency,
        'priority': priority,
        'recipient_email': recipient_email,
        'response_urls': response_urls,
        'current_date': format_datetime(utcnow(), '%B %d, %Y'),
        'expiry_date': asset.warranty_expiry_date.strftime('%B %d, %Y'),
        'is_expired': days_remaining <= 0,
        'is_critical': days_remaining <= 7
    }
    
    # Use the email directory (not emails directory)
    return render_template('email/warranty_alert.html', **email_context)



def render_enhanced_text_email(asset, recipient_email, notification_type, days_remaining):
    """Render enhanced text email template using /email/ directory"""
    # Same context as HTML version
    base_url = current_app.config.get('EXTERNAL_URL', 'http://localhost:5000')
    
    import uuid
    notification_id = str(uuid.uuid4())
    
    response_urls = {
        'renewed': f"{base_url}/notification/response/{asset.id}/{notification_id}/renewed",
        'will_not_renew': f"{base_url}/notification/response/{asset.id}/{notification_id}/will_not_renew",
        'pending': f"{base_url}/notification/response/{asset.id}/{notification_id}/pending",
        'disable_notifications': f"{base_url}/notification/response/{asset.id}/{notification_id}/disable_notifications"
    }
    
    if notification_type == 'initial':
        urgency = "INITIAL NOTICE"
    elif notification_type == 'secondary':
        urgency = "URGENT REMINDER"
    else:
        urgency = "WARRANTY ALERT"
        
    if days_remaining <= 0:
        urgency = "EXPIRED"
    elif days_remaining <= 7:
        urgency = "CRITICAL"
    
    email_context = {
        'asset': asset,
        'days_remaining': days_remaining,
        'notification_type': notification_type,
        'urgency': urgency,
        'recipient_email': recipient_email,
        'response_urls': response_urls,
        'current_date': format_datetime(utcnow(), '%B %d, %Y'),
        'expiry_date': asset.warranty_expiry_date.strftime('%B %d, %Y'),
        'is_expired': days_remaining <= 0,
        'is_critical': days_remaining <= 7
    }
    
    # Use the email directory (not emails directory)
    return render_template('email/warranty_alert.txt', **email_context)


def render_basic_email(asset, recipient_email, days_remaining):
    """Fallback: render basic HTML email template"""
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; }}
            .header {{ background-color: #f8f9fa; padding: 20px; text-align: center; }}
            .content {{ padding: 20px; }}
            .asset-info {{ background-color: #e9ecef; padding: 15px; margin: 15px 0; }}
            .alert {{ background-color: #fff3cd; border: 1px solid #ffeaa7; padding: 15px; margin: 15px 0; }}
            .critical {{ background-color: #f8d7da; border: 1px solid #f5c6cb; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>Warranty Expiration Alert</h1>
        </div>
        <div class="content">
            <div class="{'critical' if days_remaining <= 7 else 'alert'}">
                <h2>{'CRITICAL: ' if days_remaining <= 7 else ''}Warranty expires in {days_remaining} days</h2>
            </div>
            
            <div class="asset-info">
                <h3>Asset Information</h3>
                <p><strong>Product:</strong> {asset.product_name}</p>
                {f"<p><strong>Model:</strong> {asset.product_model}</p>" if asset.product_model else ""}
                {f"<p><strong>Serial:</strong> {asset.serial_number}</p>" if asset.serial_number else ""}
                <p><strong>Purchase Date:</strong> {asset.purchase_date.strftime('%B %d, %Y')}</p>
                <p><strong>Warranty Expires:</strong> {asset.warranty_expiry_date.strftime('%B %d, %Y')}</p>
                {f"<p><strong>Location:</strong> {asset.location}</p>" if asset.location else ""}
                {f"<p><strong>Vendor:</strong> {asset.vendor_company}</p>" if asset.vendor_company else ""}
            </div>
            
            <p>Please take appropriate action regarding this warranty expiration.</p>
            
            <hr>
            <p><small>This email was sent to {recipient_email} from the Asset Lookup system.</small></p>
        </div>
    </body>
    </html>
    """
    return html_content

def render_enhanced_text_email(asset, recipient_email, notification_type, days_remaining, notification_id):
    """Render enhanced text email template using /email/ directory"""
    # Same context as HTML version
    base_url = current_app.config.get('EXTERNAL_URL', 'http://localhost:5000')
    
    response_urls = {
        'renewed': f"{base_url}/notification/response/{asset.id}/{notification_id}/renewed",
        'will_not_renew': f"{base_url}/notification/response/{asset.id}/{notification_id}/will_not_renew",
        'pending': f"{base_url}/notification/response/{asset.id}/{notification_id}/pending",
        'disable_notifications': f"{base_url}/notification/response/{asset.id}/{notification_id}/disable_notifications"
    }
    
    if notification_type == 'initial':
        urgency = "INITIAL NOTICE"
    elif notification_type == 'secondary':
        urgency = "URGENT REMINDER"
    else:
        urgency = "WARRANTY ALERT"
        
    if days_remaining <= 0:
        urgency = "EXPIRED"
    elif days_remaining <= 7:
        urgency = "CRITICAL"
    
    email_context = {
        'asset': asset,
        'days_remaining': days_remaining,
        'notification_type': notification_type,
        'urgency': urgency,
        'recipient_email': recipient_email,
        'response_urls': response_urls,
        'current_date': format_datetime(utcnow(), '%B %d, %Y'),
        'expiry_date': asset.warranty_expiry_date.strftime('%B %d, %Y'),
        'is_expired': days_remaining <= 0,
        'is_critical': days_remaining <= 7
    }
    
    # Use the email directory (not emails directory)
    return render_template('email/warranty_alert.txt', **email_context)

def render_basic_text_email(asset, recipient_email, days_remaining):
    """Fallback: render basic text email"""
    text_content = f"""
WARRANTY EXPIRATION ALERT

{'CRITICAL: ' if days_remaining <= 7 else ''}Warranty expires in {days_remaining} days

ASSET INFORMATION:
Product: {asset.product_name}
{f"Model: {asset.product_model}" if asset.product_model else ""}
{f"Serial: {asset.serial_number}" if asset.serial_number else ""}
Purchase Date: {asset.purchase_date.strftime('%B %d, %Y')}
Warranty Expires: {asset.warranty_expiry_date.strftime('%B %d, %Y')}
{f"Location: {asset.location}" if asset.location else ""}
{f"Vendor: {asset.vendor_company}" if asset.vendor_company else ""}

Please take appropriate action regarding this warranty expiration.

This email was sent to {recipient_email} from the Asset Lookup system.
    """
    return text_content


def send_password_reset_email(user):
    """Send password reset email to user"""
    try:
        # Get email configuration
        mail_server = current_app.config.get('MAIL_SERVER')
        mail_port = current_app.config.get('MAIL_PORT', 587)
        mail_use_tls = current_app.config.get('MAIL_USE_TLS', True)
        mail_username = current_app.config.get('MAIL_USERNAME')
        mail_password = current_app.config.get('MAIL_PASSWORD')
        mail_default_sender = current_app.config.get('MAIL_DEFAULT_SENDER')
        
        if not all([mail_server, mail_username, mail_password, mail_default_sender]):
            current_app.logger.error("Email configuration incomplete")
            return False
        
        # Generate reset token
        import jwt
        from datetime import datetime, timedelta
        from app.config import Config
        
        token_payload = {
            'user_id': user.id,
            'exp': datetime.utcnow() + timedelta(hours=1)
        }
        
        token = jwt.encode(token_payload, Config.JWT_SECRET_KEY, algorithm='HS256')
        
        # Generate reset URL
        base_url = current_app.config.get('EXTERNAL_URL', 'http://localhost:5000')
        reset_url = f"{base_url}/reset_password/{token}"
        
        # Try template, fallback to basic
        try:
            email_context = {
                'user': user,
                'reset_url': reset_url,
                'expiry_hours': 1
            }
            html_content = render_template('email/reset_password.html', **email_context)
            text_content = render_template('email/reset_password.txt', **email_context)
        except:
            # Basic fallback
            html_content = f"""
            <h2>Password Reset Request</h2>
            <p>Hi {user.username},</p>
            <p>You requested a password reset. Click the link below to reset your password:</p>
            <p><a href="{reset_url}">Reset Password</a></p>
            <p>This link expires in 1 hour.</p>
            """
            text_content = f"""
Password Reset Request

Hi {user.username},

You requested a password reset. Visit this link to reset your password:
{reset_url}

This link expires in 1 hour.
            """
        
        # Setup SMTP and send
        server = smtplib.SMTP(mail_server, mail_port)
        if mail_use_tls:
            server.starttls()
        
        if mail_username and mail_password:
            server.login(mail_username, mail_password)
        
        msg = MIMEMultipart('alternative')
        msg['From'] = mail_default_sender
        msg['To'] = user.email
        msg['Subject'] = 'Asset Lookup - Password Reset Request'
        
        text_part = MIMEText(text_content, 'plain')
        html_part = MIMEText(html_content, 'html')
        
        msg.attach(text_part)
        msg.attach(html_part)
        
        server.send_message(msg)
        server.quit()
        
        current_app.logger.info(f"Sent password reset email to {user.email}")
        return True
        
    except Exception as e:
        current_app.logger.error(f"Error sending password reset email: {str(e)}")
        return False
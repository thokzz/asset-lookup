# app/models/notification.py - Corrected version
from app import db
import uuid
from app.utils.time_utils import utcnow

class NotificationSetting(db.Model):
    __tablename__ = 'notification_settings'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'))
    
    # Basic notification frequency settings (legacy/user preferences)
    frequency = db.Column(db.String(20), default='once')  # 'once', 'daily', 'twice_daily', 'weekly'
    day_of_week = db.Column(db.Integer, default=1)  # 0=Monday, 6=Sunday
    preferred_time = db.Column(db.String(5), default='09:00')  # HH:MM format
    preferred_second_time = db.Column(db.String(5), default='15:00')  # For twice_daily
    
    # Enhanced alert system settings
    initial_alert_enabled = db.Column(db.Boolean, default=True)
    initial_alert_days = db.Column(db.Integer, default=30)
    initial_alert_time = db.Column(db.String(5), default='09:00')
    
    secondary_alert_enabled = db.Column(db.Boolean, default=True)
    secondary_alert_days = db.Column(db.Integer, default=15)
    secondary_frequency = db.Column(db.String(20), default='daily')  # 'daily', 'twice_daily', 'weekly', 'custom'
    secondary_custom_days = db.Column(db.Integer, default=1)
    secondary_day_of_week = db.Column(db.Integer, default=1)
    secondary_alert_time = db.Column(db.String(5), default='09:00')
    
    # Scheduler settings (only used for system defaults)
    scheduler_frequency_type = db.Column(db.String(10), default='hours')  # 'minutes' or 'hours'
    scheduler_frequency_value = db.Column(db.Integer, default=1)  # Value for the frequency
    scheduler_enabled = db.Column(db.Boolean, default=True)  # Enable/disable scheduler
    
    # System-level settings (global default if user_id is NULL)
    is_system_default = db.Column(db.Boolean, default=False)
    
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)
    
    # Relationship with user
    user = db.relationship('User', backref=db.backref('notification_setting', uselist=False))
    
    def __init__(self, user_id=None, frequency='once', day_of_week=1, 
                 preferred_time='09:00', preferred_second_time='15:00', 
                 is_system_default=False):
        self.user_id = user_id
        self.frequency = frequency
        self.day_of_week = day_of_week
        self.preferred_time = preferred_time
        self.preferred_second_time = preferred_second_time
        self.is_system_default = is_system_default


class NotificationLog(db.Model):
    __tablename__ = 'notification_logs'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    asset_id = db.Column(db.String(36), db.ForeignKey('assets.id'))
    recipient_email = db.Column(db.String(255), nullable=False)
    sent_at = db.Column(db.DateTime, default=utcnow)
    status = db.Column(db.String(20), default='sent')  # sent, failed, acknowledged
    response = db.Column(db.String(50), nullable=True)  # renewed, will_not_renew, pending, disabled
    response_date = db.Column(db.DateTime, nullable=True)
    notification_type = db.Column(db.String(20), default='standard')  # standard, initial, secondary
    
    # Relationship with asset
    asset = db.relationship('Asset', backref=db.backref('notification_logs', lazy='dynamic'))
    
    def __init__(self, asset_id, recipient_email, status='sent', notification_type='standard'):
        self.asset_id = asset_id
        self.recipient_email = recipient_email
        self.status = status
        self.notification_type = notification_type

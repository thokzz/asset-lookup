from app import db
from datetime import datetime
import uuid

class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'))
    username = db.Column(db.String(80))  # Denormalized for historical tracking
    action = db.Column(db.String(50), nullable=False, index=True)  # CREATE, UPDATE, DELETE, LOGIN, etc.
    resource_type = db.Column(db.String(50), nullable=False, index=True)  # User, Asset, Group, etc.
    resource_id = db.Column(db.String(36), index=True)  # ID of the affected resource
    description = db.Column(db.Text)  # Human-readable description of the action
    details = db.Column(db.Text)  # JSON string with detailed changes
    ip_address = db.Column(db.String(45))  # Support for IPv6
    user_agent = db.Column(db.String(255))  # Browser/client information
    status = db.Column(db.String(20), default='success')  # success, failure, warning, etc.
    
    # Relationship with user
    user = db.relationship('User', backref=db.backref('audit_logs', lazy='dynamic'))
    
    def __init__(self, action, resource_type, user=None, user_id=None, username=None, resource_id=None, 
                 description=None, details=None, ip_address=None, user_agent=None, status='success'):
        self.action = action
        self.resource_type = resource_type
        self.resource_id = resource_id
        self.description = description
        self.details = details
        self.ip_address = ip_address
        self.user_agent = user_agent
        self.status = status
        
        # Set user information
        if user:
            self.user_id = user.id
            self.username = user.username
        elif user_id:
            self.user_id = user_id
            self.username = username
        else:
            self.username = 'System'

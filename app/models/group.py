from app import db
import uuid
from datetime import datetime

# Group-Permission association table
group_permission = db.Table('group_permission',
    db.Column('group_id', db.String(36), db.ForeignKey('groups.id')),
    db.Column('permission_id', db.String(36), db.ForeignKey('permissions.id'))
)

# Asset-Group association table
asset_group = db.Table('asset_group',
    db.Column('asset_id', db.String(36), db.ForeignKey('assets.id')),
    db.Column('group_id', db.String(36), db.ForeignKey('groups.id'))
)

class Group(db.Model):
    __tablename__ = 'groups'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(80), unique=True, nullable=False)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship with permissions
    permissions = db.relationship('Permission', secondary=group_permission, backref=db.backref('groups', lazy='dynamic'))
    
    def __init__(self, name, description=None):
        self.name = name
        self.description = description

class Permission(db.Model):
    __tablename__ = 'permissions'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(80), unique=True, nullable=False)
    description = db.Column(db.Text)
    
    def __init__(self, name, description=None):
        self.name = name
        self.description = description

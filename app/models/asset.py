from app import db
import uuid
from datetime import timedelta
from dateutil.relativedelta import relativedelta

# Import the time utilities
from app.utils.time_utils import utcnow, today, utc_to_local, local_to_utc

# Asset-Tag association table
asset_tag = db.Table('asset_tag',
    db.Column('asset_id', db.String(36), db.ForeignKey('assets.id')),
    db.Column('tag_id', db.String(36), db.ForeignKey('tags.id'))
)

class Asset(db.Model):
    __tablename__ = 'assets'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    product_name = db.Column(db.String(255), nullable=False)
    product_model = db.Column(db.String(255))
    internal_asset_name = db.Column(db.String(255))
    serial_number = db.Column(db.String(255))
    purchase_date = db.Column(db.Date, nullable=False)
    price = db.Column(db.Float)
    currency_symbol = db.Column(db.String(5), default='$')
    warranty_duration = db.Column(db.Integer, nullable=False)  # In months
    location = db.Column(db.String(255))
    vendor_company = db.Column(db.String(255))
    vendor_email = db.Column(db.String(255))
    notes = db.Column(db.Text)
    disposal_date = db.Column(db.Date)
    alert_period = db.Column(db.Integer, default=30)  # Days before expiry to alert
    # Use the utcnow function from time_utils
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)
    notifications_enabled = db.Column(db.Boolean, default=True)
    
    # Add an actual column for warranty_expiry_date
    warranty_expiry_date = db.Column(db.Date)
    
    # User assignment
    assigned_user_id = db.Column(db.String(36), db.ForeignKey('users.id'))
    user_email = db.Column(db.String(255))
    
    # Define the relationship here only, not in User model
    assigned_user = db.relationship('User', foreign_keys=[assigned_user_id])
    
    # Relationships
    tags = db.relationship('Tag', secondary=asset_tag, backref=db.backref('assets', lazy='dynamic'))
    assigned_groups = db.relationship('Group', secondary='asset_group', backref=db.backref('assigned_assets', lazy='dynamic'))
    files = db.relationship('AssetFile', backref='asset', cascade='all, delete-orphan')
    
    def __init__(self, *args, **kwargs):
        super(Asset, self).__init__(*args, **kwargs)
        # Calculate warranty_expiry_date when the object is created
        self.update_warranty_expiry_date()
    
    def update_warranty_expiry_date(self):
        """Update warranty_expiry_date based on purchase_date and warranty_duration"""
        if self.purchase_date and self.warranty_duration:
            # More accurate calculation for warranty expiry
            # This approach handles month transitions properly
            self.warranty_expiry_date = self.purchase_date + relativedelta(months=self.warranty_duration)
        else:
            self.warranty_expiry_date = None
    
    @property
    def is_expired(self):
        """Check if warranty has expired"""
        if self.warranty_expiry_date:
            # Use today() from time_utils instead of datetime.utcnow().date()
            return today() > self.warranty_expiry_date
        return False
    
    @property
    def is_expiring_soon(self):
        """Check if warranty is expiring soon based on alert_period"""
        if self.warranty_expiry_date:
            # Use today() from time_utils
            days_remaining = (self.warranty_expiry_date - today()).days
            return 0 < days_remaining <= self.alert_period
        return False
    
    @property
    def days_remaining(self):
        if self.warranty_expiry_date:
            # Use today() from time_utils
            delta = self.warranty_expiry_date - today()
            return delta.days
        return 0
    
    @property
    def status(self):
        """Calculate the asset's status based on warranty_expiry_date"""
        # Use today() from time_utils
        current_date = today()
        if not self.warranty_expiry_date:
            return 'Unknown'
        if self.warranty_expiry_date <= current_date:
            return 'Expired'
        # Use alert_period instead of hardcoded 30 days for consistency
        if self.warranty_expiry_date <= current_date + timedelta(days=self.alert_period):
            return 'Expiring Soon'
        # Otherwise, it's active
        return 'Active'

class AssetFile(db.Model):
    __tablename__ = 'asset_files'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    asset_id = db.Column(db.String(36), db.ForeignKey('assets.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(255), nullable=False)
    file_type = db.Column(db.String(50))
    file_size = db.Column(db.Integer)  # In bytes
    # Use the utcnow function from time_utils
    uploaded_at = db.Column(db.DateTime, default=utcnow)
    
    def __init__(self, asset_id, filename, file_path, file_type=None, file_size=None):
        self.asset_id = asset_id
        self.filename = filename
        self.file_path = file_path
        self.file_type = file_type
        self.file_size = file_size

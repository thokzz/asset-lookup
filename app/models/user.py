# app/models/user.py - Updated with 2FA support
from app import db, bcrypt, login_manager
from flask_login import UserMixin
from datetime import datetime
import uuid
import pyotp

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(user_id)

# User-Group association table
user_group = db.Table('user_group',
    db.Column('user_id', db.String(36), db.ForeignKey('users.id')),
    db.Column('group_id', db.String(36), db.ForeignKey('groups.id'))
)

class User(db.Model, UserMixin):
    __tablename__ = 'users'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    first_name = db.Column(db.String(50))
    last_name = db.Column(db.String(50))
    is_admin = db.Column(db.Boolean, default=False)
    is_group_admin = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    currency_symbol = db.Column(db.String(5), default='$')
    date_format = db.Column(db.String(20), default='MM/DD/YYYY')
    
    # 2FA fields
    totp_secret = db.Column(db.String(32))  # Base32 encoded secret
    two_factor_enabled = db.Column(db.Boolean, default=False)
    two_factor_setup_complete = db.Column(db.Boolean, default=False)
    
    # Relationship with groups
    groups = db.relationship('Group', secondary=user_group, backref=db.backref('users', lazy='dynamic'))
    
    def __init__(self, username, email, password, first_name=None, last_name=None, is_admin=False, is_group_admin=False):
        self.username = username
        self.email = email
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')
        self.first_name = first_name
        self.last_name = last_name
        self.is_admin = is_admin
        self.is_group_admin = is_group_admin
        # Generate TOTP secret on user creation
        self.totp_secret = pyotp.random_base32()
    
    @property
    def full_name(self):
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.username
    
    @property
    def role_display(self):
        """Return a user-friendly role display"""
        if self.is_admin:
            return "Administrator"
        elif self.is_group_admin:
            return "Group Admin"
        else:
            return "User"
    
    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)
    
    def set_password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')
    
    # 2FA Methods
    def get_totp_uri(self, app_name="Asset Lookup"):
        """Generate TOTP URI for QR code"""
        if not self.totp_secret:
            self.totp_secret = pyotp.random_base32()
        
        totp = pyotp.TOTP(self.totp_secret)
        return totp.provisioning_uri(
            name=self.email,
            issuer_name=app_name
        )
    
    def verify_totp(self, token):
        """Verify TOTP token"""
        if not self.totp_secret:
            return False
        
        totp = pyotp.TOTP(self.totp_secret)
        return totp.verify(token, valid_window=1)  # Allow 1 window tolerance
    
    def enable_two_factor(self):
        """Enable 2FA for this user"""
        self.two_factor_enabled = True
        self.two_factor_setup_complete = True
        
    def disable_two_factor(self):
        """Disable 2FA for this user"""
        self.two_factor_enabled = False
        self.two_factor_setup_complete = False
        # Keep the secret for potential re-enabling
    
    def needs_2fa_setup(self):
        """Check if user needs to complete 2FA setup"""
        from app.utils.config_service import ConfigService
        system_2fa_enabled = ConfigService.is_2fa_enabled()
        
        return (system_2fa_enabled and 
                not self.two_factor_setup_complete)
    
    def requires_2fa_verification(self):
        """Check if user requires 2FA verification for login"""
        from app.utils.config_service import ConfigService
        system_2fa_enabled = ConfigService.is_2fa_enabled()
        
        return (system_2fa_enabled and 
                self.two_factor_enabled and 
                self.two_factor_setup_complete)
    
    # Existing methods remain unchanged...
    def get_accessible_assets(self):
        """Get all assets this user can access based on their role and group membership"""
        # Import here to avoid circular imports
        from app.models.asset import Asset
        from app.models.group import Group
        
        # Admins can see all assets
        if self.is_admin:
            return Asset.query
        
        # Build query for accessible assets
        user_group_ids = [g.id for g in self.groups]
        
        if user_group_ids:
            query = Asset.query.filter(
                db.or_(
                    # Assets assigned directly to the user
                    Asset.assigned_user_id == self.id,
                    # Assets assigned to groups the user belongs to
                    Asset.assigned_groups.any(Group.id.in_(user_group_ids))
                )
            )
        else:
            # User has no groups, can only see directly assigned assets
            query = Asset.query.filter(Asset.assigned_user_id == self.id)
        
        return query
    
    def has_permission(self, permission, asset=None):
        """
        Enhanced permission checking that supports group-based asset permissions
        """
        # Admins have all permissions
        if self.is_admin:
            return True
        
        # FIXED: Group Admins should have CREATE permission globally
        if self.is_group_admin and permission == 'CREATE':
            return True
        
        # FIXED: Group Admins should have EDIT permission globally for assets they can access
        if self.is_group_admin and permission == 'EDIT':
            if asset is None:
                return True  # Global EDIT permission for Group Admins
            # Check if they have access to this specific asset
            if (asset.assigned_user_id == self.id or 
                any(group in asset.assigned_groups for group in self.groups)):
                return True
        
        # Check if user has the permission through any group
        for group in self.groups:
            for perm in group.permissions:
                if perm.name == permission:
                    # If checking for a specific asset
                    if asset:
                        # Check if the group is assigned to this asset
                        if group in asset.assigned_groups:
                            return True
                        # Also check if user is directly assigned to the asset
                        if asset.assigned_user_id == self.id:
                            return True
                    else:
                        # Global permission (no specific asset)
                        return True
        
        # Special case: If user is assigned to an asset, they get basic permissions
        if asset and asset.assigned_user_id == self.id:
            # Assigned users can view and edit their assets, but not delete unless explicitly granted
            if permission in ['VIEW', 'EDIT']:
                return True
        
        return False
    
    def can_delete_asset(self, asset):
        """
        Check if user can delete a specific asset
        Returns: (can_delete: bool, reason: str)
        """
        # Admin can delete anything
        if self.is_admin:
            return True, "Admin privileges"
        
        # FIXED: Group Admins can delete assets they have access to
        if self.is_group_admin:
            # Check if they have access to this asset through their groups or direct assignment
            if (asset.assigned_user_id == self.id or 
                any(group in asset.assigned_groups for group in self.groups)):
                return True, "Group Admin privileges for accessible assets"
        
        # Check direct DELETE permission
        if self.has_permission('DELETE', asset):
            return True, "Direct DELETE permission"
        
        # Check group-based permissions
        for user_group in self.groups:
            if user_group in asset.assigned_groups:
                for perm in user_group.permissions:
                    if perm.name == 'DELETE':
                        return True, f"DELETE permission via group: {user_group.name}"
        
        return False, "No DELETE permission for this asset"

    def get_asset_groups(self, asset):
        """
        Get list of user's groups that are assigned to the asset
        """
        return [group for group in self.groups if group in asset.assigned_groups]

    def get_permission_context(self, permission, asset):
        """
        Get detailed context about why user has permission for an asset
        """
        context = {
            'has_permission': False,
            'reasons': [],
            'groups': []
        }
        
        if self.is_admin:
            context['has_permission'] = True
            context['reasons'].append('System Administrator')
            return context
        
        # FIXED: Add Group Admin context
        if self.is_group_admin:
            if permission in ['CREATE', 'EDIT']:
                context['has_permission'] = True
                context['reasons'].append('Group Administrator')
                if asset and (asset.assigned_user_id == self.id or 
                             any(group in asset.assigned_groups for group in self.groups)):
                    context['reasons'].append('Access to asset via Group Admin role')
                elif permission == 'CREATE':
                    context['reasons'].append('Global CREATE permission via Group Admin role')
                return context
            elif permission == 'DELETE' and asset:
                if (asset.assigned_user_id == self.id or 
                    any(group in asset.assigned_groups for group in self.groups)):
                    context['has_permission'] = True
                    context['reasons'].append('Group Administrator with asset access')
                    return context
        
        # Check direct permissions
        for group in self.groups:
            for perm in group.permissions:
                if perm.name == permission:
                    if not asset or group in asset.assigned_groups or asset.assigned_user_id == self.id:
                        context['has_permission'] = True
                        if asset and group in asset.assigned_groups:
                            context['reasons'].append(f'Group membership: {group.name}')
                            context['groups'].append(group.name)
                        elif asset and asset.assigned_user_id == self.id:
                            context['reasons'].append('Directly assigned to asset')
                        else:
                            context['reasons'].append(f'Global {permission} permission')
        
        return context

    def can_assign_groups(self, groups=None):
        """Check if user can assign specific groups to assets"""
        if self.is_admin:
            return True  # Admins can assign any groups
        
        if not self.is_group_admin:
            return False  # Regular users cannot assign groups they don't belong to
        
        if groups is None:
            return True  # Group admins can assign groups in general
        
        # Group admins can only assign groups they belong to
        user_group_ids = {g.id for g in self.groups}
        requested_group_ids = {g.id if hasattr(g, 'id') else g for g in groups}
        
        return requested_group_ids.issubset(user_group_ids)
    
    def get_assignable_groups(self):
        """Get groups that this user can assign to assets"""
        # Import here to avoid circular imports
        from app.models.group import Group
        
        if self.is_admin:
            return Group.query.all()  # Admins can assign any groups
        elif self.is_group_admin:
            return list(self.groups)  # Group admins can assign their own groups
        else:
            return []  # Regular users cannot assign groups
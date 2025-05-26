# app/__init__.py - Fixed version with explicit model imports

from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from flask_cors import CORS
from apscheduler.schedulers.background import BackgroundScheduler
import os
import logging
from logging.handlers import RotatingFileHandler

# Initialize extensions
db = SQLAlchemy()
bcrypt = Bcrypt()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message_category = 'info'

# Create a global scheduler
scheduler = BackgroundScheduler()

def create_app():
    # Create Flask app
    app = Flask(__name__)
    
    # Load configuration
    app.config.from_object('app.config.Config')
    
    # Load settings from file if it exists
    import json
    settings_file = os.path.join(app.root_path, '..', 'instance', 'settings.json')
    if os.path.exists(settings_file):
        try:
            with open(settings_file, 'r') as f:
                settings = json.load(f)
                
            # Update app config with file settings
            for key, value in settings.items():
                app.config[key] = value
                
            app.logger.info("Loaded settings from file")
        except Exception as e:
            app.logger.error(f"Error loading settings from file: {str(e)}")
            
    # Initialize database and other extensions
    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    
    # CRITICAL: Import all models BEFORE creating tables
    with app.app_context():
        # Initialize OIDC client within application context
        from app.utils.oidc import oidc_client
        oidc_client.init_app(app)
        
        app.logger.info("Importing all models...")
        try:
            # Import all models explicitly to ensure they're registered
            from app.models.user import User
            from app.models.group import Group, Permission
            from app.models.asset import Asset, AssetFile
            from app.models.tag import Tag
            from app.models.notification import NotificationSetting, NotificationLog
            from app.models.audit import AuditLog
            from app.models.setting import Setting
            
            app.logger.info("✅ All models imported successfully")
            
            # Now create tables
            app.logger.info("Creating database tables...")
            
            # Check current tables
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            existing_tables = inspector.get_table_names()
            app.logger.info(f"Existing tables before create_all(): {existing_tables}")
            
            # Create all tables
            db.create_all()
            
            # Check tables after creation
            inspector = inspect(db.engine)
            new_tables = inspector.get_table_names()
            app.logger.info(f"Tables after create_all(): {new_tables}")
            
            if len(new_tables) > 0:
                app.logger.info("✅ Database tables created successfully")
                
                # Initialize default data ONLY after tables exist
                app.logger.info("Initializing default data...")
                initialize_default_data()
                app.logger.info("✅ Default data initialized successfully")
            else:
                app.logger.error("❌ No tables were created!")
                
        except Exception as e:
            app.logger.error(f"❌ Database initialization error: {str(e)}")
            import traceback
            app.logger.error(traceback.format_exc())
    
    # Add custom template filters
    from app.utils import time_utils

    @app.template_filter('format_datetime')
    def format_datetime_filter(value, format='%Y-%m-%d %H:%M:%S'):
        """Format a datetime according to the given format and the application timezone."""
        if value is None:
            return ""
        return time_utils.format_datetime(value, format)

    @app.template_filter('format_date')
    def format_date_filter(value, format='%Y-%m-%d'):
        """Format a date according to the given format."""
        if value is None:
            return ""
        from datetime import datetime
        if isinstance(value, datetime):
            return time_utils.format_datetime(value, format)
        return value.strftime(format)

    @app.template_filter('can_delete_asset')
    def can_delete_asset_filter(user, asset):
        """Template filter to check if user can delete an asset"""
        can_delete, reason = user.can_delete_asset(asset)
        return can_delete

    @app.template_filter('get_asset_groups')
    def get_asset_groups_filter(user, asset):
        """Template filter to get user's groups assigned to asset"""
        return user.get_asset_groups(asset)

    @app.template_filter('permission_context')
    def permission_context_filter(user, permission, asset=None):
        """Template filter to get permission context"""
        return user.get_permission_context(permission, asset)
    
    # Register blueprints
    from app.routes.auth import auth
    from app.routes.asset import asset
    from app.routes.admin import admin
    from app.routes.api import api
    from app.routes.notification import notification
    from app.routes.static_pages import static_pages
    from app.routes.oidc_auth import oidc_auth
    from app.routes.backup import backup  # Add this import
    
    app.register_blueprint(static_pages)    
    app.register_blueprint(auth)
    app.register_blueprint(asset)
    app.register_blueprint(admin)
    app.register_blueprint(api)
    app.register_blueprint(notification)
    app.register_blueprint(oidc_auth)
    app.register_blueprint(backup)  # Add this line
    
    # Error handlers
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        app.logger.error(f'Server Error: {str(error)}')
        return render_template('errors/500.html'), 500
    
    # Setup scheduler - AFTER database is ready
    with app.app_context():
        try:
            app.logger.info("Setting up scheduler...")
            
            # Load database settings now that tables exist
            load_database_settings()
            
            from app.utils.scheduler import setup_scheduler
            setup_scheduler(app, scheduler)
            
            try:
                from app.utils.backup_scheduler import setup_backup_scheduler
                setup_backup_scheduler(app, scheduler)
                app.logger.info("✅ Backup scheduler initialized successfully")
                
            except Exception as e:
                app.logger.error(f"❌ Error setting up backup scheduler: {str(e)}")
                import traceback
                app.logger.error(traceback.format_exc())

            if not scheduler.running:
                scheduler.start()
                app.logger.info("✅ Scheduler started successfully")
                
        except Exception as e:
            app.logger.error(f"❌ Scheduler setup error: {str(e)}")
            import traceback
            app.logger.error(traceback.format_exc())
    
    # Ensure upload directory exists
    upload_path = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'])
    os.makedirs(upload_path, exist_ok=True)
    app.logger.info(f"Upload directory ensured: {upload_path}")
    
    # Add context processor for global variables
    @app.context_processor
    def inject_globals():
        from datetime import datetime
        return dict(current_year=datetime.now().year)
    
    return app


def initialize_default_data():
    """Initialize default permissions, groups, and admin user if database is empty"""
    try:
        from app.models.user import User
        from app.models.group import Group, Permission
        from app.models.notification import NotificationSetting
        
        # Check if any users exist - ONLY after tables are created
        user_count = User.query.count()
        if user_count > 0:
            from flask import current_app
            current_app.logger.info(f"Database already has {user_count} users, skipping initialization")
            return  # Data already exists
        
        from flask import current_app
        current_app.logger.info("Database is empty, creating default data...")
        
        # Create permissions
        permissions_data = {
            'CREATE': 'Create new assets',
            'EDIT': 'Edit existing assets',
            'DELETE': 'Delete assets',
            'VIEW': 'View asset details',
            'EXPORT': 'Export asset data',
            'IMPORT': 'Import asset data'
        }
        
        for perm_name, perm_desc in permissions_data.items():
            if not Permission.query.filter_by(name=perm_name).first():
                perm = Permission(name=perm_name, description=perm_desc)
                db.session.add(perm)
        
        db.session.flush()  # Get IDs for permissions
        
        # Create admin group
        admin_group = Group(name='Administrators', description='Users with full administrative access')
        admin_group.permissions = Permission.query.all()
        db.session.add(admin_group)
        
        # Create group admin group
        group_admin_group = Group(name='Group Administrators', description='Users with group management and asset creation privileges')
        group_admin_permissions = Permission.query.filter(Permission.name.in_(['CREATE', 'EDIT', 'VIEW', 'EXPORT', 'IMPORT'])).all()
        group_admin_group.permissions = group_admin_permissions
        db.session.add(group_admin_group)
        
        # Create regular user group
        user_group = Group(name='Users', description='Regular users with limited access')
        user_permissions = Permission.query.filter(Permission.name.in_(['VIEW', 'EXPORT'])).all()
        user_group.permissions = user_permissions
        db.session.add(user_group)
        
        db.session.flush()  # Get IDs for groups
        
        # Create admin user
        admin_user = User(
            username='admin',
            email='admin@example.com',
            password='admin123',
            first_name='Admin',
            last_name='User',
            is_admin=True
        )
        admin_user.groups.append(admin_group)
        db.session.add(admin_user)
        
        # Create group admin user
        group_admin_user = User(
            username='groupadmin',
            email='groupadmin@example.com',
            password='groupadmin123',
            first_name='Group',
            last_name='Admin',
            is_admin=False,
            is_group_admin=True
        )
        group_admin_user.groups.append(group_admin_group)
        db.session.add(group_admin_user)
        
        # Create regular user
        regular_user = User(
            username='user',
            email='user@example.com',
            password='user123',
            first_name='Regular',
            last_name='User',
            is_admin=False
        )
        regular_user.groups.append(user_group)
        db.session.add(regular_user)
        
        # Create default notification settings - ONLY use basic fields that exist
        try:
            # Try creating with only the basic fields from the __init__ method
            default_notification_settings = NotificationSetting(
                is_system_default=True,
                frequency='once',
                day_of_week=1,
                preferred_time='09:00',
                preferred_second_time='15:00'
            )
            
            # Set additional fields after creation if they exist
            if hasattr(default_notification_settings, 'initial_alert_enabled'):
                default_notification_settings.initial_alert_enabled = True
                default_notification_settings.initial_alert_days = 30
                default_notification_settings.initial_alert_time = '09:00'
                
            if hasattr(default_notification_settings, 'secondary_alert_enabled'):
                default_notification_settings.secondary_alert_enabled = True
                default_notification_settings.secondary_alert_days = 15
                default_notification_settings.secondary_frequency = 'daily'
                default_notification_settings.secondary_custom_days = 1
                default_notification_settings.secondary_day_of_week = 1
                default_notification_settings.secondary_alert_time = '09:00'
                
            if hasattr(default_notification_settings, 'scheduler_frequency_type'):
                default_notification_settings.scheduler_frequency_type = 'hours'
                default_notification_settings.scheduler_frequency_value = 1
                default_notification_settings.scheduler_enabled = True
            
            db.session.add(default_notification_settings)
            current_app.logger.info("✅ Default notification settings created")
            
        except Exception as ns_error:
            current_app.logger.warning(f"Could not create notification settings: {str(ns_error)}")
            # Continue without notification settings if there's an issue
        
        # Commit all changes
        db.session.commit()
        
        current_app.logger.info("Default users created:")
        current_app.logger.info("  - admin / admin123 (Administrator)")
        current_app.logger.info("  - groupadmin / groupadmin123 (Group Admin)")
        current_app.logger.info("  - user / user123 (Regular User)")
        
    except Exception as e:
        from flask import current_app
        current_app.logger.error(f"Error in initialize_default_data: {str(e)}")
        import traceback
        current_app.logger.error(traceback.format_exc())
        db.session.rollback()
        raise


def load_database_settings():
    """Load configuration from database settings"""
    try:
        from app.utils.config_service import ConfigService
        from app.models.setting import Setting
        
        # Check if settings table exists
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        if 'settings' in inspector.get_table_names():
            # Override config with database settings
            config_items = {
                'ALLOW_REGISTRATION': ConfigService.get_bool('ALLOW_REGISTRATION'),
                'TWO_FACTOR_ENABLED': ConfigService.get_bool('TWO_FACTOR_ENABLED'),
                'APP_TIMEZONE': ConfigService.get_setting('APP_TIMEZONE'),
                'MAIL_SERVER': ConfigService.get_setting('MAIL_SERVER'),
                'MAIL_PORT': ConfigService.get_int('MAIL_PORT'),
                'MAIL_USE_TLS': ConfigService.get_bool('MAIL_USE_TLS'),
                'MAIL_USERNAME': ConfigService.get_setting('MAIL_USERNAME'),
                'MAIL_PASSWORD': ConfigService.get_setting('MAIL_PASSWORD'),
                'MAIL_DEFAULT_SENDER': ConfigService.get_setting('MAIL_DEFAULT_SENDER')
            }
            
            # Update app config
            from flask import current_app
            for key, value in config_items.items():
                if value is not None:
                    current_app.config[key] = value
                    
            current_app.logger.info("Loaded configuration from database")
            
    except Exception as e:
        from flask import current_app
        current_app.logger.error(f"Error loading database settings: {str(e)}")
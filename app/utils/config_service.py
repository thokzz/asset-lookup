# app/utils/config_service.py - Updated to handle 2FA settings properly
from app import db
from app.models.setting import Setting
from flask import current_app
import os
import json

class ConfigService:
    @staticmethod
    def get_setting(key, default=None):
        """Get a setting value, checking multiple sources in order"""
        # 1. First check current app config (runtime settings)
        if hasattr(current_app, 'config') and key in current_app.config:
            return current_app.config[key]
        
        # 2. Check settings file
        try:
            settings_file = os.path.join(current_app.root_path, '..', 'instance', 'settings.json')
            if os.path.exists(settings_file):
                with open(settings_file, 'r') as f:
                    settings = json.load(f)
                    if key in settings:
                        # Also update the app config for consistency
                        current_app.config[key] = settings[key]
                        return settings[key]
        except Exception as e:
            current_app.logger.error(f"Error reading settings file: {str(e)}")
        
        # 3. Check database settings
        try:
            setting = Setting.query.filter_by(id=key).first()
            if setting:
                value = setting.value
                # Try to parse JSON values
                try:
                    import json
                    parsed_value = json.loads(value)
                    # Update app config for consistency
                    current_app.config[key] = parsed_value
                    return parsed_value
                except:
                    # Update app config for consistency
                    current_app.config[key] = value
                    return value
        except Exception as e:
            current_app.logger.error(f"Error reading database setting {key}: {str(e)}")
        
        # 4. Return default
        return default
    
    @staticmethod
    def get_bool(key, default=False):
        """Get a boolean setting value"""
        value = ConfigService.get_setting(key, default)
        
        # Handle various boolean representations
        if isinstance(value, bool):
            return value
        elif isinstance(value, str):
            return value.lower() in ('true', '1', 'yes', 'on', 'enabled')
        elif isinstance(value, int):
            return bool(value)
        else:
            return bool(default)
    
    @staticmethod
    def get_int(key, default=0):
        """Get an integer setting value"""
        value = ConfigService.get_setting(key, default)
        try:
            return int(value)
        except (ValueError, TypeError):
            return int(default)
    
    @staticmethod
    def set_setting(key, value):
        """Set a setting value in the database"""
        try:
            setting = Setting.query.filter_by(id=key).first()
            if setting:
                setting.value = str(value) if not isinstance(value, str) else value
            else:
                setting = Setting(id=key, value=str(value) if not isinstance(value, str) else value)
                db.session.add(setting)
            
            # Also update the app config for immediate availability
            current_app.config[key] = value
            
            db.session.commit()
            return True
        except Exception as e:
            current_app.logger.error(f"Error setting {key}: {str(e)}")
            db.session.rollback()
            return False
    
    @staticmethod
    def refresh_config():
        """Refresh all configuration from file and database"""
        try:
            # Load from settings file
            settings_file = os.path.join(current_app.root_path, '..', 'instance', 'settings.json')
            if os.path.exists(settings_file):
                with open(settings_file, 'r') as f:
                    settings = json.load(f)
                    for key, value in settings.items():
                        current_app.config[key] = value
                        
            current_app.logger.info("Configuration refreshed successfully")
        except Exception as e:
            current_app.logger.error(f"Error refreshing configuration: {str(e)}")
    
    @staticmethod
    def is_2fa_enabled():
        """Specific method to check if 2FA is enabled system-wide"""
        return ConfigService.get_bool('TWO_FACTOR_ENABLED', False)
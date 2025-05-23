import os
import secrets

class Config:
    # Basic configuration
    SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY') or secrets.token_hex(32)
    STATIC_FOLDER = 'static'
    
    # External URL settings
    SERVER_HOST = os.environ.get('SERVER_HOST', '0.0.0.0')
    SERVER_PORT = int(os.environ.get('SERVER_PORT', 5000))
    EXTERNAL_URL = os.environ.get('EXTERNAL_URL')
    
    # Database configuration - FIXED: Use absolute path
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:////app/instance/asset_lookup.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # File upload settings
    UPLOAD_FOLDER = 'static/uploads'
    ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'xls', 'xlsx', 'txt', 'png', 'jpg', 'jpeg', 'gif', 'zip', 'rar'}
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10MB
    
    # Email settings
    MAIL_SERVER = os.environ.get('MAIL_SERVER') or ''
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 587)
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'True') != 'False'
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME') or ''
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD') or ''
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER') or 'noreply@assetlookup.com'
    
    # Application settings
    ALLOW_REGISTRATION = os.environ.get('ALLOW_REGISTRATION', 'True') != 'False'
    APP_TIMEZONE = os.environ.get('APP_TIMEZONE') or 'UTC'
    
    # 2FA settings
    TWO_FACTOR_ENABLED = os.environ.get('TWO_FACTOR_ENABLED', 'False') == 'True'
    
    # Frontend URL for CORS
    FRONTEND_URL = os.environ.get('FRONTEND_URL') or '*'
    
    # Ensure we don't have redirection issues
    PREFERRED_URL_SCHEME = os.environ.get('PREFERRED_URL_SCHEME', 'http')
    APPLICATION_ROOT = '/'
    SESSION_COOKIE_SECURE = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SERVER_NAME = None  # Important: Remove server name to prevent redirection issues
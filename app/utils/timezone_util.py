# utils/timezone_util.py
import pytz
from datetime import datetime
from flask import current_app, g, request
from functools import wraps

def get_app_timezone():
    """Get the application timezone configured in app.config"""
    app_tz_name = current_app.config.get('APP_TIMEZONE', 'UTC')
    try:
        return pytz.timezone(app_tz_name)
    except pytz.exceptions.UnknownTimeZoneError:
        current_app.logger.warning(f"Unknown timezone: {app_tz_name}, falling back to UTC")
        return pytz.UTC

def utc_to_local(utc_dt):
    """Convert UTC datetime to local timezone configured in the application"""
    if utc_dt is None:
        return None
        
    if utc_dt.tzinfo is None:
        # Assume naive datetimes are UTC
        utc_dt = pytz.UTC.localize(utc_dt)
    
    local_tz = get_app_timezone()
    return utc_dt.astimezone(local_tz)

def local_to_utc(local_dt):
    """Convert local datetime to UTC for storage"""
    if local_dt is None:
        return None
        
    local_tz = get_app_timezone()
    
    if local_dt.tzinfo is None:
        # Assume naive datetimes are in app's local timezone
        local_dt = local_tz.localize(local_dt)
    
    return local_dt.astimezone(pytz.UTC)

def local_now():
    """Get current time in application timezone"""
    utc_now = datetime.now(pytz.UTC)
    return utc_to_local(utc_now)

def format_datetime(dt, format_string=None):
    """Format datetime according to application settings"""
    if dt is None:
        return ""
    
    # Convert to local timezone if it's a UTC time
    if dt.tzinfo is None or dt.tzinfo == pytz.UTC:
        dt = utc_to_local(dt)
    
    # Use default format if none provided
    if format_string is None:
        format_string = '%Y-%m-%d %H:%M:%S'
    
    return dt.strftime(format_string)

def timezone_middleware():
    """Flask middleware to handle timezone conversion in request context"""
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            # Store the application timezone in the request context
            g.timezone = get_app_timezone()
            return f(*args, **kwargs)
        return wrapped
    return decorator

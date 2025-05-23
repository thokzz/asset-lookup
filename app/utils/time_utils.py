# app/utils/time_utils.py
import pytz
from datetime import datetime, timezone, timedelta
from flask import current_app

def get_app_timezone():
    """Get the application timezone from configuration"""
    tz_name = current_app.config.get('APP_TIMEZONE', 'UTC')
    try:
        return pytz.timezone(tz_name)
    except pytz.exceptions.UnknownTimeZoneError:
        current_app.logger.error(f"Unknown timezone: {tz_name}, falling back to UTC")
        return pytz.UTC

def utcnow():
    """Get current UTC time with timezone info"""
    return datetime.now(timezone.utc)

def localnow():
    """Get current time in application timezone"""
    app_tz = get_app_timezone()
    return datetime.now(timezone.utc).astimezone(app_tz)

def utc_to_local(utc_dt):
    """Convert UTC datetime to local datetime using app timezone"""
    if utc_dt is None:
        return None
        
    # Add timezone info if it's naive
    if utc_dt.tzinfo is None:
        utc_dt = utc_dt.replace(tzinfo=timezone.utc)
        
    # Convert to app timezone
    app_tz = get_app_timezone()
    return utc_dt.astimezone(app_tz)

def local_to_utc(local_dt):
    """Convert local datetime to UTC datetime"""
    if local_dt is None:
        return None
        
    # If it has no timezone, assume it's in app timezone
    if local_dt.tzinfo is None:
        app_tz = get_app_timezone()
        local_dt = app_tz.localize(local_dt)
        
    # Convert to UTC
    return local_dt.astimezone(timezone.utc)

def format_datetime(dt, format_str=None):
    """Format datetime according to application settings"""
    if dt is None:
        return ""
    
    # Ensure datetime has timezone info
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    
    # Convert to local time
    local_dt = utc_to_local(dt)
    
    # Use default format if none provided
    if format_str is None:
        format_str = '%Y-%m-%d %H:%M:%S'
    
    return local_dt.strftime(format_str)

def parse_datetime(date_str, format_str=None):
    """Parse datetime string to UTC datetime"""
    if not date_str:
        return None
        
    # Use default format if none provided
    if format_str is None:
        format_str = '%Y-%m-%d %H:%M:%S'
    
    # Parse as naive datetime
    dt = datetime.strptime(date_str, format_str)
    
    # Localize to app timezone then convert to UTC
    app_tz = get_app_timezone()
    local_dt = app_tz.localize(dt)
    return local_dt.astimezone(timezone.utc)

def today():
    """Get today's date in application timezone"""
    return localnow().date()

def get_expiry_threshold(days=30):
    """Calculate expiry threshold date (today + days)"""
    return (today() + timedelta(days=days))
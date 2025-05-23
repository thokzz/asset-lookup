# app/routes/api.py - Updated with notification response data and corrected asset counting
from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from app import db
from app.models.asset import Asset
from app.models.tag import Tag
from app.models.notification import NotificationLog
from app.utils.time_utils import today, format_datetime, utcnow, utc_to_local, get_app_timezone
from datetime import timedelta, datetime
from dateutil.relativedelta import relativedelta

api = Blueprint('api', __name__)

@api.route('/api/dashboard/stats')
@login_required
def dashboard_stats():
    # Use the today() function from time_utils
    current_date = today()
    
    # Get accessible assets based on user role
    accessible_assets = current_user.get_accessible_assets()
    
    # Define the expiry threshold (30 days from today)
    expiry_threshold = current_date + timedelta(days=30)
    
    # Good Standing assets: warranty expires AFTER 30 days from now (31+ days remaining)
    good_standing_count = accessible_assets.filter(
        Asset.warranty_expiry_date > expiry_threshold
    ).count()
    
    # Expiring soon assets: warranty expires within next 30 days (1-30 days remaining)
    expiring_count = accessible_assets.filter(
        Asset.warranty_expiry_date > current_date,
        Asset.warranty_expiry_date <= expiry_threshold
    ).count()
    
    # Expired assets: warranty date has passed (0 days remaining)
    expired_count = accessible_assets.filter(Asset.warranty_expiry_date <= current_date).count()
    
    total_count = accessible_assets.count()
    
    return jsonify({
        'good_standing': good_standing_count,  # Updated to match new naming
        'expiring': expiring_count,
        'expired': expired_count,
        'total': total_count,
        'as_of': format_datetime(utcnow())
    })

@api.route('/api/dashboard/expiration-timeline')
@login_required
def expiration_timeline():
    # Get expiration counts by month for the next 12 months
    timeline_data = []
    
    # Use the today() function from time_utils
    current_date = today()
    
    # Get accessible assets based on user role
    accessible_assets = current_user.get_accessible_assets()
    
    for i in range(12):
        # Use a more accurate way to add months - first day of each month
        if i == 0:
            # For the current month, start from today
            month_start = current_date
        else:
            # For future months, start from the 1st of the month
            month_start = current_date.replace(day=1) + relativedelta(months=i)
        
        # Calculate the end of the month properly
        if i == 11:
            # For the last month in our range, add one more month to include everything
            month_end = month_start.replace(day=1) + relativedelta(months=1)
        else:
            # For other months, get the 1st of the next month
            month_end = month_start.replace(day=1) + relativedelta(months=1)
        
        count = accessible_assets.filter(
            Asset.warranty_expiry_date >= month_start,
            Asset.warranty_expiry_date < month_end
        ).count()
        
        month_name = month_start.strftime('%b %Y')
        timeline_data.append({
            'month': month_name,
            'count': count,
            'start_date': month_start.isoformat(),
            'end_date': month_end.isoformat()
        })
    
    return jsonify(timeline_data)

# app/routes/api.py - Updated notification response endpoints

@api.route('/api/dashboard/notification-responses')
@login_required
def notification_responses():
    """API endpoint for notification response data - Fixed to count assets, not responses"""
    try:
        current_date = today()
        current_year_start = datetime(current_date.year, 1, 1)
        current_year_end = datetime(current_date.year + 1, 1, 1)
        
        # Get all accessible asset IDs for filtering notification logs
        accessible_assets = current_user.get_accessible_assets()
        accessible_asset_ids = [asset.id for asset in accessible_assets.all()]
        
        # Initialize response counts
        responses = {
            'renewed': 0,
            'will_not_renew': 0,
            'pending': 0,
            'disable_notifications': 0
        }
        
        # Count assets expiring this year (for comparison baseline)
        assets_expiring_this_year = 0
        
        if accessible_asset_ids:
            # Count assets that are expiring this year (baseline for comparison)
            assets_expiring_this_year = accessible_assets.filter(
                Asset.warranty_expiry_date >= current_year_start,
                Asset.warranty_expiry_date < current_year_end
            ).count()
            
            # Get the latest response per asset for this year
            from sqlalchemy import func
            
            # Subquery to get the latest response date per asset
            latest_responses_subquery = db.session.query(
                NotificationLog.asset_id,
                func.max(NotificationLog.response_date).label('latest_response_date')
            ).filter(
                NotificationLog.asset_id.in_(accessible_asset_ids),
                NotificationLog.response_date >= current_year_start,
                NotificationLog.response_date < current_year_end,
                NotificationLog.response.isnot(None)
            ).group_by(NotificationLog.asset_id).subquery()
            
            # Get the actual latest response for each asset
            latest_responses = db.session.query(
                NotificationLog.asset_id,
                NotificationLog.response
            ).join(
                latest_responses_subquery,
                (NotificationLog.asset_id == latest_responses_subquery.c.asset_id) &
                (NotificationLog.response_date == latest_responses_subquery.c.latest_response_date)
            ).filter(
                NotificationLog.response.isnot(None)
            ).all()
            
            # Count unique assets by their latest response
            for asset_id, response in latest_responses:
                if response in responses:
                    responses[response] += 1
        
        # Calculate total assets with responses
        total_assets_with_responses = sum(responses.values())
        
        return jsonify({
            'responses': responses,
            'total': total_assets_with_responses,
            'assets_expiring_this_year': assets_expiring_this_year,
            'year': current_date.year,
            'as_of': format_datetime(utcnow())
        })
        
    except Exception as e:
        current_app.logger.error(f"Error in notification_responses: {str(e)}")
        import traceback
        current_app.logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

@api.route('/api/dashboard/notification-responses/<int:year>')
@login_required
def notification_responses_by_year(year):
    """API endpoint for notification response data for a specific year - Fixed to count assets"""
    try:
        # Validate year (reasonable range)
        if year < 2020 or year > datetime.now().year + 1:
            return jsonify({'error': 'Invalid year'}), 400
        
        year_start = datetime(year, 1, 1)
        year_end = datetime(year + 1, 1, 1)
        
        # Get all accessible asset IDs for filtering notification logs
        accessible_assets = current_user.get_accessible_assets()
        accessible_asset_ids = [asset.id for asset in accessible_assets.all()]
        
        # Initialize response counts
        responses = {
            'renewed': 0,
            'will_not_renew': 0,
            'pending': 0,
            'disable_notifications': 0
        }
        
        # Count assets expiring this year (for comparison baseline)
        assets_expiring_this_year = 0
        
        if accessible_asset_ids:
            # Count assets that were expiring in the specified year
            assets_expiring_this_year = accessible_assets.filter(
                Asset.warranty_expiry_date >= year_start,
                Asset.warranty_expiry_date < year_end
            ).count()
            
            # Get the latest response per asset for specified year
            from sqlalchemy import func
            
            # Subquery to get the latest response date per asset
            latest_responses_subquery = db.session.query(
                NotificationLog.asset_id,
                func.max(NotificationLog.response_date).label('latest_response_date')
            ).filter(
                NotificationLog.asset_id.in_(accessible_asset_ids),
                NotificationLog.response_date >= year_start,
                NotificationLog.response_date < year_end,
                NotificationLog.response.isnot(None)
            ).group_by(NotificationLog.asset_id).subquery()
            
            # Get the actual latest response for each asset
            latest_responses = db.session.query(
                NotificationLog.asset_id,
                NotificationLog.response
            ).join(
                latest_responses_subquery,
                (NotificationLog.asset_id == latest_responses_subquery.c.asset_id) &
                (NotificationLog.response_date == latest_responses_subquery.c.latest_response_date)
            ).filter(
                NotificationLog.response.isnot(None)
            ).all()
            
            # Count unique assets by their latest response
            for asset_id, response in latest_responses:
                if response in responses:
                    responses[response] += 1
        
        # Calculate total assets with responses
        total_assets_with_responses = sum(responses.values())
        
        return jsonify({
            'responses': responses,
            'total': total_assets_with_responses,
            'assets_expiring_this_year': assets_expiring_this_year,
            'year': year,
            'as_of': format_datetime(utcnow())
        })
        
    except Exception as e:
        current_app.logger.error(f"Error in notification_responses_by_year: {str(e)}")
        import traceback
        current_app.logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

@api.route('/api/tags')
@login_required
def get_tags():
    # For non-admin users, only return tags that are used by their accessible assets
    if current_user.is_admin:
        tags = Tag.query.order_by(Tag.name).all()
    else:
        accessible_assets = current_user.get_accessible_assets()
        accessible_asset_ids = [asset.id for asset in accessible_assets.all()]
        
        if accessible_asset_ids:
            tags = db.session.query(Tag).join(Asset.tags).filter(
                Asset.id.in_(accessible_asset_ids)
            ).distinct().order_by(Tag.name).all()
        else:
            tags = []
    
    return jsonify([{
        'id': tag.id,
        'name': tag.name,
        'color': tag.color
    } for tag in tags])

@api.route('/api/tags', methods=['POST'])
@login_required
def create_tag_api():
    data = request.json
    
    # Validate data
    if not data or 'name' not in data:
        return jsonify({'error': 'Name is required'}), 400
    
    name = data.get('name')
    color = data.get('color', '#6c757d')
    
    # Check if tag already exists
    existing_tag = Tag.query.filter_by(name=name).first()
    if existing_tag:
        return jsonify({'error': 'Tag already exists'}), 400
    
    # Create new tag
    tag = Tag(name=name, color=color)
    db.session.add(tag)
    db.session.commit()
    
    return jsonify({
        'id': tag.id,
        'name': tag.name,
        'color': tag.color
    }), 201

@api.route('/api/search/assets')
@login_required
def search_assets():
    query = request.args.get('q', '')
    
    if not query or len(query) < 2:
        return jsonify([])
    
    search = f"%{query}%"
    
    # Get accessible assets based on user role
    accessible_assets = current_user.get_accessible_assets()
    
    assets = accessible_assets.filter(
        db.or_(
            Asset.product_name.ilike(search),
            Asset.product_model.ilike(search),
            Asset.internal_asset_name.ilike(search),
            Asset.serial_number.ilike(search)
        )
    ).limit(10).all()
    
    return jsonify([{
        'id': asset.id,
        'name': asset.product_name,
        'model': asset.product_model,
        'serial': asset.serial_number,
        'expiry': asset.warranty_expiry_date.strftime('%Y-%m-%d') if asset.warranty_expiry_date else None,
        'status': asset.status,
        'days_remaining': asset.days_remaining
    } for asset in assets])

# New API endpoint for getting assignable groups
@api.route('/api/user/assignable-groups')
@login_required
def get_assignable_groups():
    """Get groups that the current user can assign to assets"""
    groups = current_user.get_assignable_groups()
    
    return jsonify([{
        'id': group.id,
        'name': group.name,
        'description': group.description
    } for group in groups])

# New API endpoint for checking user permissions
@api.route('/api/user/permissions')
@login_required
def get_user_permissions():
    """Get current user's permissions and role information"""
    return jsonify({
        'is_admin': current_user.is_admin,
        'is_group_admin': current_user.is_group_admin,
        'role_display': current_user.role_display,
        'can_create': current_user.has_permission('CREATE'),
        'can_delete': current_user.has_permission('DELETE'),
        'groups': [{
            'id': group.id,
            'name': group.name
        } for group in current_user.groups],
        'assignable_groups': [{
            'id': group.id,
            'name': group.name
        } for group in current_user.get_assignable_groups()]
    })

# Keep existing time-related endpoints unchanged
@api.route('/api/current_time')
def current_time():
    """Returns the current time in the application's timezone"""
    now = utcnow()
    app_tz = get_app_timezone()
    local_now = utc_to_local(now)
    
    return jsonify({
        'current_time': format_datetime(now),
        'timezone': str(app_tz),
        'utc_time': now.strftime('%Y-%m-%d %H:%M:%S'),
        'timezone_offset': local_now.strftime('%z'),
        'timestamp': int(now.timestamp())
    })

@api.route('/api/timezones')
def list_timezones():
    """Returns a list of available timezones"""
    import pytz
    from flask import current_app
    
    common_timezones = [
        'UTC',
        'America/New_York',    # Eastern Time
        'America/Chicago',     # Central Time
        'America/Denver',      # Mountain Time
        'America/Los_Angeles', # Pacific Time
        'Europe/London',       # GMT/BST
        'Europe/Paris',        # Central European Time
        'Asia/Tokyo',          # Japan
        'Asia/Shanghai',       # China
        'Asia/Singapore',      # Singapore
        'Asia/Manila',         # Philippines
        'Australia/Sydney',    # Eastern Australia
    ]
    
    # Get the current app timezone
    current_tz = str(get_app_timezone())
    
    # Build a list of common timezones with their current time
    timezone_data = []
    now = utcnow()
    
    for tz_name in common_timezones:
        try:
            tz = pytz.timezone(tz_name)
            local_time = now.astimezone(tz)
            
            timezone_data.append({
                'name': tz_name,
                'display_name': tz_name.replace('_', ' ').split('/')[-1],
                'current_time': local_time.strftime('%Y-%m-%d %H:%M:%S'),
                'offset': local_time.strftime('%z'),
                'is_current': tz_name == current_tz
            })
        except pytz.exceptions.UnknownTimeZoneError:
            # Skip invalid timezones
            pass
    
    return jsonify({
        'timezones': timezone_data,
        'current_timezone': current_tz,
        'app_timezone': current_app.config.get('APP_TIMEZONE', 'UTC')
    })

# Optional: API endpoint for recent notification activity
@api.route('/api/notifications/recent')
@login_required
def recent_notifications():
    """Get recent notification activity for accessible assets"""
    try:
        limit = min(int(request.args.get('limit', 20)), 100)  # Max 100 records
        
        # Get all accessible asset IDs
        accessible_assets = current_user.get_accessible_assets()
        accessible_asset_ids = [asset.id for asset in accessible_assets.all()]
        
        if not accessible_asset_ids:
            return jsonify([])
        
        # Get recent notifications
        recent_logs = NotificationLog.query.filter(
            NotificationLog.asset_id.in_(accessible_asset_ids)
        ).order_by(NotificationLog.sent_at.desc()).limit(limit).all()
        
        notifications = []
        for log in recent_logs:
            notifications.append({
                'id': log.id,
                'asset_id': log.asset_id,
                'asset_name': log.asset.product_name if log.asset else 'Unknown',
                'recipient_email': log.recipient_email,
                'notification_type': log.notification_type,
                'status': log.status,
                'response': log.response,
                'sent_at': format_datetime(log.sent_at) if log.sent_at else None,
                'response_date': format_datetime(log.response_date) if log.response_date else None
            })
        
        return jsonify(notifications)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
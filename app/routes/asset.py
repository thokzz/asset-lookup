from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, jsonify
from flask_login import login_required, current_user
from app import db
from app.models.asset import Asset, AssetFile
from app.models.tag import Tag
from app.models.group import Group
from app.models.user import User
from werkzeug.utils import secure_filename
from app.utils.audit import log_activity, log_asset_change
import os
from datetime import datetime, date
from datetime import date, timedelta
import uuid
from flask import Blueprint, current_app
from datetime import datetime
from app.models.notification import NotificationLog

asset = Blueprint('asset', __name__)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']

@asset.route('/')
@asset.route('/dashboard')
@login_required
def dashboard():
    today = date.today()
    
    # Get accessible assets based on user role
    accessible_assets = current_user.get_accessible_assets()
    
    # Define the expiry threshold (30 days from today)
    expiry_threshold = today + timedelta(days=30)
    
    # Good Standing assets: warranty expires AFTER 30 days from now (31+ days remaining)
    good_standing_count = accessible_assets.filter(
        Asset.warranty_expiry_date > expiry_threshold
    ).count()
    
    # Expiring soon assets: warranty expires within next 30 days (1-30 days remaining)
    expiring_count = accessible_assets.filter(
        Asset.warranty_expiry_date > today,
        Asset.warranty_expiry_date <= expiry_threshold
    ).count()
    
    # Expired assets: warranty date has passed (0 or negative days remaining)
    expired_count = accessible_assets.filter(Asset.warranty_expiry_date <= today).count()
    
    # Calculate total (should match the sum of the above)
    total_count = accessible_assets.count()
    
    # Get recent assets that are expired or expiring soon (for the table)
    recent_assets = accessible_assets.filter(
        (Asset.warranty_expiry_date <= today) | 
        (Asset.warranty_expiry_date <= expiry_threshold)
    ).order_by(Asset.warranty_expiry_date.asc()).limit(10).all()
    
    # FIXED: Get ASSETS with notification responses for current year (not response count)
    current_year_start = datetime(today.year, 1, 1)
    current_year_end = datetime(today.year + 1, 1, 1)
    
    # Get all accessible asset IDs for filtering
    accessible_asset_ids = [asset.id for asset in accessible_assets.all()]
    
    # Count unique ASSETS that have responses this year (accessible to user)
    notification_responses = {}
    assets_expiring_this_year_count = 0
    
    if accessible_asset_ids:
        # First, count assets that are expiring this year (for comparison baseline)
        assets_expiring_this_year_count = accessible_assets.filter(
            Asset.warranty_expiry_date >= current_year_start,
            Asset.warranty_expiry_date < current_year_end
        ).count()
        
        # Count unique assets with each type of response
        # Use subqueries to get the latest response per asset
        from sqlalchemy import func
        
        # Get the latest response per asset
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
        response_counts = {
            'renewed': 0,
            'will_not_renew': 0,
            'pending': 0,
            'disable_notifications': 0
        }
        
        for asset_id, response in latest_responses:
            if response in response_counts:
                response_counts[response] += 1
        
        notification_responses = response_counts
    else:
        notification_responses = {
            'renewed': 0,
            'will_not_renew': 0,
            'pending': 0,
            'disable_notifications': 0
        }
    
    # Calculate total assets with responses
    total_assets_with_responses = sum(notification_responses.values())
    
    return render_template('assets/dashboard.html', 
        title='Dashboard', 
        good_standing_count=good_standing_count,
        expiring_count=expiring_count,
        expired_count=expired_count,
        total_count=total_count,
        recent_assets=recent_assets,
        # Updated: Notification response data (now counting assets, not responses)
        notification_responses=notification_responses,
        total_responses=total_assets_with_responses,
        assets_expiring_this_year=assets_expiring_this_year_count,
        current_year=today.year
    )

@asset.route('/assets')
@login_required
def asset_list():
    # Get filter and pagination parameters
    status_filter = request.args.get('status', 'all')
    tag_filter = request.args.get('tag', 'all')
    vendor_filter = request.args.get('vendor', 'all')
    search_query = request.args.get('q', '')
    
    # Pagination parameters
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 25, type=int)
    per_page = min(per_page, 100)  # Limit to 100 items per page max
    
    # Sorting parameters
    sort_by = request.args.get('sort_by', 'created_at')
    sort_dir = request.args.get('sort_dir', 'desc')
    
    # Valid sort columns
    valid_sort_columns = [
        'product_name', 'product_model', 'serial_number', 'purchase_date',
        'warranty_expiry_date', 'price', 'vendor_company', 'location',
        'created_at', 'updated_at'
    ]
    
    if sort_by not in valid_sort_columns:
        sort_by = 'created_at'
    
    # Base query - only accessible assets
    query = current_user.get_accessible_assets()
    
    # Today's date for status filtering
    today = date.today()
    expiry_threshold = today + timedelta(days=30)
    
    # Apply status filter with corrected logic
    if status_filter == 'good_standing':
        # Good Standing = expires more than 30 days from now (31+ days remaining)
        query = query.filter(Asset.warranty_expiry_date > expiry_threshold)
    elif status_filter == 'active':
        # Keep 'active' for backward compatibility - same as good_standing
        query = query.filter(Asset.warranty_expiry_date > expiry_threshold)
    elif status_filter == 'expiring':
        # Expiring soon = expires within the next 30 days (1-30 days remaining)
        query = query.filter(
            Asset.warranty_expiry_date > today,
            Asset.warranty_expiry_date <= expiry_threshold
        )
    elif status_filter == 'expired':
        # Expired = warranty_expiry_date is today or in the past (0 days remaining)
        query = query.filter(Asset.warranty_expiry_date <= today)
    
    # Apply tag filter
    if tag_filter != 'all':
        query = query.filter(Asset.tags.any(Tag.id == tag_filter))
    
    # Apply vendor filter
    if vendor_filter != 'all':
        query = query.filter(Asset.vendor_company == vendor_filter)
    
    # Apply search query
    if search_query:
        search = f"%{search_query}%"
        query = query.filter(
            db.or_(
                Asset.product_name.ilike(search),
                Asset.product_model.ilike(search),
                Asset.internal_asset_name.ilike(search),
                Asset.serial_number.ilike(search),
                Asset.vendor_company.ilike(search),
                Asset.location.ilike(search),
                Asset.notes.ilike(search)
            )
        )
    
    # Apply sorting
    sort_column = getattr(Asset, sort_by)
    if sort_dir == 'asc':
        query = query.order_by(sort_column.asc())
    else:
        query = query.order_by(sort_column.desc())
    
    # Execute paginated query
    assets = query.paginate(
        page=page, 
        per_page=per_page, 
        error_out=False
    )
    
    # Get all tags and vendors for filtering dropdowns (from accessible assets only)
    accessible_asset_ids = [asset.id for asset in query.all()]
    if accessible_asset_ids:
        tags = db.session.query(Tag).join(Asset.tags).filter(
            Asset.id.in_(accessible_asset_ids)
        ).distinct().order_by(Tag.name).all()
        vendors = db.session.query(Asset.vendor_company).filter(
            Asset.id.in_(accessible_asset_ids),
            Asset.vendor_company.isnot(None)
        ).distinct().order_by(Asset.vendor_company).all()
    else:
        tags = []
        vendors = []
    
    return render_template('assets/list.html', 
        title='Assets', 
        assets=assets,
        tags=tags,
        vendors=vendors,
        status_filter=status_filter,
        tag_filter=tag_filter,
        vendor_filter=vendor_filter,
        search_query=search_query,
        sort_by=sort_by,
        sort_dir=sort_dir,
        per_page=per_page
    )


@asset.route('/assets/create', methods=['GET', 'POST'])
@login_required
def create_asset():
    # Check permission
    if not current_user.has_permission('CREATE'):
        log_activity(
            action="PERMISSION_DENIED",
            resource_type="Asset",
            description=f"User {current_user.username} attempted to create an asset without permission",
            status="failure"
        )
        flash('You do not have permission to create assets.', 'danger')
        return redirect(url_for('asset.asset_list'))    
    
    if request.method == 'POST':
        # Extract form data
        product_name = request.form.get('product_name')
        product_model = request.form.get('product_model')
        internal_asset_name = request.form.get('internal_asset_name')
        serial_number = request.form.get('serial_number')
        purchase_date = datetime.strptime(request.form.get('purchase_date'), '%Y-%m-%d').date()
        price = float(request.form.get('price') or 0)
        currency_symbol = request.form.get('currency_symbol')
        if currency_symbol == 'custom':
            currency_symbol = request.form.get('custom_currency')
        warranty_duration = int(request.form.get('warranty_duration') or 0)
        location = request.form.get('location')
        vendor_company = request.form.get('vendor_company')
        vendor_email = request.form.get('vendor_email')
        notes = request.form.get('notes')
        disposal_date = None
        if request.form.get('disposal_date'):
            disposal_date = datetime.strptime(request.form.get('disposal_date'), '%Y-%m-%d').date()
        
        assigned_user_id = request.form.get('assigned_user_id')
        if assigned_user_id == '':  # Handle empty string
            assigned_user_id = None
        user_email = request.form.get('user_email')
        alert_period = int(request.form.get('alert_period') or 30)
        
        # Create new asset with only valid parameters
        new_asset = Asset(
            product_name=product_name,
            product_model=product_model,
            internal_asset_name=internal_asset_name,
            serial_number=serial_number,
            purchase_date=purchase_date,
            price=price,
            currency_symbol=currency_symbol,
            warranty_duration=warranty_duration,
            location=location,
            vendor_company=vendor_company,
            vendor_email=vendor_email,
            notes=notes,
            disposal_date=disposal_date,
            assigned_user_id=assigned_user_id,
            user_email=user_email,
            alert_period=alert_period
        )
        
        # Ensure warranty_expiry_date is properly set
        new_asset.update_warranty_expiry_date()
        
        # Handle tags
        tag_ids = request.form.getlist('tags')
        if tag_ids:
            tags = Tag.query.filter(Tag.id.in_(tag_ids)).all()
            new_asset.tags = tags
        
        # Handle groups
        group_ids = request.form.getlist('groups')
        if group_ids:
            groups = Group.query.filter(Group.id.in_(group_ids)).all()
            new_asset.assigned_groups = groups
        
        db.session.add(new_asset)
        db.session.commit()
        
        # Log asset creation
        log_asset_change(
            new_asset, 
            "CREATE",
            description=f"Created asset: {new_asset.product_name}"
        )

        # Handle file uploads
        if 'files' in request.files:
            files = request.files.getlist('files')
            for file in files:
                if file and file.filename and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    # Add unique identifier to prevent filename collisions
                    unique_filename = f"{uuid.uuid4().hex}_{filename}"
                    file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_filename)
                    file.save(os.path.join(current_app.root_path, file_path))
                    
                    # Create file record
                    asset_file = AssetFile(
                        asset_id=new_asset.id,
                        filename=filename,
                        file_path=file_path,
                        file_type=file.content_type,
                        file_size=len(file.read())
                    )
                    file.seek(0)  # Reset file pointer after reading
                    db.session.add(asset_file)
                    
                    # Log file upload
                    log_activity(
                        action="UPLOAD",
                        resource_type="File",
                        resource_id=asset_file.id,
                        description=f"Uploaded file {file.filename} for asset {new_asset.product_name}"
                    )
        
        db.session.commit()
        
        flash('Asset created successfully!', 'success')
        return redirect(url_for('asset.asset_detail', asset_id=new_asset.id))
    
    # GET request - show form
    users = User.query.filter_by(is_active=True).order_by(User.username).all()
    tags = Tag.query.order_by(Tag.name).all()
    groups = Group.query.order_by(Group.name).all()
    
    return render_template('assets/create.html', 
        title='Create Asset',
        users=users,
        tags=tags,
        groups=groups
    )

@asset.route('/assets/<asset_id>')
@login_required
def asset_detail(asset_id):
    # Check if user can access this asset
    accessible_assets = current_user.get_accessible_assets()
    asset = accessible_assets.filter(Asset.id == asset_id).first_or_404()
    
    return render_template('assets/detail.html', title=asset.product_name, asset=asset)

@asset.route('/assets/<asset_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_asset(asset_id):
    asset = Asset.query.get_or_404(asset_id)
    
    # Check permission
    if not current_user.has_permission('EDIT', asset):
        log_activity(
            action="PERMISSION_DENIED",
            resource_type="Asset",
            resource_id=asset.id,
            description=f"User {current_user.username} attempted to edit asset {asset.product_name} without permission",
            status="failure"
        )
        flash('You do not have permission to edit this asset.', 'danger')
        return redirect(url_for('asset.asset_detail', asset_id=asset.id))
    
    if request.method == 'POST':
        # Collect old data for audit
        old_data = {
            'product_name': asset.product_name,
            'product_model': asset.product_model,
            'internal_asset_name': asset.internal_asset_name,
            'serial_number': asset.serial_number,
            'purchase_date': asset.purchase_date.isoformat() if asset.purchase_date else None,
            'price': asset.price,
            'currency_symbol': asset.currency_symbol,
            'warranty_duration': asset.warranty_duration,
            'location': asset.location,
            'vendor_company': asset.vendor_company,
            'vendor_email': asset.vendor_email,
            'notes': asset.notes,
            'disposal_date': asset.disposal_date.isoformat() if asset.disposal_date else None,
            'assigned_user_id': asset.assigned_user_id,
            'user_email': asset.user_email,
            'alert_period': asset.alert_period,
            'tags': [tag.id for tag in asset.tags],
            'assigned_groups': [group.id for group in asset.assigned_groups]
        }
        
        # Update asset data
        asset.product_name = request.form.get('product_name')
        asset.product_model = request.form.get('product_model')
        asset.internal_asset_name = request.form.get('internal_asset_name')
        asset.serial_number = request.form.get('serial_number')
        asset.purchase_date = datetime.strptime(request.form.get('purchase_date'), '%Y-%m-%d').date()
        asset.price = float(request.form.get('price') or 0)
        currency_symbol = request.form.get('currency_symbol')
        if currency_symbol == 'custom':
            currency_symbol = request.form.get('custom_currency')
        asset.currency_symbol = currency_symbol
        asset.warranty_duration = int(request.form.get('warranty_duration') or 0)
        asset.location = request.form.get('location')
        asset.vendor_company = request.form.get('vendor_company')
        asset.vendor_email = request.form.get('vendor_email')
        asset.notes = request.form.get('notes')
        
        if request.form.get('disposal_date'):
            asset.disposal_date = datetime.strptime(request.form.get('disposal_date'), '%Y-%m-%d').date()
        else:
            asset.disposal_date = None
            
        assigned_user_id = request.form.get('assigned_user_id')
        if assigned_user_id == '':  # Handle empty string
            assigned_user_id = None
        asset.assigned_user_id = assigned_user_id
        asset.user_email = request.form.get('user_email')
        asset.alert_period = int(request.form.get('alert_period') or 30)
        
        # Update warranty_expiry_date
        asset.update_warranty_expiry_date()
        
        # Handle tags
        tag_ids = request.form.getlist('tags')
        tags = Tag.query.filter(Tag.id.in_(tag_ids)).all() if tag_ids else []
        asset.tags = tags
        
        # Handle groups
        group_ids = request.form.getlist('groups')
        groups = Group.query.filter(Group.id.in_(group_ids)).all() if group_ids else []
        asset.assigned_groups = groups
        
        # Collect new data for audit
        new_data = {
            'product_name': asset.product_name,
            'product_model': asset.product_model,
            'internal_asset_name': asset.internal_asset_name,
            'serial_number': asset.serial_number,
            'purchase_date': asset.purchase_date.isoformat() if asset.purchase_date else None,
            'price': asset.price,
            'currency_symbol': asset.currency_symbol,
            'warranty_duration': asset.warranty_duration,
            'location': asset.location,
            'vendor_company': asset.vendor_company,
            'vendor_email': asset.vendor_email,
            'notes': asset.notes,
            'disposal_date': asset.disposal_date.isoformat() if asset.disposal_date else None,
            'assigned_user_id': asset.assigned_user_id,
            'user_email': asset.user_email,
            'alert_period': asset.alert_period,
            'tags': [tag.id for tag in asset.tags],
            'assigned_groups': [group.id for group in asset.assigned_groups]
        }
        
        # Log asset update
        log_asset_change(
            asset, 
            "UPDATE",
            old_data,
            new_data,
            description=f"Updated asset: {asset.product_name}"
        )
        
        # Handle file uploads
        if 'files' in request.files:
            files = request.files.getlist('files')
            for file in files:
                if file and file.filename and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    # Add unique identifier to prevent filename collisions
                    unique_filename = f"{uuid.uuid4().hex}_{filename}"
                    file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_filename)
                    file.save(os.path.join(current_app.root_path, file_path))
                    
                    # Create file record
                    asset_file = AssetFile(
                        asset_id=asset.id,
                        filename=filename,
                        file_path=file_path,
                        file_type=file.content_type,
                        file_size=len(file.read())
                    )
                    file.seek(0)  # Reset file pointer after reading
                    db.session.add(asset_file)
        
        db.session.commit()
        flash('Asset updated successfully!', 'success')
        return redirect(url_for('asset.asset_detail', asset_id=asset.id))
    
    # GET request - show form
    users = User.query.filter_by(is_active=True).order_by(User.username).all()
    tags = Tag.query.order_by(Tag.name).all()
    groups = Group.query.order_by(Group.name).all()
    
    return render_template('assets/edit.html', 
        title='Edit Asset',
        asset=asset,
        users=users,
        tags=tags,
        groups=groups
    )


@asset.route('/assets/<asset_id>/delete', methods=['POST'])
@login_required
def delete_asset(asset_id):
    asset = Asset.query.get_or_404(asset_id)
    
    # Enhanced permission check for deletion
    can_delete = False
    
    # Check if user has DELETE permission for this asset
    if current_user.has_permission('DELETE', asset):
        can_delete = True
    
    # Additional check: if user is admin of a group assigned to this asset
    if not can_delete:
        for user_group in current_user.groups:
            if user_group in asset.assigned_groups:
                # Check if this group has DELETE permission
                for perm in user_group.permissions:
                    if perm.name == 'DELETE':
                        can_delete = True
                        break
                if can_delete:
                    break
    
    if not can_delete:
        log_activity(
            action="PERMISSION_DENIED",
            resource_type="Asset",
            resource_id=asset.id,
            description=f"User {current_user.username} attempted to delete asset {asset.product_name} without permission",
            status="failure"
        )
        flash('You do not have permission to delete this asset.', 'danger')
        return redirect(url_for('asset.asset_detail', asset_id=asset.id))
    
    asset_name = asset.product_name  # Store for audit log
    
    # Delete associated files from storage
    for file in asset.files:
        try:
            os.remove(os.path.join(current_app.root_path, file.file_path))
            log_activity(
                action="DELETE",
                resource_type="File",
                resource_id=file.id,
                description=f"Deleted file {file.filename} from asset {asset_name}"
            )
        except Exception as e:
            current_app.logger.error(f"Error deleting file {file.file_path}: {str(e)}")
            log_activity(
                action="DELETE",
                resource_type="File",
                resource_id=file.id,
                description=f"Error deleting file {file.filename}: {str(e)}",
                status="failure"
            )
    
    db.session.delete(asset)
    db.session.commit()
    
    # Log asset deletion with group context
    group_names = [group.name for group in current_user.groups if group in asset.assigned_groups]
    group_context = f" (via group membership: {', '.join(group_names)})" if group_names and not current_user.is_admin else ""
    
    log_activity(
        action="DELETE",
        resource_type="Asset",
        resource_id=asset_id,
        description=f"Deleted asset: {asset_name}{group_context}"
    )
    
    flash('Asset deleted successfully!', 'success')
    return redirect(url_for('asset.asset_list'))

@asset.route('/assets/bulk-delete', methods=['POST'])
@login_required
def bulk_delete_assets():
    """Handle bulk deletion of assets"""
    try:
        # Get selected asset IDs
        selected_ids = request.form.getlist('selected_assets')
        
        if not selected_ids:
            flash('No assets selected for deletion.', 'warning')
            return redirect(url_for('asset.asset_list'))
        
        # Get assets that user can delete
        accessible_assets = current_user.get_accessible_assets()
        assets_to_delete = accessible_assets.filter(Asset.id.in_(selected_ids)).all()
        
        # Check permissions for each asset
        cannot_delete = []
        can_delete = []
        
        for asset in assets_to_delete:
            can_del, reason = current_user.can_delete_asset(asset)
            if can_del:
                can_delete.append(asset)
            else:
                cannot_delete.append(asset.product_name)
        
        if not can_delete:
            flash('You do not have permission to delete any of the selected assets.', 'danger')
            return redirect(url_for('asset.asset_list'))
        
        # Delete assets and their files
        deleted_count = 0
        deleted_names = []
        
        for asset in can_delete:
            asset_name = asset.product_name
            
            # Delete associated files from storage
            for file in asset.files:
                try:
                    os.remove(os.path.join(current_app.root_path, file.file_path))
                    log_activity(
                        action="DELETE",
                        resource_type="File",
                        resource_id=file.id,
                        description=f"Deleted file {file.filename} from asset {asset_name} (bulk operation)"
                    )
                except Exception as e:
                    current_app.logger.error(f"Error deleting file {file.file_path}: {str(e)}")
                    log_activity(
                        action="DELETE",
                        resource_type="File",
                        resource_id=file.id,
                        description=f"Error deleting file {file.filename}: {str(e)}",
                        status="failure"
                    )
            
            db.session.delete(asset)
            deleted_count += 1
            deleted_names.append(asset_name)
        
        db.session.commit()
        
        # Log bulk deletion
        group_names = [group.name for group in current_user.groups if not current_user.is_admin]
        group_context = f" (via group membership: {', '.join(group_names)})" if group_names and not current_user.is_admin else ""
        
        log_activity(
            action="BULK_DELETE",
            resource_type="Asset",
            description=f"Bulk deleted {deleted_count} assets: {', '.join(deleted_names[:5])}"
                       f"{'...' if len(deleted_names) > 5 else ''}{group_context}"
        )
        
        flash(f'Successfully deleted {deleted_count} asset(s).', 'success')
        
        if cannot_delete:
            flash(f'Could not delete {len(cannot_delete)} asset(s) due to insufficient permissions.', 'warning')
            
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error in bulk delete: {str(e)}")
        import traceback
        current_app.logger.error(traceback.format_exc())
        flash('An error occurred during bulk deletion.', 'danger')
    
    return redirect(url_for('asset.asset_list'))

@asset.route('/tags')
@login_required
def tag_list():
    tags = Tag.query.order_by(Tag.name).all()
    return render_template('assets/tags.html', title='Tags', tags=tags)

@asset.route('/tags/create', methods=['GET', 'POST'])
@login_required
def create_tag():
    if request.method == 'POST':
        name = request.form.get('name')
        color = request.form.get('color', "#6c757d")
        
        # Check if tag already exists
        existing_tag = Tag.query.filter_by(name=name).first()
        if existing_tag:
            flash('A tag with this name already exists.', 'danger')
            return redirect(url_for('asset.tag_list'))
        
        new_tag = Tag(name=name, color=color)
        db.session.add(new_tag)
        db.session.commit()
        
        flash('Tag created successfully!', 'success')
        return redirect(url_for('asset.tag_list'))
    
    return render_template('assets/create_tag.html', title='Create Tag')

@asset.route('/tags/<tag_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_tag(tag_id):
    tag = Tag.query.get_or_404(tag_id)
    
    if request.method == 'POST':
        name = request.form.get('name')
        color = request.form.get('color', "#6c757d")
        
        # Check if another tag with this name exists
        existing_tag = Tag.query.filter(Tag.name == name, Tag.id != tag_id).first()
        if existing_tag:
            flash('A tag with this name already exists.', 'danger')
            return redirect(url_for('asset.tag_list'))
        
        tag.name = name
        tag.color = color
        db.session.commit()
        
        flash('Tag updated successfully!', 'success')
        return redirect(url_for('asset.tag_list'))
    
    return render_template('assets/edit_tag.html', title='Edit Tag', tag=tag)

@asset.route('/tags/<tag_id>/delete', methods=['POST'])
@login_required
def delete_tag(tag_id):
    tag = Tag.query.get_or_404(tag_id)
    
    db.session.delete(tag)
    db.session.commit()
    
    flash('Tag deleted successfully!', 'success')
    return redirect(url_for('asset.tag_list'))

@asset.route('/assets/<asset_id>/files/<file_id>/delete', methods=['POST'])
@login_required
def delete_file(asset_id, file_id):
    # Check if user can access this asset
    accessible_assets = current_user.get_accessible_assets()
    asset = accessible_assets.filter(Asset.id == asset_id).first_or_404()
    
    file = AssetFile.query.get_or_404(file_id)
    
    # Check if file belongs to the asset
    if file.asset_id != asset.id:
        flash('File not found.', 'danger')
        return redirect(url_for('asset.asset_detail', asset_id=asset.id))
    
    # Check if user has EDIT permission
    if not current_user.has_permission('EDIT', asset):
        flash('You do not have permission to delete files from this asset.', 'danger')
        return redirect(url_for('asset.asset_detail', asset_id=asset.id))
    
    # Delete file from storage
    try:
        os.remove(os.path.join(current_app.root_path, file.file_path))
    except Exception as e:
        current_app.logger.error(f"Error deleting file {file.file_path}: {str(e)}")
    
    db.session.delete(file)
    db.session.commit()
    
    flash('File deleted successfully!', 'success')
    return redirect(url_for('asset.asset_detail', asset_id=asset.id))

@asset.route('/export')
@login_required
def export_assets():
    # Build CSV content from accessible assets only
    import csv
    from io import StringIO
    
    # Get accessible assets
    assets = current_user.get_accessible_assets().all()
    
    # Create CSV file
    output = StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([
        'Product Name', 'Product Model', 'Internal Asset Name', 'Serial Number',
        'Purchase Date', 'Price', 'Currency Symbol', 'Warranty Duration (months)', 'Warranty Expiry Date',
        'Location', 'Vendor Company', 'Vendor Email', 'Notes', 'Disposal Date',
        'Alert Period (days)', 'Status', 'Tags'
    ])
    
    # Write data
    for asset in assets:
        tags = ', '.join([tag.name for tag in asset.tags])
        writer.writerow([
            asset.product_name, asset.product_model, asset.internal_asset_name, 
            asset.serial_number, asset.purchase_date, asset.price, asset.currency_symbol, 
            asset.warranty_duration, asset.warranty_expiry_date, asset.location, asset.vendor_company,
            asset.vendor_email, asset.notes, asset.disposal_date, asset.alert_period,
            asset.status, tags
        ])
    
    # Prepare response
    from flask import Response
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=assets.csv"}
    )

@asset.route('/import', methods=['GET', 'POST'])
@login_required
def import_assets():
    if not current_user.has_permission('CREATE'):
        flash('You do not have permission to import assets.', 'danger')
        return redirect(url_for('asset.asset_list'))
    
    if request.method == 'POST':
        if 'csv_file' not in request.files:
            flash('No file selected.', 'danger')
            return redirect(url_for('asset.import_assets'))
        
        file = request.files['csv_file']
        
        if file.filename == '':
            flash('No file selected.', 'danger')
            return redirect(url_for('asset.import_assets'))
        
        if not file.filename.endswith('.csv'):
            flash('File must be a CSV.', 'danger')
            return redirect(url_for('asset.import_assets'))
        
        # Process the CSV file
        import csv
        from io import StringIO
        
        csv_content = file.read().decode('utf-8')
        csv_file = StringIO(csv_content)
        reader = csv.DictReader(csv_file)
        
        imported_count = 0
        error_count = 0
        
        for row in reader:
            try:
                # Create new asset
                new_asset = Asset(
                    product_name=row.get('Product Name', ''),
                    product_model=row.get('Product Model', ''),
                    internal_asset_name=row.get('Internal Asset Name', ''),
                    serial_number=row.get('Serial Number', ''),
                    purchase_date=datetime.strptime(row.get('Purchase Date', ''), '%Y-%m-%d').date(),
                    price=float(row.get('Price', 0)),
                    currency_symbol=row.get('Currency Symbol', '$'),
                    warranty_duration=int(row.get('Warranty Duration (months)', 0)),
                    location=row.get('Location', ''),
                    vendor_company=row.get('Vendor Company', ''),
                    vendor_email=row.get('Vendor Email', ''),
                    notes=row.get('Notes', ''),
                    alert_period=int(row.get('Alert Period (days)', 30))
                )
                
                # Handle disposal date if provided
                if row.get('Disposal Date'):
                    new_asset.disposal_date = datetime.strptime(row.get('Disposal Date'), '%Y-%m-%d').date()
                
                # Handle tags
                if row.get('Tags'):
                    tag_names = [name.strip() for name in row.get('Tags').split(',')]
                    for tag_name in tag_names:
                        # Find or create tag
                        tag = Tag.query.filter_by(name=tag_name).first()
                        if not tag:
                            tag = Tag(name=tag_name)
                            db.session.add(tag)
                            db.session.flush()  # Generate ID without committing
                        new_asset.tags.append(tag)
                
                # For imported assets, only assign groups that the user can assign
                # This ensures group admins can only assign their own groups during import
                assignable_groups = current_user.get_assignable_groups()
                if assignable_groups and not current_user.is_admin:
                    # For non-admin users, assign their first group by default
                    new_asset.assigned_groups = [assignable_groups[0]] if assignable_groups else []
                
                db.session.add(new_asset)
                imported_count += 1
            except Exception as e:
                error_count += 1
                current_app.logger.error(f"Error importing asset: {str(e)}")
        
        db.session.commit()
        
        flash(f'Import completed. {imported_count} assets imported successfully, {error_count} errors.', 'info')
        return redirect(url_for('asset.asset_list'))
    
    return render_template('assets/import.html', title='Import Assets')

@asset.route('/debug/routes')  # or @debug.route('/debug/routes') if using new blueprint
def debug_routes():
    """Debug route to show all registered routes"""
    
    routes_info = []
    for rule in current_app.url_map.iter_rules():
        routes_info.append({
            'endpoint': rule.endpoint,
            'methods': ', '.join(rule.methods),
            'path': str(rule),
            'blueprint': rule.endpoint.split('.')[0] if '.' in rule.endpoint else 'main'
        })
    
    # Sort by blueprint and path
    routes_info.sort(key=lambda x: (x['blueprint'], x['path']))
    
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Registered Routes Debug</title>
        <style>
            body { font-family: monospace; margin: 20px; }
            table { border-collapse: collapse; width: 100%; }
            th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
            th { background-color: #f2f2f2; }
            .notification { background-color: #ffffcc; }
        </style>
    </head>
    <body>
        <h1>Registered Routes</h1>
        <table>
            <thead>
                <tr>
                    <th>Blueprint</th>
                    <th>Endpoint</th>
                    <th>Methods</th>
                    <th>Path</th>
                </tr>
            </thead>
            <tbody>
    """
    
    for route in routes_info:
        row_class = 'notification' if route['blueprint'] == 'notification' else ''
        html += f"""
                <tr class="{row_class}">
                    <td>{route['blueprint']}</td>
                    <td>{route['endpoint']}</td>
                    <td>{route['methods']}</td>
                    <td>{route['path']}</td>
                </tr>
        """
    
    html += """
            </tbody>
        </table>
        
        <h2>Check for Notification Routes</h2>
        <p>Look for routes starting with 'notification.' in the table above.</p>
        <p>If you don't see any notification routes, the blueprint isn't registered.</p>
        
        <h3>Test Links</h3>
        <ul>
            <li><a href="/notification/test">Test notification blueprint</a></li>
            <li><a href="/notification/test-response">Test notification response</a></li>
        </ul>
    </body>
    </html>
    """
    
    return html

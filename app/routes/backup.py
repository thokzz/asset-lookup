# app/routes/backup.py - Database backup management routes

from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, jsonify
from flask_login import login_required, current_user
from app import db
from app.models.setting import Setting
from app.utils.audit import log_activity
import os
import json
import sqlite3
import shutil
import gzip
import datetime
import glob
from pathlib import Path
import threading
import time

backup = Blueprint('backup', __name__)

@backup.before_request
def check_admin():
    """Ensure only admins can access backup functionality"""
    if not current_user.is_authenticated or not current_user.is_admin:
        flash('You do not have permission to access this area.', 'danger')
        return redirect(url_for('asset.dashboard'))

@backup.route('/admin/backup')
@login_required
def backup_settings():
    """Database backup settings and management page"""
    
    # Get current backup settings
    settings = get_backup_settings()
    
    # Get backup statistics
    stats = get_backup_statistics(settings['backup_path'])
    
    # Get recent backup history
    recent_backups = get_recent_backups(settings['backup_path'], limit=10)
    
    return render_template('admin/backup.html',
        title='Database Backup Management',
        settings=settings,
        stats=stats,
        recent_backups=recent_backups
    )

@backup.route('/admin/backup/settings', methods=['POST'])
@login_required
def update_backup_settings():
    """Update backup configuration settings"""
    try:
        # Get form data
        backup_path = request.form.get('backup_path', '/app/backups').strip()
        date_format = request.form.get('date_format', '%Y%m%d_%H%M%S').strip()
        name_format = request.form.get('name_format', 'asset_lookup_backup_{date}').strip()
        rotation_days = int(request.form.get('rotation_days', 30))
        auto_backup_enabled = 'auto_backup_enabled' in request.form
        backup_schedule = request.form.get('backup_schedule', 'daily').strip()
        backup_time = request.form.get('backup_time', '02:00').strip()
        compression_enabled = 'compression_enabled' in request.form
        
        # Validate inputs
        if rotation_days < 1 or rotation_days > 45:
            flash('Rotation days must be between 1 and 45 days.', 'danger')
            return redirect(url_for('backup.backup_settings'))
        
        # Validate date format
        try:
            test_date = datetime.datetime.now().strftime(date_format)
        except ValueError:
            flash('Invalid date format. Please use valid Python strftime format.', 'danger')
            return redirect(url_for('backup.backup_settings'))
        
        # Validate name format
        if '{date}' not in name_format:
            flash('Name format must contain {date} placeholder.', 'danger')
            return redirect(url_for('backup.backup_settings'))
        
        # Create backup directory if it doesn't exist
        try:
            os.makedirs(backup_path, exist_ok=True)
            # Test write permissions
            test_file = os.path.join(backup_path, '.test_write')
            with open(test_file, 'w') as f:
                f.write('test')
            os.remove(test_file)
        except Exception as e:
            flash(f'Cannot write to backup path: {str(e)}', 'danger')
            return redirect(url_for('backup.backup_settings'))
        
        # Save settings
        backup_settings = {
            'backup_path': backup_path,
            'date_format': date_format,
            'name_format': name_format,
            'rotation_days': rotation_days,
            'auto_backup_enabled': auto_backup_enabled,
            'backup_schedule': backup_schedule,
            'backup_time': backup_time,
            'compression_enabled': compression_enabled
        }
        
        save_backup_settings(backup_settings)
        
        # Log the change
        log_activity(
            action="UPDATE",
            resource_type="BackupSettings",
            description=f"Updated backup settings: Path={backup_path}, Rotation={rotation_days}d, Auto={auto_backup_enabled}"
        )
        
        flash('Backup settings updated successfully!', 'success')
        
    except ValueError as e:
        flash(f'Invalid input: {str(e)}', 'danger')
    except Exception as e:
        flash(f'Error updating backup settings: {str(e)}', 'danger')
        current_app.logger.error(f"Error updating backup settings: {str(e)}")
    
    return redirect(url_for('backup.backup_settings'))

@backup.route('/admin/backup/create', methods=['POST'])
@login_required
def create_backup():
    """Create an immediate backup"""
    try:
        settings = get_backup_settings()
        
        # Start backup in background thread with app context
        app = current_app._get_current_object()
        backup_thread = threading.Thread(target=perform_backup_with_context, args=(app, settings))
        backup_thread.daemon = True
        backup_thread.start()
        
        flash('Backup started successfully! Check the backup history for progress.', 'success')
        
        # Log the manual backup trigger
        log_activity(
            action="BACKUP_TRIGGERED",
            resource_type="Database",
            description="Manual database backup triggered by admin"
        )
        
    except Exception as e:
        flash(f'Error starting backup: {str(e)}', 'danger')
        current_app.logger.error(f"Error starting backup: {str(e)}")
    
    return redirect(url_for('backup.backup_settings'))

@backup.route('/admin/backup/restore', methods=['POST'])
@login_required
def restore_backup():
    """Restore database from backup"""
    try:
        backup_filename = request.form.get('backup_filename')
        settings = get_backup_settings()
        backup_file_path = os.path.join(settings['backup_path'], backup_filename)
        
        if not os.path.exists(backup_file_path):
            flash('Backup file not found.', 'danger')
            return redirect(url_for('backup.backup_settings'))
        
        # Create backup of current database before restore
        current_db_path = get_database_path()
        pre_restore_backup = f"{current_db_path}.pre-restore-{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        shutil.copy2(current_db_path, pre_restore_backup)
        
        # Restore from backup
        if backup_filename.endswith('.gz'):
            # Decompress and restore
            with gzip.open(backup_file_path, 'rb') as f_in:
                with open(current_db_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
        else:
            # Direct copy
            shutil.copy2(backup_file_path, current_db_path)
        
        # Verify restored database
        if verify_database_integrity(current_db_path):
            flash(f'Database successfully restored from {backup_filename}', 'success')
            
            # Log the restore
            log_activity(
                action="DATABASE_RESTORED",
                resource_type="Database",
                description=f"Database restored from backup: {backup_filename}"
            )
        else:
            # Restore failed, revert to pre-restore backup
            shutil.copy2(pre_restore_backup, current_db_path)
            flash('Database restore failed - integrity check failed. Original database restored.', 'danger')
            
    except Exception as e:
        flash(f'Error during restore: {str(e)}', 'danger')
        current_app.logger.error(f"Error during restore: {str(e)}")
    
    return redirect(url_for('backup.backup_settings'))

@backup.route('/admin/backup/delete', methods=['POST'])
@login_required
def delete_backup():
    """Delete a specific backup file"""
    try:
        backup_filename = request.form.get('backup_filename')
        settings = get_backup_settings()
        backup_file_path = os.path.join(settings['backup_path'], backup_filename)
        
        if os.path.exists(backup_file_path):
            os.remove(backup_file_path)
            flash(f'Backup {backup_filename} deleted successfully.', 'success')
            
            # Log the deletion
            log_activity(
                action="BACKUP_DELETED",
                resource_type="BackupFile",
                description=f"Backup file deleted: {backup_filename}"
            )
        else:
            flash('Backup file not found.', 'danger')
            
    except Exception as e:
        flash(f'Error deleting backup: {str(e)}', 'danger')
        current_app.logger.error(f"Error deleting backup: {str(e)}")
    
    return redirect(url_for('backup.backup_settings'))

@backup.route('/admin/backup/cleanup', methods=['POST'])
@login_required
def cleanup_backups():
    """Clean up old backups based on rotation settings"""
    try:
        settings = get_backup_settings()
        removed_count = cleanup_old_backups(settings)
        
        flash(f'Cleanup completed. Removed {removed_count} old backup(s).', 'success')
        
        # Log the cleanup
        log_activity(
            action="BACKUP_CLEANUP",
            resource_type="BackupFiles",
            description=f"Manual backup cleanup completed. Removed {removed_count} files."
        )
        
    except Exception as e:
        flash(f'Error during cleanup: {str(e)}', 'danger')
        current_app.logger.error(f"Error during cleanup: {str(e)}")
    
    return redirect(url_for('backup.backup_settings'))

@backup.route('/admin/backup/status')
@login_required
def backup_status():
    """Get backup status (for AJAX polling)"""
    try:
        settings = get_backup_settings()
        stats = get_backup_statistics(settings['backup_path'])
        recent_backups = get_recent_backups(settings['backup_path'], limit=5)
        
        return jsonify({
            'success': True,
            'stats': stats,
            'recent_backups': [
                {
                    'filename': backup['filename'],
                    'size': backup['size_formatted'],
                    'created': backup['created_formatted'],
                    'is_compressed': backup['is_compressed']
                }
                for backup in recent_backups
            ]
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

# Helper functions

def perform_backup_with_context(app, settings):
    """Wrapper function to perform backup with application context"""
    with app.app_context():
        try:
            perform_backup(settings)
        except Exception as e:
            app.logger.error(f"Backup failed in context: {str(e)}")
            import traceback
            app.logger.error(traceback.format_exc())

def get_backup_settings():
    """Get current backup settings from database/config"""
    default_settings = {
        'backup_path': '/app/backups',
        'date_format': '%Y%m%d_%H%M%S',
        'name_format': 'asset_lookup_backup_{date}',
        'rotation_days': 30,
        'auto_backup_enabled': True,
        'backup_schedule': 'daily',
        'backup_time': '02:00',
        'compression_enabled': True
    }
    
    try:
        # Try to get settings from database
        settings_record = Setting.query.filter_by(id='backup_settings').first()
        if settings_record:
            saved_settings = json.loads(settings_record.value)
            default_settings.update(saved_settings)
    except Exception as e:
        current_app.logger.warning(f"Could not load backup settings: {str(e)}")
    
    return default_settings

def save_backup_settings(settings):
    """Save backup settings to database"""
    try:
        settings_record = Setting.query.filter_by(id='backup_settings').first()
        if settings_record:
            settings_record.value = json.dumps(settings)
        else:
            settings_record = Setting(id='backup_settings', value=json.dumps(settings))
            db.session.add(settings_record)
        
        db.session.commit()
        
    except Exception as e:
        db.session.rollback()
        raise e

def get_database_path():
    """Get the path to the current database"""
    try:
        from flask import current_app
        db_url = current_app.config.get('SQLALCHEMY_DATABASE_URI', '')
        if db_url.startswith('sqlite:///'):
            return db_url.replace('sqlite:///', '')
        else:
            # Fallback
            return '/app/instance/asset_lookup.db'
    except RuntimeError:
        # Outside app context, use fallback
        return '/app/instance/asset_lookup.db'

def perform_backup(settings):
    """Perform the actual backup operation"""
    try:
        # Use print for logging when outside app context, current_app.logger when inside
        try:
            from flask import current_app
            logger = current_app.logger
            logger.info("Starting database backup...")
        except RuntimeError:
            # Outside app context, use print
            print("Starting database backup...")
            logger = None
        
        # Get database path
        source_db_path = get_database_path()
        
        if not os.path.exists(source_db_path):
            error_msg = f"Source database not found: {source_db_path}"
            if logger:
                logger.error(error_msg)
            else:
                print(f"ERROR: {error_msg}")
            raise Exception(error_msg)
        
        # Generate backup filename
        timestamp = datetime.datetime.now().strftime(settings['date_format'])
        backup_filename = settings['name_format'].format(date=timestamp) + '.db'
        backup_path = os.path.join(settings['backup_path'], backup_filename)
        
        # Ensure backup directory exists
        os.makedirs(settings['backup_path'], exist_ok=True)
        
        # Perform hot backup using SQLite backup API
        source_conn = sqlite3.connect(source_db_path)
        backup_conn = sqlite3.connect(backup_path)
        source_conn.backup(backup_conn)
        backup_conn.close()
        source_conn.close()
        
        # Verify backup integrity
        if not verify_database_integrity(backup_path):
            os.remove(backup_path)
            error_msg = "Backup integrity verification failed"
            if logger:
                logger.error(error_msg)
            else:
                print(f"ERROR: {error_msg}")
            raise Exception(error_msg)
        
        # Compress if enabled
        if settings['compression_enabled']:
            compressed_path = backup_path + '.gz'
            with open(backup_path, 'rb') as f_in:
                with gzip.open(compressed_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            os.remove(backup_path)
            backup_path = compressed_path
        
        # Create latest backup symlink/copy
        latest_path = os.path.join(settings['backup_path'], 'asset_lookup.db')
        if settings['compression_enabled']:
            # For compressed backups, decompress to create latest
            with gzip.open(backup_path, 'rb') as f_in:
                with open(latest_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
        else:
            shutil.copy2(backup_path, latest_path)
        
        # Clean up old backups
        cleanup_old_backups(settings)
        
        success_msg = f"Backup completed successfully: {os.path.basename(backup_path)}"
        if logger:
            logger.info(success_msg)
        else:
            print(f"SUCCESS: {success_msg}")
        
    except Exception as e:
        error_msg = f"Backup failed: {str(e)}"
        try:
            from flask import current_app
            current_app.logger.error(error_msg)
            import traceback
            current_app.logger.error(traceback.format_exc())
        except RuntimeError:
            # Outside app context
            print(f"ERROR: {error_msg}")
            import traceback
            traceback.print_exc()
        raise e

def verify_database_integrity(db_path):
    """Verify database integrity"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA integrity_check")
        result = cursor.fetchone()
        conn.close()
        
        return result and result[0] == "ok"
        
    except Exception:
        return False

def get_backup_statistics(backup_path):
    """Get backup statistics"""
    try:
        if not os.path.exists(backup_path):
            return {
                'total_backups': 0,
                'total_size': 0,
                'total_size_formatted': '0 B',
                'oldest_backup': None,
                'newest_backup': None
            }
        
        backup_files = []
        total_size = 0
        
        for pattern in ['asset_lookup_backup_*.db', 'asset_lookup_backup_*.db.gz']:
            files = glob.glob(os.path.join(backup_path, pattern))
            for file_path in files:
                stat = os.stat(file_path)
                backup_files.append({
                    'path': file_path,
                    'size': stat.st_size,
                    'mtime': stat.st_mtime
                })
                total_size += stat.st_size
        
        if not backup_files:
            return {
                'total_backups': 0,
                'total_size': 0,
                'total_size_formatted': '0 B',
                'oldest_backup': None,
                'newest_backup': None
            }
        
        backup_files.sort(key=lambda x: x['mtime'])
        
        return {
            'total_backups': len(backup_files),
            'total_size': total_size,
            'total_size_formatted': format_bytes(total_size),
            'oldest_backup': datetime.datetime.fromtimestamp(backup_files[0]['mtime']).strftime('%Y-%m-%d %H:%M:%S'),
            'newest_backup': datetime.datetime.fromtimestamp(backup_files[-1]['mtime']).strftime('%Y-%m-%d %H:%M:%S')
        }
        
    except Exception as e:
        current_app.logger.error(f"Error getting backup statistics: {str(e)}")
        return {
            'total_backups': 0,
            'total_size': 0,
            'total_size_formatted': '0 B',
            'oldest_backup': None,
            'newest_backup': None
        }

def get_recent_backups(backup_path, limit=10):
    """Get list of recent backups"""
    try:
        if not os.path.exists(backup_path):
            return []
        
        backup_files = []
        
        for pattern in ['asset_lookup_backup_*.db', 'asset_lookup_backup_*.db.gz']:
            files = glob.glob(os.path.join(backup_path, pattern))
            for file_path in files:
                stat = os.stat(file_path)
                backup_files.append({
                    'filename': os.path.basename(file_path),
                    'size': stat.st_size,
                    'size_formatted': format_bytes(stat.st_size),
                    'created': datetime.datetime.fromtimestamp(stat.st_mtime),
                    'created_formatted': datetime.datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                    'is_compressed': file_path.endswith('.gz')
                })
        
        # Sort by creation time, newest first
        backup_files.sort(key=lambda x: x['created'], reverse=True)
        
        return backup_files[:limit]
        
    except Exception as e:
        current_app.logger.error(f"Error getting recent backups: {str(e)}")
        return []

def cleanup_old_backups(settings):
    """Clean up old backups based on rotation days"""
    try:
        backup_path = settings['backup_path']
        rotation_days = settings['rotation_days']
        
        if not os.path.exists(backup_path):
            return 0
        
        cutoff_time = time.time() - (rotation_days * 24 * 60 * 60)
        removed_count = 0
        
        for pattern in ['asset_lookup_backup_*.db', 'asset_lookup_backup_*.db.gz']:
            files = glob.glob(os.path.join(backup_path, pattern))
            for file_path in files:
                if os.path.getmtime(file_path) < cutoff_time:
                    os.remove(file_path)
                    removed_count += 1
        
        return removed_count
        
    except Exception as e:
        try:
            from flask import current_app
            current_app.logger.error(f"Error during cleanup: {str(e)}")
        except RuntimeError:
            print(f"ERROR during cleanup: {str(e)}")
        return 0

def format_bytes(bytes_value):
    """Format bytes in human readable format"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_value < 1024.0:
            return f"{bytes_value:.1f} {unit}"
        bytes_value /= 1024.0
    return f"{bytes_value:.1f} TB"
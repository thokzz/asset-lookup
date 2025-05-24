# app/routes/auth.py - Updated with 2FA support
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, session
from flask_login import login_user, logout_user, current_user, login_required
from app import db, bcrypt
from app.models.user import User
from app.utils.email import send_password_reset_email
from app.utils.audit import log_login, log_logout, log_user_change, log_activity
from app.utils.config_service import ConfigService
import jwt
from datetime import datetime, timedelta
import os
import qrcode
import io
import base64

auth = Blueprint('auth', __name__)

@auth.route('/login', methods=['GET', 'POST'])
def login():
    # Add OIDC enabled check to template context
    from app.utils.oidc import oidc_client
    oidc_enabled = oidc_client.is_enabled()
    
    if current_user.is_authenticated:
        return redirect(url_for('asset.dashboard'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        totp_code = request.form.get('totp_code')
        remember = 'remember' in request.form
        
        # Handle 2FA verification for pending user
        if totp_code and 'pending_user_id' in session:
            user_id = session.get('pending_user_id')
            user = User.query.get(user_id)
            
            if user and user.is_active:
                if user.verify_totp(totp_code):
                    # 2FA verification successful
                    login_user(user, remember=remember)
                    log_login(user, success=True, description="Successful login with 2FA")
                    session.pop('pending_user_id', None)
                    
                    next_page = request.args.get('next')
                    if next_page and not next_page.startswith('/'):
                        next_page = None
                        
                    return redirect(next_page or url_for('asset.dashboard'))
                else:
                    # 2FA verification failed - stay in 2FA mode
                    flash('Invalid verification code. Please try again.', 'danger')
                    log_login(user, success=False, description="Invalid 2FA code")
                    return render_template('auth/login.html', 
                                         title='Login', 
                                         show_2fa=True,
                                         username=user.username,
                                         oidc_enabled=oidc_enabled)
            else:
                # User not found or inactive - clear session and restart
                session.pop('pending_user_id', None)
                flash('Session expired. Please login again.', 'warning')
                return redirect(url_for('auth.login'))
        
        # Handle initial login (username/password)
        if not username or not password:
            flash('Both username and password are required.', 'danger')
            return render_template('auth/login.html', 
                                 title='Login',
                                 oidc_enabled=oidc_enabled)
            
        # Skip password verification if this is a 2FA form submission
        if password == 'submitted':
            flash('Invalid login attempt. Please start over.', 'danger')
            return redirect(url_for('auth.login'))
            
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password) and user.is_active:
            # Check if 2FA is required
            if user.requires_2fa_verification():
                # Store user in session for 2FA verification
                session['pending_user_id'] = user.id
                session['pending_username'] = user.username  # Store username for template
                return render_template('auth/login.html', 
                                     title='Login', 
                                     show_2fa=True,
                                     username=user.username,
                                     oidc_enabled=oidc_enabled)
            else:
                # Regular login without 2FA
                login_user(user, remember=remember)
                log_login(user, success=True)
                next_page = request.args.get('next')
                
                # Check if user needs to set up 2FA
                if user.needs_2fa_setup():
                    flash('Two-Factor Authentication is now required. Please set up your authenticator app.', 'info')
                    return redirect(url_for('auth.setup_2fa'))
                
                # Validate next page to prevent open redirect vulnerabilities
                if next_page and not next_page.startswith('/'):
                    next_page = None
                    
                return redirect(next_page or url_for('asset.dashboard'))
        else:
            # Authentication failed
            if not user:
                flash('Username not found. Please check your username or register for an account.', 'danger')
                log_login(None, success=False, username=username, description="User not found")
            elif not user.is_active:
                flash('This account has been deactivated. Please contact an administrator.', 'danger')
                log_login(user, success=False, description="Inactive account")
            else:
                flash('Invalid password. Please try again.', 'danger')
                log_login(user, success=False, description="Invalid password")
            
            # Return to login form with error, preserving username
            return render_template('auth/login.html', 
                                 title='Login',
                                 username=username,
                                 oidc_enabled=oidc_enabled)
            
    # GET request - show login form
    return render_template('auth/login.html', 
                         title='Login',
                         oidc_enabled=oidc_enabled)

@auth.route('/setup-2fa', methods=['GET', 'POST'])
@login_required
def setup_2fa():
    # Check if 2FA is enabled system-wide
    if not ConfigService.is_2fa_enabled():
        flash('Two-Factor Authentication is not enabled on this system.', 'info')
        return redirect(url_for('asset.dashboard'))
    
    # Check if user already has 2FA set up
    if current_user.two_factor_setup_complete:
        flash('Two-Factor Authentication is already set up for your account.', 'info')
        return redirect(url_for('asset.dashboard'))
    
    if request.method == 'POST':
        totp_code = request.form.get('totp_code')
        
        if not totp_code:
            flash('Please enter the verification code from your authenticator app.', 'danger')
            return render_template('auth/setup_2fa.html', title='Set Up 2FA')
        
        # Verify the TOTP code
        if current_user.verify_totp(totp_code):
            # Enable 2FA for the user
            current_user.enable_two_factor()
            db.session.commit()
            
            # Log the 2FA setup
            log_activity(
                action="2FA_SETUP",
                resource_type="User",
                resource_id=current_user.id,
                description=f"User {current_user.username} successfully set up Two-Factor Authentication"
            )
            
            flash('Two-Factor Authentication has been successfully set up for your account!', 'success')
            return redirect(url_for('asset.dashboard'))
        else:
            flash('Invalid verification code. Please check your authenticator app and try again.', 'danger')
    
    # Generate QR code for TOTP setup
    totp_uri = current_user.get_totp_uri()
    
    # Create QR code
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(totp_uri)
    qr.make(fit=True)
    
    # Convert QR code to base64 image for display
    img = qr.make_image(fill_color="black", back_color="white")
    img_buffer = io.BytesIO()
    img.save(img_buffer, format='PNG')
    img_buffer.seek(0)
    img_base64 = base64.b64encode(img_buffer.getvalue()).decode()
    
    return render_template('auth/setup_2fa.html', 
                         title='Set Up 2FA',
                         qr_code=img_base64,
                         secret_key=current_user.totp_secret)

@auth.route('/logout')
def logout():
    if current_user.is_authenticated:
        log_logout(current_user)
    logout_user()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('auth.login'))

@auth.route('/register', methods=['GET', 'POST'])
def register():
    from app.config import Config
    
    if current_user.is_authenticated:
        return redirect(url_for('asset.dashboard'))
        
    # Check if registration is allowed
    if not Config.ALLOW_REGISTRATION:
        flash('Registration is currently disabled by the administrator.', 'warning')
        return redirect(url_for('auth.login'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        # Improved validation with specific error messages
        if not username or not email or not password:
            flash('All fields are required.', 'danger')
            return render_template('auth/register.html', title='Register')
            
        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('auth/register.html', title='Register', 
                                  username=username, email=email)
            
        # Check username and email format
        if len(username) < 3:
            flash('Username must be at least 3 characters.', 'danger')
            return render_template('auth/register.html', title='Register', 
                                  username=username, email=email)
                                  
        if '@' not in email or '.' not in email:
            flash('Please enter a valid email address.', 'danger')
            return render_template('auth/register.html', title='Register', 
                                  username=username, email=email)
            
        existing_user = User.query.filter((User.username == username) | (User.email == email)).first()
        if existing_user:
            if existing_user.username == username:
                flash('Username already exists. Please choose another.', 'danger')
            else:
                flash('Email already exists. Please choose another.', 'danger')
            return render_template('auth/register.html', title='Register',
                                  username=username if existing_user.username != username else "",
                                  email=email if existing_user.email != email else "")
            
        try:
            new_user = User(
                username=username,
                email=email,
                password=password,
                first_name=request.form.get('first_name'),
                last_name=request.form.get('last_name')
            )

            # Make the first user an admin
            if User.query.count() == 0:
                new_user.is_admin = True
                
            db.session.add(new_user)
            db.session.commit()
            
            log_user_change(new_user, "CREATE", 
                        description=f"New user registered: {new_user.username}")

            flash('Account created successfully! You can now log in.', 'success')
            return redirect(url_for('auth.login'))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error creating user: {str(e)}")
            flash('An error occurred during registration. Please try again.', 'danger')
        
    return render_template('auth/register.html', title='Register')

@auth.route('/reset_password_request', methods=['GET', 'POST'])
def reset_password_request():
    if current_user.is_authenticated:
        return redirect(url_for('asset.dashboard'))
        
    if request.method == 'POST':
        email = request.form.get('email')
        
        if not email:
            flash('Email address is required.', 'danger')
            return render_template('auth/reset_password_request.html', title='Reset Password')
            
        user = User.query.filter_by(email=email).first()
        
        # We always show the same message to prevent email enumeration
        if user:
            try:
                send_password_reset_email(user)
                current_app.logger.info(f"Password reset requested for {email}")
            except Exception as e:
                current_app.logger.error(f"Failed to send password reset email: {str(e)}")
                # We don't reveal the error to the user to prevent enumeration
            
        flash('If your email is registered, you will receive instructions to reset your password.', 'info')
        return redirect(url_for('auth.login'))
        
    return render_template('auth/reset_password_request.html', title='Reset Password')

@auth.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('asset.dashboard'))
    
    try:
        from app.config import Config
        # Decode the token
        payload = jwt.decode(token, Config.JWT_SECRET_KEY, algorithms=['HS256'])
        user_id = payload['user_id']
        user = User.query.get(user_id)
        
        if not user:
            flash('Invalid or expired token.', 'danger')
            return redirect(url_for('auth.reset_password_request'))
            
    except jwt.ExpiredSignatureError:
        flash('Your password reset link has expired.', 'danger')
        return redirect(url_for('auth.reset_password_request'))
    except (jwt.InvalidTokenError, KeyError) as e:
        current_app.logger.error(f"Invalid token error: {str(e)}")
        flash('Invalid token.', 'danger')
        return redirect(url_for('auth.reset_password_request'))
        
    if request.method == 'POST':
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if not password or not confirm_password:
            flash('Both fields are required.', 'danger')
            return render_template('auth/reset_password.html', token=token, title='Reset Password')
            
        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('auth/reset_password.html', token=token, title='Reset Password')
        
        try:
            user.set_password(password)
            db.session.commit()
            
            flash('Your password has been updated! You can now log in.', 'success')
            return redirect(url_for('auth.login'))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error resetting password: {str(e)}")
            flash('An error occurred. Please try again.', 'danger')
        
    return render_template('auth/reset_password.html', token=token, title='Reset Password')

@auth.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        try:
            # Determine which form was submitted
            is_password_form = 'current_password' in request.form and request.form.get('current_password')
            is_profile_form = 'email' in request.form
            
            if is_password_form:
                # Handle password change only
                current_password = request.form.get('current_password')
                new_password = request.form.get('new_password')
                confirm_new_password = request.form.get('confirm_new_password')
                
                if not current_password or not new_password or not confirm_new_password:
                    flash('All password fields are required.', 'danger')
                    return redirect(url_for('auth.profile'))
                
                if not current_user.check_password(current_password):
                    flash('Current password is incorrect.', 'danger')
                    return redirect(url_for('auth.profile'))
                    
                if new_password != confirm_new_password:
                    flash('New passwords do not match.', 'danger')
                    return redirect(url_for('auth.profile'))
                
                # Update only the password
                old_password_hash = current_user.password_hash
                current_user.set_password(new_password)
                current_user.updated_at = datetime.utcnow()
                
                db.session.commit()
                
                # Log password change
                log_user_change(current_user, "PASSWORD_CHANGE", 
                            description=f"User {current_user.username} changed password")
                
                flash('Password updated successfully.', 'success')
                return redirect(url_for('auth.profile'))
                
            elif is_profile_form:
                # Handle profile update only
                # Collect old data for audit
                old_data = {
                    'first_name': current_user.first_name,
                    'last_name': current_user.last_name,
                    'email': current_user.email,
                    'currency_symbol': current_user.currency_symbol,
                    'date_format': current_user.date_format
                }
                
                # Validate email is provided
                email = request.form.get('email')
                if not email or not email.strip():
                    flash('Email address is required.', 'danger')
                    return redirect(url_for('auth.profile'))
                
                # Check if email is already taken by another user
                existing_user = User.query.filter(User.email == email, User.id != current_user.id).first()
                if existing_user:
                    flash('Email address is already taken by another user.', 'danger')
                    return redirect(url_for('auth.profile'))
                
                # Handle custom currency
                currency_symbol = request.form.get('currency_symbol')
                if currency_symbol == 'custom':
                    custom_currency = request.form.get('custom_currency')
                    if custom_currency and custom_currency.strip():
                        currency_symbol = custom_currency.strip()
                    else:
                        flash('Custom currency symbol is required when "Custom" is selected.', 'danger')
                        return redirect(url_for('auth.profile'))
                
                # Update profile info
                current_user.first_name = request.form.get('first_name', '').strip() or None
                current_user.last_name = request.form.get('last_name', '').strip() or None
                current_user.email = email.strip()
                current_user.currency_symbol = currency_symbol
                current_user.date_format = request.form.get('date_format', 'YYYY-MM-DD')
                current_user.updated_at = datetime.utcnow()
                
                # Collect new data for audit
                new_data = {
                    'first_name': current_user.first_name,
                    'last_name': current_user.last_name,
                    'email': current_user.email,
                    'currency_symbol': current_user.currency_symbol,
                    'date_format': current_user.date_format
                }
                
                db.session.commit()
                
                # Log changes
                log_user_change(current_user, "UPDATE", old_data, new_data,
                            description=f"User {current_user.username} updated profile")
                
                flash('Profile updated successfully.', 'success')
                return redirect(url_for('auth.profile'))
            else:
                flash('No valid form data received.', 'danger')
                return redirect(url_for('auth.profile'))
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error updating profile: {str(e)}")
            import traceback
            current_app.logger.error(traceback.format_exc())
            flash('An error occurred while updating your profile. Please try again.', 'danger')
    
    # Check if 2FA is enabled for status display
    two_factor_enabled = ConfigService.is_2fa_enabled()
    
    return render_template('auth/profile.html', 
                         title='Profile',
                         two_factor_enabled=two_factor_enabled)

# 2FA Admin Overview Route
@auth.route('/admin/2fa-overview')
@login_required
def two_factor_admin_overview():
    # Check admin access
    if not current_user.is_admin:
        flash('You do not have permission to access this area.', 'danger')
        return redirect(url_for('asset.dashboard'))
    
    # Get 2FA statistics
    total_users = User.query.filter_by(is_active=True).count()
    users_with_2fa = User.query.filter_by(two_factor_setup_complete=True, is_active=True).count()
    users_without_2fa = total_users - users_with_2fa
    
    # Get list of users for detailed view
    users = User.query.filter_by(is_active=True).order_by(User.username).all()
    
    return render_template('auth/2fa_admin_overview.html',
                         title='2FA User Overview',
                         total_users=total_users,
                         users_with_2fa=users_with_2fa,
                         users_without_2fa=users_without_2fa,
                         users=users)
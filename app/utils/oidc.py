# app/utils/oidc.py - OIDC Client Module
import requests
from authlib.integrations.flask_client import OAuth
from flask import current_app, session, url_for, request
from urllib.parse import urlencode
import secrets
import hashlib
import base64
import json

class OIDCClient:
    def __init__(self, app=None):
        self.oauth = OAuth()
        self.client = None
        if app:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize OIDC client with Flask app"""
        self.oauth.init_app(app)
        
        # Get OIDC configuration
        oidc_config = self._get_oidc_config()
        
        if oidc_config and oidc_config.get('enabled'):
            try:
                # Register OIDC client
                self.client = self.oauth.register(
                    name='oidc',
                    client_id=oidc_config['client_id'],
                    client_secret=oidc_config['client_secret'],
                    server_metadata_url=oidc_config.get('discovery_url'),
                    client_kwargs={
                        'scope': 'openid email profile',
                        'token_endpoint_auth_method': 'client_secret_post'
                    }
                )
                app.logger.info("OIDC client initialized successfully")
            except Exception as e:
                app.logger.error(f"Failed to initialize OIDC client: {str(e)}")
                self.client = None
    
    def _get_oidc_config(self):
        """Get OIDC configuration from app config or settings"""
        from app.utils.config_service import ConfigService
        
        return {
            'enabled': ConfigService.get_bool('OIDC_ENABLED', False),
            'client_id': ConfigService.get_setting('OIDC_CLIENT_ID'),
            'client_secret': ConfigService.get_setting('OIDC_CLIENT_SECRET'),
            'discovery_url': ConfigService.get_setting('OIDC_DISCOVERY_URL'),
            'issuer': ConfigService.get_setting('OIDC_ISSUER'),
            'auto_create_users': ConfigService.get_bool('OIDC_AUTO_CREATE_USERS', True),
            'default_role': ConfigService.get_setting('OIDC_DEFAULT_ROLE', 'user'),
            'email_claim': ConfigService.get_setting('OIDC_EMAIL_CLAIM', 'email'),
            'username_claim': ConfigService.get_setting('OIDC_USERNAME_CLAIM', 'preferred_username'),
            'first_name_claim': ConfigService.get_setting('OIDC_FIRST_NAME_CLAIM', 'given_name'),
            'last_name_claim': ConfigService.get_setting('OIDC_LAST_NAME_CLAIM', 'family_name'),
            'groups_claim': ConfigService.get_setting('OIDC_GROUPS_CLAIM', 'groups'),
            'role_mapping': self._parse_role_mapping(ConfigService.get_setting('OIDC_ROLE_MAPPING', '{}')),
        }
    
    def _parse_role_mapping(self, mapping_str):
        """Parse role mapping from JSON string"""
        try:
            return json.loads(mapping_str) if mapping_str else {}
        except:
            return {}
    
    def is_enabled(self):
        """Check if OIDC is enabled and properly configured"""
        return self.client is not None
    
    def generate_auth_url(self, redirect_uri=None):
        """Generate authorization URL for OIDC login"""
        if not self.is_enabled():
            return None
        
        if not redirect_uri:
            redirect_uri = url_for('auth.oidc_callback', _external=True)
        
        # Generate state and nonce for security
        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        
        # Store in session for verification
        session['oidc_state'] = state
        session['oidc_nonce'] = nonce
        
        return self.client.authorize_redirect(
            redirect_uri=redirect_uri,
            state=state,
            nonce=nonce
        )
    
    def handle_callback(self, code, state):
        """Handle OIDC callback and extract user info"""
        if not self.is_enabled():
            raise Exception("OIDC not enabled")
        
        # Verify state parameter
        if state != session.get('oidc_state'):
            raise Exception("Invalid state parameter")
        
        # Exchange code for token
        token = self.client.authorize_access_token()
        
        # Verify nonce in ID token
        id_token = token.get('id_token')
        if id_token:
            nonce = session.get('oidc_nonce')
            if not self._verify_nonce(id_token, nonce):
                raise Exception("Invalid nonce in ID token")
        
        # Get user info
        user_info = self.client.parse_id_token(token)
        
        # Clear session state
        session.pop('oidc_state', None)
        session.pop('oidc_nonce', None)
        
        return user_info
    
    def _verify_nonce(self, id_token, expected_nonce):
        """Verify nonce in ID token (simplified)"""
        try:
            import jwt
            # In production, you should properly verify the JWT signature
            decoded = jwt.decode(id_token, options={"verify_signature": False})
            return decoded.get('nonce') == expected_nonce
        except:
            return False
    
    def extract_user_data(self, user_info):
        """Extract user data from OIDC user info"""
        config = self._get_oidc_config()
        
        return {
            'email': user_info.get(config['email_claim'], ''),
            'username': user_info.get(config['username_claim'], ''),
            'first_name': user_info.get(config['first_name_claim'], ''),
            'last_name': user_info.get(config['last_name_claim'], ''),
            'groups': user_info.get(config['groups_claim'], []),
            'raw_user_info': user_info
        }
    
    def determine_user_role(self, user_data):
        """Determine user role based on OIDC groups and role mapping"""
        config = self._get_oidc_config()
        role_mapping = config.get('role_mapping', {})
        user_groups = user_data.get('groups', [])
        
        # Check role mapping
        for group in user_groups:
            if group in role_mapping:
                role = role_mapping[group]
                return {
                    'is_admin': role == 'admin',
                    'is_group_admin': role == 'group_admin',
                    'role': role
                }
        
        # Default role
        default_role = config.get('default_role', 'user')
        return {
            'is_admin': default_role == 'admin',
            'is_group_admin': default_role == 'group_admin',
            'role': default_role
        }

# Initialize OIDC client
oidc_client = OIDCClient()

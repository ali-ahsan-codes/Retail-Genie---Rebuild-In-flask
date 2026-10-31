from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash
from models import User, ApiKey, ServerConfig
from utils import hash_api_key, generate_api_key
from datetime import datetime
import secrets
import uuid

auth_bp = Blueprint('auth', __name__)

# ---------- Login ----------
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Login page and authentication handler."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    
    if request.method == 'POST':
        # Check if it's a JSON request (API login) or form request (web login)
        if request.is_json:
            data = request.get_json()
            username = data.get('username')
            password = data.get('password')
            device_uuid = data.get('device_uuid')  # Optional, for mobile devices
        else:
            username = request.form.get('username')
            password = request.form.get('password')
            device_uuid = request.form.get('device_uuid')
        
        if not username or not password:
            if request.is_json:
                return jsonify({'error': 'Username and password required'}), 400
            flash('Username and password required')
            return render_template('login.html')
        
        user = User.query.filter_by(username=username).first()
        if not user:
            if request.is_json:
                return jsonify({'error': 'Invalid credentials'}), 401
            flash('Invalid username or password')
            return render_template('login.html')
        
        if not check_password_hash(user.password_hash, password):
            if request.is_json:
                return jsonify({'error': 'Invalid credentials'}), 401
            flash('Invalid username or password')
            return render_template('login.html')
        
        if not user.is_active:
            if request.is_json:
                return jsonify({'error': 'Account is inactive'}), 403
            flash('Account is inactive')
            return render_template('login.html')
        
        # Check if user role is allowed
        if user.role not in ['admin', 'sales', 'subadmin', 'captain', 'storekeeper', 'van', 'finance', 'cashier']:
            if request.is_json:
                return jsonify({'error': 'Access forbidden'}), 403
            flash('Access forbidden')
            return render_template('login.html')
        
        # Login user
        login_user(user)
        session['user_id'] = user.id
        session['role'] = user.role
        session['city_id'] = user.city_id
        
        # If device_uuid provided, update or create API key for this device
        # Note: This is for backward compatibility; the recommended way is via admin API.
        if device_uuid:
            # Check if this device already has an active key
            existing_key = ApiKey.query.filter_by(
                device_uuid=device_uuid,
                user_id=user.id,
                status='ACTIVE'
            ).first()
            
            if not existing_key:
                # Generate a new API key for this device
                raw_key = secrets.token_hex(32)
                key_hash = hash_api_key(raw_key)
                
                # Get expiry from config or default to 365 days
                try:
                    expiry_days = int(ServerConfig.get('DEFAULT_EXPIRY_DAYS', '365'))
                except:
                    expiry_days = 365
                
                api_key = ApiKey(
                    device_uuid=device_uuid,
                    api_key_hash=key_hash,
                    user_id=user.id,
                    status='ACTIVE',
                    expires_at=datetime.utcnow().replace(year=datetime.utcnow().year + 1) if expiry_days else None
                )
                db.session.add(api_key)
                db.session.commit()
                
                # Store the raw key in session for one-time display
                session['new_api_key'] = raw_key
        
        # Redirect to dashboard or return JSON response
        if request.is_json:
            # Get token configuration for mobile app
            max_token_cap = int(ServerConfig.get('MAX_TOKEN_CAP', '15'))
            token_renewal_threshold = int(ServerConfig.get('TOKEN_RENEWAL_THRESHOLD', '2'))
            default_expiry_days = int(ServerConfig.get('DEFAULT_EXPIRY_DAYS', '7'))
            
            return jsonify({
                'status': 'success',
                'user_id': user.id,
                'username': user.username,
                'role': user.role,
                'city_id': user.city_id,
                'city_name': user.city.name if user.city else None,
                'redirect': url_for('dashboard.index'),
                'token_config': {
                    'max_token_cap': max_token_cap,
                    'token_renewal_threshold': token_renewal_threshold,
                    'default_expiry_days': default_expiry_days
                }
            })
        
        # Store city ID in session for quick access
        session['city_id'] = user.city_id
        return redirect(url_for('dashboard.index'))
    
    # GET request - render login page
    # Clear any stale flash messages
    session.pop('_flashes', None)
    return render_template('login.html')

# ---------- Logout ----------
@auth_bp.route('/logout')
@login_required
def logout():
    """Logout user and clear session."""
    # Logout user
    logout_user()
    # Clear session
    session.clear()
    # Flash a message
    flash('You have been logged out successfully.')
    return redirect(url_for('auth.login'))

# ---------- API Key Status Check (for mobile) ----------
@auth_bp.route('/api-key/status', methods=['GET'])
@login_required
def api_key_status():
    """Check if the current user has an active API key for their device."""
    device_uuid = request.args.get('device_uuid')
    
    if not device_uuid:
        return jsonify({'error': 'device_uuid required'}), 400
    
    api_key = ApiKey.query.filter_by(
        device_uuid=device_uuid,
        user_id=current_user.id,
        status='ACTIVE'
    ).first()
    
    if api_key:
        # Check if expired
        if api_key.expires_at and api_key.expires_at < datetime.utcnow():
            api_key.status = 'EXPIRED'
            db.session.commit()
            return jsonify({'active': False, 'status': 'EXPIRED', 'message': 'API key has expired'})
        
        return jsonify({
            'active': True,
            'api_key_id': api_key.id,
            'status': api_key.status,
            'created_at': api_key.created_at.isoformat(),
            'last_used_at': api_key.last_used_at.isoformat() if api_key.last_used_at else None,
            'expires_at': api_key.expires_at.isoformat() if api_key.expires_at else None
        })
    else:
        return jsonify({'active': False, 'status': 'NOT_FOUND', 'message': 'No active API key for this device'})

# ---------- Generate New API Key (for mobile) ----------
@auth_bp.route('/api-key/generate', methods=['POST'])
@login_required
def generate_api_key_mobile():
    """Generate a new API key for the current user and device."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'JSON body required'}), 400
    
    device_uuid = data.get('device_uuid')
    if not device_uuid:
        return jsonify({'error': 'device_uuid required'}), 400
    
    # Check if user already has an active key for this device
    existing = ApiKey.query.filter_by(
        device_uuid=device_uuid,
        user_id=current_user.id,
        status='ACTIVE'
    ).first()
    
    if existing:
        # Revoke the existing key
        existing.status = 'REVOKED'
        db.session.commit()
    
    # Generate new key
    raw_key = secrets.token_hex(32)
    key_hash = hash_api_key(raw_key)
    
    # Get expiry from config or default to 365 days
    try:
        expiry_days = int(ServerConfig.get('DEFAULT_EXPIRY_DAYS', '365'))
    except:
        expiry_days = 365
    
    api_key = ApiKey(
        device_uuid=device_uuid,
        api_key_hash=key_hash,
        user_id=current_user.id,
        status='ACTIVE',
        expires_at=datetime.utcnow().replace(year=datetime.utcnow().year + 1) if expiry_days else None
    )
    db.session.add(api_key)
    db.session.commit()
    
    return jsonify({
        'status': 'success',
        'api_key_id': api_key.id,
        'api_key': raw_key,
        'expires_at': api_key.expires_at.isoformat() if api_key.expires_at else None,
        'message': 'API key generated successfully. This is the only time the raw key is shown.'
    })

# ---------- Revoke API Key (for mobile) ----------
@auth_bp.route('/api-key/revoke', methods=['POST'])
@login_required
def revoke_api_key_mobile():
    """Revoke an API key for the current user's device."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'JSON body required'}), 400
    
    device_uuid = data.get('device_uuid')
    if not device_uuid:
        return jsonify({'error': 'device_uuid required'}), 400
    
    api_key = ApiKey.query.filter_by(
        device_uuid=device_uuid,
        user_id=current_user.id,
        status='ACTIVE'
    ).first()
    
    if not api_key:
        return jsonify({'error': 'No active API key found for this device'}), 404
    
    api_key.status = 'REVOKED'
    db.session.commit()
    
    return jsonify({
        'status': 'success',
        'message': 'API key revoked successfully'
    })

# ---------- Session check ----------
@auth_bp.route('/session-check', methods=['GET'])
@login_required
def session_check():
    """Check if the user is authenticated and return their role."""
    return jsonify({
        'authenticated': True,
        'user_id': current_user.id,
        'username': current_user.username,
        'role': current_user.role,
        'city_id': current_user.city_id,
        'city_name': current_user.city.name if current_user.city else None
    })

# ---------- User info (for API) ----------
@auth_bp.route('/api/user/me', methods=['GET'])
@login_required
def user_info():
    """Get current user information for API clients."""
    return jsonify({
        'id': current_user.id,
        'username': current_user.username,
        'role': current_user.role,
        'city_id': current_user.city_id,
        'city_name': current_user.city.name if current_user.city else None,
        'is_active': current_user.is_active,
        'created_at': current_user.created_at.isoformat(),
        'show_stock_quantity': current_user.show_stock_quantity if hasattr(current_user, 'show_stock_quantity') else True
    })

# ---------- Update user preferences ----------
@auth_bp.route('/api/user/preferences', methods=['PUT'])
@login_required
def update_user_preferences():
    """Update user preferences like stock visibility toggle."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'JSON body required'}), 400
    
    # Update show_stock_quantity preference
    if 'show_stock_quantity' in data:
        current_user.show_stock_quantity = data['show_stock_quantity']
        db.session.commit()
        return jsonify({'status': 'success', 'message': 'Preference updated'})
    
    return jsonify({'error': 'No valid preferences provided'}), 400
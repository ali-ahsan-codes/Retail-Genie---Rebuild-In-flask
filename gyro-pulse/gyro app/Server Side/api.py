from flask import Blueprint, request, jsonify, current_app
from flask_login import current_user
from models import db, User, Message, UserSyncStatus, Product, Customer, Order, OrderItem, OrderMedia, RoleApiKey, Setting, Delivery, DeliveryItem, Payment, CashSettlement, SettlementItem, StockTransfer, StockTransferItem, FinanceTransaction, ActivityLog, Notification, DeliveryProof, Return, AgentInventory, PriceList, PriceListItem, CustomerPriceList, Warehouse, Inventory, City, InventoryTransaction, ApiKey, TokenPool, ServerConfig, Media, MediaUploadStatus, DeviceCommand
from utils import (
    save_uploaded_file, save_multiple_files,
    generate_api_key, hash_api_key, derive_session_id, generate_cipher_token,
    encrypt_gpc_payload, decrypt_gpc_payload, parse_gpc_file, import_gpc_export,
    pack_catalog, auto_refill_tokens, enqueue_delete_media_command,
    get_pending_commands, mark_command_sent, mark_command_acknowledged,
    get_master_secret, serve_gpc_file, hash_file_content
)
from werkzeug.security import check_password_hash
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from flask_socketio import emit
from sqlalchemy import or_, func, and_
from sqlalchemy.orm import joinedload, selectinload
import traceback
import json
import base64
import os
import uuid
import qrcode
import secrets
import random
from io import BytesIO
import re

api_bp = Blueprint('api', __name__, url_prefix='/api')

# ---------- Utility Functions ----------
def safe_float(value):
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None

def safe_decimal(val, default='0'):
    if val is None or val == '' or str(val).strip().lower() == 'null':
        return Decimal(str(default))
    try:
        return Decimal(str(val))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(str(default))

def get_absolute_media_url(relative_url):
    if not relative_url:
        return None
    if relative_url.startswith(('http://', 'https://')):
        return relative_url
    if not relative_url.startswith('/'):
        relative_url = '/' + relative_url
    base_url = current_app.config.get('BASE_URL', 'http://localhost:5000')
    return base_url + relative_url

def create_notification(user_id, title, body, data=None):
    notification = Notification(
        user_id=user_id,
        title=title,
        body=body,
        data=json.dumps(data) if data else None
    )
    db.session.add(notification)
    db.session.commit()

def log_activity(user_id, action, table_name=None, record_id=None, old_value=None, new_value=None, order_id=None):
    log = ActivityLog(
        user_id=user_id,
        action=action,
        table_name=table_name,
        record_id=record_id,
        old_value=json.dumps(old_value) if old_value and not isinstance(old_value, str) else str(old_value) if old_value else None,
        new_value=json.dumps(new_value) if new_value and not isinstance(new_value, str) else str(new_value) if new_value else None,
        order_id=order_id,
        timestamp=datetime.utcnow()
    )
    db.session.add(log)
    db.session.commit()

def is_city_active(city_id):
    if not city_id:
        return False
    city = City.query.get(city_id)
    return city is not None and city.is_active

def parse_iso_date(date_str):
    if not date_str:
        return None
    date_str = date_str.replace('Z', '+00:00')
    try:
        return datetime.fromisoformat(date_str)
    except ValueError:
        pattern = r'(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?'
        match = re.match(pattern, date_str)
        if match:
            date_part, time_part = match.groups()
            try:
                return datetime.strptime(f"{date_part} {time_part}", "%Y-%m-%d %H:%M:%S")
            except ValueError:
                pass
        return None

# ---------- API Key & User Validation ----------
@api_bp.before_request
def check_api_key():
    if request.endpoint == 'api.login':
        return

    if current_user.is_authenticated:
        if current_user.is_active and current_user.role in ['admin', 'subadmin', 'captain', 'storekeeper', 'sales', 'van']:
            request.user = current_user
            return
        return jsonify({'error': 'Access forbidden'}), 403

    api_key = request.headers.get('X-API-Key')
    if not api_key:
        return jsonify({'error': 'Missing API key'}), 401

    key_hash = hash_api_key(api_key)
    api_key_record = ApiKey.query.filter_by(api_key_hash=key_hash, status='ACTIVE').first()
    if api_key_record:
        user = User.query.get(api_key_record.user_id)
        if user and user.is_active:
            api_key_record.last_used_at = datetime.utcnow()
            db.session.commit()
            request.user = user
            return

    role_key = RoleApiKey.query.filter_by(api_key=api_key).first()
    if not role_key:
        return jsonify({'error': 'Invalid API key'}), 401

    if request.method == 'GET':
        user_id = request.args.get('user_id')
    else:
        if request.is_json:
            data = request.get_json()
            user_id = data.get('user_id') if data else None
        else:
            user_id = request.form.get('user_id')

    if not user_id:
        return jsonify({'error': 'user_id required for sales API'}), 400

    user = User.query.filter_by(id=user_id, is_active=True).first()
    if not user:
        return jsonify({'error': 'Invalid user'}), 401

    if user.role != role_key.role:
        return jsonify({'error': f'API key is for {role_key.role} role, but user is {user.role}'}), 401

    request.user = user

# ---------- STUB ENDPOINTS (for Android 404s) ----------
@api_bp.route('/messages/inbox', methods=['GET'])
def inbox_stub():
    return jsonify({'messages': []})

@api_bp.route('/sync/status', methods=['GET'])
def sync_status_stub():
    return jsonify({'upload_required': False})

@api_bp.route('/messages/poll', methods=['GET'])
def poll_stub():
    return jsonify({'messages': []})

@api_bp.route('/responses', methods=['GET'])
def responses_stub():
    return jsonify({'data': []})

@api_bp.route('/customers/search', methods=['GET'])
def customers_search_stub():
    # Real customer search should be implemented, but we keep stub for now
    return jsonify({'customers': []})

# ---------- REAL CUSTOMER CREATION (NEW) ----------
@api_bp.route('/customers', methods=['POST'])
def create_customer_endpoint():
    """Create a new customer. Used by Android when manual entry is used."""
    user = request.user
    if user.role not in ['sales', 'admin', 'subadmin']:
        return jsonify({'error': 'Forbidden'}), 403

    data = request.get_json()
    if not data:
        return jsonify({'error': 'JSON body required'}), 400

    name = data.get('name')
    phone = data.get('phone')
    shipping_address = data.get('shipping_address')
    billing_address = data.get('billing_address')

    if not name or not phone:
        return jsonify({'error': 'name and phone are required'}), 400

    # Check if customer already exists by phone
    existing = Customer.query.filter_by(phone=phone).first()
    if existing:
        # Return existing customer (avoid duplication)
        return jsonify({
            'status': 'success',
            'customer': {
                'id': existing.id,
                'name': existing.name,
                'phone': existing.phone,
                'shipping_address': existing.shipping_address,
                'billing_address': existing.billing_address,
                'outstanding_balance': float(existing.outstanding_balance)
            }
        }), 200

    customer = Customer(
        name=name,
        phone=phone,
        shipping_address=shipping_address,
        billing_address=billing_address,
        city_id=user.city_id,
        is_active=True
    )
    db.session.add(customer)
    db.session.commit()

    log_activity(user.id, 'create_customer', 'customers', customer.id, None, {'name': name, 'phone': phone})

    return jsonify({
        'status': 'success',
        'customer': {
            'id': customer.id,
            'name': customer.name,
            'phone': customer.phone,
            'shipping_address': customer.shipping_address,
            'billing_address': customer.billing_address,
            'outstanding_balance': float(customer.outstanding_balance)
        }
    }), 201

# ---------- LOGIN ----------
@api_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'JSON body required'}), 400
    username = data.get('username')
    password = data.get('password')
    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400
    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({'error': 'Invalid credentials'}), 401
    if not check_password_hash(user.password_hash, password):
        return jsonify({'error': 'Invalid credentials'}), 401
    if not user.is_active:
        return jsonify({'error': 'Account is inactive'}), 403
    if user.role not in ['admin', 'sales', 'subadmin', 'captain', 'storekeeper', 'van']:
        return jsonify({'error': 'Access forbidden'}), 403

    role_key = RoleApiKey.query.filter_by(role=user.role).first()
    if not role_key:
        new_key = uuid.uuid4().hex
        role_key = RoleApiKey(role=user.role, api_key=new_key)
        db.session.add(role_key)
        db.session.commit()

    return jsonify({
        'user_id': user.id,
        'api_key': role_key.api_key,
        'username': user.username,
        'role': user.role,
        'city_id': user.city_id
    })

# ---------- System Settings ----------
@api_bp.route('/settings', methods=['GET'])
def get_settings():
    user = request.user
    return jsonify({
        'currency': Setting.get('currency', '$'),
        'tax_rate': float(Setting.get('tax_rate', '0.00')),
        'tax_label': Setting.get('tax_label', 'Tax'),
        'auto_approve_enabled': Setting.get('auto_approve_enabled', 'true') == 'true',
        'auto_approve_threshold': int(Setting.get('auto_approve_threshold', '10')),
        'auto_approve_time_window': int(Setting.get('auto_approve_time_window', '1')),
        'auto_approve_max_total': int(Setting.get('auto_approve_max_total', '20')),
    })

# =============================================================================
# NEW ENDPOINTS FOR OFFLINE-FIRST SECURITY & TOKEN MANAGEMENT
# =============================================================================

@api_bp.route('/admin/api-keys', methods=['POST'])
def generate_api_key_device():
    user = request.user
    if user.role not in ['admin', 'subadmin']:
        return jsonify({'error': 'Forbidden'}), 403

    data = request.get_json()
    if not data:
        return jsonify({'error': 'JSON body required'}), 400

    user_id = data.get('user_id')
    device_uuid = data.get('device_uuid')
    expires_in_days = data.get('expires_in_days', 365)

    if not user_id or not device_uuid:
        return jsonify({'error': 'user_id and device_uuid required'}), 400

    target_user = User.query.get(user_id)
    if not target_user:
        return jsonify({'error': 'User not found'}), 404

    existing = ApiKey.query.filter_by(device_uuid=device_uuid, status='ACTIVE').first()
    if existing:
        return jsonify({'error': 'Device already has an active API key'}), 400

    raw_key = secrets.token_hex(32)
    key_hash = hash_api_key(raw_key)

    expiry = datetime.utcnow() + timedelta(days=expires_in_days) if expires_in_days else None

    api_key = ApiKey(
        device_uuid=device_uuid,
        api_key_hash=key_hash,
        user_id=target_user.id,
        status='ACTIVE',
        expires_at=expiry
    )
    db.session.add(api_key)
    db.session.commit()

    log_activity(user.id, 'generate_api_key', 'api_keys', api_key.id, None, {'user_id': target_user.id, 'device_uuid': device_uuid})

    return jsonify({
        'status': 'success',
        'api_key_id': api_key.id,
        'api_key': raw_key,
        'message': 'API key generated. This is the only time the raw key is shown.'
    })

@api_bp.route('/admin/api-keys/<int:key_id>/revoke', methods=['PUT'])
def revoke_api_key(key_id):
    user = request.user
    if user.role not in ['admin', 'subadmin']:
        return jsonify({'error': 'Forbidden'}), 403

    api_key = ApiKey.query.get(key_id)
    if not api_key:
        return jsonify({'error': 'API key not found'}), 404

    if api_key.status != 'ACTIVE':
        return jsonify({'error': 'Key already revoked or expired'}), 400

    api_key.status = 'REVOKED'
    db.session.commit()

    log_activity(user.id, 'revoke_api_key', 'api_keys', key_id, {'status': 'ACTIVE'}, {'status': 'REVOKED'})

    return jsonify({'status': 'success', 'message': 'API key revoked'})

@api_bp.route('/admin/api-keys', methods=['GET'])
def list_api_keys():
    user = request.user
    if user.role not in ['admin', 'subadmin']:
        return jsonify({'error': 'Forbidden'}), 403

    keys = ApiKey.query.options(joinedload(ApiKey.user)).all()
    result = []
    for k in keys:
        result.append({
            'id': k.id,
            'uuid': k.uuid,
            'device_uuid': k.device_uuid,
            'user_id': k.user_id,
            'username': k.user.username if k.user else None,
            'status': k.status,
            'created_at': k.created_at.isoformat(),
            'last_used_at': k.last_used_at.isoformat() if k.last_used_at else None,
            'expires_at': k.expires_at.isoformat() if k.expires_at else None
        })
    return jsonify({'api_keys': result})

@api_bp.route('/admin/tokens/<int:user_id>', methods=['GET'])
def get_user_tokens(user_id):
    user = request.user
    if user.role not in ['admin', 'subadmin']:
        return jsonify({'error': 'Forbidden'}), 403

    tokens = TokenPool.query.filter_by(user_id=user_id).order_by(TokenPool.created_at.desc()).all()
    result = []
    for t in tokens:
        result.append({
            'id': t.id,
            'uuid': t.uuid,
            'session_id': t.session_id,
            'cipher_token': t.cipher_token[:8] + '...' + t.cipher_token[-4:],
            'token_status': t.token_status,
            'expiry_timestamp': t.expiry_timestamp.isoformat(),
            'created_at': t.created_at.isoformat(),
            'used_at': t.used_at.isoformat() if t.used_at else None
        })
    total = len(result)
    unused = TokenPool.query.filter_by(user_id=user_id, token_status='UNUSED').count()
    used = TokenPool.query.filter_by(user_id=user_id, token_status='USED').count()
    expired = TokenPool.query.filter_by(user_id=user_id, token_status='EXPIRED').count()
    return jsonify({
        'tokens': result,
        'stats': {'total': total, 'unused': unused, 'used': used, 'expired': expired}
    })

@api_bp.route('/admin/gpc/generate', methods=['POST'])
def generate_gpc():
    user = request.user
    if user.role not in ['admin', 'subadmin']:
        return jsonify({'error': 'Forbidden'}), 403

    data = request.get_json()
    if not data:
        return jsonify({'error': 'JSON body required'}), 400

    user_id = data.get('user_id')
    expiry_days = data.get('expiry_days', 7)
    show_stock = data.get('show_stock_quantity', True)

    if not user_id:
        return jsonify({'error': 'user_id required'}), 400

    target_user = User.query.get(user_id)
    if not target_user:
        return jsonify({'error': 'User not found'}), 404

    max_cap = int(ServerConfig.get('MAX_TOKEN_CAP', '15'))

    try:
        encrypted_bytes, filename = generate_gpc_file(
            user_id=user_id,
            expiry_days=expiry_days,
            show_stock=show_stock,
            max_token_cap=max_cap
        )
        log_activity(user.id, 'generate_gpc', 'users', user_id, None, {'expiry_days': expiry_days, 'show_stock': show_stock})
        return serve_gpc_file(encrypted_bytes, filename)
    except Exception as e:
        current_app.logger.error(f"GPC generation error: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/admin/gpc/upload', methods=['POST'])
def upload_gpc():
    user = request.user
    if user.role not in ['admin', 'subadmin']:
        return jsonify({'error': 'Forbidden'}), 403

    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Empty filename'}), 400

    if not file.filename.endswith('.gpc'):
        return jsonify({'error': 'File must have .gpc extension'}), 400

    try:
        file_content = file.read()
        summary = import_gpc_export(file_content)
        log_activity(
            user_id=user.id,
            action='import_gpc',
            table_name='users',
            record_id=None,
            old_value=None,
            new_value=json.dumps({'filename': file.filename, 'summary': summary}),
            order_id=None
        )
        return jsonify({
            'status': 'success',
            'message': 'GPC file uploaded and processed successfully'
        })
    except Exception as e:
        current_app.logger.error(f"GPC import error: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/admin/settings/token-config', methods=['GET', 'PUT'])
def token_config():
    user = request.user
    if user.role not in ['admin', 'subadmin']:
        return jsonify({'error': 'Forbidden'}), 403

    if request.method == 'GET':
        return jsonify({
            'max_token_cap': int(ServerConfig.get('MAX_TOKEN_CAP', '15')),
            'token_renewal_threshold': int(ServerConfig.get('TOKEN_RENEWAL_THRESHOLD', '2')),
            'default_expiry_days': int(ServerConfig.get('DEFAULT_EXPIRY_DAYS', '7'))
        })

    data = request.get_json()
    if not data:
        return jsonify({'error': 'JSON body required'}), 400

    if 'max_token_cap' in data:
        ServerConfig.set('MAX_TOKEN_CAP', str(data['max_token_cap']))
    if 'token_renewal_threshold' in data:
        ServerConfig.set('TOKEN_RENEWAL_THRESHOLD', str(data['token_renewal_threshold']))
    if 'default_expiry_days' in data:
        ServerConfig.set('DEFAULT_EXPIRY_DAYS', str(data['default_expiry_days']))

    log_activity(user.id, 'update_token_config', 'server_config', None, None, data)
    return jsonify({'status': 'success', 'message': 'Token configuration updated'})

@api_bp.route('/media/upload', methods=['POST'])
def upload_media():
    user = request.user
    if user.role not in ['sales', 'van', 'captain', 'admin']:
        return jsonify({'error': 'Forbidden'}), 403

    files = request.files.getlist('files')
    if not files:
        return jsonify({'error': 'No files uploaded'}), 400

    order_id = request.form.get('order_id')
    product_id = request.form.get('product_id')

    uploaded = []
    for file in files:
        saved_url = save_uploaded_file(file, subfolder='media')
        if not saved_url:
            continue
        file.seek(0)
        content = file.read()
        file_hash = hash_file_content(content)
        file_size = len(content)

        ext = file.filename.split('.')[-1].lower() if '.' in file.filename else ''
        mime_map = {
            'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'png': 'image/png',
            'gif': 'image/gif', 'webp': 'image/webp',
            'mp4': 'video/mp4', 'mov': 'video/quicktime', 'webm': 'video/webm',
            'mp3': 'audio/mpeg', 'wav': 'audio/wav', 'aac': 'audio/aac'
        }
        mime_type = mime_map.get(ext, 'application/octet-stream')

        media = Media(
            user_id=user.id,
            order_id=int(order_id) if order_id else None,
            product_id=int(product_id) if product_id else None,
            file_name=file.filename,
            file_path=saved_url,
            file_size=file_size,
            file_hash=file_hash,
            mime_type=mime_type,
            upload_status='UPLOADED',
            uploaded_at=datetime.utcnow()
        )
        db.session.add(media)
        uploaded.append({
            'id': media.id,
            'uuid': media.uuid,
            'file_name': media.file_name,
            'url': saved_url
        })

    db.session.commit()
    log_activity(user.id, 'upload_media', 'media', None, None, {'count': len(uploaded)})
    return jsonify({'status': 'success', 'uploaded': uploaded})

@api_bp.route('/media/status', methods=['POST'])
def media_status_update():
    user = request.user
    if user.role not in ['sales', 'van', 'captain', 'admin']:
        return jsonify({'error': 'Forbidden'}), 403

    data = request.get_json()
    if not data or not isinstance(data.get('media_uuids'), list):
        return jsonify({'error': 'media_uuids list required'}), 400

    uuids = data['media_uuids']
    media_records = Media.query.filter(Media.uuid.in_(uuids), Media.user_id == user.id).all()
    for m in media_records:
        m.upload_status = 'UPLOADED'
        m.deleted_from_device = False
    db.session.commit()

    return jsonify({'status': 'success', 'updated': len(media_records)})

@api_bp.route('/device/commands/pending', methods=['GET'])
def get_pending_commands():
    user = request.user
    if user.role not in ['sales', 'van', 'captain']:
        return jsonify({'error': 'Forbidden'}), 403

    commands = get_pending_commands(user.id)
    for cmd in commands:
        mark_command_sent(cmd['id'])
    return jsonify({'commands': commands})

@api_bp.route('/device/commands/acknowledge', methods=['POST'])
def acknowledge_commands():
    user = request.user
    if user.role not in ['sales', 'van', 'captain']:
        return jsonify({'error': 'Forbidden'}), 403

    data = request.get_json()
    if not data or not isinstance(data.get('command_ids'), list):
        return jsonify({'error': 'command_ids list required'}), 400

    for cmd_id in data['command_ids']:
        mark_command_acknowledged(cmd_id)

    return jsonify({'status': 'success'})

# =============================================================================
# MOBILE SYNC
# =============================================================================
@api_bp.route('/mobile/sync', methods=['GET'])
def mobile_sync():
    user = request.user
    last_sync = request.args.get('last_sync')
    if last_sync:
        try:
            last_sync_dt = parse_iso_date(last_sync)
        except:
            last_sync_dt = None
    else:
        last_sync_dt = None

    is_lan = False
    if request.remote_addr:
        if request.remote_addr.startswith('192.168.') or request.remote_addr.startswith('10.') or request.remote_addr.startswith('172.16.'):
            is_lan = True

    product_query = Product.query.filter_by(is_active=True)
    if user.role != 'admin' and user.city_id:
        if not is_city_active(user.city_id):
            return jsonify({'error': 'Your city is currently inactive. Please contact admin.'}), 403
        product_query = product_query.filter_by(city_id=user.city_id)
    if last_sync_dt:
        product_query = product_query.filter(Product.updated_at >= last_sync_dt)
    products = product_query.all()

    customer_query = Customer.query.filter_by(is_active=True)
    if user.role != 'admin' and user.city_id:
        customer_query = customer_query.filter_by(city_id=user.city_id)
    if last_sync_dt:
        customer_query = customer_query.filter(Customer.updated_at >= last_sync_dt)
    customers = customer_query.all()

    user_query = User.query.filter(User.role.in_(['sales', 'van']), User.is_active == True)
    if user.role != 'admin' and user.city_id:
        user_query = user_query.filter_by(city_id=user.city_id)
    if last_sync_dt:
        user_query = user_query.filter(User.updated_at >= last_sync_dt)
    users = user_query.all()

    orders = []
    if user.role in ['sales', 'van']:
        if user.role == 'sales':
            order_query = Order.query.filter_by(sales_person_id=user.id)
        else:
            delivery_ids = [d.order_id for d in Delivery.query.filter_by(assigned_to_user_id=user.id).all()]
            order_query = Order.query.filter(Order.id.in_(delivery_ids))
        if last_sync_dt:
            order_query = order_query.filter(Order.updated_at >= last_sync_dt)
        orders = order_query.all()

    price_lists = []
    if user.role == 'sales' and user.city_id:
        pl_query = PriceList.query.filter_by(is_active=True)
        pl_query = pl_query.filter(or_(PriceList.city_id == user.city_id, PriceList.city_id.is_(None)))
        if last_sync_dt:
            pl_query = pl_query.filter(PriceList.updated_at >= last_sync_dt)
        price_lists = pl_query.all()

    warehouse_query = Warehouse.query.filter_by(is_active=True)
    if user.role != 'admin' and user.city_id:
        warehouse_query = warehouse_query.filter_by(city_id=user.city_id)
    warehouses = warehouse_query.all()

    product_ids = [p.id for p in products]
    inventory_data = []
    if product_ids:
        inventories = Inventory.query.filter(Inventory.product_id.in_(product_ids)).all()
        for inv in inventories:
            inventory_data.append({
                'product_id': inv.product_id,
                'warehouse_id': inv.warehouse_id,
                'current_qty': inv.current_qty,
                'reserved_qty': inv.reserved_qty,
                'available_qty': inv.available_qty
            })

    deleted_products = []
    deleted_customers = []
    deleted_users = []
    if last_sync_dt:
        deleted_products = [p.id for p in Product.query.filter(
            Product.is_active == False,
            Product.updated_at >= last_sync_dt
        ).all()]
        deleted_customers = [c.id for c in Customer.query.filter(
            Customer.is_active == False,
            Customer.updated_at >= last_sync_dt
        ).all()]
        deleted_users = [u.id for u in User.query.filter(
            User.is_active == False,
            User.updated_at >= last_sync_dt
        ).all()]

    show_stock = user.show_stock_quantity if user.show_stock_quantity is not None else True
    catalog = pack_catalog(user.id, show_stock)

    new_tokens = []
    if is_lan:
        unused_count = TokenPool.query.filter_by(user_id=user.id, token_status='UNUSED').count()
        max_cap = int(ServerConfig.get('MAX_TOKEN_CAP', '15'))
        threshold = int(ServerConfig.get('TOKEN_RENEWAL_THRESHOLD', '2'))
        if unused_count <= threshold:
            new_tokens = auto_refill_tokens(user.id, unused_count, max_cap, threshold)

    pending_commands = get_pending_commands(user.id)

    result = {
        'products': [{
            'id': p.id,
            'name': p.name,
            'sku': p.sku,
            'barcode': p.barcode,
            'description': p.description,
            'unit_price': float(p.unit_price),
            'tax_rate': float(p.tax_rate),
            'category': p.category,
            'image_url': p.image_url,
            'city_id': p.city_id,
            'updated_at': p.updated_at.isoformat()
        } for p in products],
        'customers': [{
            'id': c.id,
            'name': c.name,
            'phone': c.phone,
            'email': c.email,
            'billing_address': c.billing_address,
            'shipping_address': c.shipping_address,
            'credit_limit': float(c.credit_limit),
            'outstanding_balance': float(c.outstanding_balance),
            'city_id': c.city_id,
            'updated_at': c.updated_at.isoformat() if hasattr(c, 'updated_at') else c.created_at.isoformat()
        } for c in customers],
        'users': [{
            'id': u.id,
            'username': u.username,
            'role': u.role,
            'city_id': u.city_id
        } for u in users],
        'orders': [{
            'id': o.id,
            'customer_id': o.customer_id,
            'customer_name': o.customer_name,
            'customer_phone': o.customer_phone,
            'shipping_address': o.shipping_address,
            'latitude': float(o.latitude) if o.latitude else None,
            'longitude': float(o.longitude) if o.longitude else None,
            'status': o.status,
            'net_total': float(o.net_total),
            'paid_amount': float(o.paid_amount),
            'remaining_balance': float(o.remaining_balance),
            'warehouse_id': o.warehouse_id,
            'items': [{
                'product_id': item.product_id,
                'product_name': item.product_name,
                'unit_price': float(item.unit_price),
                'ordered_qty': item.ordered_qty,
                'picked_qty': item.picked_qty,
                'delivered_qty': item.delivered_qty,
                'line_total': float(item.line_total)
            } for item in o.items],
            'updated_at': o.updated_at.isoformat()
        } for o in orders],
        'price_lists': [{
            'id': pl.id,
            'name': pl.name,
            'city_id': pl.city_id,
            'effective_from': pl.effective_from.isoformat() if pl.effective_from else None,
            'effective_to': pl.effective_to.isoformat() if pl.effective_to else None,
            'items': [{
                'product_id': item.product_id,
                'unit_price': float(item.unit_price),
                'discount_percent': float(item.discount_percent)
            } for item in pl.items]
        } for pl in price_lists],
        'warehouses': [{
            'id': w.id,
            'name': w.name,
            'code': w.code,
            'city_id': w.city_id,
            'address': w.address
        } for w in warehouses],
        'inventory': inventory_data,
        'settings': {
            'currency': Setting.get('currency', '$'),
            'tax_rate': float(Setting.get('tax_rate', '0.00')),
            'tax_label': Setting.get('tax_label', 'Tax'),
        },
        'sync_timestamp': datetime.utcnow().isoformat(),
        'deleted_products': deleted_products,
        'deleted_customers': deleted_customers,
        'deleted_users': deleted_users,
        'catalog': catalog,
        'new_tokens': new_tokens,
        'remaining_tokens': TokenPool.query.filter_by(user_id=user.id, token_status='UNUSED').count(),
        'commands': pending_commands,
        'is_lan': is_lan
    }
    return jsonify(result)

# =============================================================================
# INVENTORY TRANSACTION – STOREKEEPER REQUEST
# =============================================================================
@api_bp.route('/inventory/request-add', methods=['POST'])
def request_stock_add():
    user = request.user
    if user.role not in ['storekeeper', 'admin']:
        return jsonify({'error': 'Only storekeepers or admins can request stock additions'}), 403

    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'JSON body required'}), 400

        product_id = data.get('product_id')
        warehouse_id = data.get('warehouse_id')
        quantity = data.get('quantity')
        notes = data.get('notes', '')
        po_number = data.get('po_number')
        po_date_str = data.get('po_date')
        ordered_qty = data.get('ordered_qty')
        attachment_url = data.get('attachment_url')

        if not product_id or not warehouse_id or quantity is None:
            return jsonify({'error': 'product_id, warehouse_id, and quantity required'}), 400

        try:
            quantity = int(quantity)
            if quantity <= 0:
                return jsonify({'error': 'Quantity must be positive'}), 400
        except ValueError:
            return jsonify({'error': 'Quantity must be an integer'}), 400

        product = Product.query.get(product_id)
        if not product:
            return jsonify({'error': 'Product not found'}), 404

        warehouse = Warehouse.query.get(warehouse_id)
        if not warehouse:
            return jsonify({'error': 'Warehouse not found'}), 404

        if warehouse.city_id and not is_city_active(warehouse.city_id):
            return jsonify({'error': 'The city associated with this warehouse is currently inactive. Cannot request stock.'}), 400

        po_date = parse_iso_date(po_date_str)

        ordered_qty_int = None
        if ordered_qty is not None:
            try:
                ordered_qty_int = int(ordered_qty)
            except ValueError:
                return jsonify({'error': 'Ordered quantity must be an integer'}), 400

        txn = InventoryTransaction(
            product_id=product.id,
            warehouse_id=warehouse.id,
            quantity=quantity,
            type='stock_add',
            requested_by=user.id,
            notes=notes,
            status='pending',
            po_number=po_number,
            po_date=po_date,
            ordered_qty=ordered_qty_int,
            attachment_url=attachment_url
        )
        db.session.add(txn)
        db.session.flush()

        auto_approved = False
        if Setting.get('auto_approve_enabled', 'true') == 'true':
            threshold = int(Setting.get('auto_approve_threshold', '10'))
            if quantity <= threshold:
                window_days = int(Setting.get('auto_approve_time_window', '1'))
                max_total = int(Setting.get('auto_approve_max_total', '20'))
                cutoff = datetime.utcnow() - timedelta(days=window_days)
                recent_total = db.session.query(func.sum(InventoryTransaction.quantity))\
                    .filter(InventoryTransaction.requested_by == user.id,
                            InventoryTransaction.created_at >= cutoff,
                            InventoryTransaction.status.in_(['pending', 'approved']),
                            InventoryTransaction.type == 'stock_add')\
                    .scalar() or 0
                if recent_total + quantity <= max_total:
                    auto_approved = True
                    txn.status = 'approved'
                    txn.approved_by = None
                    txn.approved_at = datetime.utcnow()

                    inv = Inventory.query.filter_by(product_id=product.id, warehouse_id=warehouse.id).first()
                    before_qty = inv.current_qty if inv else 0
                    if inv:
                        inv.current_qty += quantity
                    else:
                        inv = Inventory(product_id=product.id, warehouse_id=warehouse.id, current_qty=quantity)
                        db.session.add(inv)
                    after_qty = inv.current_qty
                    txn.before_qty = before_qty
                    txn.after_qty = after_qty

                    log_activity(user.id, 'auto_approve_stock_add', 'inventory_transactions', txn.id,
                                 None, {'product_id': product.id, 'warehouse_id': warehouse.id, 'quantity': quantity,
                                        'po_number': po_number, 'ordered_qty': ordered_qty, 'before_qty': before_qty, 'after_qty': after_qty})
                    create_notification(
                        user_id=user.id,
                        title='Stock Request Auto‑Approved',
                        body=f'Your request for {quantity} x {product.name} was auto‑approved.'
                    )

        db.session.commit()

        if not auto_approved:
            admins = User.query.filter(User.role.in_(['admin', 'subadmin']), User.is_active == True).all()
            for admin in admins:
                create_notification(
                    user_id=admin.id,
                    title='New Stock Request Pending',
                    body=f'Storekeeper {user.username} requested {quantity} x {product.name}. Please approve.',
                    data={'transaction_id': txn.id}
                )

        return jsonify({
            'status': txn.status,
            'transaction_id': txn.id,
            'auto_approved': auto_approved,
            'message': 'Request submitted' + (' and auto‑approved' if auto_approved else ', pending approval')
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Stock request error: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'error': f'Server error: {str(e)}'}), 500

@api_bp.route('/inventory/upload-po', methods=['POST'])
def upload_po_slip():
    user = request.user
    if user.role not in ['storekeeper', 'admin']:
        return jsonify({'error': 'Forbidden'}), 403

    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Empty filename'}), 400

    url = save_uploaded_file(file, subfolder='po_slips')
    if not url:
        return jsonify({'error': 'Failed to save file'}), 500

    return jsonify({
        'status': 'success',
        'url': url
    })

@api_bp.route('/inventory-transactions', methods=['GET'])
def list_inventory_transactions():
    user = request.user
    if user.role not in ['admin', 'subadmin']:
        return jsonify({'error': 'Forbidden'}), 403

    status_filter = request.args.get('status')
    type_filter = request.args.get('type')
    from_date = request.args.get('from')
    to_date = request.args.get('to')
    limit = min(int(request.args.get('limit', 50)), 200)

    query = InventoryTransaction.query
    if status_filter:
        query = query.filter_by(status=status_filter)
    if type_filter:
        query = query.filter_by(type=type_filter)
    if from_date:
        query = query.filter(InventoryTransaction.created_at >= from_date)
    if to_date:
        query = query.filter(InventoryTransaction.created_at <= to_date)

    if user.role == 'subadmin' and user.city_id:
        warehouse_ids = [w.id for w in Warehouse.query.filter_by(city_id=user.city_id).all()]
        user_ids = [u.id for u in User.query.filter_by(city_id=user.city_id).all()]
        query = query.filter(
            or_(
                InventoryTransaction.warehouse_id.in_(warehouse_ids),
                InventoryTransaction.agent_user_id.in_(user_ids),
                InventoryTransaction.requested_by.in_(user_ids)
            )
        )

    transactions = query.options(
        joinedload(InventoryTransaction.product),
        joinedload(InventoryTransaction.warehouse),
        joinedload(InventoryTransaction.requester),
        joinedload(InventoryTransaction.approver),
        joinedload(InventoryTransaction.agent_user)
    ).order_by(InventoryTransaction.created_at.desc()).limit(limit).all()

    result = []
    for t in transactions:
        result.append({
            'id': t.id,
            'product_id': t.product_id,
            'product_name': t.product.name if t.product else 'Unknown',
            'warehouse_id': t.warehouse_id,
            'warehouse_name': t.warehouse.name if t.warehouse else 'N/A',
            'agent_user_id': t.agent_user_id,
            'agent_username': t.agent_user.username if t.agent_user else None,
            'quantity': t.quantity,
            'type': t.type,
            'status': t.status,
            'requested_by': t.requester.username if t.requester else 'Unknown',
            'approved_by': t.approver.username if t.approver else None,
            'notes': t.notes,
            'created_at': t.created_at.isoformat(),
            'approved_at': t.approved_at.isoformat() if t.approved_at else None,
            'po_number': t.po_number,
            'po_date': t.po_date.isoformat() if t.po_date else None,
            'attachment_url': t.attachment_url,
            'ordered_qty': t.ordered_qty,
            'before_qty': t.before_qty,
            'after_qty': t.after_qty
        })
    return jsonify({'transactions': result})

@api_bp.route('/inventory-transactions/<int:txn_id>/approve', methods=['PUT'])
def approve_inventory_transaction(txn_id):
    user = request.user
    if user.role not in ['admin', 'subadmin']:
        return jsonify({'error': 'Forbidden'}), 403

    txn = InventoryTransaction.query.get(txn_id)
    if not txn:
        return jsonify({'error': 'Transaction not found'}), 404
    if txn.status != 'pending':
        return jsonify({'error': f'Transaction already {txn.status}'}), 400

    try:
        before_qty = None
        after_qty = None

        if txn.type == 'stock_add':
            inv = Inventory.query.filter_by(product_id=txn.product_id, warehouse_id=txn.warehouse_id).first()
            before_qty = inv.current_qty if inv else 0
            if inv:
                inv.current_qty += txn.quantity
            else:
                inv = Inventory(product_id=txn.product_id, warehouse_id=txn.warehouse_id, current_qty=txn.quantity)
                db.session.add(inv)
            after_qty = inv.current_qty
        elif txn.type == 'return':
            if txn.agent_user_id:
                agent_inv = AgentInventory.query.filter_by(user_id=txn.agent_user_id, product_id=txn.product_id).first()
                before_qty = agent_inv.current_physical_qty if agent_inv else 0
                if agent_inv:
                    agent_inv.current_physical_qty += txn.quantity
                else:
                    agent_inv = AgentInventory(user_id=txn.agent_user_id, product_id=txn.product_id, current_physical_qty=txn.quantity)
                    db.session.add(agent_inv)
                after_qty = agent_inv.current_physical_qty
            elif txn.warehouse_id:
                inv = Inventory.query.filter_by(product_id=txn.product_id, warehouse_id=txn.warehouse_id).first()
                before_qty = inv.current_qty if inv else 0
                if inv:
                    inv.current_qty += txn.quantity
                else:
                    inv = Inventory(product_id=txn.product_id, warehouse_id=txn.warehouse_id, current_qty=txn.quantity)
                    db.session.add(inv)
                after_qty = inv.current_qty
        elif txn.type == 'correction':
            if txn.warehouse_id:
                inv = Inventory.query.filter_by(product_id=txn.product_id, warehouse_id=txn.warehouse_id).first()
                before_qty = inv.current_qty if inv else 0
                if inv:
                    inv.current_qty += txn.quantity
                else:
                    inv = Inventory(product_id=txn.product_id, warehouse_id=txn.warehouse_id, current_qty=txn.quantity if txn.quantity > 0 else 0)
                    db.session.add(inv)
                after_qty = inv.current_qty
            elif txn.agent_user_id:
                agent_inv = AgentInventory.query.filter_by(user_id=txn.agent_user_id, product_id=txn.product_id).first()
                before_qty = agent_inv.current_physical_qty if agent_inv else 0
                if agent_inv:
                    agent_inv.current_physical_qty += txn.quantity
                else:
                    agent_inv = AgentInventory(user_id=txn.agent_user_id, product_id=txn.product_id, current_physical_qty=txn.quantity if txn.quantity > 0 else 0)
                    db.session.add(agent_inv)
                after_qty = agent_inv.current_physical_qty
        else:
            return jsonify({'error': f'Unsupported transaction type: {txn.type}'}), 400

        txn.before_qty = before_qty
        txn.after_qty = after_qty
        txn.status = 'approved'
        txn.approved_by = user.id
        txn.approved_at = datetime.utcnow()
        db.session.commit()

        log_activity(user.id, 'approve_inventory_transaction', 'inventory_transactions', txn.id,
                     {'status': 'pending'}, {'status': 'approved', 'quantity': txn.quantity,
                      'before_qty': before_qty, 'after_qty': after_qty})

        create_notification(
            user_id=txn.requested_by,
            title='Stock Request Approved',
            body=f'Your request for {txn.quantity} x {txn.product.name} has been approved. (Before: {before_qty}, After: {after_qty})',
            data={'transaction_id': txn.id}
        )

        return jsonify({'status': 'success', 'message': 'Transaction approved'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Approve transaction error: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/inventory-transactions/<int:txn_id>/reject', methods=['PUT'])
def reject_inventory_transaction(txn_id):
    user = request.user
    if user.role not in ['admin', 'subadmin']:
        return jsonify({'error': 'Forbidden'}), 403

    txn = InventoryTransaction.query.get(txn_id)
    if not txn:
        return jsonify({'error': 'Transaction not found'}), 404
    if txn.status != 'pending':
        return jsonify({'error': f'Transaction already {txn.status}'}), 400

    try:
        data = request.get_json() or {}
        reason = data.get('reason', 'No reason provided')
        txn.status = 'rejected'
        txn.notes = (txn.notes or '') + f' Rejected: {reason}'
        db.session.commit()

        log_activity(user.id, 'reject_inventory_transaction', 'inventory_transactions', txn.id,
                     {'status': 'pending'}, {'status': 'rejected', 'reason': reason})

        create_notification(
            user_id=txn.requested_by,
            title='Stock Request Rejected',
            body=f'Your request for {txn.quantity} x {txn.product.name} was rejected. Reason: {reason}',
            data={'transaction_id': txn.id}
        )

        return jsonify({'status': 'success', 'message': 'Transaction rejected'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Reject transaction error: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

# ========================
# CITIES
# ========================
@api_bp.route('/cities', methods=['GET'])
def list_cities():
    user = request.user
    if user.role not in ['admin', 'subadmin', 'captain', 'storekeeper']:
        return jsonify({'error': 'Forbidden'}), 403

    include_inactive = request.args.get('include_inactive', 'false').lower() == 'true'
    if user.role == 'admin' and include_inactive:
        cities = City.query.all()
    else:
        cities = City.query.filter_by(is_active=True).all()

    return jsonify({
        'cities': [{'id': c.id, 'name': c.name, 'is_active': c.is_active} for c in cities]
    })

@api_bp.route('/cities', methods=['POST'])
def create_city():
    user = request.user
    if user.role != 'admin':
        return jsonify({'error': 'Only admin can create cities'}), 403

    data = request.get_json()
    if not data:
        return jsonify({'error': 'JSON body required'}), 400

    name = data.get('name')
    if not name or not name.strip():
        return jsonify({'error': 'City name is required'}), 400

    if City.query.filter_by(name=name.strip()).first():
        return jsonify({'error': 'City already exists'}), 400

    city = City(name=name.strip(), is_active=True)
    db.session.add(city)
    db.session.commit()

    log_activity(user.id, 'create_city', 'cities', city.id, None, {'name': city.name})
    return jsonify({'status': 'success', 'id': city.id, 'name': city.name})

@api_bp.route('/cities/<int:city_id>/toggle', methods=['PUT'])
def toggle_city_status(city_id):
    user = request.user
    if user.role != 'admin':
        return jsonify({'error': 'Only admin can change city status'}), 403

    city = City.query.get(city_id)
    if not city:
        return jsonify({'error': 'City not found'}), 404

    new_status = not city.is_active
    city.is_active = new_status
    db.session.commit()

    if not new_status:
        log_activity(user.id, 'close_city', 'cities', city.id, {'is_active': True}, {'is_active': False})
        message = f'City "{city.name}" has been closed (inactive).'
    else:
        log_activity(user.id, 'reactivate_city', 'cities', city.id, {'is_active': False}, {'is_active': True})
        message = f'City "{city.name}" has been reactivated.'

    return jsonify({
        'status': 'success',
        'city_id': city.id,
        'is_active': city.is_active,
        'message': message
    })

# ========================
# WAREHOUSES
# ========================
@api_bp.route('/warehouses', methods=['GET'])
def list_warehouses():
    user = request.user
    if user.role not in ['admin', 'subadmin', 'storekeeper']:
        return jsonify({'error': 'Forbidden'}), 403

    include_inactive = request.args.get('include_inactive', 'false').lower() == 'true'
    if user.role == 'admin' and include_inactive:
        warehouses = Warehouse.query.all()
    else:
        query = Warehouse.query.filter_by(is_active=True)
        if user.role == 'storekeeper' and user.city_id:
            query = query.filter_by(city_id=user.city_id)
        elif user.role == 'subadmin' and user.city_id:
            query = query.filter_by(city_id=user.city_id)
        warehouses = query.all()

    result = [{
        'id': w.id,
        'name': w.name,
        'code': w.code,
        'city_id': w.city_id,
        'city_name': w.city.name if w.city else None,
        'address': w.address,
        'is_active': w.is_active,
        'created_at': w.created_at.isoformat()
    } for w in warehouses]
    return jsonify({'warehouses': result})

@api_bp.route('/warehouses', methods=['POST'])
def create_warehouse():
    user = request.user
    if user.role not in ['admin', 'subadmin']:
        return jsonify({'error': 'Forbidden'}), 403

    data = request.get_json()
    name = data.get('name')
    code = data.get('code')
    city_id = data.get('city_id')
    address = data.get('address')

    if not name or not code or not city_id:
        return jsonify({'error': 'name, code, city_id required'}), 400

    if not is_city_active(city_id):
        return jsonify({'error': 'Selected city is inactive'}), 400

    if Warehouse.query.filter_by(code=code).first():
        return jsonify({'error': 'Warehouse code already exists'}), 400

    warehouse = Warehouse(
        name=name,
        code=code,
        city_id=city_id,
        address=address,
        is_active=True
    )
    db.session.add(warehouse)
    db.session.commit()
    log_activity(user.id, 'create_warehouse', 'warehouses', warehouse.id, None, {'name': name, 'code': code})
    return jsonify({'status': 'success', 'id': warehouse.id, 'message': 'Warehouse created'})

@api_bp.route('/warehouses/<int:warehouse_id>', methods=['PUT'])
def update_warehouse(warehouse_id):
    user = request.user
    if user.role not in ['admin', 'subadmin']:
        return jsonify({'error': 'Forbidden'}), 403

    warehouse = Warehouse.query.get(warehouse_id)
    if not warehouse:
        return jsonify({'error': 'Warehouse not found'}), 404

    data = request.get_json()
    old_data = {'name': warehouse.name, 'code': warehouse.code, 'address': warehouse.address, 'is_active': warehouse.is_active}
    warehouse.name = data.get('name', warehouse.name)
    warehouse.code = data.get('code', warehouse.code)
    warehouse.address = data.get('address', warehouse.address)
    warehouse.is_active = data.get('is_active', warehouse.is_active)
    db.session.commit()
    log_activity(user.id, 'update_warehouse', 'warehouses', warehouse_id, old_data, {'name': warehouse.name, 'code': warehouse.code})
    return jsonify({'status': 'success', 'message': 'Warehouse updated'})

@api_bp.route('/warehouses/<int:warehouse_id>', methods=['DELETE'])
def delete_warehouse(warehouse_id):
    user = request.user
    if user.role not in ['admin', 'subadmin']:
        return jsonify({'error': 'Forbidden'}), 403

    warehouse = Warehouse.query.get(warehouse_id)
    if not warehouse:
        return jsonify({'error': 'Warehouse not found'}), 404
    warehouse.is_active = False
    db.session.commit()
    log_activity(user.id, 'delete_warehouse', 'warehouses', warehouse_id, {'is_active': True}, {'is_active': False})
    return jsonify({'status': 'success', 'message': 'Warehouse deactivated'})

# ========================
# INVENTORY MANAGEMENT
# ========================
@api_bp.route('/products/<int:product_id>/inventory', methods=['GET'])
def get_product_inventory(product_id):
    user = request.user
    if user.role not in ['admin', 'subadmin', 'storekeeper']:
        return jsonify({'error': 'Forbidden'}), 403

    product = Product.query.get(product_id)
    if not product:
        return jsonify({'error': 'Product not found'}), 404

    inventories = Inventory.query.filter_by(product_id=product_id).all()
    result = []
    for inv in inventories:
        result.append({
            'warehouse_id': inv.warehouse_id,
            'warehouse_name': inv.warehouse.name,
            'current_qty': inv.current_qty,
            'reserved_qty': inv.reserved_qty,
            'available_qty': inv.available_qty
        })
    total_current = sum(inv.current_qty for inv in inventories)
    total_reserved = sum(inv.reserved_qty for inv in inventories)
    return jsonify({
        'product_id': product_id,
        'inventory': result,
        'total_current': total_current,
        'total_reserved': total_reserved,
        'total_available': total_current - total_reserved
    })

@api_bp.route('/inventory/update', methods=['POST'])
def update_inventory():
    user = request.user
    if user.role not in ['admin', 'subadmin']:
        return jsonify({'error': 'Forbidden'}), 403

    data = request.get_json()
    product_id = data.get('product_id')
    warehouse_id = data.get('warehouse_id')
    quantity = data.get('quantity')
    operation = data.get('operation', 'set')

    if not product_id or not warehouse_id or quantity is None:
        return jsonify({'error': 'product_id, warehouse_id, quantity required'}), 400

    product = Product.query.get(product_id)
    if not product:
        return jsonify({'error': 'Product not found'}), 404
    warehouse = Warehouse.query.get(warehouse_id)
    if not warehouse:
        return jsonify({'error': 'Warehouse not found'}), 404
    if not warehouse.is_active:
        return jsonify({'error': 'Warehouse is inactive'}), 400
    if not is_city_active(warehouse.city_id):
        return jsonify({'error': 'City of this warehouse is inactive'}), 400

    inv = Inventory.query.filter_by(product_id=product_id, warehouse_id=warehouse_id).first()
    if not inv:
        inv = Inventory(product_id=product_id, warehouse_id=warehouse_id, current_qty=0, reserved_qty=0)
        db.session.add(inv)

    old_qty = inv.current_qty
    if operation == 'set':
        inv.current_qty = quantity
    elif operation == 'add':
        inv.current_qty += quantity
    elif operation == 'subtract':
        inv.current_qty = max(0, inv.current_qty - quantity)
    else:
        return jsonify({'error': 'Invalid operation'}), 400

    product.current_warehouse_qty = sum(i.current_qty for i in product.inventory_items)
    product.reserved_warehouse_qty = sum(i.reserved_qty for i in product.inventory_items)

    db.session.commit()
    log_activity(user.id, 'update_inventory', 'inventory', inv.id, {'old_qty': old_qty}, {'new_qty': inv.current_qty})
    return jsonify({'status': 'success', 'message': 'Inventory updated', 'new_qty': inv.current_qty})

# ========================
# ORDER LIFECYCLE
# ========================
@api_bp.route('/orders/place', methods=['POST'])
def place_order():
    user = request.user
    if user.role not in ['sales', 'admin']:
        return jsonify({'error': 'Only sales reps can place orders'}), 403

    data = request.get_json()
    if not data:
        return jsonify({'error': 'JSON body required'}), 400

    customer_id = data.get('customer_id')
    if not customer_id:
        return jsonify({'error': 'customer_id required'}), 400

    customer = Customer.query.get(customer_id)
    if not customer:
        return jsonify({'error': 'Customer not found'}), 404

    if customer.city_id and not is_city_active(customer.city_id):
        return jsonify({
            'error': 'The city for this customer is currently inactive. Cannot place order.'
        }), 400

    order_total = Decimal('0.00')
    items_data = data.get('items', [])
    if not items_data:
        return jsonify({'error': 'At least one item required'}), 400

    for item in items_data:
        product_id = item.get('product_id')
        qty = item.get('quantity', 1)
        if not product_id:
            return jsonify({'error': 'product_id required for each item'}), 400
        product = Product.query.get(product_id)
        if not product:
            return jsonify({'error': f'Product {product_id} not found'}), 404
        price = safe_decimal(item.get('unit_price', product.unit_price))
        line_total = price * Decimal(str(qty))
        order_total += line_total

    discount = safe_decimal(data.get('discount'))
    tax_rate = safe_decimal(data.get('tax_rate'))
    tax_amount = (order_total - discount) * tax_rate / Decimal('100')
    net_total = order_total - discount + tax_amount

    if customer.credit_limit and customer.credit_limit > 0:
        new_outstanding = customer.outstanding_balance + net_total
        if new_outstanding > customer.credit_limit:
            return jsonify({
                'error': 'Credit limit exceeded',
                'credit_limit': float(customer.credit_limit),
                'outstanding_balance': float(customer.outstanding_balance),
                'order_total': float(net_total)
            }), 400

    try:
        order = Order(
            customer_id=customer.id,
            customer_name=customer.name,
            customer_phone=customer.phone,
            shipping_address=data.get('shipping_address', customer.shipping_address),
            latitude=data.get('latitude'),
            longitude=data.get('longitude'),
            city_id=customer.city_id,
            sales_person_id=user.id,
            status='pending',
            subtotal=order_total,
            discount=discount,
            tax_amount=tax_amount,
            net_total=net_total,
            paid_amount=Decimal('0.00'),
            remaining_balance=net_total,
            payment_terms=data.get('payment_terms'),
            special_instructions=data.get('special_instructions')
        )
        db.session.add(order)
        db.session.flush()

        for item in items_data:
            product_id = item.get('product_id')
            qty = item.get('quantity', 1)
            product = Product.query.get(product_id)
            if not product:
                continue
            unit_price = safe_decimal(item.get('unit_price', product.unit_price))
            line_total = unit_price * Decimal(str(qty))
            order_item = OrderItem(
                order_id=order.id,
                product_id=product.id,
                product_name=product.name,
                product_barcode=product.barcode,
                unit_price=unit_price,
                ordered_qty=qty,
                line_total=line_total
            )
            db.session.add(order_item)

        media_files = data.get('media', [])
        for media in media_files:
            order_media = OrderMedia(
                order_id=order.id,
                media_type=media.get('type', 'image'),
                file_url=media.get('url')
            )
            db.session.add(order_media)

        db.session.commit()
        log_activity(user.id, 'place_order', 'orders', order.id, None, {'customer': customer.name, 'total': str(net_total)})

        captains = User.query.filter_by(role='captain', city_id=user.city_id, is_active=True).all()
        for captain in captains:
            create_notification(
                user_id=captain.id,
                title='New Order',
                body=f'Order #{order.id} from {customer.name} worth ${net_total:.2f}',
                data={'order_id': order.id, 'status': 'pending'}
            )

        try:
            socketio = current_app.socketio
            socketio.emit('new_order', {
                'order_id': order.id,
                'customer_name': customer.name,
                'net_total': float(net_total)
            }, room='captains')
        except Exception as e:
            current_app.logger.warning(f"Socket emit failed for order {order.id}: {str(e)}")

        return jsonify({
            'status': 'success',
            'order_id': order.id,
            'message': 'Order placed successfully'
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Place order error: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'error': 'Internal server error'}), 500

@api_bp.route('/orders', methods=['GET'])
def list_orders():
    user = request.user
    allowed_roles = ['sales', 'captain', 'admin', 'subadmin', 'storekeeper']
    if user.role not in allowed_roles:
        return jsonify({'error': 'Forbidden'}), 403

    query = Order.query
    if user.role == 'sales':
        query = query.filter_by(sales_person_id=user.id)
    elif user.role == 'captain':
        query = query.filter_by(city_id=user.city_id)
    elif user.role == 'storekeeper':
        query = query.filter_by(city_id=user.city_id)
    elif user.role in ['admin', 'subadmin']:
        if user.city_id:
            query = query.filter_by(city_id=user.city_id)

    status = request.args.get('status')
    if status:
        query = query.filter_by(status=status)
    customer_id = request.args.get('customer_id')
    if customer_id:
        query = query.filter_by(customer_id=customer_id)
    from_date = request.args.get('from')
    to_date = request.args.get('to')
    if from_date:
        query = query.filter(Order.created_at >= from_date)
    if to_date:
        query = query.filter(Order.created_at <= to_date)
    limit = request.args.get('limit', default=100, type=int)
    offset = request.args.get('offset', default=0, type=int)

    orders = query.options(
        joinedload(Order.sales_person),
        joinedload(Order.captain),
        joinedload(Order.warehouse),
        selectinload(Order.items)
    ).order_by(Order.created_at.desc()).offset(offset).limit(limit).all()

    result = []
    for o in orders:
        result.append({
            'id': o.id,
            'customer_name': o.customer_name,
            'customer_phone': o.customer_phone,
            'status': o.status,
            'net_total': float(o.net_total),
            'paid_amount': float(o.paid_amount),
            'remaining_balance': float(o.remaining_balance),
            'warehouse_id': o.warehouse_id,
            'warehouse_name': o.warehouse.name if o.warehouse else None,
            'sales_person': o.sales_person.username if o.sales_person else None,
            'captain': o.captain.username if o.captain else None,
            'created_at': o.created_at.isoformat(),
            'items': [{
                'id': item.id,
                'product_name': item.product_name,
                'unit_price': float(item.unit_price),
                'ordered_qty': item.ordered_qty,
                'picked_qty': item.picked_qty,
                'delivered_qty': item.delivered_qty,
                'line_total': float(item.line_total)
            } for item in o.items]
        })
    total_count = query.count()
    return jsonify({
        'orders': result,
        'total': total_count,
        'limit': limit,
        'offset': offset
    })

@api_bp.route('/orders/<int:order_id>', methods=['GET'])
def order_detail(order_id):
    user = request.user
    order = Order.query.options(
        joinedload(Order.sales_person),
        joinedload(Order.captain),
        joinedload(Order.store_keeper),
        joinedload(Order.warehouse),
        selectinload(Order.items),
        selectinload(Order.media)
    ).get(order_id)
    if not order:
        return jsonify({'error': 'Order not found'}), 404

    if user.role not in ['admin', 'subadmin']:
        if user.role == 'sales' and order.sales_person_id != user.id:
            return jsonify({'error': 'Access denied'}), 403
        if user.role == 'captain' and order.city_id != user.city_id:
            return jsonify({'error': 'Access denied'}), 403
        if user.role == 'storekeeper' and order.city_id != user.city_id:
            return jsonify({'error': 'Access denied'}), 403

    return jsonify({
        'id': order.id,
        'customer_id': order.customer_id,
        'customer_name': order.customer_name,
        'customer_phone': order.customer_phone,
        'shipping_address': order.shipping_address,
        'latitude': float(order.latitude) if order.latitude else None,
        'longitude': float(order.longitude) if order.longitude else None,
        'status': order.status,
        'subtotal': float(order.subtotal),
        'discount': float(order.discount),
        'tax_amount': float(order.tax_amount),
        'net_total': float(order.net_total),
        'paid_amount': float(order.paid_amount),
        'remaining_balance': float(order.remaining_balance),
        'warehouse_id': order.warehouse_id,
        'warehouse_name': order.warehouse.name if order.warehouse else None,
        'sales_person': order.sales_person.username if order.sales_person else None,
        'captain': order.captain.username if order.captain else None,
        'store_keeper': order.store_keeper.username if order.store_keeper else None,
        'payment_terms': order.payment_terms,
        'special_instructions': order.special_instructions,
        'created_at': order.created_at.isoformat(),
        'updated_at': order.updated_at.isoformat(),
        'picked_at': order.picked_at.isoformat() if order.picked_at else None,
        'packed_at': order.packed_at.isoformat() if order.packed_at else None,
        'package_barcode': order.package_barcode,
        'package_qr': order.package_qr,
        'dispatched_at': order.dispatched_at.isoformat() if order.dispatched_at else None,
        'items': [{
            'id': item.id,
            'product_id': item.product_id,
            'product_name': item.product_name,
            'product_barcode': item.product_barcode,
            'unit_price': float(item.unit_price),
            'ordered_qty': item.ordered_qty,
            'picked_qty': item.picked_qty,
            'delivered_qty': item.delivered_qty,
            'line_total': float(item.line_total),
            'note': item.note
        } for item in order.items],
        'media': [{
            'id': m.id,
            'media_type': m.media_type,
            'file_url': m.file_url,
            'uploaded_at': m.uploaded_at.isoformat()
        } for m in order.media]
    })

@api_bp.route('/orders/<int:order_id>/edit', methods=['PUT'])
def edit_order(order_id):
    user = request.user
    if user.role not in ['sales', 'captain', 'admin']:
        return jsonify({'error': 'Forbidden'}), 403

    order = Order.query.get(order_id)
    if not order:
        return jsonify({'error': 'Order not found'}), 404

    if order.status != 'pending':
        return jsonify({'error': 'Only pending orders can be edited'}), 400

    if not is_city_active(order.city_id):
        return jsonify({'error': 'City is inactive. Cannot edit order.'}), 400

    if user.role == 'sales' and order.sales_person_id != user.id:
        return jsonify({'error': 'Access denied'}), 403
    if user.role == 'captain' and order.city_id != user.city_id:
        return jsonify({'error': 'Access denied'}), 403

    data = request.get_json()
    if 'shipping_address' in data:
        order.shipping_address = data['shipping_address']
    if 'latitude' in data:
        order.latitude = data['latitude']
    if 'longitude' in data:
        order.longitude = data['longitude']
    if 'payment_terms' in data:
        order.payment_terms = data['payment_terms']
    if 'special_instructions' in data:
        order.special_instructions = data['special_instructions']

    if 'items' in data:
        for item in order.items:
            db.session.delete(item)
        new_items = data['items']
        new_total = Decimal('0.00')
        for it in new_items:
            product_id = it.get('product_id')
            qty = it.get('quantity', 1)
            product = Product.query.get(product_id)
            if not product:
                continue
            unit_price = safe_decimal(it.get('unit_price', product.unit_price))
            line_total = unit_price * Decimal(str(qty))
            new_total += line_total
            order_item = OrderItem(
                order_id=order.id,
                product_id=product.id,
                product_name=product.name,
                product_barcode=product.barcode,
                unit_price=unit_price,
                ordered_qty=qty,
                line_total=line_total
            )
            db.session.add(order_item)
        order.subtotal = new_total
        discount = safe_decimal(data.get('discount', order.discount))
        if 'tax_rate' in data:
            tax_rate = safe_decimal(data['tax_rate'])
        else:
            tax_rate = Decimal(str(order.tax_rate or 0))
        tax_amount = (new_total - discount) * tax_rate / Decimal('100')
        order.discount = discount
        order.tax_amount = tax_amount
        order.net_total = new_total - discount + tax_amount
        order.remaining_balance = order.net_total - order.paid_amount

    db.session.commit()
    log_activity(user.id, 'edit_order', 'orders', order.id, None, {'status': 'edited'}, order_id=order.id)
    return jsonify({'status': 'success', 'message': 'Order updated'})

@api_bp.route('/orders/<int:order_id>/reject', methods=['POST'])
def reject_order(order_id):
    user = request.user
    if user.role not in ['captain', 'admin']:
        return jsonify({'error': 'Only captains or admins can reject orders'}), 403

    order = Order.query.get(order_id)
    if not order:
        return jsonify({'error': 'Order not found'}), 404

    if order.city_id != user.city_id and user.role != 'admin':
        return jsonify({'error': 'Order does not belong to your city'}), 403

    if order.status != 'pending':
        return jsonify({'error': f'Order is already {order.status}'}), 400

    try:
        data = request.get_json() or {}
        reason = data.get('reason', 'No reason provided')
        order.status = 'rejected'
        order.special_instructions = (order.special_instructions or '') + f' Rejected: {reason}'
        db.session.commit()

        create_notification(
            user_id=order.sales_person_id,
            title='Order Rejected',
            body=f'Order #{order.id} was rejected. Reason: {reason}',
            data={'order_id': order.id, 'status': 'rejected'}
        )
        log_activity(user.id, 'reject_order', 'orders', order.id, {'status': 'pending'}, {'status': 'rejected', 'reason': reason}, order_id=order.id)
        return jsonify({'status': 'success', 'message': 'Order rejected'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Reject order error: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/orders/<int:order_id>/transit', methods=['PUT'])
def transit_order(order_id):
    user = request.user
    if user.role not in ['captain', 'van', 'admin']:
        return jsonify({'error': 'Forbidden'}), 403

    order = Order.query.get(order_id)
    if not order:
        return jsonify({'error': 'Order not found'}), 404

    if not is_city_active(order.city_id):
        return jsonify({'error': 'City is inactive. Cannot mark as in transit.'}), 400

    if order.status != 'dispatched':
        return jsonify({'error': f'Order must be dispatched first (current: {order.status})'}), 400

    try:
        order.status = 'in_transit'
        db.session.commit()
        create_notification(
            user_id=order.sales_person_id,
            title='Order In Transit',
            body=f'Order #{order.id} is on the way.',
            data={'order_id': order.id, 'status': 'in_transit'}
        )
        log_activity(user.id, 'transit_order', 'orders', order.id, {'status': 'dispatched'}, {'status': 'in_transit'}, order_id=order.id)
        return jsonify({'status': 'success', 'message': 'Order marked as in transit'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Transit order error: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/orders/<int:order_id>/deliver', methods=['PUT'])
def deliver_order(order_id):
    user = request.user
    if user.role not in ['van', 'captain', 'admin']:
        return jsonify({'error': 'Forbidden'}), 403

    order = Order.query.get(order_id)
    if not order:
        return jsonify({'error': 'Order not found'}), 404

    if order.status == 'delivered':
        return jsonify({'status': 'success', 'message': 'Order is already marked as delivered'}), 200

    if not is_city_active(order.city_id):
        return jsonify({'error': 'City is inactive. Cannot deliver order.'}), 400

    if order.status not in ['in_transit', 'dispatched']:
        return jsonify({'error': f'Order must be in transit or dispatched (current: {order.status})'}), 400

    data = request.get_json() or {}
    delivered_items = data.get('items', [])
    if not delivered_items:
        return jsonify({'error': 'Provide items with delivered quantities'}), 400

    delivery = Delivery.query.filter_by(order_id=order.id).first()
    agent_user_id = delivery.assigned_to_user_id if delivery else user.id

    try:
        for delivered in delivered_items:
            order_item_id = delivered.get('order_item_id')
            qty = delivered.get('delivered_qty', 0)
            if qty == 0:
                continue
            item = OrderItem.query.get(order_item_id)
            if not item or item.order_id != order.id:
                continue
            agent_inv = AgentInventory.query.filter_by(user_id=agent_user_id, product_id=item.product_id).first()
            available = agent_inv.current_physical_qty if agent_inv else 0
            if available < qty:
                return jsonify({
                    'error': f'Insufficient stock for product {item.product_name}. Available: {available}, requested to deliver: {qty}'
                }), 400

        for delivered in delivered_items:
            order_item_id = delivered.get('order_item_id')
            qty = delivered.get('delivered_qty', 0)
            if not order_item_id:
                continue
            item = OrderItem.query.get(order_item_id)
            if item and item.order_id == order.id:
                item.delivered_qty = qty

        all_delivered = all(item.delivered_qty >= item.ordered_qty for item in order.items)
        if all_delivered:
            order.status = 'delivered'
        else:
            order.status = 'partially_delivered'

        if delivery:
            delivery.status = 'delivered' if all_delivered else 'partially_delivered'
            delivery.actual_delivery_date = datetime.utcnow()

        for item in order.items:
            if item.delivered_qty > 0:
                agent_inv = AgentInventory.query.filter_by(user_id=agent_user_id, product_id=item.product_id).first()
                if agent_inv:
                    agent_inv.current_physical_qty = max(
                        Decimal('0'),
                        safe_decimal(agent_inv.current_physical_qty) - safe_decimal(item.delivered_qty)
                    )

        db.session.commit()

        create_notification(
            user_id=order.sales_person_id,
            title='Order Delivered',
            body=f'Order #{order.id} has been delivered.',
            data={'order_id': order.id, 'status': order.status}
        )
        log_activity(user.id, 'deliver_order', 'orders', order.id, {'status': order.status}, {'status': 'delivered'}, order_id=order.id)
        return jsonify({'status': 'success', 'message': f'Order marked as {order.status}'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Deliver order error: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/orders/<int:order_id>/close', methods=['PUT'])
def close_order(order_id):
    user = request.user
    if user.role not in ['admin', 'subadmin', 'finance']:
        return jsonify({'error': 'Forbidden'}), 403

    order = Order.query.get(order_id)
    if not order:
        return jsonify({'error': 'Order not found'}), 404

    if order.status not in ['delivered', 'partially_delivered']:
        return jsonify({'error': f'Order must be delivered or partially delivered (current: {order.status})'}), 400

    if order.remaining_balance > 0:
        return jsonify({'error': 'Order has outstanding balance. Collect payment first.'}), 400

    try:
        order.status = 'closed'
        db.session.commit()
        log_activity(user.id, 'close_order', 'orders', order.id, {'status': 'delivered'}, {'status': 'closed'}, order_id=order.id)
        return jsonify({'status': 'success', 'message': 'Order closed'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Close order error: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

# ========================
# DELIVERY MANAGEMENT
# ========================
@api_bp.route('/deliveries/assign', methods=['POST'])
def assign_delivery():
    user = request.user
    if user.role not in ['captain', 'admin']:
        return jsonify({'error': 'Only captains or admins can assign deliveries'}), 403

    data = request.get_json()
    order_id = data.get('order_id')
    assigned_to_user_id = data.get('assigned_to_user_id')
    scheduled_date = data.get('scheduled_date')
    notes = data.get('notes', '')

    if not order_id or not assigned_to_user_id:
        return jsonify({'error': 'order_id and assigned_to_user_id required'}), 400

    order = Order.query.get(order_id)
    if not order:
        return jsonify({'error': 'Order not found'}), 404

    if not is_city_active(order.city_id):
        return jsonify({'error': 'City is inactive. Cannot assign delivery.'}), 400

    if order.status not in ['ready', 'packed', 'approved']:
        return jsonify({'error': f'Order status {order.status} not ready for delivery'}), 400

    existing = Delivery.query.filter_by(order_id=order_id).first()
    if existing:
        return jsonify({'error': 'Delivery already assigned for this order'}), 400

    assigned_to = User.query.get(assigned_to_user_id)
    if not assigned_to or assigned_to.role not in ['van', 'sales']:
        return jsonify({'error': 'Assigned user must be a van or sales rep'}), 400

    delivery = Delivery(
        order_id=order.id,
        assigned_to_user_id=assigned_to.id,
        assigned_by_user_id=user.id,
        status='pending',
        scheduled_date=parse_iso_date(scheduled_date) if scheduled_date else None,
        notes=notes
    )
    db.session.add(delivery)
    db.session.commit()

    order.delivery_agent_id = assigned_to.id
    db.session.commit()

    create_notification(
        user_id=assigned_to.id,
        title='New Delivery Assignment',
        body=f'Delivery for order #{order.id} to {order.customer_name} has been assigned.',
        data={'order_id': order.id, 'delivery_id': delivery.id}
    )
    log_activity(user.id, 'assign_delivery', 'deliveries', delivery.id, None, {'order_id': order_id, 'assigned_to': assigned_to.username}, order_id=order.id)
    return jsonify({'status': 'success', 'message': 'Delivery assigned', 'delivery_id': delivery.id})

@api_bp.route('/deliveries', methods=['GET'])
def list_deliveries():
    user = request.user
    if user.role not in ['captain', 'van', 'admin', 'subadmin']:
        return jsonify({'error': 'Forbidden'}), 403

    query = Delivery.query
    if user.role == 'van':
        query = query.filter_by(assigned_to_user_id=user.id)
    elif user.role == 'captain':
        order_ids = [o.id for o in Order.query.filter_by(city_id=user.city_id).all()]
        query = query.filter(Delivery.order_id.in_(order_ids))
    elif user.role in ['admin', 'subadmin'] and user.city_id:
        order_ids = [o.id for o in Order.query.filter_by(city_id=user.city_id).all()]
        query = query.filter(Delivery.order_id.in_(order_ids))

    status = request.args.get('status')
    if status:
        query = query.filter_by(status=status)

    deliveries = query.options(
        joinedload(Delivery.assigned_to),
        joinedload(Delivery.assigned_by)
    ).order_by(Delivery.created_at.desc()).all()

    order_ids = [d.order_id for d in deliveries]
    orders = Order.query.filter(Order.id.in_(order_ids)).all() if order_ids else []
    order_map = {o.id: o for o in orders}

    result = []
    for d in deliveries:
        order = order_map.get(d.order_id)
        result.append({
            'id': d.id,
            'order_id': d.order_id,
            'customer_name': order.customer_name if order else 'N/A',
            'assigned_to': d.assigned_to.username if d.assigned_to else 'Unknown',
            'assigned_by': d.assigned_by.username if d.assigned_by else 'Unknown',
            'status': d.status,
            'scheduled_date': d.scheduled_date.isoformat() if d.scheduled_date else None,
            'actual_delivery_date': d.actual_delivery_date.isoformat() if d.actual_delivery_date else None,
            'notes': d.notes,
            'created_at': d.created_at.isoformat()
        })
    return jsonify({'deliveries': result})

@api_bp.route('/deliveries/<int:delivery_id>/pickup', methods=['PUT'])
def pickup_delivery(delivery_id):
    user = request.user
    if user.role not in ['van', 'admin']:
        return jsonify({'error': 'Forbidden'}), 403

    delivery = Delivery.query.get(delivery_id)
    if not delivery:
        return jsonify({'error': 'Delivery not found'}), 404

    if delivery.status != 'pending':
        return jsonify({'error': 'Delivery already picked up or in progress'}), 400

    if user.role == 'van' and delivery.assigned_to_user_id != user.id:
        return jsonify({'error': 'You are not assigned to this delivery'}), 403

    try:
        delivery.status = 'picked_up'
        db.session.commit()
        log_activity(user.id, 'pickup_delivery', 'deliveries', delivery.id, {'status': 'pending'}, {'status': 'picked_up'}, order_id=delivery.order_id)
        return jsonify({'status': 'success', 'message': 'Delivery picked up'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Pickup delivery error: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/deliveries/<int:delivery_id>/deliver', methods=['POST'])
def deliver_delivery(delivery_id):
    user = request.user
    if user.role not in ['van', 'captain', 'admin']:
        return jsonify({'error': 'Forbidden'}), 403

    delivery = Delivery.query.get(delivery_id)
    if not delivery:
        return jsonify({'error': 'Delivery not found'}), 404

    if delivery.status not in ['picked_up', 'in_transit']:
        return jsonify({'error': 'Delivery must be picked up to complete'}), 400

    data = request.get_json() or {}
    status = data.get('status', 'delivered')
    if status not in ['delivered', 'partial', 'rejected']:
        return jsonify({'error': 'Invalid delivery status'}), 400

    try:
        items_data = data.get('items', [])
        for item_data in items_data:
            order_item_id = item_data.get('order_item_id')
            delivered_qty = item_data.get('delivered_qty', 0)
            returned_qty = item_data.get('returned_qty', 0)
            if not order_item_id:
                continue
            order_item = OrderItem.query.get(order_item_id)
            if order_item and order_item.order_id == delivery.order_id:
                if status == 'delivered':
                    order_item.delivered_qty = delivered_qty if delivered_qty else order_item.ordered_qty
                elif status == 'partial':
                    order_item.delivered_qty = delivered_qty
                    if returned_qty:
                        order_item.delivered_qty = order_item.ordered_qty - returned_qty
                elif status == 'rejected':
                    order_item.delivered_qty = 0

        if status == 'delivered':
            delivery.status = 'delivered'
        elif status == 'partial':
            delivery.status = 'partially_delivered'
        else:
            delivery.status = 'rejected'

        delivery.actual_delivery_date = datetime.utcnow()

        proof_data = data.get('proof', {})
        proof = DeliveryProof(
            delivery_id=delivery.id,
            signature_image_url=proof_data.get('signature_image_url'),
            photo_urls=proof_data.get('photo_urls', []),
            voice_url=proof_data.get('voice_url'),
            customer_feedback=proof_data.get('customer_feedback')
        )
        db.session.add(proof)

        order = Order.query.get(delivery.order_id)
        if order:
            if status == 'delivered':
                order.status = 'delivered'
            elif status == 'partial':
                order.status = 'partially_delivered'
            else:
                order.status = 'rejected'

        db.session.commit()

        create_notification(
            user_id=order.sales_person_id if order else None,
            title=f'Delivery {delivery.status}',
            body=f'Order #{delivery.order_id} has been {delivery.status}.',
            data={'delivery_id': delivery.id, 'order_id': delivery.order_id}
        )
        log_activity(user.id, f'delivery_{delivery.status}', 'deliveries', delivery.id, None, {'status': delivery.status}, order_id=delivery.order_id)
        return jsonify({'status': 'success', 'message': f'Delivery marked as {delivery.status}'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Deliver delivery error: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

# ========================
# PAYMENTS
# ========================
@api_bp.route('/payments/collect', methods=['POST'])
def collect_payment():
    user = request.user
    if user.role not in ['sales', 'van', 'captain', 'admin']:
        return jsonify({'error': 'Forbidden'}), 403

    data = request.get_json()
    order_id = data.get('order_id')
    customer_id = data.get('customer_id')
    amount = data.get('amount')
    payment_method = data.get('payment_method', 'cash')
    reference = data.get('reference')
    notes = data.get('notes')

    if not customer_id or not amount:
        return jsonify({'error': 'customer_id and amount required'}), 400

    amount = safe_decimal(amount)
    if amount <= 0:
        return jsonify({'error': 'Amount must be positive'}), 400

    customer = Customer.query.get(customer_id)
    if not customer:
        return jsonify({'error': 'Customer not found'}), 404

    order = None
    if order_id:
        order = Order.query.get(order_id)
        if order and order.customer_id != customer.id:
            return jsonify({'error': 'Order does not belong to this customer'}), 400
        if order and order.remaining_balance > 0:
            if amount > order.remaining_balance:
                return jsonify({
                    'error': f'Amount exceeds remaining balance of {order.remaining_balance}. Please adjust or apply as credit.'
                }), 400
        elif order and order.remaining_balance <= 0:
            return jsonify({'error': 'Order is already fully paid'}), 400

    try:
        payment = Payment(
            order_id=order.id if order else None,
            customer_id=customer.id,
            user_id=user.id,
            amount=amount,
            payment_method=payment_method,
            reference=reference,
            status='completed',
            notes=notes
        )
        db.session.add(payment)

        customer.outstanding_balance = max(Decimal('0.00'), customer.outstanding_balance - amount)

        if order:
            order.paid_amount += amount
            order.remaining_balance = order.net_total - order.paid_amount

        finance = FinanceTransaction(
            order_id=order.id if order else None,
            customer_id=customer.id,
            user_id=user.id,
            transaction_type='payment',
            amount=amount,
            reference=reference or f'Payment #{payment.id}',
            description=f'Payment collected by {user.username}'
        )
        db.session.add(finance)

        db.session.commit()

        create_notification(
            user_id=customer.id,
            title='Payment Received',
            body=f'A payment of {amount} has been received.',
            data={'payment_id': payment.id, 'amount': float(amount)}
        )
        log_activity(user.id, 'collect_payment', 'payments', payment.id, None, {'customer': customer.name, 'amount': str(amount)}, order_id=order.id if order else None)
        return jsonify({
            'status': 'success',
            'message': 'Payment recorded',
            'payment_id': payment.id
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Collect payment error: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/payments', methods=['GET'])
def list_payments():
    user = request.user
    if user.role not in ['admin', 'subadmin', 'finance', 'captain']:
        return jsonify({'error': 'Forbidden'}), 403

    query = Payment.query
    if user.role == 'captain':
        order_ids = [o.id for o in Order.query.filter_by(city_id=user.city_id).all()]
        query = query.filter(Payment.order_id.in_(order_ids))

    payments = query.order_by(Payment.transaction_date.desc()).all()
    result = []
    for p in payments:
        result.append({
            'id': p.id,
            'order_id': p.order_id,
            'customer_name': p.customer.name if p.customer else 'N/A',
            'amount': float(p.amount),
            'payment_method': p.payment_method,
            'collected_by': p.user.username if p.user else 'Unknown',
            'transaction_date': p.transaction_date.isoformat(),
            'status': p.status,
            'reference': p.reference
        })
    return jsonify({'payments': result})

# ========================
# CASH SETTLEMENTS
# ========================
@api_bp.route('/cash-settlements/submit', methods=['POST'])
def submit_cash_settlement():
    user = request.user
    if user.role not in ['sales', 'van', 'captain']:
        return jsonify({'error': 'Only sales/van can submit settlements'}), 403

    data = request.get_json()
    amount = data.get('amount')
    if not amount:
        return jsonify({'error': 'amount required'}), 400
    amount = Decimal(str(amount))

    settlement = CashSettlement(
        user_id=user.id,
        amount=amount,
        status='pending'
    )
    db.session.add(settlement)
    db.session.commit()
    log_activity(user.id, 'submit_settlement', 'cash_settlements', settlement.id, None, {'amount': str(amount)})
    return jsonify({'status': 'success', 'message': 'Settlement submitted', 'settlement_id': settlement.id})

@api_bp.route('/cash-settlements/<int:settlement_id>/verify', methods=['PUT'])
def verify_settlement(settlement_id):
    user = request.user
    if user.role not in ['cashier', 'admin']:
        return jsonify({'error': 'Only cashiers can verify'}), 403

    settlement = CashSettlement.query.get(settlement_id)
    if not settlement:
        return jsonify({'error': 'Settlement not found'}), 404
    if settlement.status != 'pending':
        return jsonify({'error': 'Settlement already processed'}), 400

    try:
        data = request.get_json()
        verified_amount = Decimal(str(data.get('verified_amount', settlement.amount)))
        settlement.status = 'verified'
        settlement.cashier_id = user.id
        if verified_amount != settlement.amount:
            settlement.notes = (settlement.notes or '') + f' Discrepancy: expected {settlement.amount}, verified {verified_amount}'
            settlement.amount = verified_amount
        db.session.commit()
        log_activity(user.id, 'verify_settlement', 'cash_settlements', settlement.id, {'status': 'pending'}, {'status': 'verified', 'amount': str(settlement.amount)})
        return jsonify({'status': 'success', 'message': 'Settlement verified'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Verify settlement error: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/cash-settlements/<int:settlement_id>/approve', methods=['PUT'])
def approve_settlement(settlement_id):
    user = request.user
    if user.role not in ['finance', 'admin']:
        return jsonify({'error': 'Only finance can approve'}), 403

    settlement = CashSettlement.query.get(settlement_id)
    if not settlement:
        return jsonify({'error': 'Settlement not found'}), 404
    if settlement.status != 'verified':
        return jsonify({'error': 'Settlement must be verified first'}), 400

    try:
        settlement.status = 'approved'
        settlement.finance_verifier_id = user.id
        db.session.commit()

        finance = FinanceTransaction(
            user_id=user.id,
            transaction_type='settlement',
            amount=settlement.amount,
            reference=f'Settlement #{settlement.id}',
            description=f'Cash settlement approved by {user.username}'
        )
        db.session.add(finance)
        db.session.commit()
        log_activity(user.id, 'approve_settlement', 'cash_settlements', settlement.id, {'status': 'verified'}, {'status': 'approved'})
        return jsonify({'status': 'success', 'message': 'Settlement approved'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Approve settlement error: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

# ========================
# STOCK TRANSFERS
# ========================
@api_bp.route('/stock-transfers/create', methods=['POST'])
def create_stock_transfer():
    user = request.user
    if user.role not in ['captain', 'admin']:
        return jsonify({'error': 'Only captains can create transfers'}), 403

    data = request.get_json()
    from_user_id = data.get('from_user_id')
    to_user_id = data.get('to_user_id')
    meeting_location = data.get('meeting_location')
    scheduled_time = data.get('scheduled_time')
    items = data.get('items', [])

    if not from_user_id or not to_user_id or not items:
        return jsonify({'error': 'from_user_id, to_user_id and items required'}), 400

    from_user = User.query.get(from_user_id)
    to_user = User.query.get(to_user_id)
    if not from_user or not to_user:
        return jsonify({'error': 'Users not found'}), 404

    try:
        transfer = StockTransfer(
            from_user_id=from_user.id,
            to_user_id=to_user.id,
            captain_approved_by=user.id,
            status='requested',
            meeting_location=meeting_location,
            scheduled_time=parse_iso_date(scheduled_time) if scheduled_time else None
        )
        db.session.add(transfer)
        db.session.flush()

        for item in items:
            product_id = item.get('product_id')
            qty = item.get('requested_qty', 0)
            if product_id and qty > 0:
                transfer_item = StockTransferItem(
                    stock_transfer_id=transfer.id,
                    product_id=product_id,
                    requested_qty=qty
                )
                db.session.add(transfer_item)

        db.session.commit()
        log_activity(user.id, 'create_transfer', 'stock_transfers', transfer.id, None, {'from': from_user.username, 'to': to_user.username})
        return jsonify({'status': 'success', 'message': 'Transfer created', 'transfer_id': transfer.id})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Create transfer error: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/stock-transfers/<int:transfer_id>/accept-sender', methods=['PUT'])
def accept_sender_transfer(transfer_id):
    user = request.user
    transfer = StockTransfer.query.get(transfer_id)
    if not transfer:
        return jsonify({'error': 'Transfer not found'}), 404

    if transfer.from_user_id != user.id:
        return jsonify({'error': 'You are not the sender'}), 403
    if transfer.status != 'requested':
        return jsonify({'error': 'Transfer already accepted'}), 400

    try:
        transfer.status = 'accepted_sender'
        db.session.commit()
        log_activity(user.id, 'accept_sender_transfer', 'stock_transfers', transfer.id, {'status': 'requested'}, {'status': 'accepted_sender'})
        return jsonify({'status': 'success', 'message': 'Sender accepted'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Accept sender error: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/stock-transfers/<int:transfer_id>/accept-receiver', methods=['PUT'])
def accept_receiver_transfer(transfer_id):
    transfer = StockTransfer.query.get_or_404(transfer_id)
    if transfer.status == 'completed':
        return jsonify({'status': 'error', 'message': 'Transfer already completed'}), 400

    old_status = transfer.status
    transfer.status = 'completed'
    transfer.transfer_date = datetime.now(timezone.utc)

    db.session.commit()
    log_activity(
        user_id=request.user.id,
        action='accept_receiver_transfer',
        table_name='stock_transfers',
        record_id=transfer.id,
        old_value={'status': old_status},
        new_value={'status': 'completed'}
    )

    return jsonify({'status': 'success', 'message': 'Stock transfer completed successfully'}), 200

@api_bp.route('/stock-transfers', methods=['GET'])
def list_transfers():
    user = request.user
    if user.role not in ['captain', 'admin', 'subadmin', 'storekeeper']:
        return jsonify({'error': 'Forbidden'}), 403

    query = StockTransfer.query

    if user.role == 'captain':
        city_users = [u.id for u in User.query.filter_by(city_id=user.city_id).all()]
        query = query.filter(
            (StockTransfer.from_user_id.in_(city_users)) |
            (StockTransfer.to_user_id.in_(city_users))
        )
    elif user.role == 'storekeeper' and user.city_id:
        warehouse_ids = [w.id for w in Warehouse.query.filter_by(city_id=user.city_id).all()]
        query = query.filter(
            (StockTransfer.sender_warehouse_id.in_(warehouse_ids)) |
            (StockTransfer.receiver_warehouse_id.in_(warehouse_ids))
        )
    elif user.role in ['admin', 'subadmin'] and user.city_id:
        warehouse_ids = [w.id for w in Warehouse.query.filter_by(city_id=user.city_id).all()]
        query = query.filter(
            (StockTransfer.sender_warehouse_id.in_(warehouse_ids)) |
            (StockTransfer.receiver_warehouse_id.in_(warehouse_ids))
        )

    transfers = query.options(
        joinedload(StockTransfer.from_user),
        joinedload(StockTransfer.to_user),
        joinedload(StockTransfer.captain),
        joinedload(StockTransfer.sender_warehouse),
        joinedload(StockTransfer.receiver_warehouse),
        selectinload(StockTransfer.items)
    ).order_by(StockTransfer.created_at.desc()).all()

    result = []
    for t in transfers:
        result.append({
            'id': t.id,
            'from_user': t.from_user.username if t.from_user else None,
            'to_user': t.to_user.username if t.to_user else None,
            'sender_warehouse_name': t.sender_warehouse.name if t.sender_warehouse else None,
            'receiver_warehouse_name': t.receiver_warehouse.name if t.receiver_warehouse else None,
            'status': t.status,
            'meeting_location': t.meeting_location,
            'scheduled_time': t.scheduled_time.isoformat() if t.scheduled_time else None,
            'transfer_date': t.transfer_date.isoformat() if t.transfer_date else None,
            'transfer_barcode': t.transfer_barcode,
            'items': [{
                'product_id': item.product_id,
                'product_name': item.product.name if item.product else 'N/A',
                'requested_qty': item.requested_qty,
                'transferred_qty': item.transferred_qty
            } for item in t.items]
        })
    return jsonify({'transfers': result})

@api_bp.route('/stock-transfers/<int:transfer_id>', methods=['GET'])
def get_stock_transfer(transfer_id):
    user = request.user
    if user.role not in ['captain', 'admin', 'subadmin']:
        return jsonify({'error': 'Forbidden'}), 403

    transfer = StockTransfer.query.options(
        joinedload(StockTransfer.from_user),
        joinedload(StockTransfer.to_user),
        selectinload(StockTransfer.items).joinedload(StockTransferItem.product)
    ).get(transfer_id)
    if not transfer:
        return jsonify({'error': 'Transfer not found'}), 404

    if user.role != 'admin':
        city_users = [u.id for u in User.query.filter_by(city_id=user.city_id).all()]
        if transfer.from_user_id not in city_users and transfer.to_user_id not in city_users:
            return jsonify({'error': 'Access denied'}), 403

    return jsonify({
        'id': transfer.id,
        'from_user': transfer.from_user.username if transfer.from_user else 'Unknown',
        'to_user': transfer.to_user.username if transfer.to_user else 'Unknown',
        'status': transfer.status,
        'meeting_location': transfer.meeting_location,
        'scheduled_time': transfer.scheduled_time.isoformat() if transfer.scheduled_time else None,
        'transfer_date': transfer.transfer_date.isoformat() if transfer.transfer_date else None,
        'items': [{
            'product_id': item.product_id,
            'product_name': item.product.name if item.product else 'N/A',
            'requested_qty': item.requested_qty,
            'transferred_qty': item.transferred_qty
        } for item in transfer.items]
    })

# ========================
# STOREKEEPER ENDPOINTS
# ========================
@api_bp.route('/storekeeper/dashboard', methods=['GET'])
def get_storekeeper_dashboard():
    user = request.user
    if user.role not in ['storekeeper', 'admin']:
        return jsonify({'error': 'Forbidden'}), 403

    warehouse_id = request.args.get('warehouse_id', type=int)
    if not warehouse_id:
        return jsonify({"error": "warehouse_id is required"}), 400

    try:
        today = datetime.now().date()
        total_stock = db.session.query(
            func.sum(Inventory.current_qty)
        ).filter(Inventory.warehouse_id == warehouse_id).scalar() or 0

        pending_approvals = StockTransfer.query.filter(
            (StockTransfer.sender_warehouse_id == warehouse_id) |
            (StockTransfer.receiver_warehouse_id == warehouse_id),
            StockTransfer.status.in_(['PENDING_ADMIN', 'PENDING_SENDER'])
        ).count()

        today_given = db.session.query(
            func.sum(StockTransferItem.requested_qty)
        ).join(StockTransfer).filter(
            StockTransfer.sender_warehouse_id == warehouse_id,
            StockTransfer.status == 'RECEIVED',
            func.date(StockTransfer.updated_at) == today
        ).scalar() or 0

        return jsonify({
            "warehouse_id": warehouse_id,
            "total_stock_count": int(total_stock),
            "pending_approvals_count": pending_approvals,
            "today_issued_stock_count": int(today_given)
        }), 200

    except Exception as e:
        current_app.logger.error(f"Storekeeper dashboard error: {str(e)}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500

@api_bp.route('/storekeeper/inventory/search', methods=['GET'])
def search_store_inventory():
    user = request.user
    if user.role not in ['storekeeper', 'admin']:
        return jsonify({'error': 'Forbidden'}), 403

    warehouse_id = request.args.get('warehouse_id', type=int)
    query_str = request.args.get('q', '', type=str).strip()

    if not warehouse_id:
        return jsonify({"error": "warehouse_id is required"}), 400

    try:
        query = db.session.query(
            Product.id,
            Product.name,
            Product.sku,
            Product.barcode,
            Inventory.current_qty.label('quantity')
        ).join(Inventory, Inventory.product_id == Product.id)\
         .filter(Inventory.warehouse_id == warehouse_id)

        if query_str:
            query = query.filter(
                (Product.name.ilike(f"%{query_str}%")) |
                (Product.sku.ilike(f"%{query_str}%")) |
                (Product.barcode == query_str)
            )

        results = query.all()

        items = [{
            "product_id": r.id,
            "product_name": r.name,
            "sku": r.sku,
            "barcode": r.barcode,
            "quantity_in_hand": r.quantity
        } for r in results]

        return jsonify({"count": len(items), "items": items}), 200

    except Exception as e:
        current_app.logger.error(f"Inventory search error: {str(e)}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500

@api_bp.route('/storekeeper/transfers/request', methods=['POST'])
def request_inter_store_transfer():
    user = request.user
    if user.role not in ['storekeeper', 'admin']:
        return jsonify({'error': 'Only storekeepers or admins can request stock'}), 403

    data = request.get_json()
    if not data:
        return jsonify({'error': 'JSON body required'}), 400

    sender_wh = data.get('sender_warehouse_id')
    receiver_wh = data.get('receiver_warehouse_id')
    items_data = data.get('items', [])
    requested_by_user_id = data.get('requested_by_user_id', user.id)

    if not sender_wh or not receiver_wh or not items_data:
        return jsonify({'error': 'sender_warehouse_id, receiver_warehouse_id and items are required'}), 400

    sender = Warehouse.query.get(sender_wh)
    receiver = Warehouse.query.get(receiver_wh)
    if not sender or not receiver:
        return jsonify({'error': 'One or both warehouses not found'}), 404
    if sender.id == receiver.id:
        return jsonify({'error': 'Sender and receiver warehouses must be different'}), 400

    for item in items_data:
        product_id = item.get('product_id')
        qty = item.get('quantity', 0)
        if not product_id or qty <= 0:
            return jsonify({'error': f'Invalid item: {item}'}), 400
        product = Product.query.get(product_id)
        if not product:
            return jsonify({'error': f'Product {product_id} not found'}), 404

    try:
        transfer = StockTransfer(
            sender_warehouse_id=sender_wh,
            receiver_warehouse_id=receiver_wh,
            requested_by_user_id=requested_by_user_id,
            status='PENDING_ADMIN',
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.session.add(transfer)
        db.session.flush()

        for item in items_data:
            transfer_item = StockTransferItem(
                stock_transfer_id=transfer.id,
                product_id=item['product_id'],
                requested_qty=item['quantity'],
                transferred_qty=0
            )
            db.session.add(transfer_item)

        db.session.commit()

        log_activity(user.id, 'request_stock_transfer', 'stock_transfers', transfer.id,
                     None, {'sender': sender_wh, 'receiver': receiver_wh, 'items': items_data})

        create_notification(
            user_id=user.id,
            title='Stock Transfer Requested',
            body=f'Transfer #{transfer.id} from {sender.name} to {receiver.name} has been submitted for admin approval.'
        )

        admins = User.query.filter(User.role.in_(['admin', 'subadmin']), User.is_active == True).all()
        for admin in admins:
            create_notification(
                user_id=admin.id,
                title='New Stock Transfer Request',
                body=f'Storekeeper {user.username} requests transfer #{transfer.id} from {sender.name} to {receiver.name}.',
                data={'transfer_id': transfer.id}
            )

        return jsonify({
            "message": "Transfer request sent successfully",
            "transfer_id": transfer.id,
            "status": "PENDING_ADMIN"
        }), 201

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Request transfer error: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/storekeeper/transfers/<int:transfer_id>/dispatch', methods=['POST'])
def dispatch_inter_store_transfer(transfer_id):
    user = request.user
    if user.role not in ['storekeeper', 'admin']:
        return jsonify({'error': 'Only storekeepers or admins can dispatch transfers'}), 403

    transfer = StockTransfer.query.get(transfer_id)
    if not transfer:
        return jsonify({'error': 'Transfer not found'}), 404

    if user.role != 'admin' and transfer.sender_warehouse_id != user.warehouse_id:
        return jsonify({'error': 'You are not the sender of this transfer'}), 403

    if transfer.status not in ['APPROVED_BY_ADMIN', 'PENDING_SENDER']:
        return jsonify({'error': f'Transfer cannot be dispatched in current state: {transfer.status}'}), 400

    for item in transfer.items:
        inventory = Inventory.query.filter_by(
            warehouse_id=transfer.sender_warehouse_id,
            product_id=item.product_id
        ).first()
        if not inventory or inventory.current_qty < item.requested_qty:
            return jsonify({
                'error': f'Insufficient stock for product {item.product_id} in sender warehouse. Available: {inventory.current_qty if inventory else 0}, requested: {item.requested_qty}'
            }), 400

    try:
        unique_barcode = f"TRF-{uuid.uuid4().hex[:8].upper()}"
        transfer.transfer_barcode = unique_barcode
        transfer.status = 'DISPATCHED'
        transfer.updated_at = datetime.utcnow()
        db.session.commit()

        log_activity(user.id, 'dispatch_transfer', 'stock_transfers', transfer.id,
                     {'status': 'APPROVED_BY_ADMIN'}, {'status': 'DISPATCHED', 'barcode': unique_barcode})

        create_notification(
            user_id=transfer.requested_by_user_id or user.id,
            title='Stock Dispatched',
            body=f'Transfer #{transfer.id} has been dispatched. Barcode: {unique_barcode}'
        )

        return jsonify({
            "message": "Stock dispatched. Barcode generated.",
            "transfer_id": transfer.id,
            "transfer_barcode": unique_barcode
        }), 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Dispatch transfer error: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/storekeeper/transfers/scan-receive', methods=['POST'])
def scan_and_receive_stock():
    user = request.user
    if user.role not in ['storekeeper', 'admin']:
        return jsonify({'error': 'Only storekeepers or admins can receive stock'}), 403

    data = request.get_json()
    if not data:
        return jsonify({'error': 'JSON body required'}), 400

    barcode = data.get('barcode', '').strip()
    receiver_wh_id = data.get('receiver_warehouse_id')

    if not barcode or not receiver_wh_id:
        return jsonify({'error': 'barcode and receiver_warehouse_id required'}), 400

    transfer = StockTransfer.query.filter_by(
        transfer_barcode=barcode,
        status='DISPATCHED'
    ).first()

    if not transfer:
        return jsonify({'error': 'Invalid barcode or transfer not in DISPATCHED state'}), 404

    if transfer.receiver_warehouse_id != receiver_wh_id:
        return jsonify({'error': 'This transfer is intended for a different store'}), 403

    if user.role != 'admin' and user.warehouse_id != receiver_wh_id:
        return jsonify({'error': 'You are not authorized to receive for this warehouse'}), 403

    try:
        for item in transfer.items:
            donor_inv = Inventory.query.filter_by(
                warehouse_id=transfer.sender_warehouse_id,
                product_id=item.product_id
            ).first()
            if donor_inv:
                if donor_inv.current_qty < item.requested_qty:
                    raise Exception(f"Insufficient stock in donor warehouse for product {item.product_id}")
                donor_inv.current_qty -= item.requested_qty
            else:
                raise Exception(f"Product {item.product_id} not found in donor warehouse")

            receiver_inv = Inventory.query.filter_by(
                warehouse_id=transfer.receiver_warehouse_id,
                product_id=item.product_id
            ).first()

            if receiver_inv:
                receiver_inv.current_qty += item.requested_qty
            else:
                receiver_inv = Inventory(
                    warehouse_id=transfer.receiver_warehouse_id,
                    product_id=item.product_id,
                    current_qty=item.requested_qty,
                    reserved_qty=0
                )
                db.session.add(receiver_inv)

            item.transferred_qty = item.requested_qty
            item.scan_confirm_time = datetime.utcnow()

        transfer.status = 'RECEIVED'
        transfer.updated_at = datetime.utcnow()
        db.session.commit()

        log_activity(user.id, 'receive_transfer', 'stock_transfers', transfer.id,
                     {'status': 'DISPATCHED'}, {'status': 'RECEIVED'})

        create_notification(
            user_id=transfer.requested_by_user_id or user.id,
            title='Transfer Received',
            body=f'Transfer #{transfer.id} has been successfully received.'
        )

        return jsonify({
            "message": "Barcode verified! Stock has been automatically added to your store.",
            "transfer_id": transfer.id
        }), 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Receive transfer error: {str(e)}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500

# ========================
# RETURNS
# ========================
@api_bp.route('/returns', methods=['POST'])
def create_return():
    user = request.user
    if user.role not in ['sales', 'van', 'captain', 'admin']:
        return jsonify({'error': 'Forbidden'}), 403

    data = request.get_json()
    order_id = data.get('order_id')
    product_id = data.get('product_id')
    return_type = data.get('return_type')
    quantity = data.get('quantity')
    reason = data.get('reason')

    if not product_id or not return_type or not quantity:
        return jsonify({'error': 'product_id, return_type, quantity required'}), 400

    product = Product.query.get(product_id)
    if not product:
        return jsonify({'error': 'Product not found'}), 404

    try:
        ret = Return(
            order_id=order_id,
            product_id=product.id,
            user_id=user.id,
            return_type=return_type,
            quantity=quantity,
            reason=reason,
            status='pending'
        )
        db.session.add(ret)
        db.session.commit()
        log_activity(user.id, 'create_return', 'returns', ret.id, None, {'product': product.name, 'qty': quantity})
        return jsonify({'status': 'success', 'message': 'Return created', 'return_id': ret.id})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Create return error: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/returns/<int:return_id>/approve', methods=['PUT'])
def approve_return(return_id):
    user = request.user
    if user.role not in ['captain', 'admin']:
        return jsonify({'error': 'Only captains/admins can approve returns'}), 403

    ret = Return.query.get(return_id)
    if not ret:
        return jsonify({'error': 'Return not found'}), 404
    if ret.status != 'pending':
        return jsonify({'error': 'Return already processed'}), 400

    try:
        ret.status = 'approved'
        ret.approved_by = user.id
        ret.approved_at = datetime.utcnow()

        if ret.return_type in ['customer_return', 'damaged', 'expired']:
            agent_inv = AgentInventory.query.filter_by(user_id=ret.user_id, product_id=ret.product_id).first()
            if agent_inv:
                agent_inv.current_physical_qty += ret.quantity
            else:
                agent_inv = AgentInventory(user_id=ret.user_id, product_id=ret.product_id, current_physical_qty=ret.quantity)
                db.session.add(agent_inv)

        db.session.commit()
        log_activity(user.id, 'approve_return', 'returns', ret.id, {'status': 'pending'}, {'status': 'approved'})
        return jsonify({'status': 'success', 'message': 'Return approved'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Approve return error: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/returns/<int:return_id>/reject', methods=['PUT'])
def reject_return(return_id):
    user = request.user
    if user.role not in ['captain', 'admin']:
        return jsonify({'error': 'Only captains/admins can reject returns'}), 403

    ret = Return.query.get(return_id)
    if not ret:
        return jsonify({'error': 'Return not found'}), 404
    if ret.status != 'pending':
        return jsonify({'error': 'Return already processed'}), 400

    try:
        data = request.get_json()
        reason = data.get('reason', 'No reason provided')
        ret.status = 'rejected'
        ret.reason = (ret.reason or '') + f' Rejected: {reason}'
        db.session.commit()
        log_activity(user.id, 'reject_return', 'returns', ret.id, {'status': 'pending'}, {'status': 'rejected', 'reason': reason})
        return jsonify({'status': 'success', 'message': 'Return rejected'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Reject return error: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/returns', methods=['GET'])
def list_returns():
    user = request.user
    if user.role not in ['captain', 'admin', 'subadmin']:
        return jsonify({'error': 'Forbidden'}), 403

    query = Return.query
    if user.role == 'captain':
        order_ids = [o.id for o in Order.query.filter_by(city_id=user.city_id).all()]
        query = query.filter(Return.order_id.in_(order_ids))

    returns = query.options(
        joinedload(Return.product),
        joinedload(Return.user),
        joinedload(Return.approver)
    ).order_by(Return.created_at.desc()).all()
    result = []
    for r in returns:
        result.append({
            'id': r.id,
            'order_id': r.order_id,
            'product_id': r.product_id,
            'product_name': r.product.name if r.product else 'N/A',
            'user': r.user.username if r.user else 'Unknown',
            'return_type': r.return_type,
            'quantity': r.quantity,
            'reason': r.reason,
            'status': r.status,
            'created_at': r.created_at.isoformat()
        })
    return jsonify({'returns': result})

# ========================
# PRICE LISTS
# ========================
@api_bp.route('/price-lists', methods=['GET'])
def list_price_lists():
    user = request.user
    if user.role not in ['admin', 'subadmin', 'sales']:
        return jsonify({'error': 'Forbidden'}), 403

    query = PriceList.query.filter_by(is_active=True)
    if user.role == 'sales' and user.city_id:
        query = query.filter(or_(PriceList.city_id == user.city_id, PriceList.city_id.is_(None)))

    price_lists = query.options(
        joinedload(PriceList.city),
        selectinload(PriceList.items).joinedload(PriceListItem.product)
    ).all()
    result = []
    for pl in price_lists:
        result.append({
            'id': pl.id,
            'name': pl.name,
            'city_id': pl.city_id,
            'city_name': pl.city.name if pl.city else None,
            'effective_from': pl.effective_from.isoformat() if pl.effective_from else None,
            'effective_to': pl.effective_to.isoformat() if pl.effective_to else None,
            'items': [{
                'product_id': item.product_id,
                'product_name': item.product.name if item.product else 'N/A',
                'unit_price': float(item.unit_price),
                'discount_percent': float(item.discount_percent)
            } for item in pl.items]
        })
    return jsonify({'price_lists': result})

@api_bp.route('/price-lists', methods=['POST'])
def create_price_list():
    user = request.user
    if user.role not in ['admin', 'subadmin']:
        return jsonify({'error': 'Forbidden'}), 403

    data = request.get_json()
    name = data.get('name')
    city_id = data.get('city_id')
    if city_id == '':
        city_id = None

    effective_from = data.get('effective_from')
    effective_to = data.get('effective_to')
    items = data.get('items', [])

    if not name or not items:
        return jsonify({'error': 'name and items required'}), 400

    if not City.query.first():
        default_city = City(name='Default City', is_active=True)
        db.session.add(default_city)
        db.session.commit()
        if city_id is None:
            city_id = default_city.id

    price_list = PriceList(
        name=name,
        city_id=city_id,
        effective_from=parse_iso_date(effective_from) if effective_from else None,
        effective_to=parse_iso_date(effective_to) if effective_to else None,
        is_active=True
    )
    db.session.add(price_list)
    db.session.flush()

    for item in items:
        product_id = item.get('product_id')
        unit_price = item.get('unit_price')
        discount = item.get('discount_percent', 0)
        if product_id and unit_price:
            product = Product.query.get(product_id)
            if not product:
                return jsonify({'error': f'Product with id {product_id} not found'}), 400
            pl_item = PriceListItem(
                price_list_id=price_list.id,
                product_id=product_id,
                unit_price=Decimal(str(unit_price)),
                discount_percent=Decimal(str(discount))
            )
            db.session.add(pl_item)

    db.session.commit()
    log_activity(user.id, 'create_price_list', 'price_lists', price_list.id, None, {'name': name})
    return jsonify({'status': 'success', 'message': 'Price list created', 'id': price_list.id})

@api_bp.route('/price-lists/<int:price_list_id>', methods=['DELETE'])
def delete_price_list(price_list_id):
    user = request.user
    if user.role not in ['admin', 'subadmin']:
        return jsonify({'error': 'Forbidden'}), 403

    price_list = PriceList.query.get(price_list_id)
    if not price_list:
        return jsonify({'error': 'Price list not found'}), 404
    price_list.is_active = False
    db.session.commit()
    log_activity(user.id, 'delete_price_list', 'price_lists', price_list_id, {'is_active': True}, {'is_active': False})
    return jsonify({'status': 'success', 'message': 'Price list deactivated'})

@api_bp.route('/customers/<int:customer_id>/price-list', methods=['POST'])
def assign_price_list(customer_id):
    user = request.user
    if user.role not in ['admin', 'subadmin']:
        return jsonify({'error': 'Forbidden'}), 403

    data = request.get_json()
    price_list_id = data.get('price_list_id')
    if not price_list_id:
        return jsonify({'error': 'price_list_id required'}), 400

    customer = Customer.query.get(customer_id)
    if not customer:
        return jsonify({'error': 'Customer not found'}), 404
    price_list = PriceList.query.get(price_list_id)
    if not price_list:
        return jsonify({'error': 'Price list not found'}), 404

    CustomerPriceList.query.filter_by(customer_id=customer.id).delete()
    cp = CustomerPriceList(customer_id=customer.id, price_list_id=price_list.id)
    db.session.add(cp)
    db.session.commit()
    log_activity(user.id, 'assign_price_list', 'customer_price_lists', cp.id, None, {'customer': customer.name, 'price_list': price_list.name})
    return jsonify({'status': 'success', 'message': 'Price list assigned'})

# ========================
# CREDIT LIMIT
# ========================
@api_bp.route('/customers/credit', methods=['GET'])
def list_customer_credit():
    user = request.user
    if user.role not in ['admin', 'subadmin', 'finance', 'captain']:
        return jsonify({'error': 'Forbidden'}), 403

    customers = Customer.query.filter_by(is_active=True).all()
    if user.role == 'captain' and user.city_id:
        customers = [c for c in customers if c.city_id == user.city_id]

    result = []
    for c in customers:
        result.append({
            'id': c.id,
            'name': c.name,
            'outstanding_balance': float(c.outstanding_balance),
            'credit_limit': float(c.credit_limit)
        })
    return jsonify({'customers': result})

@api_bp.route('/customers/<int:customer_id>/credit-limit', methods=['PUT'])
def update_credit_limit(customer_id):
    user = request.user
    if user.role not in ['admin', 'subadmin']:
        return jsonify({'error': 'Forbidden'}), 403

    data = request.get_json()
    new_limit = data.get('credit_limit')
    if new_limit is None:
        return jsonify({'error': 'credit_limit required'}), 400

    customer = Customer.query.get(customer_id)
    if not customer:
        return jsonify({'error': 'Customer not found'}), 404

    old_limit = customer.credit_limit
    customer.credit_limit = Decimal(str(new_limit))
    db.session.commit()
    log_activity(user.id, 'update_credit_limit', 'customers', customer.id, {'credit_limit': str(old_limit)}, {'credit_limit': str(new_limit)})
    return jsonify({'status': 'success', 'message': 'Credit limit updated'})

# ========================
# REPORTS
# ========================
@api_bp.route('/reports/sales', methods=['GET'])
def sales_report():
    user = request.user
    if user.role not in ['admin', 'subadmin', 'finance', 'captain']:
        return jsonify({'error': 'Forbidden'}), 403

    from_date = request.args.get('from')
    to_date = request.args.get('to')
    group_by = request.args.get('group_by', 'day')

    query = Order.query
    if from_date:
        query = query.filter(Order.created_at >= from_date)
    if to_date:
        query = query.filter(Order.created_at <= to_date)
    if user.role == 'captain' and user.city_id:
        query = query.filter_by(city_id=user.city_id)

    orders = query.all()
    from collections import defaultdict
    groups = defaultdict(lambda: {'total': Decimal('0.00'), 'count': 0})
    for o in orders:
        if group_by == 'day':
            key = o.created_at.strftime('%Y-%m-%d')
        elif group_by == 'week':
            key = o.created_at.strftime('%Y-%W')
        else:
            key = o.created_at.strftime('%Y-%m')
        groups[key]['total'] += o.net_total
        groups[key]['count'] += 1

    report = []
    for key, val in groups.items():
        report.append({
            'period': key,
            'total_sales': float(val['total']),
            'order_count': val['count'],
            'avg_order_value': float(val['total'] / val['count']) if val['count'] > 0 else 0
        })
    report.sort(key=lambda x: x['period'])
    return jsonify({'report': report})

@api_bp.route('/reports/inventory', methods=['GET'])
def inventory_report():
    user = request.user
    if user.role not in ['admin', 'subadmin', 'storekeeper']:
        return jsonify({'error': 'Forbidden'}), 403

    products = Product.query.filter_by(is_active=True).all()
    result = []
    for p in products:
        total_qty = sum(inv.current_qty for inv in p.inventory_items)
        result.append({
            'id': p.id,
            'name': p.name,
            'current_warehouse_qty': total_qty,
            'reserved_warehouse_qty': sum(inv.reserved_qty for inv in p.inventory_items)
        })
    return jsonify({'products': result})

@api_bp.route('/reports/delivery-performance', methods=['GET'])
def delivery_performance():
    user = request.user
    if user.role not in ['admin', 'subadmin', 'captain']:
        return jsonify({'error': 'Forbidden'}), 403

    query = Delivery.query
    if user.role == 'captain' and user.city_id:
        order_ids = [o.id for o in Order.query.filter_by(city_id=user.city_id).all()]
        query = query.filter(Delivery.order_id.in_(order_ids))

    deliveries = query.all()
    total = len(deliveries)

    on_time = sum(1 for d in deliveries
                  if d.status == 'delivered'
                  and (not d.scheduled_date or d.actual_delivery_date <= d.scheduled_date))

    delayed = sum(1 for d in deliveries
                  if d.status == 'delivered'
                  and d.scheduled_date
                  and d.actual_delivery_date > d.scheduled_date)

    failed = sum(1 for d in deliveries if d.status in ['rejected', 'partially_delivered'])

    return jsonify({
        'total': total,
        'on_time': on_time,
        'delayed': delayed,
        'failed': failed
    })

# ========================
# AUDIT LOGS
# ========================
@api_bp.route('/audit-logs', methods=['GET'])
def audit_logs():
    user = request.user
    if user.role not in ['admin', 'subadmin', 'captain']:
        return jsonify({'error': 'Forbidden'}), 403

    query = ActivityLog.query
    action = request.args.get('action')
    if action:
        query = query.filter_by(action=action)
    from_date = request.args.get('from')
    to_date = request.args.get('to')
    if from_date:
        query = query.filter(ActivityLog.timestamp >= from_date)
    if to_date:
        query = query.filter(ActivityLog.timestamp <= to_date)

    if user.role == 'captain' and user.city_id:
        order_ids = [o.id for o in Order.query.filter_by(city_id=user.city_id).all()]
        query = query.filter(ActivityLog.order_id.in_(order_ids))

    limit = request.args.get('limit', 100, type=int)
    offset = request.args.get('offset', 0, type=int)
    logs = query.options(
        joinedload(ActivityLog.user)
    ).order_by(ActivityLog.timestamp.desc()).offset(offset).limit(limit).all()
    result = []
    for log in logs:
        result.append({
            'id': log.id,
            'user_id': log.user_id,
            'username': log.user.username if log.user else 'Unknown',
            'action': log.action,
            'table_name': log.table_name,
            'record_id': log.record_id,
            'old_value': log.old_value,
            'new_value': log.new_value,
            'order_id': log.order_id,
            'timestamp': log.timestamp.isoformat()
        })
    return jsonify({'logs': result, 'total': query.count()})

# ========================
# CAPTAIN PENDING ORDERS
# ========================
@api_bp.route('/captain/pending-orders', methods=['GET'])
def captain_pending_orders():
    user = request.user
    if user.role not in ['captain', 'admin']:
        return jsonify({'error': 'Forbidden'}), 403

    query = Order.query.filter_by(status='pending')
    if user.role == 'captain':
        query = query.filter_by(city_id=user.city_id)

    orders = query.options(
        joinedload(Order.sales_person),
        selectinload(Order.items),
        selectinload(Order.media)
    ).order_by(Order.created_at.asc()).all()
    result = []
    for o in orders:
        result.append({
            'id': o.id,
            'customer_name': o.customer_name,
            'customer_phone': o.customer_phone,
            'shipping_address': o.shipping_address,
            'latitude': float(o.latitude) if o.latitude else None,
            'longitude': float(o.longitude) if o.longitude else None,
            'net_total': float(o.net_total),
            'sales_person': o.sales_person.username if o.sales_person else None,
            'created_at': o.created_at.isoformat(),
            'items': [{
                'product_name': item.product_name,
                'ordered_qty': item.ordered_qty,
                'unit_price': float(item.unit_price)
            } for item in o.items],
            'media': [{
                'media_type': m.media_type,
                'file_url': m.file_url
            } for m in o.media]
        })
    return jsonify({'orders': result})

# ========================
# PRODUCT MANAGEMENT
# ========================
@api_bp.route('/products/search', methods=['GET'])
def search_products():
    user = request.user
    if user.role not in ['admin', 'subadmin', 'storekeeper', 'captain', 'sales']:
        return jsonify({'error': 'Forbidden'}), 403

    query = request.args.get('q', '')
    barcode = request.args.get('barcode')
    limit = min(int(request.args.get('limit', 20)), 200)

    product_query = Product.query.filter_by(is_active=True)
    if user.role != 'admin' and user.city_id:
        product_query = product_query.filter_by(city_id=user.city_id)

    if barcode:
        product_query = product_query.filter(Product.barcode == barcode)
    elif query:
        product_query = product_query.filter(
            or_(
                Product.name.ilike(f'%{query}%'),
                Product.sku.ilike(f'%{query}%'),
                Product.barcode.ilike(f'%{query}%')
            )
        )
    else:
        product_query = product_query.limit(limit)

    products = product_query.limit(limit).all()
    result = [{
        'id': p.id,
        'name': p.name,
        'sku': p.sku,
        'barcode': p.barcode,
        'unit_price': float(p.unit_price),
        'image_url': p.image_url,
        'current_warehouse_qty': p.total_current_qty,
        'reserved_warehouse_qty': p.total_reserved_qty
    } for p in products]
    return jsonify({'products': result})

@api_bp.route('/products', methods=['POST'])
def create_product():
    user = request.user
    if user.role not in ['admin', 'subadmin']:
        return jsonify({'error': 'Only admins or subadmins can create products'}), 403

    data = request.get_json()
    if not data:
        return jsonify({'error': 'JSON body required'}), 400

    required = ['name', 'unit_price', 'city_id']
    for field in required:
        if field not in data:
            return jsonify({'error': f'Missing required field: {field}'}), 400

    name = data.get('name').strip()
    if not name:
        return jsonify({'error': 'Product name cannot be empty'}), 400

    try:
        unit_price = Decimal(str(data['unit_price']))
        if unit_price < 0:
            return jsonify({'error': 'Unit price must be non-negative'}), 400
    except:
        return jsonify({'error': 'Invalid unit_price'}), 400

    city_id = data.get('city_id')
    if not is_city_active(city_id):
        return jsonify({'error': 'Invalid or inactive city'}), 400

    sku = data.get('sku', '').strip() or None
    barcode = data.get('barcode', '').strip() or None
    if sku and Product.query.filter_by(sku=sku).first():
        return jsonify({'error': 'SKU already exists'}), 400
    if barcode and Product.query.filter_by(barcode=barcode).first():
        return jsonify({'error': 'Barcode already exists'}), 400

    product = Product(
        name=name,
        sku=sku,
        barcode=barcode,
        description=data.get('description', '').strip() or None,
        unit_price=unit_price,
        tax_rate=Decimal(str(data.get('tax_rate', 0))),
        category=data.get('category', '').strip() or None,
        image_url=data.get('image_url', '').strip() or None,
        city_id=city_id,
        is_active=data.get('is_active', True)
    )
    db.session.add(product)
    db.session.commit()

    log_activity(user.id, 'create_product', 'products', product.id,
                 None, {'name': product.name, 'sku': product.sku, 'barcode': product.barcode})
    create_notification(
        user_id=user.id,
        title='Product Created',
        body=f'Product "{product.name}" has been added to the system.'
    )

    return jsonify({
        'status': 'success',
        'id': product.id,
        'message': 'Product created successfully'
    })

@api_bp.route('/products', methods=['GET'])
def list_products():
    user = request.user
    if user.role not in ['admin', 'subadmin']:
        return jsonify({'error': 'Forbidden'}), 403

    city_id = request.args.get('city_id', type=int)
    is_active = request.args.get('is_active')
    if is_active is not None:
        is_active = is_active.lower() == 'true'
    q = request.args.get('q', '').strip()
    limit = min(int(request.args.get('limit', 20)), 100)
    offset = int(request.args.get('offset', 0))

    query = Product.query
    if city_id is not None:
        query = query.filter_by(city_id=city_id)

    if is_active is None:
        is_active = True
    query = query.filter_by(is_active=is_active)

    if q:
        query = query.filter(
            or_(
                Product.name.ilike(f'%{q}%'),
                Product.sku.ilike(f'%{q}%'),
                Product.barcode.ilike(f'%{q}%')
            )
        )

    total = query.count()
    products = query.options(
        joinedload(Product.city)
    ).order_by(Product.id.desc()).offset(offset).limit(limit).all()

    result = []
    for p in products:
        result.append({
            'id': p.id,
            'name': p.name,
            'sku': p.sku,
            'barcode': p.barcode,
            'description': p.description,
            'unit_price': float(p.unit_price),
            'tax_rate': float(p.tax_rate),
            'current_warehouse_qty': p.total_current_qty,
            'reserved_warehouse_qty': p.total_reserved_qty,
            'category': p.category,
            'image_url': p.image_url,
            'city_id': p.city_id,
            'city_name': p.city.name if p.city else None,
            'is_active': p.is_active,
            'created_at': p.created_at.isoformat(),
            'updated_at': p.updated_at.isoformat()
        })

    return jsonify({
        'products': result,
        'total': total,
        'limit': limit,
        'offset': offset
    })

@api_bp.route('/products/<int:product_id>', methods=['PUT'])
def update_product(product_id):
    user = request.user
    if user.role not in ['admin', 'subadmin']:
        return jsonify({'error': 'Only admins or subadmins can update products'}), 403

    product = Product.query.get(product_id)
    if not product:
        return jsonify({'error': 'Product not found'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'error': 'JSON body required'}), 400

    old_values = {
        'name': product.name,
        'sku': product.sku,
        'barcode': product.barcode,
        'unit_price': float(product.unit_price),
        'tax_rate': float(product.tax_rate),
        'description': product.description,
        'category': product.category,
        'image_url': product.image_url,
        'city_id': product.city_id,
        'is_active': product.is_active
    }

    if 'name' in data:
        name = data['name'].strip()
        if not name:
            return jsonify({'error': 'Product name cannot be empty'}), 400
        product.name = name

    if 'sku' in data:
        sku = data['sku'].strip() or None
        if sku != product.sku and sku and Product.query.filter_by(sku=sku).first():
            return jsonify({'error': 'SKU already exists'}), 400
        product.sku = sku

    if 'barcode' in data:
        barcode = data['barcode'].strip() or None
        if barcode != product.barcode and barcode and Product.query.filter_by(barcode=barcode).first():
            return jsonify({'error': 'Barcode already exists'}), 400
        product.barcode = barcode

    if 'unit_price' in data:
        try:
            unit_price = Decimal(str(data['unit_price']))
            if unit_price < 0:
                return jsonify({'error': 'Unit price must be non-negative'}), 400
            product.unit_price = unit_price
        except:
            return jsonify({'error': 'Invalid unit_price'}), 400

    if 'tax_rate' in data:
        try:
            tax_rate = Decimal(str(data['tax_rate']))
            if tax_rate < 0:
                return jsonify({'error': 'Tax rate must be non-negative'}), 400
            product.tax_rate = tax_rate
        except:
            return jsonify({'error': 'Invalid tax_rate'}), 400

    if 'description' in data:
        product.description = data['description'].strip() or None

    if 'category' in data:
        product.category = data['category'].strip() or None

    if 'image_url' in data:
        product.image_url = data['image_url'].strip() or None

    if 'city_id' in data:
        city_id = data['city_id']
        if not is_city_active(city_id):
            return jsonify({'error': 'Invalid or inactive city'}), 400
        product.city_id = city_id

    if 'is_active' in data:
        product.is_active = data['is_active']

    product.updated_at = datetime.utcnow()
    db.session.commit()

    log_activity(user.id, 'update_product', 'products', product.id,
                 old_values, {'name': product.name, 'sku': product.sku, 'barcode': product.barcode})
    create_notification(
        user_id=user.id,
        title='Product Updated',
        body=f'Product "{product.name}" has been updated.'
    )

    return jsonify({
        'status': 'success',
        'message': 'Product updated successfully'
    })

@api_bp.route('/products/<int:product_id>', methods=['DELETE'])
def delete_product(product_id):
    user = request.user
    if user.role not in ['admin', 'subadmin']:
        return jsonify({'error': 'Only admins or subadmins can delete products'}), 403

    product = Product.query.get(product_id)
    if not product:
        return jsonify({'error': 'Product not found'}), 404

    product.is_active = False
    product.updated_at = datetime.utcnow()
    db.session.commit()

    log_activity(user.id, 'delete_product', 'products', product.id,
                 {'is_active': True}, {'is_active': False})

    return jsonify({
        'status': 'success',
        'message': 'Product deactivated successfully'
    })

# ========================
# FINANCE TRANSACTIONS
# ========================
@api_bp.route('/finance/transactions', methods=['GET'])
def list_finance_transactions():
    user = request.user
    if user.role not in ['admin', 'subadmin', 'finance', 'captain']:
        return jsonify({'error': 'Forbidden'}), 403

    query = FinanceTransaction.query
    if user.role == 'captain':
        order_ids = [o.id for o in Order.query.filter_by(city_id=user.city_id).all()]
        query = query.filter(FinanceTransaction.order_id.in_(order_ids))

    transactions = query.order_by(FinanceTransaction.transaction_date.desc()).limit(100).all()
    result = []
    for t in transactions:
        result.append({
            'id': t.id,
            'transaction_type': t.transaction_type,
            'amount': float(t.amount),
            'reference': t.reference,
            'customer_name': t.customer.name if t.customer else None,
            'username': t.user.username if t.user else None,
            'transaction_date': t.transaction_date.isoformat()
        })
    return jsonify({'transactions': result})

# =============================================================================
# End of api.py
# =============================================================================
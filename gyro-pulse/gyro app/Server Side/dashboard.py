from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, send_file, current_app
from flask_login import login_required, current_user
from sqlalchemy import func
from models import (
    db, User, Message, UserSyncStatus, Order, OrderItem, Customer, Product, City,
    RoleApiKey, Setting, Delivery, Payment, CashSettlement, StockTransfer, StockTransferItem,
    FinanceTransaction, Return, AgentInventory, Warehouse, Inventory, InventoryTransaction,
    ApiKey, TokenPool, ServerConfig, Media, DeviceCommand, ActivityLog
)
from utils import generate_api_key, save_uploaded_file, serve_gpc_file, generate_gpc_file, get_master_secret
from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta
import os
import json
import traceback
from backup import export_backup_zip, import_backup_from_zip, get_backup_dir, list_backup_files, restore_database_from_sql
from decimal import Decimal
from sqlalchemy import or_

dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')

@dashboard_bp.before_request
@login_required
def check_role():
    if current_user.role not in ['admin', 'subadmin', 'captain', 'storekeeper']:
        flash('Access denied')
        return redirect(url_for('auth.logout'))

# ---------- Dashboard Home ----------
@dashboard_bp.route('/')
@login_required
def index():
    return render_template("operations.html")

@dashboard_bp.route("/legacy")
@login_required
def legacy_dashboard():
    role = current_user.role
    if role == 'admin':
        return render_template('admin_dashboard.html')
    elif role == 'subadmin':
        return render_template('subadmin_dashboard.html')
    elif role == 'captain':
        return render_template('captain_dashboard.html')
    elif role == 'storekeeper':
        return render_template('storekeeper_dashboard.html')
    else:
        flash('Access denied')
        return redirect(url_for('auth.logout'))

# ---------- API: Stats ----------
@dashboard_bp.route('/api/stats')
@login_required
def api_stats():
    if current_user.role not in ['admin', 'subadmin']:
        return jsonify({'error': 'Forbidden'}), 403

    total = Message.query.count()
    text_count = Message.query.filter_by(type='data').count()
    media_count = Message.query.filter(Message.type.in_(['video', 'audio', 'picture'])).count()
    location_count = Message.query.filter(Message.latitude.isnot(None)).count()
    today = Message.query.filter(func.date(Message.created_at) == datetime.utcnow().date()).count()

    daily = []
    for i in range(6, -1, -1):
        day = datetime.utcnow().date() - timedelta(days=i)
        count = Message.query.filter(func.date(Message.created_at) == day).count()
        daily.append({'date': day.isoformat(), 'count': count})

    return jsonify({
        'total': total,
        'text': text_count,
        'media': media_count,
        'location': location_count,
        'today': today,
        'daily': daily
    })

# ---------- API: Messages ----------
@dashboard_bp.route('/api/messages')
@login_required
def api_messages():
    if current_user.role not in ['admin', 'subadmin']:
        return jsonify({'error': 'Forbidden'}), 403

    limit = min(int(request.args.get('limit', 20)), 100)
    offset = int(request.args.get('offset', 0))
    msg_type = request.args.get('type')
    from_date = request.args.get('from')
    to_date = request.args.get('to')

    query = Message.query
    if msg_type:
        query = query.filter_by(type=msg_type)
    if from_date:
        query = query.filter(func.date(Message.created_at) >= from_date)
    if to_date:
        query = query.filter(func.date(Message.created_at) <= to_date)

    total = query.count()
    messages = query.order_by(Message.created_at.desc()).offset(offset).limit(limit).all()

    result = []
    for m in messages:
        user = User.query.get(m.user_id)
        result.append({
            'id': m.id,
            'type': m.type,
            'content': m.content,
            'media_url': m.media_url,
            'latitude': float(m.latitude) if m.latitude else None,
            'longitude': float(m.longitude) if m.longitude else None,
            'username': user.username if user else 'Unknown',
            'created_at': m.created_at.isoformat()
        })

    return jsonify({'data': result, 'total': total})

@dashboard_bp.route('/api/messages/<int:message_id>')
@login_required
def api_message_detail(message_id):
    if current_user.role not in ['admin', 'subadmin']:
        return jsonify({'error': 'Forbidden'}), 403

    msg = Message.query.get(message_id)
    if not msg:
        return jsonify({'error': 'Not found'}), 404

    user = User.query.get(msg.user_id)
    return jsonify({
        'id': msg.id,
        'type': msg.type,
        'content': msg.content,
        'media_url': msg.media_url,
        'latitude': float(msg.latitude) if msg.latitude else None,
        'longitude': float(msg.longitude) if msg.longitude else None,
        'username': user.username if user else 'Unknown',
        'created_at': msg.created_at.isoformat()
    })

# ---------- API: Users ----------
@dashboard_bp.route('/api/users')
@login_required
def api_users():
    if current_user.role not in ['admin', 'subadmin']:
        return jsonify({'error': 'Forbidden'}), 403

    users = User.query.filter_by(is_active=True).all()
    result = []
    for u in users:
        city_name = u.city.name if u.city else None
        result.append({
            'id': u.id,
            'username': u.username,
            'role': u.role,
            'city_name': city_name,
            'is_active': u.is_active,
            'created_at': u.created_at.isoformat()
        })
    return jsonify({'data': result})

@dashboard_bp.route('/api/users', methods=['POST'])
@login_required
def create_user():
    if current_user.role not in ['admin', 'subadmin']:
        return jsonify({'error': 'Forbidden'}), 403

    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    role = data.get('role')
    city_id = data.get('city_id')

    if not username or not password or not role:
        return jsonify({'error': 'Username, password, and role required'}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({'error': 'Username already exists'}), 400

    user = User(
        username=username,
        password_hash=generate_password_hash(password),
        role=role,
        city_id=city_id,
        created_by=current_user.id,
        is_active=True
    )
    db.session.add(user)
    db.session.commit()

    if role in ['sales', 'captain', 'van', 'storekeeper']:
        role_key = RoleApiKey.query.filter_by(role=role).first()
        if not role_key:
            import uuid
            new_key = uuid.uuid4().hex
            role_key = RoleApiKey(role=role, api_key=new_key)
            db.session.add(role_key)
            db.session.commit()

    return jsonify({
        'status': 'success',
        'user_id': user.id,
        'message': 'User created successfully'
    })

@dashboard_bp.route('/api/users/<int:user_id>', methods=['DELETE'])
@login_required
def delete_user(user_id):
    if current_user.role != 'admin':
        return jsonify({'error': 'Only admin can delete users'}), 403

    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    if user.id == current_user.id:
        return jsonify({'error': 'Cannot deactivate yourself'}), 400

    user.is_active = False
    db.session.commit()
    return jsonify({'status': 'success', 'message': 'User deactivated successfully'})

# =====================================================================
# EXTENDED SETTINGS (including token configuration)
# =====================================================================
@dashboard_bp.route('/api/settings', methods=['GET'])
@login_required
def get_settings():
    if current_user.role not in ['admin', 'subadmin']:
        return jsonify({'error': 'Forbidden'}), 403

    return jsonify({
        'currency': Setting.get('currency', '$'),
        'tax_rate': float(Setting.get('tax_rate', '0.00')),
        'tax_label': Setting.get('tax_label', 'Tax'),
        'auto_approve_enabled': Setting.get('auto_approve_enabled', 'true') == 'true',
        'auto_approve_threshold': int(Setting.get('auto_approve_threshold', '10')),
        'auto_approve_time_window': int(Setting.get('auto_approve_time_window', '1')),
        'auto_approve_max_total': int(Setting.get('auto_approve_max_total', '20')),
        # NEW token configuration
        'max_token_cap': int(ServerConfig.get('MAX_TOKEN_CAP', '15')),
        'token_renewal_threshold': int(ServerConfig.get('TOKEN_RENEWAL_THRESHOLD', '2')),
        'default_expiry_days': int(ServerConfig.get('DEFAULT_EXPIRY_DAYS', '7')),
    })

@dashboard_bp.route('/api/settings', methods=['POST'])
@login_required
def update_settings():
    if current_user.role not in ['admin', 'subadmin']:
        return jsonify({'error': 'Forbidden'}), 403

    data = request.get_json()
    if 'currency' in data:
        Setting.set('currency', data['currency'])
    if 'tax_rate' in data:
        Setting.set('tax_rate', str(data['tax_rate']))
    if 'tax_label' in data:
        Setting.set('tax_label', data['tax_label'])
    # Auto‑approve settings
    if 'auto_approve_enabled' in data:
        Setting.set('auto_approve_enabled', 'true' if data['auto_approve_enabled'] else 'false')
    if 'auto_approve_threshold' in data:
        Setting.set('auto_approve_threshold', str(data['auto_approve_threshold']))
    if 'auto_approve_time_window' in data:
        Setting.set('auto_approve_time_window', str(data['auto_approve_time_window']))
    if 'auto_approve_max_total' in data:
        Setting.set('auto_approve_max_total', str(data['auto_approve_max_total']))

    # NEW: token configuration
    if 'max_token_cap' in data:
        ServerConfig.set('MAX_TOKEN_CAP', str(data['max_token_cap']))
    if 'token_renewal_threshold' in data:
        ServerConfig.set('TOKEN_RENEWAL_THRESHOLD', str(data['token_renewal_threshold']))
    if 'default_expiry_days' in data:
        ServerConfig.set('DEFAULT_EXPIRY_DAYS', str(data['default_expiry_days']))

    return jsonify({'status': 'success', 'message': 'Settings updated'})

# =====================================================================
# NEW: ADMIN API KEY & TOKEN MANAGEMENT (dashboard endpoints)
# =====================================================================

@dashboard_bp.route('/api/admin/api-keys')
@login_required
def list_api_keys_dashboard():
    """List all API keys (for admin UI)."""
    if current_user.role not in ['admin', 'subadmin']:
        return jsonify({'error': 'Forbidden'}), 403

    keys = ApiKey.query.options(db.joinedload(ApiKey.user)).all()
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

@dashboard_bp.route('/api/admin/role-keys', methods=['GET'])
@login_required
def list_role_keys_dashboard():
    """List one shared API key record per account type without exposing raw keys."""
    if current_user.role not in ['admin', 'subadmin']:
        return jsonify({'error': 'Forbidden'}), 403

    keys = RoleApiKey.query.order_by(RoleApiKey.role.asc()).all()
    return jsonify({'role_keys': [{
        'id': key.id,
        'role': key.role,
        'created_at': key.created_at.isoformat(),
        'updated_at': key.updated_at.isoformat() if key.updated_at else None
    } for key in keys]})

@dashboard_bp.route('/api/admin/role-keys', methods=['POST'])
@login_required
def generate_role_key_dashboard():
    """Create or rotate the single shared API key for an account type."""
    if current_user.role not in ['admin', 'subadmin']:
        return jsonify({'error': 'Forbidden'}), 403

    data = request.get_json() or {}
    role = str(data.get('role', '')).strip().lower()
    allowed_roles = ['sales', 'captain', 'storekeeper', 'van', 'finance', 'cashier']
    if role not in allowed_roles:
        return jsonify({'error': 'Invalid account type'}), 400

    role_key = RoleApiKey.query.filter_by(role=role).first()
    raw_key = generate_api_key()
    if role_key:
        role_key.api_key = raw_key
    else:
        role_key = RoleApiKey(role=role, api_key=raw_key)
        db.session.add(role_key)
    db.session.commit()

    return jsonify({
        'status': 'success',
        'role': role,
        'api_key': raw_key,
        'message': 'Shared API key generated. This is the only time the raw key is shown.'
    })

@dashboard_bp.route('/api/admin/role-keys/<int:key_id>', methods=['DELETE'])
@login_required
def revoke_role_key_dashboard(key_id):
    """Remove the shared API key for an account type."""
    if current_user.role not in ['admin', 'subadmin']:
        return jsonify({'error': 'Forbidden'}), 403

    role_key = RoleApiKey.query.get(key_id)
    if not role_key:
        return jsonify({'error': 'Role API key not found'}), 404
    role = role_key.role
    db.session.delete(role_key)
    db.session.commit()
    return jsonify({'status': 'success', 'message': f'{role} shared API key revoked'})

@dashboard_bp.route('/api/admin/tokens/<int:user_id>')
@login_required
def get_user_tokens_dashboard(user_id):
    """Get token pool for a user (dashboard view)."""
    if current_user.role not in ['admin', 'subadmin']:
        return jsonify({'error': 'Forbidden'}), 403

    tokens = TokenPool.query.filter_by(user_id=user_id).order_by(TokenPool.created_at.desc()).all()
    result = []
    for t in tokens:
        result.append({
            'id': t.id,
            'uuid': t.uuid,
            'session_id': t.session_id,
            'cipher_token': t.cipher_token[:8] + '...' + t.cipher_token[-4:],  # masked for security
            'token_status': t.token_status,
            'expiry_timestamp': t.expiry_timestamp.isoformat(),
            'created_at': t.created_at.isoformat(),
            'used_at': t.used_at.isoformat() if t.used_at else None
        })
    # Statistics
    total = len(result)
    unused = TokenPool.query.filter_by(user_id=user_id, token_status='UNUSED').count()
    used = TokenPool.query.filter_by(user_id=user_id, token_status='USED').count()
    expired = TokenPool.query.filter_by(user_id=user_id, token_status='EXPIRED').count()
    return jsonify({
        'tokens': result,
        'stats': {'total': total, 'unused': unused, 'used': used, 'expired': expired}
    })

# =====================================================================
# FIXED: GPC GENERATION ENDPOINT (accepts GET and POST)
# =====================================================================
@dashboard_bp.route('/api/admin/gpc/generate', methods=['GET', 'POST'])
@login_required
def generate_gpc_dashboard():
    """Generate a .gpc login file via dashboard (triggers download)."""
    if current_user.role not in ['admin', 'subadmin']:
        return jsonify({'error': 'Forbidden'}), 403

    # Handle both GET (from download link) and POST (from form)
    if request.method == 'POST':
        data = request.get_json()
        if not data:
            return jsonify({'error': 'JSON body required'}), 400
        user_id = data.get('user_id')
        expiry_days = data.get('expiry_days', 7)
        show_stock = data.get('show_stock_quantity', True)
    else:  # GET
        user_id = request.args.get('user_id')
        expiry_days = int(request.args.get('expiry_days', 7))
        show_stock = request.args.get('show_stock_quantity', 'true').lower() == 'true'

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
        # Log activity
        log = ActivityLog(
            user_id=current_user.id,
            action='generate_gpc_dashboard',
            table_name='users',
            record_id=user_id,
            new_value=json.dumps({'expiry_days': expiry_days, 'show_stock': show_stock}),
            timestamp=datetime.utcnow()
        )
        db.session.add(log)
        db.session.commit()

        return serve_gpc_file(encrypted_bytes, filename)
    except Exception as e:
        current_app.logger.error(f"GPC generation error: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

# =====================================================================
# (Existing) INVENTORY TRANSACTIONS (for admin dashboard)
# =====================================================================
@dashboard_bp.route('/api/inventory-transactions')
@login_required
def get_inventory_transactions():
    user = current_user
    if user.role not in ['admin', 'subadmin']:
        return jsonify({'error': 'Forbidden'}), 403

    status = request.args.get('status', 'pending')
    limit = min(int(request.args.get('limit', 50)), 200)
    offset = int(request.args.get('offset', 0))

    query = InventoryTransaction.query
    if status:
        query = query.filter_by(status=status)

    # Subadmin city filter
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

    total = query.count()
    transactions = query.order_by(InventoryTransaction.created_at.desc()).offset(offset).limit(limit).all()

    result = []
    for t in transactions:
        result.append({
            'id': t.id,
            'product_id': t.product_id,
            'product_name': t.product.name if t.product else 'Unknown',
            'warehouse_id': t.warehouse_id,
            'warehouse_name': t.warehouse.name if t.warehouse else 'N/A',
            'quantity': t.quantity,
            'type': t.type,
            'status': t.status,
            'requested_by': t.requester.username if t.requester else 'Unknown',
            'approved_by': t.approver.username if t.approver else None,
            'notes': t.notes,
            'created_at': t.created_at.isoformat(),
            'approved_at': t.approved_at.isoformat() if t.approved_at else None,
            # NEW fields
            'po_number': t.po_number,
            'po_date': t.po_date.isoformat() if t.po_date else None,
            'attachment_url': t.attachment_url,
            'ordered_qty': t.ordered_qty,
            'before_qty': t.before_qty,
            'after_qty': t.after_qty
        })
    return jsonify({
        'transactions': result,
        'total': total,
        'limit': limit,
        'offset': offset
    })

# =====================================================================
# (Existing) DELIVERIES, SETTLEMENTS, STOCK TRANSFERS, FINANCE, etc.
# =====================================================================

@dashboard_bp.route('/api/deliveries')
@login_required
def get_deliveries_dashboard():
    user = current_user
    query = Delivery.query

    if user.role == 'captain':
        if user.city_id:
            order_ids = [o.id for o in Order.query.filter_by(city_id=user.city_id).all()]
            query = query.filter(Delivery.order_id.in_(order_ids))
    elif user.role == 'storekeeper':
        query = query.filter(Delivery.status.in_(['pending', 'picked_up']))
    elif user.role not in ['admin', 'subadmin']:
        return jsonify({'error': 'Forbidden'}), 403

    deliveries = query.order_by(Delivery.created_at.desc()).limit(50).all()
    result = []
    for d in deliveries:
        order = Order.query.get(d.order_id)
        result.append({
            'id': d.id,
            'order_id': d.order_id,
            'customer_name': order.customer_name if order else 'N/A',
            'assigned_to': d.assigned_to.username if d.assigned_to else 'Unknown',
            'status': d.status,
            'scheduled_date': d.scheduled_date.isoformat() if d.scheduled_date else None,
            'actual_delivery_date': d.actual_delivery_date.isoformat() if d.actual_delivery_date else None,
            'created_at': d.created_at.isoformat()
        })
    return jsonify({'deliveries': result})

@dashboard_bp.route('/api/deliveries/<int:delivery_id>/status', methods=['PUT'])
@login_required
def update_delivery_status_dashboard(delivery_id):
    user = current_user
    if user.role not in ['admin', 'subadmin', 'captain']:
        return jsonify({'error': 'Forbidden'}), 403

    delivery = Delivery.query.get(delivery_id)
    if not delivery:
        return jsonify({'error': 'Delivery not found'}), 404

    data = request.get_json()
    status = data.get('status')
    if not status or status not in ['pending', 'picked_up', 'in_transit', 'delivered', 'partially_delivered', 'rejected']:
        return jsonify({'error': 'Invalid status'}), 400

    delivery.status = status
    if status == 'in_transit':
        order = Order.query.get(delivery.order_id)
        if order:
            order.status = 'in_transit'
    db.session.commit()
    return jsonify({'status': 'success', 'message': f'Delivery status updated to {status}'})

@dashboard_bp.route('/api/settlements')
@login_required
def get_settlements_dashboard():
    user = current_user
    if user.role not in ['admin', 'subadmin', 'cashier', 'finance']:
        return jsonify({'error': 'Forbidden'}), 403

    query = CashSettlement.query
    if user.role == 'cashier':
        query = query.filter(CashSettlement.status == 'pending')

    settlements = query.order_by(CashSettlement.created_at.desc()).limit(50).all()
    result = []
    for s in settlements:
        result.append({
            'id': s.id,
            'user_id': s.user_id,
            'username': s.user.username if s.user else 'Unknown',
            'amount': float(s.amount),
            'status': s.status,
            'settlement_date': s.settlement_date.isoformat(),
            'cashier': s.cashier.username if s.cashier else None,
            'finance_verifier': s.finance_verifier.username if s.finance_verifier else None,
            'notes': s.notes
        })
    return jsonify({'settlements': result})

@dashboard_bp.route('/api/settlements/<int:settlement_id>/verify', methods=['PUT'])
@login_required
def verify_settlement_dashboard(settlement_id):
    user = current_user
    if user.role not in ['cashier', 'admin', 'subadmin']:
        return jsonify({'error': 'Forbidden'}), 403

    settlement = CashSettlement.query.get(settlement_id)
    if not settlement:
        return jsonify({'error': 'Settlement not found'}), 404
    if settlement.status != 'pending':
        return jsonify({'error': 'Settlement already processed'}), 400

    data = request.get_json()
    verified_amount = data.get('verified_amount', settlement.amount)
    settlement.status = 'verified'
    settlement.cashier_id = user.id
    if verified_amount != settlement.amount:
        settlement.notes = (settlement.notes or '') + f' Discrepancy: expected {settlement.amount}, verified {verified_amount}'
        settlement.amount = verified_amount
    db.session.commit()
    return jsonify({'status': 'success', 'message': 'Settlement verified'})

@dashboard_bp.route('/api/settlements/<int:settlement_id>/approve', methods=['PUT'])
@login_required
def approve_settlement_dashboard(settlement_id):
    user = current_user
    if user.role not in ['admin', 'subadmin', 'finance']:
        return jsonify({'error': 'Forbidden'}), 403

    settlement = CashSettlement.query.get(settlement_id)
    if not settlement:
        return jsonify({'error': 'Settlement not found'}), 404
    if settlement.status != 'verified':
        return jsonify({'error': 'Settlement must be verified first'}), 400

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

    return jsonify({'status': 'success', 'message': 'Settlement approved'})

@dashboard_bp.route('/api/stock-transfers')
@login_required
def get_stock_transfers_dashboard():
    user = current_user
    if user.role not in ['captain', 'admin', 'subadmin']:
        return jsonify({'error': 'Forbidden'}), 403

    query = StockTransfer.query
    if user.role == 'captain' and user.city_id:
        users_in_city = [u.id for u in User.query.filter_by(city_id=user.city_id).all()]
        query = query.filter(
            (StockTransfer.from_user_id.in_(users_in_city)) |
            (StockTransfer.to_user_id.in_(users_in_city))
        )

    transfers = query.order_by(StockTransfer.created_at.desc()).limit(50).all()
    result = []
    for t in transfers:
        result.append({
            'id': t.id,
            'from_user': t.from_user.username if t.from_user else 'Unknown',
            'to_user': t.to_user.username if t.to_user else 'Unknown',
            'status': t.status,
            'meeting_location': t.meeting_location,
            'scheduled_time': t.scheduled_time.isoformat() if t.scheduled_time else None,
            'items_count': len(t.items)
        })
    return jsonify({'transfers': result})

@dashboard_bp.route('/api/finance/summary')
@login_required
def finance_summary_dashboard():
    if current_user.role not in ['admin', 'subadmin', 'finance']:
        return jsonify({'error': 'Forbidden'}), 403

    today = datetime.utcnow().date()
    payments_today = Payment.query.filter(
        func.date(Payment.transaction_date) == today,
        Payment.status == 'completed'
    ).all()
    total_collected = sum(p.amount for p in payments_today)

    total_outstanding = db.session.query(func.sum(Customer.outstanding_balance)).scalar() or Decimal('0.00')

    pending_settlements = CashSettlement.query.filter_by(status='pending').all()
    pending_amount = sum(s.amount for s in pending_settlements)

    return jsonify({
        'total_collected_today': float(total_collected),
        'total_outstanding': float(total_outstanding),
        'pending_settlements': len(pending_settlements),
        'pending_settlement_amount': float(pending_amount)
    })

# ---------- Storekeeper Picking & Packing Routes ----------
@dashboard_bp.route('/api/orders/approved')
@login_required
def get_approved_orders():
    user = current_user
    if user.role not in ['storekeeper', 'admin', 'subadmin']:
        return jsonify({'error': 'Forbidden'}), 403

    query = Order.query.filter(Order.status.in_(['approved', 'picked']))
    if user.role != 'admin' and user.role != 'subadmin':
        query = query.filter_by(city_id=user.city_id)

    warehouse_id = request.args.get('warehouse_id')
    if warehouse_id:
        query = query.filter_by(warehouse_id=warehouse_id)

    orders = query.order_by(Order.created_at.asc()).limit(50).all()
    result = []
    for o in orders:
        result.append({
            'id': o.id,
            'customer_name': o.customer_name,
            'status': o.status,
            'warehouse_id': o.warehouse_id,
            'warehouse_name': o.warehouse.name if o.warehouse else None,
            'items_count': len(o.items),
            'created_at': o.created_at.isoformat()
        })
    return jsonify({'orders': result})

@dashboard_bp.route('/api/orders/picked')
@login_required
def get_picked_orders():
    user = current_user
    if user.role not in ['storekeeper', 'admin', 'subadmin']:
        return jsonify({'error': 'Forbidden'}), 403

    query = Order.query.filter_by(status='picked')
    if user.role != 'admin' and user.role != 'subadmin':
        query = query.filter_by(city_id=user.city_id)

    warehouse_id = request.args.get('warehouse_id')
    if warehouse_id:
        query = query.filter_by(warehouse_id=warehouse_id)

    orders = query.order_by(Order.created_at.asc()).limit(50).all()
    result = []
    for o in orders:
        result.append({
            'id': o.id,
            'customer_name': o.customer_name,
            'warehouse_id': o.warehouse_id,
            'warehouse_name': o.warehouse.name if o.warehouse else None,
            'items': [{'product_name': i.product_name, 'ordered_qty': i.ordered_qty} for i in o.items],
            'created_at': o.created_at.isoformat()
        })
    return jsonify({'orders': result})

# ---------- RETURNS ----------
@dashboard_bp.route('/api/returns')
@login_required
def get_returns_dashboard():
    user = current_user
    if user.role not in ['admin', 'subadmin', 'captain']:
        return jsonify({'error': 'Forbidden'}), 403

    query = Return.query
    if user.role == 'captain' and user.city_id:
        order_ids = [o.id for o in Order.query.filter_by(city_id=user.city_id).all()]
        query = query.filter(Return.order_id.in_(order_ids))

    returns = query.order_by(Return.created_at.desc()).limit(50).all()
    result = []
    for r in returns:
        result.append({
            'id': r.id,
            'order_id': r.order_id,
            'product_id': r.product_id,
            'user_id': r.user_id,
            'return_type': r.return_type,
            'quantity': r.quantity,
            'reason': r.reason,
            'status': r.status,
            'created_at': r.created_at.isoformat()
        })
    return jsonify({'returns': result})

# ========================
# WAREHOUSE MANAGEMENT (FIXED: allows storekeeper and captain)
# ========================
@dashboard_bp.route('/api/warehouses')
@login_required
def get_warehouses_dashboard():
    user = current_user
    if user.role not in ['admin', 'subadmin', 'captain', 'storekeeper']:
        return jsonify({'error': 'Forbidden'}), 403

    query = Warehouse.query.filter_by(is_active=True)
    if user.role != 'admin' and user.city_id:
        query = query.filter_by(city_id=user.city_id)

    warehouses = query.all()
    result = []
    for w in warehouses:
        result.append({
            'id': w.id,
            'name': w.name,
            'code': w.code,
            'city_id': w.city_id,
            'city_name': w.city.name if w.city else None,
            'address': w.address,
            'is_active': w.is_active,
            'created_at': w.created_at.isoformat()
        })
    return jsonify({'warehouses': result})

@dashboard_bp.route('/api/warehouses', methods=['POST'])
@login_required
def create_warehouse_dashboard():
    user = current_user
    if user.role not in ['admin', 'subadmin']:
        return jsonify({'error': 'Forbidden'}), 403

    data = request.get_json()
    name = data.get('name')
    code = data.get('code')
    city_id = data.get('city_id')
    address = data.get('address')

    if not name or not code or not city_id:
        return jsonify({'error': 'name, code, city_id required'}), 400

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
    return jsonify({'status': 'success', 'id': warehouse.id, 'message': 'Warehouse created'})

@dashboard_bp.route('/api/warehouses/<int:warehouse_id>', methods=['PUT'])
@login_required
def update_warehouse_dashboard(warehouse_id):
    user = current_user
    if user.role not in ['admin', 'subadmin']:
        return jsonify({'error': 'Forbidden'}), 403

    warehouse = Warehouse.query.get(warehouse_id)
    if not warehouse:
        return jsonify({'error': 'Warehouse not found'}), 404

    data = request.get_json()
    warehouse.name = data.get('name', warehouse.name)
    warehouse.code = data.get('code', warehouse.code)
    warehouse.address = data.get('address', warehouse.address)
    warehouse.is_active = data.get('is_active', warehouse.is_active)
    db.session.commit()
    return jsonify({'status': 'success', 'message': 'Warehouse updated'})

@dashboard_bp.route('/api/warehouses/<int:warehouse_id>', methods=['DELETE'])
@login_required
def delete_warehouse_dashboard(warehouse_id):
    user = current_user
    if user.role not in ['admin', 'subadmin']:
        return jsonify({'error': 'Forbidden'}), 403

    warehouse = Warehouse.query.get(warehouse_id)
    if not warehouse:
        return jsonify({'error': 'Warehouse not found'}), 404
    warehouse.is_active = False
    db.session.commit()
    return jsonify({'status': 'success', 'message': 'Warehouse deactivated'})

# ========================
# PRODUCT INVENTORY
# ========================
@dashboard_bp.route('/api/products/<int:product_id>/inventory')
@login_required
def get_product_inventory_dashboard(product_id):
    user = current_user
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
    return jsonify({
        'product_id': product_id,
        'product_name': product.name,
        'inventory': result,
        'total_current': sum(i.current_qty for i in inventories),
        'total_reserved': sum(i.reserved_qty for i in inventories),
        'total_available': sum(i.available_qty for i in inventories)
    })

@dashboard_bp.route('/api/inventory/update', methods=['POST'])
@login_required
def update_inventory_dashboard():
    user = current_user
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

    inv = Inventory.query.filter_by(product_id=product_id, warehouse_id=warehouse_id).first()
    if not inv:
        inv = Inventory(product_id=product_id, warehouse_id=warehouse_id, current_qty=0, reserved_qty=0)
        db.session.add(inv)

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
    return jsonify({'status': 'success', 'message': 'Inventory updated', 'new_qty': inv.current_qty})

# ---------- Backup & Restore ----------
@dashboard_bp.route('/api/backup/list')
@login_required
def list_backups():
    if current_user.role != 'admin':
        return jsonify({'error': 'Forbidden'}), 403
    files = list_backup_files()
    return jsonify({'files': files})

@dashboard_bp.route('/api/backup/create', methods=['POST'])
@login_required
def create_backup():
    if current_user.role != 'admin':
        return jsonify({'error': 'Forbidden'}), 403
    try:
        filepath = export_backup_zip()
        return jsonify({'status': 'success', 'file': os.path.basename(filepath)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@dashboard_bp.route('/api/backup/restore', methods=['POST'])
@login_required
def restore_backup():
    if current_user.role != 'admin':
        return jsonify({'error': 'Forbidden'}), 403

    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Empty filename'}), 400

    mode = request.form.get('mode', 'flush')
    try:
        import_backup_from_zip(file, mode)
        return jsonify({'status': 'success', 'message': 'Restore completed'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@dashboard_bp.route('/api/backup/download/<filename>')
@login_required
def download_backup(filename):
    if current_user.role != 'admin':
        return jsonify({'error': 'Forbidden'}), 403
    backup_dir = get_backup_dir()
    filepath = os.path.join(backup_dir, filename)
    if not os.path.exists(filepath):
        return jsonify({'error': 'File not found'}), 404
    return send_file(filepath, as_attachment=True)

# ---------- Label print view ----------
@dashboard_bp.route('/order/<int:order_id>/label')
@login_required
def order_label(order_id):
    order = Order.query.get(order_id)
    if not order:
        return 'Order not found', 404
    if not order.package_barcode:
        return 'Order not packed yet', 400
    if current_user.role != 'admin' and current_user.city_id != order.city_id:
        return 'Forbidden', 403
    import qrcode, base64
    from io import BytesIO
    image = BytesIO()
    qrcode.make(order.package_qr).save(image, format='PNG')
    return render_template('label.html', order=order, qr_image=base64.b64encode(image.getvalue()).decode())

# ============================================================
# Captain Performance Summary
# ============================================================
@dashboard_bp.route('/api/captain/performance')
@login_required
def captain_performance():
    user = current_user
    if user.role != 'captain':
        return jsonify({'error': 'Forbidden'}), 403

    pending_orders = Order.query.filter_by(status='pending', city_id=user.city_id).count()

    today = datetime.utcnow().date()
    today_orders = Order.query.filter(
        func.date(Order.created_at) == today,
        Order.city_id == user.city_id,
        Order.status.in_(['delivered', 'closed', 'approved'])
    ).all()
    today_sales = sum(o.net_total for o in today_orders)

    delivered_today = Order.query.filter(
        func.date(Order.created_at) == today,
        Order.status == 'delivered',
        Order.city_id == user.city_id
    ).count()

    deliveries = Delivery.query.join(Order).filter(
        Order.city_id == user.city_id,
        Delivery.status == 'delivered',
        Delivery.actual_delivery_date.isnot(None)
    ).all()
    on_time = 0
    total_delivered = len(deliveries)
    for d in deliveries:
        if d.scheduled_date and d.actual_delivery_date <= d.scheduled_date:
            on_time += 1
        elif not d.scheduled_date:
            on_time += 1
    on_time_percent = round((on_time / total_delivered * 100) if total_delivered > 0 else 0, 1)

    sales_trend = []
    for i in range(6, -1, -1):
        day = datetime.utcnow().date() - timedelta(days=i)
        day_orders = Order.query.filter(
            func.date(Order.created_at) == day,
            Order.city_id == user.city_id,
            Order.status.in_(['delivered', 'closed', 'approved'])
        ).all()
        total = sum(o.net_total for o in day_orders)
        sales_trend.append({
            'date': day.isoformat(),
            'total': float(total)
        })

    delivered_count = Order.query.filter_by(city_id=user.city_id, status='delivered').count()
    in_transit_count = Order.query.filter_by(city_id=user.city_id, status='in_transit').count()
    pending_count = Order.query.filter_by(city_id=user.city_id, status='pending').count()
    rejected_count = Order.query.filter_by(city_id=user.city_id, status='rejected').count()

    return jsonify({
        'pending_orders': pending_orders,
        'today_sales': float(today_sales),
        'delivered_today': delivered_today,
        'on_time_percent': on_time_percent,
        'sales_trend': sales_trend,
        'delivered_count': delivered_count,
        'in_transit_count': in_transit_count,
        'pending_count': pending_count,
        'rejected_count': rejected_count
    })
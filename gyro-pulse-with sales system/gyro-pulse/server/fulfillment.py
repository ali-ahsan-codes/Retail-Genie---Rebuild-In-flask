"""Transactional fulfillment. Reservation stays held until warehouse dispatch readiness."""
import base64
import uuid
from datetime import datetime
from functools import wraps
from io import BytesIO

import qrcode
from flask import jsonify, request
from models import db, Order, OrderItem, Inventory, Warehouse, User, AgentInventory


def register_fulfillment(app):
    def operation(roles):
        def decorate(fn):
            @wraps(fn)
            def run(order_id):
                from api import check_api_key
                failure = check_api_key()
                if failure is not None:
                    return failure
                user = request.user
                if user.role not in roles:
                    return jsonify(error='Forbidden'), 403
                order = db.session.query(Order).filter_by(id=order_id).with_for_update().first()
                if not order:
                    return jsonify(error='Order not found'), 404
                if user.role != 'admin' and user.city_id != order.city_id:
                    return jsonify(error='Order belongs to another city'), 403
                try:
                    result = fn(order, request.get_json(silent=True) or {}, user)
                    db.session.commit()
                    return jsonify(status='success', order_id=order.id, order_status=order.status, **(result or {}))
                except (ValueError, TypeError) as exc:
                    db.session.rollback()
                    return jsonify(error=str(exc)), 400
                except Exception:
                    db.session.rollback()
                    app.logger.exception('Fulfillment failed')
                    return jsonify(error='Fulfillment failed'), 500
            return run
        return decorate

    def state(order, expected):
        if order.status not in expected:
            raise ValueError('Invalid order state: ' + order.status)

    def inventory(order, item):
        row = db.session.query(Inventory).filter_by(warehouse_id=order.warehouse_id, product_id=item.product_id).with_for_update().first()
        if not row:
            raise ValueError('Inventory not found')
        return row

    @app.route('/api/orders/<int:order_id>/approve', methods=['PUT', 'POST'])
    @operation(['admin', 'captain'])
    def approve_order(order, data, user):
        state(order, ['pending'])
        if not order.items:
            raise ValueError('Order has no items')
        warehouses = Warehouse.query.filter_by(city_id=order.city_id, is_active=True)
        if data.get('warehouse_id'):
            warehouses = warehouses.filter_by(id=data['warehouse_id'])
        for warehouse in warehouses.order_by(Warehouse.id).all():
            rows = {i.product_id: i for i in db.session.query(Inventory).filter_by(warehouse_id=warehouse.id).order_by(Inventory.id).with_for_update().all()}
            quantities = {}
            for item in order.items:
                if item.ordered_qty <= 0:
                    raise ValueError('Invalid order quantity')
                quantities[item.product_id] = quantities.get(item.product_id, 0) + item.ordered_qty
            if all(pid in rows and rows[pid].current_qty - rows[pid].reserved_qty >= qty for pid, qty in quantities.items()):
                for pid, qty in quantities.items():
                    rows[pid].reserved_qty += qty
                order.warehouse_id = warehouse.id
                order.captain_id = user.id
                order.status = 'approved'
                return
        raise ValueError('No warehouse has sufficient available stock')

    @app.route('/api/orders/<int:order_id>/pick', methods=['PUT', 'POST'])
    @operation(['admin', 'storekeeper'])
    def pick_item(order, data, user):
        state(order, ['approved'])
        qty = data.get('quantity', 1)
        if not isinstance(qty, int) or isinstance(qty, bool) or qty <= 0:
            raise ValueError('Quantity must be a positive integer')
        item = next((i for i in order.items if (data.get('product_id') and i.product_id == data['product_id']) or (data.get('barcode') and i.product_barcode == data['barcode'])), None)
        if item is None or item.picked_qty + qty > item.ordered_qty:
            raise ValueError('Invalid item or excessive picked quantity')
        item.picked_qty += qty
        # Do not release reservation here: goods are still in warehouse stock.
        if all(i.picked_qty == i.ordered_qty for i in order.items):
            order.status = 'picked'
            order.picked_at = datetime.utcnow()

    @app.route('/api/orders/<int:order_id>/pack', methods=['PUT', 'POST'])
    @operation(['admin', 'storekeeper'])
    def pack_order(order, data, user):
        state(order, ['picked'])
        order.package_barcode = f'PKG-{order.id}-{uuid.uuid4().hex[:12]}'
        # Store a short scan payload, not a PNG in a VARCHAR(255) column.
        order.package_qr = request.host_url.rstrip('/') + f'/dashboard/order/{order.id}/label'
        order.packed_at = datetime.utcnow()
        order.status = 'packed'
        return {'barcode': order.package_barcode, 'label_url': order.package_qr}

    @app.route('/api/orders/<int:order_id>/ready', methods=['PUT', 'POST'])
    @operation(['admin', 'storekeeper'])
    def mark_ready(order, data, user):
        state(order, ['packed'])
        for item in order.items:
            row = inventory(order, item)
            if row.current_qty < item.ordered_qty or row.reserved_qty < item.ordered_qty:
                raise ValueError('Inventory invariant violated')
            row.current_qty -= item.ordered_qty
            row.reserved_qty -= item.ordered_qty
        order.store_keeper_id = user.id
        order.status = 'ready'

    @app.route('/api/orders/<int:order_id>/dispatch-scan', methods=['PUT', 'POST'])
    @operation(['admin', 'storekeeper', 'van'])
    def dispatch_scan(order, data, user):
        state(order, ['ready'])
        if data.get('barcode') != order.package_barcode:
            raise ValueError('Package barcode mismatch')
        scan = data.get('scan_type')
        if scan == 'storekeeper' and user.role in ['storekeeper', 'admin']:
            order.storekeeper_confirmed_at = datetime.utcnow()
        elif scan == 'delivery' and user.role in ['van', 'admin']:
            agent_id = data.get('delivery_agent_id') if user.role == 'admin' else user.id
            agent = User.query.get(agent_id)
            if not agent or not agent.is_active or agent.role != 'van' or agent.city_id != order.city_id:
                raise ValueError('Invalid delivery agent')
            order.delivery_agent_id = agent.id
            order.delivery_confirmed_at = datetime.utcnow()
        else:
            raise ValueError('Invalid scan type or role')
        if order.storekeeper_confirmed_at and order.delivery_confirmed_at:
            for item in order.items:
                row = AgentInventory.query.filter_by(user_id=order.delivery_agent_id, product_id=item.product_id).with_for_update().first()
                if row is None:
                    row = AgentInventory(user_id=order.delivery_agent_id, product_id=item.product_id, current_physical_qty=0)
                    db.session.add(row)
                row.current_physical_qty += item.ordered_qty
            order.status = 'dispatched'
            order.dispatched_at = datetime.utcnow()

    @app.route('/api/orders/<int:order_id>/qr.png')
    @operation(['admin', 'captain', 'storekeeper', 'van'])
    def package_qr(order, data, user):
        if not order.package_qr:
            raise ValueError('Order not packed')
        image = BytesIO()
        qrcode.make(order.package_qr).save(image, format='PNG')
        return {'qr_base64': base64.b64encode(image.getvalue()).decode()}

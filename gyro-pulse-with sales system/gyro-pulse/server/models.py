from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
import uuid

db = SQLAlchemy()

# ========================
# ROLE API KEYS
# ========================
class RoleApiKey(db.Model):
    __tablename__ = 'role_api_keys'
    id = db.Column(db.Integer, primary_key=True)
    role = db.Column(db.String(20), unique=True, nullable=False)
    api_key = db.Column(db.String(64), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# ========================
# SYSTEM SETTINGS (legacy)
# ========================
class Setting(db.Model):
    __tablename__ = 'settings'
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @staticmethod
    def get(key, default=None):
        setting = Setting.query.filter_by(key=key).first()
        return setting.value if setting else default

    @staticmethod
    def set(key, value):
        setting = Setting.query.filter_by(key=key).first()
        if setting:
            setting.value = value
        else:
            setting = Setting(key=key, value=value)
            db.session.add(setting)
        db.session.commit()

# ========================
# SERVER CONFIGURATION (NEW)
# ========================
class ServerConfig(db.Model):
    __tablename__ = 'server_config'
    key = db.Column(db.String(100), primary_key=True)
    value = db.Column(db.Text, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @staticmethod
    def get(key, default=None):
        config = ServerConfig.query.get(key)
        return config.value if config else default

    @staticmethod
    def set(key, value):
        config = ServerConfig.query.get(key)
        if config:
            config.value = value
        else:
            config = ServerConfig(key=key, value=value)
            db.session.add(config)
        db.session.commit()

# ========================
# CITY
# ========================
class City(db.Model):
    __tablename__ = 'cities'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)

    users = db.relationship('User', backref='city', lazy=True)
    products = db.relationship('Product', backref='city', lazy=True)
    customers = db.relationship('Customer', backref='city', lazy=True)
    orders = db.relationship('Order', backref='city', lazy=True)
    warehouses = db.relationship('Warehouse', backref='city', lazy=True)

# ========================
# USER
# ========================
class User(db.Model, UserMixin):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    city_id = db.Column(db.Integer, db.ForeignKey('cities.id'), nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    last_sync_at = db.Column(db.DateTime, nullable=True)
    show_stock_quantity = db.Column(db.Boolean, default=True)

    creator = db.relationship('User', remote_side=[id], backref='created_users')
    sync_status = db.relationship('UserSyncStatus', backref='user', uselist=False, cascade='all, delete-orphan')
    device_tokens = db.relationship('DeviceToken', backref='user', lazy=True, cascade='all, delete-orphan')
    
    # ===== NEW RELATIONSHIPS (parent side with backref) =====
    api_keys = db.relationship('ApiKey', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    token_pools = db.relationship('TokenPool', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    media_files = db.relationship('Media', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    device_commands = db.relationship('DeviceCommand', backref='user', lazy='dynamic', cascade='all, delete-orphan')

    def get_id(self):
        return str(self.id)

# ========================
# DEVICE TOKENS (for push notifications, legacy)
# ========================
class DeviceToken(db.Model):
    __tablename__ = 'device_tokens'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    token = db.Column(db.String(255), nullable=False, unique=True)
    device_type = db.Column(db.String(20), default='android')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ========================
# USER SYNC STATUS
# ========================
class UserSyncStatus(db.Model):
    __tablename__ = 'user_sync_status'
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    last_message_timestamp = db.Column(db.DateTime, nullable=True)
    upload_required = db.Column(db.Boolean, default=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# ========================
# MESSAGES
# ========================
class Message(db.Model):
    __tablename__ = 'messages'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    receiver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    type = db.Column(db.String(20), nullable=False)
    content = db.Column(db.Text)
    media_url = db.Column(db.String(255))
    latitude = db.Column(db.Numeric(10,7))
    longitude = db.Column(db.Numeric(10,7))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    device_id = db.Column(db.String(50))
    read = db.Column(db.Boolean, default=False)

    sender = db.relationship('User', foreign_keys=[sender_id], backref='sent_messages')
    receiver = db.relationship('User', foreign_keys=[receiver_id], backref='received_messages')
    user = db.relationship('User', foreign_keys=[user_id], backref='messages')

# ========================
# PRODUCTS
# ========================
class Product(db.Model):
    __tablename__ = 'products'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    sku = db.Column(db.String(100), unique=True)
    barcode = db.Column(db.String(100), unique=True, index=True)
    description = db.Column(db.Text)
    unit_price = db.Column(db.Numeric(12, 2), nullable=False, default=0.00)
    tax_rate = db.Column(db.Numeric(5, 2), default=0.00)
    current_warehouse_qty = db.Column(db.Integer, default=0)
    reserved_warehouse_qty = db.Column(db.Integer, default=0)
    category = db.Column(db.String(100))
    image_url = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True)
    city_id = db.Column(db.Integer, db.ForeignKey('cities.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (db.Index('idx_products_updated_at', 'updated_at'),)

    inventory_items = db.relationship('Inventory', backref='product', lazy=True, cascade='all, delete-orphan')
    price_list_items = db.relationship('PriceListItem', backref='product', lazy=True)

    @property
    def available_warehouse_qty(self):
        return sum(inv.current_qty - inv.reserved_qty for inv in self.inventory_items)

    @property
    def total_current_qty(self):
        return sum(inv.current_qty for inv in self.inventory_items)

    @property
    def total_reserved_qty(self):
        return sum(inv.reserved_qty for inv in self.inventory_items)

# ========================
# WAREHOUSE
# ========================
class Warehouse(db.Model):
    __tablename__ = 'warehouses'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(20), unique=True, nullable=False)
    city_id = db.Column(db.Integer, db.ForeignKey('cities.id'), nullable=False)
    address = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    inventory = db.relationship('Inventory', backref='warehouse', lazy=True, cascade='all, delete-orphan')
    orders = db.relationship('Order', backref='warehouse', lazy=True)

# ========================
# INVENTORY
# ========================
class Inventory(db.Model):
    __tablename__ = 'inventory'
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False)
    current_qty = db.Column(db.Integer, default=0)
    reserved_qty = db.Column(db.Integer, default=0)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('product_id', 'warehouse_id', name='uix_product_warehouse'),)

    @property
    def available_qty(self):
        return self.current_qty - self.reserved_qty

# ========================
# INVENTORY TRANSACTIONS
# ========================
class InventoryTransaction(db.Model):
    __tablename__ = 'inventory_transactions'
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=True)
    agent_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    quantity = db.Column(db.Integer, nullable=False)
    type = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), default='pending')
    requested_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    approved_at = db.Column(db.DateTime, nullable=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=True)
    return_id = db.Column(db.Integer, db.ForeignKey('returns.id'), nullable=True)
    po_number = db.Column(db.String(100), nullable=True)
    po_date = db.Column(db.DateTime, nullable=True)
    attachment_url = db.Column(db.String(500), nullable=True)
    ordered_qty = db.Column(db.Integer, nullable=True)
    before_qty = db.Column(db.Integer, nullable=True)
    after_qty = db.Column(db.Integer, nullable=True)

    product = db.relationship('Product')
    warehouse = db.relationship('Warehouse')
    agent_user = db.relationship('User', foreign_keys=[agent_user_id])
    requester = db.relationship('User', foreign_keys=[requested_by])
    approver = db.relationship('User', foreign_keys=[approved_by])
    order = db.relationship('Order', foreign_keys=[order_id])
    return_ref = db.relationship('Return', foreign_keys=[return_id])

# ========================
# CUSTOMERS
# ========================
class Customer(db.Model):
    __tablename__ = 'customers'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(100))
    billing_address = db.Column(db.Text)
    shipping_address = db.Column(db.Text)
    credit_limit = db.Column(db.Numeric(12, 2), default=0.00)
    outstanding_balance = db.Column(db.Numeric(12, 2), default=0.00)
    city_id = db.Column(db.Integer, db.ForeignKey('cities.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    payments = db.relationship('Payment', backref='customer', lazy=True)
    price_lists = db.relationship('CustomerPriceList', backref='customer', lazy=True)

# ========================
# AGENT INVENTORY
# ========================
class AgentInventory(db.Model):
    __tablename__ = 'agent_inventory'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    current_physical_qty = db.Column(db.Integer, default=0)
    reserved_qty = db.Column(db.Integer, default=0)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship('User')
    product = db.relationship('Product')

# ========================
# ORDERS
# ========================
class Order(db.Model):
    __tablename__ = 'orders'
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'))
    customer_name = db.Column(db.String(200))
    customer_phone = db.Column(db.String(20))
    shipping_address = db.Column(db.Text)
    latitude = db.Column(db.Numeric(10, 7))
    longitude = db.Column(db.Numeric(10, 7))
    city_id = db.Column(db.Integer, db.ForeignKey('cities.id'), nullable=False)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=True)

    sales_person_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    captain_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    store_keeper_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    delivery_agent_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    order_date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(50), default='pending')

    subtotal = db.Column(db.Numeric(12, 2), default=0.00)
    tax_amount = db.Column(db.Numeric(12, 2), default=0.00)
    discount = db.Column(db.Numeric(12, 2), default=0.00)
    net_total = db.Column(db.Numeric(12, 2), default=0.00)
    paid_amount = db.Column(db.Numeric(12, 2), default=0.00)
    remaining_balance = db.Column(db.Numeric(12, 2), default=0.00)
    payment_terms = db.Column(db.String(100))
    special_instructions = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    picked_at = db.Column(db.DateTime, nullable=True)
    packed_at = db.Column(db.DateTime, nullable=True)
    package_barcode = db.Column(db.String(100), nullable=True)
    package_qr = db.Column(db.String(255), nullable=True)

    storekeeper_confirmed_at = db.Column(db.DateTime, nullable=True)
    delivery_confirmed_at = db.Column(db.DateTime, nullable=True)
    dispatched_at = db.Column(db.DateTime, nullable=True)

    sales_person = db.relationship('User', foreign_keys=[sales_person_id])
    captain = db.relationship('User', foreign_keys=[captain_id])
    customer = db.relationship('Customer')
    items = db.relationship('OrderItem', backref='order', cascade='all, delete-orphan')
    media = db.relationship('OrderMedia', backref='order', cascade='all, delete-orphan')
    deliveries = db.relationship('Delivery', backref='order', lazy=True)
    payments = db.relationship('Payment', backref='order', lazy=True)
    returns = db.relationship('Return', backref='order', lazy=True)

# ========================
# ORDER ITEMS
# ========================
class OrderItem(db.Model):
    __tablename__ = 'order_items'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    product_name = db.Column(db.String(200))
    product_barcode = db.Column(db.String(100))
    unit_price = db.Column(db.Numeric(12, 2), default=0.00)
    ordered_qty = db.Column(db.Integer, default=0)
    picked_qty = db.Column(db.Integer, default=0)
    delivered_qty = db.Column(db.Integer, default=0)
    line_total = db.Column(db.Numeric(12, 2), default=0.00)
    note = db.Column(db.String(255))

    product = db.relationship('Product')

# ========================
# ORDER MEDIA
# ========================
class OrderMedia(db.Model):
    __tablename__ = 'order_media'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    media_type = db.Column(db.String(20))
    file_url = db.Column(db.String(500))
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

# ========================
# DELIVERY MANAGEMENT
# ========================
class Delivery(db.Model):
    __tablename__ = 'deliveries'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    assigned_to_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    assigned_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    status = db.Column(db.String(30), default='pending')
    scheduled_date = db.Column(db.DateTime, nullable=True)
    actual_delivery_date = db.Column(db.DateTime, nullable=True)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    assigned_to = db.relationship('User', foreign_keys=[assigned_to_user_id])
    assigned_by = db.relationship('User', foreign_keys=[assigned_by_user_id])
    items = db.relationship('DeliveryItem', backref='delivery', cascade='all, delete-orphan')
    proof = db.relationship('DeliveryProof', backref='delivery', uselist=False, cascade='all, delete-orphan')

class DeliveryItem(db.Model):
    __tablename__ = 'delivery_items'
    id = db.Column(db.Integer, primary_key=True)
    delivery_id = db.Column(db.Integer, db.ForeignKey('deliveries.id'), nullable=False)
    order_item_id = db.Column(db.Integer, db.ForeignKey('order_items.id'), nullable=False)
    delivered_qty = db.Column(db.Integer, default=0)
    returned_qty = db.Column(db.Integer, default=0)
    notes = db.Column(db.Text)

    order_item = db.relationship('OrderItem')

class DeliveryProof(db.Model):
    __tablename__ = 'delivery_proof'
    id = db.Column(db.Integer, primary_key=True)
    delivery_id = db.Column(db.Integer, db.ForeignKey('deliveries.id'), nullable=False)
    signature_image_url = db.Column(db.String(500))
    photo_urls = db.Column(db.JSON)
    voice_url = db.Column(db.String(500))
    customer_feedback = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ========================
# PAYMENT COLLECTION
# ========================
class Payment(db.Model):
    __tablename__ = 'payments'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    payment_method = db.Column(db.String(30), nullable=False)
    reference = db.Column(db.String(100))
    transaction_date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='completed')
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', foreign_keys=[user_id])

# ========================
# CASH SETTLEMENT
# ========================
class CashSettlement(db.Model):
    __tablename__ = 'cash_settlements'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    settlement_date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='pending')
    cashier_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    finance_verifier_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship('User', foreign_keys=[user_id])
    cashier = db.relationship('User', foreign_keys=[cashier_id])
    finance_verifier = db.relationship('User', foreign_keys=[finance_verifier_id])
    items = db.relationship('SettlementItem', backref='settlement', cascade='all, delete-orphan')

class SettlementItem(db.Model):
    __tablename__ = 'settlement_items'
    id = db.Column(db.Integer, primary_key=True)
    settlement_id = db.Column(db.Integer, db.ForeignKey('cash_settlements.id'), nullable=False)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=True)
    payment_id = db.Column(db.Integer, db.ForeignKey('payments.id'), nullable=True)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    payment_method = db.Column(db.String(30))
    reference = db.Column(db.String(100))

# ========================
# STOCK TRANSFER (ENHANCED)
# ========================
class StockTransfer(db.Model):
    __tablename__ = 'stock_transfers'
    id = db.Column(db.Integer, primary_key=True)
    from_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    to_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    captain_approved_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    sender_warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=True)
    receiver_warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=True)
    requested_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    transfer_barcode = db.Column(db.String(50), unique=True, nullable=True)
    status = db.Column(db.String(50), default='requested')
    meeting_location = db.Column(db.String(255))
    scheduled_time = db.Column(db.DateTime, nullable=True)
    transfer_date = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    from_user = db.relationship('User', foreign_keys=[from_user_id])
    to_user = db.relationship('User', foreign_keys=[to_user_id])
    captain = db.relationship('User', foreign_keys=[captain_approved_by])
    sender_warehouse = db.relationship('Warehouse', foreign_keys=[sender_warehouse_id])
    receiver_warehouse = db.relationship('Warehouse', foreign_keys=[receiver_warehouse_id])
    requested_by_user = db.relationship('User', foreign_keys=[requested_by_user_id])
    items = db.relationship('StockTransferItem', backref='transfer', cascade='all, delete-orphan')

class StockTransferItem(db.Model):
    __tablename__ = 'stock_transfer_items'
    id = db.Column(db.Integer, primary_key=True)
    stock_transfer_id = db.Column(db.Integer, db.ForeignKey('stock_transfers.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    requested_qty = db.Column(db.Integer, default=0)
    transferred_qty = db.Column(db.Integer, default=0)
    scan_confirm_time = db.Column(db.DateTime, nullable=True)

    product = db.relationship('Product')

# ========================
# FINANCE TRANSACTIONS
# ========================
class FinanceTransaction(db.Model):
    __tablename__ = 'finance_transactions'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    transaction_type = db.Column(db.String(30), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    reference = db.Column(db.String(100))
    description = db.Column(db.Text)
    transaction_date = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    order = db.relationship('Order', foreign_keys=[order_id])
    customer = db.relationship('Customer', foreign_keys=[customer_id])
    user = db.relationship('User', foreign_keys=[user_id])

# ========================
# ACTIVITY LOGS
# ========================
class ActivityLog(db.Model):
    __tablename__ = 'activity_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=True)
    action = db.Column(db.String(100))
    table_name = db.Column(db.String(50))
    record_id = db.Column(db.Integer)
    old_value = db.Column(db.Text)
    new_value = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', foreign_keys=[user_id])
    order = db.relationship('Order', foreign_keys=[order_id])

# ========================
# NOTIFICATIONS
# ========================
class Notification(db.Model):
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, nullable=False)
    data = db.Column(db.Text)
    read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', foreign_keys=[user_id])

# ========================
# RETURNS
# ========================
class Return(db.Model):
    __tablename__ = 'returns'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    return_type = db.Column(db.String(30), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(255))
    status = db.Column(db.String(20), default='pending')
    media_urls = db.Column(db.JSON)
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    product = db.relationship('Product')
    user = db.relationship('User', foreign_keys=[user_id])
    approver = db.relationship('User', foreign_keys=[approved_by])

# ========================
# PRICE LISTS & DISCOUNT RULES
# ========================
class PriceList(db.Model):
    __tablename__ = 'price_lists'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    city_id = db.Column(db.Integer, db.ForeignKey('cities.id'), nullable=True)
    effective_from = db.Column(db.DateTime, nullable=True)
    effective_to = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    city = db.relationship('City')
    items = db.relationship('PriceListItem', backref='price_list', cascade='all, delete-orphan')
    customer_assignments = db.relationship('CustomerPriceList', backref='price_list', lazy=True)

class PriceListItem(db.Model):
    __tablename__ = 'price_list_items'
    id = db.Column(db.Integer, primary_key=True)
    price_list_id = db.Column(db.Integer, db.ForeignKey('price_lists.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    unit_price = db.Column(db.Numeric(12, 2), nullable=False)
    discount_percent = db.Column(db.Numeric(5, 2), default=0.00)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class CustomerPriceList(db.Model):
    __tablename__ = 'customer_price_lists'
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False)
    price_list_id = db.Column(db.Integer, db.ForeignKey('price_lists.id'), nullable=False)
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)

# ============================================================
# NEW TABLES FOR OFFLINE-FIRST SECURITY & MEDIA MANAGEMENT
# ============================================================

# ========================
# DEVICE API KEYS
# ========================
class ApiKey(db.Model):
    __tablename__ = 'api_keys'
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    device_uuid = db.Column(db.String(64), nullable=False, unique=True)
    api_key_hash = db.Column(db.String(128), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    status = db.Column(db.String(20), default='ACTIVE')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_used_at = db.Column(db.DateTime, nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True)

    # user relationship is provided by backref in User model
    # Do NOT add a separate 'user' relationship here

    __table_args__ = (db.Index('idx_api_keys_status', 'status'),)

# ========================
# ONE-TIME CIPHER TOKENS
# ========================
class TokenPool(db.Model):
    __tablename__ = 'token_pools'
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    session_id = db.Column(db.String(64), nullable=False)
    cipher_token = db.Column(db.String(64), unique=True, nullable=False)
    token_status = db.Column(db.String(20), default='UNUSED')
    expiry_timestamp = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    used_at = db.Column(db.DateTime, nullable=True)

    # user relationship is provided by backref in User model
    # Do NOT add a separate 'user' relationship here

    __table_args__ = (db.Index('idx_token_pools_status_expiry', 'token_status', 'expiry_timestamp'),)

# ========================
# MEDIA FILES (uploaded from mobile)
# ========================
class Media(db.Model):
    __tablename__ = 'media'
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=True)
    file_name = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    file_size = db.Column(db.Integer)
    file_hash = db.Column(db.String(64))
    mime_type = db.Column(db.String(100))
    encryption_key_ref = db.Column(db.String(64), nullable=True)
    upload_status = db.Column(db.String(20), default='PENDING')
    uploaded_at = db.Column(db.DateTime, nullable=True)
    deleted_from_device = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # user relationship is provided by backref in User model
    # Do NOT add a separate 'user' relationship here

    order = db.relationship('Order', backref=db.backref('media_files', lazy='dynamic'))
    product = db.relationship('Product', backref=db.backref('media_files', lazy='dynamic'))

    __table_args__ = (db.Index('idx_media_upload_status', 'upload_status'),)

# ========================
# MEDIA UPLOAD STATUS (tracking per media file sync attempts)
# ========================
class MediaUploadStatus(db.Model):
    __tablename__ = 'media_upload_status'
    id = db.Column(db.Integer, primary_key=True)
    media_id = db.Column(db.Integer, db.ForeignKey('media.id'), nullable=False)
    upload_attempt = db.Column(db.Integer, default=0)
    last_attempt_at = db.Column(db.DateTime, nullable=True)
    status_message = db.Column(db.Text, nullable=True)
    success = db.Column(db.Boolean, default=False)
    completed_at = db.Column(db.DateTime, nullable=True)

    media = db.relationship('Media', backref=db.backref('upload_statuses', lazy='dynamic'))

# ========================
# DEVICE COMMAND QUEUE
# ========================
class DeviceCommand(db.Model):
    __tablename__ = 'device_commands'
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    command_type = db.Column(db.String(50), nullable=False)
    payload = db.Column(db.JSON, nullable=True)
    status = db.Column(db.String(20), default='PENDING')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    sent_at = db.Column(db.DateTime, nullable=True)
    acknowledged_at = db.Column(db.DateTime, nullable=True)

    # user relationship is provided by backref in User model
    # Do NOT add a separate 'user' relationship here

    __table_args__ = (db.Index('idx_device_commands_status', 'status'),)
class OfflineSubmission(db.Model):
    """Unique per-device order identity prevents duplicate retry/import submissions."""
    __tablename__ = 'offline_submissions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    client_id = db.Column(db.String(64), nullable=False)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    __table_args__ = (db.UniqueConstraint('user_id', 'client_id'),)

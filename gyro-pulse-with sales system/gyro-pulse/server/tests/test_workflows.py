import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
import pytest
os.environ['DATABASE_URL'] = 'sqlite://'
os.environ['SECRET_KEY'] = 'testing-key-not-for-deployment'
os.environ['MASTER_SECRET'] = 'testing-master-secret'
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app
from models import db, City, User, Warehouse, Product, Inventory, Order, OrderItem, ApiKey, AgentInventory
from utils import hash_api_key
from werkzeug.security import generate_password_hash

@pytest.fixture()
def setup():
    app = create_app()
    app.config.update(TESTING=True)
    with app.app_context():
        db.create_all()
        city = City(name='Muscat', is_active=True)
        db.session.add(city); db.session.flush()
        admin = User(username='admin', role='admin', password_hash=generate_password_hash('StrongTestPassword'), is_active=True, city_id=city.id)
        van = User(username='van', role='van', password_hash='unused', is_active=True, city_id=city.id)
        warehouse = Warehouse(name='Central', code='CENTRAL', city_id=city.id, is_active=True)
        product = Product(name='Tea', sku='TEA', barcode='123', city_id=city.id, unit_price=10, is_active=True)
        db.session.add_all([admin, van, warehouse, product]); db.session.flush()
        db.session.add(Inventory(product_id=product.id, warehouse_id=warehouse.id, current_qty=10, reserved_qty=0))
        order = Order(city_id=city.id, sales_person_id=admin.id, customer_name='Test customer', status='pending', net_total=20)
        db.session.add(order); db.session.flush()
        db.session.add(OrderItem(order_id=order.id, product_id=product.id, product_name='Tea', product_barcode='123', ordered_qty=2, picked_qty=0, unit_price=10))
        db.session.commit()
        yield app, order.id, van.id
        db.session.remove(); db.drop_all()

def client(setup):
    c = setup[0].test_client()
    assert c.post('/login', json={'username':'admin','password':'StrongTestPassword'}).status_code == 200
    return c

def test_full_fulfillment(setup):
    c=client(setup); oid=setup[1]; base=f'/api/orders/{oid}'
    assert c.post(base+'/approve',json={}).status_code==200
    assert Inventory.query.first().reserved_qty == 2
    assert c.post(base+'/approve',json={}).status_code==400
    assert c.post(base+'/pick',json={'barcode':'123','quantity':3}).status_code==400
    assert c.post(base+'/pick',json={'barcode':'123','quantity':2}).status_code==200
    assert Inventory.query.first().reserved_qty == 2
    response=c.post(base+'/pack',json={}); assert response.status_code==200
    barcode=response.json['barcode']
    assert c.post(base+'/ready',json={}).status_code==200
    assert Inventory.query.first().current_qty==8
    assert Inventory.query.first().reserved_qty==0
    assert c.post(base+'/dispatch-scan',json={'barcode':'wrong','scan_type':'storekeeper'}).status_code==400
    assert c.post(base+'/dispatch-scan',json={'barcode':barcode,'scan_type':'storekeeper'}).status_code==200
    response=c.post(base+'/dispatch-scan',json={'barcode':barcode,'scan_type':'delivery','delivery_agent_id':setup[2]})
    assert response.status_code==200, response.json
    assert response.json['order_status']=='dispatched'
    assert AgentInventory.query.first().current_physical_qty==2
    assert c.post(base+'/dispatch-scan',json={'barcode':barcode,'scan_type':'delivery','delivery_agent_id':setup[2]}).status_code==400

def test_key_expiry_and_device_binding(setup):
    app,oid,_=setup
    user=User.query.filter_by(username='admin').first()
    key=ApiKey(user_id=user.id,api_key_hash=hash_api_key('test-key'),device_uuid='device-one',status='ACTIVE',expires_at=datetime.utcnow()+timedelta(days=1))
    db.session.add(key);db.session.commit()
    c=app.test_client()
    assert c.get('/api/orders',headers={'X-API-Key':'test-key'}).status_code==401
    assert c.get('/api/orders',headers={'X-API-Key':'test-key','X-Device-UUID':'device-one'}).status_code==200
    key.expires_at=datetime.utcnow()-timedelta(seconds=1);db.session.commit()
    assert c.get('/api/orders',headers={'X-API-Key':'test-key','X-Device-UUID':'device-one'}).status_code==401

def test_mobile_key_generation_and_revoke(setup):
    c=client(setup)
    response=c.post('/api-key/generate',json={'device_uuid':'phone'})
    assert response.status_code==200, response.json
    assert c.post('/api-key/revoke',json={'device_uuid':'phone'}).status_code==200

def test_session_401_and_dashboard(setup):
    c=setup[0].test_client()
    assert c.get('/session-check').status_code==401
    c=client(setup)
    assert c.get('/dashboard/').status_code==200
    assert c.get('/api/orders').status_code==200

def test_gpc_roundtrip(setup):
    from utils import encrypt_gpc_payload, decrypt_gpc_payload
    raw=encrypt_gpc_payload({'hello':'world'},b'test-secret')
    assert decrypt_gpc_payload(raw,b'test-secret')=={'hello':'world'}
    with pytest.raises(ValueError):decrypt_gpc_payload(raw,b'wrong-secret')

def test_order_retries_do_not_duplicate(setup):
    from models import Customer, OfflineSubmission
    c=client(setup)
    customer=Customer(name='Shop',phone='99999999',city_id=1,outstanding_balance=0)
    db.session.add(customer);db.session.commit()
    payload={'customer_id':customer.id,'client_order_id':'stable-phone-order-1','items':[{'product_id':1,'quantity':2}]}
    first=c.post('/api/orders/place',json=payload)
    assert first.status_code==200, first.json
    second=c.post('/api/orders/place',json=payload)
    assert second.status_code==200
    assert first.json['order_id']==second.json['order_id']
    assert OfflineSubmission.query.count()==1
    assert Customer.query.first().outstanding_balance==20

def test_invalid_order_quantity(setup):
    from models import Customer
    c=client(setup)
    customer=Customer(name='Shop',phone='99999999',city_id=1)
    db.session.add(customer);db.session.commit()
    for qty in [-1,0,1.5,True]:
        response=c.post('/api/orders/place',json={'customer_id':customer.id,'items':[{'product_id':1,'quantity':qty}]})
        assert response.status_code==400

def test_gpc_import_creates_orders_and_is_retry_safe(setup):
    from models import Customer
    from utils import import_gpc_export, encrypt_gpc_payload
    from flask import request
    admin=User.query.filter_by(username='admin').first()
    sales=User(username='sales',role='sales',password_hash='unused',city_id=1,is_active=True)
    customer=Customer(name='Shop',phone='99999999',city_id=1,outstanding_balance=0)
    db.session.add_all([sales,customer]);db.session.commit()
    data={'user_id':sales.id,'orders':[{'client_order_id':'offline-1','customer_id':customer.id,'items':[{'product_id':1,'quantity':2}]}]}
    encrypted=encrypt_gpc_payload(data,b'testing-master-secret')
    with setup[0].test_request_context('/api/admin/gpc/upload'):
        request.user=admin
        result=import_gpc_export(encrypted)
        assert result['accepted']==1, result
        assert import_gpc_export(encrypted)['accepted']==1
    assert Order.query.filter_by(sales_person_id=sales.id).count()==1

def test_api_login_returns_device_key(setup):
    c=setup[0].test_client()
    response=c.post('/api/login',json={'username':'admin','password':'StrongTestPassword','device_uuid':'phone-one'})
    assert response.status_code==200, response.json
    headers={'X-API-Key':response.json['api_key'],'X-Device-UUID':'phone-one'}
    assert c.get('/api/orders',headers=headers).status_code==200
    assert c.get('/api/orders',headers={**headers,'X-Device-UUID':'other-phone'}).status_code==401

def test_insufficient_stock_does_not_reserve(setup):
    c=client(setup)
    Inventory.query.first().current_qty=1;db.session.commit()
    assert c.post(f'/api/orders/{setup[1]}/approve',json={}).status_code==400
    assert Inventory.query.first().reserved_qty==0
    assert db.session.get(Order,setup[1]).status=='pending'

def test_wrong_role_cannot_approve(setup):
    c=setup[0].test_client()
    van=User.query.filter_by(username='van').first()
    van.password_hash=generate_password_hash('VanPassword123');db.session.commit()
    assert c.post('/login',json={'username':'van','password':'VanPassword123'}).status_code==200
    assert c.post(f'/api/orders/{setup[1]}/approve',json={}).status_code==403

def test_cross_city_fulfillment_forbidden(setup):
    c=client(setup)
    user=User.query.filter_by(username='admin').first()
    city=City(name='Other',is_active=True);db.session.add(city);db.session.flush()
    user.role='captain';user.city_id=city.id;db.session.commit()
    assert c.post(f'/api/orders/{setup[1]}/approve',json={}).status_code==403

def test_no_default_account_on_import(setup):
    assert User.query.count()==2
    assert User.query.filter_by(username='admin').first().password_hash != 'admin123'

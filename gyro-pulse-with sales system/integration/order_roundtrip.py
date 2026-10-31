"""Offline native catalog -> cloud proposal -> actual native approval compatibility.
Uses separate interpreters, real native services and private in-memory SQLite. NOT TLS/UAT.
"""

import argparse
import json
from catalog_roundtrip import ROOT, run, PRODUCE

SUBMIT = r"""
import sys,json
from flask import Flask
from uuid import uuid4
from models import db
from sync_core import Inbox,Outbox,Transport
from catalog_bridge import CatalogHead,CatalogApplication,apply_message
from field_orders import SubmittedOrder,enqueue_proposal
catalog=json.load(sys.stdin)
app=Flask(__name__);app.config['SQLALCHEMY_DATABASE_URI']='sqlite://';db.init_app(app)
with app.app_context():
    for model in [Inbox,Outbox,CatalogHead,CatalogApplication,SubmittedOrder]:model.__table__.create(db.engine)
    context=Transport('gyro',catalog['company_id'],catalog['instance_id'],catalog['office_id'])
    context.accept(catalog);db.session.commit();apply_message(context,catalog['message_id']);db.session.commit()
    payload=dict(schema_version=1,order_id=str(uuid4()),store_id=catalog['payload']['store']['id'],catalog_message_id=catalog['message_id'],customer_phone='+96800000000',customer_name='Synthetic Offline Check',items=[dict(product_id=catalog['payload']['items'][0]['id'],quantity=2,unit_price='1.250')])
    row=enqueue_proposal(context,payload,1);db.session.commit()
    assert enqueue_proposal(context,payload,1).message_id==row.message_id
    print(json.dumps(dict(catalog=catalog,order=json.loads(db.session.get(Outbox,row.message_id).envelope))))
"""
APPROVE = r"""
import sys,json
from flask import Flask
from decimal import Decimal
from uuid import uuid4
from retail_genie.extensions import db
from retail_genie.models import TenantContainer,Company,Store,CatalogProduct,InventoryBalance,InventoryMovement,User,OrderNumberSeries,SalesOrder,OrderPayment
from retail_genie.field_integration import FieldConnection
from retail_genie.field_orders import stage_message,review,context_for,FieldProposal,FieldReviewAudit
from retail_genie.realtime.service import initialize_realtime_registry
from retail_genie.tenancy.service import seed_tenant_data_policies
data=json.load(sys.stdin);catalog=data['catalog'];order=data['order']
app=Flask(__name__);app.config['SQLALCHEMY_DATABASE_URI']='sqlite://';db.init_app(app);initialize_realtime_registry(app)
with app.app_context():
    db.create_all()
    tenant=TenantContainer(name='Synthetic',slug='synthetic');db.session.add(tenant);db.session.flush();seed_tenant_data_policies(tenant.id)
    company=Company(id=catalog['company_id'],tenant_container_id=tenant.id,name='Synthetic',slug='synthetic');db.session.add(company);db.session.flush()
    store=Store(id=order['payload']['store_id'],tenant_container_id=tenant.id,company_id=company.id,name='Synthetic',code='SYN');db.session.add(store);db.session.flush()
    item=catalog['payload']['items'][0]
    product=CatalogProduct(id=item['id'],tenant_container_id=tenant.id,company_id=company.id,name=item['name'],price=Decimal(item['price']));db.session.add(product);db.session.flush()
    db.session.add(InventoryBalance(tenant_container_id=tenant.id,company_id=company.id,store_id=store.id,product_owner_company_id=company.id,product_id=product.id,quantity_on_hand=17))
    db.session.add(FieldConnection(company_id=company.id,instance_id=order['instance_id'],office_id=order['office_id']))
    actor=User(username='synthetic-reviewer',password_hash='unused',role='super_admin');db.session.add(actor)
    db.session.add(OrderNumberSeries(tenant_container_id=tenant.id,company_id=company.id,prefix='SYN-',next_number=1));db.session.commit()
    context=context_for(company.id);context.accept(order);db.session.commit()
    proposal=stage_message(company.id,order['message_id']);db.session.commit()
    assert SalesOrder.query.count()==0 and InventoryMovement.query.count()==0
    with app.test_request_context():
        native_id=review(actor,company.id,proposal.id,approve=True)
        assert review(actor,company.id,proposal.id,approve=True)==native_id
    assert FieldProposal.query.one().native_order_id==native_id
    assert SalesOrder.query.count()==1 and InventoryMovement.query.count()==1 and FieldReviewAudit.query.count()==1
    assert InventoryBalance.query.one().quantity_on_hand==15 and OrderPayment.query.count()==0
    print(json.dumps(dict(passed=True,source='real_native_catalog',cloud='immutable_proposal',native='actual_native_POS',duplicate_approval='one_order',stock_deductions=1,payments=0)))
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retail-python", required=True)
    parser.add_argument("--gyro-python", required=True)
    args = parser.parse_args()
    if (ROOT / "retail-genie/.env.retail-genie").exists():
        raise SystemExit("Use a clean isolated checkout without a live native env file")
    catalog = run(args.retail_python, PRODUCE, ROOT / "retail-genie")
    proposal = run(args.gyro_python, SUBMIT, ROOT / "gyro-pulse/server", catalog)
    print(run(args.retail_python, APPROVE, ROOT / "retail-genie", proposal).strip())


if __name__ == "__main__":
    main()

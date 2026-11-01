"""Offline REAL native-model -> envelope -> Gyro projection compatibility check.
Two independent Python environments, private in-memory SQLite, no external TLS/UAT claim.
Usage: python integration/catalog_roundtrip.py --retail-python /path/python --gyro-python /path/python
"""

import argparse
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PRODUCE = r"""
import json,sys
from flask import Flask
from decimal import Decimal
from uuid import uuid4
from retail_genie.extensions import db
from retail_genie.models.tenancy import TenantContainer,Company,Store
from retail_genie.models.catalog import CatalogProduct,InventoryBalance,InventoryMovement
from retail_genie.field_integration import FieldConnection
from retail_genie.field_catalog import enqueue_snapshot
from retail_genie.sync_core import decode
app=Flask(__name__);app.config['SQLALCHEMY_DATABASE_URI']='sqlite://';db.init_app(app)
with app.app_context():
    db.create_all()
    tenant=TenantContainer(name='Synthetic',slug='synthetic');db.session.add(tenant);db.session.flush()
    company=Company(name='Synthetic Office',slug='synthetic',tenant_container_id=tenant.id);db.session.add(company);db.session.flush()
    store=Store(name='Synthetic Store',code='SYN',tenant_container_id=tenant.id,company_id=company.id);db.session.add(store);db.session.flush()
    product=CatalogProduct(tenant_container_id=tenant.id,company_id=company.id,name='Synthetic Tea',price=Decimal('1.250'));db.session.add(product);db.session.flush()
    db.session.add(FieldConnection(company_id=company.id,office_id=str(uuid4()),instance_id=str(uuid4())))
    balance=InventoryBalance(tenant_container_id=tenant.id,company_id=company.id,store_id=store.id,product_owner_company_id=company.id,product_id=product.id,quantity_on_hand=17);db.session.add(balance);db.session.commit()
    row=enqueue_snapshot(company.id,store.id);db.session.commit()
    assert InventoryMovement.query.count()==0 and balance.quantity_on_hand==17
    print(row.envelope)
"""
APPLY = r"""
import json,sys
from flask import Flask
from sqlalchemy import inspect
from models import db
from sync_core import Inbox,Outbox,Transport
from catalog_bridge import CatalogHead,CatalogApplication,apply_message,projection
app=Flask(__name__);app.config['SQLALCHEMY_DATABASE_URI']='sqlite://';db.init_app(app)
envelope=json.load(sys.stdin)
with app.app_context():
    for model in [Inbox,Outbox,CatalogHead,CatalogApplication]:model.__table__.create(db.engine)
    context=Transport('gyro',envelope['company_id'],envelope['instance_id'],envelope['office_id'])
    first=context.accept(envelope);db.session.commit()
    assert context.accept(envelope)==first;db.session.commit()
    assert apply_message(context,envelope['message_id'])=='applied';db.session.commit()
    assert apply_message(context,envelope['message_id'])=='applied';db.session.commit()
    view=projection(context,envelope['payload']['store']['id'])
    assert view['payload']==envelope['payload'] and view['read_only'] is True
    assert view['payload']['items'][0]['price']=='1.250'
    assert view['payload']['items'][0]['on_hand']==17
    assert first['status']=='received' and Inbox.query.count()==1 and CatalogApplication.query.count()==1
    assert set(inspect(db.engine).get_table_names())=={'hybrid_sync_inbox','hybrid_sync_outbox','hybrid_catalog_heads','hybrid_catalog_applications'}
    print(json.dumps(dict(passed=True,source='actual_native_models',projection='read_only',receipt='received',legacy_stock_tables_created=False)))
"""


def run(python, code, root, input_data=None):
    env = {
        **os.environ,
        "PYTHONPATH": str(root),
        "SECRET_KEY": "offline-compatibility-check-" + "x" * 32,
        "DATABASE_URL": "sqlite://",
        "APP_ENV": "test",
        "REALTIME_DISPATCH_ENABLED": "false",
    }
    result = subprocess.run(
        [python, "-c", code],
        input=input_data,
        text=True,
        capture_output=True,
        env=env,
        cwd=root,
        timeout=60,
    )
    if result.returncode:
        raise SystemExit(
            "Offline catalog compatibility check failed; no production DB was used. "
            + result.stderr[-1500:]
        )
    return result.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retail-python", required=True)
    parser.add_argument("--gyro-python", required=True)
    args = parser.parse_args()
    if (ROOT / "retail-genie/.env.retail-genie").exists():
        raise SystemExit(
            "Refusing to load a live native environment file; use a clean isolated checkout."
        )
    envelope = run(args.retail_python, PRODUCE, ROOT / "retail-genie")
    # IPC only: synthetic payload never written as a repository dataset or credential file.
    print(run(args.gyro_python, APPLY, ROOT / "gyro-pulse/server", envelope).strip())


if __name__ == "__main__":
    main()

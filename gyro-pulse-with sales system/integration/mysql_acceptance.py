"""DESTRUCTIVE disposable-DB acceptance only. Never accepts an application/live DB name.
Run in EACH app's own interpreter with HYBRID_ALLOW_DISPOSABLE_MYSQL=1 and
HYBRID_MYSQL_TEST_URL=mysql+pymysql://.../hybrid_acceptance_<side>.
Native case also requires mysql/mysqldump tools and restores into a separate disposable DB.
"""

import argparse, json, os, sys, subprocess, shutil, traceback
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4
from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]


def configuration(side):
    value = os.environ.get("HYBRID_MYSQL_TEST_URL", "")
    url = make_url(value)
    if (
        os.environ.get("HYBRID_ALLOW_DISPOSABLE_MYSQL") != "1"
        or url.drivername != "mysql+pymysql"
        or url.database != "hybrid_acceptance_" + side
    ):
        raise RuntimeError("Explicit disposable MySQL database/consent required")
    return value, url


def gyro_mobile_http(value):
    """Actual MySQL-backed factory + Flask HTTP pairing/enrollment, not a SQLite fixture."""
    import html, re
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization, hashes

    if (ROOT / "gyro-pulse/server/.env").exists():
        raise RuntimeError("Refusing live cloud environment file")
    os.environ.update(
        APP_ENV="test",
        SECRET_KEY="disposable-ci-only-" + "x" * 32,
        DATABASE_URL=value,
        GYRO_DEPLOYMENT_MODE="dedicated",
        GYRO_COMPANY_ID=str(uuid4()),
        GYRO_INSTANCE_ID=str(uuid4()),
        GYRO_PUBLIC_BASE_URL="https://company.example.test",
    )
    os.environ.pop("CORS_ALLOWED_ORIGINS", None)
    from app import create_app
    from models import db, User
    from field_mobile import Device
    from mobile_crypto import b64, fingerprint
    from catalog_bridge import apply_message
    from sync_core import Transport, Outbox

    app = create_app()
    app.config["TESTING"] = True

    def bundle(response):
        assert response.status_code == 200
        return json.loads(
            html.unescape(
                re.search(
                    r"<textarea[^>]*>(.*?)</textarea>", response.text, re.S
                ).group(1)
            )
        )

    with app.app_context():
        db.drop_all()
        db.create_all()
        assert (
            app.test_cli_runner()
            .invoke(args=["bind-company", "--confirm-empty-database"])
            .exit_code
            == 0
        )
        user = User(
            username="acceptance-admin",
            password_hash="unused",
            role="admin",
            is_active=True,
        )
        db.session.add(user)
        db.session.commit()
        client = app.test_client()
        with client.session_transaction() as session:
            session["_user_id"] = str(user.id)
            session["_fresh"] = True
        assert client.get("/integrations").status_code == 200
        with client.session_transaction() as session:
            csrf = session["hybrid_csrf"]
        office = str(uuid4())
        grant = bundle(
            client.post(
                "/integrations",
                data=dict(action="issue", office_id=office, csrf_token=csrf),
            )
        )
        office_exchange = client.post("/api/v1/pairing/exchange", json=grant)
        assert office_exchange.status_code == 200
        office_token = office_exchange.json
        assert (
            client.post(
                "/integrations", data=dict(action="transport_enable", csrf_token=csrf)
            ).status_code
            == 200
        )
        key = ec.generate_private_key(ec.SECP256R1())
        pub = b64(
            key.public_key().public_bytes(
                serialization.Encoding.DER,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        )
        device_id = str(uuid4())
        grant = bundle(
            client.post(
                "/integrations/devices",
                data=dict(
                    action="issue",
                    device_id=device_id,
                    owner_id=user.id,
                    key_fingerprint=fingerprint(pub),
                    csrf_token=csrf,
                ),
            )
        )
        proof = b64(
            key.sign(
                (
                    "retail.hybrid.device.enroll.v1|"
                    + grant["grant_id"]
                    + "|"
                    + grant["pairing_code"]
                ).encode(),
                ec.ECDSA(hashes.SHA256()),
            )
        )
        data = dict(grant=grant, public_key=pub, proof=proof)
        response = client.post("/api/v1/devices/enroll", json=data)
        assert response.status_code == 200
        token = response.json
        assert client.post("/api/v1/devices/enroll", json=data).status_code == 401
        identity = (token["company_id"], token["instance_id"], token["office_id"])
        context = Transport("gyro", *identity)
        store_id = str(uuid4())
        product_id = str(uuid4())
        catalog = Transport("retail", *identity).envelope(
            "catalog.snapshot",
            dict(
                schema_version=1,
                mode="full",
                sequence=1,
                store=dict(id=store_id, name="Acceptance", code="CI"),
                captured_at=datetime.utcnow().isoformat() + "Z",
                currency=None,
                items=[
                    dict(
                        id=product_id,
                        sku="SYN",
                        barcode=None,
                        name="Synthetic",
                        category=None,
                        active=True,
                        price="1.250",
                        low_stock_price=None,
                        on_hand=20,
                        low_stock_threshold=3,
                    )
                ],
            ),
        )
        context.accept(catalog)
        db.session.commit()
        apply_message(context, catalog["message_id"])
        db.session.commit()
        order = dict(
            schema_version=1,
            order_id=str(uuid4()),
            store_id=store_id,
            catalog_message_id=catalog["message_id"],
            customer_phone="+96800000000",
            customer_name="Synthetic",
            items=[dict(product_id=product_id, quantity=2, unit_price="1.250")],
        )
        raw = json.dumps(
            dict(
                schema_version=1,
                company_id=identity[0],
                instance_id=identity[1],
                office_id=identity[2],
                device_id=device_id,
                order=order,
            )
        ).encode()
        wire = dict(
            body=b64(raw), signature=b64(key.sign(raw, ec.ECDSA(hashes.SHA256())))
        )
        headers = {
            "Authorization": "Bearer " + token["access_token"],
            "X-Company-ID": identity[0],
            "X-Instance-ID": identity[1],
            "X-Office-ID": identity[2],
            "X-Device-ID": device_id,
        }
        first = client.post("/api/v1/device/orders", json=wire, headers=headers)
        assert first.status_code == 200
        assert (
            client.post("/api/v1/device/orders", json=wire, headers=headers).json
            == first.json
        )
        assert Outbox.query.count() == 1
        # Trusted terminal native fact allows ONLY that exact offline-first content to
        # reconcile after catalog advance. It does not enqueue another sale proposal.
        from catalog_bridge import CatalogHead
        from sync_core import canonical
        import hashlib

        CatalogHead.query.one().message_id = str(uuid4())
        db.session.commit()
        offline_order = dict(order)
        offline_order["order_id"] = str(uuid4())
        raw_offline = json.dumps(
            dict(
                schema_version=1,
                company_id=identity[0],
                instance_id=identity[1],
                office_id=identity[2],
                device_id=device_id,
                order=offline_order,
            )
        ).encode()
        wire = dict(
            body=b64(raw_offline),
            signature=b64(key.sign(raw_offline, ec.ECDSA(hashes.SHA256()))),
        )
        assert (
            client.post("/api/v1/device/orders", json=wire, headers=headers).status_code
            == 409
        )
        decision = dict(
            schema_version=1,
            company_id=identity[0],
            instance_id=identity[1],
            office_id=identity[2],
            order_id=offline_order["order_id"],
            payload_sha256=hashlib.sha256(
                canonical(offline_order).encode()
            ).hexdigest(),
            device_id=device_id,
            state="approved",
            native_order_id=str(uuid4()),
        )
        oh = {
            "Authorization": "Bearer " + office_token["access_token"],
            "X-Company-ID": identity[0],
            "X-Instance-ID": identity[1],
            "X-Office-ID": identity[2],
        }
        assert (
            client.post(
                "/api/v1/devices/decisions", json=decision, headers=oh
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/api/v1/devices/decisions", json=decision, headers=oh
            ).status_code
            == 200
        )
        receipt = client.post("/api/v1/device/orders", json=wire, headers=headers)
        assert (
            receipt.status_code == 200
            and receipt.json["native_approval"] == "approved"
            and Outbox.query.count() == 1
        )

        assert (
            client.post(
                "/integrations/devices",
                data=dict(action="revoke", device_id=device_id, csrf_token=csrf),
            ).status_code
            == 200
        )
        assert (
            client.post("/api/v1/device/orders", json=wire, headers=headers).status_code
            == 401
        )
    return dict(
        mysql_office_pairing=True,
        mysql_device_enrollment=True,
        mysql_grant_replay_rejected=True,
        mysql_signed_order_dedup=True,
        mysql_device_revoke=True,
        mysql_native_decision_stale_reconciliation=True,
    )


def run(side):
    value, url = configuration(side)
    from flask import Flask

    if side == "gyro":
        sys.path.insert(0, str(ROOT / "gyro-pulse/server"))
        from models import db
        from sync_core import Inbox, Outbox, Transport

        app = Flask(__name__)
        app.config.update(
            SQLALCHEMY_DATABASE_URI=value,
            SQLALCHEMY_ENGINE_OPTIONS={
                "isolation_level": "REPEATABLE READ",
                "hide_parameters": True,
            },
        )
        db.init_app(app)
        with app.app_context():
            for model in [Inbox, Outbox]:
                model.__table__.drop(db.engine, checkfirst=True)
                model.__table__.create(db.engine)
            identity = [str(uuid4()) for _ in range(3)]
            env = Transport("retail", *identity).envelope(
                "catalog.snapshot", {"items": []}
            )
        barrier = Barrier(2)

        def receive():
            with app.app_context():
                barrier.wait(timeout=20)
                receipt = Transport("gyro", *identity).accept(env)
                db.session.commit()
                return receipt

        with ThreadPoolExecutor(max_workers=2) as pool:
            jobs = [pool.submit(receive) for _ in range(2)]
            receipts = [f.result(timeout=60) for f in jobs]
        with app.app_context():
            assert receipts[0] == receipts[1] and Inbox.query.count() == 1
            source = Transport("retail", *identity)
            row = source.enqueue(env)
            # MySQL's default DATETIME rounds fractional seconds. Make availability
            # explicitly past before testing simultaneous eligible lease claims.
            row.available_at = datetime.utcnow() - timedelta(seconds=2)
            db.session.commit()
        barrier = Barrier(2)

        def claim():
            with app.app_context():
                barrier.wait(timeout=20)
                rows = Transport("retail", *identity).claim(limit=1)
                db.session.commit()
                return rows

        with ThreadPoolExecutor(max_workers=2) as pool:
            jobs = [pool.submit(claim) for _ in range(2)]
            claims = [f.result(timeout=60) for f in jobs]
        count = sum(len(rows) for rows in claims)
        assert count == 1, "claims_count_" + str(count)
        # Bounded real transport load, not a claim of representative business/SLA load.
        import random, time
        from sqlalchemy.exc import OperationalError

        messages = [
            Transport("retail", *identity).envelope("catalog.snapshot", {"items": []})
            for _ in range(50)
        ]
        deliveries = messages * 4
        random.Random(7).shuffle(deliveries)

        def loaded_receive(message):
            for attempt in range(6):
                with app.app_context():
                    try:
                        receipt = Transport("gyro", *identity).accept(message)
                        db.session.commit()
                        return receipt
                    except OperationalError as error:
                        db.session.rollback()
                        if (
                            not getattr(error, "orig", None)
                            or error.orig.args[0] not in (1205, 1213)
                            or attempt == 5
                        ):
                            raise
                time.sleep(0.02 * (attempt + 1))

        started = time.monotonic()
        with ThreadPoolExecutor(max_workers=8) as pool:
            observed = list(pool.map(loaded_receive, deliveries))
        elapsed = time.monotonic() - started
        with app.app_context():
            assert Inbox.query.count() == 51
        assert (
            len(observed) == 200 and len({row["message_id"] for row in observed}) == 50
        )
        mobile = gyro_mobile_http(value)
        return dict(
            **mobile,
            real_mysql_concurrency=True,
            inbox_rows=51,
            concurrent_claims=1,
            load_deliveries=200,
            load_unique_messages=50,
            load_workers=8,
            load_elapsed_seconds=round(elapsed, 3),
            production_load_sla_accepted=False,
        )
    sys.path.insert(0, str(ROOT / "retail-genie"))
    os.environ.update(
        SECRET_KEY="disposable-ci-only-" + "x" * 32,
        DATABASE_URL=value,
        REALTIME_DISPATCH_ENABLED="false",
    )
    if (ROOT / "retail-genie/.env.retail-genie").exists():
        raise RuntimeError("Refusing live environment file")
    from retail_genie.extensions import db
    from retail_genie.field_mobile import decision_record
    from retail_genie.models import (
        TenantContainer,
        Company,
        Store,
        CatalogProduct,
        InventoryBalance,
        InventoryMovement,
        User,
        OrderNumberSeries,
        SalesOrder,
    )
    from retail_genie.field_integration import FieldConnection
    from retail_genie.field_orders import (
        stage_message,
        review,
        context_for,
        FieldProposal,
        FieldReviewAudit,
    )
    from retail_genie.tenancy.service import seed_tenant_data_policies
    from retail_genie.realtime.service import initialize_realtime_registry
    from retail_genie.sync_core import Transport

    app = Flask(__name__)
    app.secret_key = "disposable-ci-only-" + "x" * 32
    app.config.update(
        SQLALCHEMY_DATABASE_URI=value,
        SQLALCHEMY_ENGINE_OPTIONS={
            "isolation_level": "REPEATABLE READ",
            "hide_parameters": True,
        },
    )
    db.init_app(app)
    initialize_realtime_registry(app)
    with app.app_context():
        db.drop_all()
        db.create_all()
        tenant = TenantContainer(name="Acceptance", slug="acceptance")
        db.session.add(tenant)
        db.session.flush()
        seed_tenant_data_policies(tenant.id)
        company = Company(
            tenant_container_id=tenant.id, name="Acceptance", slug="acceptance"
        )
        db.session.add(company)
        db.session.flush()
        store = Store(
            tenant_container_id=tenant.id,
            company_id=company.id,
            name="Acceptance",
            code="TEST",
        )
        db.session.add(store)
        db.session.flush()
        product = CatalogProduct(
            tenant_container_id=tenant.id,
            company_id=company.id,
            name="Synthetic",
            price=Decimal("1.250"),
        )
        db.session.add(product)
        db.session.flush()
        db.session.add(
            InventoryBalance(
                tenant_container_id=tenant.id,
                company_id=company.id,
                store_id=store.id,
                product_owner_company_id=company.id,
                product_id=product.id,
                quantity_on_hand=20,
            )
        )
        actor = User(
            username="acceptance-admin", role="super_admin", password_hash="unused"
        )
        db.session.add(actor)
        connection = FieldConnection(
            company_id=company.id, instance_id=str(uuid4()), office_id=str(uuid4())
        )
        db.session.add(connection)
        db.session.add(
            OrderNumberSeries(
                tenant_container_id=tenant.id,
                company_id=company.id,
                prefix="CI-",
                next_number=1,
            )
        )
        db.session.commit()
        proposal = dict(
            schema_version=1,
            order_id=str(uuid4()),
            store_id=store.id,
            catalog_message_id=str(uuid4()),
            customer_phone="+96800000000",
            customer_name="Synthetic",
            items=[dict(product_id=product.id, quantity=2, unit_price="1.250")],
        )
        sender = Transport(
            "gyro", company.id, connection.instance_id, connection.office_id
        )
        env = sender.envelope("field.order", proposal)
        context_for(company.id).accept(env)
        db.session.commit()
        stage_message(company.id, env["message_id"])
        db.session.commit()
        company_id = company.id
        actor_id = actor.id
        business_id = proposal["order_id"]
    barrier = Barrier(2)

    def approve():
        with app.test_request_context():
            actor = db.session.get(User, actor_id)
            barrier.wait(timeout=20)
            return review(actor, company_id, business_id, approve=True)

    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(approve) for _ in range(2)]
        ids = [f.result(timeout=60) for f in jobs]
    with app.app_context():
        assert (
            ids[0] == ids[1]
            and SalesOrder.query.count() == 1
            and InventoryMovement.query.count() == 1
            and FieldReviewAudit.query.count() == 1
        )
        assert (
            InventoryBalance.query.one().quantity_on_hand == 18
            and FieldProposal.query.one().native_order_id == ids[0]
        )
        native_fact = decision_record(company_id, business_id)
        assert (
            native_fact["state"] == "approved"
            and native_fact["native_order_id"] == ids[0]
        )
        # An actual consistent logical dump and restore, not a copied SQLite fixture.
        if not shutil.which("mysqldump") or not shutil.which("mysql"):
            raise RuntimeError(
                "Actual mysql/mysqldump tools required for restore evidence"
            )
        env = {**os.environ, "MYSQL_PWD": url.password or ""}
        common = [
            "--host",
            url.host or "127.0.0.1",
            "--port",
            str(url.port or 3306),
            "--user",
            url.username or "root",
        ]
        dump = subprocess.run(
            [
                "mysqldump",
                *common,
                "--single-transaction",
                "--skip-lock-tables",
                "--no-tablespaces",
                "--set-gtid-purged=OFF",
                "--column-statistics=0",
                url.database,
            ],
            capture_output=True,
            env=env,
            timeout=90,
        )
        if dump.returncode or len(dump.stdout) > 40 * 1024 * 1024:
            raise RuntimeError("MySQL backup failed/bounds exceeded")
        restored = "hybrid_acceptance_restored"
        from sqlalchemy import create_engine, text

        admin = create_engine(url.set(database="mysql"), hide_parameters=True)
        with admin.begin() as conn:
            conn.exec_driver_sql("DROP DATABASE IF EXISTS hybrid_acceptance_restored")
            conn.exec_driver_sql(
                "CREATE DATABASE hybrid_acceptance_restored CHARACTER SET utf8mb4"
            )
        result = subprocess.run(
            ["mysql", *common, restored],
            input=dump.stdout,
            capture_output=True,
            env=env,
            timeout=90,
        )
        if result.returncode:
            raise RuntimeError("MySQL restore failed")
        engine = create_engine(url.set(database=restored), hide_parameters=True)
        with engine.connect() as conn:
            assert (
                conn.exec_driver_sql("SELECT COUNT(*) FROM sales_orders").scalar_one()
                == 1
            )
            assert (
                conn.exec_driver_sql(
                    "SELECT quantity_on_hand FROM inventory_balances"
                ).scalar_one()
                == 18
            )
            assert (
                conn.exec_driver_sql(
                    "SELECT COUNT(*) FROM inventory_movements"
                ).scalar_one()
                == 1
            )
            assert (
                conn.execute(
                    text(
                        "SELECT native_order_id FROM hybrid_field_proposals WHERE id=:id"
                    ),
                    {"id": business_id},
                ).scalar_one()
                == ids[0]
            )
        engine.dispose()
        admin.dispose()
    return dict(
        real_mysql_concurrency=True,
        native_orders=1,
        stock_deductions=1,
        backup_restore=True,
        restored_mapping_matches=True,
        mysql_native_terminal_record_verified=True,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("side", choices=["gyro", "retail"])
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        checks = run(args.side)
        passed = True
    except Exception as error:
        # Never print URL/password or SQL parameter dumps.
        import traceback

        checks = {
            "failure_type": type(error).__name__,
            "frames": [
                dict(
                    file=Path(frame.filename).name,
                    line=frame.lineno,
                    function=frame.name,
                )
                for frame in traceback.extract_tb(error.__traceback__)[-8:]
            ],
        }
        original = getattr(error, "orig", None)
        if original and original.args and type(original.args[0]) is int:
            checks["sql_error_code"] = original.args[0]
        passed = False
    report = dict(
        schema_version=1,
        side=args.side,
        passed=passed,
        checks=checks,
        commit=os.environ.get("GITHUB_SHA"),
        run_url=os.environ.get("ACCEPTANCE_RUN_URL"),
        recorded_at=datetime.utcnow().isoformat() + "Z",
        production_accepted=False,
    )
    Path(args.output).write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
    annotation = "notice" if passed else "error"
    print(
        "::"
        + annotation
        + " title=Hybrid observed "
        + args.side
        + "::"
        + json.dumps(report)
    )
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()

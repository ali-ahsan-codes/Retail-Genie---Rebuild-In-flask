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
from datetime import datetime
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
            source.enqueue(env)
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
        assert sum(len(rows) for rows in claims) == 1
        return dict(real_mysql_concurrency=True, inbox_rows=1, concurrent_claims=1)
    sys.path.insert(0, str(ROOT / "retail-genie"))
    os.environ.update(
        SECRET_KEY="disposable-ci-only-" + "x" * 32,
        DATABASE_URL=value,
        REALTIME_DISPATCH_ENABLED="false",
    )
    if (ROOT / "retail-genie/.env.retail-genie").exists():
        raise RuntimeError("Refusing live environment file")
    from retail_genie.extensions import db
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

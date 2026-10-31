"""Office unit tests: fake HTTPS exchange, not live MySQL/TLS/UAT acceptance."""

import os, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.update(
    SECRET_KEY="office-test-secret-" + "x" * 32,
    DATABASE_URL="sqlite://",
    REALTIME_DISPATCH_ENABLED="false",
)
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from urllib.error import HTTPError
import pytest
from cryptography.fernet import Fernet
from retail_genie import create_app
from retail_genie.extensions import db
from retail_genie import field_integration as field


@pytest.fixture
def office():
    app = create_app(
        {
            "TESTING": True,
            "REALTIME_DISPATCH_ENABLED": False,
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
            "FIELD_INTEGRATION_KEY": Fernet.generate_key().decode(),
            "FIELD_GYRO_ALLOWED_ORIGINS": "https://cloud.example.test",
        }
    )
    with app.app_context():
        field.FieldConnection.__table__.create(db.engine)
        field.FieldIntegrationAudit.__table__.create(db.engine)
        row = field.FieldConnection(company_id=str(uuid4()), office_id=str(uuid4()))
        db.session.add(row)
        db.session.commit()
        bundle = dict(
            schema_version=1,
            company_id=row.company_id,
            instance_id=str(uuid4()),
            office_id=row.office_id,
            base_url="https://cloud.example.test",
            grant_id=str(uuid4()),
            pairing_code="p" * 43,
            expires_at="2027-01-01T00:00:00Z",
            scopes=["connection:read"],
        )
        yield app, row, bundle
        db.session.remove()
        field.FieldIntegrationAudit.__table__.drop(db.engine)
        field.FieldConnection.__table__.drop(db.engine)


def reply(bundle):
    return dict(
        schema_version=1,
        company_id=bundle["company_id"],
        instance_id=bundle["instance_id"],
        office_id=bundle["office_id"],
        credential_id=str(uuid4()),
        access_token="a" * 43,
        expires_at=(datetime.now(timezone.utc) + timedelta(days=30))
        .isoformat()
        .replace("+00:00", "Z"),
        scopes=["connection:read"],
    )


def test_success_encrypted_and_pinned(office, monkeypatch):
    app, row, bundle = office
    token = reply(bundle)
    monkeypatch.setattr(field, "exchange_http", lambda base, payload: token)
    field.enroll(row, bundle)
    assert (
        row.instance_id == bundle["instance_id"] and row.base_url == bundle["base_url"]
    )
    assert token["access_token"] not in row.credential_encrypted
    assert (
        field.cipher().decrypt(row.credential_encrypted.encode()).decode()
        == token["access_token"]
    )
    with pytest.raises(ValueError):
        field.enroll(row, {**bundle, "instance_id": str(uuid4())})


@pytest.mark.parametrize(
    "case",
    ["company", "office", "origin", "lan", "http", "scope", "duplicate", "no_key"],
)
def test_fail_before_network(office, monkeypatch, case):
    app, row, bundle = office
    calls = []
    monkeypatch.setattr(field, "exchange_http", lambda *args: calls.append(args))
    if case in {"company", "office"}:
        bundle[case + "_id"] = str(uuid4())
    elif case == "origin":
        bundle["base_url"] = "https://attacker.example.test"
    elif case == "lan":
        bundle["base_url"] = "https://192.168.1.20"
    elif case == "http":
        bundle["base_url"] = "http://cloud.example.test"
    elif case == "scope":
        bundle["scopes"] = ["orders:write"]
    elif case == "no_key":
        app.config["FIELD_INTEGRATION_KEY"] = "bad-key"
    else:
        with pytest.raises(ValueError):
            field.loads('{"a":1,"a":2}')
        return
    with pytest.raises(ValueError):
        field.enroll(row, bundle)
    assert not calls and row.credential_encrypted is None


@pytest.mark.parametrize(
    "case",
    [
        "company_id",
        "instance_id",
        "office_id",
        "scopes",
        "expiry",
        "token",
        "version",
        "unknown",
    ],
)
def test_bad_response_not_persisted(office, monkeypatch, case):
    app, row, bundle = office
    value = reply(bundle)
    if case in {"company_id", "instance_id", "office_id"}:
        value[case] = str(uuid4())
    elif case == "scopes":
        value["scopes"] = ["stock:write"]
    elif case == "expiry":
        value["expires_at"] = "2001-01-01T00:00:00Z"
    elif case == "token":
        value["access_token"] = "short"
    elif case == "version":
        value["schema_version"] = True
    else:
        value["other"] = "unexpected"
    monkeypatch.setattr(field, "exchange_http", lambda *args: value)
    with pytest.raises(ValueError):
        field.enroll(row, bundle)
    assert (
        db.session.get(field.FieldConnection, row.company_id).credential_encrypted
        is None
    )


def test_redirects_disallowed():
    assert (
        field.NoRedirect().redirect_request(
            None, None, 302, "Found", {}, "https://evil.example.test"
        )
        is None
    )


def test_native_ui_csrf_and_auth(office):
    app, _, _ = office
    c = app.test_client()
    assert c.get("/settings/field-integration").status_code in {302, 401}
    assert (
        c.post("/settings/field-integration", data={"action": "initialize"}).status_code
        == 400
    )


def test_http_exchange_exact_target_and_size_limit(office, monkeypatch):
    app, row, bundle = office
    calls = []

    class Headers:
        def get_content_type(self):
            return "application/json"

    class Response:
        status = 200
        headers = Headers()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, limit):
            assert limit == 16385
            return b"x" * 16385

    class Opener:
        def open(self, request, timeout):
            calls.append(request)
            assert (
                request.full_url == "https://cloud.example.test/api/v1/pairing/exchange"
            )
            assert timeout == 10
            assert request.method == "POST"
            assert bundle["pairing_code"] not in request.full_url
            return Response()

    monkeypatch.setattr(field, "build_opener", lambda *handlers: Opener())
    with pytest.raises(ValueError):
        field.enroll(row, bundle)
    assert len(calls) == 1 and row.credential_encrypted is None


def test_success_audit_contains_no_secrets(office, monkeypatch):
    app, row, bundle = office
    response = reply(bundle)
    monkeypatch.setattr(field, "exchange_http", lambda *args: response)
    field.enroll(row, bundle, actor_id="test-office-admin")
    audit = field.FieldIntegrationAudit.query.one()
    assert (audit.company_id, audit.office_id, audit.actor_id) == (
        row.company_id,
        row.office_id,
        "test-office-admin",
    )
    assert response["access_token"] not in str(audit.__dict__)

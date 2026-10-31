from datetime import datetime, timedelta
import html, json, re
from uuid import uuid4
import pytest
from test_dedicated_recovery import dedicated_app
from models import db, User
from integration_api import Grant, Credential, Office, Audit


@pytest.fixture
def paired_app(dedicated_app):
    runner = dedicated_app.test_cli_runner()
    assert (
        runner.invoke(args=["bind-company", "--confirm-empty-database"]).exit_code == 0
    )
    user = User(
        username="pair-admin", password_hash="unused", role="admin", is_active=True
    )
    db.session.add(user)
    db.session.commit()
    client = dedicated_app.test_client()
    with client.session_transaction() as s:
        s["_user_id"] = str(user.id)
        s["_fresh"] = True
    return dedicated_app, client, str(uuid4())


def issue(fixture):
    app, client, office = fixture
    assert client.get("/integrations").status_code == 200
    with client.session_transaction() as s:
        csrf = s["hybrid_csrf"]
    r = client.post(
        "/integrations",
        data={"action": "issue", "office_id": office, "csrf_token": csrf},
    )
    assert r.status_code == 200, r.data
    assert r.headers["Cache-Control"] == "no-store"
    return json.loads(
        html.unescape(
            re.search(r"<textarea[^>]*>(.*?)</textarea>", r.text, re.S).group(1)
        )
    )


def exchange(fixture, bundle):
    return fixture[1].post("/api/v1/pairing/exchange", json=bundle)


def headers(value):
    return {
        "Authorization": "Bearer " + value["access_token"],
        "X-Company-ID": value["company_id"],
        "X-Instance-ID": value["instance_id"],
        "X-Office-ID": value["office_id"],
    }


def test_full_rotation_and_revoke(paired_app):
    bundle = issue(paired_app)
    app, c, _ = paired_app
    response = exchange(paired_app, bundle)
    assert response.status_code == 200
    first = response.json
    assert bundle["pairing_code"] not in str(Grant.query.first().__dict__)
    assert first["access_token"] not in str(Credential.query.first().__dict__)
    assert (
        c.get("/api/v1/integration/status", headers=headers(first)).json[
            "business_sync_enabled"
        ]
        is False
    )
    assert exchange(paired_app, bundle).status_code == 401
    pending = issue(paired_app)
    assert (
        c.get("/api/v1/integration/status", headers=headers(first)).status_code == 200
    )
    second = exchange(paired_app, pending).json
    assert (
        c.get("/api/v1/integration/status", headers=headers(first)).status_code == 401
    )
    assert (
        c.get("/api/v1/integration/status", headers=headers(second)).status_code == 200
    )
    with c.session_transaction() as s:
        csrf = s["hybrid_csrf"]
    assert (
        c.post(
            "/integrations", data={"action": "revoke", "csrf_token": csrf}
        ).status_code
        == 200
    )
    assert (
        c.get("/api/v1/integration/status", headers=headers(second)).status_code == 401
    )
    assert Audit.query.count() == 5


@pytest.mark.parametrize(
    "key,value",
    [
        ("company_id", str(uuid4())),
        ("instance_id", str(uuid4())),
        ("office_id", str(uuid4())),
        ("base_url", "https://other.example.test"),
        ("scopes", ["orders:write"]),
        ("schema_version", True),
        ("pairing_code", "x" * 43),
    ],
)
def test_tampered_pairing_rejected_without_consumption(paired_app, key, value):
    bundle = issue(paired_app)
    bad = {**bundle, key: value}
    assert exchange(paired_app, bad).status_code == 401
    assert exchange(paired_app, bundle).status_code == 200


@pytest.mark.parametrize(
    "kind",
    [
        "expired_grant",
        "revoked_grant",
        "expired_bearer",
        "wrong_company",
        "wrong_instance",
        "wrong_office",
        "legacy_key",
    ],
)
def test_denials(paired_app, kind):
    bundle = issue(paired_app)
    app, c, _ = paired_app
    if kind.endswith("_grant"):
        grant = Grant.query.first()
        if kind == "expired_grant":
            grant.expires_at = datetime.utcnow() - timedelta(seconds=1)
        else:
            grant.revoked_at = datetime.utcnow()
        db.session.commit()
        assert exchange(paired_app, bundle).status_code == 401
        return
    response = exchange(paired_app, bundle).json
    h = headers(response)
    if kind == "expired_bearer":
        Credential.query.first().expires_at = datetime.utcnow() - timedelta(seconds=1)
        db.session.commit()
    elif kind == "legacy_key":
        h = {"X-API-Key": "legacy-role-key"}
    else:
        h["X-" + kind.removeprefix("wrong_").title() + "-ID"] = str(uuid4())
    assert c.get("/api/v1/integration/status", headers=h).status_code == 401


def test_csrf_pin_supersession_and_json_limits(paired_app):
    app, c, office = paired_app
    assert (
        c.post(
            "/integrations", data={"action": "issue", "office_id": office}
        ).status_code
        == 400
    )
    assert (
        c.post(
            "/integrations", data={"action": "issue", "csrf_token": "💀"}
        ).status_code
        == 400
    )
    old = issue(paired_app)
    new = issue(paired_app)
    assert exchange(paired_app, old).status_code == 401
    with c.session_transaction() as s:
        csrf = s["hybrid_csrf"]
    assert (
        c.post(
            "/integrations",
            data={"action": "issue", "office_id": str(uuid4()), "csrf_token": csrf},
        ).status_code
        == 400
    )
    assert (
        c.post(
            "/api/v1/pairing/exchange",
            data='{"schema_version":1,"schema_version":1}',
            content_type="application/json",
        ).status_code
        == 401
    )
    assert (
        c.post(
            "/api/v1/pairing/exchange",
            data="x" * 16385,
            content_type="application/json",
        ).status_code
        == 413
    )
    assert exchange(paired_app, new).status_code == 200


def test_anonymous_admin_denied(paired_app):
    app, _, _ = paired_app
    anonymous = app.test_client()
    assert anonymous.get("/integrations").status_code == 403
    assert anonymous.post("/integrations", data={"action": "revoke"}).status_code == 403
    assert anonymous.get("/api/v1/integration/status").status_code == 401
    assert (
        anonymous.get("/api/v1/integration/status?access_token=abc").status_code == 401
    )
    assert anonymous.post("/api/products", json={}).status_code == 409


@pytest.mark.parametrize("role,active", [("viewer", True), ("admin", False)])
def test_inactive_or_non_admin_cannot_issue(paired_app, role, active):
    app, c, _ = paired_app
    user = User.query.filter_by(username="pair-admin").one()
    user.role = role
    user.is_active = active
    db.session.commit()
    assert c.get("/integrations").status_code == 403


def test_schema_initialization_explicit(paired_app):
    app, c, _ = paired_app
    Grant.__table__.drop(db.engine)
    assert c.get("/integrations").status_code == 503
    result = app.test_cli_runner().invoke(args=["init-field-pairing"])
    assert result.exit_code == 0, result.output
    assert c.get("/integrations").status_code == 200


@pytest.mark.parametrize(
    "value", ["https://cloud.example.test?", "https://cloud.example.test#"]
)
def test_empty_query_or_fragment_not_an_origin(value):
    from dedicated import origin as config_origin
    from integration_contract import origin as contract_origin

    for validate in [config_origin, contract_origin]:
        with pytest.raises(ValueError):
            validate(value)

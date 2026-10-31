from uuid import uuid4
import pytest
from app import create_app
from models import db, User
from dedicated import DeploymentBinding, origin


@pytest.fixture
def dedicated_app(monkeypatch):
    monkeypatch.setenv('APP_ENV','test')
    monkeypatch.setenv('SECRET_KEY','dedicated-test-only-'+'x'*32)
    monkeypatch.setenv('DATABASE_URL','sqlite://')
    monkeypatch.setenv('GYRO_DEPLOYMENT_MODE','dedicated')
    monkeypatch.setenv('GYRO_COMPANY_ID',str(uuid4()))
    monkeypatch.setenv('GYRO_INSTANCE_ID',str(uuid4()))
    monkeypatch.setenv('GYRO_PUBLIC_BASE_URL','https://company.example.test')
    monkeypatch.delenv('CORS_ALLOWED_ORIGINS',raising=False)
    app=create_app();app.config['TESTING']=True
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove();db.drop_all()


def test_health_without_binding_but_business_fails_closed(dedicated_app):
    client=dedicated_app.test_client()
    assert client.get('/health').status_code==200
    assert client.get('/api/v1/hybrid/status').status_code==503
    assert client.post('/api/products',json={}).status_code==503


def test_empty_binding_idempotent_then_blocks_legacy_stock(dedicated_app):
    runner=dedicated_app.test_cli_runner()
    for _ in range(2):
        result=runner.invoke(args=['bind-company','--confirm-empty-database'])
        assert result.exit_code==0,result.output
    assert DeploymentBinding.query.count()==1
    client=dedicated_app.test_client()
    assert client.get('/api/v1/hybrid/status').json['business_sync_enabled'] is False
    assert client.post('/api/products',json={}).status_code==409
    assert client.get('/uploads/old.gpc').status_code==409


def test_nonempty_database_cannot_be_adopted(dedicated_app):
    db.session.add(User(username='existing',password_hash='unused',role='admin',is_active=True));db.session.commit()
    result=dedicated_app.test_cli_runner().invoke(args=['bind-company','--confirm-empty-database'])
    assert result.exit_code!=0 and DeploymentBinding.query.count()==0


def test_binding_mismatch_never_reassigned(dedicated_app):
    runner=dedicated_app.test_cli_runner();assert runner.invoke(args=['bind-company','--confirm-empty-database']).exit_code==0
    original=DeploymentBinding.query.one().company_id
    dedicated_app.config['GYRO_COMPANY_ID']=str(uuid4())
    assert dedicated_app.test_client().get('/api/v1/hybrid/status').status_code==503
    assert runner.invoke(args=['bind-company','--confirm-empty-database']).exit_code!=0
    assert DeploymentBinding.query.one().company_id==original


@pytest.mark.parametrize('value',['http://office.test','https://user:secret@office.test','https://office.test/path','https://office.test?key=x','https://office.test/#frag','*','https://office.test:99999','https://*','https://*.example.test','https://foo%2Fbar'])
def test_invalid_origin_rejected(value):
    with pytest.raises(ValueError):origin(value)


def test_missing_identity_rejected(dedicated_app,monkeypatch):
    monkeypatch.delenv('GYRO_COMPANY_ID')
    with pytest.raises(ValueError):create_app()


def test_dedicated_does_not_trust_forwarded_host(dedicated_app):
    assert dedicated_app.test_cli_runner().invoke(args=['bind-company','--confirm-empty-database']).exit_code==0
    with dedicated_app.test_request_context('/api/v1/hybrid/status',headers={'X-Forwarded-Host':'attacker.test'}):
        from flask import request
        assert request.host!='attacker.test'


def test_no_default_secret_in_dedicated_mode(dedicated_app,monkeypatch):
    monkeypatch.delenv("SECRET_KEY")
    with pytest.raises(ValueError):create_app()

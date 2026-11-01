"""Recovered Phase 2A: one company/instance/database, explicit binding, fail-closed legacy access.
No scheduler, pairing, stock ledger, automatic schema creation or business sync here.
"""
import os
import ipaddress
import re
from urllib.parse import urlsplit
from uuid import UUID
import click
from flask import jsonify, request
from sqlalchemy import inspect, select, literal
from sqlalchemy.exc import SQLAlchemyError
from models import db


class DeploymentBinding(db.Model):
    __tablename__ = 'hybrid_deployment_binding'
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.String(36), nullable=False)
    instance_id = db.Column(db.String(36), nullable=False)
    public_origin = db.Column(db.String(300), nullable=False)
    schema_version = db.Column(db.Integer, nullable=False, default=1)
    __table_args__ = {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8mb4'}


def uid(value):
    try:
        parsed = UUID(value)
    except (ValueError, TypeError, AttributeError):
        raise ValueError('A canonical non-zero UUID is required') from None
    if not isinstance(value, str) or str(parsed) != value or parsed.int == 0:
        raise ValueError('A canonical non-zero UUID is required')
    return value


def origin(value):
    if not isinstance(value, str) or '?' in value or '#' in value:
        raise ValueError('An HTTPS origin without query or fragment is required')
    if not isinstance(value, str) or len(value) > 300 or any(ord(c) <= 32 for c in value):
        raise ValueError('Explicit HTTPS public origin required')
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise ValueError('Invalid public origin') from None
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or parsed.query or parsed.fragment or parsed.path not in {'', '/'}
            or (port is not None and not 1 <= port <= 65535)):
        raise ValueError('HTTPS origin only, without credentials, path, query or fragment')
    host = parsed.hostname
    if '%' in host:
        raise ValueError('Encoded/wildcard hostname is not allowed')
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if len(host) > 253 or not all(re.fullmatch(r'[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?', label) for label in host.split('.')):
            raise ValueError('Explicit DNS hostname or IP address required; no wildcards')
    return value.rstrip('/')


def configure(app):
    mode = os.environ.get('GYRO_DEPLOYMENT_MODE', 'standalone')
    if mode not in {'standalone', 'dedicated'}:
        raise ValueError('GYRO_DEPLOYMENT_MODE must be standalone or dedicated')
    app.config['GYRO_DEPLOYMENT_MODE'] = mode
    if mode == 'dedicated':
        if len(os.environ.get('SECRET_KEY', '')) < 32:
            raise ValueError('Dedicated mode requires an independent SECRET_KEY of at least 32 characters')
        if os.environ.get('APP_ENV') == 'production' and len(os.environ.get('JWT_SECRET_KEY', '')) < 32:
            raise ValueError('Dedicated production requires an independent JWT_SECRET_KEY of at least 32 characters')
        app.config.update(GYRO_COMPANY_ID=uid(os.environ.get('GYRO_COMPANY_ID')),
                          GYRO_INSTANCE_ID=uid(os.environ.get('GYRO_INSTANCE_ID')),
                          GYRO_PUBLIC_BASE_URL=origin(os.environ.get('GYRO_PUBLIC_BASE_URL')))
        if not os.environ.get('DATABASE_URL'):
            raise ValueError('Dedicated deployment requires an explicit separate DATABASE_URL')
        if os.environ.get('APP_ENV') == 'production' and not os.environ['DATABASE_URL'].startswith('mysql+pymysql://'):
            raise ValueError('Dedicated production requires explicit MySQL/PyMySQL; SQLite is test-only')
    return mode


def expected(app):
    return (app.config['GYRO_COMPANY_ID'], app.config['GYRO_INSTANCE_ID'], app.config['GYRO_PUBLIC_BASE_URL'])


def binding_matches(app):
    row = db.session.get(DeploymentBinding, 1)
    return bool(row and row.schema_version == 1 and
                (row.company_id, row.instance_id, row.public_origin) == expected(app))


def register(app):
    @app.before_request
    def dedicated_guard():
        if app.config['GYRO_DEPLOYMENT_MODE'] != 'dedicated' or request.endpoint == 'health_check':
            return None
        try:
            matches = binding_matches(app)
        except SQLAlchemyError:
            db.session.rollback()
            matches = False
        if not matches:
            return jsonify(error='Dedicated binding absent/mismatched; operator recovery required', production_ready=False), 503
        # Until explicit reviewed adapters exist, NONE of the legacy business endpoints are safe.
        if request.endpoint not in {'auth.login', 'api.login', 'auth.logout', 'hybrid_status', 'integration.manage', 'integration.exchange', 'integration.status', 'integration.sync_receive', 'integration.sync_pull', 'integration.sync_ack', 'integration.catalog_snapshot', 'integration.orders_manage', 'mobile.manage', 'mobile.enroll', 'mobile.catalog', 'mobile.submit', 'mobile.registry', 'mobile.publish_decision'} and request.endpoint is not None:
            return jsonify(error='Legacy business access disabled in connected mode', authority='retail-genie'), 409
        return None

    @app.get('/api/v1/hybrid/status')
    def hybrid_status():
        if app.config['GYRO_DEPLOYMENT_MODE'] != 'dedicated':
            return jsonify(error='Dedicated deployment not configured'), 409
        return jsonify(schema_version=1, company_id=app.config['GYRO_COMPANY_ID'],
                       instance_id=app.config['GYRO_INSTANCE_ID'], inventory_authority='retail-genie',
                       business_sync_enabled=False, pairing_available=all(inspect(db.engine).has_table(name) for name in ['hybrid_integration_office','hybrid_pairing_grants','hybrid_integration_credentials','hybrid_integration_audit']), production_ready=False)

    @app.cli.command('init-deployment-binding')
    def initialize():
        DeploymentBinding.__table__.create(db.engine, checkfirst=True)
        click.echo('Binding table ready. No company is trusted automatically.')

    @app.cli.command('bind-company')
    @click.option('--confirm-empty-database', is_flag=True, required=True)
    def bind(confirm_empty_database):
        if app.config['GYRO_DEPLOYMENT_MODE'] != 'dedicated':
            raise click.ClickException('Configure dedicated mode first')
        try:
            row = db.session.get(DeploymentBinding, 1)
            if row:
                if not binding_matches(app):
                    raise click.ClickException('Existing identity cannot be reassigned; reviewed migration required')
                click.echo('Already bound to the same identity; no changes.')
                return
            inspector = inspect(db.engine)
            names = set(inspector.get_table_names())
            known = set(db.metadata.tables)
            if names - known:
                raise click.ClickException('Unknown tables present; refuse to adopt an unverified database')
            for name in names - {DeploymentBinding.__tablename__}:
                table = db.metadata.tables[name]
                if db.session.execute(select(literal(1)).select_from(table).limit(1)).first():
                    raise click.ClickException('Database contains rows; binding requires a separate empty database')
            db.session.add(DeploymentBinding(id=1, company_id=expected(app)[0], instance_id=expected(app)[1],
                                             public_origin=expected(app)[2], schema_version=1))
            db.session.commit()
            click.echo('Dedicated identity bound; legacy business writers remain disabled.')
        except SQLAlchemyError:
            db.session.rollback()
            raise click.ClickException('Binding failed; initialize schema and retry the SAME identity') from None

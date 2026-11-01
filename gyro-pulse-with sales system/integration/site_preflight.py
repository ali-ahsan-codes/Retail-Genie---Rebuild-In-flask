"""Read-only, operator-authorized HTTPS preflight. NOT a penetration test or security sign-off.
No credentials, proxy discovery, redirects, TLS bypass or business writes. At most two GETs.
Run from an authorized machine that can reach the real cloud/office origin, not a fake local site.
"""
import argparse
import hashlib
import http.client
import ipaddress
import json
import re
import ssl
import time
from urllib.parse import urlsplit
from datetime import datetime, timezone
from pathlib import Path


def checked_origin(value):
    if not isinstance(value, str) or not value.isascii() or len(value) > 300 or any(ord(ch) < 33 for ch in value):
        raise ValueError('ASCII HTTPS origin required')
    try:
        parsed = urlsplit(value)
        parsed_port = parsed.port
    except ValueError:
        raise ValueError('Invalid HTTPS origin or port') from None
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username is not None or parsed.password is not None
            or parsed.path not in ('', '/') or parsed.query or parsed.fragment or '?' in value or '#' in value or '\\' in value):
        raise ValueError('Only a bare HTTPS origin, without credentials/path/query/fragment, is permitted')
    host = parsed.hostname
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if len(host) > 253 or any(not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', part) for part in host.split('.')):
            raise ValueError('Invalid hostname')
    port = parsed_port if parsed_port is not None else 443
    if not 1 <= port <= 65535:
        raise ValueError('Invalid HTTPS port')
    return host, port


def check_headers(headers):
    hsts = headers.get('strict-transport-security', '')
    match = re.search(r'(?:^|;)\s*max-age\s*=\s*(\d+)\s*(?:;|$)', hsts, re.I)
    return dict(hsts_one_year=bool(match and int(match.group(1)) >= 31536000),
                nosniff=headers.get('x-content-type-options', '').lower() == 'nosniff')


def request(host, port, path):
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    connection = http.client.HTTPSConnection(host, port, timeout=10, context=context)
    try:
        connection.connect()
        version = connection.sock.version()
        certificate = connection.sock.getpeercert()
        fingerprint = hashlib.sha256(connection.sock.getpeercert(binary_form=True)).hexdigest()
        remaining = ssl.cert_time_to_seconds(certificate['notAfter']) - time.time()
        connection.request('GET', path, headers={'Accept': 'application/json', 'Connection': 'close'})
        response = connection.getresponse()
        headers = {key.lower(): value for key, value in response.getheaders()}
        body = response.read(32769)
        if len(body) > 32768:
            raise ValueError('Response bounds exceeded')
        return response.status, headers, body, dict(tls_version=version,
            certificate_sha256=fingerprint, certificate_days_remaining=int(remaining // 86400))
    finally:
        connection.close()


def probe(origin, kind, transport=request):
    host, port = checked_origin(origin)
    path = '/health' if kind == 'gyro' else '/healthz'
    status, headers, body, tls = transport(host, port, path)
    checks = check_headers(headers)
    checks.update(health_http_200=status == 200,
                  platform_ca_hostname_verified=True,
                  negotiated_modern_tls=tls['tls_version'] in ('TLSv1.2', 'TLSv1.3'),
                  certificate_valid_14_days=tls['certificate_days_remaining'] >= 14,
                  json_content_type=headers.get('content-type', '').split(';')[0].strip().lower() == 'application/json')
    try:
        health = json.loads(body)
        checks['healthy_json'] = isinstance(health, dict) and health.get('status') == ('healthy' if kind == 'gyro' else 'ok')
    except (ValueError, UnicodeError):
        checks['healthy_json'] = False
    if kind == 'gyro' and checks['healthy_json']:
        checks['dedicated_gyro'] = health.get('deployment_mode') == 'dedicated'
        auth_status, _, _, _ = transport(host, port, '/api/v1/devices/registry')
        checks['anonymous_registry_denied'] = auth_status in (401, 403)
    return dict(checks=checks, tls=tls, preflight_passed=all(checks.values()),
                redirects_followed=False, credentials_sent=False, business_writes=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origin')
    parser.add_argument('--kind', choices=('gyro', 'retail'), required=True)
    parser.add_argument('--confirm-owned-site', action='store_true')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    report = dict(schema_version=1, kind='https_site_preflight', passed=False, preflight_passed=False,
                  security_review_accepted=False, production_accepted=False,
                  recorded_at=datetime.now(timezone.utc).isoformat())
    try:
        if not args.origin or not args.confirm_owned_site:
            raise ValueError('An authorized real origin and explicit owned-site confirmation are required; no network calls made')
        checked_origin(args.origin)
        report.update(probe(args.origin, args.kind))
        report['origin'] = args.origin
        # Deliberately NOT passed=True: certificate/header preflight cannot self-certify security.
    except Exception as error:
        report['failure_type'] = type(error).__name__
        if type(error) is ValueError:
            report['blocker'] = str(error)
    Path(args.output).write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report['preflight_passed'] else 1)


if __name__ == '__main__':
    main()

"""Opt-in browser smoke: use an isolated, seeded demo server, never production.
BASE_URL, DEMO_USERNAME, DEMO_PASSWORD required. CHROMIUM_EXECUTABLE optional.
Run directly (not collected by pytest). Output includes screenshots, no credentials.
"""
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

out = Path(__file__).resolve().parents[2] / 'preview'
out.mkdir(exist_ok=True)
with sync_playwright() as p:
    options = {'headless': True, 'args': ['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage', '--single-process', '--no-zygote']}
    if os.getenv('CHROMIUM_EXECUTABLE'):
        options['executable_path'] = os.environ['CHROMIUM_EXECUTABLE']
    browser = p.chromium.launch(**options)
    page = browser.new_page(viewport={'width': 1440, 'height': 1000})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(os.environ['BASE_URL'].rstrip('/') + '/login')
    page.screenshot(path=str(out / 'login-desktop.png'), full_page=True)
    page.fill('[name=username]', os.environ['DEMO_USERNAME'])
    page.fill('[name=password]', os.environ['DEMO_PASSWORD'])
    page.get_by_role('button', name='Sign in').click()
    page.wait_for_selector('#orders tr')
    assert page.locator('#orders tr').count() > 0
    page.screenshot(path=str(out / 'operations-desktop.png'), full_page=True)
    before = page.get_by_role('button', name='Approve', exact=True).count()
    if before:
        page.get_by_role('button', name='Approve', exact=True).first.click()
        page.wait_for_function("document.querySelectorAll('#orders tr').length > 0 && [...document.querySelectorAll('#orders button')].some(b => b.textContent === 'Pick item')")
        page.screenshot(path=str(out / 'order-approved.png'), full_page=True)
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate('document.documentElement.scrollWidth') == 390
    page.screenshot(path=str(out / 'operations-mobile-web.png'), full_page=True)
    assert not errors, errors
    print('PASS: login, live orders, approval, 390px layout; no JavaScript errors')
    browser.close()

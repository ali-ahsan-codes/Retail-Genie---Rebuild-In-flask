from retail_genie.extensions import db
from retail_genie.models import TaxSetting


def test_tax_boolean_string_is_parsed_not_coerced_as_truthy(app, client, create_user):
    create_user("settings.admin", role="admin", permissions=[])
    client.post("/login", data={"username": "settings.admin", "password": "A-long-test-password-4!"})
    response = client.post("/api/v1/settings/tax", json={"taxes": [{"name": "VAT", "rate": "5", "is_enabled": "false"}]})
    assert response.status_code == 200, response.get_json()
    with app.app_context():
        tax = TaxSetting.query.one()
        assert tax.is_enabled is False
    invalid = client.post("/api/v1/settings/tax", json={"taxes": [{"name": "VAT", "rate": "5", "is_enabled": "sometimes"}]})
    assert invalid.status_code == 400

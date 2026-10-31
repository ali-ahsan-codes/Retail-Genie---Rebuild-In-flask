import unittest
from datetime import datetime, timedelta

from utils import build_gpc_payload


class DummyUser:
    def __init__(self, user_id, username, role, city_id):
        self.id = user_id
        self.username = username
        self.role = role
        self.city_id = city_id


class GpcPayloadContractTest(unittest.TestCase):
    def test_build_gpc_payload_includes_sync_fields(self):
        user = DummyUser(7, "alice", "sales", 3)
        base_url = "http://192.168.1.25:5000/"
        expiry_date = datetime.utcnow() + timedelta(days=7)
        catalog = {"products": [{"id": 1, "name": "Widget", "unit_price": 10.5}]}
        tokens = ["token-1", "token-2"]

        payload = build_gpc_payload(
            user=user,
            api_key="secret-key-123",
            session_id="session-xyz",
            device_uuid="device-uuid-999",
            expiry_date=expiry_date,
            catalog=catalog,
            tokens=tokens,
            show_stock=True,
            base_url=base_url,
            master_secret="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        )

        self.assertEqual(payload["user_id"], 7)
        self.assertEqual(payload["username"], "alice")
        self.assertEqual(payload["api_key"], "secret-key-123")
        self.assertEqual(payload["session_id"], "session-xyz")
        self.assertEqual(payload["device_uuid"], "device-uuid-999")
        self.assertEqual(payload["base_url"], base_url)
        self.assertEqual(payload["server_url"], base_url)
        self.assertEqual(payload["role"], "sales")
        self.assertEqual(payload["city_id"], 3)
        self.assertEqual(payload["master_secret"], "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef")
        self.assertTrue(payload["catalog_permissions"]["show_stock_quantity"])
        self.assertEqual(payload["tokens"], tokens)


if __name__ == "__main__":
    unittest.main()

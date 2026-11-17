import tempfile
import unittest
from pathlib import Path

from v1_store import V1Store
from web_server import APIError, RequestHandler


class V1StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = V1Store(Path(self.temp_dir.name) / "v1.db")

    def tearDown(self):
        self.store.close()
        self.temp_dir.cleanup()

    def test_seeded_roles_can_authenticate(self):
        self.assertEqual(self.store.authenticate("admin", "admin123")["role_code"], "ADMIN")
        self.assertEqual(
            self.store.authenticate("operator", "operator123")["role_code"],
            "OPERATOR",
        )
        self.assertEqual(
            self.store.authenticate("viewer", "viewer123")["role_code"], "VIEWER"
        )
        self.assertIsNone(self.store.authenticate("admin", "wrong-password"))

    def test_device_crud_and_enabled_state(self):
        self.store.save_device(
            {
                "device_code": "TEST-01",
                "device_name": "测试设备",
                "device_type": "电表",
                "area_code": "测试区",
                "location_desc": "一层",
            }
        )
        self.store.save_device(
            {
                "device_code": "TEST-01",
                "device_name": "更新设备",
                "device_type": "电表",
                "area_code": "测试区",
                "location_desc": "二层",
                "is_edit": True,
            }
        )
        row = next(item for item in self.store.list_devices() if item["device_code"] == "TEST-01")
        self.assertEqual(row["device_name"], "更新设备")
        self.store.set_device_enabled("TEST-01", False)
        row = next(item for item in self.store.list_devices() if item["device_code"] == "TEST-01")
        self.assertEqual(row["enabled"], 0)

    def test_duplicate_device_code_is_rejected(self):
        device = {
            "device_code": "TEST-02",
            "device_name": "设备",
            "area_code": "测试区",
        }
        self.store.save_device(device)
        with self.assertRaisesRegex(ValueError, "设备编号已存在"):
            self.store.save_device(device)

    def test_invalid_device_code_is_rejected(self):
        with self.assertRaises(ValueError):
            self.store.save_device(
                {
                    "device_code": "设备 1",
                    "device_name": "设备",
                    "area_code": "区域",
                }
            )

    def test_viewer_cannot_use_device_write_permission(self):
        RequestHandler._require_operator({"role_code": "OPERATOR"})
        with self.assertRaisesRegex(APIError, "只读账号"):
            RequestHandler._require_operator({"role_code": "VIEWER"})

    def test_v1_schema_has_only_first_iteration_tables(self):
        tables = {
            row["name"]
            for row in self.store.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        self.assertTrue(
            {"sys_user", "device", "metric_definition", "telemetry_event"} <= tables
        )
        self.assertFalse({"alert_record", "rule_state", "dlq"} & tables)


if __name__ == "__main__":
    unittest.main()

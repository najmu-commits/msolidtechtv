import unittest

import app as app_module


class AccessCodeTests(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()
        app_module.ACCESS_CODES.clear()
        app_module.ACCESS_CODES.update({
            "1111": {"device_id": None, "label": "Customer 1", "paid": True, "expires_at": None},
            "2222": {"device_id": None, "label": "Customer 2", "paid": True, "expires_at": None},
        })

    def test_same_device_can_use_same_code(self):
        device_id = "device-abc"

        first = self.client.post("/api/verify-pin", json={"pin": "1111", "device_id": device_id})
        second = self.client.post("/api/verify-pin", json={"pin": "1111", "device_id": device_id})

        self.assertEqual(first.status_code, 200)
        self.assertTrue(first.get_json()["success"])
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.get_json()["success"])

    def test_different_device_cannot_use_same_code(self):
        first = self.client.post("/api/verify-pin", json={"pin": "2222", "device_id": "device-1"})
        second = self.client.post("/api/verify-pin", json={"pin": "2222", "device_id": "device-2"})

        self.assertEqual(first.status_code, 200)
        self.assertTrue(first.get_json()["success"])
        self.assertEqual(second.status_code, 401)
        self.assertFalse(second.get_json()["success"])

    def test_admin_can_create_access_code(self):
        response = self.client.post("/api/access-codes", json={"label": "Alice"})

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["success"])
        self.assertIn("code", payload)
        self.assertTrue(len(payload["code"]) >= 4)

    def test_unpaid_code_is_rejected(self):
        response = self.client.post("/api/access-codes", json={"label": "Bob", "paid": False})
        code = response.get_json()["code"]

        result = self.client.post("/api/verify-pin", json={"pin": code, "device_id": "device-3"})

        self.assertEqual(result.status_code, 401)
        self.assertFalse(result.get_json()["success"])

    def test_expired_code_is_rejected(self):
        code = "3333"
        app_module.ACCESS_CODES[code] = {"device_id": None, "label": "Expired", "paid": True, "expires_at": "2000-01-01T00:00:00"}

        result = self.client.post("/api/verify-pin", json={"pin": code, "device_id": "device-4"})

        self.assertEqual(result.status_code, 401)
        self.assertFalse(result.get_json()["success"])

    def test_admin_login_gate_redirects_and_allows_access(self):
        locked = self.client.get("/admin/access-codes")
        self.assertEqual(locked.status_code, 302)

        login = self.client.post("/admin/login", data={"pin": "1234"}, follow_redirects=False)
        self.assertEqual(login.status_code, 302)

        page = self.client.get("/admin/access-codes")
        self.assertEqual(page.status_code, 200)


if __name__ == "__main__":
    unittest.main()

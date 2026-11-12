import os
import tempfile
import unittest

os.environ["FORGE_DATA"] = tempfile.mkdtemp(prefix="forge-api-")
from fastapi.testclient import TestClient
from forge.app import app


class APITests(unittest.TestCase):
    def test_permissions_and_scope(self):
        with TestClient(app) as c:
            self.assertEqual(c.get("/health").status_code, 200)
            from unittest.mock import patch

            with patch("forge.app.TOKEN", "test-secret"):
                self.assertEqual(c.get("/api/config").status_code, 401)
                self.assertEqual(
                    c.get(
                        "/api/config", headers={"Authorization": "Bearer test-secret"}
                    ).status_code,
                    200,
                )
            with patch.dict(
                os.environ,
                {
                    "FORGE_MODEL_URL": "http://operator:private@localhost:8081/v1?api_key=hidden"
                },
            ):
                self.assertEqual(
                    c.get("/api/config").json()["model_url"], "http://localhost:8081/v1"
                )
            self.assertEqual(
                c.post(
                    "/api/projects", headers={"Origin": "https://evil.example"}, json={}
                ).status_code,
                403,
            )
            body = {
                "title": "API project",
                "brief": "Build the task tracker reference",
                "provider": "scripted",
                "idempotency_key": "api-test-key",
            }
            p = c.post("/api/projects", json=body).json()
            pid = p["id"]
            p = c.post("/api/projects/" + pid + "/plan").json()
            t = p["tasks"][0]
            self.assertEqual(
                c.patch(
                    "/api/tasks/" + t["id"],
                    json={
                        "title": "Edited task",
                        "role": "frontend",
                        "acceptance": ["Reference tracker behavior"],
                    },
                ).status_code,
                200,
            )
            self.assertEqual(
                c.get(
                    "/api/tasks/" + t["id"] + "/artifact/%2e%2e/%2e%2e/forge.sqlite3"
                ).status_code,
                404,
            )
            # Keep scheduler paused while checking approval policy.
            c.post("/api/projects/" + pid + "/pause")
            c.post("/api/projects/" + pid + "/approve")
            self.assertEqual(
                c.patch(
                    "/api/tasks/" + t["id"],
                    json={
                        "title": "Changed scope",
                        "role": "frontend",
                        "acceptance": ["new"],
                    },
                ).status_code,
                400,
            )
            self.assertEqual(
                c.post("/api/tasks/" + t["id"] + "/retry").status_code, 400
            )


if __name__ == "__main__":
    unittest.main()

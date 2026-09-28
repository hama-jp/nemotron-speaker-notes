import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
import server


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.data = Path(self.temp.name)
        self.patcher = patch.object(server, "DATA", self.data)
        self.patcher.start()
        self.client = TestClient(server.app)

    def tearDown(self):
        self.client.close()
        self.patcher.stop()
        self.temp.cleanup()

    def test_empty_history_and_missing_job(self):
        self.assertEqual(self.client.get("/api/jobs").json(), [])
        self.assertEqual(self.client.get("/api/jobs/missing").status_code, 404)
        self.assertEqual(self.client.get("/api/jobs/invalid!").status_code, 404)

    def test_cross_origin_upload_rejected(self):
        response = self.client.post(
            "/api/jobs",
            headers={"Origin": "https://other.example"},
            files={"file": ("test.wav", b"fake")},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(list(self.data.iterdir()), [])

    def test_invalid_and_empty_upload_leave_no_job(self):
        self.assertEqual(
            self.client.post("/api/jobs", files={"file": ("a.exe", b"x")}).status_code,
            400,
        )
        with patch.object(server.shutil, "disk_usage") as usage:
            usage.return_value.free = 20 * 1024**3
            self.assertEqual(
                self.client.post(
                    "/api/jobs", files={"file": ("a.wav", b"")}
                ).status_code,
                400,
            )
        self.assertEqual(list(self.data.iterdir()), [])

    def test_incomplete_results_and_startup_recovery(self):
        p = self.data / "test"
        p.mkdir()
        (p / "job.json").write_text(json.dumps({"id": "test", "status": "running"}))
        self.assertEqual(self.client.get("/api/jobs/test/result").status_code, 409)
        server.recover()
        self.assertEqual(self.client.get("/api/jobs/test").json()["status"], "error")

    def test_media_supports_seeking(self):
        p = self.data / "test"
        p.mkdir()
        (p / "job.json").write_text(
            json.dumps({"id": "test", "status": "done", "media_file": "audio.wav"})
        )
        (p / "audio.wav").write_bytes(b"0123456789")
        response = self.client.get(
            "/api/jobs/test/media", headers={"Range": "bytes=2-5"}
        )
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response.content, b"2345")


if __name__ == "__main__":
    unittest.main()

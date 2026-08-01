import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

import api
from models import Application, Job


class FakeQuery:
    def __init__(self, result):
        self._result = result

    def filter_by(self, **kwargs):
        return self

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self._result


class FakeSession:
    def __init__(self, job_result=None, application_result=None):
        self._job_result = job_result
        self._application_result = application_result
        self.rolled_back = False

    def query(self, model):
        if model is Job:
            return FakeQuery(self._job_result)
        if model is Application:
            return FakeQuery(self._application_result)
        return FakeQuery(None)

    def add(self, obj):
        return None

    def commit(self):
        raise IntegrityError("stmt", None, Exception("conflict"))

    def rollback(self):
        self.rolled_back = True

    def refresh(self, obj):
        return None

    def close(self):
        return None


class ConcurrencyHandlingTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(api.app)

    def test_create_manual_job_returns_409_when_commit_hits_integrity_error(self):
        with patch("api.SessionLocal", return_value=FakeSession()), patch("api.categorize_job", return_value=("not_relevant", 0)), patch("api.classify_eu_compatibility", return_value="unclear"), patch("api.is_switzerland", return_value=False), patch("api.compute_resume_match", return_value={"match_pct": 0}):
            response = self.client.post(
                "/jobs/manual",
                json={
                    "title": "Senior Frontend Engineer",
                    "company": "Example",
                    "url": "https://example.com/job",
                    "description": "Frontend role",
                    "location": "Remote",
                    "source_label": "manual",
                },
            )

        self.assertEqual(response.status_code, 409)
        self.assertIn("already exists", response.text.lower())

    def test_create_application_returns_409_when_commit_hits_integrity_error(self):
        with patch("api.SessionLocal", return_value=FakeSession(job_result=object())), patch("api.SessionLocal", return_value=FakeSession(job_result=object())):
            response = self.client.post("/jobs/1/apply", json={})

        self.assertEqual(response.status_code, 409)
        self.assertIn("already exists", response.text.lower())


if __name__ == "__main__":
    unittest.main()

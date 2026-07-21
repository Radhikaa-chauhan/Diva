"""Regression test for A1: create_job must return a valid JobCreateOut."""
import unittest
from datetime import datetime, timezone

import pydantic

from app.schemas import JobCreateOut


class TestJobCreateOut(unittest.TestCase):

    def test_full_construction_valid(self):
        """The shape create_job now returns must validate."""
        out = JobCreateOut(
            job_id="abc-123",
            status="pending",
            created_at=datetime.now(timezone.utc),
        )
        self.assertEqual(out.job_id, "abc-123")
        self.assertEqual(out.status, "pending")

    def test_job_id_only_is_invalid(self):
        """The old create_job call site (job_id only) must fail validation —
        guards against reintroducing the 500 on POST /api/jobs."""
        with self.assertRaises(pydantic.ValidationError):
            JobCreateOut(job_id="abc-123")


if __name__ == "__main__":
    unittest.main()

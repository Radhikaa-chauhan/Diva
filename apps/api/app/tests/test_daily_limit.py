"""Daily generation cap: 3/day allowed, 4th blocked; resets next UTC day."""
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.generation_job import GenerationJob, JobStatus
from app.models.reference_photo import ReferencePhoto
from app.models.user import User
from app.routers.jobs import _check_rate_limit


class TestDailyLimit(unittest.TestCase):

    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.user = User(email="a@x.com", password_hash="h", display_name="A")
        ref = ReferencePhoto(title="R", thumbnail_url="http://x/t.jpg", style_description={}, prompt_template="p")
        self.db.add_all([self.user, ref])
        self.db.commit()
        self.ref_id = ref.id

    def tearDown(self):
        self.db.close()

    def _add_job(self, created_at: datetime):
        job = GenerationJob(
            user_id=self.user.id, reference_photo_id=self.ref_id,
            status=JobStatus.COMPLETE, selfie_image_url="http://x/s.jpg",
        )
        self.db.add(job)
        self.db.commit()
        # created_at has a server default; override for the test window
        job.created_at = created_at
        self.db.commit()

    def test_fourth_generation_today_blocked(self):
        now = datetime.now(timezone.utc)
        for _ in range(3):
            self._add_job(now)
        with self.assertRaises(HTTPException) as ctx:
            _check_rate_limit(self.user, self.db)
        self.assertEqual(ctx.exception.status_code, 429)
        self.assertIn("Daily limit", ctx.exception.detail)

    def test_under_limit_allowed(self):
        now = datetime.now(timezone.utc)
        self._add_job(now)
        self._add_job(now)
        _check_rate_limit(self.user, self.db)  # 3rd attempt allowed → no raise

    def test_yesterdays_generations_dont_count(self):
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        for _ in range(5):
            self._add_job(yesterday)
        _check_rate_limit(self.user, self.db)  # today is empty → allowed


if __name__ == "__main__":
    unittest.main()

"""Admin dashboard: gating + stats correctness."""
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.deps import is_admin, require_admin
from app.models.generation_job import GenerationJob, JobStatus
from app.models.reference_photo import ReferencePhoto
from app.models.social import Post
from app.models.user import User
from app.routers.admin import get_stats, list_users


class TestAdminGating(unittest.TestCase):

    def test_is_admin_matches_configured_emails(self):
        admin = User(email="Boss@Diva.ai", password_hash="h", display_name="Boss")
        normal = User(email="joe@x.com", password_hash="h", display_name="Joe")
        with patch("app.config.get_settings") as gs:
            gs.return_value.admin_emails_list = ["boss@diva.ai"]
            self.assertTrue(is_admin(admin))   # case-insensitive
            self.assertFalse(is_admin(normal))

    def test_require_admin_403_for_non_admin(self):
        normal = User(email="joe@x.com", password_hash="h", display_name="Joe")
        with patch("app.config.get_settings") as gs:
            gs.return_value.admin_emails_list = ["boss@diva.ai"]
            with self.assertRaises(HTTPException) as ctx:
                require_admin(current_user=normal)
            self.assertEqual(ctx.exception.status_code, 403)


class TestAdminStats(unittest.TestCase):

    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        self.db = Session()

        now = datetime.now(timezone.utc)
        # Active recently
        u1 = User(email="a@x.com", password_hash="h", display_name="A",
                  is_email_verified=True, last_login_at=now - timedelta(hours=2))
        # Active this week but not today
        u2 = User(email="b@x.com", password_hash="h", display_name="B",
                  last_login_at=now - timedelta(days=3))
        # Never logged in, old signup
        u3 = User(email="c@x.com", password_hash="h", display_name="C",
                  created_at=now - timedelta(days=40))
        self.db.add_all([u1, u2, u3])
        self.db.commit()
        self.u1 = u1

        ref = ReferencePhoto(title="R", thumbnail_url="http://x/t.jpg",
                             style_description={}, prompt_template="p")
        self.db.add(ref)
        self.db.commit()
        self.db.add(GenerationJob(user_id=u1.id, reference_photo_id=ref.id,
                                  status=JobStatus.COMPLETE, selfie_image_url="http://x/s.jpg"))
        self.db.add(Post(user_id=u1.id, job_id="jj", image_url="http://x/r.jpg"))
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_stats(self):
        stats = get_stats(db=self.db)
        self.assertEqual(stats.total_users, 3)
        self.assertEqual(stats.active_24h, 1)
        self.assertEqual(stats.active_7d, 2)
        self.assertEqual(stats.verified_users, 1)
        self.assertEqual(stats.total_generations, 1)
        self.assertEqual(stats.total_posts, 1)

    def test_user_search(self):
        result = list_users(page=1, per_page=25, q="a@x", db=self.db)
        self.assertEqual(result.total, 1)
        self.assertEqual(result.items[0].email, "a@x.com")


if __name__ == "__main__":
    unittest.main()

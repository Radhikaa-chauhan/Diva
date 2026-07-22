"""Profiles API: counts, follow state, private-post visibility, username dedupe."""
import unittest

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.social import Follow, Post
from app.models.user import User
from app.routers.auth import _unique_username
from app.routers.users import get_profile, get_profile_posts


class TestProfilesApi(unittest.TestCase):

    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        self.db = Session()

        self.alice = User(email="alice@x.com", username="alice", password_hash="h", display_name="Alice")
        self.bob = User(email="bob@x.com", username="bob", password_hash="h", display_name="Bob")
        self.db.add_all([self.alice, self.bob])
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def _post(self, user, visibility="public", suffix=""):
        post = Post(
            user_id=user.id,
            job_id=f"job-{user.id}-{visibility}{suffix}",
            image_url="http://x/r.jpg",
            visibility=visibility,
        )
        self.db.add(post)
        self.db.commit()
        return post

    def test_profile_counts_and_follow_state(self):
        self._post(self.bob, "public")
        self._post(self.bob, "private")  # not counted publicly
        self.db.add(Follow(follower_id=self.alice.id, following_id=self.bob.id))
        self.bob.followers_count = 1
        self.db.commit()

        profile = get_profile("bob", current_user=self.alice, db=self.db)
        self.assertEqual(profile.posts_count, 1)
        self.assertEqual(profile.followers_count, 1)
        self.assertTrue(profile.is_following)

        anon = get_profile("bob", current_user=None, db=self.db)
        self.assertFalse(anon.is_following)

    def test_profile_posts_visibility(self):
        public_post = self._post(self.bob, "public")
        self._post(self.bob, "private")

        # Non-owner sees only public
        seen = get_profile_posts("bob", page=1, per_page=20, current_user=self.alice, db=self.db)
        self.assertEqual(seen.total, 1)
        self.assertEqual(seen.items[0].id, public_post.id)

        # Owner sees both
        own = get_profile_posts("bob", page=1, per_page=20, current_user=self.bob, db=self.db)
        self.assertEqual(own.total, 2)

    def test_unknown_username_is_404(self):
        with self.assertRaises(HTTPException) as ctx:
            get_profile("ghost", current_user=None, db=self.db)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_unique_username_dedupes(self):
        self.assertEqual(_unique_username(self.db, "alice@elsewhere.com"), "alice2")
        self.assertEqual(_unique_username(self.db, "brand.new@x.com"), "brand.new")


if __name__ == "__main__":
    unittest.main()

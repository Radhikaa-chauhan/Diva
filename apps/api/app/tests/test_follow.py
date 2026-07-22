"""Follow API: idempotency, self-follow guard, counters, listings."""
import unittest

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.social import Follow
from app.models.user import User
from app.routers.users import follow_user, list_followers, list_following, unfollow_user


class TestFollowApi(unittest.TestCase):

    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        self.db = Session()

        self.alice = User(email="alice@x.com", password_hash="h", display_name="Alice")
        self.bob = User(email="bob@x.com", password_hash="h", display_name="Bob")
        self.db.add_all([self.alice, self.bob])
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_follow_creates_one_row_and_increments_counters(self):
        result = follow_user(self.bob.id, current_user=self.alice, db=self.db)
        self.assertTrue(result.is_following)
        self.assertEqual(result.followers_count, 1)
        self.assertEqual(self.bob.followers_count, 1)
        self.assertEqual(self.alice.following_count, 1)
        self.assertEqual(self.db.get(Follow, (self.alice.id, self.bob.id)) is not None, True)

    def test_double_follow_is_idempotent(self):
        follow_user(self.bob.id, current_user=self.alice, db=self.db)
        follow_user(self.bob.id, current_user=self.alice, db=self.db)
        self.assertEqual(self.bob.followers_count, 1)

    def test_self_follow_is_400(self):
        with self.assertRaises(HTTPException) as ctx:
            follow_user(self.alice.id, current_user=self.alice, db=self.db)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_unfollow_decrements_and_is_idempotent(self):
        follow_user(self.bob.id, current_user=self.alice, db=self.db)
        result = unfollow_user(self.bob.id, current_user=self.alice, db=self.db)
        self.assertFalse(result.is_following)
        self.assertEqual(self.bob.followers_count, 0)
        self.assertIsNone(self.db.get(Follow, (self.alice.id, self.bob.id)))

        # Unfollowing again must not go negative or raise
        unfollow_user(self.bob.id, current_user=self.alice, db=self.db)
        self.assertEqual(self.bob.followers_count, 0)

    def test_follow_nonexistent_user_is_404(self):
        with self.assertRaises(HTTPException) as ctx:
            follow_user("does-not-exist", current_user=self.alice, db=self.db)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_followers_and_following_listings(self):
        follow_user(self.bob.id, current_user=self.alice, db=self.db)

        followers = list_followers(self.bob.id, page=1, per_page=20, db=self.db)
        self.assertEqual(followers.total, 1)
        self.assertEqual(followers.items[0].id, self.alice.id)

        following = list_following(self.alice.id, page=1, per_page=20, db=self.db)
        self.assertEqual(following.total, 1)
        self.assertEqual(following.items[0].id, self.bob.id)


if __name__ == "__main__":
    unittest.main()

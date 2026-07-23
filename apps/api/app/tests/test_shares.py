"""Share-to-friends: follow-gating, dedupe, inbox, unread count, mark-read."""
import unittest

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.social import Follow, Post, PostShare
from app.models.user import User
from app.routers.shares import (
    list_received_shares,
    mark_shares_read,
    share_post,
    unread_share_count,
)
from app.schemas import ShareCreate


class TestShares(unittest.TestCase):

    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.alice = User(email="a@x.com", username="a", password_hash="h", display_name="Alice")
        self.bob = User(email="b@x.com", username="b", password_hash="h", display_name="Bob")
        self.carol = User(email="c@x.com", username="c", password_hash="h", display_name="Carol")
        self.db.add_all([self.alice, self.bob, self.carol])
        self.db.commit()
        self.post = Post(user_id=self.alice.id, job_id="j1", image_url="http://x/r.jpg", visibility="public")
        self.db.add(self.post)
        # Alice follows Bob (so Alice can share TO Bob)
        self.db.add(Follow(follower_id=self.alice.id, following_id=self.bob.id))
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_share_with_followed_user(self):
        result = share_post(self.post.id, ShareCreate(user_ids=[self.bob.id]), current_user=self.alice, db=self.db)
        self.assertEqual(result.shared_with, 1)
        self.assertIsNotNone(
            self.db.query(PostShare).filter_by(to_user_id=self.bob.id, post_id=self.post.id).first()
        )

    def test_cannot_share_with_non_followed_user(self):
        with self.assertRaises(HTTPException) as ctx:
            share_post(self.post.id, ShareCreate(user_ids=[self.carol.id]), current_user=self.alice, db=self.db)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_resharing_is_deduped(self):
        share_post(self.post.id, ShareCreate(user_ids=[self.bob.id]), current_user=self.alice, db=self.db)
        result = share_post(self.post.id, ShareCreate(user_ids=[self.bob.id]), current_user=self.alice, db=self.db)
        self.assertEqual(result.shared_with, 0)  # already shared → skipped
        self.assertEqual(self.db.query(PostShare).count(), 1)

    def test_inbox_and_unread_and_mark_read(self):
        share_post(self.post.id, ShareCreate(user_ids=[self.bob.id]), current_user=self.alice, db=self.db)

        # Bob's inbox has the share, from Alice
        inbox = list_received_shares(page=1, per_page=20, current_user=self.bob, db=self.db)
        self.assertEqual(inbox.total, 1)
        self.assertEqual(inbox.items[0].sender.id, self.alice.id)
        self.assertEqual(inbox.items[0].post.id, self.post.id)

        # Unread count is 1, then 0 after mark-read
        self.assertEqual(unread_share_count(current_user=self.bob, db=self.db).count, 1)
        mark_shares_read(current_user=self.bob, db=self.db)
        self.assertEqual(unread_share_count(current_user=self.bob, db=self.db).count, 0)

        # Alice (sender) sees nothing in her own inbox
        self.assertEqual(list_received_shares(page=1, per_page=20, current_user=self.alice, db=self.db).total, 0)


if __name__ == "__main__":
    unittest.main()

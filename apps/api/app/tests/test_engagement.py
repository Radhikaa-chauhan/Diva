"""Engagement API: likes, comments, saves — idempotency, counters, authz."""
import unittest

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.social import Comment, Post
from app.models.user import User
from app.routers.engagement import (
    create_comment,
    delete_comment,
    like_post,
    list_comments,
    list_saved_posts,
    save_post,
    unlike_post,
    unsave_post,
)
from app.schemas import CommentCreate


class TestEngagementApi(unittest.TestCase):

    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        self.db = Session()

        self.alice = User(email="alice@x.com", password_hash="h", display_name="Alice")
        self.bob = User(email="bob@x.com", password_hash="h", display_name="Bob")
        self.carol = User(email="carol@x.com", password_hash="h", display_name="Carol")
        self.db.add_all([self.alice, self.bob, self.carol])
        self.db.commit()

        self.post = Post(
            user_id=self.bob.id, job_id="job-bob", image_url="http://x/r.jpg", visibility="public"
        )
        self.db.add(self.post)
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_like_twice_counts_once_then_unlike(self):
        like_post(self.post.id, current_user=self.alice, db=self.db)
        result = like_post(self.post.id, current_user=self.alice, db=self.db)
        self.assertEqual(result.likes_count, 1)

        result = unlike_post(self.post.id, current_user=self.alice, db=self.db)
        self.assertEqual(result.likes_count, 0)
        # Unlike again: still zero, no error
        result = unlike_post(self.post.id, current_user=self.alice, db=self.db)
        self.assertEqual(result.likes_count, 0)

    def test_save_appears_in_saved_listing(self):
        save_post(self.post.id, current_user=self.alice, db=self.db)
        saved = list_saved_posts(page=1, per_page=20, current_user=self.alice, db=self.db)
        self.assertEqual(saved.total, 1)
        self.assertEqual(saved.items[0].id, self.post.id)
        self.assertTrue(saved.items[0].is_saved)

        unsave_post(self.post.id, current_user=self.alice, db=self.db)
        saved = list_saved_posts(page=1, per_page=20, current_user=self.alice, db=self.db)
        self.assertEqual(saved.total, 0)

    def test_comment_roundtrip_updates_counter(self):
        out = create_comment(
            self.post.id, CommentCreate(text="gorgeous!"), current_user=self.alice, db=self.db
        )
        self.assertEqual(out.text, "gorgeous!")
        self.assertEqual(out.author.id, self.alice.id)
        self.assertEqual(self.post.comments_count, 1)

        comments = list_comments(self.post.id, page=1, per_page=20, current_user=None, db=self.db)
        self.assertEqual(comments.total, 1)

    def test_comment_delete_authz(self):
        out = create_comment(
            self.post.id, CommentCreate(text="hi"), current_user=self.alice, db=self.db
        )
        # Carol is neither comment author nor post owner
        with self.assertRaises(HTTPException) as ctx:
            delete_comment(out.id, current_user=self.carol, db=self.db)
        self.assertEqual(ctx.exception.status_code, 403)

        # Post owner (bob) can delete someone else's comment on his post
        delete_comment(out.id, current_user=self.bob, db=self.db)
        self.assertTrue(self.db.get(Comment, out.id).is_deleted)
        self.assertEqual(self.post.comments_count, 0)

    def test_private_post_engagement_blocked_for_non_owner(self):
        private = Post(
            user_id=self.bob.id, job_id="job-priv", image_url="http://x/p.jpg", visibility="private"
        )
        self.db.add(private)
        self.db.commit()

        with self.assertRaises(HTTPException) as ctx:
            like_post(private.id, current_user=self.alice, db=self.db)
        self.assertEqual(ctx.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()

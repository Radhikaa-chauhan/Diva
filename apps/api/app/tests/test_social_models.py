"""Social model graph test on in-memory SQLite: relationships, constraints."""
import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Comment, Follow, GenerationJob, Like, Post, SavedPost, User
from app.models.generation_job import JobStatus


class TestSocialModels(unittest.TestCase):

    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine)
        self.db = self.Session()

        self.alice = User(email="alice@x.com", password_hash="h", display_name="Alice")
        self.bob = User(email="bob@x.com", password_hash="h", display_name="Bob")
        self.db.add_all([self.alice, self.bob])
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def _make_post(self, user) -> Post:
        job = GenerationJob(
            user_id=user.id,
            reference_photo_id=None,
            status=JobStatus.COMPLETE,
            selfie_image_url="http://x/selfie.jpg",
            result_urls=["http://x/result.jpg"],
        )
        # reference FK is nullable=False on jobs — use a raw post without it instead
        post = Post(user_id=user.id, job_id=f"job-{user.id}", image_url="http://x/result.jpg")
        self.db.add(post)
        self.db.commit()
        return post

    def test_full_engagement_graph(self):
        post = self._make_post(self.bob)

        self.db.add_all([
            Follow(follower_id=self.alice.id, following_id=self.bob.id),
            Like(user_id=self.alice.id, post_id=post.id),
            Comment(user_id=self.alice.id, post_id=post.id, text="stunning!"),
            SavedPost(user_id=self.alice.id, post_id=post.id),
        ])
        self.db.commit()

        self.assertEqual(post.author.id, self.bob.id)
        self.assertEqual(
            self.db.scalar(select(Follow).where(Follow.follower_id == self.alice.id)).following_id,
            self.bob.id,
        )
        comment = self.db.scalar(select(Comment).where(Comment.post_id == post.id))
        self.assertEqual(comment.text, "stunning!")
        self.assertEqual(comment.author.display_name, "Alice")
        self.assertIsNotNone(self.db.get(Like, (self.alice.id, post.id)))
        self.assertIsNotNone(self.db.get(SavedPost, (self.alice.id, post.id)))

    def test_self_follow_rejected(self):
        self.db.add(Follow(follower_id=self.alice.id, following_id=self.alice.id))
        with self.assertRaises(IntegrityError):
            self.db.commit()
        self.db.rollback()

    def test_duplicate_like_rejected(self):
        post = self._make_post(self.bob)
        self.db.add(Like(user_id=self.alice.id, post_id=post.id))
        self.db.commit()
        self.db.add(Like(user_id=self.alice.id, post_id=post.id))
        with self.assertRaises(IntegrityError):
            self.db.commit()
        self.db.rollback()

    def test_one_post_per_job(self):
        post = self._make_post(self.bob)
        self.db.add(Post(user_id=self.bob.id, job_id=post.job_id, image_url="http://x/2.jpg"))
        with self.assertRaises(IntegrityError):
            self.db.commit()
        self.db.rollback()

    def test_user_counters_default_zero(self):
        self.assertEqual(self.alice.followers_count, 0)
        self.assertEqual(self.alice.following_count, 0)


if __name__ == "__main__":
    unittest.main()

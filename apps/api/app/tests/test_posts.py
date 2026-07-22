"""Posts API: publish, read, delete — on an in-memory SQLite DB."""
import unittest

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.generation_job import GenerationJob, JobStatus
from app.models.reference_photo import ReferencePhoto
from app.models.social import Post
from app.models.user import User
from app.routers.posts import create_post, delete_post, get_post
from app.schemas import PostCreate


class TestPostsApi(unittest.TestCase):

    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        self.db = Session()

        self.alice = User(email="alice@x.com", password_hash="h", display_name="Alice")
        self.bob = User(email="bob@x.com", password_hash="h", display_name="Bob")
        self.reference = ReferencePhoto(
            title="Editorial", thumbnail_url="http://x/thumb.jpg",
            style_description={}, prompt_template="a secret hidden prompt",
        )
        self.db.add_all([self.alice, self.bob, self.reference])
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def _job(self, user, status=JobStatus.COMPLETE, result_urls=("http://x/r.jpg",)):
        job = GenerationJob(
            user_id=user.id,
            reference_photo_id=self.reference.id,
            status=status,
            selfie_image_url="http://x/s.jpg",
            result_urls=list(result_urls) if result_urls else None,
            prompt_used="a secret hidden prompt",
        )
        self.db.add(job)
        self.db.commit()
        return job

    def test_publish_success_never_exposes_prompt(self):
        job = self._job(self.alice)
        out = create_post(PostCreate(job_id=job.id), current_user=self.alice, db=self.db)

        self.assertEqual(out.author.id, self.alice.id)
        self.assertNotIn("prompt", out.model_dump_json())

    def test_publish_someone_elses_job_is_403(self):
        job = self._job(self.bob)
        with self.assertRaises(HTTPException) as ctx:
            create_post(PostCreate(job_id=job.id), current_user=self.alice, db=self.db)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_publish_incomplete_job_is_400(self):
        job = self._job(self.alice, status=JobStatus.GENERATING, result_urls=None)
        with self.assertRaises(HTTPException) as ctx:
            create_post(PostCreate(job_id=job.id), current_user=self.alice, db=self.db)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_double_publish_is_409(self):
        job = self._job(self.alice)
        create_post(PostCreate(job_id=job.id), current_user=self.alice, db=self.db)
        with self.assertRaises(HTTPException) as ctx:
            create_post(PostCreate(job_id=job.id), current_user=self.alice, db=self.db)
        self.assertEqual(ctx.exception.status_code, 409)

    def test_private_post_hidden_from_non_owner(self):
        job = self._job(self.alice)
        post_out = create_post(
            PostCreate(job_id=job.id, visibility="private"), current_user=self.alice, db=self.db
        )
        with self.assertRaises(HTTPException) as ctx:
            get_post(post_out.id, current_user=self.bob, db=self.db)
        self.assertEqual(ctx.exception.status_code, 404)

        # Owner can still see it
        seen = get_post(post_out.id, current_user=self.alice, db=self.db)
        self.assertEqual(seen.id, post_out.id)

    def test_delete_by_non_owner_is_403(self):
        job = self._job(self.alice)
        post_out = create_post(PostCreate(job_id=job.id), current_user=self.alice, db=self.db)
        with self.assertRaises(HTTPException) as ctx:
            delete_post(post_out.id, current_user=self.bob, db=self.db)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_delete_by_owner_soft_deletes(self):
        job = self._job(self.alice)
        post_out = create_post(PostCreate(job_id=job.id), current_user=self.alice, db=self.db)
        delete_post(post_out.id, current_user=self.alice, db=self.db)

        post = self.db.get(Post, post_out.id)
        self.assertTrue(post.is_deleted)
        with self.assertRaises(HTTPException) as ctx:
            get_post(post_out.id, current_user=self.alice, db=self.db)
        self.assertEqual(ctx.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()

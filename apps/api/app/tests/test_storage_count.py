"""Regression: a completed job must increase the user's storage_used_bytes,
even when files live on S3 (get_file_size can't measure S3 URLs)."""
import asyncio
import io
import unittest
from unittest.mock import patch

from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.generation_job import GenerationJob, JobStatus
from app.models.reference_photo import ReferencePhoto
from app.models.user import User
from app.services import job_runner
from app.services.flux import GenerationResult


def _nonuniform_jpeg() -> bytes:
    img = Image.new("RGB", (256, 256), "purple")
    img.paste("white", (0, 0, 128, 256))  # non-uniform so the quality gate passes
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


class TestStorageCount(unittest.TestCase):

    def test_storage_used_bytes_increases_on_s3(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)

        db = Session()
        user = User(email="a@x.com", password_hash="h", display_name="A", storage_used_bytes=0)
        ref = ReferencePhoto(title="R", thumbnail_url="http://x/t.jpg", style_description={}, prompt_template="p")
        db.add_all([user, ref])
        db.commit()
        # Selfie is an S3 URL — get_file_size() would return 0 for it.
        job = GenerationJob(
            id="j1", user_id=user.id, reference_photo_id=ref.id, status=JobStatus.PENDING,
            selfie_image_url="https://bucket.s3.us-east-1.amazonaws.com/selfies/x.jpg",
        )
        db.add(job)
        db.commit()
        user_id = user.id
        db.close()

        result_bytes = _nonuniform_jpeg()
        selfie_bytes = b"x" * 4096

        async def fake_generate(sb, prompt):
            return GenerationResult(
                image_bytes=result_bytes, content_type="image/jpeg",
                cost_usd=0.0, prompt_used=prompt, provider_used="huggingface",
            )

        with patch.object(job_runner, "SessionLocal", Session), \
             patch.object(job_runner, "generate", fake_generate), \
             patch.object(job_runner.storage, "save_bytes",
                          return_value="https://bucket.s3.us-east-1.amazonaws.com/results/j1.jpg"):
            asyncio.run(job_runner.run_job("j1", selfie_bytes=selfie_bytes))

        db = Session()
        refreshed = db.get(User, user_id)
        self.assertEqual(refreshed.storage_used_bytes, len(selfie_bytes) + len(result_bytes))
        self.assertGreater(refreshed.storage_used_bytes, 0)
        db.close()


if __name__ == "__main__":
    unittest.main()

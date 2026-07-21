"""Worker tests: quality gate, bytes pass-through, COMPLETE/FAILED outcomes."""
import asyncio
import io
import unittest
from unittest.mock import MagicMock, patch

from PIL import Image

from app.models.generation_job import JobStatus
from app.services import job_runner
from app.services.flux import GenerationError, GenerationResult


def _jpeg(size=(128, 128), color="purple") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="JPEG")
    return buf.getvalue()


def _fake_job():
    job = MagicMock()
    job.status = JobStatus.PENDING
    job.selfie_image_url = "http://localhost:8000/storage/selfies/x.jpg"
    job.prompt_used = "editorial style"
    job.user_id = "user-1"
    return job


class TestQualityGate(unittest.TestCase):

    def test_normal_image_passes(self):
        # Non-uniform image: half purple, half white
        img = Image.new("RGB", (128, 128), "purple")
        img.paste("white", (0, 0, 64, 128))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        self.assertTrue(job_runner._passes_quality_gate(buf.getvalue()))

    def test_blank_image_rejected(self):
        self.assertFalse(job_runner._passes_quality_gate(_jpeg(color="white")))

    def test_garbage_bytes_rejected(self):
        self.assertFalse(job_runner._passes_quality_gate(b"not an image"))

    def test_tiny_image_rejected(self):
        self.assertFalse(job_runner._passes_quality_gate(_jpeg(size=(10, 10))))


class TestRunJob(unittest.TestCase):

    def _run(self, generate_mock, save_mock=None):
        """Run run_job with mocked DB sessions; returns the fake job."""
        job = _fake_job()
        db = MagicMock()
        db.get.return_value = job

        with patch.object(job_runner, "SessionLocal", return_value=db), \
             patch.object(job_runner, "generate", generate_mock), \
             patch.object(job_runner.storage, "save_bytes",
                          save_mock or MagicMock(return_value="https://bucket.s3.us-east-1.amazonaws.com/results/j1.jpg")), \
             patch.object(job_runner.storage, "get_file_size", return_value=0):
            asyncio.run(job_runner.run_job("j1", selfie_bytes=_jpeg()))
        return job, generate_mock

    def test_success_path_sets_complete_and_uses_passed_bytes(self):
        selfie = _jpeg()
        # Non-uniform result so the quality gate passes
        img = Image.new("RGB", (256, 256), "purple")
        img.paste("white", (0, 0, 128, 256))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")

        async def fake_generate(selfie_bytes, prompt):
            assert selfie_bytes == selfie, "worker must use the bytes handed to it"
            return GenerationResult(
                image_bytes=buf.getvalue(), content_type="image/jpeg",
                cost_usd=0.0, prompt_used=prompt, provider_used="huggingface",
            )

        job = _fake_job()
        db = MagicMock()
        db.get.return_value = job
        with patch.object(job_runner, "SessionLocal", return_value=db), \
             patch.object(job_runner, "generate", fake_generate), \
             patch.object(job_runner.storage, "save_bytes",
                          MagicMock(return_value="https://bucket.s3.us-east-1.amazonaws.com/results/j1.jpg")), \
             patch.object(job_runner.storage, "get_file_size", return_value=0):
            asyncio.run(job_runner.run_job("j1", selfie_bytes=selfie))

        self.assertEqual(job.status, JobStatus.COMPLETE)
        self.assertEqual(job.result_urls, ["https://bucket.s3.us-east-1.amazonaws.com/results/j1.jpg"])

    def test_failure_path_sets_failed_with_error(self):
        async def fake_generate(selfie_bytes, prompt):
            raise GenerationError("provider down")

        with patch.object(job_runner, "RETRY_BASE_DELAY", 0):
            job, _ = self._run(fake_generate)

        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertIn("provider down", job.error_message)

    def test_already_complete_is_skipped(self):
        job = _fake_job()
        job.status = JobStatus.COMPLETE
        db = MagicMock()
        db.get.return_value = job
        generate_mock = MagicMock()

        with patch.object(job_runner, "SessionLocal", return_value=db), \
             patch.object(job_runner, "generate", generate_mock):
            asyncio.run(job_runner.run_job("j1", selfie_bytes=_jpeg()))

        generate_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()

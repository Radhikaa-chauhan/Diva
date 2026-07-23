"""Admin reference management: create, auto-draft, update, delete."""
import asyncio
import io
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException, UploadFile
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.generation_job import GenerationJob, JobStatus
from app.models.reference_photo import ReferencePhoto
from app.models.user import User
from app.routers.admin import (
    create_reference,
    delete_reference,
    draft_reference_prompt,
    list_all_references,
    update_reference,
)
from app.schemas import ReferenceUpdate


def _img_upload(name="ref.png") -> UploadFile:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), "purple").save(buf, format="PNG")
    buf.seek(0)
    return UploadFile(filename=name, file=buf, headers={"content-type": "image/png"})


class TestAdminReferences(unittest.TestCase):

    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()

    def tearDown(self):
        self.db.close()

    def test_create_reference_from_upload(self):
        with patch("app.routers.admin.storage.save_bytes", return_value="https://b.s3.amazonaws.com/thumbnails/x.png"), \
             patch("app.routers.admin.clear_references_cache"):
            out = asyncio.run(create_reference(
                image=_img_upload(), title="Golden Hour", prompt_template="warm editorial scene",
                collection="Editorial", db=self.db,
            ))
        self.assertEqual(out.title, "Golden Hour")
        self.assertEqual(out.prompt_template, "warm editorial scene")
        self.assertTrue(out.active)
        self.assertEqual(self.db.query(ReferencePhoto).count(), 1)

    def test_draft_prompt_uses_curation(self):
        draft = {"style_description": {"mood": "warm"}, "prompt_template": "Place this person in a warm scene..."}
        with patch("app.routers.admin.curation.draft_from_image", new=AsyncMock(return_value=draft)):
            out = asyncio.run(draft_reference_prompt(image=_img_upload()))
        self.assertEqual(out.prompt_template, draft["prompt_template"])

    def test_non_image_rejected(self):
        bad = UploadFile(filename="x.txt", file=io.BytesIO(b"hi"), headers={"content-type": "text/plain"})
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(draft_reference_prompt(image=bad))
        self.assertEqual(ctx.exception.status_code, 400)

    def test_deactivate_hides_from_users(self):
        ref = ReferencePhoto(title="R", thumbnail_url="http://x/t.jpg", style_description={}, prompt_template="p", active=True)
        self.db.add(ref)
        self.db.commit()
        with patch("app.routers.admin.clear_references_cache"):
            out = update_reference(ref.id, ReferenceUpdate(active=False), db=self.db)
        self.assertFalse(out.active)

    def test_delete_unreferenced(self):
        ref = ReferencePhoto(title="R", thumbnail_url="http://x/t.jpg", style_description={}, prompt_template="p")
        self.db.add(ref)
        self.db.commit()
        rid = ref.id
        with patch("app.routers.admin.clear_references_cache"):
            delete_reference(rid, db=self.db)
        self.assertIsNone(self.db.get(ReferencePhoto, rid))

    def test_list_includes_inactive(self):
        self.db.add_all([
            ReferencePhoto(title="A", thumbnail_url="http://x/a.jpg", style_description={}, prompt_template="p", active=True),
            ReferencePhoto(title="B", thumbnail_url="http://x/b.jpg", style_description={}, prompt_template="p", active=False),
        ])
        self.db.commit()
        rows = list_all_references(db=self.db)
        self.assertEqual(len(rows), 2)


if __name__ == "__main__":
    unittest.main()

"""Bio update + avatar upload."""
import asyncio
import io
import unittest
from unittest.mock import patch

from fastapi import HTTPException, UploadFile
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.user import User
from app.routers.auth import update_me, upload_avatar
from app.schemas import UpdateProfileRequest


def _png_upload() -> UploadFile:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), "purple").save(buf, format="PNG")
    buf.seek(0)
    return UploadFile(filename="pic.png", file=buf, headers={"content-type": "image/png"})


class TestBioAvatar(unittest.TestCase):

    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.user = User(email="a@x.com", username="a", password_hash="h", display_name="A")
        self.db.add(self.user)
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_update_bio(self):
        with patch("app.routers.auth.is_admin", return_value=False):
            out = update_me(UpdateProfileRequest(bio="AI art enthusiast 🎨"), current_user=self.user, db=self.db)
        self.assertEqual(out.bio, "AI art enthusiast 🎨")
        self.assertEqual(self.user.bio, "AI art enthusiast 🎨")

    def test_bio_omitted_leaves_unchanged(self):
        self.user.bio = "keep me"
        self.db.commit()
        with patch("app.routers.auth.is_admin", return_value=False):
            update_me(UpdateProfileRequest(display_name="A2"), current_user=self.user, db=self.db)
        self.assertEqual(self.user.bio, "keep me")

    def test_avatar_upload_sets_url(self):
        with patch("app.routers.auth.storage.save_bytes", return_value="https://b.s3.amazonaws.com/avatars/x.png") as save, \
             patch("app.routers.auth.is_admin", return_value=False):
            out = asyncio.run(upload_avatar(file=_png_upload(), current_user=self.user, db=self.db))
        save.assert_called_once()
        self.assertEqual(str(out.avatar_url), "https://b.s3.amazonaws.com/avatars/x.png")
        self.assertEqual(self.user.avatar_url, "https://b.s3.amazonaws.com/avatars/x.png")

    def test_non_image_rejected(self):
        bad = UploadFile(filename="x.txt", file=io.BytesIO(b"hi"), headers={"content-type": "text/plain"})
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(upload_avatar(file=bad, current_user=self.user, db=self.db))
        self.assertEqual(ctx.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()

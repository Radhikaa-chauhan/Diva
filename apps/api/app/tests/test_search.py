"""Search API: partial matches, private posts excluded."""
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.social import Post
from app.models.user import User
from app.routers.search import search_posts, search_users


class TestSearchApi(unittest.TestCase):

    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        self.db = Session()

        self.alice = User(email="alice@x.com", username="alicewonder", password_hash="h", display_name="Alice W")
        self.bob = User(email="bob@x.com", username="bob", password_hash="h", display_name="Bobby Tables")
        self.db.add_all([self.alice, self.bob])
        self.db.commit()

        self.db.add_all([
            Post(user_id=self.alice.id, job_id="j1", image_url="http://x/1.jpg",
                 caption="golden hour editorial", visibility="public"),
            Post(user_id=self.alice.id, job_id="j2", image_url="http://x/2.jpg",
                 caption="golden secret", visibility="private"),
        ])
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_user_search_partial_match(self):
        result = search_users(q="alice", page=1, per_page=20, db=self.db)
        self.assertEqual(result.total, 1)
        self.assertEqual(result.items[0].username, "alicewonder")

        # display_name matches too
        result = search_users(q="tables", page=1, per_page=20, db=self.db)
        self.assertEqual(result.items[0].username, "bob")

    def test_post_search_excludes_private(self):
        result = search_posts(q="golden", page=1, per_page=20, current_user=self.alice, db=self.db)
        self.assertEqual(result.total, 1)
        self.assertEqual(result.items[0].caption, "golden hour editorial")

    def test_no_match_is_empty_not_error(self):
        result = search_posts(q="zzzz", page=1, per_page=20, current_user=None, db=self.db)
        self.assertEqual(result.total, 0)


if __name__ == "__main__":
    unittest.main()

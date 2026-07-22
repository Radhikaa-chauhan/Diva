"""Feed/explore API: visibility filtering, follow-graph scoping, empty-follow fallback."""
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.social import Follow, Post
from app.models.user import User
from app.routers.feed import get_explore, get_feed


class TestFeedApi(unittest.TestCase):

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

    def tearDown(self):
        self.db.close()

    def _post(self, user, visibility="public", job_id=None):
        post = Post(
            user_id=user.id,
            job_id=job_id or f"job-{user.id}-{visibility}",
            image_url="http://x/r.jpg",
            visibility=visibility,
        )
        self.db.add(post)
        self.db.commit()
        return post

    def test_feed_shows_only_followed_public_posts(self):
        self.db.add(Follow(follower_id=self.alice.id, following_id=self.bob.id))
        self.db.commit()

        public_post = self._post(self.bob, visibility="public")
        self._post(self.bob, visibility="private")  # not in anyone's feed
        self._post(self.carol, visibility="public")  # alice doesn't follow carol

        result = get_feed(page=1, per_page=20, current_user=self.alice, db=self.db)
        self.assertEqual(result.total, 1)
        self.assertEqual(result.items[0].id, public_post.id)

    def test_own_private_post_visible_via_explore_only_to_self(self):
        # Explore never shows private posts, even the owner's — private
        # posts are reached via the single-post GET, not listings.
        self._post(self.alice, visibility="private")
        result = get_explore(page=1, per_page=20, current_user=self.alice, db=self.db)
        self.assertEqual(result.total, 0)

    def test_feed_falls_back_to_explore_when_following_nobody(self):
        self._post(self.bob, visibility="public")
        result = get_feed(page=1, per_page=20, current_user=self.alice, db=self.db)
        self.assertEqual(result.total, 1)

    def test_is_liked_and_is_saved_hydrated_for_viewer(self):
        from app.models.social import Like, SavedPost

        post = self._post(self.bob, visibility="public")
        self.db.add_all([
            Like(user_id=self.alice.id, post_id=post.id),
            SavedPost(user_id=self.alice.id, post_id=post.id),
        ])
        self.db.commit()

        result = get_explore(page=1, per_page=20, current_user=self.alice, db=self.db)
        self.assertTrue(result.items[0].is_liked)
        self.assertTrue(result.items[0].is_saved)

        # Anonymous viewer never sees is_liked/is_saved as true
        anon_result = get_explore(page=1, per_page=20, current_user=None, db=self.db)
        self.assertFalse(anon_result.items[0].is_liked)


if __name__ == "__main__":
    unittest.main()

"""Unit tests for database module, connection checks, and pool metrics."""
import unittest
from unittest.mock import MagicMock, patch

from app.database import (
    Base,
    check_db_connection,
    get_db,
    get_pool_status,
    run_auto_migrations,
)


class TestDatabaseModule(unittest.TestCase):

    def test_check_db_connection(self):
        """Verify database connectivity health check."""
        self.assertTrue(check_db_connection())

    def test_get_pool_status(self):
        """Verify pool status returns dictionary metrics."""
        status = get_pool_status()
        self.assertIn("type", status)

    def test_run_auto_migrations_executes_safely(self):
        """Verify run_auto_migrations executes without error."""
        run_auto_migrations()

    def test_get_db_session_lifecycle(self):
        """Verify get_db dependency yields session and closes cleanly."""
        generator = get_db()
        db_session = next(generator)
        self.assertIsNotNone(db_session)
        try:
            next(generator)
        except StopIteration:
            pass


if __name__ == "__main__":
    unittest.main()

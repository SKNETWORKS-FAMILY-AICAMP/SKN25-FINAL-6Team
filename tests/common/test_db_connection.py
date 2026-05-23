from __future__ import annotations

import os
import unittest

import psycopg
from dotenv import load_dotenv


load_dotenv()

DB_HOST = "100.97.235.15"
DB_PORT = "5432"
DB_USER = "game_cs_user"
DB_NAME = "game_cs"


class TestDbConnection(unittest.TestCase):
    def test_psycopg_connection_with_db_password(self) -> None:
        db_password = os.environ.get("DB_PASSWORD")
        if not db_password:
            self.skipTest("DB_PASSWORD environment variable is required")

        with psycopg.connect(host=DB_HOST, port=DB_PORT, user=DB_USER, password=db_password, dbname=DB_NAME, connect_timeout=15) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                self.assertEqual(cur.fetchone(), (1,))


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional
SCHEMA = '\nCREATE TABLE IF NOT EXISTS profiles (\n    profile_id       TEXT PRIMARY KEY,\n    profile_url      TEXT NOT NULL,\n    name             TEXT,\n    city             TEXT,\n    address          TEXT,\n    email            TEXT,\n    listing_url      TEXT,            \n    listing_title    TEXT,\n    query            TEXT,            \n    listing_count    INTEGER DEFAULT 1,  -- сколько кровельных объявлений этого аккаунта найдено\n    description      TEXT,\n    collected_at     TEXT\n);\n\nCREATE TABLE IF NOT EXISTS processed_listings (\n    listing_url TEXT PRIMARY KEY,\n    query       TEXT,\n    region      TEXT,\n    processed_at TEXT\n);\n\nCREATE TABLE IF NOT EXISTS run_stats (\n    id INTEGER PRIMARY KEY AUTOINCREMENT,\n    query TEXT,\n    region TEXT,\n    listings_found INTEGER,\n    run_at TEXT\n);\nCREATE TABLE IF NOT EXISTS query_completion (\n    query TEXT NOT NULL,\n    region TEXT NOT NULL,\n    completed_at TEXT NOT NULL,\n    PRIMARY KEY (query, region)\n);'

@dataclass
class ProfileRecord:
    profile_id: str
    profile_url: str
    name: str
    city: str
    address: str
    email: str
    listing_url: str
    listing_title: str
    query: str
    description: str = ''

class Database:

    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self):
        self.conn.close()

    def is_listing_processed(self, listing_url: str) -> bool:
        cur = self.conn.execute('SELECT 1 FROM processed_listings WHERE listing_url = ?', (listing_url,))
        return cur.fetchone() is not None

    def mark_listing_processed(self, listing_url: str, query: str, region: str):
        self.conn.execute('INSERT OR IGNORE INTO processed_listings (listing_url, query, region, processed_at) VALUES (?, ?, ?, ?)', (listing_url, query, region, datetime.now().isoformat(timespec='seconds')))
        self.conn.commit()

    def get_profile(self, profile_id: str) -> Optional[sqlite3.Row]:
        self.conn.row_factory = sqlite3.Row
        cur = self.conn.execute('SELECT * FROM profiles WHERE profile_id = ?', (profile_id,))
        return cur.fetchone()

    def upsert_profile(self, rec: ProfileRecord):
        existing = self.get_profile(rec.profile_id)
        if existing is None:
            self.conn.execute('\n                INSERT INTO profiles (\n                    profile_id, profile_url, name, city, address, email,\n                    listing_url, listing_title, query, listing_count,\n                    description, collected_at\n                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)\n                ', (rec.profile_id, rec.profile_url, rec.name, rec.city, rec.address, rec.email, rec.listing_url, rec.listing_title, rec.query, rec.description, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        else:
            self.conn.execute('UPDATE profiles SET listing_count = listing_count + 1 WHERE profile_id = ?', (rec.profile_id,))
        self.conn.commit()

    def profile_exists(self, profile_id: str) -> bool:
        return self.get_profile(profile_id) is not None

    def all_profiles(self) -> list[sqlite3.Row]:
        self.conn.row_factory = sqlite3.Row
        cur = self.conn.execute('SELECT * FROM profiles ORDER BY collected_at')
        return cur.fetchall()

    def count_profiles(self) -> int:
        cur = self.conn.execute('SELECT COUNT(*) FROM profiles')
        return cur.fetchone()[0]

    def log_run_stats(self, query: str, region: str, listings_found: int):
        self.conn.execute('INSERT INTO run_stats (query, region, listings_found, run_at) VALUES (?, ?, ?, ?)', (query, region, listings_found, datetime.now().isoformat(timespec='seconds')))
        self.conn.commit()

    def query_region_done(self, query: str, region: str) -> bool:
        cur = self.conn.execute('SELECT 1 FROM query_completion WHERE query = ? AND region = ? LIMIT 1', (query, region))
        return cur.fetchone() is not None

    def mark_query_complete(self, query: str, region: str):
        self.conn.execute('INSERT OR REPLACE INTO query_completion VALUES (?, ?, ?)', (query, region, datetime.now().isoformat(timespec='seconds')))
        self.conn.commit()

@contextmanager
def open_db(db_path: Path) -> Iterator[Database]:
    db = Database(db_path)
    try:
        yield db
    finally:
        db.close()

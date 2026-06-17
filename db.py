"""Database setup: connection helper + schema.

The data model is three tables:

  movies         one row per film (the facts you filter on)
  genres         the canonical genre list from TMDb (id -> name)
  movie_genres   junction table linking the two (a movie has many genres)

Splitting genres into their own table is what lets us cleanly support
"match ANY of these genres" vs. "match ALL of these genres" later on.
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "movies.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS movies (
    id                INTEGER PRIMARY KEY,   -- TMDb movie id
    title             TEXT    NOT NULL,
    release_year      INTEGER,
    rating            REAL,                  -- TMDb vote_average (0-10)
    vote_count        INTEGER,
    runtime           INTEGER,               -- minutes; NULL until enriched
    original_language TEXT,                  -- ISO 639-1 code, e.g. "en"
    overview          TEXT,
    poster_url        TEXT,
    popularity        REAL
);

CREATE TABLE IF NOT EXISTS genres (
    id   INTEGER PRIMARY KEY,                -- TMDb genre id
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS movie_genres (
    movie_id INTEGER NOT NULL REFERENCES movies(id) ON DELETE CASCADE,
    genre_id INTEGER NOT NULL REFERENCES genres(id) ON DELETE CASCADE,
    PRIMARY KEY (movie_id, genre_id)
);

-- Indexes that make the common filters fast.
CREATE INDEX IF NOT EXISTS idx_movies_year     ON movies(release_year);
CREATE INDEX IF NOT EXISTS idx_movies_rating    ON movies(rating);
CREATE INDEX IF NOT EXISTS idx_movies_language  ON movies(original_language);
CREATE INDEX IF NOT EXISTS idx_mg_genre         ON movie_genres(genre_id);
"""


def get_connection() -> sqlite3.Connection:
    """Return a SQLite connection with row access by column name and FKs on."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Create the tables and indexes if they don't already exist."""
    with get_connection() as conn:
        conn.executescript(SCHEMA)
    print(f"Database ready at {DB_PATH}")


if __name__ == "__main__":
    init_db()

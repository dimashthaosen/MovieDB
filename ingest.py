"""Pull movie data from TMDb into the local SQLite database.

Usage:
    python ingest.py                 # load ~200 popular movies (10 pages)
    python ingest.py --pages 25      # load ~500 movies
    python ingest.py --enrich        # also fetch runtime for each movie (slow)

This covers build steps 1 & 2: get data from the API and store it locally
so filtering is fast and you're never blocked by rate limits.
"""

import argparse
import os
import time

import requests
from dotenv import load_dotenv

from db import get_connection, init_db

load_dotenv()

API_KEY = os.getenv("TMDB_API_KEY")
BASE_URL = "https://api.themoviedb.org/3"
IMAGE_BASE = "https://image.tmdb.org/t/p/w342"  # poster size


def _require_key() -> None:
    if not API_KEY or API_KEY == "your_key_here":
        raise SystemExit(
            "No TMDb API key found.\n"
            "  1. Copy .env.example to .env\n"
            "  2. Paste your key (https://www.themoviedb.org/settings/api)\n"
        )


def _get(path: str, **params) -> dict:
    """Call a TMDb endpoint and return the parsed JSON."""
    params["api_key"] = API_KEY
    resp = requests.get(f"{BASE_URL}{path}", params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def load_genres(conn) -> None:
    """Fetch the canonical genre list and upsert it."""
    data = _get("/genre/movie/list", language="en-US")
    rows = [(g["id"], g["name"]) for g in data["genres"]]
    conn.executemany(
        "INSERT INTO genres (id, name) VALUES (?, ?) "
        "ON CONFLICT(id) DO UPDATE SET name = excluded.name",
        rows,
    )
    print(f"Loaded {len(rows)} genres")


def _poster_url(poster_path: str | None) -> str | None:
    return f"{IMAGE_BASE}{poster_path}" if poster_path else None


def _year(release_date: str | None) -> int | None:
    if release_date and len(release_date) >= 4:
        try:
            return int(release_date[:4])
        except ValueError:
            return None
    return None


def store_movie(conn, m: dict, runtime: int | None = None) -> None:
    """Upsert a single movie row and its genre links."""
    conn.execute(
        """
        INSERT INTO movies
            (id, title, release_year, rating, vote_count, runtime,
             original_language, overview, poster_url, popularity)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            title=excluded.title, release_year=excluded.release_year,
            rating=excluded.rating, vote_count=excluded.vote_count,
            runtime=COALESCE(excluded.runtime, movies.runtime),
            original_language=excluded.original_language,
            overview=excluded.overview, poster_url=excluded.poster_url,
            popularity=excluded.popularity
        """,
        (
            m["id"], m.get("title", "Untitled"), _year(m.get("release_date")),
            m.get("vote_average"), m.get("vote_count"), runtime,
            m.get("original_language"), m.get("overview"),
            _poster_url(m.get("poster_path")), m.get("popularity"),
        ),
    )
    conn.execute("DELETE FROM movie_genres WHERE movie_id = ?", (m["id"],))
    genre_ids = m.get("genre_ids") or [g["id"] for g in m.get("genres", [])]
    if genre_ids:
        conn.executemany(
            "INSERT OR IGNORE INTO movie_genres (movie_id, genre_id) VALUES (?, ?)",
            [(m["id"], gid) for gid in genre_ids],
        )


def ingest(pages: int, enrich: bool) -> None:
    _require_key()
    init_db()
    conn = get_connection()
    with conn:
        load_genres(conn)
        total = 0
        for page in range(1, pages + 1):
            data = _get(
                "/discover/movie",
                sort_by="popularity.desc",
                include_adult="false",
                page=page,
            )
            for m in data["results"]:
                runtime = None
                if enrich:
                    details = _get(f"/movie/{m['id']}")
                    runtime = details.get("runtime")
                    time.sleep(0.05)  # be polite to the API
                store_movie(conn, m, runtime)
                total += 1
            print(f"Page {page}/{pages} -> {total} movies so far")
            time.sleep(0.1)
    conn.close()
    print(f"\nDone. {total} movies in the database.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Load movies from TMDb into SQLite.")
    parser.add_argument("--pages", type=int, default=10,
                        help="number of TMDb pages to fetch (20 movies each)")
    parser.add_argument("--enrich", action="store_true",
                        help="also fetch runtime per movie (1 extra API call each)")
    args = parser.parse_args()
    ingest(args.pages, args.enrich)

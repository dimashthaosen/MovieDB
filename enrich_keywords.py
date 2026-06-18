"""Fetch TMDb keywords for every movie in the database.

Keywords are far more specific than the 19 broad genres (e.g. 'film noir',
'anime', 'cyberpunk', 'heist'), so they're what we build the fine-grained
"collections" on top of. Run once after ingesting movies:

    python enrich_keywords.py

It's resumable — only movies without keywords yet are fetched, so re-running
after an interruption picks up where it left off.
"""

import time

from db import get_connection, init_db
from ingest import _get, _require_key  # reuse the resilient, host-failover GET


def enrich() -> None:
    _require_key()
    init_db()
    conn = get_connection()

    pending = conn.execute(
        "SELECT id FROM movies "
        "WHERE id NOT IN (SELECT DISTINCT movie_id FROM movie_keywords) "
        "ORDER BY popularity DESC"
    ).fetchall()
    total = len(pending)
    print(f"{total} movies need keywords.")

    done = 0
    for row in pending:
        movie_id = row["id"]
        data = _get(f"/movie/{movie_id}/keywords")
        kws = data.get("keywords", [])
        with conn:
            if kws:
                conn.executemany(
                    "INSERT INTO keywords (id, name) VALUES (?, ?) "
                    "ON CONFLICT(id) DO UPDATE SET name = excluded.name",
                    [(k["id"], k["name"]) for k in kws],
                )
                conn.executemany(
                    "INSERT OR IGNORE INTO movie_keywords (movie_id, keyword_id) VALUES (?, ?)",
                    [(movie_id, k["id"]) for k in kws],
                )
        done += 1
        if done % 50 == 0 or done == total:
            print(f"  {done}/{total} movies enriched")
        time.sleep(0.03)  # be polite to the API

    conn.close()
    print("Done.")


if __name__ == "__main__":
    enrich()

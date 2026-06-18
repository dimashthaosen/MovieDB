"""Resilient, cached TMDb HTTP client — the single source of movie data.

The app runs "live": every request is served straight from TMDb rather than a
local database. This module owns the HTTP details so queries.py and the ingest
scripts can share one client:

  - Host failover: some ISPs block api.themoviedb.org but leave api.tmdb.org
    reachable, so we sweep both with retry + backoff.
  - In-memory response cache (short TTL) so repeated/paginated requests and the
    genre list don't re-hit the network on every page load.

Requires TMDB_API_KEY in the environment (a .env locally, or the host's env
vars in production).
"""

import os
import time

import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("TMDB_API_KEY")
IMAGE_BASE = "https://image.tmdb.org/t/p/w342"

# Tried in order; first reachable host wins and is remembered for the rest.
API_HOSTS = [
    "https://api.themoviedb.org/3",
    "https://api.tmdb.org/3",
]
MAX_ROUNDS = 4
CACHE_TTL = 300  # seconds

_base_url: str | None = None
_cache: dict[str, tuple[float, dict]] = {}


class TMDbError(RuntimeError):
    pass


class TMDbNotFound(TMDbError):
    """A 404 from TMDb (e.g. unknown movie id) — not retried."""


def require_key() -> None:
    if not API_KEY or API_KEY == "your_key_here":
        raise TMDbError(
            "No TMDb API key. Set TMDB_API_KEY in the environment "
            "(a .env file locally, or your host's env vars in production)."
        )


def _candidate_hosts() -> list[str]:
    if _base_url:
        return [_base_url] + [h for h in API_HOSTS if h != _base_url]
    return list(API_HOSTS)


def get(path: str, **params) -> dict:
    """GET a TMDb endpoint as JSON, with caching and host failover."""
    require_key()
    cache_key = path + "?" + "&".join(f"{k}={params[k]}" for k in sorted(params))
    now = time.time()
    cached = _cache.get(cache_key)
    if cached and cached[0] > now:
        return cached[1]

    query = {**params, "api_key": API_KEY}
    last_err = None
    global _base_url
    for attempt in range(MAX_ROUNDS):
        for host in _candidate_hosts():
            try:
                resp = requests.get(f"{host}{path}", params=query, timeout=15)
                if resp.status_code == 404:
                    raise TMDbNotFound(path)
                if resp.status_code in (401, 403):
                    # Bad/missing/unauthorised key — fail fast with a clear message.
                    # Retrying would just burn the serverless timeout and 502.
                    raise TMDbError(
                        f"TMDb auth failed ({resp.status_code}). Check TMDB_API_KEY "
                        f"is set correctly in the environment. Response: {resp.text[:160]}"
                    )
                resp.raise_for_status()
                data = resp.json()
                _base_url = host
                _cache[cache_key] = (now + CACHE_TTL, data)
                return data
            except requests.RequestException as e:
                last_err = e
        time.sleep(1.0 * (attempt + 1))
    raise TMDbError(f"TMDb unreachable after {MAX_ROUNDS} retries: {type(last_err).__name__}")


def poster_url(poster_path: str | None) -> str | None:
    return f"{IMAGE_BASE}{poster_path}" if poster_path else None


def year_of(release_date: str | None) -> int | None:
    if release_date and len(release_date) >= 4 and release_date[:4].isdigit():
        return int(release_date[:4])
    return None

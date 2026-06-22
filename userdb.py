"""User accounts + saved taste profiles, stored in Postgres (Vercel Postgres / Neon).

Storage is optional: if POSTGRES_URL isn't set, configured() is False and the
account endpoints return 503, so the rest of the app keeps working. Tables are
created automatically on first use — there's no SQL to run by hand.
"""

import os

import bcrypt
import psycopg
from psycopg.types.json import Jsonb

def _resolve_database_url():
    """Find the Postgres connection string under whatever name the host used.

    Vercel/Neon name it after the prefix chosen when connecting the database
    (e.g. POSTGRES_URL, STORAGE_URL, DATABASE_URL). As a last resort we scan the
    environment for any value that looks like a Postgres URL, so it works no
    matter which prefix was picked in the Vercel dialog.
    """
    for name in ("POSTGRES_URL", "DATABASE_URL", "STORAGE_URL", "POSTGRES_PRISMA_URL",
                 "STORAGE_POSTGRES_URL", "DATABASE_POSTGRES_URL", "POSTGRES_URL_NON_POOLING"):
        value = os.getenv(name)
        if value:
            return value
    for value in os.environ.values():
        if isinstance(value, str) and value.startswith(("postgres://", "postgresql://")):
            return value
    return None


DATABASE_URL = _resolve_database_url()

STATEMENTS = [
    """CREATE TABLE IF NOT EXISTS users (
        id            serial PRIMARY KEY,
        email         text UNIQUE NOT NULL,
        password_hash text NOT NULL,
        created_at    timestamptz DEFAULT now()
    )""",
    """CREATE TABLE IF NOT EXISTS taste_profiles (
        user_id    integer PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
        profile    jsonb NOT NULL,
        updated_at timestamptz DEFAULT now()
    )""",
    """CREATE TABLE IF NOT EXISTS favorites (
        user_id  integer NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        movie_id integer NOT NULL,
        movie    jsonb NOT NULL,
        added_at timestamptz DEFAULT now(),
        PRIMARY KEY (user_id, movie_id)
    )""",
]

_initialized = False


class EmailTaken(Exception):
    pass


def configured() -> bool:
    return bool(DATABASE_URL)


def _connect():
    if not DATABASE_URL:
        raise RuntimeError("POSTGRES_URL is not set")
    # prepare_threshold=None keeps us compatible with pgbouncer (Vercel's pooled URL).
    return psycopg.connect(DATABASE_URL, prepare_threshold=None)


def init_db() -> None:
    """Create tables if needed (runs once per process)."""
    global _initialized
    if _initialized:
        return
    with _connect() as conn:
        for stmt in STATEMENTS:
            conn.execute(stmt)
    _initialized = True


def _hash(password: str) -> str:
    return bcrypt.hashpw(password.encode()[:72], bcrypt.gensalt()).decode()


def _verify(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode()[:72], hashed.encode())
    except ValueError:
        return False


def create_user(email: str, password: str) -> dict:
    init_db()
    try:
        with _connect() as conn:
            row = conn.execute(
                "INSERT INTO users (email, password_hash) VALUES (%s, %s) RETURNING id, email",
                (email.strip().lower(), _hash(password)),
            ).fetchone()
        return {"id": row[0], "email": row[1]}
    except psycopg.errors.UniqueViolation:
        raise EmailTaken()


def authenticate(email: str, password: str) -> dict | None:
    init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, email, password_hash FROM users WHERE email = %s",
            (email.strip().lower(),),
        ).fetchone()
    if not row or not _verify(password, row[2]):
        return None
    return {"id": row[0], "email": row[1]}


def get_profile(user_id: int):
    init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT profile FROM taste_profiles WHERE user_id = %s", (user_id,)
        ).fetchone()
    return row[0] if row else None


def save_profile(user_id: int, profile: dict) -> None:
    init_db()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO taste_profiles (user_id, profile, updated_at) "
            "VALUES (%s, %s, now()) "
            "ON CONFLICT (user_id) DO UPDATE SET profile = EXCLUDED.profile, updated_at = now()",
            (user_id, Jsonb(profile)),
        )


def list_favorites(user_id: int) -> list[dict]:
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT movie FROM favorites WHERE user_id = %s ORDER BY added_at DESC",
            (user_id,),
        ).fetchall()
    return [r[0] for r in rows]


def add_favorite(user_id: int, movie: dict) -> None:
    init_db()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO favorites (user_id, movie_id, movie) VALUES (%s, %s, %s) "
            "ON CONFLICT (user_id, movie_id) DO UPDATE SET movie = EXCLUDED.movie",
            (user_id, int(movie["id"]), Jsonb(movie)),
        )


def remove_favorite(user_id: int, movie_id: int) -> None:
    init_db()
    with _connect() as conn:
        conn.execute(
            "DELETE FROM favorites WHERE user_id = %s AND movie_id = %s",
            (user_id, movie_id),
        )

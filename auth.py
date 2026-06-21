"""Login tokens (JWT). Stateless: the signed token *is* the session.

Set JWT_SECRET in the environment to a long random string. A weak default is
used only so local dev doesn't crash before it's configured.
"""

import os
import time

import jwt

SECRET = os.getenv("JWT_SECRET", "dev-insecure-change-me")
ALGORITHM = "HS256"
TTL_SECONDS = 60 * 60 * 24 * 30  # 30 days


def make_token(user: dict) -> str:
    payload = {
        "sub": str(user["id"]),
        "email": user["email"],
        "exp": int(time.time()) + TTL_SECONDS,
    }
    return jwt.encode(payload, SECRET, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """Return the token payload, or raise jwt.PyJWTError if invalid/expired."""
    return jwt.decode(token, SECRET, algorithms=[ALGORITHM])

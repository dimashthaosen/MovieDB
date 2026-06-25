"""FastAPI app: exposes the filter query as a REST endpoint and serves the UI.

Run with:
    uvicorn main:app --reload

Then open http://127.0.0.1:8000  (UI)
Interactive API docs are at http://127.0.0.1:8000/docs
"""

from pathlib import Path

import psycopg
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import auth
import companion
import queries
import tmdb
import userdb

app = FastAPI(title="Movie Recommendation App")


@app.exception_handler(tmdb.TMDbError)
async def _tmdb_error(request, exc: tmdb.TMDbError):
    """Surface TMDb outages / missing key as a clean 502 instead of a 500."""
    return JSONResponse(status_code=502, content={"detail": f"TMDb data unavailable: {exc}"})


@app.exception_handler(psycopg.Error)
async def _db_error(request, exc: psycopg.Error):
    """Database hiccup -> clean 503 instead of a 500."""
    return JSONResponse(status_code=503, content={"detail": "Account storage is unavailable right now."})

STATIC_DIR = Path(__file__).parent / "static"


@app.get("/api/genres")
def get_genres():
    """All available genres, for the filter dropdown."""
    return queries.list_genres()


@app.get("/api/collections")
def get_collections():
    """Curated fine-grained sub-genres (Crime Noir, Anime, …) with movie counts."""
    return queries.list_collections()


@app.get("/api/movies")
def get_movies(
    query: str | None = Query(default=None, description="independent title search"),
    genres: list[int] | None = Query(default=None, description="genre ids to match"),
    genre_match: str = Query(default="any", pattern="^(any|all)$"),
    year_min: int | None = None,
    year_max: int | None = None,
    rating_min: float | None = Query(default=None, ge=0, le=10),
    language: str | None = None,
    runtime_max: int | None = None,
    collection: str | None = Query(default=None, description="curated sub-genre slug, e.g. 'crime-noir'"),
    sort_by: str = Query(default="popularity", pattern="^(rating|popularity|year|title|runtime|best_match)$"),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """Filtered movie search. Every parameter is optional."""
    fetch_limit = limit + 1
    using_fallback = False
    try:
        if query and query.strip():
            results = queries.search_movie_titles(query, limit=fetch_limit, offset=offset)
        else:
            keyword_ids = queries.keyword_ids_for_collection(collection) if collection else None
            results = queries.search_movies(
                genres=genres, genre_match=genre_match,
                year_min=year_min, year_max=year_max, rating_min=rating_min,
                language=language, runtime_max=runtime_max, keyword_ids=keyword_ids,
                sort_by=sort_by, sort_dir=sort_dir, limit=fetch_limit, offset=offset,
            )
    except tmdb.TMDbError:
        using_fallback = True
        results = queries.fallback_movies(
            query=query, collection=collection, genres=genres,
            year_min=year_min, year_max=year_max, rating_min=rating_min,
            language=language, runtime_max=runtime_max,
            sort_by=sort_by, sort_dir=sort_dir, limit=fetch_limit, offset=offset,
        )
    has_more = len(results) > limit
    return {
        "count": min(len(results), limit),
        "has_more": has_more,
        "results": results[:limit],
        "fallback": using_fallback,
        "warning": "TMDb is temporarily unavailable, showing offline fallback results." if using_fallback else None,
    }


@app.get("/api/movies/{movie_id}")
def get_movie(movie_id: int):
    """Full details for a single movie."""
    movie = queries.get_movie(movie_id)
    if movie is None:
        raise HTTPException(status_code=404, detail="Movie not found")
    return movie


@app.get("/api/movies/{movie_id}/extras")
def get_movie_extras(movie_id: int):
    """Cast, crew, trailer, and production facts for a single movie."""
    extras = queries.get_movie_extras(movie_id)
    if extras is None:
        raise HTTPException(status_code=404, detail="Movie not found")
    return extras


@app.get("/api/movies/{movie_id}/similar")
def get_similar(movie_id: int, limit: int = Query(default=12, ge=1, le=50)):
    """Movies most similar to this one, ranked by shared genres."""
    if queries.get_movie(movie_id) is None:
        raise HTTPException(status_code=404, detail="Movie not found")
    return {"results": queries.similar_movies(movie_id, limit=limit)}


@app.get("/api/movies/{movie_id}/recommendations")
def get_recommendation_groups(movie_id: int, limit: int = Query(default=8, ge=1, le=20)):
    groups = queries.recommendation_groups(movie_id, limit=limit)
    if groups is None:
        raise HTTPException(status_code=404, detail="Movie not found")
    return {"groups": groups}


@app.get("/api/movies/{movie_id}/watch-providers")
def get_watch_providers(movie_id: int, region: str = Query(default="IN", min_length=2, max_length=2)):
    if queries.get_movie(movie_id) is None:
        raise HTTPException(status_code=404, detail="Movie not found")
    return queries.watch_providers(movie_id, region=region)


@app.get("/api/people")
def search_people(query: str, limit: int = Query(default=6, ge=1, le=12)):
    return {"results": queries.search_people(query, limit=limit)}


@app.get("/api/people/{person_id}/movies")
def get_person_movies(person_id: int, limit: int = Query(default=24, ge=1, le=50)):
    person = queries.person_movies(person_id, limit=limit)
    if person is None:
        raise HTTPException(status_code=404, detail="Person not found")
    return person


@app.get("/api/suggest")
def suggest_titles(query: str, limit: int = Query(default=6, ge=1, le=12)):
    return {"results": queries.suggest_titles(query, limit=limit)}


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    context: dict | None = None


class TasteProfileRequest(BaseModel):
    liked_movie_ids: list[int | None] = []
    vibes: list[str] = []
    rating_flexibility: float = 0.35
    language_scope: str | None = None
    era: str | None = None
    runtime: str | None = None
    movie_type: str | None = None
    zeitgeist: str | None = None
    limit: int = 24


def _optional_user_from_authorization(authorization: str) -> dict | None:
    token = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
    if not token:
        return None
    try:
        payload = auth.decode_token(token)
    except auth.jwt.PyJWTError:
        return None
    return {"id": int(payload["sub"]), "email": payload["email"]}


def _unique_ids(ids: list[int | None]) -> list[int]:
    out = []
    seen = set()
    for mid in ids:
        if not mid:
            continue
        mid = int(mid)
        if mid in seen:
            continue
        seen.add(mid)
        out.append(mid)
    return out


@app.post("/api/recommendations/personalized")
def personalized_recommendations(req: TasteProfileRequest, authorization: str = Header(default="")):
    profile = req.dict()
    profile["manual_liked_movie_ids"] = _unique_ids(req.liked_movie_ids)
    user = _optional_user_from_authorization(authorization)
    if user and userdb.configured():
        favorites = userdb.list_favorites(user["id"])
        favorite_ids = [m.get("id") for m in favorites if isinstance(m, dict)]
        profile["favorite_movie_ids"] = _unique_ids(favorite_ids)
        profile["liked_movie_ids"] = _unique_ids(req.liked_movie_ids + favorite_ids)
    else:
        profile["favorite_movie_ids"] = []
    limit = max(1, min(req.limit, 50))
    return queries.personalized_recommendations(profile, limit=limit)


@app.post("/api/chat")
def chat(req: ChatRequest):
    """AI companion: natural-language movie recommendations grounded in the DB."""
    history = [{"role": m.role, "content": m.content} for m in req.messages]
    try:
        return companion.chat(history, context=req.context)
    except RuntimeError as e:  # missing API key
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:  # upstream / network failure
        raise HTTPException(status_code=502, detail=f"Companion error: {type(e).__name__}")


@app.get("/api/config")
def get_config():
    """Public flags the frontend needs at boot (e.g. whether accounts are on)."""
    return {"accounts_enabled": userdb.configured()}


# ---------------- Accounts + saved taste profiles ----------------
class Credentials(BaseModel):
    email: str
    password: str


class ProfileBody(BaseModel):
    profile: dict


def _require_storage() -> None:
    if not userdb.configured():
        raise HTTPException(status_code=503, detail="Accounts aren't configured on this deployment.")


def current_user(authorization: str = Header(default="")) -> dict:
    token = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
    if not token:
        raise HTTPException(status_code=401, detail="Please sign in.")
    try:
        payload = auth.decode_token(token)
    except auth.jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Your session expired — sign in again.")
    return {"id": int(payload["sub"]), "email": payload["email"]}


@app.post("/api/auth/signup")
def signup(body: Credentials):
    _require_storage()
    email = body.email.strip()
    if "@" not in email or "." not in email or len(body.password) < 6:
        raise HTTPException(status_code=400, detail="Enter a valid email and a password of at least 6 characters.")
    try:
        user = userdb.create_user(email, body.password)
    except userdb.EmailTaken:
        raise HTTPException(status_code=409, detail="That email is already registered. Try logging in.")
    return {"token": auth.make_token(user), "email": user["email"]}


@app.post("/api/auth/login")
def login(body: Credentials):
    _require_storage()
    user = userdb.authenticate(body.email, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="Wrong email or password.")
    return {"token": auth.make_token(user), "email": user["email"]}


@app.get("/api/auth/me")
def whoami(user=Depends(current_user)):
    return {"email": user["email"]}


@app.get("/api/taste-profile")
def get_taste_profile(user=Depends(current_user)):
    _require_storage()
    return {"profile": userdb.get_profile(user["id"])}


@app.put("/api/taste-profile")
def put_taste_profile(body: ProfileBody, user=Depends(current_user)):
    _require_storage()
    userdb.save_profile(user["id"], body.profile)
    return {"ok": True}


class FavoriteBody(BaseModel):
    movie: dict


@app.get("/api/favorites")
def get_favorites(user=Depends(current_user)):
    _require_storage()
    return {"results": userdb.list_favorites(user["id"])}


@app.post("/api/favorites")
def add_favorite(body: FavoriteBody, user=Depends(current_user)):
    _require_storage()
    if not body.movie.get("id"):
        raise HTTPException(status_code=400, detail="movie.id is required")
    userdb.add_favorite(user["id"], body.movie)
    return {"ok": True}


@app.delete("/api/favorites/{movie_id}")
def delete_favorite(movie_id: int, user=Depends(current_user)):
    _require_storage()
    userdb.remove_favorite(user["id"], movie_id)
    return {"ok": True}


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


# Serve the rest of the static files (if you add CSS/JS files later).
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

"""FastAPI app: exposes the filter query as a REST endpoint and serves the UI.

Run with:
    uvicorn main:app --reload

Then open http://127.0.0.1:8000  (UI)
Interactive API docs are at http://127.0.0.1:8000/docs
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import companion
import queries
import tmdb

app = FastAPI(title="Movie Recommendation App")


@app.exception_handler(tmdb.TMDbError)
async def _tmdb_error(request, exc: tmdb.TMDbError):
    """Surface TMDb outages / missing key as a clean 502 instead of a 500."""
    return JSONResponse(status_code=502, content={"detail": f"TMDb data unavailable: {exc}"})

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
    genres: list[int] | None = Query(default=None, description="genre ids to match"),
    genre_match: str = Query(default="any", pattern="^(any|all)$"),
    year_min: int | None = None,
    year_max: int | None = None,
    rating_min: float | None = Query(default=None, ge=0, le=10),
    language: str | None = None,
    runtime_max: int | None = None,
    collection: str | None = Query(default=None, description="curated sub-genre slug, e.g. 'crime-noir'"),
    sort_by: str = Query(default="popularity", pattern="^(rating|popularity|year|title|runtime)$"),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """Filtered movie search. Every parameter is optional."""
    keyword_ids = queries.keyword_ids_for_collection(collection) if collection else None
    results = queries.search_movies(
        genres=genres, genre_match=genre_match,
        year_min=year_min, year_max=year_max, rating_min=rating_min,
        language=language, runtime_max=runtime_max, keyword_ids=keyword_ids,
        sort_by=sort_by, sort_dir=sort_dir, limit=limit, offset=offset,
    )
    return {"count": len(results), "results": results}


@app.get("/api/movies/{movie_id}")
def get_movie(movie_id: int):
    """Full details for a single movie."""
    movie = queries.get_movie(movie_id)
    if movie is None:
        raise HTTPException(status_code=404, detail="Movie not found")
    return movie


@app.get("/api/movies/{movie_id}/similar")
def get_similar(movie_id: int, limit: int = Query(default=12, ge=1, le=50)):
    """Movies most similar to this one, ranked by shared genres."""
    if queries.get_movie(movie_id) is None:
        raise HTTPException(status_code=404, detail="Movie not found")
    return {"results": queries.similar_movies(movie_id, limit=limit)}


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]


@app.post("/api/chat")
def chat(req: ChatRequest):
    """AI companion: natural-language movie recommendations grounded in the DB."""
    history = [{"role": m.role, "content": m.content} for m in req.messages]
    try:
        return companion.chat(history)
    except RuntimeError as e:  # missing API key
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:  # upstream / network failure
        raise HTTPException(status_code=502, detail=f"Companion error: {type(e).__name__}")


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


# Serve the rest of the static files (if you add CSS/JS files later).
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

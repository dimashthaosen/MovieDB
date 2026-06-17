"""FastAPI app: exposes the filter query as a REST endpoint and serves the UI.

Run with:
    uvicorn main:app --reload

Then open http://127.0.0.1:8000  (UI)
Interactive API docs are at http://127.0.0.1:8000/docs
"""

from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import queries

app = FastAPI(title="Movie Recommendation App")

STATIC_DIR = Path(__file__).parent / "static"


@app.get("/api/genres")
def get_genres():
    """All available genres, for the filter dropdown."""
    return queries.list_genres()


@app.get("/api/movies")
def get_movies(
    genres: list[int] | None = Query(default=None, description="genre ids to match"),
    genre_match: str = Query(default="any", pattern="^(any|all)$"),
    year_min: int | None = None,
    year_max: int | None = None,
    rating_min: float | None = Query(default=None, ge=0, le=10),
    language: str | None = None,
    runtime_max: int | None = None,
    sort_by: str = Query(default="popularity", pattern="^(rating|popularity|year|title|runtime)$"),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """Filtered movie search. Every parameter is optional."""
    results = queries.search_movies(
        genres=genres, genre_match=genre_match,
        year_min=year_min, year_max=year_max, rating_min=rating_min,
        language=language, runtime_max=runtime_max,
        sort_by=sort_by, sort_dir=sort_dir, limit=limit, offset=offset,
    )
    return {"count": len(results), "results": results}


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


# Serve the rest of the static files (if you add CSS/JS files later).
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

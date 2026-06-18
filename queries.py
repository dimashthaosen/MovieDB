"""The data layer — served live from TMDb (no local database).

Every filter choice becomes a TMDb /discover/movie query parameter; details and
recommendations come from /movie/{id}. Function signatures and return shapes are
unchanged from the old SQLite version, so the API, frontend, and AI companion
all work without modification.

Movie dicts have the same shape everywhere:
    id, title, release_year, rating, vote_count, runtime, original_language,
    overview, poster_url, popularity, genres (list of names)
"""

import subgenres
import tmdb

# Our sort keys -> TMDb /discover sort_by fields.
SORT_MAP = {
    "popularity": "popularity",
    "rating": "vote_average",
    "year": "primary_release_date",
    "title": "original_title",
    "runtime": "popularity",  # TMDb can't sort by runtime; fall back gracefully
}

_genre_map: dict[int, str] | None = None


def _genre_id_to_name() -> dict[int, str]:
    """Cached TMDb genre id -> name map."""
    global _genre_map
    if _genre_map is None:
        data = tmdb.get("/genre/movie/list", language="en-US")
        _genre_map = {g["id"]: g["name"] for g in data["genres"]}
    return _genre_map


def _to_movie(item: dict) -> dict:
    """Normalise a TMDb movie (list item or full detail) to our shape."""
    gm = _genre_id_to_name()
    raw_genres = item.get("genres")
    if raw_genres and isinstance(raw_genres[0], dict):       # full detail
        genres = sorted(g["name"] for g in raw_genres)
    else:                                                    # list item: genre_ids
        genres = sorted(gm[g] for g in item.get("genre_ids", []) if g in gm)
    va = item.get("vote_average")
    return {
        "id": item["id"],
        "title": item.get("title") or "Untitled",
        "release_year": tmdb.year_of(item.get("release_date")),
        "rating": round(va, 1) if va else None,
        "vote_count": item.get("vote_count"),
        "runtime": item.get("runtime"),  # present only on /movie/{id}
        "original_language": item.get("original_language"),
        "overview": item.get("overview"),
        "poster_url": tmdb.poster_url(item.get("poster_path")),
        "popularity": item.get("popularity"),
        "genres": genres,
    }


def _discover_slice(params: dict, limit: int, offset: int) -> list[dict]:
    """Fetch the TMDb /discover pages covering [offset, offset+limit) and slice.

    TMDb paginates 20 results per page, so we fetch only the pages that overlap
    the requested window and slice within them.
    """
    first_page = offset // 20 + 1
    last_page = min((offset + limit - 1) // 20 + 1, 500)  # TMDb caps at page 500
    collected: list[dict] = []
    for page in range(first_page, last_page + 1):
        data = tmdb.get("/discover/movie", page=page, **params)
        collected.extend(data.get("results", []))
        if page >= data.get("total_pages", page):
            break
    base = (first_page - 1) * 20
    return collected[offset - base: offset - base + limit]


def search_movies(
    genres: list[int] | None = None,
    genre_match: str = "any",
    year_min: int | None = None,
    year_max: int | None = None,
    rating_min: float | None = None,
    language: str | None = None,
    runtime_max: int | None = None,
    keyword_ids: list[int] | None = None,
    sort_by: str = "popularity",
    sort_dir: str = "desc",
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """Filtered movie search via TMDb /discover. Every filter is optional."""
    direction = "asc" if sort_dir.lower() == "asc" else "desc"
    params: dict = {
        "include_adult": "false",
        "sort_by": f"{SORT_MAP.get(sort_by, 'popularity')}.{direction}",
    }
    if genres:
        sep = "," if genre_match == "all" else "|"   # comma = AND, pipe = OR
        params["with_genres"] = sep.join(str(g) for g in genres)
    if year_min is not None:
        params["primary_release_date.gte"] = f"{year_min}-01-01"
    if year_max is not None:
        params["primary_release_date.lte"] = f"{year_max}-12-31"
    if rating_min is not None:
        params["vote_average.gte"] = rating_min
        params["vote_count.gte"] = 100               # ignore obscure perfect scores
    if sort_by == "rating":
        params.setdefault("vote_count.gte", 200)     # quality floor when ranking by rating
    if language:
        params["with_original_language"] = language
    if runtime_max is not None:
        params["with_runtime.lte"] = runtime_max
    if keyword_ids:
        params["with_keywords"] = "|".join(str(k) for k in keyword_ids)

    return [_to_movie(it) for it in _discover_slice(params, limit, offset)]


def get_movie(movie_id: int) -> dict | None:
    """Full details for a single movie, or None if it doesn't exist."""
    try:
        data = tmdb.get(f"/movie/{movie_id}")
    except tmdb.TMDbNotFound:
        return None
    return _to_movie(data)


def similar_movies(movie_id: int, limit: int = 12) -> list[dict]:
    """Movies similar to the given one, via TMDb recommendations.

    Each result carries `shared_genres` (overlap with the reference movie's
    genres) so the UI can still show a "N shared genres" label.
    """
    try:
        ref = tmdb.get(f"/movie/{movie_id}")
    except tmdb.TMDbNotFound:
        return []
    ref_genres = {g["id"] for g in ref.get("genres", [])}

    data = tmdb.get(f"/movie/{movie_id}/recommendations", page=1)
    results = data.get("results", [])
    if not results:  # fall back to TMDb's "similar" if no recommendations
        results = tmdb.get(f"/movie/{movie_id}/similar", page=1).get("results", [])

    movies = []
    for it in results[:limit]:
        m = _to_movie(it)
        m["shared_genres"] = len(set(it.get("genre_ids", [])) & ref_genres)
        movies.append(m)
    return movies


def find_by_title(title: str) -> dict | None:
    """Best-effort lookup of a movie by title (most popular match)."""
    if not title:
        return None
    results = tmdb.get("/search/movie", query=title, include_adult="false").get("results", [])
    if not results:
        return None
    return _to_movie(max(results, key=lambda r: r.get("popularity", 0)))


def list_genres() -> list[dict]:
    """All TMDb genres, for the filter dropdown."""
    data = tmdb.get("/genre/movie/list", language="en-US")
    return [{"id": g["id"], "name": g["name"]}
            for g in sorted(data["genres"], key=lambda g: g["name"])]


def keyword_ids_for_collection(slug: str) -> list[int]:
    """The TMDb keyword ids that define a curated collection."""
    coll = subgenres.get(slug)
    return coll["keyword_ids"] if coll else []


def list_collections(min_count: int = 3) -> list[dict]:
    """Curated sub-genre collections with live TMDb counts (drops empty ones)."""
    out = []
    for coll in subgenres.COLLECTIONS:
        ids = coll.get("keyword_ids") or []
        if not ids:
            continue
        data = tmdb.get(
            "/discover/movie",
            with_keywords="|".join(str(k) for k in ids),
            include_adult="false",
            page=1,
        )
        count = data.get("total_results", 0)
        if count >= min_count:
            out.append({
                "slug": coll["slug"], "label": coll["label"],
                "emoji": coll["emoji"], "count": count,
            })
    out.sort(key=lambda c: c["count"], reverse=True)
    return out


if __name__ == "__main__":
    print("Top 5 highest-rated movies (live):")
    for movie in search_movies(sort_by="rating", limit=5):
        genres = ", ".join(movie["genres"])
        print(f"  {movie['rating']}  {movie['title']} ({movie['release_year']}) [{genres}]")

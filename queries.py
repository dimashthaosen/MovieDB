"""The core feature: turn user filter choices into one SQL query.

Every filter is optional. Unselected filters are simply skipped, so the
same function handles "all action movies after 2010 rated 7+" and
"just show me everything" without any special-casing.
"""

from db import get_connection

# Columns the caller is allowed to sort by -> the actual SQL expression.
# Whitelisting prevents SQL injection through the sort parameter.
SORT_COLUMNS = {
    "rating": "m.rating",
    "popularity": "m.popularity",
    "year": "m.release_year",
    "title": "m.title",
    "runtime": "m.runtime",
}


def search_movies(
    genres: list[int] | None = None,
    genre_match: str = "any",          # "any" -> OR, "all" -> AND
    year_min: int | None = None,
    year_max: int | None = None,
    rating_min: float | None = None,
    language: str | None = None,
    runtime_max: int | None = None,
    sort_by: str = "popularity",
    sort_dir: str = "desc",
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """Return movies matching the given filters as a list of dicts."""
    where: list[str] = []
    params: list = []

    # --- Genre filter (uses the junction table) -----------------------
    if genres:
        placeholders = ", ".join("?" for _ in genres)
        if genre_match == "all":
            # Movie must be linked to every requested genre.
            where.append(
                f"m.id IN ("
                f"  SELECT movie_id FROM movie_genres"
                f"  WHERE genre_id IN ({placeholders})"
                f"  GROUP BY movie_id HAVING COUNT(DISTINCT genre_id) = ?"
                f")"
            )
            params.extend(genres)
            params.append(len(genres))
        else:  # "any"
            where.append(
                f"m.id IN ("
                f"  SELECT movie_id FROM movie_genres"
                f"  WHERE genre_id IN ({placeholders})"
                f")"
            )
            params.extend(genres)

    # --- Simple column filters ---------------------------------------
    if year_min is not None:
        where.append("m.release_year >= ?")
        params.append(year_min)
    if year_max is not None:
        where.append("m.release_year <= ?")
        params.append(year_max)
    if rating_min is not None:
        where.append("m.rating >= ?")
        params.append(rating_min)
    if language:
        where.append("m.original_language = ?")
        params.append(language)
    if runtime_max is not None:
        where.append("m.runtime IS NOT NULL AND m.runtime <= ?")
        params.append(runtime_max)

    # --- Assemble the query ------------------------------------------
    sql = "SELECT m.* FROM movies m"
    if where:
        sql += " WHERE " + " AND ".join(where)

    sort_col = SORT_COLUMNS.get(sort_by, "m.popularity")
    direction = "ASC" if sort_dir.lower() == "asc" else "DESC"
    sql += f" ORDER BY {sort_col} {direction} NULLS LAST"

    sql += " LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    conn = get_connection()
    try:
        rows = conn.execute(sql, params).fetchall()
        movies = [dict(row) for row in rows]
        # Attach each movie's genre names in a single extra query.
        _attach_genres(conn, movies)
        return movies
    finally:
        conn.close()


def _attach_genres(conn, movies: list[dict]) -> None:
    if not movies:
        return
    ids = [m["id"] for m in movies]
    placeholders = ", ".join("?" for _ in ids)
    rows = conn.execute(
        f"SELECT mg.movie_id, g.name FROM movie_genres mg"
        f" JOIN genres g ON g.id = mg.genre_id"
        f" WHERE mg.movie_id IN ({placeholders})",
        ids,
    ).fetchall()
    by_movie: dict[int, list[str]] = {}
    for r in rows:
        by_movie.setdefault(r["movie_id"], []).append(r["name"])
    for m in movies:
        m["genres"] = sorted(by_movie.get(m["id"], []))


def list_genres() -> list[dict]:
    """Return all genres (for populating the UI dropdown)."""
    conn = get_connection()
    try:
        rows = conn.execute("SELECT id, name FROM genres ORDER BY name").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


if __name__ == "__main__":
    # Quick manual smoke test (build step 3): filter by a single criterion.
    print("Top 5 highest-rated movies:")
    for movie in search_movies(sort_by="rating", limit=5):
        genres = ", ".join(movie["genres"])
        print(f"  {movie['rating']:>4}  {movie['title']} ({movie['release_year']}) [{genres}]")

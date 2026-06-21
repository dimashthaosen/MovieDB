"""The data layer — served live from TMDb (no local database).

Every filter choice becomes a TMDb /discover/movie query parameter; details and
recommendations come from /movie/{id}. Function signatures and return shapes are
unchanged from the old SQLite version, so the API, frontend, and AI companion
all work without modification.

Movie dicts have the same shape everywhere:
    id, title, release_year, rating, vote_count, runtime, original_language,
    overview, poster_url, popularity, genres (list of names)
"""

import re

import subgenres
import tmdb

FALLBACK_MOVIES = [
    {"id": -1001, "title": "Lady Bird", "release_year": 2017, "rating": 7.4, "vote_count": 8000, "runtime": 94, "original_language": "en", "overview": "A sharp coming-of-age story about a Sacramento teenager trying to define herself before college.", "poster_url": None, "popularity": 90, "genres": ["Comedy", "Drama"], "collections": ["coming-of-age"]},
    {"id": -1002, "title": "The Perks of Being a Wallflower", "release_year": 2012, "rating": 7.8, "vote_count": 10500, "runtime": 103, "original_language": "en", "overview": "An introverted freshman finds friendship, music, and emotional honesty during a difficult year.", "poster_url": None, "popularity": 85, "genres": ["Drama", "Romance"], "collections": ["coming-of-age"]},
    {"id": -1003, "title": "Stand by Me", "release_year": 1986, "rating": 7.9, "vote_count": 6000, "runtime": 89, "original_language": "en", "overview": "Four boys take a formative journey that becomes a memory of friendship, fear, and growing up.", "poster_url": None, "popularity": 75, "genres": ["Adventure", "Drama"], "collections": ["coming-of-age"]},
    {"id": -1004, "title": "The Edge of Seventeen", "release_year": 2016, "rating": 7.2, "vote_count": 4200, "runtime": 105, "original_language": "en", "overview": "A painfully funny high-school portrait of insecurity, family friction, and finding your footing.", "poster_url": None, "popularity": 72, "genres": ["Comedy", "Drama"], "collections": ["coming-of-age"]},
    {"id": -1005, "title": "Eighth Grade", "release_year": 2018, "rating": 7.2, "vote_count": 3900, "runtime": 94, "original_language": "en", "overview": "A tender, anxious look at adolescence in the social media age.", "poster_url": None, "popularity": 70, "genres": ["Comedy", "Drama"], "collections": ["coming-of-age"]},
    {"id": -1006, "title": "Boyhood", "release_year": 2014, "rating": 7.5, "vote_count": 5200, "runtime": 166, "original_language": "en", "overview": "A life-spanning portrait of childhood, family change, and ordinary growing up.", "poster_url": None, "popularity": 66, "genres": ["Drama"], "collections": ["coming-of-age"]},
    {"id": -1007, "title": "Moonlight", "release_year": 2016, "rating": 7.4, "vote_count": 7200, "runtime": 111, "original_language": "en", "overview": "A lyrical triptych about identity, masculinity, intimacy, and becoming yourself.", "poster_url": None, "popularity": 82, "genres": ["Drama"], "collections": ["coming-of-age"]},
    {"id": -1008, "title": "Dead Poets Society", "release_year": 1989, "rating": 8.3, "vote_count": 12000, "runtime": 128, "original_language": "en", "overview": "An inspirational boarding-school drama about art, pressure, rebellion, and self-expression.", "poster_url": None, "popularity": 88, "genres": ["Drama"], "collections": ["coming-of-age"]},
    {"id": -1009, "title": "Booksmart", "release_year": 2019, "rating": 7.0, "vote_count": 3600, "runtime": 102, "original_language": "en", "overview": "Two overachievers try to squeeze a whole high-school party life into one chaotic night.", "poster_url": None, "popularity": 64, "genres": ["Comedy"], "collections": ["coming-of-age"]},
    {"id": -1010, "title": "The Breakfast Club", "release_year": 1985, "rating": 7.7, "vote_count": 8000, "runtime": 98, "original_language": "en", "overview": "Five students in detention discover the fragile people behind their social labels.", "poster_url": None, "popularity": 78, "genres": ["Comedy", "Drama"], "collections": ["coming-of-age"]},
    {"id": -1011, "title": "Spirited Away", "release_year": 2001, "rating": 8.5, "vote_count": 17000, "runtime": 125, "original_language": "ja", "overview": "A young girl enters a strange spirit world and learns courage, resilience, and compassion.", "poster_url": None, "popularity": 95, "genres": ["Adventure", "Animation", "Family", "Fantasy"], "collections": ["anime", "coming-of-age"]},
    {"id": -1012, "title": "Your Name.", "release_year": 2016, "rating": 8.5, "vote_count": 12000, "runtime": 106, "original_language": "ja", "overview": "Two teenagers mysteriously connected across distance and time search for each other.", "poster_url": None, "popularity": 92, "genres": ["Animation", "Drama", "Romance"], "collections": ["anime", "coming-of-age"]},
    {"id": -1013, "title": "The Dark Knight", "release_year": 2008, "rating": 8.5, "vote_count": 35000, "runtime": 152, "original_language": "en", "overview": "Batman faces an anarchic criminal force that tests the moral limits of heroism.", "poster_url": None, "popularity": 95, "genres": ["Action", "Crime", "Thriller"], "collections": ["superhero", "crime-noir"]},
    {"id": -1014, "title": "Inception", "release_year": 2010, "rating": 8.4, "vote_count": 36000, "runtime": 148, "original_language": "en", "overview": "A dream-invasion specialist takes on a layered heist inside the architecture of the mind.", "poster_url": None, "popularity": 94, "genres": ["Action", "Adventure", "Science Fiction"], "collections": ["heist", "sci-fi"]},
    {"id": -1015, "title": "Parasite", "release_year": 2019, "rating": 8.5, "vote_count": 20000, "runtime": 132, "original_language": "ko", "overview": "A poor family infiltrates a wealthy household in a razor-sharp social thriller.", "poster_url": None, "popularity": 89, "genres": ["Comedy", "Drama", "Thriller"], "collections": ["crime-noir"]},
]

# Our sort keys -> TMDb /discover sort_by fields.
SORT_MAP = {
    "popularity": "popularity",
    "rating": "vote_average",
    "year": "primary_release_date",
    "title": "original_title",
    "best_match": "popularity",
    "runtime": "popularity",  # TMDb can't sort by runtime; fall back gracefully
}

_genre_map: dict[int, str] | None = None

VIBE_GENRES = {
    "action": ["Action", "Adventure", "Thriller"],
    "funny": ["Comedy"],
    "romantic": ["Romance", "Comedy", "Drama"],
    "dark": ["Crime", "Drama", "Thriller"],
    "mind_bending": ["Mystery", "Science Fiction", "Thriller"],
    "comfort": ["Comedy", "Family", "Romance"],
    "scary": ["Horror", "Thriller"],
    "visual": ["Adventure", "Animation", "Fantasy", "Science Fiction"],
}

LANGUAGE_SCOPES = {
    "english": ["en"],
    "indian": ["hi", "ta", "te", "ml", "kn", "bn", "mr"],
    "east_asian": ["ja", "ko", "zh", "cn"],
}

VIBE_LABELS = {
    "action": "high-energy action",
    "funny": "comedy",
    "romantic": "romance",
    "dark": "darker crime/drama",
    "mind_bending": "mind-bending mystery/sci-fi",
    "comfort": "comfort watch",
    "scary": "horror/suspense",
    "visual": "visual spectacle",
}

ANCHOR_SOURCE_WEIGHT = 7.5
DISCOVERY_SOURCE_WEIGHT = 3.0

MOVIE_TYPE_FACETS = {
    "prestige": {"prestige", "critically_loved"},
    "popcorn": {"popcorn", "mainstream"},
    "cult": {"sleeper", "niche", "edge", "genre_bender"},
    "comfort": {"comfort"},
    "edgy": {"edge", "niche"},
    "imaginative": {"imaginative", "genre_bender"},
}

ZEITGEIST_FACETS = {
    "current": {"current_zeitgeist", "mainstream"},
    "modern_classic": {"modern_classic_window", "critically_loved"},
    "retro": {"classic_or_retro"},
    "sleeper": {"sleeper", "niche"},
    "mainstream": {"mainstream"},
}


def _genre_id_to_name() -> dict[int, str]:
    """Cached TMDb genre id -> name map."""
    global _genre_map
    if _genre_map is None:
        data = tmdb.get("/genre/movie/list", language="en-US")
        _genre_map = {g["id"]: g["name"] for g in data["genres"]}
    return _genre_map


def _genre_name_to_id() -> dict[str, int]:
    return {name.lower(): gid for gid, name in _genre_id_to_name().items()}




def _mojibake_score(text: str) -> int:
    markers = (
        "\u00c3", "\u00c2", "\u00e2", "\u00f0\u0178", "\ufffd",
        "\x80", "\x81", "\x82", "\x83", "\x84", "\x85",
    )
    return sum(text.count(marker) for marker in markers)


def _clean_text(value):
    if not isinstance(value, str) or not _mojibake_score(value):
        return value
    best = value
    best_score = _mojibake_score(value)
    for encoding in ("latin1", "cp1252"):
        try:
            repaired = value.encode(encoding).decode("utf-8")
        except UnicodeError:
            continue
        score = _mojibake_score(repaired)
        if score < best_score:
            best, best_score = repaired, score
    if "\ufffd" in best:
        best = re.sub(r"\s*\ufffd+\s*", " - ", best)
        best = re.sub(r"\s+-\s+", " - ", best).strip(" -")
    return best


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
        "title": _clean_text(item.get("title")) or "Untitled",
        "release_year": tmdb.year_of(item.get("release_date")),
        "rating": round(va, 1) if va else None,
        "vote_count": item.get("vote_count"),
        "runtime": item.get("runtime"),  # present only on /movie/{id}
        "original_language": item.get("original_language"),
        "overview": _clean_text(item.get("overview")),
        "poster_url": tmdb.poster_url(item.get("poster_path")),
        "popularity": item.get("popularity"),
        "genres": genres,
    }


def fallback_movies(
    query: str | None = None,
    collection: str | None = None,
    genres: list[int] | None = None,
    year_min: int | None = None,
    year_max: int | None = None,
    rating_min: float | None = None,
    language: str | None = None,
    runtime_max: int | None = None,
    sort_by: str = "best_match",
    sort_dir: str = "desc",
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """Small offline fallback used when TMDb discover/search is temporarily down."""
    genre_names = _genre_id_to_name()
    wanted_genres = {genre_names.get(gid) for gid in genres or []}
    wanted_genres.discard(None)
    q = (query or "").strip().lower()
    rows = []
    for movie in FALLBACK_MOVIES:
        if q and q not in movie["title"].lower():
            continue
        if collection and collection not in movie.get("collections", []):
            continue
        if wanted_genres and not (set(movie.get("genres", [])) & wanted_genres):
            continue
        if year_min is not None and (movie.get("release_year") or 0) < year_min:
            continue
        if year_max is not None and (movie.get("release_year") or 9999) > year_max:
            continue
        if rating_min is not None and (movie.get("rating") or 0) < rating_min:
            continue
        if language and movie.get("original_language") != language:
            continue
        if runtime_max is not None and movie.get("runtime") and movie["runtime"] > runtime_max:
            continue
        rows.append({k: v for k, v in movie.items() if k != "collections"})

    reverse = sort_dir != "asc"
    key_map = {
        "rating": lambda m: m.get("rating") or 0,
        "year": lambda m: m.get("release_year") or 0,
        "title": lambda m: m.get("title") or "",
        "popularity": lambda m: m.get("popularity") or 0,
        "best_match": lambda m: ((m.get("rating") or 0) * 10) + (m.get("popularity") or 0) / 2,
    }
    rows.sort(key=key_map.get(sort_by, key_map["best_match"]), reverse=reverse)
    return rows[offset: offset + limit]


def _money(value: int | None) -> int | None:
    return value if value and value > 0 else None


def _trailer_url(videos: dict | None) -> str | None:
    results = (videos or {}).get("results", [])
    youtube = [v for v in results if v.get("site") == "YouTube" and v.get("key")]
    preferred = next(
        (
            v for v in youtube
            if v.get("official") and v.get("type") in {"Trailer", "Teaser"}
        ),
        None,
    )
    fallback = next((v for v in youtube if v.get("type") in {"Trailer", "Teaser"}), None)
    video = preferred or fallback or (youtube[0] if youtube else None)
    return f"https://www.youtube.com/watch?v={video['key']}" if video else None


def _cast(credits: dict | None, limit: int = 8) -> list[dict]:
    cast = []
    for person in (credits or {}).get("cast", [])[:limit]:
        cast.append({
            "id": person.get("id"),
            "name": _clean_text(person.get("name")),
            "character": _clean_text(person.get("character")),
            "profile_url": tmdb.profile_url(person.get("profile_path")),
        })
    return cast


def _crew(credits: dict | None) -> dict:
    out = {"directors": [], "writers": [], "composers": []}
    for person in (credits or {}).get("crew", []):
        job = person.get("job")
        name = _clean_text(person.get("name"))
        if not name:
            continue
        if job == "Director" and name not in out["directors"]:
            out["directors"].append(name)
        elif job in {"Writer", "Screenplay", "Story"} and name not in out["writers"]:
            out["writers"].append(name)
        elif job == "Original Music Composer" and name not in out["composers"]:
            out["composers"].append(name)
    return {key: names[:4] for key, names in out.items() if names}


def _crew_ids(credits: dict | None) -> dict:
    out = {"directors": [], "writers": [], "composers": []}
    for person in (credits or {}).get("crew", []):
        job = person.get("job")
        pid = person.get("id")
        name = person.get("name")
        if not pid or not name:
            continue
        item = {"id": pid, "name": _clean_text(name)}
        if job == "Director" and item not in out["directors"]:
            out["directors"].append(item)
        elif job in {"Writer", "Screenplay", "Story"} and item not in out["writers"]:
            out["writers"].append(item)
        elif job == "Original Music Composer" and item not in out["composers"]:
            out["composers"].append(item)
    return {key: people[:4] for key, people in out.items() if people}


def _enrich_movie_detail(data: dict) -> dict:
    movie = _to_movie(data)
    movie.update({
        "tagline": _clean_text(data.get("tagline")),
        "status": _clean_text(data.get("status")),
        "release_date": data.get("release_date"),
        "budget": _money(data.get("budget")),
        "revenue": _money(data.get("revenue")),
        "production_countries": [
            _clean_text(c.get("name")) for c in data.get("production_countries", []) if c.get("name")
        ],
        "production_companies": [
            _clean_text(c.get("name")) for c in data.get("production_companies", []) if c.get("name")
        ][:4],
        "cast": _cast(data.get("credits")),
        "crew": _crew(data.get("credits")),
        "trailer_url": _trailer_url(data.get("videos")),
        "homepage": data.get("homepage"),
    })
    return movie


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


def _score_movie(item: dict) -> float:
    rating = item.get("vote_average") or 0
    votes = item.get("vote_count") or 0
    popularity = item.get("popularity") or 0
    year = tmdb.year_of(item.get("release_date")) or 0
    vote_weight = min(votes / 1000, 1.0)
    popularity_weight = min(popularity / 500, 1.0)
    recency_weight = max(min((year - 1980) / 50, 1.0), 0.0) if year else 0
    return (rating * 0.62) + (vote_weight * 1.8) + (popularity_weight * 1.2) + (recency_weight * 0.45)


def _best_match_slice(params: dict, limit: int, offset: int) -> list[dict]:
    """Blend rating, votes, popularity, and recency for a more useful default rank."""
    fetch_limit = min(max(offset + limit, 80), 160)
    params = {**params, "sort_by": "popularity.desc"}
    params.setdefault("vote_count.gte", 50)
    results = _discover_slice(params, fetch_limit, 0)
    ranked = sorted(results, key=_score_movie, reverse=True)
    return ranked[offset: offset + limit]


def search_movies(
    genres: list[int] | None = None,
    genre_match: str = "any",
    year_min: int | None = None,
    year_max: int | None = None,
    rating_min: float | None = None,
    language: str | None = None,
    origin_country: str | None = None,
    person_ids: list[int] | None = None,
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
    if origin_country:
        params["with_origin_country"] = origin_country.upper()
    if person_ids:
        params["with_cast"] = "|".join(str(pid) for pid in person_ids)
    if runtime_max is not None:
        params["with_runtime.lte"] = runtime_max
    if keyword_ids:
        params["with_keywords"] = "|".join(str(k) for k in keyword_ids)

    if sort_by == "best_match":
        return [_to_movie(it) for it in _best_match_slice(params, limit, offset)]
    return [_to_movie(it) for it in _discover_slice(params, limit, offset)]


def _search_slice(query: str, limit: int, offset: int) -> list[dict]:
    """Fetch TMDb title-search pages covering [offset, offset+limit)."""
    first_page = offset // 20 + 1
    last_page = min((offset + limit - 1) // 20 + 1, 500)
    collected: list[dict] = []
    for page in range(first_page, last_page + 1):
        data = tmdb.get("/search/movie", query=query, include_adult="false", page=page)
        collected.extend(data.get("results", []))
        if page >= data.get("total_pages", page):
            break
    base = (first_page - 1) * 20
    return collected[offset - base: offset - base + limit]


def search_movie_titles(query: str, limit: int = 50, offset: int = 0) -> list[dict]:
    """Search movies by title using TMDb's title search endpoint."""
    q = query.strip()
    if not q:
        return []
    return [_to_movie(it) for it in _search_slice(q, limit, offset)]


def suggest_titles(query: str, limit: int = 6) -> list[dict]:
    q = query.strip()
    if len(q) < 2:
        return []
    rows = tmdb.get("/search/movie", query=q, include_adult="false", page=1).get("results", [])
    out = []
    for item in rows[:limit]:
        out.append({
            "id": item.get("id"),
            "title": item.get("title") or "Untitled",
            "release_year": tmdb.year_of(item.get("release_date")),
            "poster_url": tmdb.poster_url(item.get("poster_path")),
        })
    return out


def get_movie(movie_id: int) -> dict | None:
    """Full details for a single movie, or None if it doesn't exist."""
    try:
        data = tmdb.get(f"/movie/{movie_id}")
    except tmdb.TMDbNotFound:
        return None
    return _to_movie(data)


def get_movie_extras(movie_id: int) -> dict | None:
    """Cast, crew, trailer, and production facts for a movie."""
    try:
        data = tmdb.get(f"/movie/{movie_id}", append_to_response="credits,videos")
    except tmdb.TMDbNotFound:
        return None
    enriched = _enrich_movie_detail(data)
    return {
        "tagline": enriched.get("tagline"),
        "status": enriched.get("status"),
        "release_date": enriched.get("release_date"),
        "budget": enriched.get("budget"),
        "revenue": enriched.get("revenue"),
        "production_countries": enriched.get("production_countries", []),
        "production_companies": enriched.get("production_companies", []),
        "cast": enriched.get("cast", []),
        "crew": enriched.get("crew", {}),
        "crew_people": _crew_ids(data.get("credits")),
        "trailer_url": enriched.get("trailer_url"),
        "homepage": enriched.get("homepage"),
    }


def watch_providers(movie_id: int, region: str = "IN") -> dict:
    data = tmdb.get(f"/movie/{movie_id}/watch/providers")
    result = (data.get("results") or {}).get(region.upper(), {})
    def rows(key: str) -> list[dict]:
        return [
            {
                "name": p.get("provider_name"),
                "logo_url": tmdb.poster_url(p.get("logo_path")),
            }
            for p in result.get(key, [])[:8]
            if p.get("provider_name")
        ]
    return {
        "region": region.upper(),
        "link": result.get("link"),
        "flatrate": rows("flatrate"),
        "rent": rows("rent"),
        "buy": rows("buy"),
    }


def person_movies(person_id: int, limit: int = 24) -> dict | None:
    try:
        person = tmdb.get(f"/person/{person_id}")
        credits = tmdb.get(f"/person/{person_id}/movie_credits")
    except tmdb.TMDbNotFound:
        return None
    seen = {}
    for item in credits.get("cast", []) + credits.get("crew", []):
        if item.get("id") and item.get("poster_path"):
            seen[item["id"]] = item
    movies = sorted(seen.values(), key=lambda it: it.get("popularity", 0), reverse=True)
    return {
        "id": person.get("id"),
        "name": person.get("name"),
        "profile_url": tmdb.profile_url(person.get("profile_path")),
        "known_for_department": person.get("known_for_department"),
        "movies": [_to_movie(it) for it in movies[:limit]],
    }


def search_people(query: str, limit: int = 6) -> list[dict]:
    q = query.strip()
    if len(q) < 2:
        return []
    data = tmdb.get("/search/person", query=q, include_adult="false", page=1)
    return [
        {
            "id": p.get("id"),
            "name": p.get("name"),
            "profile_url": tmdb.profile_url(p.get("profile_path")),
            "known_for_department": p.get("known_for_department"),
        }
        for p in data.get("results", [])[:limit]
    ]


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


def recommendation_groups(movie_id: int, limit: int = 8) -> dict | None:
    try:
        ref = tmdb.get(f"/movie/{movie_id}", append_to_response="credits")
    except tmdb.TMDbNotFound:
        return None

    ref_movie = _to_movie(ref)
    ref_genre_ids = [g.get("id") for g in ref.get("genres", []) if g.get("id")]
    ref_year = ref_movie.get("release_year")
    credits = ref.get("credits") or {}
    director_ids = [p["id"] for p in _crew_ids(credits).get("directors", []) if p.get("id")]

    def without_ref(rows: list[dict]) -> list[dict]:
        out = []
        for movie in rows:
            if movie["id"] != movie_id and movie["id"] not in {m["id"] for m in out}:
                out.append(movie)
        return out[:limit]

    groups = {
        "tmdb": {"label": "TMDb recommends", "results": without_ref(similar_movies(movie_id, limit=limit))},
        "director": {"label": "Same director", "results": []},
        "decade": {"label": "Same era and genres", "results": []},
    }

    if director_ids:
        data = tmdb.get(
            "/discover/movie",
            with_crew="|".join(str(pid) for pid in director_ids),
            include_adult="false",
            sort_by="popularity.desc",
            page=1,
        )
        groups["director"]["results"] = without_ref([_to_movie(it) for it in data.get("results", [])])

    if ref_year and ref_genre_ids:
        decade_start = (ref_year // 10) * 10
        data = tmdb.get(
            "/discover/movie",
            with_genres="|".join(str(gid) for gid in ref_genre_ids),
            **{
                "primary_release_date.gte": f"{decade_start}-01-01",
                "primary_release_date.lte": f"{decade_start + 9}-12-31",
            },
            include_adult="false",
            sort_by="vote_average.desc",
            **{"vote_count.gte": 100},
            page=1,
        )
        groups["decade"]["results"] = without_ref([_to_movie(it) for it in data.get("results", [])])

    return {key: group for key, group in groups.items() if group["results"]}


def _profile_year_bounds(era: str | None) -> tuple[int | None, int | None]:
    if era == "new":
        return 2020, None
    if era == "modern":
        return 2000, None
    if era == "classic":
        return None, 1999
    if era == "90s":
        return 1990, 1999
    return None, None


def _profile_runtime_max(runtime: str | None) -> int | None:
    if runtime == "short":
        return 105
    if runtime == "normal":
        return 145
    return None


def _risk_level(movie: dict, rating_flexibility: float) -> str:
    rating = movie.get("rating") or 0
    votes = movie.get("vote_count") or 0
    if rating >= 7.3 and votes >= 650:
        return "Safe pick"
    if rating >= 6.2 or rating_flexibility >= 0.6:
        return "Slight gamble"
    return "Wild card"


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(value, high))


def _movie_facets(movie: dict) -> set[str]:
    genres = set(movie.get("genres") or [])
    rating = movie.get("rating") or 0
    votes = movie.get("vote_count") or 0
    popularity = movie.get("popularity") or 0
    year = movie.get("release_year") or 0
    facets: set[str] = set()

    if genres & {"Action", "Adventure", "Science Fiction", "Fantasy"}:
        facets.add("popcorn")
    if genres & {"Drama", "History", "War"} and rating >= 7.0:
        facets.add("prestige")
    if genres & {"Comedy", "Family", "Romance", "Animation"}:
        facets.add("comfort")
    if genres & {"Crime", "Mystery", "Thriller", "Horror"}:
        facets.add("edge")
    if genres & {"Science Fiction", "Fantasy", "Animation"}:
        facets.add("imaginative")
    if genres & {"Documentary", "History", "War"}:
        facets.add("real_world")
    if len(genres) >= 4:
        facets.add("genre_bender")
    if popularity >= 180 or votes >= 3000:
        facets.add("mainstream")
    if rating >= 7.6 and votes >= 500:
        facets.add("critically_loved")
    if rating >= 6.0 and votes < 900 and popularity < 120:
        facets.add("sleeper")
    if votes < 450 and popularity < 80:
        facets.add("niche")
    if year and year <= 1999:
        facets.add("classic_or_retro")
    if year and year >= 2020 and popularity >= 60:
        facets.add("current_zeitgeist")
    if 2000 <= year <= 2014:
        facets.add("modern_classic_window")
    return facets


def _facet_label(facet: str) -> str:
    return {
        "popcorn": "big-screen popcorn energy",
        "prestige": "prestige-drama weight",
        "comfort": "comfort-watch texture",
        "edge": "edgier genre tension",
        "imaginative": "imaginative world-building",
        "real_world": "real-world subject matter",
        "genre_bender": "genre-bending mix",
        "mainstream": "mainstream zeitgeist appeal",
        "critically_loved": "critical/audience respect",
        "sleeper": "sleeper-pick potential",
        "niche": "niche discovery energy",
        "classic_or_retro": "classic/retro era feel",
        "current_zeitgeist": "current zeitgeist pull",
        "modern_classic_window": "modern-classic window",
    }.get(facet, facet.replace("_", " "))


def _anchor_profile(anchor_movies: list[dict]) -> dict:
    genre_weights: dict[str, float] = {}
    facet_weights: dict[str, float] = {}
    languages: dict[str, int] = {}
    decades: dict[str, int] = {}
    years = []
    ratings = []
    for index, movie in enumerate(anchor_movies):
        weight = max(1.0 - index * 0.12, 0.55)
        for genre in movie.get("genres", []):
            genre_weights[genre] = genre_weights.get(genre, 0) + weight
        for facet in _movie_facets(movie):
            facet_weights[facet] = facet_weights.get(facet, 0) + weight
        lang = movie.get("original_language")
        if lang:
            languages[lang] = languages.get(lang, 0) + 1
        if movie.get("release_year"):
            years.append(movie["release_year"])
            decade = _decade_label(movie["release_year"])
            decades[decade] = decades.get(decade, 0) + 1
        if movie.get("rating"):
            ratings.append(movie["rating"])
    dominant_language = max(languages, key=languages.get) if languages else None
    dominant_decade = max(decades, key=decades.get) if decades else None
    return {
        "genre_weights": genre_weights,
        "facet_weights": facet_weights,
        "languages": languages,
        "dominant_language": dominant_language,
        "dominant_decade": dominant_decade,
        "year_center": sum(years) / len(years) if years else None,
        "avg_rating": sum(ratings) / len(ratings) if ratings else None,
    }


def _vibe_profile(vibes: list[str]) -> dict:
    genre_weights: dict[str, float] = {}
    labels = []
    for vibe in vibes:
        labels.append(VIBE_LABELS.get(vibe, vibe.replace("_", " ")))
        for genre in VIBE_GENRES.get(vibe, []):
            genre_weights[genre] = genre_weights.get(genre, 0) + 1.0
    return {"genre_weights": genre_weights, "labels": labels}


def _weighted_overlap(movie_genres: set[str], weights: dict[str, float]) -> tuple[float, list[str]]:
    if not movie_genres or not weights:
        return 0.0, []
    total = sum(weights.values()) or 1.0
    matched = {genre: weights[genre] for genre in movie_genres if genre in weights}
    ratio = sum(matched.values()) / total
    names = [genre for genre, _ in sorted(matched.items(), key=lambda item: item[1], reverse=True)]
    return ratio, names


def _facet_score(movie: dict, anchor_data: dict) -> tuple[float, str | None]:
    facets = _movie_facets(movie)
    ratio, matches = _weighted_overlap(facets, anchor_data.get("facet_weights", {}))
    if not matches:
        return 0.0, None
    score = ratio * 10
    labels = ", ".join(_facet_label(f) for f in matches[:2])
    return score, "matches the movie type your anchors suggest: " + labels


def _zeitgeist_score(movie: dict, profile: dict, anchor_data: dict) -> tuple[float, str | None]:
    facets = _movie_facets(movie)
    rating_flex = float(profile.get("rating_flexibility", 0.35))
    score = 0.0
    reason = None
    if "current_zeitgeist" in facets and profile.get("era") in ("", None, "new", "modern"):
        score += 4.0
        reason = "has current zeitgeist pull"
    if "mainstream" in facets and rating_flex <= 0.45:
        score += 3.5
        reason = "has mainstream zeitgeist appeal"
    if ("sleeper" in facets or "niche" in facets) and rating_flex >= 0.65:
        score += 4.5
        reason = "has sleeper-pick discovery energy"
    if "classic_or_retro" in facets and (profile.get("era") in ("classic", "90s") or anchor_data.get("dominant_decade") in {"1980s", "1990s"}):
        score += 4.0
        reason = "carries classic/retro appeal"
    if "modern_classic_window" in facets and anchor_data.get("dominant_decade") in {"2000s", "2010s"}:
        score += 3.0
        reason = "sits in the modern-classic window"
    return score, reason


def _explicit_facet_preference_score(movie: dict, profile: dict) -> tuple[float, str | None]:
    facets = _movie_facets(movie)
    movie_type = profile.get("movie_type")
    zeitgeist = profile.get("zeitgeist")
    score = 0.0
    reason = None

    type_facets = MOVIE_TYPE_FACETS.get(movie_type or "", set())
    type_matches = facets & type_facets
    if type_matches:
        score += 4.5
        labels = ", ".join(_facet_label(f) for f in sorted(type_matches)[:2])
        reason = "fits your movie-type preference: " + labels
    elif movie_type:
        score -= 4.0

    zeitgeist_facets = ZEITGEIST_FACETS.get(zeitgeist or "", set())
    zeitgeist_matches = facets & zeitgeist_facets
    if zeitgeist_matches:
        score += 4.0
        labels = ", ".join(_facet_label(f) for f in sorted(zeitgeist_matches)[:2])
        reason = (reason + "; " if reason else "") + "fits your zeitgeist preference: " + labels
    elif zeitgeist:
        score -= 3.0

    return score, reason


def _confidence_score(movie: dict) -> float:
    rating = movie.get("rating") or 0
    votes = movie.get("vote_count") or 0
    popularity = movie.get("popularity") or 0
    rating_part = _clamp((rating - 5.4) / 3.3, 0, 1) * 8
    vote_part = _clamp(votes / 1800, 0, 1) * 5
    popularity_part = _clamp(popularity / 400, 0, 1) * 3
    return rating_part + vote_part + popularity_part


def _novelty_score(movie: dict, profile: dict, anchor_data: dict) -> tuple[float, str | None]:
    rating_flex = float(profile.get("rating_flexibility", 0.35))
    rating = movie.get("rating") or 0
    votes = movie.get("vote_count") or 0
    popularity = movie.get("popularity") or 0
    score = 0.0
    reason = None
    if rating_flex >= 0.65 and rating >= 5.8 and votes < 900:
        score += 5.0
        reason = "fits your adventurous rating range"
    if rating_flex >= 0.75 and popularity < 80:
        score += 2.5
        reason = "adds a less obvious pick to the mix"
    if rating_flex <= 0.25 and (rating < 6.8 or votes < 250):
        score -= 12.0
    avg_anchor_rating = anchor_data.get("avg_rating")
    if avg_anchor_rating and rating and rating < avg_anchor_rating - 1.8 and rating_flex < 0.55:
        score -= 8.0
    return score, reason


def _era_score(movie: dict, profile: dict, anchor_data: dict) -> tuple[float, str | None]:
    year = movie.get("release_year")
    if not year:
        return 0.0, None
    year_min, year_max = _profile_year_bounds(profile.get("era"))
    if profile.get("era") and ((year_min is None or year >= year_min) and (year_max is None or year <= year_max)):
        return 5.5, "fits your era preference"
    if not profile.get("era") and anchor_data.get("dominant_decade") == _decade_label(year):
        return 4.0, "matches the era your anchors point toward"
    center = anchor_data.get("year_center")
    if center:
        distance = abs(year - center)
        if distance <= 7:
            return 3.5, "stays close to your anchor era"
        if distance <= 18:
            return 1.5, None
    return 0.0, None


def _language_score(movie: dict, profile: dict, anchor_data: dict) -> tuple[float, str | None]:
    lang = movie.get("original_language")
    selected = LANGUAGE_SCOPES.get(profile.get("language_scope"), [])
    if selected and lang in selected:
        return 5.5, "fits your language preference"
    if not selected and lang and lang == anchor_data.get("dominant_language"):
        return 5.0, "matches the language pattern in your anchors"
    anchor_langs = anchor_data.get("languages") or {}
    if lang and lang in anchor_langs:
        return min(3.5 + anchor_langs[lang] * 1.0, 6.0), "keeps the language close to your anchors"
    return 0.0, None


def _runtime_score(movie: dict, profile: dict) -> tuple[float, str | None]:
    runtime_pref = profile.get("runtime")
    runtime_max = _profile_runtime_max(runtime_pref)
    runtime = movie.get("runtime")
    if runtime_pref == "epic":
        return 1.5, "keeps room for a bigger movie night"
    if runtime_pref and runtime_max and runtime and runtime <= runtime_max:
        return 3.5, "fits your runtime mood"
    return 0.0, None


def _source_score(movie: dict) -> tuple[float, str | None]:
    sources = set(movie.get("_sources") or [])
    source_weight = min(movie.get("_source_weight", 0.0), 18.0) * 0.12
    anchor_sources = [source for source in sources if source.startswith("anchor:")]
    if len(anchor_sources) >= 2:
        return 10.0 + source_weight, "connects multiple movies you liked"
    if anchor_sources:
        return 7.0 + source_weight, "comes from a movie you liked"
    if "vibe_discovery" in sources and "anchor_discovery" in sources:
        return 6.0 + source_weight, "balances your anchors with the chosen vibe"
    if "vibe_discovery" in sources:
        return 4.0 + source_weight, "was discovered from your selected vibe"
    return 1.5 + source_weight, None


def _synergy_score(movie_genres: set[str], anchor_matches: list[str], vibe_matches: list[str], profile: dict) -> tuple[float, str | None]:
    vibes = set(profile.get("vibes", []))
    score = 0.0
    reason = None
    if anchor_matches and vibe_matches:
        score += 5.0
        reason = "blends your anchor taste with tonight's vibe"
    if {"dark", "action"} <= vibes and {"Crime", "Thriller"} <= movie_genres:
        score += 3.5
        reason = "hits the dark action-thriller lane"
    if {"comfort", "romantic"} <= vibes and movie_genres & {"Romance", "Comedy"}:
        score += 3.5
        reason = "leans into a lighter comfort-romance mood"
    if {"mind_bending", "scary"} <= vibes and movie_genres & {"Mystery", "Horror", "Science Fiction"}:
        score += 3.5
        reason = "leans into eerie, puzzle-box tension"
    return score, reason


def _append_reason(reasons: list[tuple[float, str]], weight: float, text: str | None) -> None:
    if text and all(existing != text for _, existing in reasons):
        reasons.append((weight, text))


def _personal_score(movie: dict, profile: dict, anchor_data: dict, vibe_data: dict) -> tuple[float, list[str]]:
    score = 12.0
    reason_weights: list[tuple[float, str]] = []
    movie_genres = set(movie.get("genres") or [])

    anchor_ratio, anchor_matches = _weighted_overlap(movie_genres, anchor_data.get("genre_weights", {}))
    vibe_ratio, vibe_matches = _weighted_overlap(movie_genres, vibe_data.get("genre_weights", {}))
    if anchor_matches:
        anchor_score = anchor_ratio * 22
        score += anchor_score
        _append_reason(reason_weights, anchor_score, "shares your anchor taste: " + ", ".join(anchor_matches[:3]))
    elif anchor_data.get("genre_weights"):
        score -= 5.0
    if vibe_matches:
        vibe_score = vibe_ratio * 18
        score += vibe_score
        _append_reason(reason_weights, vibe_score, "matches your selected vibe: " + ", ".join(vibe_matches[:3]))
    elif vibe_data.get("genre_weights"):
        score -= 6.0

    source_bonus, source_reason = _source_score(movie)
    score += source_bonus
    _append_reason(reason_weights, source_bonus, source_reason)

    confidence = _confidence_score(movie)
    score += confidence
    rating = movie.get("rating") or 0
    if rating >= 7.2:
        _append_reason(reason_weights, min(confidence, 10), f"strong audience score ({rating:.1f})")

    novelty, novelty_reason = _novelty_score(movie, profile, anchor_data)
    score += novelty
    _append_reason(reason_weights, abs(novelty), novelty_reason)

    era_bonus, era_reason = _era_score(movie, profile, anchor_data)
    score += era_bonus
    _append_reason(reason_weights, era_bonus, era_reason)

    language_bonus, language_reason = _language_score(movie, profile, anchor_data)
    score += language_bonus
    _append_reason(reason_weights, language_bonus, language_reason)

    runtime_bonus, runtime_reason = _runtime_score(movie, profile)
    score += runtime_bonus
    _append_reason(reason_weights, runtime_bonus, runtime_reason)

    synergy_bonus, synergy_reason = _synergy_score(movie_genres, anchor_matches, vibe_matches, profile)
    score += synergy_bonus
    _append_reason(reason_weights, synergy_bonus, synergy_reason)

    facet_bonus, facet_reason = _facet_score(movie, anchor_data)
    score += facet_bonus
    _append_reason(reason_weights, facet_bonus, facet_reason)

    zeitgeist_bonus, zeitgeist_reason = _zeitgeist_score(movie, profile, anchor_data)
    score += zeitgeist_bonus
    _append_reason(reason_weights, zeitgeist_bonus, zeitgeist_reason)

    explicit_bonus, explicit_reason = _explicit_facet_preference_score(movie, profile)
    score += explicit_bonus
    _append_reason(reason_weights, abs(explicit_bonus), explicit_reason)

    if not reason_weights:
        reason_weights.append((1.0, "balanced by rating, popularity, and your broad preferences"))
    reasons = [text for _, text in sorted(reason_weights, key=lambda item: item[0], reverse=True)[:3]]
    return _clamp(score, 1, 96), reasons


def _fits_profile_constraints(movie: dict, profile: dict) -> bool:
    year_min, year_max = _profile_year_bounds(profile.get("era"))
    year = movie.get("release_year")
    if year_min is not None and year and year < year_min:
        return False
    if year_max is not None and year and year > year_max:
        return False
    languages = LANGUAGE_SCOPES.get(profile.get("language_scope"), [])
    if languages and movie.get("original_language") not in languages:
        return False
    runtime_max = _profile_runtime_max(profile.get("runtime"))
    runtime = movie.get("runtime")
    if runtime_max and runtime and runtime > runtime_max:
        return False
    return True


def _add_candidate(candidates: dict[int, dict], movie: dict, source: str, source_weight: float = 1.0) -> None:
    if not movie.get("id"):
        return
    current = candidates.get(movie["id"])
    if current is None:
        current = dict(movie)
        current["_sources"] = []
        current["_source_weight"] = 0.0
        candidates[movie["id"]] = current
    if source not in current["_sources"]:
        current["_sources"].append(source)
    current["_source_weight"] = current.get("_source_weight", 0.0) + source_weight


def _discover_candidates(
    candidates: dict[int, dict],
    source: str,
    source_weight: float,
    *,
    genres: list[int] | None = None,
    languages: list[str] | None = None,
    year_min: int | None = None,
    year_max: int | None = None,
    rating_min: float | None = None,
    runtime_max: int | None = None,
    limit: int = 24,
) -> None:
    kwargs = {
        "genres": genres or None,
        "genre_match": "any",
        "year_min": year_min,
        "year_max": year_max,
        "rating_min": rating_min,
        "runtime_max": runtime_max,
        "sort_by": "popularity",
        "limit": limit,
    }
    if languages:
        for lang in languages[:5]:
            try:
                rows = search_movies(**kwargs, language=lang)
            except tmdb.TMDbError:
                continue
            for movie in rows:
                _add_candidate(candidates, movie, source, source_weight)
    else:
        try:
            rows = search_movies(**kwargs)
        except tmdb.TMDbError:
            return
        for movie in rows:
            _add_candidate(candidates, movie, source, source_weight)


def _decade_label(year: int | None) -> str:
    if not year:
        return "unknown"
    return f"{(year // 10) * 10}s"


def _diversify_ranked_movies(scored: list[dict], limit: int, profile: dict) -> list[dict]:
    if limit <= 0:
        return []
    pool = sorted(scored, key=lambda m: (m.get("match_score") or 0, m.get("rating") or 0), reverse=True)
    selected: list[dict] = []
    genre_counts: dict[str, int] = {}
    language_counts: dict[str, int] = {}
    decade_counts: dict[str, int] = {}
    risk_counts: dict[str, int] = {}
    rating_flex = float(profile.get("rating_flexibility", 0.35))

    def remember(picked: dict) -> None:
        for genre in picked.get("genres") or []:
            genre_counts[genre] = genre_counts.get(genre, 0) + 1
        lang = picked.get("original_language") or "unknown"
        language_counts[lang] = language_counts.get(lang, 0) + 1
        decade = _decade_label(picked.get("release_year"))
        decade_counts[decade] = decade_counts.get(decade, 0) + 1
        risk = picked.get("risk_level") or ""
        if risk:
            risk_counts[risk] = risk_counts.get(risk, 0) + 1

    protected_count = min(3, limit, len(pool))
    for _ in range(protected_count):
        picked = pool.pop(0)
        selected.append(picked)
        remember(picked)

    while pool and len(selected) < limit:
        best_index = 0
        best_value = -999.0
        best_remaining_score = float(pool[0].get("match_score") or 0)
        for index, movie in enumerate(pool):
            if float(movie.get("match_score") or 0) < best_remaining_score - 6:
                continue
            value = float(movie.get("match_score") or 0)
            genres = movie.get("genres") or []
            repeated_genres = sum(max(genre_counts.get(g, 0) - 1, 0) for g in genres)
            value -= repeated_genres * 1.8
            if any(genre_counts.get(g, 0) == 0 for g in genres):
                value += 2.0

            lang = movie.get("original_language") or "unknown"
            if language_counts.get(lang, 0) == 0:
                value += 1.5
            elif not LANGUAGE_SCOPES.get(profile.get("language_scope")):
                value -= language_counts[lang] * 1.2

            decade = _decade_label(movie.get("release_year"))
            if decade_counts.get(decade, 0) == 0:
                value += 1.0
            else:
                value -= decade_counts[decade] * 0.7

            risk = movie.get("risk_level") or ""
            if rating_flex >= 0.65 and risk and risk_counts.get(risk, 0) == 0:
                value += 1.6
            if rating_flex <= 0.25 and risk == "Wild card":
                value -= 8.0

            if value > best_value:
                best_value = value
                best_index = index

        picked = pool.pop(best_index)
        selected.append(picked)
        remember(picked)

    return selected


def personalized_recommendations(profile: dict, limit: int = 24) -> dict:
    """Score recommendations from a lightweight taste profile."""
    liked_ids = [int(mid) for mid in profile.get("liked_movie_ids", [])[:5] if mid]
    vibes = profile.get("vibes", [])[:5]
    genre_ids = _genre_name_to_id()

    anchor_movies = []
    for mid in liked_ids:
        try:
            movie = get_movie(mid)
        except tmdb.TMDbError:
            movie = None
        if movie:
            anchor_movies.append(movie)
    anchor_data = _anchor_profile(anchor_movies)
    vibe_data = _vibe_profile(vibes)

    target_genres = set(anchor_data["genre_weights"])
    target_genres.update(vibe_data["genre_weights"])
    target_genre_ids = [genre_ids[g.lower()] for g in target_genres if g.lower() in genre_ids]
    anchor_genre_ids = [genre_ids[g.lower()] for g in anchor_data["genre_weights"] if g.lower() in genre_ids]
    vibe_genre_ids = [genre_ids[g.lower()] for g in vibe_data["genre_weights"] if g.lower() in genre_ids]

    year_min, year_max = _profile_year_bounds(profile.get("era"))
    runtime_max = _profile_runtime_max(profile.get("runtime"))
    rating_flex = float(profile.get("rating_flexibility", 0.35))
    rating_min = round(max(7.2 - (rating_flex * 1.9), 4.7), 1)
    language_scope = profile.get("language_scope")
    languages = LANGUAGE_SCOPES.get(language_scope, [])

    candidates: dict[int, dict] = {}
    for movie_id in liked_ids:
        try:
            similar_rows = similar_movies(movie_id, limit=14)
        except tmdb.TMDbError:
            similar_rows = []
        for movie in similar_rows:
            _add_candidate(candidates, movie, f"anchor:{movie_id}", ANCHOR_SOURCE_WEIGHT)

    if anchor_genre_ids:
        _discover_candidates(
            candidates, "anchor_discovery", DISCOVERY_SOURCE_WEIGHT,
            genres=anchor_genre_ids, languages=languages, year_min=year_min,
            year_max=year_max, rating_min=rating_min, runtime_max=runtime_max, limit=24,
        )
    _discover_candidates(
        candidates, "vibe_discovery", DISCOVERY_SOURCE_WEIGHT + 1.5,
        genres=vibe_genre_ids or target_genre_ids, languages=languages, year_min=year_min,
        year_max=year_max, rating_min=max(rating_min - 0.3, 4.7), runtime_max=runtime_max, limit=26,
    )
    if target_genre_ids:
        _discover_candidates(
            candidates, "blend_discovery", DISCOVERY_SOURCE_WEIGHT + 2.0,
            genres=target_genre_ids, languages=languages, year_min=year_min,
            year_max=year_max, rating_min=rating_min, runtime_max=runtime_max, limit=34,
        )
    if profile.get("era") and target_genre_ids:
        _discover_candidates(
            candidates, "era_discovery", DISCOVERY_SOURCE_WEIGHT,
            genres=target_genre_ids, languages=languages, year_min=year_min,
            year_max=year_max, rating_min=max(rating_min - 0.4, 4.7), runtime_max=runtime_max, limit=18,
        )
    if rating_flex >= 0.65 and target_genre_ids:
        _discover_candidates(
            candidates, "explore_discovery", DISCOVERY_SOURCE_WEIGHT,
            genres=target_genre_ids, languages=languages, year_min=year_min,
            year_max=year_max, rating_min=max(rating_min - 1.0, 4.6), runtime_max=runtime_max, limit=20,
        )

    for mid in liked_ids:
        candidates.pop(mid, None)

    scored = []
    for movie in candidates.values():
        if not _fits_profile_constraints(movie, profile):
            continue
        score, reasons = _personal_score(movie, profile, anchor_data, vibe_data)
        movie = dict(movie)
        movie["match_score"] = round(score)
        movie["match_reasons"] = reasons
        movie["risk_level"] = _risk_level(movie, rating_flex)
        movie.pop("_sources", None)
        movie.pop("_source_weight", None)
        scored.append(movie)

    scored.sort(key=lambda m: (m.get("match_score") or 0, m.get("rating") or 0, m.get("popularity") or 0), reverse=True)
    ranked = _diversify_ranked_movies(scored, limit, profile)
    return {
        "profile_summary": {
            "anchors": [m["title"] for m in anchor_movies],
            "vibes": vibes,
            "rating_flexibility": rating_flex,
            "language_scope": language_scope or "any",
            "era": profile.get("era") or "any",
            "runtime": profile.get("runtime") or "any",
            "movie_type": profile.get("movie_type") or "any",
            "zeitgeist": profile.get("zeitgeist") or "any",
        },
        "results": ranked,
    }


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

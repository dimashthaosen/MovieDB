"""AI movie companion, powered by OpenRouter (OpenAI-compatible API).

The model can't see the database directly. Instead we expose two tools —
search_movies and similar_movies — and let the model call them to ground every
recommendation in real rows from movies.db. The model interprets natural-language
requests ("a short feel-good sci-fi for tonight"), calls the tools, and replies
conversationally; we also surface the actual movies it found as cards.

Configure via .env:
    OPENROUTER_API_KEY=sk-or-...
    OPENROUTER_MODEL=google/gemini-3.1-flash-lite:online   (optional override)
"""

import json
import os
import re

from dotenv import load_dotenv
from openai import OpenAI

import queries
import subgenres

load_dotenv()

# Slugs the companion may pass to the search tool's `collection` argument.
_COLLECTION_SLUGS = [c["slug"] for c in subgenres.COLLECTIONS]

API_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL = os.getenv("OPENROUTER_MODEL", "google/gemini-3.1-flash-lite:online")
BASE_URL = "https://openrouter.ai/api/v1"
MAX_TOOL_ROUNDS = 5  # safety cap on the tool-calling loop

LANGUAGE_ALIASES = {
    "tamil": "ta",
    "hindi": "hi",
    "telugu": "te",
    "malayalam": "ml",
    "kannada": "kn",
    "marathi": "mr",
    "bengali": "bn",
    "punjabi": "pa",
    "english": "en",
    "korean": "ko",
    "japanese": "ja",
    "cantonese": "cn",
    "mandarin": "zh",
    "chinese": "zh",
    "spanish": "es",
    "french": "fr",
    "german": "de",
}

COUNTRY_ALIASES = {
    "hong kong": "HK",
    "hk": "HK",
    "india": "IN",
    "indian": "IN",
    "korea": "KR",
    "south korea": "KR",
    "korean": "KR",
    "japan": "JP",
    "japanese": "JP",
    "china": "CN",
    "chinese": "CN",
    "france": "FR",
    "french": "FR",
    "germany": "DE",
    "german": "DE",
    "uk": "GB",
    "british": "GB",
    "united kingdom": "GB",
    "usa": "US",
    "us": "US",
    "american": "US",
}

PERSON_ALIASES = {
    "shahrukh": "Shah Rukh Khan",
    "shah rukh": "Shah Rukh Khan",
    "srk": "Shah Rukh Khan",
    "aamir khan": "Aamir Khan",
    "salman khan": "Salman Khan",
    "rajinikanth": "Rajinikanth",
    "vijay": "Vijay",
    "ajith": "Ajith Kumar",
    "kamal haasan": "Kamal Haasan",
    "tom cruise": "Tom Cruise",
    "leonardo dicaprio": "Leonardo DiCaprio",
    "jackie chan": "Jackie Chan",
    "tony leung": "Tony Leung Chiu-wai",
}

GENRE_ALIASES = {
    "action": "Action",
    "adventure": "Adventure",
    "animation": "Animation",
    "comedy": "Comedy",
    "crime": "Crime",
    "documentary": "Documentary",
    "drama": "Drama",
    "family": "Family",
    "fantasy": "Fantasy",
    "horror": "Horror",
    "musical": "Music",
    "music": "Music",
    "mystery": "Mystery",
    "romance": "Romance",
    "romantic": "Romance",
    "sci fi": "Science Fiction",
    "sci-fi": "Science Fiction",
    "science fiction": "Science Fiction",
    "thriller": "Thriller",
    "war": "War",
    "western": "Western",
}

SYSTEM_PROMPT = (
    "You are MovieDB's friendly movie companion. You help the user find films to "
    "watch from a local database. You CANNOT recommend any movie unless it is "
    "returned by one of your tools — never invent titles or rely on outside "
    "knowledge for recommendations. Use search_movies for descriptive requests "
    "(genre, language, country, era, actor, rating, mood) and similar_movies "
    "when the user references a specific film. Understand natural phrasing: "
    "Tamil movies means language=ta, Hindi means language=hi, Hong Kong means "
    "origin_country=HK, and late 90s means 1997-1999. For actor requests, pass "
    "the person's name in `people`, e.g. Shahrukh/SRK means Shah Rukh Khan. "
    "For niche sub-genres like cyberpunk, film noir, anime, "
    "heist, slasher or zombie movies, pass the matching `collection` argument to "
    "search_movies rather than guessing broad genres. Call the tools, then "
    "recommend a few options conversationally. Format replies as a short intro "
    "followed by Markdown bullets. Each bullet must start with **Title** (YYYY) "
    "when the year is known, or **Title** if it is not. Use only the year from "
    "tool results; do not write full dates like YYYY-MM-DD, approximate dates, "
    "or release-date labels. Keep each reason to one sentence. Do not use tables."
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_movies",
            "description": "Search the movie database with optional filters. Every filter is optional; omit what you don't need.",
            "parameters": {
                "type": "object",
                "properties": {
                    "genres": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Genre names, e.g. ['Science Fiction', 'Comedy'].",
                    },
                    "genre_match": {
                        "type": "string",
                        "enum": ["any", "all"],
                        "description": "'all' = must match every listed genre; 'any' = at least one. Default 'any'.",
                    },
                    "year_min": {"type": "integer", "description": "Earliest release year."},
                    "year_max": {"type": "integer", "description": "Latest release year."},
                    "rating_min": {"type": "number", "description": "Minimum rating, 0-10."},
                    "language": {"type": "string", "description": "ISO 639-1 code, e.g. 'en', 'ko', 'ja'."},
                    "origin_country": {"type": "string", "description": "ISO 3166-1 country code for movie origin/production, e.g. HK, IN, KR, JP."},
                    "people": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Actor names to include, e.g. ['Shah Rukh Khan'], ['Tony Leung Chiu-wai'].",
                    },
                    "collection": {
                        "type": "string",
                        "enum": _COLLECTION_SLUGS,
                        "description": "A specific sub-genre to narrow to, e.g. 'cyberpunk', 'crime-noir', 'anime', 'heist'. Use this when the user names a niche category that isn't a broad genre.",
                    },
                    "sort_by": {
                        "type": "string",
                        "enum": ["best_match", "popularity", "rating", "year", "title"],
                        "description": "Sort order. Default 'best_match' for subjective recommendation requests.",
                    },
                    "limit": {"type": "integer", "description": "Max results, 1-15. Default 8."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "similar_movies",
            "description": "Find movies similar to a given film by shared genres.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Title (or part of it) of the reference movie."},
                    "limit": {"type": "integer", "description": "Max results, 1-15. Default 8."},
                },
                "required": ["title"],
            },
        },
    },
]


def _genre_name_to_id() -> dict[str, int]:
    return {g["name"].lower(): g["id"] for g in queries.list_genres()}


def _latest_user_text(history: list[dict]) -> str:
    for msg in reversed(history):
        if msg.get("role") == "user":
            return msg.get("content", "")
    return ""


def _extract_years(text: str) -> tuple[int | None, int | None]:
    lower = text.lower()
    decade = re.search(r"\b(early|mid|late)?\s*'?(\d{2})s\b", lower)
    if decade:
        era, yy = decade.groups()
        base = 1900 + int(yy) if int(yy) > 30 else 2000 + int(yy)
        if era == "early":
            return base, base + 3
        if era == "mid":
            return base + 4, base + 6
        if era == "late":
            return base + 7, base + 9
        return base, base + 9

    if "classic" in lower or "old" in lower:
        return None, 1980
    if "recent" in lower or "new" in lower:
        return 2020, None

    years = [int(y) for y in re.findall(r"\b(19\d{2}|20\d{2})\b", lower)]
    if len(years) >= 2:
        return min(years), max(years)
    if len(years) == 1:
        year = years[0]
        if re.search(r"\b(after|since|from)\s+" + str(year), lower):
            return year, None
        if re.search(r"\b(before|until|pre)\s+" + str(year), lower):
            return None, year
        return year, year
    return None, None


def _extract_named_people(text: str) -> list[str]:
    lower = text.lower()
    people = [name for alias, name in PERSON_ALIASES.items() if re.search(rf"\b{re.escape(alias)}\b", lower)]
    non_people = set(LANGUAGE_ALIASES) | set(COUNTRY_ALIASES) | set(GENRE_ALIASES) | {"movie", "movies", "film", "films"}

    patterns = [
        r"\b(?:with|starring|featuring|from|by)\s+([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){0,3})",
        r"\b([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){1,3})\s+movies\b",
    ]
    for pattern in patterns:
        for match in re.findall(pattern, text):
            candidate = match.strip()
            candidate_lower = candidate.lower()
            if candidate_lower not in non_people and candidate not in people:
                people.append(candidate)
    return people[:3]


def _extract_intent(text: str) -> dict:
    lower = re.sub(r"\s+", " ", text.lower())
    intent: dict = {}

    genres = []
    for alias, genre in GENRE_ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", lower) and genre not in genres:
            genres.append(genre)
    if genres:
        intent["genres"] = genres
        intent["genre_match"] = "all" if len(genres) > 1 else "any"

    for alias, code in LANGUAGE_ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", lower):
            intent.setdefault("language", code)
            break

    for alias, code in sorted(COUNTRY_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        if re.search(rf"\b{re.escape(alias)}\b", lower):
            intent["origin_country"] = code
            break

    year_min, year_max = _extract_years(text)
    if year_min is not None:
        intent["year_min"] = year_min
    if year_max is not None:
        intent["year_max"] = year_max

    people = _extract_named_people(text)
    if people:
        intent["people"] = people

    if any(word in lower for word in ("best", "good", "recommend", "top", "worth watching")):
        intent["sort_by"] = "best_match"

    return intent


def _merge_tool_intent(args: dict, intent: dict) -> dict:
    merged = dict(args)
    for key, value in intent.items():
        if key == "genres" and value:
            existing = merged.get("genres") or []
            merged["genres"] = list(dict.fromkeys([*existing, *value]))
        elif key == "people" and value:
            existing = merged.get("people") or []
            merged["people"] = list(dict.fromkeys([*existing, *value]))
        elif merged.get(key) in (None, "", []):
            merged[key] = value
    return merged


def _resolve_people(names: list[str]) -> list[int]:
    ids = []
    for name in names:
        matches = queries.search_people(name, limit=1)
        if matches and matches[0].get("id"):
            ids.append(matches[0]["id"])
    return list(dict.fromkeys(ids))


def _compact(movie: dict) -> dict:
    """Trim a movie row to what the model needs to reason about it."""
    return {
        "id": movie["id"],
        "title": movie["title"],
        "year": movie.get("release_year"),
        "rating": movie.get("rating"),
        "genres": movie.get("genres", []),
        "language": movie.get("original_language"),
    }


def _run_tool(name: str, args: dict, intent: dict | None = None) -> tuple[list[dict], str]:
    """Execute a tool. Returns (full movie dicts, JSON string for the model)."""
    if name == "search_movies":
        args = _merge_tool_intent(args, intent or {})
        genre_map = _genre_name_to_id()
        genre_ids = [genre_map[g.lower()] for g in args.get("genres", []) if g.lower() in genre_map]
        kw_ids = queries.keyword_ids_for_collection(args["collection"]) if args.get("collection") else None
        person_ids = _resolve_people(args.get("people", [])) if args.get("people") else None
        movies = queries.search_movies(
            genres=genre_ids or None,
            genre_match=args.get("genre_match", "any"),
            year_min=args.get("year_min"),
            year_max=args.get("year_max"),
            rating_min=args.get("rating_min"),
            language=args.get("language"),
            origin_country=args.get("origin_country"),
            person_ids=person_ids,
            keyword_ids=kw_ids,
            sort_by=args.get("sort_by", "best_match"),
            limit=min(args.get("limit", 8), 15),
        )
    elif name == "similar_movies":
        ref = queries.find_by_title(args.get("title", ""))
        if ref is None:
            return [], json.dumps({"error": f"No movie matching '{args.get('title')}' in the database."})
        movies = queries.similar_movies(ref["id"], limit=min(args.get("limit", 8), 15))
    else:
        return [], json.dumps({"error": f"Unknown tool {name}"})

    payload = {"count": len(movies), "results": [_compact(m) for m in movies]}
    return movies, json.dumps(payload)


def _require_key() -> None:
    if not API_KEY or API_KEY == "your_key_here":
        raise RuntimeError(
            "No OpenRouter API key. Add OPENROUTER_API_KEY to your .env "
            "(get one at https://openrouter.ai/keys)."
        )


def _normalise_reply(text: str) -> str:
    """Clean common model formatting glitches before the UI renders the reply."""
    text = re.sub(r"\b((?:19|20)\d{2})-\d{2}-\d{2}\b", r"\1", text or "")
    text = re.sub(r"\bRelease date:\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bReleased:\s*", "", text, flags=re.IGNORECASE)
    return text.strip()


def _context_message(context: dict | None) -> dict | None:
    if not context:
        return None
    safe = {
        "search": context.get("search"),
        "genre": context.get("genre"),
        "collection": context.get("collection"),
        "year_min": context.get("year_min"),
        "year_max": context.get("year_max"),
        "rating_min": context.get("rating_min"),
        "sort_by": context.get("sort_by"),
    }
    safe = {k: v for k, v in safe.items() if v not in (None, "")}
    if not safe:
        return None
    return {
        "role": "system",
        "content": "Current browsing context from the UI. Use it only when helpful: " + json.dumps(safe),
    }


def chat(history: list[dict], context: dict | None = None) -> dict:
    """Run one companion turn.

    `history` is a list of {role, content} dicts (user/assistant turns).
    Returns {reply: str, movies: [full movie dicts]}.
    """
    _require_key()
    client = OpenAI(base_url=BASE_URL, api_key=API_KEY)

    context_msg = _context_message(context)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if context_msg:
        messages.append(context_msg)
    messages.extend(history)
    intent = _extract_intent(_latest_user_text(history))
    surfaced: dict[int, dict] = {}  # movie id -> full dict, deduped, insertion-ordered

    for _ in range(MAX_TOOL_ROUNDS):
        resp = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            max_tokens=1024,
            extra_headers={"X-Title": "MovieDB"},
        )
        msg = resp.choices[0].message

        # Re-append the assistant turn (with any tool calls) before sending results.
        assistant_turn: dict = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            assistant_turn["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in msg.tool_calls
            ]
        messages.append(assistant_turn)

        if not msg.tool_calls:
            return {"reply": _normalise_reply(msg.content or ""), "movies": list(surfaced.values())}

        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            movies, result_json = _run_tool(tc.function.name, args, intent=intent)
            for m in movies:
                surfaced.setdefault(m["id"], m)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result_json})

    # Hit the loop cap — return whatever we have with a graceful note.
    return {
        "reply": "I found some options but couldn't quite finish — here's what matched.",
        "movies": list(surfaced.values()),
    }

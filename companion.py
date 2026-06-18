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

SYSTEM_PROMPT = (
    "You are MovieDB's friendly movie companion. You help the user find films to "
    "watch from a local database. You CANNOT recommend any movie unless it is "
    "returned by one of your tools — never invent titles or rely on outside "
    "knowledge for recommendations. Use search_movies for descriptive requests "
    "(genre, era, rating, mood) and similar_movies when the user references a "
    "specific film. For niche sub-genres like cyberpunk, film noir, anime, "
    "heist, slasher or zombie movies, pass the matching `collection` argument to "
    "search_movies rather than guessing broad genres. Call the tools, then "
    "recommend a few options conversationally "
    "with one short reason each. Keep replies concise and warm."
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
                    "collection": {
                        "type": "string",
                        "enum": _COLLECTION_SLUGS,
                        "description": "A specific sub-genre to narrow to, e.g. 'cyberpunk', 'crime-noir', 'anime', 'heist'. Use this when the user names a niche category that isn't a broad genre.",
                    },
                    "sort_by": {
                        "type": "string",
                        "enum": ["popularity", "rating", "year", "title"],
                        "description": "Sort order. Default 'popularity'.",
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


def _compact(movie: dict) -> dict:
    """Trim a movie row to what the model needs to reason about it."""
    return {
        "id": movie["id"],
        "title": movie["title"],
        "year": movie.get("release_year"),
        "rating": movie.get("rating"),
        "genres": movie.get("genres", []),
    }


def _run_tool(name: str, args: dict) -> tuple[list[dict], str]:
    """Execute a tool. Returns (full movie dicts, JSON string for the model)."""
    if name == "search_movies":
        genre_map = _genre_name_to_id()
        genre_ids = [genre_map[g.lower()] for g in args.get("genres", []) if g.lower() in genre_map]
        kw_ids = queries.keyword_ids_for_collection(args["collection"]) if args.get("collection") else None
        movies = queries.search_movies(
            genres=genre_ids or None,
            genre_match=args.get("genre_match", "any"),
            year_min=args.get("year_min"),
            year_max=args.get("year_max"),
            rating_min=args.get("rating_min"),
            language=args.get("language"),
            keyword_ids=kw_ids,
            sort_by=args.get("sort_by", "popularity"),
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


def chat(history: list[dict]) -> dict:
    """Run one companion turn.

    `history` is a list of {role, content} dicts (user/assistant turns).
    Returns {reply: str, movies: [full movie dicts]}.
    """
    _require_key()
    client = OpenAI(base_url=BASE_URL, api_key=API_KEY)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}, *history]
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
            return {"reply": msg.content or "", "movies": list(surfaced.values())}

        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            movies, result_json = _run_tool(tc.function.name, args)
            for m in movies:
                surfaced.setdefault(m["id"], m)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result_json})

    # Hit the loop cap — return whatever we have with a graceful note.
    return {
        "reply": "I found some options but couldn't quite finish — here's what matched.",
        "movies": list(surfaced.values()),
    }

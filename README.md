# 🎬 Movie Recommendation App

A movie **filtering engine** with an AI companion: pick criteria (genre, year,
rating, sub-genre…) or just chat for a recommendation. Built on Python + FastAPI,
served **live from the TMDb API** (no local database), with a plain HTML/JS front end.

## Architecture

```
                 ┌──────────────── TMDb API ────────────────┐
                 │  /discover  /movie/{id}  /genre  /search  │
                 └────────────────────▲──────────────────────┘
                                       │ tmdb.py (cached, host-failover)
   static/index.html  ◄──►  main.py (FastAPI)  ──►  queries.py  ──┘
                                  │
                                  └──►  companion.py ──► OpenRouter (AI chat)
```

| File                | Role                                                                  |
|---------------------|-----------------------------------------------------------------------|
| `tmdb.py`           | Resilient, cached TMDb HTTP client (host failover + response cache)   |
| `queries.py`        | Turns filters into live TMDb queries — the core feature               |
| `subgenres.py`      | Curated sub-genre "collections" (Crime Noir, Anime…) → TMDb keyword ids |
| `companion.py`      | AI movie companion via OpenRouter, grounded in the live data          |
| `main.py`           | FastAPI app: `/api/movies`, `/api/genres`, `/api/collections`, `/api/chat`, serves the UI |
| `static/index.html` | UI: filters, sub-genre chips, results grid, detail modal, chat        |
| `ingest.py` / `db.py` / `seed_demo.py` / `enrich_keywords.py` | Optional offline tooling to build a local SQLite snapshot (not used at runtime) |

## Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Add your API keys
copy .env.example .env          # then edit .env:
#   TMDB_API_KEY        — required (free): https://www.themoviedb.org/settings/api  (v3 auth)
#   OPENROUTER_API_KEY  — required for the 🤖 AI companion: https://openrouter.ai/keys

# 3. Run the app
uvicorn main:app --reload       # or: python -m uvicorn main:app --reload
```

Then open <http://127.0.0.1:8000> for the UI, or <http://127.0.0.1:8000/docs>
for the interactive API. There's nothing to ingest — data is fetched live.

## The filter query

`queries.search_movies(...)` accepts every filter as an **optional** argument;
unselected filters become TMDb `/discover` query params:

- `genres` (list of ids) + `genre_match` = `"any"` (OR) or `"all"` (AND)
- `year_min` / `year_max`, `rating_min`, `language` (ISO code), `runtime_max`
- `keyword_ids` — drives the sub-genre collections (`/api/collections`)
- `sort_by` (`popularity` | `rating` | `year` | `title`) + `sort_dir`
- `limit` / `offset` (pagination)

## Deploying

The app is stateless and serves live from TMDb, so it runs on **any** host —
including **Vercel** (which couldn't serve the old file-based SQLite). Just set
two environment variables in your host's dashboard and deploy:

- `TMDB_API_KEY` — **required at runtime** (every request hits TMDb)
- `OPENROUTER_API_KEY` — required for the 🤖 AI companion

A `render.yaml` blueprint is included for one-click Render deploys; on Vercel,
expose `main:app` as the ASGI entrypoint and add the same env vars.

> Going live removed the bundled `movies.db` (and its size limits / redeploy-to-update
> cycle). The `ingest.py` / `seed_demo.py` scripts remain only as optional offline tooling.

## Next steps

1. **Favorites / watchlist** — let users mark films, then bias recommendations.
2. **Weighted ranking** — blend rating × popularity.
3. **More collections** — the keyword-id pattern in `subgenres.py` makes new ones trivial.

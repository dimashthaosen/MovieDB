# 🎬 Movie Recommendation App

A movie **filtering engine**: pick criteria (genre, year, rating, …) and get
matching films back. Built on Python + FastAPI + SQLite, with a plain HTML/JS
front end. Designed so you can layer real "recommendation" logic on top later.

## Architecture

```
TMDb API  ──ingest.py──►  movies.db (SQLite)  ◄──queries.py──  main.py (FastAPI)  ◄──►  static/index.html
```

| File              | Role                                                            |
|-------------------|-----------------------------------------------------------------|
| `db.py`           | Schema + connection helper (movies / genres / movie_genres)     |
| `ingest.py`       | Pulls movies from TMDb into the local database                  |
| `queries.py`      | Builds the dynamic filter query — the core feature              |
| `main.py`         | FastAPI app: `/api/movies`, `/api/genres`, serves the UI        |
| `static/index.html` | Minimal UI: filter dropdowns + results grid                   |

## Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Add your free TMDb API key
#    Get one at https://www.themoviedb.org/settings/api  (API Key, v3 auth)
copy .env.example .env          # then edit .env and paste your key

# 3. Load some movies into the database (~200 by default)
python ingest.py                # or:  python ingest.py --pages 25

# 4. Run the app
uvicorn main:app --reload
```

Then open <http://127.0.0.1:8000> for the UI, or
<http://127.0.0.1:8000/docs> for the interactive API.

## The filter query

`queries.search_movies(...)` accepts every filter as an **optional** argument;
unselected filters are skipped. Supported filters:

- `genres` (list of ids) + `genre_match` = `"any"` or `"all"`
- `year_min` / `year_max`
- `rating_min`
- `language` (ISO code, e.g. `"en"`)
- `runtime_max` (needs `python ingest.py --enrich` to populate runtimes)
- `sort_by` (`popularity` | `rating` | `year` | `title` | `runtime`) + `sort_dir`
- `limit` / `offset` (pagination)

## Deploying (Render)

The app ships with `render.yaml` and a committed `movies.db`, so deploying needs
no external database:

1. Push this repo to GitHub.
2. On [render.com](https://render.com): **New → Blueprint**, pick this repo. Render
   reads `render.yaml` and creates the web service.
3. In the service's **Environment** tab, add:
   - `OPENROUTER_API_KEY` — required for the 🤖 AI companion
   - `TMDB_API_KEY` — only needed if you re-run the ingest later
4. Deploy. Render runs `uvicorn main:app` and serves the app at your `*.onrender.com` URL.

> SQLite works because the app only **reads** `movies.db` at runtime. To grow the
> catalog, re-run `ingest.py` locally and commit the updated `movies.db`.
>
> **Note on Vercel:** this app does *not* run on Vercel as-is — Vercel's serverless
> filesystem is read-only/ephemeral, so file-based SQLite can't be served. Vercel
> would require migrating to a hosted database (e.g. Turso or Postgres).

## Next steps (the "recommendation" upgrade)

1. **Weighted results** — sort by a blend of rating × popularity.
2. **Favorites** — let users mark films, then surface their common genres.
3. **"More like this"** — given a movie, find others sharing the most genres.

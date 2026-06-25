# MovieDB

MovieDB is a movie discovery app built with FastAPI, TMDb, OpenRouter, and a plain HTML/CSS/JavaScript frontend.

It helps users browse movies, filter by taste, save favorites, open rich detail pages, and ask an AI companion for grounded recommendations.

## Current Features

- Live TMDb-powered movie browsing.
- Database-wide title search with pagination.
- Filters for genres, year range, minimum rating, original language, runtime, and sort order.
- Curated collection chips such as Anime, Biopic, Holiday, and Coming of Age.
- Movie detail modal with overview, trailer/site links, cast, crew, facts, where-to-watch providers, and recommendation groups.
- Favorites / My List for signed-in users.
- Personalized For You recommendations using explicit taste inputs plus saved favorites when signed in.
- AI companion powered by OpenRouter and grounded through local movie search tools.
- Optional account support backed by Postgres and JWT auth.

## Stack

| File | Purpose |
| --- | --- |
| `main.py` | FastAPI app, API routes, auth routes, and static UI serving |
| `queries.py` | TMDb query layer, ranking, recommendation logic, and For You scoring |
| `tmdb.py` | TMDb client with caching, retries, and host failover |
| `companion.py` | AI companion with tool-calling into movie search |
| `userdb.py` | Optional Postgres user, favorites, and saved taste profile storage |
| `auth.py` | JWT and password helpers |
| `subgenres.py` | Curated collection definitions and TMDb keyword ids |
| `static/index.html` | Frontend shell and HTML markup |
| `static/styles.css` | Frontend styles and responsive layout |
| `static/app.js` | Client-side app logic |

## Setup

```bash
pip install -r requirements.txt
copy .env.example .env
python -m uvicorn main:app --reload
```

Open `http://127.0.0.1:8000`.

## Environment Variables

Required:

- `TMDB_API_KEY`: TMDb v3 API key.
- `OPENROUTER_API_KEY`: OpenRouter key for the AI companion.

Optional:

- `OPENROUTER_MODEL`: defaults to `google/gemini-3.1-flash-lite:online`.
- `JWT_SECRET`: secret used for account sessions.
- `POSTGRES_URL`, `DATABASE_URL`, or another configured Postgres URL: enables accounts, favorites, and saved taste profiles.

## Main API Endpoints

- `GET /api/movies`: browse/search movies with filters, `limit`, and `offset`.
- `GET /api/genres`: TMDb genre list.
- `GET /api/collections`: curated collection chips with counts.
- `GET /api/movies/{id}`: movie details.
- `GET /api/movies/{id}/extras`: cast, crew, facts, and trailers.
- `GET /api/movies/{id}/watch-providers`: streaming/rent/buy provider data.
- `GET /api/movies/{id}/recommendations`: grouped More Like This recommendations.
- `POST /api/recommendations/personalized`: For You recommendations.
- `POST /api/chat`: AI companion.
- `POST /api/auth/signup`, `POST /api/auth/login`, `GET /api/auth/me`: account flow.
- `GET/POST/DELETE /api/favorites`: My List.
- `GET/PUT /api/taste-profile`: saved For You taste profile.

## Notes

- The app uses live TMDb data at runtime; there is no bundled movie database.
- The frontend has been split into `static/index.html`, `static/styles.css`, and `static/app.js`. A future pass can split `app.js` into modules for modal, chat, recommendations, auth, and filters.
- `ingest.py`, `db.py`, `seed_demo.py`, and `enrich_keywords.py` are optional older/offline utilities and are not required for the live app.

## Suggested Next Improvements

- Split `static/app.js` into smaller modules once the product surface settles.
- Add automated browser tests for search, pagination, For You, details, auth, and favorites.
- Add server-side response caching or a shared cache for higher traffic.
- Add richer onboarding for For You so users can build a taste profile before browsing.
- Add clearer production deployment notes for Vercel and Render.

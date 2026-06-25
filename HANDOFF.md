# MovieDB Handoff

Last updated: 2026-06-26

MovieDB is a FastAPI movie discovery app with a plain HTML/CSS/JavaScript frontend. It uses live TMDb data for browsing and details, OpenRouter for the AI companion, and optional Postgres storage for accounts, favorites, and saved taste profiles.

## Repository

- GitHub: https://github.com/dimashthaosen/MovieDB
- Current branch: `main`
- Primary UI shell: `static/index.html`
- Local run command: `python -m uvicorn main:app --reload`

## Current Product State

| Area | Status |
| --- | --- |
| Live TMDb browse/search | Done |
| Database-wide search | Done |
| Pagination | Done |
| Genre/year/rating/language/runtime/sort filters | Done |
| Curated collections | Done |
| Movie detail modal | Done |
| Cast, crew, facts, trailers | Done |
| Where to watch | Done |
| More Like This groups | Done |
| Favorites / My List | Done, requires account storage |
| Accounts | Done, requires Postgres and JWT secret |
| Saved taste profile | Done, requires account storage |
| For You personalized recommendations | Done |
| Saved favorites blended into For You | Done |
| AI movie companion | Done |

## Architecture

```text
Browser UI
  -> main.py FastAPI routes
    -> queries.py recommendation/search layer
      -> tmdb.py live TMDb client
    -> companion.py OpenRouter AI companion
    -> userdb.py optional Postgres storage
```

## Important Files

- `main.py`: FastAPI app, movie endpoints, auth endpoints, favorites, taste profile.
- `queries.py`: TMDb discover/search wrappers, ranking, personalized scoring.
- `tmdb.py`: TMDb request helper with cache and failover.
- `companion.py`: AI companion prompt and tool-calling.
- `userdb.py`: Postgres-backed user accounts, favorites, taste profiles.
- `auth.py`: JWT and password helpers.
- `subgenres.py`: curated collection configuration.
- `static/index.html`: frontend shell and markup.
- `static/styles.css`: frontend styles and responsive layout.
- `static/app.js`: client-side logic for browse, filters, modal, chat, auth, favorites, and For You.

## Environment Variables

Required:

- `TMDB_API_KEY`: TMDb v3 key.
- `OPENROUTER_API_KEY`: OpenRouter key.

Optional:

- `OPENROUTER_MODEL`: defaults to `google/gemini-3.1-flash-lite:online`.
- `JWT_SECRET`: required for stable account sessions in production.
- `POSTGRES_URL` or `DATABASE_URL`: enables account/favorites/profile storage.

## Main Endpoints

- `GET /api/movies`
  - Params: `query`, `genres`, `genre_match`, `year_min`, `year_max`, `rating_min`, `language`, `runtime_max`, `collection`, `sort_by`, `sort_dir`, `limit`, `offset`.
- `GET /api/genres`
- `GET /api/collections`
- `GET /api/movies/{movie_id}`
- `GET /api/movies/{movie_id}/extras`
- `GET /api/movies/{movie_id}/watch-providers`
- `GET /api/movies/{movie_id}/recommendations`
- `POST /api/recommendations/personalized`
- `POST /api/chat`
- `POST /api/auth/signup`
- `POST /api/auth/login`
- `GET /api/auth/me`
- `GET/POST/DELETE /api/favorites`
- `GET/PUT /api/taste-profile`

## Current Frontend Behavior

- Search bar calls backend search, not local filtering.
- Browse pages show 50 movies per page with Previous/Next controls.
- Filters reset pagination to page 1.
- For You uses manual liked-movie anchors plus saved favorites when signed in.
- The For You panel explains that saved favorites quietly improve picks.
- Browse/search/page/For You requests show skeleton loading states.
- Phone header wraps so search gets a full-width row.

## Known Technical Debt

- `static/app.js` is still large and should eventually be split into modules for filters, modal, chat, auth, favorites, and recommendations.
- README/deployment notes should be kept updated whenever new product features ship.
- There are no automated browser regression tests yet.
- TMDb data can be slow or unavailable, so higher-traffic deployments should use stronger caching.

## Suggested Next Pass

1. Split `static/app.js` into smaller modules without changing behavior.
2. Add Playwright smoke tests for browse, search, pagination, details, For You, and favorites.
3. Add a clearer first-run onboarding path for For You.
4. Add a production deploy checklist for Vercel/Render env vars.

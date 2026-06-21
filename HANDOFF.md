# MovieDB — Handoff Document

_Last updated: 2026-06-19_

A movie discovery web app: filter by genre/year/rating/sub-genre, view details
and "more like this," and chat with an AI companion for recommendations. Data is
served **live from the TMDb API** — there is no database to maintain.

- **Repo:** https://github.com/dimashthaosen/MovieDB
- **Production:** https://movie-db-ashy-five.vercel.app (Vercel)
- **Stack:** Python · FastAPI · plain HTML/JS · TMDb API · OpenRouter (AI)

---

## 1. Current status

| Area | State |
|------|-------|
| Core filtering UI (genre, year, rating, sort) | ✅ Done |
| Sub-genre "collections" chips (Crime Noir, Anime, Cyberpunk…) | ✅ Done |
| Movie detail modal + "more like this" | ✅ Done |
| AI companion (chat → grounded recommendations) | ✅ Done |
| Live TMDb data layer (no local DB) | ✅ Done |
| Local run | ✅ Verified working |
| Vercel deploy | ⚠️ Function runs; was returning 502 — see §6 (env-var key had trailing whitespace; fix is re-pasting a clean 32-char key + redeploy) |
| Render deploy (`render.yaml`) | Available, not actively used |

---

## 2. Architecture

```
                 ┌──────────────── TMDb API ────────────────┐
                 │  /discover  /movie/{id}  /genre  /search  │
                 └────────────────────▲──────────────────────┘
                                       │ tmdb.py (cached, host-failover)
   static/index.html  ◄──►  main.py (FastAPI)  ──►  queries.py  ──┘
                                  │
                                  └──►  companion.py ──► OpenRouter (AI chat)
```

The app is **stateless**: every request fetches live from TMDb. This is why it
deploys on Vercel (no file-based database to persist).

### Key files
| File | Role |
|------|------|
| `tmdb.py` | Resilient, cached TMDb HTTP client (host failover + response cache, fail-fast on 401) |
| `queries.py` | Turns filter choices into live TMDb queries — the core data layer |
| `subgenres.py` | Curated sub-genre "collections" → pre-resolved TMDb keyword IDs |
| `companion.py` | AI companion via OpenRouter, with tool-calling into the live queries |
| `main.py` | FastAPI app + endpoints, serves the UI |
| `static/index.html` | Entire front end (filters, chips, grid, detail modal, chat) |
| `requirements.txt` | Python deps (fastapi, uvicorn, requests, python-dotenv, openai) |
| `render.yaml` | Render deploy blueprint |
| `ingest.py`, `db.py`, `seed_demo.py`, `enrich_keywords.py` | **Optional offline tooling** to build a local SQLite snapshot — NOT used at runtime |

### API endpoints
- `GET /api/movies` — filtered search (`genres`, `genre_match`, `year_min/max`, `rating_min`, `language`, `runtime_max`, `collection`, `sort_by`, `sort_dir`, `limit`, `offset`)
- `GET /api/movies/{id}` — full detail
- `GET /api/movies/{id}/similar` — recommendations
- `GET /api/genres` — genre list
- `GET /api/collections` — sub-genre collections with live counts
- `POST /api/chat` — AI companion (`{messages:[{role,content}]}` → `{reply, movies}`)

---

## 3. Configuration (environment variables)

Both are required **at runtime** (the app calls these APIs on every request):

| Var | Purpose | Where to get it |
|-----|---------|-----------------|
| `TMDB_API_KEY` | Movie data | https://www.themoviedb.org/settings/api → **"API Key (v3 auth)"** — a **32-char** key (NOT the long v4 `eyJ…` token) |
| `OPENROUTER_API_KEY` | AI companion | https://openrouter.ai/keys (pay-as-you-go credit) |

Local: a `.env` file (gitignored). Production: the host's env-var dashboard.
`OPENROUTER_MODEL` optionally overrides the model (default `google/gemini-3.1-flash-lite:online`).

---

## 4. Run locally

```bash
pip install -r requirements.txt
copy .env.example .env          # then paste both keys into .env
python -m uvicorn main:app --reload
```

Open http://127.0.0.1:8000. (Use `python -m uvicorn`, not bare `uvicorn` — the
script may not be on PATH.)

---

## 5. Deploy

### Vercel (current production)
1. Expose `main:app` as the ASGI entrypoint (project is already configured).
2. **Settings → Environment Variables**: add `TMDB_API_KEY` and `OPENROUTER_API_KEY`
   for **all environments** (Production/Preview/Development).
3. **Redeploy** — env-var changes only apply to new deployments.

### Render (alternative)
`render.yaml` is included. New → Blueprint → pick the repo → set the two env vars
→ deploy. Runs `python -m uvicorn main:app`.

---

## 6. Gotchas & lessons learned (read before debugging)

1. **TMDb env-var key with trailing whitespace → 401.** A copy-pasted key often
   picks up a trailing newline/space (33 chars instead of 32). TMDb then returns
   `Invalid API key`. The 401 error message now prints a masked key fingerprint
   (`len=…, '1cb4…b368'`) to diagnose this. Fix: re-paste exactly 32 chars, no
   trailing whitespace, then redeploy.
2. **v3 key vs v4 token.** The app uses the short **v3** key via `?api_key=`. The
   long v4 `eyJ…` token will 401.
3. **Vercel needs a redeploy after editing env vars** — they don't apply to the
   running deployment retroactively.
4. **Dev's home ISP intermittently blocks `api.themoviedb.org`** (TLS resets). 
   `tmdb.py` automatically falls back to `api.tmdb.org` and retries — this does
   NOT affect cloud hosts (Vercel/Render reach TMDb fine).
5. **`uvicorn: command not found`** on Windows → use `python -m uvicorn`.
6. **Vercel + SQLite doesn't work** — the app used to bundle `movies.db`, but
   Vercel's read-only/ephemeral filesystem can't serve file-based SQLite. That's
   why it was rearchitected to live TMDb serving. Don't reintroduce a file DB for
   the Vercel deploy.

---

## 7. Optional next steps

- **Favorites / watchlist** — let users mark films, bias recommendations.
- **Weighted ranking** — blend rating × popularity for "best" sorting.
- **More collections** — add entries to `subgenres.py` (pre-resolve keyword IDs).
- **Runtime filter in the UI** — backend already supports `runtime_max` live.
- **Response caching / rate-limit handling** — for higher traffic, cache TMDb
  responses more aggressively (basic in-memory TTL cache already in `tmdb.py`).

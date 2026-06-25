const $ = (id) => document.getElementById(id);
    const esc = (s) => String(s ?? "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");

    const state = {
      allGenres: [], genres: [], genreMatch: "any", genreMenuOpen: false,
      yearMin: "", yearMax: "", ratingMin: "", language: "", runtimeMax: "", sortBy: "popularity",
      collections: [], activeCollection: null, query: "",
      results: [], lastCount: 0, page: 0, pageSize: 50, hasMore: false,
      forYou: false, tasteLoading: false,
      taste: { liked_movies: [], anchorQuery: "", anchorSuggestions: [], anchorLoading: false, vibes: [], rating_flexibility: 0.35, language_scope: "", era: "", runtime: "", movie_type: "", zeitgeist: "" },
      modalId: null,
      chatOpen: false, chatMessages: [], typing: false,
      user: null, accountsEnabled: false,
      favorites: new Set(), favoritesList: [], viewingList: false,
    };
    const favCandidates = new Map();
    const favSnapshot = (m) => ({ id: m.id, title: m.title, release_year: m.release_year, rating: m.rating, poster_url: m.poster_url, genres: m.genres || [], runtime: m.runtime });
    const movieCache = new Map();
    const extrasCache = new Map();
    const providerCache = new Map();
    const recCache = new Map();
    let tasteRequestSeq = 0;
    let tasteTimer = null;

    // Deterministic poster gradient (matches design tokens) for missing images.
    const PALETTES = [
      ["#214d4f","#0c1c1d"],["#4a2333","#1c0d13"],["#26264f","#0f0f22"],
      ["#234d2c","#0d1d12"],["#4a3a1f","#1c160c"],["#3a234f","#160d22"],
      ["#1f3550","#0c1622"],["#4a2c1f","#1c100c"],["#2f4a4a","#101f1f"],
      ["#43204a","#190c1c"],["#4a4220","#1c190c"],["#1f4a44","#0c1c1a"],
    ];
    function gradientFor(id) {
      const i = (((Math.abs(id) - 1) % PALETTES.length) + PALETTES.length) % PALETTES.length;
      const p = PALETTES[i];
      return `linear-gradient(155deg, ${p[0]} 0%, ${p[1]} 100%)`;
    }
    function posterLayer(m) {
      const bg = `background:${gradientFor(m.id)}`;
      const img = m.poster_url ? `<img src="${esc(m.poster_url)}" alt="" loading="lazy" />` : "";
      return { bg, img };
    }
    const ratingText = (r) => (r ? Number(r).toFixed(1) : "–");
    const minimal = (text) => esc(text)
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/(^|\n)\s*[\*\-]\s+/g, "$1• ");

    /* ---------------- data ---------------- */
    async function api(path) {
      const r = await fetch(path);
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    }
    async function cached(map, key, path) {
      if (!map.has(key)) map.set(key, api(path));
      return map.get(key);
    }

    function buildQuery() {
      const p = new URLSearchParams();
      state.genres.forEach((id) => p.append("genres", id));
      p.set("genre_match", state.genreMatch);
      if (state.query.trim()) p.set("query", state.query.trim());
      if (state.yearMin) p.set("year_min", state.yearMin);
      if (state.yearMax) p.set("year_max", state.yearMax);
      if (state.ratingMin) p.set("rating_min", state.ratingMin);
      if (state.language) p.set("language", state.language);
      if (state.runtimeMax) p.set("runtime_max", state.runtimeMax);
      if (state.activeCollection) p.set("collection", state.activeCollection);
      p.set("sort_by", state.sortBy);
      p.set("sort_dir", state.sortBy === "title" ? "asc" : "desc");
      p.set("limit", String(state.pageSize));
      p.set("offset", String(state.page * state.pageSize));
      return p.toString();
    }

    let fetchTimer = null;
    function scheduleFetch(delay = 0) {
      clearTimeout(fetchTimer);
      fetchTimer = setTimeout(fetchMovies, delay);
    }
    async function fetchMovies() {
      if (!state.viewingList && !state.forYou) {
        renderBrowseLoading(state.query.trim() ? "Searching movies" : "Loading titles");
      }
      try {
        const data = await api("/api/movies?" + buildQuery());
        state.results = data.results || [];
        state.lastCount = data.count ?? state.results.length;
        state.hasMore = !!data.has_more;
      } catch (e) {
        state.results = [];
        state.lastCount = 0;
        state.hasMore = false;
      }
      renderGrid();
    }

    function browseFetch() {
      state.forYou = false;
      tasteRequestSeq += 1;
      state.viewingList = false;
      renderTasteControls();
      fetchMovies();
    }

    function resetBrowsePage() {
      state.page = 0;
      state.hasMore = false;
    }

    function restartBrowseFetch() {
      resetBrowsePage();
      browseFetch();
    }

    function leaveForYou() {
      state.forYou = false;
      state.tasteLoading = false;
      tasteRequestSeq += 1;
      resetBrowsePage();
      renderTasteControls();
      fetchMovies();
    }

    function visibleMovies() {
      const source = state.viewingList ? state.favoritesList : state.results;
      if (!state.viewingList) return source;
      const q = state.query.trim().toLowerCase();
      if (!q) return source;
      return source.filter((m) => (m.title || "").toLowerCase().includes(q));
    }

    let anchorTimer = null;
    function compactTitle(m) {
      return `${m.title || "Untitled"}${m.release_year ? ` (${m.release_year})` : ""}`;
    }
    function addAnchorMovie(movie) {
      if (state.tasteLoading) return;
      if (!movie || !movie.id || state.taste.liked_movies.some(m => m.id === movie.id)) return;
      state.taste.liked_movies = state.taste.liked_movies.concat([movie]).slice(0, 5);
      state.taste.anchorQuery = "";
      state.taste.anchorSuggestions = [];
      $("anchorSearch").value = "";
      renderTasteControls();
      if (state.forYou) runTasteMatch();
    }
    function removeAnchorMovie(id) {
      if (state.tasteLoading) return;
      state.taste.liked_movies = state.taste.liked_movies.filter(m => m.id !== id);
      renderTasteControls();
      if (state.forYou) runTasteMatch();
    }
    async function searchAnchorMovies(query) {
      const q = query.trim();
      state.taste.anchorQuery = q;
      if (q.length < 2) {
        state.taste.anchorSuggestions = [];
        state.taste.anchorLoading = false;
        renderTasteControls();
        return [];
      }
      state.taste.anchorLoading = true;
      renderTasteControls();
      try {
        const data = await api("/api/movies?query=" + encodeURIComponent(q) + "&limit=6");
        if (state.taste.anchorQuery !== q) return;
        const selected = new Set(state.taste.liked_movies.map(m => m.id));
        state.taste.anchorSuggestions = (data.results || []).filter(m => !selected.has(m.id)).slice(0, 5);
        return state.taste.anchorSuggestions;
      } catch (e) {
        if (state.taste.anchorQuery === q) state.taste.anchorSuggestions = [];
        return [];
      } finally {
        if (state.taste.anchorQuery === q) {
          state.taste.anchorLoading = false;
          renderTasteControls();
        }
      }
    }

    async function addFirstAnchorCandidate() {
      if (state.tasteLoading) return;
      const current = $("anchorSearch").value.trim();
      const first = state.taste.anchorSuggestions[0];
      if (first && (!current || compactTitle(first).toLowerCase().includes(current.toLowerCase()) || first.title.toLowerCase().includes(current.toLowerCase()))) {
        addAnchorMovie(first);
        return;
      }
      const matches = await searchAnchorMovies(current);
      if (matches && matches[0]) addAnchorMovie(matches[0]);
    }

    /* ---------------- render: grid + meta ---------------- */
    function genreLabelText() {
      if (state.genres.length === 0) return "All genres";
      if (state.genres.length === 1) {
        const g = state.allGenres.find((x) => x.id === state.genres[0]);
        return g ? g.name : "1 selected";
      }
      return state.genres.length + " selected";
    }

    function reasonText(reason) {
      return String(reason || "")
        .replace(/^shares your anchor taste:/i, "Shares your taste:")
        .replace(/^matches your selected vibe:/i, "Matches your vibe:")
        .replace(/^fits your movie-type preference:/i, "Fits your preferred type:")
        .replace(/^fits your zeitgeist preference:/i, "Fits your discovery mode:");
    }

    function cardHTML(m) {
      const { bg, img } = posterLayer(m);
      const sub = m.release_year ? esc(m.release_year) + (m.runtime ? " · " + m.runtime + " min" : "") : (m.runtime ? m.runtime + " min" : "—");
      const top = (m.genres && m.genres[0]) ? esc(m.genres[0]) : "";
      favCandidates.set(m.id, favSnapshot(m));
      const fav = state.user
        ? `<button class="fav-btn ${state.favorites.has(m.id) ? "on" : ""}" data-fav="${m.id}" aria-label="Save to your list" title="Save to your list">${state.favorites.has(m.id) ? "♥" : "♡"}</button>`
        : "";
      const match = m.match_score
        ? `<div class="match-panel"><div class="match-score">${esc(m.match_score)}% taste match${m.risk_level ? ` · ${esc(m.risk_level)}` : ""}</div><ul>${(m.match_reasons || []).slice(0, 3).map(r => `<li>${esc(reasonText(r))}</li>`).join("")}</ul></div>`
        : "";
      return `
        <div class="card" data-id="${m.id}">
          <div class="poster" style="${bg}">
            ${img}
            <div class="scrim"></div>
            <div class="badge"><span class="star">&#9733;</span>${ratingText(m.rating)}</div>
            <div class="topgenre">${top}</div>
            ${fav}
          </div>
          <div class="card-info">
            <div class="card-title">${esc(m.title)}</div>
            <div class="card-sub">${sub}</div>
            ${match}
          </div>
        </div>`;
    }

    function skeletonGrid(count = 10) {
      return `<div class="grid skeleton-grid">${Array.from({ length: count }).map(() => `
        <div class="skeleton-card">
          <div class="sk-poster"></div>
          <div class="sk-info">
            <div class="sk-line"></div>
            <div class="sk-line short"></div>
          </div>
        </div>
      `).join("")}</div>`;
    }

    function renderBrowseLoading(label) {
      const start = (state.page * state.pageSize) + 1;
      const end = (state.page + 1) * state.pageSize;
      $("meta").innerHTML = `<span class="num">${esc(label)}</span><span class="lbl">Page ${state.page + 1} · ${start}-${end}</span>`;
      $("results").innerHTML = skeletonGrid(10);
      $("pager").innerHTML = "";
    }

    function pageRangeLabel(listLength = state.results.length) {
      if (!listLength) return `Page ${state.page + 1}`;
      const start = (state.page * state.pageSize) + 1;
      const end = (state.page * state.pageSize) + listLength;
      return `Page ${state.page + 1} · ${start}-${end}${state.hasMore ? "+" : ""}`;
    }

    function renderForYouLoading() {
      $("tasteStatus").textContent = "Scoring your taste profile...";
      $("meta").innerHTML = `<span class="num">For You</span><span class="lbl">building matches from your signals and saved favorites</span>`;
      $("results").innerHTML = skeletonGrid(8);
      $("pager").innerHTML = "";
    }

    function renderGrid() {
      const list = visibleMovies();
      if (state.viewingList) {
        $("meta").innerHTML = `<span class="num">${list.length}</span><span class="lbl">in your list</span>`;
        $("results").innerHTML = list.length
          ? `<div class="grid">${list.map(cardHTML).join("")}</div>`
          : `<div class="empty"><div class="ico">♡</div><div class="msg">No saved movies yet — tap the ♥ on any poster to add it.</div></div>`;
        renderPager();
        return;
      }
      // meta
      const bits = [];
      if (state.activeCollection) {
        const c = state.collections.find((x) => x.slug === state.activeCollection);
        if (c) bits.push(c.label);
      }
      if (state.genres.length) bits.push(genreLabelText());
      const summary = bits.length ? " · " + bits.join(" · ") : "";
      const pageSummary = state.forYou ? "" : ` · ${pageRangeLabel(list.length)}`;
      $("meta").innerHTML = state.forYou
        ? `<span class="num">${list.length}</span><span class="lbl">taste matches with reasons</span>`
        : `<span class="num">${list.length}</span><span class="lbl">titles${esc(summary)}${esc(pageSummary)}</span>`;

      if (!list.length) {
        const emptyMessage = state.forYou
          ? "No For You matches yet. Add a favorite, choose a vibe, or loosen rating tolerance."
          : "No movies match those filters.";
        $("results").innerHTML = `
          <div class="empty">
            <div class="ico">&#127902;</div>
            <div class="msg">${esc(emptyMessage)}</div>
            <button id="emptyReset">Reset filters</button>
          </div>`;
        const er = $("emptyReset");
        if (er) er.addEventListener("click", resetFilters);
        renderPager();
        return;
      }
      $("results").innerHTML = `<div class="grid">${list.map(cardHTML).join("")}</div>`;
      renderPager();
    }

    function renderPager() {
      if (state.forYou || state.viewingList || (!state.hasMore && state.page === 0)) {
        $("pager").innerHTML = "";
        return;
      }
      $("pager").innerHTML = `
        <button id="prevPage" type="button" ${state.page === 0 ? "disabled" : ""}>Previous</button>
        <span class="page-label">${esc(pageRangeLabel())}</span>
        <button id="nextPage" type="button" ${state.hasMore ? "" : "disabled"}>Next</button>`;
      $("prevPage").addEventListener("click", () => goPage(state.page - 1));
      $("nextPage").addEventListener("click", () => goPage(state.page + 1));
    }

    function goPage(page) {
      if (page < 0 || (page > state.page && !state.hasMore)) return;
      state.page = page;
      window.scrollTo({ top: 0, behavior: "smooth" });
      fetchMovies();
    }

    function tastePayload() {
      return {
        liked_movie_ids: state.taste.liked_movies.map(m => m.id).filter(Boolean),
        vibes: state.taste.vibes,
        rating_flexibility: Number(state.taste.rating_flexibility || 0.35),
        language_scope: state.taste.language_scope || null,
        era: state.taste.era || null,
        runtime: state.taste.runtime || null,
        movie_type: state.taste.movie_type || null,
        zeitgeist: state.taste.zeitgeist || null,
        limit: 36,
      };
    }

    function tasteSignalSummary() {
      const parts = [];
      if (state.user && state.favoritesList.length) {
        parts.push(`${state.favoritesList.length} saved favorite${state.favoritesList.length === 1 ? "" : "s"}`);
      }
      if (state.taste.liked_movies.length) {
        parts.push(`${state.taste.liked_movies.length} manual pick${state.taste.liked_movies.length === 1 ? "" : "s"}`);
      }
      if (state.taste.vibes.length) {
        parts.push(`${state.taste.vibes.length} vibe${state.taste.vibes.length === 1 ? "" : "s"}`);
      }
      return parts.length ? `Using ${parts.join(" + ")}.` : "Using broad discovery signals.";
    }

    function scheduleTasteMatch(delay = 450) {
      if (!state.forYou || state.tasteLoading) return;
      clearTimeout(tasteTimer);
      tasteTimer = setTimeout(runTasteMatch, delay);
    }

    function renderTasteControls() {
      $("tastePanel").classList.toggle("open", state.forYou);
      $("tasteToggle").classList.toggle("on", state.forYou);
      $("runTaste").disabled = state.tasteLoading;
      $("anchorAdd").disabled = state.tasteLoading;
      $("anchorSearch").disabled = state.tasteLoading;
      document.querySelectorAll(".vibe-chip").forEach(btn => {
        btn.classList.toggle("on", state.taste.vibes.includes(btn.dataset.vibe));
        btn.disabled = state.tasteLoading;
      });
      $("tasteEra").value = state.taste.era || "";
      $("tasteType").value = state.taste.movie_type || "";
      $("tasteLanguage").value = state.taste.language_scope || "";
      $("tasteRuntime").value = state.taste.runtime || "";
      $("tasteZeitgeist").value = state.taste.zeitgeist || "";
      $("ratingFlex").value = state.taste.rating_flexibility ?? 0.35;
      ["tasteEra", "tasteType", "tasteLanguage", "tasteRuntime", "tasteZeitgeist", "ratingFlex"].forEach(id => {
        $(id).disabled = state.tasteLoading;
      });
      $("anchorSearch").value = state.taste.anchorQuery || "";
      $("anchorList").innerHTML = state.taste.liked_movies.map(m => `
        <span class="anchor-chip">${esc(compactTitle(m))}<button type="button" data-anchor-remove="${m.id}" aria-label="Remove ${esc(m.title)}" ${state.tasteLoading ? "disabled" : ""}>&times;</button></span>
      `).join("");
      const suggestions = state.taste.anchorLoading
        ? `<span class="anchor-hint">Searching...</span>`
        : state.taste.anchorSuggestions.map(m => `<button class="anchor-suggestion" type="button" data-anchor-id="${m.id}" ${state.tasteLoading ? "disabled" : ""}>${esc(compactTitle(m))}</button>`).join("");
      $("anchorSuggestions").innerHTML = suggestions;
    }

    async function runTasteMatch() {
      const requestId = ++tasteRequestSeq;
      state.forYou = true;
      state.tasteLoading = true;
      renderTasteControls();
      renderForYouLoading();
      try {
        const request = {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(tastePayload()),
        };
        const r = getToken() ? await authedFetch("/api/recommendations/personalized", request) : await fetch("/api/recommendations/personalized", request);
        if (!r.ok) throw new Error("HTTP " + r.status);
        const data = await r.json();
        if (requestId !== tasteRequestSeq || !state.forYou) return;
        state.results = data.results || [];
        state.lastCount = state.results.length;
        $("tasteStatus").textContent = state.results.length
          ? `${tasteSignalSummary()} Sorted by personal fit, with reasons on each card.`
          : "No matches yet. Add a favorite, choose a vibe, or loosen rating tolerance.";
      } catch (e) {
        if (requestId !== tasteRequestSeq || !state.forYou) return;
        state.results = [];
        $("tasteStatus").textContent = "Could not build matches right now.";
      } finally {
        if (requestId !== tasteRequestSeq) return;
        state.tasteLoading = false;
        renderGrid();
        renderTasteControls();
      }
    }

    /* ---------------- render: genres ---------------- */
    function renderGenreTrigger() { $("genreLabel").textContent = genreLabelText(); }

    function renderGenrePopover() {
      const existing = $("genrePopover");
      if (existing) existing.remove();
      const overlay = $("genreOverlay");
      if (overlay) overlay.remove();
      if (!state.genreMenuOpen) return;

      const ov = document.createElement("div");
      ov.className = "popover-overlay"; ov.id = "genreOverlay";
      ov.addEventListener("click", () => { state.genreMenuOpen = false; renderGenrePopover(); });

      const pop = document.createElement("div");
      pop.className = "popover"; pop.id = "genrePopover";
      pop.innerHTML = `
        <div class="popover-top">
          <div class="seg">
            <button data-m="any" class="${state.genreMatch === "any" ? "on" : ""}">Any</button>
            <button data-m="all" class="${state.genreMatch === "all" ? "on" : ""}">All</button>
          </div>
          <button class="clear-btn" id="clearGenres">Clear</button>
        </div>
        <div class="genre-pills">
          ${state.allGenres.map((g) => `<button class="gpill ${state.genres.includes(g.id) ? "on" : ""}" data-gid="${g.id}">${esc(g.name)}</button>`).join("")}
        </div>`;

      pop.querySelectorAll(".seg button").forEach((b) =>
        b.addEventListener("click", () => { state.genreMatch = b.dataset.m; resetBrowsePage(); renderGenrePopover(); browseFetch(); })
      );
      pop.querySelector("#clearGenres").addEventListener("click", () => { state.genres = []; resetBrowsePage(); renderGenrePopover(); renderGenreTrigger(); browseFetch(); });
      pop.querySelectorAll(".gpill").forEach((b) =>
        b.addEventListener("click", () => {
          const id = Number(b.dataset.gid);
          state.genres = state.genres.includes(id) ? state.genres.filter((x) => x !== id) : state.genres.concat([id]);
          resetBrowsePage(); renderGenrePopover(); renderGenreTrigger(); browseFetch();
        })
      );
      $("genreField").appendChild(ov);
      $("genreField").appendChild(pop);
    }

    /* ---------------- render: collections ---------------- */
    function renderCollections() {
      const chips = [];
      if (state.user) {
        chips.push(`<button class="chip ${state.viewingList ? "on" : ""}" data-list="1"><span>♥</span><span>My List</span><span class="cnt">${state.favoritesList.length}</span></button>`);
      }
      chips.push(`<button class="chip ${(!state.activeCollection && !state.viewingList) ? "on" : ""}" data-slug=""><span>&#127916;</span><span>All</span></button>`);
      for (const c of state.collections) {
        chips.push(`<button class="chip ${(state.activeCollection === c.slug && !state.viewingList) ? "on" : ""}" data-slug="${esc(c.slug)}"><span>${c.emoji}</span><span>${esc(c.label)}</span><span class="cnt">${c.count ?? ""}</span></button>`);
      }
      const bar = $("collections");
      bar.innerHTML = chips.join("");
      bar.querySelectorAll(".chip").forEach((ch) =>
        ch.addEventListener("click", () => {
          if (ch.dataset.list) { state.viewingList = true; renderCollections(); renderGrid(); return; }
          state.viewingList = false;
          state.activeCollection = ch.dataset.slug || null;
          renderCollections(); restartBrowseFetch();
        })
      );
    }

    /* ---------------- modal ---------------- */
    function miniHTML(m, sharedLabel) {
      const { bg, img } = posterLayer(m);
      const shared = sharedLabel != null ? `<div class="shared">${sharedLabel}</div>` : "";
      return `
        <div class="mini" data-id="${m.id}">
          <div class="poster" style="${bg}">
            ${img}
            <div class="mscrim"></div>
            <div class="mbadge"><span class="star">&#9733;</span>${ratingText(m.rating)}</div>
            <div class="mt">${esc(m.title)}</div>
          </div>
          ${shared}
        </div>`;
    }

    function personHTML(p) {
      const photo = p.profile_url
        ? `<img src="${esc(p.profile_url)}" alt="" loading="lazy" />`
        : `<div class="person-fallback">${esc((p.name || "?").slice(0, 1))}</div>`;
      return `
        <div class="person-card">
          ${photo}
          <div class="person-info">
            <div class="person-name">${esc(p.name || "Unknown")}</div>
            <div class="person-role">${esc(p.character || p.job || "")}</div>
          </div>
        </div>`;
    }

    function crewHTML(crew, loading) {
      if (loading) return `<div class="detail-section"><h3>Crew</h3><div class="detail-loading">Loading crew...</div></div>`;
      if (!crew) return "";
      const rows = [
        crew.directors?.length ? `<div><b>Directing:</b> ${crew.directors.map(esc).join(", ")}</div>` : "",
        crew.writers?.length ? `<div><b>Writing:</b> ${crew.writers.map(esc).join(", ")}</div>` : "",
        crew.producers?.length ? `<div><b>Production:</b> ${crew.producers.map(esc).join(", ")}</div>` : "",
        crew.composers?.length ? `<div><b>Music:</b> ${crew.composers.map(esc).join(", ")}</div>` : "",
      ].filter(Boolean).join("");
      return rows ? `<div class="detail-section"><h3>Crew</h3><div class="crew-list">${rows}</div></div>` : "";
    }

    function money(n) {
      if (!n) return "";
      if (n >= 1e9) return "$" + (n / 1e9).toFixed(1) + "B";
      if (n >= 1e6) return "$" + Math.round(n / 1e6) + "M";
      return "$" + Number(n).toLocaleString();
    }

    function factsHTML(m) {
      const country = (m.production_countries || []).map((c) => c.name || c).filter(Boolean).join(", ");
      const companies = (m.production_companies || []).map((c) => c.name || c).filter(Boolean).slice(0, 3).join(", ");
      const facts = [
        ["Status", m.status],
        ["Release", m.release_date],
        ["Country", country],
        ["Budget", money(m.budget)],
        ["Revenue", money(m.revenue)],
        ["Studios", companies],
      ].filter(([, v]) => v);
      if (!facts.length) return "";
      return `<div class="detail-section"><h3>Details</h3><div class="facts-grid">${facts.map(([k, v]) => `<div class="fact"><b>${esc(k)}</b><span>${esc(v)}</span></div>`).join("")}</div></div>`;
    }

    function providersHTML(providers, loading) {
      if (loading) return `<div class="detail-section"><h3>Where to watch in India</h3><div class="detail-loading">Loading availability...</div></div>`;
      if (!providers || (!providers.flatrate?.length && !providers.rent?.length && !providers.buy?.length)) {
        return `<div class="detail-section"><h3>Where to watch in India</h3><div class="detail-loading">No India streaming, rent, or buy options found on TMDb for this title.</div></div>`;
      }
      const group = (label, rows) => rows?.length
        ? `<div class="provider-group"><b>${label}</b><div class="provider-row">${rows.map((p) => `<span class="provider">${p.logo_url ? `<img src="${esc(p.logo_url)}" alt="" />` : ""}${esc(p.name)}</span>`).join("")}</div></div>`
        : "";
      const body = [group("Stream", providers.flatrate), group("Rent", providers.rent), group("Buy", providers.buy)].join("");
      return `<div class="detail-section"><h3>Where to watch in India</h3>${body}${providers.link ? `<a class="detail-link secondary" href="${esc(providers.link)}" target="_blank" rel="noreferrer">View all options</a>` : ""}</div>`;
    }

    function recGroupsHTML(groups, loading, fallbackSimilar) {
      if (loading) return `<div class="similar-wrap"><h3>More like this</h3><div class="detail-loading">Loading recommendations...</div></div>`;
      const entries = groups ? Object.values(groups).filter((g) => g.results?.length) : [];
      if (entries.length) {
        return `<div class="similar-wrap"><h3>More like this</h3>${entries.map((g) => `
          <div class="rec-group">
            <div class="rec-title">${esc(g.label)}</div>
            <div class="similar-grid">${g.results.map((s) => miniHTML(s, s.shared_genres != null ? `${s.shared_genres} shared genre${s.shared_genres === 1 ? "" : "s"}` : null)).join("")}</div>
          </div>`).join("")}</div>`;
      }
      const simHTML = fallbackSimilar?.length
        ? fallbackSimilar.map((s) => miniHTML(s, (s.shared_genres || 0) + " shared genre" + (s.shared_genres === 1 ? "" : "s"))).join("")
        : `<p style="color:var(--faint)">No similar titles found.</p>`;
      return `<div class="similar-wrap"><h3>More like this</h3><div class="similar-grid">${simHTML}</div></div>`;
    }

    async function openModal(id) {
      const key = String(id);
      state.modalId = key;
      $("modal").classList.add("open");
      updateScrollLock();
      $("modalContent").innerHTML = `<div style="padding:60px;text-align:center;color:var(--faint)">Loading…</div>`;
      try {
        const m = await cached(movieCache, key, `/api/movies/${id}`);
        let movie = { ...m };
        let similar = null;
        let providers = null;
        let groups = null;
        let extrasLoading = true;
        let providersLoading = true;
        let recLoading = true;
        const rerender = () => {
          if (state.modalId === key) renderModal(movie, { similar, providers, groups, extrasLoading, providersLoading, recLoading });
        };
        rerender();
        cached(extrasCache, key, `/api/movies/${id}/extras`)
          .then((extras) => {
            if (state.modalId !== key) return;
            movie = { ...movie, ...extras };
            extrasLoading = false;
            rerender();
          })
          .catch(() => { extrasLoading = false; rerender(); });
        cached(providerCache, key, `/api/movies/${id}/watch-providers?region=IN`)
          .then((data) => {
            if (state.modalId !== key) return;
            providers = data;
            providersLoading = false;
            rerender();
          })
          .catch(() => { providersLoading = false; rerender(); });
        Promise.all([
          cached(recCache, key, `/api/movies/${id}/recommendations?limit=8`).catch(() => null),
          api(`/api/movies/${id}/similar?limit=8`).catch(() => ({ results: [] })),
        ]).then(([rec, sim]) => {
          if (state.modalId !== key) return;
          groups = rec?.groups || null;
          similar = sim?.results || [];
          recLoading = false;
          rerender();
        }).catch(() => { recLoading = false; rerender(); });
      } catch (e) {
        $("modalContent").innerHTML = `<div style="padding:60px;text-align:center;color:var(--faint)">Couldn't load this title.</div>`;
      }
    }

    function renderModal(m, detail = {}) {
      const { bg, img } = posterLayer(m);
      const lang = m.original_language ? m.original_language.toUpperCase() : "";
      const runtime = m.runtime ? m.runtime + " min" : "";
      const vc = m.vote_count || 0;
      const votes = vc >= 1e6 ? (vc / 1e6).toFixed(1) + "M votes"
        : vc >= 1000 ? Math.round(vc / 1000) + "K votes"
        : vc > 0 ? vc + " votes" : "";
      const metaParts = [
        `<span class="rate">&#9733; ${ratingText(m.rating)}</span>`,
        m.release_year ? `<span>${esc(m.release_year)}</span>` : "",
        runtime ? `<span>${runtime}</span>` : "",
        lang ? `<span>${lang}</span>` : "",
        votes ? `<span class="votes">${votes}</span>` : "",
      ].filter(Boolean).join("");
      const actionLinks = [
        m.trailer_url ? `<a class="detail-link" href="${esc(m.trailer_url)}" target="_blank" rel="noreferrer">Watch trailer</a>` : "",
        m.homepage ? `<a class="detail-link secondary" href="${esc(m.homepage)}" target="_blank" rel="noreferrer">Official site</a>` : "",
      ].filter(Boolean).join("");
      favCandidates.set(m.id, favSnapshot(m));
      const favBtn = state.user
        ? `<button class="list-btn fav-btn ${state.favorites.has(m.id) ? "on" : ""}" data-fav="${m.id}">${state.favorites.has(m.id) ? "♥ In your list" : "♡ Save to list"}</button>`
        : "";
      const tagline = m.tagline ? `<p class="overview"><em>${esc(m.tagline)}</em></p>` : "";
      const cast = m.cast?.length
        ? `<div class="detail-section"><h3>Cast</h3><div class="cast-grid">${m.cast.map(personHTML).join("")}</div></div>`
        : detail.extrasLoading ? `<div class="detail-section"><h3>Cast</h3><div class="detail-loading">Loading cast...</div></div>` : "";
      $("modalContent").innerHTML = `
        <button class="modal-close" id="modalClose">&times;</button>
        <div class="hero">
          <div class="hero-poster" style="${bg}">
            ${img}
            <div class="pscrim"></div>
          </div>
          <div class="hero-info">
            <h2>${esc(m.title)}</h2>
            <div class="hero-meta">${metaParts}</div>
            <div class="gchips">${(m.genres || []).map((g) => `<span>${esc(g)}</span>`).join("")}</div>
            ${tagline}
            <p class="overview">${esc(m.overview || "No overview available.")}</p>
            ${(favBtn || actionLinks) ? `<div class="detail-actions">${favBtn}${actionLinks}</div>` : ""}
          </div>
        </div>
        ${cast}
        ${crewHTML(m.crew, detail.extrasLoading && !m.crew)}
        ${factsHTML(m)}
        ${providersHTML(detail.providers, detail.providersLoading)}
        ${recGroupsHTML(detail.groups, detail.recLoading, detail.similar)}`;
      $("modalClose").addEventListener("click", closeModal);
    }
    function closeModal() { state.modalId = null; $("modal").classList.remove("open"); updateScrollLock(); }
    const isMobile = () => window.matchMedia("(max-width: 600px)").matches;
    function updateScrollLock() {
      document.body.classList.toggle("locked", isMobile() && (state.modalId !== null || state.chatOpen));
    }

    /* ---------------- chat ---------------- */
    function renderChat() {
      const log = $("chatLog");
      let html = "";
      for (const msg of state.chatMessages) {
        html += `<div class="bubble ${msg.role === "user" ? "user" : "bot"}">${msg.role === "user" ? esc(msg.text) : minimal(msg.text)}</div>`;
        if (msg.movies && msg.movies.length) {
          html += `<div class="chat-movies">` + msg.movies.slice(0, 9).map((s) => {
            const { bg, img } = posterLayer(s);
            return `<div class="mini" data-id="${s.id}"><div class="poster" style="${bg}">${img}<div class="mscrim"></div><div class="cm-t">${esc(s.title)}</div></div></div>`;
          }).join("") + `</div>`;
        }
      }
      if (state.typing) html += `<div class="typing"><span></span><span></span><span></span></div>`;
      log.innerHTML = html;
      log.scrollTop = log.scrollHeight;
    }

    async function sendChat(text) {
      state.chatMessages.push({ role: "user", text });
      state.typing = true;
      renderChat();
      try {
        const history = state.chatMessages.map((m) => ({ role: m.role === "user" ? "user" : "assistant", content: m.text }));
        const r = await fetch("/api/chat", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ messages: history, context: chatContext() }),
        });
        state.typing = false;
        if (!r.ok) {
          const err = await r.json().catch(() => ({}));
          state.chatMessages.push({ role: "bot", text: err.detail || "Something went wrong." });
        } else {
          const data = await r.json();
          state.chatMessages.push({ role: "bot", text: data.reply || "(no reply)", movies: data.movies || [] });
        }
      } catch (e) {
        state.typing = false;
        state.chatMessages.push({ role: "bot", text: "Couldn't reach the companion. Is the server running?" });
      }
      renderChat();
    }

    function chatContext() {
      return {
        mode: state.forYou ? "personalized" : "browse",
        active_collection: state.activeCollection,
        genres: state.genres.map(id => state.allGenres.find(g => g.id === id)?.name).filter(Boolean),
        sort_by: state.sortBy,
        visible_titles: visibleMovies().slice(0, 8).map(m => ({ title: m.title, year: m.release_year, rating: m.rating, genres: m.genres })),
        taste: state.taste,
      };
    }

    /* ---------------- filters / events ---------------- */
    function resetFilters() {
      state.genres = []; state.genreMatch = "any"; state.yearMin = ""; state.yearMax = "";
      state.ratingMin = ""; state.language = ""; state.runtimeMax = ""; state.sortBy = "popularity"; state.activeCollection = null; state.query = "";
      resetBrowsePage();
      $("yearMin").value = ""; $("yearMax").value = ""; $("ratingMin").value = "";
      $("languageFilter").value = ""; $("runtimeMax").value = ""; $("sortBy").value = "popularity"; $("search").value = "";
      renderGenreTrigger(); renderGenrePopover(); renderCollections(); browseFetch();
    }

    $("search").addEventListener("input", (e) => {
      state.query = e.target.value;
      resetBrowsePage();
      state.forYou = false;
      state.viewingList = false;
      renderTasteControls();
      renderCollections();
      scheduleFetch(300);
    });
    $("homeLogo").addEventListener("click", () => {
      history.pushState(null, "", "/");
      window.scrollTo({ top: 0, behavior: "smooth" });
      resetFilters();
    });
    $("yearMin").addEventListener("input", (e) => { state.yearMin = e.target.value; resetBrowsePage(); state.forYou = false; state.viewingList = false; renderTasteControls(); renderCollections(); scheduleFetch(350); });
    $("yearMax").addEventListener("input", (e) => { state.yearMax = e.target.value; resetBrowsePage(); state.forYou = false; state.viewingList = false; renderTasteControls(); renderCollections(); scheduleFetch(350); });
    $("ratingMin").addEventListener("input", (e) => { state.ratingMin = e.target.value; resetBrowsePage(); state.forYou = false; state.viewingList = false; renderTasteControls(); renderCollections(); scheduleFetch(350); });
    $("languageFilter").addEventListener("change", (e) => { state.language = e.target.value; restartBrowseFetch(); });
    $("runtimeMax").addEventListener("change", (e) => { state.runtimeMax = e.target.value; restartBrowseFetch(); });
    $("sortBy").addEventListener("change", (e) => { state.sortBy = e.target.value; restartBrowseFetch(); });
    $("reset").addEventListener("click", resetFilters);
    $("genreTrigger").addEventListener("click", () => { state.genreMenuOpen = !state.genreMenuOpen; renderGenrePopover(); });
    $("tasteToggle").addEventListener("click", () => {
      if (state.forYou) {
        leaveForYou();
        return;
      }
      state.forYou = true;
      renderTasteControls();
      runTasteMatch();
    });
    $("runTaste").addEventListener("click", runTasteMatch);
    $("clearTaste").addEventListener("click", leaveForYou);
    $("anchorSearch").addEventListener("input", (e) => {
      clearTimeout(anchorTimer);
      anchorTimer = setTimeout(() => searchAnchorMovies(e.target.value), 250);
    });
    $("anchorSearch").addEventListener("keydown", (e) => {
      if (e.key !== "Enter") return;
      e.preventDefault();
      addFirstAnchorCandidate();
    });
    $("anchorAdd").addEventListener("click", addFirstAnchorCandidate);
    $("anchorSuggestions").addEventListener("click", (e) => {
      const btn = e.target.closest("[data-anchor-id]");
      if (!btn) return;
      const movie = state.taste.anchorSuggestions.find(m => String(m.id) === btn.dataset.anchorId);
      addAnchorMovie(movie);
    });
    $("anchorList").addEventListener("click", (e) => {
      const btn = e.target.closest("[data-anchor-remove]");
      if (btn) removeAnchorMovie(Number(btn.dataset.anchorRemove));
    });
    document.querySelectorAll(".vibe-chip").forEach(btn => {
      btn.addEventListener("click", () => {
        if (state.tasteLoading) return;
        const vibe = btn.dataset.vibe;
        state.taste.vibes = state.taste.vibes.includes(vibe) ? state.taste.vibes.filter(v => v !== vibe) : state.taste.vibes.concat([vibe]);
        renderTasteControls();
        scheduleTasteMatch();
      });
    });
    ["tasteEra", "tasteType", "tasteLanguage", "tasteRuntime", "tasteZeitgeist", "ratingFlex"].forEach(id => {
      $(id).addEventListener("change", () => {
        state.taste.era = $("tasteEra").value;
        state.taste.movie_type = $("tasteType").value;
        state.taste.language_scope = $("tasteLanguage").value;
        state.taste.runtime = $("tasteRuntime").value;
        state.taste.zeitgeist = $("tasteZeitgeist").value;
        state.taste.rating_flexibility = Number($("ratingFlex").value);
        scheduleTasteMatch();
      });
    });

    // Delegated click for any poster card / mini (grid, modal, chat) -> open detail.
    document.addEventListener("click", (e) => {
      const favBtn = e.target.closest(".fav-btn");
      if (favBtn) { e.preventDefault(); e.stopPropagation(); toggleFavorite(favBtn.dataset.fav); return; }
      const tile = e.target.closest("[data-id]");
      if (tile) { openModal(Number(tile.dataset.id)); return; }
      if (e.target === $("modal")) closeModal();
    });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModal(); });

    // Chat
    $("fab").addEventListener("click", () => {
      state.chatOpen = true;
      $("chatPanel").classList.add("open");
      updateScrollLock();
      if (!state.chatMessages.length) {
        state.chatMessages.push({ role: "bot", text: "Hi! Tell me what you're in the mood for \u2014 a genre, a vibe, or a movie you love \u2014 and I'll find something for you." });
      }
      renderChat();
      $("chatInput").focus();
    });
    $("chatClose").addEventListener("click", () => { state.chatOpen = false; $("chatPanel").classList.remove("open"); updateScrollLock(); });
    $("chatForm").addEventListener("submit", (e) => {
      e.preventDefault();
      const text = $("chatInput").value.trim();
      if (!text) return;
      $("chatInput").value = "";
      sendChat(text);
    });
    $("chatSuggestions").addEventListener("click", (e) => {
      if (e.target.tagName !== "BUTTON") return;
      $("chatInput").value = e.target.textContent;
      sendChat(e.target.textContent);
    });

    /* ---------------- accounts ---------------- */
    const TOKEN_KEY = "moviedb_token";
    const getToken = () => localStorage.getItem(TOKEN_KEY) || "";
    const setToken = (t) => t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY);
    function authedFetch(path, opts = {}) {
      const headers = Object.assign({}, opts.headers, { Authorization: "Bearer " + getToken() });
      return fetch(path, Object.assign({}, opts, { headers }));
    }

    function renderAccount() {
      const el = $("account");
      if (!state.accountsEnabled) { el.innerHTML = ""; }
      else if (state.user) {
        el.innerHTML = `<span class="account-email" title="${esc(state.user.email)}">${esc(state.user.email)}</span><button class="account-btn" id="signOutBtn">Sign out</button>`;
        $("signOutBtn").addEventListener("click", signOut);
      } else {
        el.innerHTML = `<button class="account-btn" id="signInBtn">Sign in</button>`;
        $("signInBtn").addEventListener("click", () => openAuth("login"));
      }
      const loggedIn = !!state.user;
      $("saveTaste").hidden = !loggedIn;
      $("loadTaste").hidden = !loggedIn;
    }

    function signOut() {
      setToken(""); state.user = null;
      state.favorites = new Set(); state.favoritesList = []; state.viewingList = false;
      renderAccount(); renderCollections(); renderGrid();
    }

    let authMode = "login";
    function renderAuthMode() {
      const signup = authMode === "signup";
      $("authTitle").textContent = signup ? "Create account" : "Sign in";
      $("authSubmit").textContent = signup ? "Create account" : "Sign in";
      $("authToggleText").textContent = signup ? "Already have an account?" : "New here?";
      $("authToggle").textContent = signup ? "Sign in" : "Create an account";
      $("authPassword").setAttribute("autocomplete", signup ? "new-password" : "current-password");
    }
    function openAuth(mode) {
      authMode = mode;
      $("authError").textContent = ""; $("authEmail").value = ""; $("authPassword").value = "";
      renderAuthMode();
      $("authBackdrop").classList.add("open");
      $("authEmail").focus();
    }
    function closeAuth() { $("authBackdrop").classList.remove("open"); }

    $("authToggle").addEventListener("click", () => { authMode = authMode === "signup" ? "login" : "signup"; $("authError").textContent = ""; renderAuthMode(); });
    $("authClose").addEventListener("click", closeAuth);
    $("authBackdrop").addEventListener("click", (e) => { if (e.target === $("authBackdrop")) closeAuth(); });
    $("authForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      const email = $("authEmail").value.trim();
      const password = $("authPassword").value;
      $("authError").textContent = "";
      $("authSubmit").disabled = true;
      try {
        const r = await fetch("/api/auth/" + (authMode === "signup" ? "signup" : "login"), {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, password }),
        });
        const data = await r.json().catch(() => ({}));
        if (!r.ok) { $("authError").textContent = data.detail || "Something went wrong."; return; }
        setToken(data.token);
        state.user = { email: data.email };
        closeAuth();
        renderAccount();
        loadTasteProfile(true);
        loadFavorites();
      } catch (err) {
        $("authError").textContent = "Couldn't reach the server.";
      } finally {
        $("authSubmit").disabled = false;
      }
    });

    function persistableTaste() {
      const t = state.taste;
      return {
        liked_movies: t.liked_movies, vibes: t.vibes, rating_flexibility: t.rating_flexibility,
        language_scope: t.language_scope, era: t.era, runtime: t.runtime,
        movie_type: t.movie_type, zeitgeist: t.zeitgeist,
      };
    }
    async function saveTasteProfile() {
      if (!state.user) return;
      $("tasteStatus").textContent = "Saving to your account...";
      try {
        const r = await authedFetch("/api/taste-profile", {
          method: "PUT", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ profile: persistableTaste() }),
        });
        if (r.status === 401) { signOut(); $("tasteStatus").textContent = "Session expired — sign in again."; return; }
        $("tasteStatus").textContent = r.ok ? "Saved to your account ✓" : "Couldn't save right now.";
      } catch (e) { $("tasteStatus").textContent = "Couldn't save right now."; }
    }
    async function loadTasteProfile(silent) {
      if (!state.user) return;
      try {
        const r = await authedFetch("/api/taste-profile");
        if (r.status === 401) { signOut(); return; }
        if (!r.ok) return;
        const data = await r.json();
        if (data.profile) {
          Object.assign(state.taste, data.profile);
          renderTasteControls();
          if (!silent) $("tasteStatus").textContent = "Loaded your saved profile.";
        } else if (!silent) {
          $("tasteStatus").textContent = "No saved profile yet — set signals and Save.";
        }
      } catch (e) { /* ignore */ }
    }
    $("saveTaste").addEventListener("click", saveTasteProfile);
    $("loadTaste").addEventListener("click", () => loadTasteProfile(false));

    /* ---------------- favorites ---------------- */
    function refreshHearts(id) {
      const on = state.favorites.has(id);
      document.querySelectorAll(`.fav-btn[data-fav="${id}"]`).forEach((b) => {
        b.classList.toggle("on", on);
        b.textContent = b.classList.contains("list-btn")
          ? (on ? "♥ In your list" : "♡ Save to list")
          : (on ? "♥" : "♡");
      });
    }

    async function toggleFavorite(id) {
      id = Number(id);
      if (!state.user) return;
      const wasFav = state.favorites.has(id);
      if (wasFav) {
        state.favorites.delete(id);
        state.favoritesList = state.favoritesList.filter((m) => m.id !== id);
      } else {
        state.favorites.add(id);
        const snap = favCandidates.get(id);
        if (snap && !state.favoritesList.some((m) => m.id === id)) state.favoritesList.unshift(snap);
      }
      refreshHearts(id);
      renderCollections();
      if (state.viewingList) renderGrid();
      if (state.forYou && !state.tasteLoading) runTasteMatch();
      try {
        const r = wasFav
          ? await authedFetch(`/api/favorites/${id}`, { method: "DELETE" })
          : await authedFetch("/api/favorites", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ movie: favCandidates.get(id) || { id } }) });
        if (r && r.status === 401) signOut();
      } catch (e) { /* keep optimistic state */ }
    }

    async function loadFavorites() {
      if (!state.user) { state.favorites = new Set(); state.favoritesList = []; return; }
      try {
        const r = await authedFetch("/api/favorites");
        if (r.status === 401) { signOut(); return; }
        if (!r.ok) return;
        const data = await r.json();
        state.favoritesList = data.results || [];
        state.favorites = new Set(state.favoritesList.map((m) => m.id));
        renderCollections();
        renderGrid();
        if (state.forYou && !state.tasteLoading) runTasteMatch();
      } catch (e) { /* ignore */ }
    }

    /* ---------------- init ---------------- */
    async function init() {
      try { state.allGenres = await api("/api/genres"); } catch (e) { state.allGenres = []; }
      renderGenreTrigger();
      try { state.collections = await api("/api/collections"); } catch (e) { state.collections = []; }
      renderCollections();
      renderTasteControls();
      try { const cfg = await api("/api/config"); state.accountsEnabled = !!cfg.accounts_enabled; } catch (e) {}
      if (state.accountsEnabled && getToken()) {
        try {
          const me = await authedFetch("/api/auth/me");
          if (me.ok) { state.user = await me.json(); } else { setToken(""); }
        } catch (e) {}
      }
      renderAccount();
      if (state.user) loadTasteProfile(true);
      await fetchMovies();
      if (state.user) loadFavorites();
    }
    init();

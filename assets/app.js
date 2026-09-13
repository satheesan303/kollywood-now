/* Kollywood Now — front end.
   Talks to the local aggregator (/api/news) and falls back to the
   snapshot in data/news.json when the server isn't running. */

(() => {
  "use strict";

  const PAGE_SIZE = 18;
  const AUTO_REFRESH_MS = 10 * 60 * 1000;
  const TAMIL_RANGE = /[஀-௿]/;

  const CATEGORIES = [
    ["all", "Home"],
    ["buzz", "Top News"],
    ["box-office", "Box Office"],
    ["trailers", "Trailers"],
    ["ott", "OTT"],
    ["reviews", "Reviews"],
    ["music", "Music"],
    ["casting", "Casting"],
  ];

  // Portal homepage sections, in display order.
  //   feature = one large lead item + a short list (used once, up top)
  //   cards   = editorial 3-across photo cards
  //   rows    = two-column "in brief" list, numbered
  // A section with fewer than `min` matching stories is skipped.
  const SECTIONS = [
    { key: "buzz", label: "Top News", kind: "feature", count: 5, min: 3 },
    { key: "box-office", label: "Box Office", kind: "cards", count: 6, min: 3 },
    { key: "trailers", label: "Trailers &amp; First Looks", kind: "cards", count: 6, min: 3 },
    { key: "ott", label: "OTT &amp; Streaming", kind: "rows", count: 6, min: 3 },
    { key: "reviews", label: "Reviews", kind: "rows", count: 4, min: 3 },
    { key: "music", label: "Music", kind: "rows", count: 4, min: 3 },
    { key: "casting", label: "Casting &amp; Shoots", kind: "rows", count: 6, min: 3 },
  ];

  const state = {
    articles: [],
    trending: [],
    feeds: [],
    generated: "",
    category: "all",
    source: "",
    sort: "new",
    query: "",
    shown: PAGE_SIZE,
    heroUrls: [],
  };

  const $ = (sel) => document.querySelector(sel);
  const el = {
    hero: $("#hero"), feed: $("#feed"), pills: $("#pills"), ticker: $("#ticker"),
    trending: $("#trending"), bars: $("#source-bars"), health: $("#health"),
    generated: $("#generated"), sourceFilter: $("#source-filter"), sort: $("#sort"),
    search: $("#search"), more: $("#more"), resultLine: $("#result-line"),
    refresh: $("#refresh"), theme: $("#theme"), footerSources: $("#footer-sources"),
    sections: $("#sections"), toolbar: $("#toolbar"), backHome: $("#back-home"),
    today: $("#today"), tally: $("#tally"), feedCount: $("#feed-count"),
    footerNav: $("#footer-nav"), footerTally: $("#footer-tally"),
    footerHealthNote: $("#footer-health-note"),
  };

  /* ---------------------------------------------------------------- utils */

  const escapeHtml = (str = "") =>
    str.replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));

  function highlight(text, query) {
    const safe = escapeHtml(text);
    if (!query) return safe;
    const needle = query.trim().replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    if (!needle) return safe;
    return safe.replace(new RegExp(`(${needle})`, "ig"), "<mark>$1</mark>");
  }

  function timeAgo(iso) {
    if (!iso) return "recently";
    const diff = (Date.now() - new Date(iso).getTime()) / 1000;
    if (Number.isNaN(diff)) return "recently";
    if (diff < 90) return "just now";
    if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.round(diff / 3600)}h ago`;
    if (diff < 604800) return `${Math.round(diff / 86400)}d ago`;
    return new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short" });
  }

  const CATEGORY_LABEL = Object.fromEntries(CATEGORIES);
  const isTamil = (text) => TAMIL_RANGE.test(text || "");
  const tclass = (article) => (isTamil(article.title) ? " tamil-title" : "");

  /* Deterministic poster tile for the many feeds that ship no image. */
  function posterTile(article) {
    let hash = 0;
    for (const ch of article.title) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
    const hue = hash % 360;
    const initials = article.title
      .replace(/[^A-Za-z ]/g, " ").trim().split(/\s+/)
      .slice(0, 2).map((w) => w[0]).join("").toUpperCase() || "KN";
    const bg = `linear-gradient(135deg, hsl(${hue} 55% 30%), hsl(${(hue + 48) % 360} 60% 16%))`;
    return `<div class="tile" style="background:${bg}"><span>${escapeHtml(initials)}</span></div>`;
  }

  /* The tile always renders first so a photo that fails to load (hotlink
     blocks, dead link) degrades to the tile instead of an empty box. */
  function art(article) {
    const tile = posterTile(article);
    if (!article.image) return tile;
    return tile + `<img src="${escapeHtml(article.image)}" alt="" loading="lazy" decoding="async" onerror="this.remove()">`;
  }

  /* -------------------------------------------------------- reveal-on-scroll */

  let revealObserver = null;
  function observeReveals(root) {
    if (!revealObserver) {
      revealObserver = ("IntersectionObserver" in window)
        ? new IntersectionObserver((entries) => {
            for (const entry of entries) {
              if (entry.isIntersecting) {
                entry.target.classList.add("in");
                revealObserver.unobserve(entry.target);
              }
            }
          }, { rootMargin: "0px 0px -8% 0px", threshold: 0.05 })
        : null;
    }
    const targets = root.querySelectorAll(".reveal");
    if (!revealObserver) { targets.forEach((t) => t.classList.add("in")); return; }
    targets.forEach((t) => revealObserver.observe(t));
  }

  /* ------------------------------------------------------------- rendering */

  function cardHtml(article) {
    const tag = CATEGORY_LABEL[article.category] || "Buzz";
    return `
      <article class="card">
        <a class="art" href="${escapeHtml(article.url)}" target="_blank" rel="noopener noreferrer"
           aria-label="${escapeHtml(article.title)}">
          <span class="tag">${escapeHtml(tag)}</span>
          ${art(article)}
        </a>
        <a href="${escapeHtml(article.url)}" target="_blank" rel="noopener noreferrer" class="${tclass(article).trim()}">
          <h3>${highlight(article.title, state.query)}</h3>
        </a>
        ${article.summary ? `<p>${highlight(article.summary, state.query)}</p>` : ""}
        <div class="meta">
          <span class="src">${escapeHtml(article.source)}</span>
          <span class="dot"></span>
          <span>${timeAgo(article.published)}</span>
        </div>
      </article>`;
  }

  function sectionCardHtml(article) {
    return `
      <a class="pcard${tclass(article)}" href="${escapeHtml(article.url)}" target="_blank" rel="noopener noreferrer">
        <div class="art">${art(article)}</div>
        <h3>${escapeHtml(article.title)}</h3>
        <div class="card-meta">
          <span class="src">${escapeHtml(article.source)}</span>
          <span class="dot"></span><span>${timeAgo(article.published)}</span>
        </div>
      </a>`;
  }

  function sectionRowHtml(article, index) {
    return `
      <a class="drow${tclass(article)}" href="${escapeHtml(article.url)}" target="_blank" rel="noopener noreferrer">
        <span class="num">${index}</span>
        <div class="art">${art(article)}</div>
        <div>
          <h3>${escapeHtml(article.title)}</h3>
          <div class="card-meta">
            <span class="src">${escapeHtml(article.source)}</span>
            <span class="dot"></span><span>${timeAgo(article.published)}</span>
          </div>
        </div>
      </a>`;
  }

  function featureModuleHtml(items) {
    const [lead, ...rest] = items;
    const list = rest.slice(0, 4).map((a) => `
      <a class="flist-item${tclass(a)}" href="${escapeHtml(a.url)}" target="_blank" rel="noopener noreferrer">
        <div class="art">${art(a)}</div>
        <div>
          <h3>${escapeHtml(a.title)}</h3>
          <div class="card-meta">
            <span class="src">${escapeHtml(a.source)}</span>
            <span class="dot"></span><span>${timeAgo(a.published)}</span>
          </div>
        </div>
      </a>`).join("");
    return `
      <div class="feature-module">
        <a class="feature-main${tclass(lead)}" href="${escapeHtml(lead.url)}" target="_blank" rel="noopener noreferrer">
          <div class="art">${art(lead)}</div>
          <h3>${escapeHtml(lead.title)}</h3>
          ${lead.summary ? `<p>${escapeHtml(lead.summary)}</p>` : ""}
          <div class="card-meta">
            <span class="src">${escapeHtml(lead.source)}</span>
            <span class="dot"></span><span>${timeAgo(lead.published)}</span>
          </div>
        </a>
        <div class="feature-list">${list}</div>
      </div>`;
  }

  function adSlot(id, size) {
    return `
      <div class="ad-slot ad-infeed" id="${id}" data-ad-size="${size}">
        <span class="ad-eyebrow">Advertisement</span>
        <span class="ad-size">${size.replace("x", " × ")} — your banner here</span>
      </div>`;
  }

  /* Editorial homepage: category-grouped blocks. Only shown when nothing is
     filtered — the moment a pill, source or search is applied we drop to
     the flat grid instead, so every existing filter keeps working exactly
     as it did. */
  function renderSections(articles, usedUrls) {
    const used = new Set(usedUrls);
    const blocks = [];

    for (const sec of SECTIONS) {
      const pool = articles.filter((a) => a.category === sec.key && !used.has(a.url));
      // Card and feature layouts are image-led, so float photographed
      // stories up (sort is stable, so freshness order survives within
      // each group). The text-forward "rows" list doesn't need it.
      const ordered = sec.kind === "rows"
        ? pool
        : [...pool].sort((a, b) => (a.image ? 0 : 1) - (b.image ? 0 : 1));
      const items = ordered.slice(0, sec.count);
      if (items.length < sec.min) continue;
      for (const a of items) used.add(a.url);

      const total = articles.filter((a) => a.category === sec.key).length;
      let body;
      if (sec.kind === "feature") {
        body = featureModuleHtml(items);
      } else if (sec.kind === "cards") {
        body = `<div class="section-cards">${items.map(sectionCardHtml).join("")}</div>`;
      } else {
        body = `<div class="section-rows">${items.map((a, i) => sectionRowHtml(a, i + 1)).join("")}</div>`;
      }

      blocks.push(`
        <div class="section-block reveal">
          <div class="section-head">
            <div class="title">${sec.label}</div>
            <div class="count">${total} stories &rarr;</div>
          </div>
          ${body}
        </div>`);
    }

    // Two in-feed ad breaks, spaced through the sections rather than stacked.
    if (blocks.length > 1) blocks.splice(1, 0, adSlot("ad-infeed-1", "728x90"));
    if (blocks.length > 4) blocks.splice(4, 0, adSlot("ad-infeed-2", "728x90"));

    el.sections.innerHTML = blocks.join("");
    observeReveals(el.sections);
  }

  /* The lead slot is a dominant 16:10 image, so a story without a photo
     leaves the page looking broken. Reach past the very newest item for the
     freshest *photographed* one, staying inside the recent window. */
  function pickHero(list) {
    if (!list.length) return [];
    const recent = list.slice(0, 14);
    const lead = recent.find((a) => a.image) || list[0];
    const rest = list.filter((a) => a.url !== lead.url).slice(0, 4);
    return [lead, ...rest];
  }

  function renderHero(list) {
    const [lead, ...rest] = list;
    if (!lead) { el.hero.innerHTML = ""; return; }
    const tag = CATEGORY_LABEL[lead.category] || "Buzz";
    el.hero.innerHTML = `
      <a class="hero-lead${tclass(lead)}" href="${escapeHtml(lead.url)}" target="_blank" rel="noopener noreferrer">
        <div class="art">${art(lead)}</div>
        <span class="cat-eyebrow">${escapeHtml(tag)} &middot; Lead story</span>
        <h2>${escapeHtml(lead.title)}</h2>
        ${lead.summary ? `<p>${escapeHtml(lead.summary)}</p>` : ""}
        <div class="meta">
          <span class="src">${escapeHtml(lead.source)}</span>
          <span class="dot"></span><span>${timeAgo(lead.published)}</span>
        </div>
      </a>
      <div class="hero-side">
        <div class="head">Next Up</div>
        ${rest.map((a) => `
          <a class="mini${tclass(a)}" href="${escapeHtml(a.url)}" target="_blank" rel="noopener noreferrer">
            <div class="thumb">${art(a)}</div>
            <div>
              <div class="card-meta">
                <span class="src">${escapeHtml(a.source)}</span>
                <span class="dot"></span><span>${timeAgo(a.published)}</span>
              </div>
              <h3>${escapeHtml(a.title)}</h3>
            </div>
          </a>`).join("")}
      </div>`;
  }

  function renderTicker(list) {
    const line = list.slice(0, 14)
      .map((a) => `<span><b>${escapeHtml(a.source)}</b>${escapeHtml(a.title)}</span>`)
      .join("");
    el.ticker.innerHTML = line + line;   // duplicated so the loop is seamless
  }

  function renderPills(base) {
    const counts = { all: base.length };
    for (const a of base) counts[a.category] = (counts[a.category] || 0) + 1;
    el.pills.innerHTML = CATEGORIES
      .filter(([key]) => key === "all" || counts[key])
      .map(([key, label]) => `
        <button class="navtab" data-cat="${key}" aria-pressed="${state.category === key}">
          ${label}
        </button>`).join("");

    el.footerNav.innerHTML = CATEGORIES
      .filter(([key]) => key !== "all" && counts[key])
      .map(([key, label]) => `<a href="#" data-cat="${key}">${label}</a>`).join("");
  }

  function renderSidebar(base) {
    el.trending.innerHTML = state.trending.length
      ? state.trending.slice(0, 8).map((t, i) => `
          <button class="trend-row" data-term="${escapeHtml(t.term)}">
            <span class="n">${i + 1}</span>
            <span class="term">${escapeHtml(t.term)}</span>
            <span class="count">${t.count} stories</span>
          </button>`).join("")
      : `<span class="panel-note">Not enough headlines yet.</span>`;

    const counts = {};
    for (const a of base) counts[a.source] = (counts[a.source] || 0) + 1;
    const top = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 6);
    const max = top.length ? top[0][1] : 1;
    el.bars.innerHTML = top.map(([name, n]) => `
      <div class="mix-row" data-source="${escapeHtml(name)}">
        <div class="row"><span>${escapeHtml(name)}</span><b>${n}</b></div>
        <div class="track"><div class="fill" style="width:${Math.round((n / max) * 100)}%"></div></div>
      </div>`).join("");

    el.health.innerHTML = state.feeds.map((f) => {
      const query = decodeURIComponent((f.url.match(/[?&]q=([^&]+)/) || [, ""])[1] || "")
        .replace(/\+/g, " ").replace(/when:\d+d/, "").replace(/["()]/g, "").trim();
      const label = query ? `${f.name} · ${query.slice(0, 20)}…` : f.name;
      return `<li><span class="led ${f.ok ? "" : "bad"}"></span>
                <span class="name" title="${escapeHtml(f.url)}">${escapeHtml(label)}</span>
                <span class="n">${f.ok ? f.items : "down"}</span></li>`;
    }).join("");

    const outlets = [...new Set(base.map((a) => a.source))].sort();
    el.footerSources.innerHTML = outlets
      .slice(0, 10)
      .map((s) => `<span>${escapeHtml(s)}</span>`).join("");

    if (state.generated) {
      el.generated.textContent = `refreshed ${timeAgo(state.generated)}`;
    }
    const healthy = state.feeds.filter((f) => f.ok).length;
    el.feedCount.textContent = `${healthy}/${state.feeds.length} live`;
    el.footerHealthNote.textContent = `${healthy}/${state.feeds.length} feeds healthy`;
  }

  /* -------------------------------------------------------------- filtering */

  function visible() {
    const query = state.query.trim().toLowerCase();
    let list = state.articles.filter((a) => {
      if (state.category !== "all" && a.category !== state.category) return false;
      if (state.source && a.source !== state.source) return false;
      if (query && !(`${a.title} ${a.summary} ${a.source}`.toLowerCase().includes(query))) return false;
      return true;
    });
    if (state.sort === "old") list = [...list].reverse();
    else if (state.sort === "source") {
      list = [...list].sort((a, b) => a.source.localeCompare(b.source) || b.ts - a.ts);
    }
    return list;
  }

  function render() {
    const base = state.articles.filter((a) => !state.source || a.source === state.source);
    renderPills(base);
    renderSidebar(state.articles);

    const pristine = state.category === "all" && !state.source && !state.query && state.sort === "new";

    // A filtered view is a results page, not the homepage: the lead story and
    // its rail belong to the homepage only, and leaving them up made a tab
    // click look like nothing had happened.
    el.hero.hidden = !pristine;
    el.sections.hidden = !pristine;
    el.toolbar.hidden = pristine;
    el.resultLine.hidden = pristine;
    el.feed.hidden = pristine;

    if (pristine) {
      renderSections(state.articles, state.heroUrls);
      el.more.hidden = true;
      return;
    }

    const list = visible();
    const slice = list.slice(0, state.shown);

    el.feed.innerHTML = slice.length
      ? slice.map(cardHtml).join("")
      : `<div class="empty"><strong>No stories match that.</strong>
           Try a different name, or clear the filters to see all ${state.articles.length} headlines.</div>`;

    el.more.hidden = list.length <= state.shown;
    el.more.textContent = `Load more stories (${Math.max(list.length - state.shown, 0)} left)`;

    el.resultLine.innerHTML = `Showing <b>${slice.length}</b> of <b>${list.length}</b> matching stories`;
  }

  function resetFilters() {
    state.category = "all";
    state.source = "";
    state.query = "";
    state.sort = "new";
    state.shown = PAGE_SIZE;
    el.search.value = "";
    el.sourceFilter.value = "";
    el.sort.value = "new";
    render();
  }

  /* ------------------------------------------------------------------ data */

  async function load(force = false) {
    el.refresh.setAttribute("aria-busy", "true");
    const endpoints = force
      ? ["/api/refresh", "/api/news", "data/news.json"]
      : ["/api/news", "data/news.json"];

    for (const url of endpoints) {
      try {
        const res = await fetch(url, { cache: "no-store" });
        if (!res.ok) continue;
        const data = await res.json();
        if (!data.articles || !data.articles.length) continue;

        state.articles = data.articles;
        state.trending = data.trending || [];
        state.feeds = data.feeds || [];
        state.generated = data.generated || "";
        state.shown = PAGE_SIZE;

        const heroStories = pickHero(state.articles);
        state.heroUrls = heroStories.map((a) => a.url);
        renderHero(heroStories);
        renderTicker(state.articles);
        observeReveals(document);

        const sources = [...new Set(state.articles.map((a) => a.source))].sort();
        el.sourceFilter.innerHTML = `<option value="">All sources (${sources.length})</option>` +
          sources.map((s) => `<option value="${escapeHtml(s)}">${escapeHtml(s)}</option>`).join("");
        el.sourceFilter.value = state.source;

        const outlets = new Set(state.articles.map((a) => a.source)).size;
        el.tally.textContent = `${state.articles.length} stories · ${outlets} outlets`;
        el.footerTally.textContent = `${state.articles.length} stories · ${outlets} outlets`;
        el.today.textContent = new Date().toLocaleDateString("en-IN", {
          weekday: "long", day: "numeric", month: "long",
        });

        render();
        el.refresh.removeAttribute("aria-busy");
        return;
      } catch (err) { /* try the next endpoint */ }
    }

    el.refresh.removeAttribute("aria-busy");
    el.hero.innerHTML = "";
    el.sections.innerHTML = "";
    el.feed.hidden = false;
    el.feed.innerHTML = `<div class="empty">
        <strong>Couldn't reach the feeds.</strong>
        Start the aggregator with <code>python server.py</code> and open
        <code>http://localhost:8080</code>, then hit Refresh.
      </div>`;
  }

  /* --------------------------------------------------------------- events */

  /* Bring the results under the sticky nav rather than to the absolute top,
     where the masthead and leaderboard would push them past the fold. */
  function scrollToTop() {
    requestAnimationFrame(() => window.scrollTo({ top: 0, behavior: "auto" }));
  }

  function scrollToResults() {
    const top = el.toolbar.getBoundingClientRect().top + window.scrollY - 60;
    window.scrollTo({ top: Math.max(top, 0), behavior: "smooth" });
  }

  function setCategory(cat) {
    state.category = cat;
    state.shown = PAGE_SIZE;
    render();
    if (cat === "all") scrollToTop();
    else scrollToResults();
  }

  el.pills.addEventListener("click", (e) => {
    const button = e.target.closest(".navtab");
    if (!button) return;
    setCategory(button.dataset.cat);
  });

  // Clicking a section's "N stories →" jumps into that filtered view too.
  el.sections.addEventListener("click", (e) => {
    const link = e.target.closest(".count");
    if (!link) return;
    const bar = link.closest(".section-block");
    const title = bar.querySelector(".title").textContent.trim();
    const match = CATEGORIES.find(([, label]) => title.toLowerCase().startsWith(label.toLowerCase()));
    if (match) { e.preventDefault(); setCategory(match[0]); }
  });

  el.footerNav.addEventListener("click", (e) => {
    const a = e.target.closest("a[data-cat]");
    if (!a) return;
    e.preventDefault();
    setCategory(a.dataset.cat);
  });

  el.backHome.addEventListener("click", () => {
    resetFilters();
    scrollToTop();
  });

  el.trending.addEventListener("click", (e) => {
    const row = e.target.closest(".trend-row");
    if (!row) return;
    el.search.value = row.dataset.term;
    state.query = row.dataset.term;
    state.shown = PAGE_SIZE;
    render();
    scrollToResults();
  });

  el.bars.addEventListener("click", (e) => {
    const row = e.target.closest(".mix-row");
    if (!row) return;
    state.source = state.source === row.dataset.source ? "" : row.dataset.source;
    el.sourceFilter.value = state.source;
    state.shown = PAGE_SIZE;
    render();
  });

  let searchTimer;
  el.search.addEventListener("input", (e) => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      state.query = e.target.value;
      state.shown = PAGE_SIZE;
      render();
    }, 160);
  });

  el.sourceFilter.addEventListener("change", (e) => {
    state.source = e.target.value;
    state.shown = PAGE_SIZE;
    render();
  });

  el.sort.addEventListener("change", (e) => {
    state.sort = e.target.value;
    render();
  });

  el.more.addEventListener("click", () => {
    state.shown += PAGE_SIZE;
    render();
  });

  el.refresh.addEventListener("click", () => load(true));

  el.theme.addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("kn-theme", next); } catch (err) { /* private mode */ }
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "/" && document.activeElement !== el.search) {
      e.preventDefault();
      el.search.focus();
    }
    if (e.key === "Escape" && document.activeElement === el.search) {
      el.search.value = "";
      state.query = "";
      render();
      el.search.blur();
    }
  });

  try {
    const saved = localStorage.getItem("kn-theme");
    if (saved) document.documentElement.dataset.theme = saved;
  } catch (err) { /* private mode */ }

  load();
  setInterval(() => load(true), AUTO_REFRESH_MS);
})();

# Kollywood Now

A Tamil film-industry news site that pulls live headlines from dozens of outlets,
merges them, removes duplicates and puts them on one page.

No frameworks, no `npm install`, no API keys — just Python's standard library.

## Run it

```bash
python server.py
```

Then open <http://localhost:8080>. On Windows you can double-click **start.bat**,
which launches the server and opens the browser for you.

Other options:

```bash
python server.py --port 9000   # different port
python server.py --snapshot    # refresh data/news.json and exit (no server)
```

## How the news gets here

`data/sources.json` lists the feeds. Two kinds:

| Kind | Examples | Images? |
| --- | --- | --- |
| Publisher RSS | News18 Tamil, News18 South, Cinema Express, The Hindu, Hindustan Times, Indian Express, Filmibeat Tamil, DT Next, Times of India | yes, in the feed |
| Google News searches | seven topic queries — Kollywood, reviews, box office, star news, teasers, OTT | no |

Publisher feeds carry the article photo, so they are weighted heavily. The
Google News queries add breadth of outlets — each result keeps its own
publisher, pulling in Sacnilk, Koimoi, NDTV, Moneycontrol, WION and others —
but their links are opaque redirects with no readable page, so those stories
have no photo and are capped lower.

For every item the server then:

1. pulls out title, link, summary, image, publish time;
2. drops anything older than 21 days;
3. filters out other film industries — a headline about a Malayalam, Telugu or
   Kannada release with no Tamil marker is discarded;
4. on feeds marked `cinema_only`, drops anything that is not film-shaped, so a
   general Tamil Nadu news feed does not bring civic stories along;
5. tags it as box office / review / trailer / OTT / music / casting / buzz from
   keywords in the headline, in English **and Tamil script**;
6. de-duplicates on canonical URL *and* on a normalised headline, so the same
   story from three outlets appears once;
7. caps any one outlet at 24 stories so a busy newsroom can't flood the page;
8. **backfills missing images** — for up to 90 imageless stories it fetches the
   article page and reads its `og:image`, cached in `data/image-cache.json`;
9. counts proper-noun phrases across the headlines to build the trending rail.

Roughly 60% of stories end up with a real photo. The rest are Google News
items, which fall back to a generated poster tile — a fixed hue derived from
the headline with the film's initials set in it.

Results are cached for 10 minutes and written to `data/news.json` after every
successful refresh, so you always have the last good copy on disk.

## Using the site

The homepage is an **editorial grid**: a photo-led lead story with a "Next Up"
rail, then category blocks — Top News as a feature module, Box Office and
Trailers as photo cards, OTT / Reviews / Music / Casting as numbered "in brief"
lists. Sections fade in as you scroll.

- **Category nav** — Top News, Box Office, Trailers, OTT, Reviews, Music,
  Casting. Picking one (or searching) swaps the sectioned homepage for a flat
  filtered grid; **← Back to home** returns.
- **Search** — press `/` to jump to it, `Esc` to clear; matches are highlighted
- **Trending names** — click a name to search for it
- **Newsroom mix** — click an outlet's bar to see only its stories
- **Feed health** — green/red dot per feed with the item count
- **Refresh** — forces a new fetch; the page also refreshes itself every 10 minutes
- **Theme** — light by default, toggle in the masthead, remembered per browser

Every card links straight to the outlet that reported the story — this page
aggregates headlines, it doesn't republish articles.

## Design

The front end follows the **Editorial Grid / Magazine** direction: asymmetric
grid, large imagery, generous whitespace, scroll reveals, square-ish corners.

| Token | Value |
| --- | --- |
| Headlines | Newsreader (serif, built for online journalism) |
| Body / UI | Roboto |
| Tamil headlines | Noto Sans Tamil — Newsreader has no Tamil coverage |
| Accent | `#c81e3a` |
| Paper / ink | `#faf9f6` on `#18161a` (dark theme: `#121212` / `#ece9e4`) |

Two details worth knowing if you edit the CSS:

- A story's photo is layered **over** a generated poster tile, and both are
  `position: absolute`. If you drop the positioning from the image, the tile
  wins the paint order and hides the photo.
- The footer uses its own `--footer-*` tokens so it stays a dark band in both
  themes. Don't point it at `--text` / `--bg`, which invert.
- The lead story and the card sections prefer *photographed* stories, since
  those slots are image-led. The "in brief" lists don't.

## Advertising

Six slots ship as labelled placeholders, ready to swap for real ad tags:

| Slot id | Size | Where |
| --- | --- | --- |
| `ad-leaderboard` | 728×90 | above the lead story |
| `ad-infeed-1`, `ad-infeed-2` | 728×90 | between category sections |
| `ad-sidebar-1`, `ad-sidebar-2` | 300×250 | in the right rail |
| `ad-footer` | 728×90 | above the footer |

There's a commented-out AdSense `<script>` in `index.html`'s `<head>` — paste
your publisher id there, then replace each placeholder's inner markup with the
`<ins class="adsbygoogle">` block for that slot.

## Adding a source

Edit `data/sources.json` and restart (or hit <http://localhost:8080/api/refresh>):

```json
{ "name": "Some Outlet", "url": "https://example.com/tamil/feed/", "tamil_only": true, "max": 30 }
```

- `tamil_only: true` — keep only items mentioning a Tamil-cinema keyword. Use it
  for general entertainment feeds; leave it `false` for feeds that are already
  Tamil-only.
- `max` — how many items this feed may contribute per refresh.

The keyword lists that drive filtering and tagging (`TAMIL_WORDS`,
`OTHER_INDUSTRY`, `CINEMA_WORDS`, `CATEGORY_RULES`) are at the top of
`server.py`. Prefer adding a publisher feed over another Google News query —
publisher feeds bring their photos with them.

## Endpoints

| Route | What it returns |
| --- | --- |
| `/api/news` | cached payload — articles, sources, trending, feed report |
| `/api/refresh` | forces a fetch, then the same payload |
| `/api/status` | just the timestamp, count and per-feed health |

## Files

```
index.html                  markup
assets/styles.css           theme, layout, cards
assets/app.js               rendering, filtering, search
server.py                   fetcher, parser, de-duplicator, HTTP server
data/sources.json           the feed list — edit this
data/news.json              last successful snapshot (auto-written)
data/image-cache.json       scraped og:image lookups (auto-written)
start.bat                   Windows launcher

design/                     the portal redesign
  Main.dc.html              home, desktop 1440
  Mobile.dc.html            home, phone 390
  Components.dc.html        palette, type ramp, part anatomy
  canvas.json               artboard layout for a design canvas
  build_artboards.py        regenerates the artboards from data/news.json
  build_preview.py          renders the artboards into design/preview.html
  preview.html              the viewable design (auto-written)
```

## design/ — earlier direction (superseded)

`design/` holds the earlier **dense-portal** treatment — packed category
blocks, thumbnail-left rows, a wide red category bar, Anton/Archivo Narrow
type. The live site has since been rebuilt on the editorial grid above, so
these artboards no longer match `index.html`. They're kept as reference and
still regenerate from the live snapshot:

```bash
python server.py --snapshot && python design/build_artboards.py && python design/build_preview.py
```

Then open <http://localhost:8080/design/preview.html>. The `.dc.html` artboards
and `canvas.json` are ready for a Claude Design canvas, which needs Node or Bun
to assemble; note that a published canvas blocks remote images, so those would
need embedding first.

## Notes

- Open the site through the server, not by double-clicking `index.html` — the
  browser blocks `file://` pages from reading `data/news.json`.
- Feeds change. If a source goes red in the Feed health panel, its URL has moved;
  swap it in `data/sources.json`.
- Some Google News results still slip through with a mixed-industry headline
  (a Tamil star billed in a Kannada release, say). Tighten `OTHER_INDUSTRY` in
  `server.py` if you want a stricter page.

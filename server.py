#!/usr/bin/env python3
"""
Kollywood Now - local news aggregator + web server.

Pulls Tamil film-industry news from every feed listed in data/sources.json,
normalises it, de-duplicates it and serves it at /api/news.
Standard library only - no pip install needed.

    python server.py            # http://localhost:8080
    python server.py --port 9000
    python server.py --snapshot # just refresh data/news.json and exit
"""

import argparse
import concurrent.futures as futures
import gzip
import html
import io
import json
import os
import re
import ssl
import sys
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
SOURCES_FILE = os.path.join(DATA, "sources.json")
SNAPSHOT_FILE = os.path.join(DATA, "news.json")

CACHE_SECONDS = 600          # 10 minutes
FETCH_TIMEOUT = 20
MAX_ITEMS = 200
MAX_AGE_DAYS = 21            # ignore anything older than this
MAX_PER_SOURCE = 24          # stop one busy outlet from flooding the page

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

# --- what counts as "Tamil cinema" for the mixed / national feeds ----------
TAMIL_WORDS = [
    "tamil", "kollywood", "rajinikanth", "kamal haasan", "vijay",
    "ajith", "suriya", "dhanush", "sivakarthikeyan", "vijay sethupathi",
    "nayanthara", "trisha", "keerthy suresh", "vetrimaaran", "lokesh kanagaraj",
    "mari selvaraj", "pa ranjith", "nelson dilipkumar", "anirudh ravichander",
    "ar rahman", "a r rahman", "ilaiyaraaja", "yuvan", "silambarasan", "simbu",
    "karthi", "udhayanidhi", "sun pictures", "red giant", "jailer", "coolie",
    "parasakthi", "jana nayagan", "karuppu", "arasan", "thalapathy", "thalaivar",
    "sai pallavi", "soori", "yogi babu", "santhanam", "aishwarya rajesh",
    # Tamil script, for the Tamil-language feeds
    "தமிழ்", "சினிமா",
    "திரைப்பட", "நடிகர்",
    "நடிகை", "இயக்குநர்",
    "ரஜினி", "கமல்", "விஜய்",
    "அஜித்", "சூர்யா",
    "தனுஷ்", "டீசர்",
    "ட்ரெயலர்",
]

# Article images: many feeds ship none, so fall back to the page's own og:image.
OG_PATTERNS = (
    r'<meta[^>]+property=["\']og:image(?::url)?["\'][^>]+content=["\']([^"\']+)',
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image(?::url)?["\']',
    r'<meta[^>]+name=["\']twitter:image(?::src)?["\'][^>]+content=["\']([^"\']+)',
)
BACKFILL_LIMIT = 90       # how many imageless articles to chase per refresh
BACKFILL_TIMEOUT = 9
IMAGE_CACHE_FILE = None   # set in main()
_IMAGE_CACHE = {}

# A headline that is clearly about another industry, with no explicit Tamil
# marker, is dropped - shared-name actors otherwise leak in.
OTHER_INDUSTRY = [
    "malayalam", "mollywood", "mammootty", "mohanlal", "telugu", "tollywood",
    "kannada", "sandalwood", "bollywood", "hindi film", "marathi",
    "vijay deverakonda", "vijay varma", "bigg boss 20", "us open",
    "premier league", "world cup",
]
STRONG_TAMIL = ["tamil", "kollywood"]

# General-news feeds carry plenty of non-cinema Tamil Nadu stories. Feeds
# flagged cinema_only must also say something film-shaped.
CINEMA_WORDS = [
    "film", "films", "movie", "movies", "cinema", "actor", "actress",
    "director", "trailer", "teaser", "first look", "box office", "ott",
    "streaming", "shooting", "screenplay", "producer", "release date",
    "song", "album", "audio launch", "sequel", "biopic", "web series",
    "படம்", "படத்த", "சினிமா", "திரைப்பட",
    "நடிகர்", "நடிகை", "இயக்குநர்",
    "டீசர்", "டிரெய்லர்", "ட்ரெய்லர்",
    "வசூல்", "ஓடிடி", "பாடல்", "படப்பிடிப்பு",
]

_WORD_CACHE = {}


def _matches(text, words):
    key = id(words)
    pattern = _WORD_CACHE.get(key)
    if pattern is None:
        pattern = re.compile(r"(?<![a-z])(?:%s)(?![a-z])"
                             % "|".join(re.escape(w) for w in words))
        _WORD_CACHE[key] = pattern
    return bool(pattern.search(text.lower()))

CATEGORY_RULES = [
    ("box-office", ["box office", "collection day", "day collection", "crore",
                    "opening day", "worldwide gross", "advance booking",
                    "occupancy", "footfall",
                    "வசூல்", "கோடி", "பாக்ஸ் ஆபிஸ்"]),
    ("reviews",    ["review", "rating", "verdict", "critics",
                    "விமர்சனம்", "ரிவ்யூ"]),
    ("ott",        ["ott", "netflix", "prime video", "jiohotstar", "hotstar",
                    "zee5", "sonyliv", "streaming", "digital premiere",
                    "digital rights",
                    "ஓடிடி", "நெட்ஃபிளிக்ஸ்", "ஸ்ட்ரீமிங்"]),
    ("music",      ["song", "single", "album", "audio launch", "lyrical",
                    "music director", "bgm", "anirudh", "rahman", "composer",
                    "பாடல்", "இசை", "ஆல்பம்"]),
    ("trailers",   ["teaser", "trailer", "first look", "glimpse",
                    "motion poster", "title announcement", "promo",
                    "டீசர்", "டிரெய்லர்", "ட்ரெய்லர்",
                    "ஃபர்ஸ்ட் லுக்", "புரோமோ"]),
    ("casting",    ["signs", "joins", "roped in", "to direct", "next film",
                    "announced", "shooting", "wraps", "muhurat", "on floors",
                    "confirmed for", "cast",
                    "படப்பிடிப்பு", "அறிவிப்பு", "இணைந்தார்"]),
]

STOPWORDS = set("""a an and are as at be but by for from has have he her his if in
into is it its of on or she that the their there they this to was were will with
you your about after all also been can new now not out over said says than then
what when which who why how does day film films movie movies tamil actor actress
star first latest big top get gets set sets says say make makes just like more
most very much just year years time times back next take takes""".split())


# --------------------------------------------------------------------------- #
# fetching
# --------------------------------------------------------------------------- #
def fetch(url, timeout=FETCH_TIMEOUT):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
        "Accept-Language": "en-IN,en;q=0.9",
        "Accept-Encoding": "gzip",
    })
    with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as resp:
        raw = resp.read()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
    return raw.decode("utf-8", "ignore")


# --------------------------------------------------------------------------- #
# parsing helpers
# --------------------------------------------------------------------------- #
TAG_RE = re.compile(r"<[^>]+>")


def _clean_cdata(text):
    text = re.sub(r"^\s*<!\[CDATA\[", "", text)
    text = re.sub(r"\]\]>\s*$", "", text)
    return text.strip()


def _tag(block, name):
    match = re.search(r"<%s[^>]*>(.*?)</%s>" % (name, name), block, re.S | re.I)
    return _clean_cdata(match.group(1)) if match else ""


def strip_html(text, limit=280):
    text = _clean_cdata(text)
    # Unescape *before* stripping tags: several feeds (Times of India among
    # them) ship their markup escaped, so &lt;img ...&gt; survives the tag
    # regex and then unescaping would turn it into visible junk text.
    text = html.unescape(text)
    # Some feeds double-escape, so unescaping can expose a CDATA marker the
    # anchored cleaner already ran past. Drop them wherever they sit.
    text = re.sub(r"<!\[CDATA\[|\]\]>", " ", text)
    text = re.sub(r"<script.*?</script>", " ", text, flags=re.S | re.I)
    text = TAG_RE.sub(" ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0] + "…"
    return text


def find_image(block):
    patterns = (
        r'<media:content[^>]+url="([^"]+)"',
        r'<media:thumbnail[^>]+url="([^"]+)"',
        r'<enclosure[^>]+url="([^"]+)"',
        r"<image>\s*<url>(.*?)</url>",
        r"<img[^>]+src=['\"]([^'\"]+)['\"]",
        r"&lt;img[^&]+src=['\"]([^'\"]+)['\"]",
    )
    for pattern in patterns:
        match = re.search(pattern, block, re.I | re.S)
        if not match:
            continue
        url = html.unescape(match.group(1).strip())
        if url.startswith("//"):
            url = "https:" + url
        if url.startswith("http") and not url.lower().endswith((".mp3", ".mp4")):
            return url
    return ""


def parse_date(text):
    text = _clean_cdata(text)
    if not text:
        return None
    try:
        stamp = parsedate_to_datetime(text)
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        return stamp.astimezone(timezone.utc)
    except Exception:                                              # noqa: BLE001
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S"):
        try:
            stamp = datetime.strptime(text.strip(), fmt)
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            return stamp.astimezone(timezone.utc)
        except ValueError:
            continue
    return None


def looks_tamil(text):
    return _matches(text, TAMIL_WORDS)


def is_other_industry(text):
    """True when the story clearly belongs to another film industry."""
    return _matches(text, OTHER_INDUSTRY) and not _matches(text, STRONG_TAMIL)


def categorise(title, summary):
    low = (title + " " + summary).lower()
    for name, words in CATEGORY_RULES:
        if any(word in low for word in words):
            return name
    return "buzz"


def normalise_key(title):
    key = re.sub(r"[^a-z0-9 ]", " ", title.lower())
    return " ".join(key.split()[:9])


# --------------------------------------------------------------------------- #
# feed -> articles
# --------------------------------------------------------------------------- #
def parse_feed(xml, feed):
    blocks = re.findall(r"<item[\s>].*?</item>", xml, re.S | re.I)
    if not blocks:
        blocks = re.findall(r"<entry[\s>].*?</entry>", xml, re.S | re.I)

    articles = []
    for block in blocks:
        title = strip_html(_tag(block, "title"), 200)
        if not title:
            continue

        link = _tag(block, "link")
        if not link:
            match = re.search(r'<link[^>]+href="([^"]+)"', block, re.I)
            link = match.group(1) if match else ""
        link = html.unescape(link.strip())
        if not link.startswith("http"):
            continue

        summary = strip_html(_tag(block, "description")
                             or _tag(block, "summary")
                             or _tag(block, "content:encoded"))
        source = feed["name"]

        # Google News hides the real publisher at the end of the headline.
        if "news.google.com" in feed["url"]:
            match = re.search(r"\s-\s([^-]{2,40})$", title)
            if match:
                source = match.group(1).strip()
                title = title[:match.start()].strip()
            summary = ""      # Google's description is just a list of links

        blurb = title + " " + summary
        if feed.get("tamil_only") and not looks_tamil(blurb):
            continue
        if feed.get("cinema_only") and not _matches(blurb, CINEMA_WORDS):
            continue
        if is_other_industry(blurb):
            continue

        published = parse_date(_tag(block, "pubDate")
                               or _tag(block, "published")
                               or _tag(block, "updated")
                               or _tag(block, "dc:date"))

        articles.append({
            "title": title,
            "url": link,
            "source": source,
            "summary": summary,
            "image": find_image(block),
            "published": published.isoformat() if published else "",
            "ts": published.timestamp() if published else 0.0,
            "category": categorise(title, summary),
        })

    cutoff = time.time() - MAX_AGE_DAYS * 86400
    articles = [a for a in articles if a["ts"] >= cutoff]
    articles.sort(key=lambda a: a["ts"], reverse=True)
    return articles[:feed.get("max", 40)]


def load_sources():
    with open(SOURCES_FILE, "r", encoding="utf-8") as handle:
        return json.load(handle)["feeds"]


PHRASE_RE = re.compile(r"\b([A-Z][a-z']{2,}(?:\s+[A-Z][a-z']{2,}){0,2})\b")
PHRASE_BLOCKLIST = {
    "box office", "the times", "times of india", "official trailer", "movie review",
    "release date", "ott release", "first look", "day collection", "this week",
    "new ott", "watch the", "here is", "check out", "read more", "day box",
    "worldwide box", "india net", "tamil nadu", "the hindu", "hindustan times",
    "indian express", "movie showtimes", "sneak peek", "day worldwide",
}


def trending(articles, limit=14):
    """Frequency of proper-noun phrases in recent headlines - the trending rail."""
    counts = {}
    for article in articles[:140]:
        for phrase in PHRASE_RE.findall(article["title"]):
            key = phrase.lower()
            if key in PHRASE_BLOCKLIST or key in STOPWORDS:
                continue
            if len(key) < 4 or all(w in STOPWORDS for w in key.split()):
                continue
            entry = counts.setdefault(key, {"n": 0, "label": phrase})
            entry["n"] += 1

    # a longer phrase wins over the single word it contains ("Vijay Sethupathi")
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1]["n"], -len(kv[0])))
    chosen = []
    for key, entry in ranked:
        if entry["n"] < 2:
            continue
        if any(key in other and key != other for other, _ in chosen):
            continue
        chosen.append((key, entry))
        if len(chosen) >= limit:
            break
    return [{"term": e["label"], "count": e["n"]} for _, e in chosen]


def scrape_image(url):
    """Read a story page and return its og:image, or '' if there isn't one."""
    try:
        page = fetch(url, timeout=BACKFILL_TIMEOUT)[:220000]
    except Exception:                                              # noqa: BLE001
        return ""
    for pattern in OG_PATTERNS:
        match = re.search(pattern, page, re.I)
        if not match:
            continue
        image = html.unescape(match.group(1).strip())
        if image.startswith("//"):
            image = "https:" + image
        if image.startswith("http") and not image.lower().endswith((".svg", ".gif")):
            return image
    return ""


def backfill_images(articles):
    """Chase og:image for the newest articles that arrived without one.

    Google News links are opaque redirects with no usable page, so they are
    skipped - those keep the generated poster tile.
    """
    targets = [a for a in articles
               if not a["image"] and "news.google.com" not in a["url"]][:BACKFILL_LIMIT]
    if not targets:
        return 0

    def work(article):
        cached = _IMAGE_CACHE.get(article["url"])
        if cached is not None:
            return article, cached
        found = scrape_image(article["url"])
        _IMAGE_CACHE[article["url"]] = found
        return article, found

    filled = 0
    with futures.ThreadPoolExecutor(max_workers=10) as pool:
        for article, image in pool.map(work, targets):
            if image:
                article["image"] = image
                filled += 1
    return filled


def load_image_cache():
    if not IMAGE_CACHE_FILE:
        return
    try:
        with open(IMAGE_CACHE_FILE, "r", encoding="utf-8") as handle:
            _IMAGE_CACHE.update(json.load(handle))
    except (OSError, ValueError):
        pass


def save_image_cache():
    if not IMAGE_CACHE_FILE:
        return
    try:
        trimmed = dict(list(_IMAGE_CACHE.items())[-1500:])
        with open(IMAGE_CACHE_FILE, "w", encoding="utf-8") as handle:
            json.dump(trimmed, handle)
    except OSError:
        pass


def collect():
    """Fetch every feed in parallel, then merge, de-duplicate and sort."""
    feeds = load_sources()
    articles, report = [], []

    def work(feed):
        started = time.time()
        try:
            return feed, parse_feed(fetch(feed["url"]), feed), None, time.time() - started
        except Exception as exc:                                   # noqa: BLE001
            return feed, [], "%s: %s" % (type(exc).__name__, exc), time.time() - started

    with futures.ThreadPoolExecutor(max_workers=12) as pool:
        for feed, items, error, took in pool.map(work, feeds):
            articles.extend(items)
            report.append({
                "name": feed["name"],
                "url": feed["url"],
                "items": len(items),
                "ok": error is None,
                "error": error,
                "seconds": round(took, 2),
            })

    seen_url, seen_title, per_source, unique = set(), set(), {}, []
    for article in sorted(articles, key=lambda a: a["ts"], reverse=True):
        canon = re.sub(r"[?#].*$", "", article["url"]).rstrip("/").lower()
        key = normalise_key(article["title"])
        source = article["source"]
        if canon in seen_url or (key and key in seen_title):
            continue
        if per_source.get(source, 0) >= MAX_PER_SOURCE:
            continue
        seen_url.add(canon)
        seen_title.add(key)
        per_source[source] = per_source.get(source, 0) + 1
        unique.append(article)

    unique = unique[:MAX_ITEMS]

    filled = backfill_images(unique)
    save_image_cache()
    with_image = sum(1 for a in unique if a["image"])

    return {
        "generated": datetime.now(timezone.utc).isoformat(),
        "count": len(unique),
        "sources": sorted({a["source"] for a in unique}),
        "images": {"total": with_image, "scraped": filled},
        "feeds": report,
        "trending": trending(unique),
        "articles": unique,
    }


# --------------------------------------------------------------------------- #
# cache + snapshot
# --------------------------------------------------------------------------- #
def save_snapshot(payload):
    try:
        with open(SNAPSHOT_FILE, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=1)
    except OSError:
        pass


def load_snapshot():
    try:
        with open(SNAPSHOT_FILE, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        data["stale"] = True
        return data
    except (OSError, ValueError):
        return {"generated": "", "count": 0, "articles": [], "sources": [],
                "feeds": [], "trending": [], "error": "no data available"}


class Cache:
    def __init__(self):
        self.payload = None
        self.stamp = 0.0
        self.lock = threading.Lock()

    def get(self, force=False):
        with self.lock:
            fresh = self.payload and (time.time() - self.stamp) < CACHE_SECONDS
            if fresh and not force:
                return self.payload
            try:
                self.payload = collect()
                self.stamp = time.time()
                save_snapshot(self.payload)
            except Exception as exc:                               # noqa: BLE001
                sys.stderr.write("refresh failed: %s\n" % exc)
                if self.payload is None:
                    self.payload = load_snapshot()
            return self.payload


CACHE = Cache()


# --------------------------------------------------------------------------- #
# http
# --------------------------------------------------------------------------- #
class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def log_message(self, fmt, *args):
        if "/api/" in (self.path or ""):
            sys.stdout.write("  %s %s\n" % (self.command, self.path))

    def _json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        route = urllib.parse.urlparse(self.path).path
        if route == "/api/news":
            self._json(CACHE.get())
        elif route == "/api/refresh":
            self._json(CACHE.get(force=True))
        elif route == "/api/status":
            payload = CACHE.get()
            self._json({"generated": payload.get("generated"),
                        "count": payload.get("count"),
                        "feeds": payload.get("feeds", [])})
        else:
            super().do_GET()

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()


def main():
    global IMAGE_CACHE_FILE
    parser = argparse.ArgumentParser(description="Kollywood Now server")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--snapshot", action="store_true",
                        help="refresh data/news.json and exit")
    args = parser.parse_args()

    IMAGE_CACHE_FILE = os.path.join(DATA, "image-cache.json")
    load_image_cache()

    if args.snapshot:
        payload = collect()
        save_snapshot(payload)
        good = sum(1 for feed in payload["feeds"] if feed["ok"])
        shots = payload["images"]
        print("%d stories from %d/%d feeds -> data/news.json"
              % (payload["count"], good, len(payload["feeds"])))
        print("images: %d of %d (%d scraped from the article pages)"
              % (shots["total"], payload["count"], shots["scraped"]))
        for feed in payload["feeds"]:
            print("  %-16s %3d  %s" % (feed["name"], feed["items"],
                                       feed["error"] or "ok"))
        return

    print("Kollywood Now - warming up the feeds...")
    payload = CACHE.get()
    good = sum(1 for feed in payload.get("feeds", []) if feed["ok"])
    print("  %d stories from %d/%d feeds"
          % (payload.get("count", 0), good, len(payload.get("feeds", []))))
    print("  open  ->  http://localhost:%d" % args.port)
    print("  stop  ->  Ctrl+C")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
        server.server_close()


if __name__ == "__main__":
    main()

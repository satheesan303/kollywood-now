#!/usr/bin/env python3
"""Generate the design artboards from the live aggregator snapshot.

Main.dc.html and Mobile.dc.html are rebuilt from data/news.json, so the design
always shows real headlines and the real article photography rather than
placeholder copy. Components.dc.html is hand-authored and left alone.

    python design/build_artboards.py
"""

import html
import json
import os
import re
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
SNAPSHOT = os.path.join(os.path.dirname(HERE), "data", "news.json")

INK, PAPER, CARD, RULE = "#16130f", "#f3f0ea", "#ffffff", "#d9d2c6"
SOFT_RULE, MUTED, BODY, GOLD = "#e6e0d5", "#6f665b", "#4b433a", "#e2a32b"
NARROW = "'Archivo Narrow', 'Arial Narrow', sans-serif"
TAMIL = "'Noto Sans Tamil', 'Archivo Narrow', sans-serif"
ANTON = "Anton, Impact, sans-serif"

# duotone pairs for the tiles that stand in when a story has no photo
TILE_HUES = [
    ("#2d1c46", "#130b1f"), ("#123a52", "#071722"), ("#6b1f36", "#2a0c16"),
    ("#1f4133", "#0a1a13"), ("#5c3a10", "#241505"), ("#4d1220", "#1d060c"),
    ("#0f3b3a", "#041614"), ("#3d2a55", "#170f21"),
]

SECTIONS = [
    ("TOP NEWS", "buzz", "cards"),
    ("BOX OFFICE", "box-office", "cards"),
    ("TRAILERS &amp; FIRST LOOKS", "trailers", "cards"),
    ("OTT &amp; STREAMING", "ott", "rows"),
    ("REVIEWS", "reviews", "rows"),
    ("CASTING &amp; SHOOTS", "casting", "rows"),
]

TAMIL_RANGE = re.compile(r"[஀-௿]")


def esc(text):
    return html.escape(text or "", quote=True)


def is_tamil(text):
    return bool(TAMIL_RANGE.search(text or ""))


def face(text):
    return TAMIL if is_tamil(text) else NARROW


def initials(title):
    words = re.sub(r"[^A-Za-z ]", " ", title).split()
    return ("".join(w[0] for w in words[:2]).upper() or "KN")


def tile(title, font_size):
    digest = 0
    for ch in title:
        digest = (digest * 31 + ord(ch)) & 0xFFFFFFFF
    top, bottom = TILE_HUES[digest % len(TILE_HUES)]
    return ('<div style="position: absolute; inset: 0; background: linear-gradient(140deg, %s, %s); '
            'display: grid; place-items: center;">'
            '<span style="font-family: %s; font-size: %dpx; color: rgba(255,255,255,.9);">%s</span>'
            '</div>' % (top, bottom, ANTON, font_size, esc(initials(title))))


def art(article, font_size):
    """The article photo over its poster tile.

    The tile always sits underneath, so a photo an outlet refuses to serve
    off-site degrades to the tile instead of leaving an empty box.
    """
    backdrop = tile(article["title"], font_size)
    if not article.get("image"):
        return backdrop
    return (backdrop +
            '<img src="%s" alt="" loading="lazy" onerror="this.style.display=\'none\'" '
            'style="position: absolute; inset: 0; width: 100%%; height: 100%%; '
            'object-fit: cover; display: block;">' % esc(article["image"]))


def ago(article, now):
    if not article.get("ts"):
        return "recently"
    delta = now - article["ts"]
    if delta < 3600:
        return "%dm" % max(1, round(delta / 60))
    if delta < 86400:
        return "%dh" % round(delta / 3600)
    return "%dd" % round(delta / 86400)


def load():
    with open(SNAPSHOT, "r", encoding="utf-8") as handle:
        return json.load(handle)


def pick(pool, category, count, need_image=False, used=None):
    """Freshest unused stories from a category, photographed ones first.

    need_image only expresses a preference: a section still fills up from
    imageless stories rather than disappearing, and those render as tiles.
    """
    candidates = [a for a in pool
                  if a["url"] not in used
                  and (not category or a["category"] == category)]
    if need_image:
        candidates.sort(key=lambda a: 0 if a.get("image") else 1)

    out = candidates[:count]
    for article in out:
        used.add(article["url"])
    return out


# --------------------------------------------------------------------------- #
# desktop pieces
# --------------------------------------------------------------------------- #
def section_bar(label, count, spine="{{accent}}"):
    return ('<div style="display: flex; align-items: stretch; background: %s; margin-bottom: 14px;">'
            '<div style="width: 10px; background: %s;"></div>'
            '<div style="padding: 9px 16px; font-family: %s; font-size: 19px; letter-spacing: 1px; color: #ffffff;">%s</div>'
            '<div style="flex-grow: 1;"></div>'
            '<div style="display: flex; align-items: center; padding: 0 16px; font-size: 11.5px; '
            'font-weight: 700; letter-spacing: .8px; color: #b3aa9d;">%d STORIES &nbsp;&rsaquo;</div></div>'
            % (INK, spine, ANTON, label, count))


def card(article, now):
    return ('<a href="%s" target="_blank" rel="noopener" style="background: %s; border: 1px solid %s; display: block;">'
            '<div style="position: relative; height: 132px; background: #efeae1; overflow: hidden;">%s</div>'
            '<div style="padding: 11px 12px 13px;">'
            '<div style="font-family: %s; font-size: 16.5px; font-weight: 700; line-height: 1.28;">%s</div>'
            '<div style="font-size: 10.5px; color: %s; margin-top: 7px; font-weight: 600;">%s &middot; %s</div>'
            '</div></a>'
            % (esc(article["url"]), CARD, RULE, art(article, 40), face(article["title"]),
               esc(article["title"]), MUTED, esc(article["source"]), ago(article, now)))


def dense_row(article, index, now):
    return ('<a href="%s" target="_blank" rel="noopener" style="display: flex; gap: 12px; align-items: center; '
            'padding: 11px 0; border-bottom: 1px solid %s;">'
            '<span style="font-family: %s; font-size: 20px; color: #cbc2b4; width: 24px; flex: 0 0 24px;">%02d</span>'
            '<div style="position: relative; flex: 0 0 62px; height: 46px; overflow: hidden; background: #efeae1;">%s</div>'
            '<div style="min-width: 0;">'
            '<div style="font-family: %s; font-size: 15.5px; font-weight: 700; line-height: 1.26;">%s</div>'
            '<div style="font-size: 10.5px; color: %s; margin-top: 3px; font-weight: 600;">%s &middot; %s</div>'
            '</div></a>'
            % (esc(article["url"]), SOFT_RULE, ANTON, index, art(article, 17),
               face(article["title"]), esc(article["title"]), MUTED,
               esc(article["source"]), ago(article, now)))


def side_row(article, now, last=False):
    border = "" if last else "border-bottom: 1px solid %s;" % SOFT_RULE
    return ('<a href="%s" target="_blank" rel="noopener" style="display: flex; gap: 12px; padding: {{rowPad}}; %s">'
            '<div style="position: relative; flex: 0 0 78px; height: 58px; overflow: hidden; background: #efeae1;">%s</div>'
            '<div style="min-width: 0;">'
            '<div style="font-size: 10.5px; font-weight: 700; letter-spacing: .9px; color: {{accent}}; '
            'text-transform: uppercase; margin-bottom: 3px;">%s</div>'
            '<div style="font-family: %s; font-size: 15.5px; font-weight: 700; line-height: 1.24;">%s</div>'
            '<div style="font-size: 10.5px; color: %s; margin-top: 4px; font-weight: 600;">%s &middot; %s</div>'
            '</div></a>'
            % (esc(article["url"]), border, art(article, 21), esc(article["category"].replace("-", " ")),
               face(article["title"]), esc(article["title"]), MUTED,
               esc(article["source"]), ago(article, now)))


def build_main(data):
    now = datetime.now(timezone.utc).timestamp()
    pool = data["articles"]
    used = set()
    counts = {}
    for article in pool:
        counts[article["category"]] = counts.get(article["category"], 0) + 1

    lead = pick(pool, None, 1, need_image=True, used=used)[0]
    nexts = pick(pool, None, 4, need_image=True, used=used)

    blocks = []
    for label, category, style in SECTIONS:
        want = 4 if style == "cards" else 6
        items = pick(pool, category, want, need_image=(style == "cards"), used=used)
        if len(items) < (4 if style == "cards" else 3):
            continue
        if style == "rows" and len(items) % 2:
            items = items[:-1] if len(items) > 3 else items
        if style == "cards":
            cards = "".join(card(a, now) for a in items)
            body = ('<div style="display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); '
                    'gap: {{cardGap}};">%s</div>' % cards)
        else:
            rows = "".join(dense_row(a, i + 1, now) for i, a in enumerate(items))
            body = ('<div style="display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); '
                    'gap: 0 24px; background: %s; border: 1px solid %s; padding: 4px 16px;">%s</div>'
                    % (CARD, RULE, rows))
        blocks.append('<div>%s%s</div>' % (section_bar(label, counts.get(category, 0)), body))

    trending = "".join(
        '<div style="display: flex; align-items: baseline; gap: 12px; padding: 9px 0; %s">'
        '<span style="font-family: %s; font-size: 19px; color: %s; width: 22px;">%d</span>'
        '<span style="flex-grow: 1; font-size: 15px; font-weight: 600;">%s</span>'
        '<span style="font-size: 11px; color: %s; font-weight: 600;">%d stories</span></div>'
        % ("" if i == len(data["trending"][:8]) - 1 else "border-bottom: 1px solid %s;" % SOFT_RULE,
           ANTON, "{{accent}}" if i < 2 else "#b3aa9d", i + 1, esc(t["term"]), MUTED, t["count"])
        for i, t in enumerate(data["trending"][:8]))

    tally = {}
    for article in pool:
        tally[article["source"]] = tally.get(article["source"], 0) + 1
    top = sorted(tally.items(), key=lambda kv: -kv[1])[:6]
    biggest = top[0][1] if top else 1
    mix = "".join(
        '<div><div style="display: flex; justify-content: space-between; font-size: 12.5px; '
        'font-weight: 600; margin-bottom: 5px;"><span>%s</span><span style="color: %s;">%d</span></div>'
        '<div style="height: 6px; background: #ece6da;"><div style="width: %d%%; height: 100%%; '
        'background: %s;"></div></div></div>'
        % (esc(name), MUTED, n, round(n / biggest * 100), "{{accent}}" if n / biggest > .7 else GOLD)
        for name, n in top)

    health = "".join(
        '<div style="display: flex; align-items: center; gap: 9px;">'
        '<span style="width: 7px; height: 7px; background: %s; border-radius: 50%%; flex: 0 0 auto;"></span>'
        '<span style="flex-grow: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">%s</span>'
        '<span style="color: #7a7167;">%s</span></div>'
        % ("#7df5a8" if f["ok"] else "#d5301c", esc(f["name"]), f["items"] if f["ok"] else "down")
        for f in data["feeds"][:8])

    ticker = "".join(
        '<span><b style="color: {{accent}};">%s</b> &nbsp;%s</span>'
        '<span style="color: #4a443d;">&#9670;</span>'
        % (esc(a["source"]), esc(a["title"][:78]))
        for a in pool[:3])

    stamp = datetime.now().strftime("%A, %-d %B %Y") if os.name != "nt" \
        else datetime.now().strftime("%A, %d %B %Y").replace(" 0", " ")
    shot = data.get("images", {})
    photo_note = "%d of %d stories arrived with a photo" % (shot.get("total", 0), data["count"])

    return TEMPLATE_MAIN.format(
        stamp=esc(stamp), count=data["count"], outlets=len(data["sources"]),
        feeds=len(data["feeds"]), photo_note=esc(photo_note), ticker=ticker,
        lead_art=art(lead, 96), lead_cat=esc(lead["category"].replace("-", " ")),
        lead_face=face(lead["title"]), lead_title=esc(lead["title"]),
        lead_dek=('<p style="margin: 0 0 14px; font-size: 15px; line-height: 1.5; color: %s;">%s</p>'
                  % (BODY, esc(lead["summary"]))) if lead.get("summary") else "",
        lead_source=esc(lead["source"]), lead_ago=ago(lead, now),
        next_rows="".join(side_row(a, now, last=(i == len(nexts) - 1))
                          for i, a in enumerate(nexts)),
        blocks="".join(blocks), trending=trending, mix=mix, health=health,
        ink=INK, paper=PAPER, card=CARD, rule=RULE, muted=MUTED, gold=GOLD, anton=ANTON)


def build_mobile(data):
    now = datetime.now(timezone.utc).timestamp()
    pool = data["articles"]
    used = set()
    lead = pick(pool, None, 1, need_image=True, used=used)[0]
    nexts = pick(pool, None, 4, need_image=True, used=used)
    grid = pick(pool, "box-office", 2, need_image=True, used=used) or \
        pick(pool, None, 2, need_image=True, used=used)
    rows = pick(pool, "ott", 4, used=used) or pick(pool, None, 4, used=used)

    def m_row(article, last=False):
        border = "" if last else "border-bottom: 1px solid %s;" % SOFT_RULE
        return ('<a href="%s" target="_blank" rel="noopener" style="display: flex; gap: 12px; padding: 12px 0; %s">'
                '<div style="position: relative; flex: 0 0 82px; height: 60px; overflow: hidden; background: #efeae1;">%s</div>'
                '<div style="min-width: 0;">'
                '<div style="font-size: 10px; font-weight: 700; letter-spacing: .9px; color: {{accent}}; '
                'text-transform: uppercase; margin-bottom: 3px;">%s</div>'
                '<div style="font-family: %s; font-size: 16px; font-weight: 700; line-height: 1.22;">%s</div>'
                '<div style="font-size: 10.5px; color: %s; margin-top: 4px; font-weight: 600;">%s &middot; %s</div>'
                '</div></a>'
                % (esc(article["url"]), border, art(article, 22),
                   esc(article["category"].replace("-", " ")), face(article["title"]),
                   esc(article["title"]), MUTED, esc(article["source"]), ago(article, now)))

    def m_card(article):
        return ('<a href="%s" target="_blank" rel="noopener" style="background: %s; border: 1px solid %s; display: block;">'
                '<div style="position: relative; height: 106px; overflow: hidden; background: #efeae1;">%s</div>'
                '<div style="padding: 10px 11px 12px;">'
                '<div style="font-family: %s; font-size: 15.5px; font-weight: 700; line-height: 1.22;">%s</div>'
                '<div style="font-size: 10px; color: %s; margin-top: 6px; font-weight: 600;">%s &middot; %s</div>'
                '</div></a>'
                % (esc(article["url"]), CARD, RULE, art(article, 32), face(article["title"]),
                   esc(article["title"]), MUTED, esc(article["source"]), ago(article, now)))

    def m_dense(article, i, last=False):
        border = "" if last else "border-bottom: 1px solid %s;" % SOFT_RULE
        return ('<a href="%s" target="_blank" rel="noopener" style="display: flex; gap: 12px; align-items: center; '
                'padding: 13px 0; %s">'
                '<span style="font-family: %s; font-size: 20px; color: #cbc2b4; width: 22px; flex: 0 0 22px;">%02d</span>'
                '<div style="flex-grow: 1; min-width: 0;">'
                '<div style="font-family: %s; font-size: 15.5px; font-weight: 700; line-height: 1.24;">%s</div>'
                '<div style="font-size: 10px; color: %s; margin-top: 3px; font-weight: 600;">%s &middot; %s</div>'
                '</div></a>'
                % (esc(article["url"]), border, ANTON, i, face(article["title"]),
                   esc(article["title"]), MUTED, esc(article["source"]), ago(article, now)))

    trending = "".join(
        '<div style="display: flex; align-items: baseline; gap: 12px; padding: 10px 0; %s">'
        '<span style="font-family: %s; font-size: 19px; color: %s; width: 20px;">%d</span>'
        '<span style="flex-grow: 1; font-size: 15px; font-weight: 600;">%s</span>'
        '<span style="font-size: 11px; color: %s; font-weight: 600;">%d</span></div>'
        % ("" if i == 5 else "border-bottom: 1px solid %s;" % SOFT_RULE,
           ANTON, "{{accent}}" if i < 2 else "#b3aa9d", i + 1, esc(t["term"]), MUTED, t["count"])
        for i, t in enumerate(data["trending"][:6]))

    return TEMPLATE_MOBILE.format(
        count=data["count"], outlets=len(data["sources"]),
        ticker_source=esc(pool[0]["source"]), ticker_title=esc(pool[0]["title"][:52]),
        lead_art=art(lead, 52), lead_face=face(lead["title"]), lead_title=esc(lead["title"]),
        lead_dek=('<p style="margin: 0 0 11px; font-size: 14px; line-height: 1.5; color: %s;">%s</p>'
                  % (BODY, esc(lead["summary"][:150]))) if lead.get("summary") else "",
        lead_source=esc(lead["source"]), lead_ago=ago(lead, now),
        next_rows="".join(m_row(a, last=(i == len(nexts) - 1)) for i, a in enumerate(nexts)),
        cards="".join(m_card(a) for a in grid),
        dense="".join(m_dense(a, i + 1, last=(i == len(rows) - 1)) for i, a in enumerate(rows)),
        trending=trending, ink=INK, paper=PAPER, card=CARD, rule=RULE,
        muted=MUTED, gold=GOLD, anton=ANTON)


TEMPLATE_MAIN = """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <script src="./support.js"></script>
</head>
<body>
<x-dc>
<helmet>
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Anton&family=Archivo+Narrow:wght@600;700&family=Archivo:wght@400;500;600;700&family=Noto+Sans+Tamil:wght@600&display=swap">
  <style>
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: {paper}; color: #1c1815; font-family: Archivo, system-ui, sans-serif; }}
    a {{ color: #16130f; text-decoration: none; }}
    a:hover {{ color: #d5301c; }}
  </style>
</helmet>

<div style="width: 1440px; background: {paper};">

  <div style="background: {ink}; color: #9a9186; padding: 0 40px; height: 34px; display: flex; align-items: center; justify-content: space-between; font-size: 11.5px; font-weight: 500; letter-spacing: .3px;">
    <div style="display: flex; align-items: center; gap: 18px;">
      <span>{stamp} &middot; Chennai</span>
      <span style="color: #4a443d;">|</span>
      <span>{count} stories &middot; {outlets} outlets &middot; {photo_note}</span>
    </div>
    <div style="display: flex; align-items: center; gap: 14px;">
      <span style="color: {muted};">Follow the desk</span>
      <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M21 5H3v14h18z"/><path d="m3 6 9 7 9-7"/></svg>
      <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="5"/><circle cx="12" cy="12" r="4"/><circle cx="17.5" cy="6.5" r="1"/></svg>
      <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="5" width="20" height="14" rx="4"/><path d="m10 9 6 3-6 3z"/></svg>
    </div>
  </div>

  <div style="background: {card}; border-bottom: 3px solid {ink}; padding: 0 40px; height: 92px; display: flex; align-items: center; justify-content: space-between;">
    <div style="display: flex; align-items: center; gap: 14px;">
      <div style="width: 52px; height: 52px; background: {{{{accent}}}}; display: grid; place-items: center;">
        <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="#ffffff" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6.5h18v13H3z"/><path d="M7 6.5v13M17 6.5v13"/><path d="M3 11h4M17 11h4M3 15h4M17 15h4"/></svg>
      </div>
      <div>
        <div style="font-family: {anton}; font-size: 40px; line-height: .92; letter-spacing: .5px; color: {ink};">KOLLYWOOD<span style="color: {{{{accent}}}};">NOW</span></div>
        <div style="font-size: 11px; font-weight: 600; letter-spacing: 2.6px; color: {muted}; text-transform: uppercase; margin-top: 4px;">Tamil cinema desk &middot; every source, one page</div>
      </div>
    </div>
    <div style="display: flex; align-items: center; gap: 12px;">
      <div style="display: flex; align-items: center; gap: 9px; border: 1.5px solid {rule}; background: #faf8f4; height: 44px; width: 300px; padding: 0 14px;">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="{muted}" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.2-3.2"/></svg>
        <span style="font-size: 14px; color: #918878;">Search stars, films, studios</span>
      </div>
      <div style="height: 44px; padding: 0 20px; background: {ink}; color: #ffffff; display: flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 700; letter-spacing: .4px;">
        <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round"><path d="M20 11a8 8 0 1 0-2.3 6"/><path d="M20 4v7h-7"/></svg>
        REFRESH
      </div>
    </div>
  </div>

  <div style="background: {{{{accent}}}}; padding: 0 40px; height: 46px; display: flex; align-items: stretch;">
    <div style="display: flex; align-items: center; padding: 0 18px 0 0; font-family: {anton}; font-size: 15px; letter-spacing: 1px; color: #ffffff;">HOME</div>
    <div style="display: flex; align-items: center; padding: 0 18px; color: #ffffff; font-size: 13px; font-weight: 700; letter-spacing: .7px; background: rgba(0,0,0,.22);">TOP NEWS</div>
    <div style="display: flex; align-items: center; padding: 0 18px; color: rgba(255,255,255,.9); font-size: 13px; font-weight: 700; letter-spacing: .7px;">BOX OFFICE</div>
    <div style="display: flex; align-items: center; padding: 0 18px; color: rgba(255,255,255,.9); font-size: 13px; font-weight: 700; letter-spacing: .7px;">REVIEWS</div>
    <div style="display: flex; align-items: center; padding: 0 18px; color: rgba(255,255,255,.9); font-size: 13px; font-weight: 700; letter-spacing: .7px;">TRAILERS</div>
    <div style="display: flex; align-items: center; padding: 0 18px; color: rgba(255,255,255,.9); font-size: 13px; font-weight: 700; letter-spacing: .7px;">OTT</div>
    <div style="display: flex; align-items: center; padding: 0 18px; color: rgba(255,255,255,.9); font-size: 13px; font-weight: 700; letter-spacing: .7px;">MUSIC</div>
    <div style="display: flex; align-items: center; padding: 0 18px; color: rgba(255,255,255,.9); font-size: 13px; font-weight: 700; letter-spacing: .7px;">CASTING</div>
    <div style="flex-grow: 1;"></div>
    <div style="display: flex; align-items: center; gap: 7px; color: #ffffff; font-size: 12px; font-weight: 700; letter-spacing: .6px;">
      <span style="width: 8px; height: 8px; background: #7df5a8; border-radius: 50%;"></span>
      {feeds} FEEDS LIVE
    </div>
  </div>

  <div style="background: {ink}; height: 42px; display: flex; align-items: stretch; overflow: hidden;">
    <div style="background: {gold}; color: {ink}; display: flex; align-items: center; padding: 0 18px; font-family: {anton}; font-size: 14px; letter-spacing: 1.4px; white-space: nowrap;">JUST IN</div>
    <div style="display: flex; align-items: center; gap: 20px; padding: 0 20px; color: #d8d1c6; font-size: 13.5px; white-space: nowrap;">{ticker}</div>
  </div>

  <div style="padding: 26px 40px 0; display: flex; gap: 40px; align-items: flex-start;">

    <div style="width: 960px; display: flex; flex-direction: column; gap: {{{{secGap}}}};">

      <div style="display: flex; gap: 24px; align-items: stretch;">
        <div style="width: 580px; background: {card}; border: 1px solid {rule};">
          <div style="position: relative; height: 300px; overflow: hidden; background: #efeae1;">
            {lead_art}
            <div style="position: absolute; left: 0; top: 0; background: {{{{accent}}}}; color: #ffffff; font-size: 11px; font-weight: 700; letter-spacing: 1.3px; padding: 7px 12px; text-transform: uppercase;">{lead_cat} &middot; lead story</div>
          </div>
          <div style="padding: 18px 20px 20px;">
            <h1 style="margin: 0 0 10px; font-family: {lead_face}; font-size: 32px; font-weight: 700; line-height: 1.14; letter-spacing: -.2px; text-wrap: pretty;">{lead_title}</h1>
            {lead_dek}
            <div style="display: flex; align-items: center; gap: 10px; font-size: 11.5px; font-weight: 600; letter-spacing: .5px; color: {muted}; text-transform: uppercase;">
              <span style="color: {{{{accent}}}};">{lead_source}</span><span>&middot;</span><span>{lead_ago} ago</span>
            </div>
          </div>
        </div>

        <div style="width: 356px; background: {card}; border: 1px solid {rule}; padding: 0 16px; display: flex; flex-direction: column;">
          <div style="padding: 13px 0 11px; border-bottom: 2px solid {ink}; font-family: {anton}; font-size: 16px; letter-spacing: .8px;">NEXT UP</div>
          {next_rows}
        </div>
      </div>

      {blocks}
    </div>

    <div style="width: 360px; display: flex; flex-direction: column; gap: 20px;">
      <div style="background: {card}; border: 1px solid {rule};">
        <div style="background: {{{{accent}}}}; color: #ffffff; padding: 9px 14px; font-family: {anton}; font-size: 16px; letter-spacing: .9px;">TRENDING NAMES</div>
        <div style="padding: 4px 14px 10px;">{trending}</div>
      </div>

      <div style="background: {card}; border: 1px solid {rule};">
        <div style="background: {ink}; color: #ffffff; padding: 9px 14px; font-family: {anton}; font-size: 16px; letter-spacing: .9px;">NEWSROOM MIX</div>
        <div style="padding: 12px 14px 14px; display: flex; flex-direction: column; gap: 11px;">{mix}</div>
      </div>

      <div style="background: {ink}; color: #d8d1c6; padding: 14px;">
        <div style="font-family: {anton}; font-size: 15px; letter-spacing: .9px; color: #ffffff; margin-bottom: 10px;">FEED HEALTH</div>
        <div style="display: flex; flex-direction: column; gap: 7px; font-size: 12px;">{health}</div>
      </div>
    </div>
  </div>

  <div style="margin-top: 34px; background: {ink}; color: #9a9186; padding: 30px 40px 26px;">
    <div style="display: grid; grid-template-columns: 1.4fr 1fr 1fr 1fr; gap: 32px;">
      <div>
        <div style="font-family: {anton}; font-size: 26px; color: #ffffff; letter-spacing: .5px;">KOLLYWOOD<span style="color: {{{{accent}}}};">NOW</span></div>
        <p style="margin: 10px 0 0; font-size: 13px; line-height: 1.6; max-width: 34ch;">A reading desk for Tamil cinema. Headlines are pulled from public feeds, de-duplicated and grouped &mdash; every card links back to the outlet that reported it.</p>
      </div>
      <div>
        <div style="font-size: 11px; font-weight: 700; letter-spacing: 1.4px; color: #ffffff; text-transform: uppercase; margin-bottom: 11px;">Sections</div>
        <div style="display: flex; flex-direction: column; gap: 7px; font-size: 13px;"><a href="#" style="color: #9a9186;">Top news</a><a href="#" style="color: #9a9186;">Box office</a><a href="#" style="color: #9a9186;">Reviews</a><a href="#" style="color: #9a9186;">Trailers</a><a href="#" style="color: #9a9186;">OTT</a></div>
      </div>
      <div>
        <div style="font-size: 11px; font-weight: 700; letter-spacing: 1.4px; color: #ffffff; text-transform: uppercase; margin-bottom: 11px;">Outlets</div>
        <div style="display: flex; flex-direction: column; gap: 7px; font-size: 13px;"><a href="#" style="color: #9a9186;">News18 Tamil</a><a href="#" style="color: #9a9186;">Cinema Express</a><a href="#" style="color: #9a9186;">DT Next</a><a href="#" style="color: #9a9186;">The Hindu</a><a href="#" style="color: #9a9186;">All {outlets} outlets</a></div>
      </div>
      <div>
        <div style="font-size: 11px; font-weight: 700; letter-spacing: 1.4px; color: #ffffff; text-transform: uppercase; margin-bottom: 11px;">The desk</div>
        <div style="display: flex; flex-direction: column; gap: 7px; font-size: 13px;"><a href="#" style="color: #9a9186;">How it works</a><a href="#" style="color: #9a9186;">Feed health</a><a href="#" style="color: #9a9186;">Add a source</a></div>
      </div>
    </div>
    <div style="margin-top: 24px; padding-top: 16px; border-top: 1px solid #2e2921; display: flex; justify-content: space-between; font-size: 11.5px; color: {muted};">
      <span>Aggregated headlines, not republished articles. Photos remain with the outlet that published them.</span>
      <span>{count} stories &middot; {outlets} outlets</span>
    </div>
  </div>

</div>
</x-dc>

<script data-dc-script data-props='{{"accent":{{"editor":"color","default":"#d5301c","options":["#d5301c","#b0182b","#1d6a7a","#16130f"],"section":"Theme"}},"density":{{"editor":"enum","options":["Packed","Roomy"],"default":"Packed","section":"Theme"}},"$preview":{{"width":1440,"height":3700}}}}'>
class Component extends DCLogic {{
  renderVals() {{
    const roomy = (this.props.density ?? 'Packed') === 'Roomy';
    return {{
      accent: this.props.accent ?? '#d5301c',
      secGap: roomy ? '40px' : '26px',
      cardGap: roomy ? '22px' : '16px',
      rowPad: roomy ? '15px 0' : '10px 0',
    }};
  }}
}}
</script>
</body>
</html>
"""

TEMPLATE_MOBILE = """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <script src="./support.js"></script>
</head>
<body>
<x-dc>
<helmet>
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Anton&family=Archivo+Narrow:wght@600;700&family=Archivo:wght@400;500;600;700&family=Noto+Sans+Tamil:wght@600&display=swap">
  <style>
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: {paper}; color: #1c1815; font-family: Archivo, system-ui, sans-serif; }}
    a {{ color: #16130f; text-decoration: none; }}
    a:hover {{ color: #d5301c; }}
  </style>
</helmet>

<div style="width: 390px; background: {paper};">

  <div style="background: {ink}; color: #9a9186; height: 30px; display: flex; align-items: center; justify-content: space-between; padding: 0 14px; font-size: 10.5px; font-weight: 500;">
    <span>Chennai</span>
    <span>{count} stories &middot; {outlets} outlets</span>
  </div>

  <div style="background: {card}; border-bottom: 3px solid {ink}; height: 64px; display: flex; align-items: center; justify-content: space-between; padding: 0 14px;">
    <div style="display: flex; align-items: center; gap: 10px;">
      <div style="width: 38px; height: 38px; background: {{{{accent}}}}; display: grid; place-items: center;">
        <svg viewBox="0 0 24 24" width="21" height="21" fill="none" stroke="#ffffff" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6.5h18v13H3z"/><path d="M7 6.5v13M17 6.5v13"/><path d="M3 11h4M17 11h4M3 15h4M17 15h4"/></svg>
      </div>
      <div style="font-family: {anton}; font-size: 25px; line-height: .95; letter-spacing: .4px;">KOLLYWOOD<span style="color: {{{{accent}}}};">NOW</span></div>
    </div>
    <div style="display: flex; gap: 8px;">
      <div style="width: 44px; height: 44px; border: 1.5px solid {rule}; display: grid; place-items: center;">
        <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="{ink}" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.2-3.2"/></svg>
      </div>
      <div style="width: 44px; height: 44px; background: {ink}; display: grid; place-items: center;">
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="#ffffff" stroke-width="2.1" stroke-linecap="round"><path d="M4 7h16M4 12h16M4 17h10"/></svg>
      </div>
    </div>
  </div>

  <div style="background: {{{{accent}}}}; height: 48px; display: flex; align-items: stretch; overflow: hidden;">
    <div style="display: flex; align-items: center; padding: 0 15px; background: rgba(0,0,0,.24); color: #ffffff; font-size: 13px; font-weight: 700; letter-spacing: .6px;">TOP NEWS</div>
    <div style="display: flex; align-items: center; padding: 0 15px; color: rgba(255,255,255,.92); font-size: 13px; font-weight: 700; letter-spacing: .6px;">BOX OFFICE</div>
    <div style="display: flex; align-items: center; padding: 0 15px; color: rgba(255,255,255,.92); font-size: 13px; font-weight: 700; letter-spacing: .6px;">REVIEWS</div>
    <div style="display: flex; align-items: center; padding: 0 15px; color: rgba(255,255,255,.92); font-size: 13px; font-weight: 700; letter-spacing: .6px;">OTT</div>
  </div>

  <div style="background: {ink}; height: 38px; display: flex; align-items: stretch; overflow: hidden;">
    <div style="background: {gold}; color: {ink}; display: flex; align-items: center; padding: 0 12px; font-family: {anton}; font-size: 12.5px; letter-spacing: 1.2px; white-space: nowrap;">JUST IN</div>
    <div style="display: flex; align-items: center; padding: 0 12px; color: #d8d1c6; font-size: 12.5px; white-space: nowrap;">
      <span><b style="color: {{{{accent}}}};">{ticker_source}</b> &nbsp;{ticker_title}</span>
    </div>
  </div>

  <div style="padding: 14px 14px 0;">
    <a href="#" style="display: block; background: {card}; border: 1px solid {rule};">
      <div style="position: relative; height: 196px; overflow: hidden; background: #efeae1;">
        {lead_art}
        <div style="position: absolute; left: 0; top: 0; background: {{{{accent}}}}; color: #ffffff; font-size: 10px; font-weight: 700; letter-spacing: 1.2px; padding: 6px 10px;">LEAD STORY</div>
      </div>
      <div style="padding: 14px 14px 16px;">
        <h1 style="margin: 0 0 8px; font-family: {lead_face}; font-size: 24px; font-weight: 700; line-height: 1.16; text-wrap: pretty;">{lead_title}</h1>
        {lead_dek}
        <div style="font-size: 11px; font-weight: 600; letter-spacing: .4px; color: {muted}; text-transform: uppercase;"><span style="color: {{{{accent}}}};">{lead_source}</span> &middot; {lead_ago} ago</div>
      </div>
    </a>
  </div>

  <div style="padding: 18px 14px 0;">
    <div style="display: flex; align-items: stretch; background: {ink}; margin-bottom: 10px;">
      <div style="width: 8px; background: {{{{accent}}}};"></div>
      <div style="padding: 8px 13px; font-family: {anton}; font-size: 16px; letter-spacing: .9px; color: #ffffff;">NEXT UP</div>
    </div>
    <div style="background: {card}; border: 1px solid {rule}; padding: 0 13px;">{next_rows}</div>
  </div>

  <div style="padding: 18px 14px 0;">
    <div style="display: flex; align-items: stretch; background: {ink}; margin-bottom: 10px;">
      <div style="width: 8px; background: {{{{accent}}}};"></div>
      <div style="padding: 8px 13px; font-family: {anton}; font-size: 16px; letter-spacing: .9px; color: #ffffff;">BOX OFFICE</div>
    </div>
    <div style="display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px;">{cards}</div>
  </div>

  <div style="padding: 18px 14px 0;">
    <div style="display: flex; align-items: stretch; background: {ink}; margin-bottom: 10px;">
      <div style="width: 8px; background: {{{{accent}}}};"></div>
      <div style="padding: 8px 13px; font-family: {anton}; font-size: 16px; letter-spacing: .9px; color: #ffffff;">OTT &amp; STREAMING</div>
    </div>
    <div style="background: {card}; border: 1px solid {rule}; padding: 0 13px;">{dense}</div>
  </div>

  <div style="padding: 18px 14px 0;">
    <div style="background: {{{{accent}}}}; color: #ffffff; padding: 9px 13px; font-family: {anton}; font-size: 16px; letter-spacing: .9px;">TRENDING NAMES</div>
    <div style="background: {card}; border: 1px solid {rule}; border-top: 0; padding: 4px 13px 8px;">{trending}</div>
  </div>

  <div style="margin-top: 20px; background: {ink}; color: #9a9186; padding: 22px 14px;">
    <div style="font-family: {anton}; font-size: 22px; color: #ffffff; letter-spacing: .4px;">KOLLYWOOD<span style="color: {{{{accent}}}};">NOW</span></div>
    <p style="margin: 9px 0 16px; font-size: 12.5px; line-height: 1.6;">Headlines pulled from public feeds, de-duplicated and grouped. Every card links back to the outlet that reported it.</p>
    <div style="display: flex; flex-wrap: wrap; gap: 8px 16px; font-size: 12.5px;">
      <a href="#" style="color: #9a9186;">Top news</a><a href="#" style="color: #9a9186;">Box office</a><a href="#" style="color: #9a9186;">Reviews</a><a href="#" style="color: #9a9186;">Trailers</a><a href="#" style="color: #9a9186;">OTT</a>
    </div>
  </div>

</div>
</x-dc>

<script data-dc-script data-props='{{"accent":{{"editor":"color","default":"#d5301c","options":["#d5301c","#b0182b","#1d6a7a","#16130f"],"section":"Theme"}},"$preview":{{"width":390,"height":2900}}}}'>
class Component extends DCLogic {{
  renderVals() {{
    return {{ accent: this.props.accent ?? '#d5301c' }};
  }}
}}
</script>
</body>
</html>
"""


def main():
    data = load()
    for name, markup in (("Main.dc.html", build_main(data)),
                         ("Mobile.dc.html", build_mobile(data))):
        with open(os.path.join(HERE, name), "w", encoding="utf-8") as handle:
            handle.write(markup)
        print("wrote %s" % name)
    shot = data.get("images", {})
    print("from %d stories, %d with a real photo (%d scraped)"
          % (data["count"], shot.get("total", 0), shot.get("scraped", 0)))


if __name__ == "__main__":
    main()

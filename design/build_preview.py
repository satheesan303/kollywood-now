#!/usr/bin/env python3
"""Render the .dc.html artboards into one plain HTML preview page.

The design canvas normally supplies the runtime that resolves {{holes}} and
the <x-dc> wrapper. This does the same substitution statically so the
artboards can be viewed in any browser:

    python design/build_preview.py     ->  design/preview.html
"""

import html
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "preview.html")

# The values the artboard logic returns for the default "Packed" density.
VALUES = {
    "accent": "#d5301c",
    "secGap": "26px",
    "cardGap": "16px",
    "rowPad": "10px 0",
}

BOARDS = [
    ("Main.dc.html", "Home — desktop", 1440),
    ("Mobile.dc.html", "Home — phone", 390),
    ("Components.dc.html", "The kit", 880),
]

NOTES = [
    ("The brief",
     "Dense Tamil-cinema portal in the genre of the reference: packed category "
     "blocks, thumbnail-left rows, a wide red category bar, a heavy footer. "
     "Behindwoods' own wordmark, logo and branded elements are not copied."),
    ("The headlines",
     "Real stories from the aggregator as of 7 Sep 2026, so the density is "
     "honest — this is what 197 stories across 56 outlets actually looks like."),
    ("The levers",
     "Accent drives the nav bar, section rules, category tags and trending "
     "numbers. Density switches section, card and row spacing between Packed "
     "(shown) and Roomy."),
]


def extract(path):
    """Pull the <helmet> contents and the <x-dc> body out of an artboard."""
    with open(path, "r", encoding="utf-8") as handle:
        source = handle.read()

    helmet = re.search(r"<helmet>(.*?)</helmet>", source, re.S)
    body = re.search(r"<x-dc>(.*?)</x-dc>", source, re.S)
    if not body:
        raise ValueError("no <x-dc> block in %s" % path)

    markup = body.group(1)
    if helmet:
        markup = markup.replace(helmet.group(0), "")

    for name, value in VALUES.items():
        markup = markup.replace("{{%s}}" % name, value)

    leftover = re.findall(r"\{\{\s*([\w.$]+)\s*\}\}", markup)
    if leftover:
        raise ValueError("unresolved holes in %s: %s"
                         % (os.path.basename(path), sorted(set(leftover))))

    return helmet.group(1).strip() if helmet else "", markup.strip()


def main():
    heads, sections = [], []

    for filename, title, width in BOARDS:
        head, markup = extract(os.path.join(HERE, filename))
        heads.append(head)
        sections.append("""
    <section class="board">
      <div class="board-bar">
        <span class="board-name">{title}</span>
        <span class="board-size">{width}px &middot; {filename}</span>
      </div>
      <div class="board-frame" style="width: {width}px;">{markup}</div>
    </section>""".format(title=html.escape(title), width=width,
                         filename=html.escape(filename), markup=markup))

    # every artboard loads the same font link and reset; one copy is enough
    head = heads[0]

    notes = "".join(
        '<div class="note"><b>{h}</b><p>{p}</p></div>'.format(
            h=html.escape(h), p=html.escape(p)) for h, p in NOTES)

    page = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Kollywood Now — portal redesign</title>
{head}
<style>
  body {{ margin: 0; background: #2a2622; font-family: Archivo, system-ui, sans-serif; }}
  .canvas {{ padding: 34px 34px 60px; display: flex; gap: 46px; align-items: flex-start; overflow-x: auto; }}
  .board {{ flex: 0 0 auto; }}
  .board-bar {{ display: flex; align-items: baseline; gap: 12px; margin-bottom: 9px; }}
  .board-name {{ font-family: Anton, Impact, sans-serif; font-size: 17px; letter-spacing: .9px; color: #f3f0ea; }}
  .board-size {{ font-size: 11.5px; color: #8d857b; font-weight: 600; }}
  .board-frame {{ background: #f3f0ea; box-shadow: 0 20px 60px rgba(0,0,0,.45); }}
  .notes {{ display: flex; gap: 20px; padding: 0 34px 60px; max-width: 1180px; }}
  .note {{ flex: 1; background: #35302b; border-left: 3px solid #d5301c; padding: 14px 16px; }}
  .note b {{ display: block; font-size: 12px; letter-spacing: 1.3px; text-transform: uppercase; color: #f3f0ea; margin-bottom: 6px; }}
  .note p {{ margin: 0; font-size: 13px; line-height: 1.6; color: #b3aa9d; }}
</style>
</head>
<body>
  <div class="canvas">{sections}
  </div>
  <div class="notes">{notes}</div>
</body>
</html>
""".format(head=head, sections="".join(sections), notes=notes)

    with open(OUT, "w", encoding="utf-8") as handle:
        handle.write(page)
    print("wrote %s (%.0f KB)" % (OUT, os.path.getsize(OUT) / 1024))


if __name__ == "__main__":
    main()

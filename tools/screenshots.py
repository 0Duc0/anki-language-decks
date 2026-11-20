"""Render real cards (Anki's own renderer, the deck's templates, CSS and fonts) to PNG with headless Chrome.

usage: python3 tools/screenshots.py <collection.anki2> <out_dir> <name>=<search>[:<card ord>][:front] ...
The collection's media folder must hold the fonts the CSS refers to.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

TTS = re.compile(r"\[anki:tts[^\]]*\](.*?)\[/anki:tts\]", re.S)
SOUND = re.compile(r"\[sound:[^\]]+\]|\[anki:play:[aq]:\d+\]")
SPEAKER = '<span style="display:inline-block;width:22px;height:22px;border-radius:50%;background:#e9e4dc;' \
          'text-align:center;line-height:22px;font-size:12px;vertical-align:middle">▶</span>'


def page_html(card_html: str, dark: bool) -> str:
    body = TTS.sub(SPEAKER, card_html)
    body = SOUND.sub(SPEAKER, body)
    cls = "card nightMode" if dark else "card"
    return (f'<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
            f'<style>html,body{{margin:0}}</style></head><body class="{cls}">{body}</body></html>')


def shoot(col_path: str, out_dir: str, specs: list[str], width: int = 760, dark: bool = False,
          open_details: bool = True) -> list[str]:
    from anki.collection import Collection
    from playwright.sync_api import sync_playwright

    col = Collection(col_path)
    media = col.media.dir()
    os.makedirs(out_dir, exist_ok=True)
    made = []
    try:
        with sync_playwright() as p:
            chrome = "/usr/bin/google-chrome" if os.path.exists("/usr/bin/google-chrome") else None
            browser = p.chromium.launch(executable_path=chrome)
            page = browser.new_page(viewport={"width": width, "height": 900}, device_scale_factor=2)
            for spec in specs:
                name, query = spec.split("=", 1)
                parts = query.split("::")
                search, ord_ = parts[0], int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
                front = "front" in parts[1:]
                nids = col.find_notes(search)
                if not nids:
                    print("not found:", search, file=sys.stderr)
                    continue
                cards = {c.ord: c for c in col.get_note(nids[0]).cards()}
                card = cards.get(ord_) or next(iter(cards.values()))
                html = card.question() if front else card.answer()
                tmp = Path(media) / f"_shot_{name}.html"
                tmp.write_text(page_html(html, dark), encoding="utf-8")
                page.goto(tmp.as_uri())
                page.wait_for_timeout(400)
                if open_details:   # show the closed dropdowns (examples, hints) like a user who clicked them
                    page.evaluate("document.querySelectorAll('details.cr-ex, details.cr-prod-hints')"
                                  ".forEach(d => d.open = true)")
                    page.wait_for_timeout(150)
                out = os.path.join(out_dir, f"{name}.png")
                page.screenshot(path=out, full_page=True)
                tmp.unlink()
                made.append(out)
            browser.close()
    finally:
        col.close()
    return made


if __name__ == "__main__":
    dark = "--dark" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--dark"]
    for path in shoot(args[0], args[1], args[2:], dark=dark):
        print(path)

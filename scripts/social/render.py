"""Render card HTML to PNG with a headless browser.

Uses the Chrome already installed on the machine (Playwright's channel="chrome";
GitHub's Ubuntu runners have it too), so no browser is downloaded. Pages load
only local files: the site's own fonts (css/fonts.css) and cards.css.
"""
from __future__ import annotations

from pathlib import Path

from sitedata import HERE, ROOT

FONTS_CSS = (ROOT / "css" / "fonts.css").as_uri()
CARDS_CSS = (HERE / "cards.css").as_uri()


def document(card_html, lang):
    return (f'<!doctype html><html lang="{lang}"><head><meta charset="utf-8">'
            f'<link rel="stylesheet" href="{FONTS_CSS}"><link rel="stylesheet" href="{CARDS_CSS}">'
            f'</head><body>{card_html}</body></html>')


class Renderer:
    def __enter__(self):
        from playwright.sync_api import sync_playwright   # only needed when rendering
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(channel="chrome")
        self._page = self._browser.new_page(viewport={"width": 1600, "height": 1350}, device_scale_factor=1)
        return self

    def __exit__(self, *exc):
        self._browser.close()
        self._pw.stop()

    def png(self, card_html, lang, html_path: Path, png_path: Path):
        html_path.write_text(document(card_html, lang), "utf-8")
        self._page.goto(html_path.as_uri())
        self._page.evaluate("document.fonts.ready")
        self._page.locator(".card").first.screenshot(path=str(png_path))

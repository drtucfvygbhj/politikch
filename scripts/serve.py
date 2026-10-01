#!/usr/bin/env python3
"""Serve the site locally on localhost:8001 (for "Start Politikch" and
the preview in Claude Code). Local only, never published.

Two differences from `python3 -m http.server`:
  * it listens on this computer only (127.0.0.1), not on the whole network;
  * it tells the browser to check every file with the server before reusing
    its copy ("Cache-Control: no-cache"). Locally the data files keep the same
    address (?v=… is only rewritten when the site is deployed), so without this
    a browser can keep showing last week's data for hours after a pull. An
    unchanged file still comes back as a quick "304 Not Modified".

Usage: python3 scripts/serve.py [port]
"""
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOST = "127.0.0.1"


class NoCacheHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8001
    handler = partial(NoCacheHandler, directory=str(ROOT))
    with ThreadingHTTPServer((HOST, port), handler) as httpd:
        print(f"Serving {ROOT.name} at localhost:{port} (this computer only)")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()

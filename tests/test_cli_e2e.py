"""End-to-end CLI tests for frowse (and agent-browser drop-in alias)."""

from __future__ import annotations

import http.server
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        html = """<!doctype html>
        <html>
          <head><title>Frowse Test App</title></head>
          <body>
            <header>
              <nav>
                <a href="/about">About</a>
                <a href="/pricing">Pricing</a>
              </nav>
            </header>
            <main>
              <h1>Welcome to Frowse</h1>
              <form onsubmit="event.preventDefault(); document.getElementById('out').innerText = 'Searched: ' + document.getElementById('q').value + ' | ' + document.getElementById('country').value;">
                <input id="q" type="search" placeholder="Search packages..." />
                <select id="country" aria-label="Country">
                  <option value="US">United States</option>
                  <option value="CA">Canada</option>
                </select>
                <button type="submit">Run Search</button>
              </form>
              <div id="out">idle</div>
            </main>
          </body>
        </html>"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def log_message(self, format, *args):
        return


@pytest.fixture(scope="module")
def test_server():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}"
    srv.shutdown()


def _run_cli(args: list[str], binary: str = "frowse", session: str = "e2e-test") -> dict:
    bin_path = str(Path(sys.executable).parent / binary)
    cmd = [bin_path, "--session", session, "--json", *args]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, f"CLI failed ({proc.returncode}): stdout={proc.stdout} stderr={proc.stderr}"
    payload = json.loads(proc.stdout)
    assert payload["ok"] is True, f"Unexpected error: {payload}"
    return payload["data"]


def test_e2e_frowse_workflow(test_server: str):
    session = f"e2e-{os.getpid()}"
    try:
        # 1. Open page (using agent-browser drop-in alias!)
        opened = _run_cli(["open", test_server], binary="agent-browser", session=session)
        assert opened["title"] == "Frowse Test App"

        # 2. Snapshot returns lightweight Folate-ready DOM summary
        snap = _run_cli(["snapshot"], session=session)
        assert 'input[search] "Search packages..."' in snap["summary"]
        assert '"Run Search"' in snap["summary"]
        assert 'select "Country"' in snap["summary"]

        # 3. Query Folate directly
        qres = _run_cli(["query", "Search packages input", "--top-k", "2"], session=session)
        assert len(qres["matches"]) >= 1
        assert qres["matches"][0]["selector"] == "#q"

        # 4. Fill, select, and click using pure natural-language Folate prompts!
        fill_res = _run_cli(["fill", "Search packages input", "folate-cli"], session=session)
        assert fill_res["resolvedBy"] == "folate"

        sel_res = _run_cli(["select", "Country dropdown", "Canada"], session=session)
        assert sel_res["resolvedBy"] == "folate"

        click_res = _run_cli(["click", "click Run Search button"], session=session)
        assert click_res["resolvedBy"] == "folate"

        # 5. Verify result via explicit CSS selector
        out = _run_cli(["get", "text", "#out"], session=session)
        assert out["text"] == "Searched: folate-cli | CA"

        # 6. Legacy @eN refs mode still works for drop-in compatibility
        refs_snap = _run_cli(["snapshot", "--refs"], session=session)
        assert any(r["ref"] == "@e1" for r in refs_snap["refs"])

        # 7. Tab management
        new_tab = _run_cli(["tab", "new", "--label", "docs", test_server], session=session)
        assert new_tab["label"] == "docs"
        tabs = _run_cli(["tab", "list"], session=session)
        assert len(tabs["tabs"]) == 2
        _run_cli(["tab", "close", "docs"], session=session)
    finally:
        _run_cli(["close"], session=session)

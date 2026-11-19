"""Tests for the lightweight DOM summarizer."""

from __future__ import annotations

import shutil
from playwright.sync_api import sync_playwright

from frowse.summarizer import extract_refs, summarize_dom


def _launch_browser(pw):
    exe = shutil.which("chromium") or shutil.which("google-chrome")
    return pw.chromium.launch(headless=True, executable_path=exe)


def test_summarizer_compresses_repeated_elements():
    cards = "\n".join(
        f'<div class="card"><a href="/item/{i}">Product {i}</a><button>Add to cart</button></div>'
        for i in range(1, 31)
    )
    html = f"""
    <html>
      <head><title>Shop Demo</title></head>
      <body>
        <header>
          <nav aria-label="Main">
            <a href="/">Home</a>
            <a href="/deals">Deals</a>
            <a href="/cart">Cart</a>
          </nav>
          <form role="search" name="site-search">
            <input type="search" placeholder="Search products..." />
            <button type="submit">Search</button>
          </form>
        </header>
        <main>
          <h1>Featured Products</h1>
          {cards}
          <form name="newsletter">
            <label for="email">Email address</label>
            <input id="email" type="email" />
            <select name="country" aria-label="Country">
              <option value="US">United States</option>
              <option value="CA">Canada</option>
              <option value="UK">United Kingdom</option>
            </select>
            <button type="submit">Subscribe</button>
          </form>
        </main>
        <footer>
          <a href="/privacy">Privacy</a>
          <a href="/terms">Terms</a>
        </footer>
      </body>
    </html>
    """
    with sync_playwright() as pw:
        browser = _launch_browser(pw)
        page = browser.new_page()
        page.set_content(html)

        summary = summarize_dom(page)
        refs = extract_refs(page)
        browser.close()

    text = summary["summary"]
    # Repeated "Add to cart" buttons must be deduplicated into a single token with (x30)
    assert '"Add to cart" (x30)' in text
    assert "Product 1" in text
    assert "+22 more" in text
    # Form inputs and select options must be preserved for Folate prompt crafting
    assert 'input[search] "Search products..."' in text
    assert 'input[email] "Email address"' in text
    assert 'select "Country" (United States, Canada, United Kingdom)' in text
    # Summary should be dramatically smaller than a full 68-ref list
    full_refs_len = sum(len(f'{r["ref"]} [{r["role"]}] "{r["label"]}"\n') for r in refs)
    assert len(text) < full_refs_len
    assert len(text) < 1200


def test_summarizer_section_filter_and_hidden_elements():
    html = """
    <html>
      <body>
        <header><a href="/home">Home</a></header>
        <main id="checkout">
          <button>Pay Now</button>
          <button style="display:none">Hidden Button</button>
        </main>
      </body>
    </html>
    """
    with sync_playwright() as pw:
        browser = _launch_browser(pw)
        page = browser.new_page()
        page.set_content(html)

        sec = summarize_dom(page, section="#checkout")
        browser.close()

    assert "Pay Now" in sec["summary"]
    assert "Hidden Button" not in sec["summary"]
    assert "Home" not in sec["summary"]

"""Tests for SelectorResolver and Folate integration."""

from __future__ import annotations

import shutil
from playwright.sync_api import sync_playwright

from frowse.resolver import SelectorResolver, is_explicit_selector, to_playwright_selector


def test_selector_classification():
    assert is_explicit_selector("#submit")
    assert is_explicit_selector(".btn-primary")
    assert is_explicit_selector('input[name="q"]')
    assert is_explicit_selector("//button[@type='submit']")
    assert is_explicit_selector("button")
    assert is_explicit_selector("@e3")

    assert not is_explicit_selector("click Search Flights button")
    assert not is_explicit_selector("Email address input")
    assert not is_explicit_selector("folate:#search")


def test_xpath_normalization():
    assert to_playwright_selector("/html/body/form/button") == "xpath=/html/body/form/button"
    assert to_playwright_selector("//button") == "//button"
    assert to_playwright_selector("#search") == "#search"


def test_folate_resolves_natural_language_prompts():
    html = """
    <html>
      <body>
        <nav>
          <a href="/docs">Documentation</a>
          <a href="/login">Sign in</a>
        </nav>
        <form>
          <input type="search" placeholder="Search documentation..." />
          <button type="submit">Search</button>
        </form>
      </body>
    </html>
    """
    exe = shutil.which("chromium") or shutil.which("google-chrome")
    resolver = SelectorResolver()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, executable_path=exe)
        page = browser.new_page()
        page.set_content(html)

        r_input = resolver.resolve(page, "Search documentation input")
        assert r_input.resolved_by == "folate"
        assert "placeholder" in r_input.selector or "input" in r_input.selector
        assert page.locator(r_input.playwright_selector).count() == 1

        r_link = resolver.resolve(page, "Sign in link")
        assert r_link.resolved_by == "folate"
        assert page.locator(r_link.playwright_selector).inner_text().strip() == "Sign in"

        r_btn = resolver.resolve(page, "click Search button")
        assert r_btn.resolved_by == "folate"
        assert page.locator(r_btn.playwright_selector).inner_text().strip() == "Search"

        browser.close()

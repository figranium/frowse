"""Smart selector resolver for Frowse.

Routes explicit CSS/XPath/@eN selectors directly to Playwright, and routes
natural-language element descriptions (or `folate:` queries) through
FolateSelectorFinder to traverse the live DOM and return a verified selector.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_HTML_TAGS = {
    "a", "article", "aside", "audio", "body", "button", "canvas", "code",
    "details", "dialog", "div", "em", "fieldset", "figcaption", "figure",
    "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6", "head", "header",
    "hr", "html", "i", "iframe", "img", "input", "label", "legend", "li",
    "link", "main", "menu", "nav", "ol", "option", "p", "pre", "section",
    "select", "small", "span", "strong", "summary", "svg", "table", "tbody",
    "td", "textarea", "th", "thead", "title", "tr", "ul", "video",
}

_CSS_COMPOUND_RE = re.compile(
    r"^[a-zA-Z][a-zA-Z0-9-]*"
    r"(\[[^\]]+\]|\.[a-zA-Z_][a-zA-Z0-9_-]*|#[a-zA-Z_][a-zA-Z0-9_-]*|:[a-zA-Z-]+(\([^)]*\))?)+$"
)

_REF_RE = re.compile(r"^@e\d+$")


@dataclass
class ResolvedTarget:
    selector: str
    playwright_selector: str
    resolved_by: str  # "ref" | "selector" | "folate"
    score: float | None = None
    element: str | None = None
    candidates: list[dict[str, Any]] = field(default_factory=list)


def is_ref(sel: str) -> bool:
    return bool(_REF_RE.match(sel.strip()))


def is_explicit_selector(sel: str) -> bool:
    """Return True if `sel` looks like CSS, XPath, or a Playwright engine selector."""
    s = sel.strip()
    if not s:
        return False
    if s.startswith("folate:"):
        return False
    if is_ref(s):
        return True
    if s.startswith(("#", ".", "[", "/", "//", "css=", "xpath=", "text=", "role=", "testid=", "id=", "data-testid=")):
        return True
    if " > " in s or ":nth-" in s or ":has(" in s or ":text(" in s:
        return True
    if _CSS_COMPOUND_RE.match(s):
        return True
    if s.lower() in _HTML_TAGS:
        return True
    return False


def to_playwright_selector(selector: str) -> str:
    """Normalize a Folate-returned selector (CSS or single-slash XPath) for Playwright."""
    s = selector.strip()
    if s.startswith("/") and not s.startswith("//"):
        return f"xpath={s}"
    return s


class SelectorResolver:
    """Resolves @eN refs, explicit selectors, and natural-language Folate prompts."""

    def __init__(self, model_dir: str | None = None):
        self._model_dir = model_dir
        self._finder: Any = None

    @property
    def finder(self) -> Any:
        if self._finder is None:
            from folate import FolateSelectorFinder

            self._finder = FolateSelectorFinder(model_dir=self._model_dir)
        return self._finder

    def query_folate(
        self,
        target: Any,
        prompt: str,
        top_k: int = 3,
        max_candidates: int = 64,
    ) -> list[dict[str, Any]]:
        """Run Folate against the live Page/Frame HTML and return ranked matches."""
        q = prompt.strip()
        if q.startswith("folate:"):
            q = q[len("folate:") :].strip()
        if not q:
            raise ValueError("Folate query prompt cannot be empty")

        page_html = target.content()
        matches = self.finder.rank(
            q,
            page_html,
            top_k=top_k,
            max_candidates=max_candidates,
        )
        for m in matches:
            m["playwright_selector"] = to_playwright_selector(m["selector"])
        return matches

    def resolve(
        self,
        target: Any,
        sel: str,
        refs: dict[str, dict[str, str]] | None = None,
        top_k: int = 5,
        max_candidates: int = 64,
        prefer_visible: bool = True,
    ) -> ResolvedTarget:
        """Resolve a selector, @eN ref, or natural-language Folate prompt."""
        s = sel.strip()
        if not s:
            raise ValueError("Selector cannot be empty")

        if is_ref(s):
            if not refs or s not in refs:
                raise ValueError(
                    f"Unknown ref {s}. Run `snapshot --refs` first or pass a natural-language Folate prompt."
                )
            ref_sel = refs[s]["selector"]
            return ResolvedTarget(
                selector=ref_sel,
                playwright_selector=to_playwright_selector(ref_sel),
                resolved_by="ref",
            )

        if is_explicit_selector(s):
            return ResolvedTarget(
                selector=s,
                playwright_selector=to_playwright_selector(s),
                resolved_by="selector",
            )

        matches = self.query_folate(
            target, s, top_k=top_k, max_candidates=max_candidates
        )
        if not matches:
            raise ValueError(f"Folate found no interactive elements matching: {s!r}")

        fallback: dict[str, Any] | None = None
        for m in matches:
            pw_sel = m["playwright_selector"]
            try:
                loc = target.locator(pw_sel)
                count = loc.count()
            except Exception:
                continue
            if count == 0:
                continue
            if fallback is None:
                fallback = m
            if not prefer_visible:
                return ResolvedTarget(
                    selector=m["selector"],
                    playwright_selector=pw_sel,
                    resolved_by="folate",
                    score=m["score"],
                    element=m["element"],
                    candidates=matches,
                )
            try:
                if loc.first.is_visible():
                    return ResolvedTarget(
                        selector=m["selector"],
                        playwright_selector=pw_sel,
                        resolved_by="folate",
                        score=m["score"],
                        element=m["element"],
                        candidates=matches,
                    )
            except Exception:
                continue

        chosen = fallback or matches[0]
        return ResolvedTarget(
            selector=chosen["selector"],
            playwright_selector=chosen["playwright_selector"],
            resolved_by="folate",
            score=chosen["score"],
            element=chosen["element"],
            candidates=matches,
        )

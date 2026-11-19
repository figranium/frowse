---
name: frowse-extract
description: Extract text, attributes, and structured data with frowse, or hand off verified selectors to a script for bulk scraping.
---

# Frowse Extraction & Bulk Handoff

## Single-Page Extraction

- **Full readable text**: `frowse read` (active tab) or `frowse read <url>` (fetches without launching Chrome).
- **Specific element**: `frowse get text "<folate prompt or CSS>"`, `frowse get attr "<sel>" href`, `frowse get value "<sel>"`, `frowse get count "<sel>"`.
- **DOM queries via JS**: `frowse eval "Array.from(document.querySelectorAll('.card h2')).map(e => e.innerText)"`

## Hybrid Bulk Workflow (Lowest Token Cost)

Never run 50+ `snapshot` turns to scrape a list or paginate a catalog:
1. Run `frowse open <url>` and `frowse snapshot` once.
2. Discover exact CSS selectors via `frowse query "<prompt>" --json`.
3. Write a small Playwright/fetch script using those verified selectors to loop over all items/pages at zero LLM token cost.

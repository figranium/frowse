---
name: frowse
description: Token-lean browser automation using frowse DOM summaries and Folate natural-language element grounding.
---

# Frowse Browser Automation & Folate Prompting

Use `frowse` (or `agent-browser`) to drive headless Chromium with minimal context tokens.

## Core Loop

1. `frowse open <url>`
2. `frowse snapshot` — returns a compact region-by-region DOM summary (not a full tree).
3. Act with a **Folate prompt** directly in `click`, `fill`, `type`, `select`, `hover`, `check`, `get`, `wait`:
   - `frowse fill "Search packages input in header" "folate"`
   - `frowse select "Country dropdown" "Canada"`
   - `frowse click "Run Search button"`
4. `frowse close` when done.

## Writing Perfect Folate Prompts

Folate ranks elements by matching your prompt against `[TAG]`, `[TYPE]`, `[PLACEHOLDER]`, `[ARIA-LABEL]`, `[NAME]`, `[ID]`, `[TEXT]`, and `[PARENT]`.

- **Mirror the summary tokens**: If `snapshot` shows `input[email] "Email address"` under `[form:login]`, write `"Email address email input in form"`, not `"the box where I type my mail"`.
- **Include kind + label + region**: `"Sign in link in nav"`, `"Submit button in dialog"`, `"Country select"`.
- **Avoid filler**: Skip instructions like `"please find and click on the..."` — use concise noun/action phrases.
- **Verify without acting**: Use `frowse query "<prompt>" --top-k 3` to inspect ranked selectors and confidence scores before clicking.

## Handling Edge Cases

- **Collapsed items (`+N more`)**: Query Folate directly if you know the target's name, or browse with `frowse snapshot --section "main"`.
- **Never dump `get text body` / `get html body`**: `body` pulls navbars, footers, and boilerplate. Read only what you need via targeted `get text "#buybox"` / `get text "price in main"` or a compact `eval` returning `{title, price, ...}`.
- **Generic labels on complex pages**: If `"Go"` or `"Submit"` appears in multiple regions, include the landmark (`"Go button in header site-search"`).
- **Repeated buttons (`"Add to cart" (x30)`)**: Click the item's unique title link first (`frowse click "Anker Soundcore Q20i link"`), then `"Add to Cart button"` on the detail page, or use `snapshot --refs` (`click @eN`).
- **Structured output**: Add `--json` to get `{ok, data: {resolvedBy, selector, score, ...}}`.

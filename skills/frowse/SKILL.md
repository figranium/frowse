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

- **Collapsed items (`+N more`)**: If you already know the target's name, query Folate directly (it scans the full DOM). To browse hidden items, scope with `frowse snapshot --section "main"`.
- **Repeated identical buttons (`"Add to cart" (x30)`)**: Folate cannot disambiguate identical buttons across cards/rows. Click the item's unique title/detail link first (e.g. `frowse click "Anker Soundcore Q20i link"`), then click `"Add to Cart button"` on the detail page. If there is no detail page, use `frowse snapshot --refs` (`click @eN`) or a scoped CSS selector.
- **Structured output**: Add `--json` to any command to get `{ok, data: {resolvedBy, selector, score, ...}}`.

---
name: frowse-debug
description: Debug SPAs, iframes, dynamic waits, console logs, page errors, and visual state with frowse.
---

# Frowse Debugging & Verification

## Waiting for Dynamic UI

Prefer deterministic waits over fixed sleeps:
- `frowse wait "<folate prompt or CSS>" --state visible`
- `frowse wait --text "Dashboard"` / `frowse wait --url "**/dashboard"`
- `frowse wait --fn "!document.body.innerText.includes('Loading')"`
- `frowse wait "#spinner" --state hidden`

## Inspecting State & Errors

- `frowse is visible "<sel>"`, `frowse is enabled "<sel>"`, `frowse is checked "<sel>"`
- `frowse console` (`--clear`) and `frowse errors` (`--clear`)
- `frowse screenshot out.png` (`--full` for full page) or `frowse highlight "<sel>"`

## Iframes

- `frowse frame "<iframe selector or prompt>"` → run `snapshot` / `click` / `fill` inside the iframe → `frowse frame main` to return.

## Browser Launch & Environment

- **Missing browser executable**: Frowse auto-detects system Chrome/Chromium and auto-installs Playwright Chromium if absent. To install manually: `~/.frowse/venv/bin/python -m playwright install chromium` (or `python -m playwright install chromium`), or pass `--executable-path /path/to/chrome`.
- **Containers, sandboxes & HTTPS proxies**: If Chromium hits sandbox or `ERR_CERT_AUTHORITY_INVALID` errors, set `FROWSE_IGNORE_HTTPS_ERRORS=1` or launch Chrome directly and attach via CDP:
  `google-chrome --headless=new --no-sandbox --remote-debugging-port=9222 --ignore-certificate-errors about:blank &`
  `frowse --cdp 9222 open <url>`

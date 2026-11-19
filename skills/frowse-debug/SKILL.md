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

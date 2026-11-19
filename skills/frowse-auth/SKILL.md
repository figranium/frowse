---
name: frowse-auth
description: Manage isolated browser sessions, authenticated cookies/storage, CDP attachment, and login flows with frowse.
---

# Frowse Sessions, Auth & State

## Isolated Sessions

- Use `--session <name>` (e.g. `frowse --session work open https://app.example.com`) to keep cookies, tabs, and storage isolated per workflow.
- Shut down all sessions cleanly with `frowse close --all`.

## Reusing Authenticated Browsers

- Attach to an already-logged-in Chrome instance: `frowse --cdp 9222 snapshot`

## Cookies & Web Storage

- `frowse cookies` / `frowse cookies set <name> <val> --http-only` / `frowse cookies clear`
- `frowse storage local [key]` / `frowse storage local set <k> <v>` / `frowse storage session`

## Multi-Tab & Dialog Flows

- `frowse tab new --label oauth https://...`, `frowse tab oauth`, `frowse tab close oauth`
- `alert` and `beforeunload` dialogs auto-accept; handle `confirm`/`prompt` with `frowse dialog status`, `frowse dialog accept [text]`, or `frowse dialog dismiss`.

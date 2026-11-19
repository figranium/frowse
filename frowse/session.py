"""Playwright browser session manager for Frowse."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from playwright.sync_api import Browser, BrowserContext, Frame, Page, Playwright, sync_playwright

from frowse.resolver import ResolvedTarget, SelectorResolver, to_playwright_selector
from frowse.summarizer import extract_refs, summarize_dom

_DEFAULT_TIMEOUT_MS = int(os.environ.get("FROWSE_DEFAULT_TIMEOUT", os.environ.get("AGENT_BROWSER_DEFAULT_TIMEOUT", "15000")))


def _find_browser_executable(explicit_path: str | None = None) -> str | None:
    if explicit_path:
        return explicit_path
    env_path = os.environ.get("FROWSE_EXECUTABLE_PATH") or os.environ.get("AGENT_BROWSER_EXECUTABLE_PATH")
    if env_path and os.path.exists(env_path):
        return env_path
    for candidate in ("chromium", "chromium-browser", "google-chrome", "chrome"):
        found = shutil.which(candidate)
        if found:
            return found
    return None


@dataclass
class TabState:
    tab_id: str
    page: Page
    label: str | None = None
    active_frame: Frame | None = None
    refs: dict[str, dict[str, str]] = field(default_factory=dict)


class BrowserSession:
    """Manages a Playwright browser, tabs, frames, logs, and Folate resolution."""

    def __init__(
        self,
        headed: bool = False,
        executable_path: str | None = None,
        cdp_url: str | None = None,
        timeout_ms: int = _DEFAULT_TIMEOUT_MS,
        user_agent: str | None = None,
        viewport: tuple[int, int] | None = None,
        model_dir: str | None = None,
    ):
        self.headed = headed
        self.executable_path = executable_path
        self.cdp_url = cdp_url
        self.timeout_ms = timeout_ms
        self.user_agent = user_agent
        self.viewport = viewport or (1280, 800)
        self.resolver = SelectorResolver(model_dir=model_dir)

        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._tabs: dict[str, TabState] = {}
        self._tab_counter = 0
        self._active_tab_id: str | None = None

        self._console_logs: list[dict[str, Any]] = []
        self._page_errors: list[dict[str, Any]] = []
        self._pending_dialog: Any = None
        self._pending_dialog_info: dict[str, str] | None = None
        self._auto_dialog = os.environ.get("AGENT_BROWSER_NO_AUTO_DIALOG") != "1"

    def ensure_started(self) -> None:
        if self._context is not None:
            return
        self._pw = sync_playwright().start()
        if self.cdp_url:
            endpoint = self.cdp_url
            if endpoint.isdigit():
                endpoint = f"http://127.0.0.1:{endpoint}"
            self._browser = self._pw.chromium.connect_over_cdp(endpoint)
            if self._browser.contexts:
                self._context = self._browser.contexts[0]
            else:
                self._context = self._browser.new_context(
                    viewport={"width": self.viewport[0], "height": self.viewport[1]},
                    user_agent=self.user_agent,
                )
        else:
            launch_kwargs: dict[str, Any] = {"headless": not self.headed}
            exe = _find_browser_executable(self.executable_path)
            if exe:
                launch_kwargs["executable_path"] = exe
            try:
                self._browser = self._pw.chromium.launch(**launch_kwargs)
            except Exception as exc:
                if exe is None and "Executable doesn't exist" in str(exc):
                    print(
                        "[frowse] No system Chrome/Chromium found; installing Playwright Chromium...",
                        file=sys.stderr,
                    )
                    try:
                        subprocess.run(
                            [sys.executable, "-m", "playwright", "install", "chromium"],
                            check=True,
                        )
                        self._browser = self._pw.chromium.launch(**launch_kwargs)
                    except Exception as install_exc:
                        raise RuntimeError(
                            "Failed to auto-install Chromium. Run "
                            f"`{sys.executable} -m playwright install chromium`, "
                            "or pass `--executable-path <path>` / `--cdp <port>`."
                        ) from install_exc
                else:
                    raise
            ctx_kwargs: dict[str, Any] = {
                "viewport": {"width": self.viewport[0], "height": self.viewport[1]}
            }
            if self.user_agent:
                ctx_kwargs["user_agent"] = self.user_agent
            if (
                os.environ.get("FROWSE_IGNORE_HTTPS_ERRORS") == "1"
                or os.environ.get("AGENT_BROWSER_IGNORE_HTTPS_ERRORS") == "1"
            ):
                ctx_kwargs["ignore_https_errors"] = True
            self._context = self._browser.new_context(**ctx_kwargs)

        self._context.set_default_timeout(self.timeout_ms)
        if self._context.pages:
            for p in self._context.pages:
                self._register_page(p)
        else:
            page = self._context.new_page()
            self._register_page(page)

    def _register_page(self, page: Page, label: str | None = None) -> TabState:
        self._tab_counter += 1
        tid = f"t{self._tab_counter}"
        tab = TabState(tab_id=tid, page=page, label=label)
        self._tabs[tid] = tab
        if self._active_tab_id is None:
            self._active_tab_id = tid

        page.on("console", lambda msg: self._console_logs.append({"type": msg.type, "text": msg.text}))
        page.on("pageerror", lambda err: self._page_errors.append({"message": str(err)}))
        page.on("dialog", self._handle_dialog)
        page.on("close", lambda _p=None: self._on_page_close(tid))
        return tab

    def _on_page_close(self, tid: str) -> None:
        self._tabs.pop(tid, None)
        if self._active_tab_id == tid:
            self._active_tab_id = next(iter(self._tabs), None)

    def _handle_dialog(self, dialog: Any) -> None:
        if self._auto_dialog and dialog.type in ("alert", "beforeunload"):
            try:
                dialog.accept()
                return
            except Exception:
                pass
        self._pending_dialog = dialog
        self._pending_dialog_info = {"type": dialog.type, "message": dialog.message}

    @property
    def active_tab(self) -> TabState:
        self.ensure_started()
        if not self._active_tab_id or self._active_tab_id not in self._tabs:
            page = self._context.new_page()  # type: ignore[union-attr]
            tab = self._register_page(page)
            self._active_tab_id = tab.tab_id
        return self._tabs[self._active_tab_id]

    @property
    def active_page(self) -> Page:
        return self.active_tab.page

    @property
    def active_target(self) -> Page | Frame:
        tab = self.active_tab
        if tab.active_frame is not None and not tab.active_frame.is_detached():
            return tab.active_frame
        tab.active_frame = None
        return tab.page

    def _resolve_locator(self, sel: str, prefer_visible: bool = True) -> tuple[Any, ResolvedTarget]:
        target = self.active_target
        tab = self.active_tab
        resolved = self.resolver.resolve(
            target,
            sel,
            refs=tab.refs,
            prefer_visible=prefer_visible,
        )
        loc = target.locator(resolved.playwright_selector)
        if resolved.resolved_by == "folate" and loc.count() > 1:
            # Prefer first visible element when Folate's selector matches multiple
            for i in range(min(loc.count(), 10)):
                cand = loc.nth(i)
                try:
                    if cand.is_visible():
                        return cand, resolved
                except Exception:
                    continue
        return loc.first, resolved

    def _resolution_meta(self, resolved: ResolvedTarget) -> dict[str, Any]:
        meta: dict[str, Any] = {
            "resolvedBy": resolved.resolved_by,
            "selector": resolved.selector,
        }
        if resolved.score is not None:
            meta["score"] = round(resolved.score, 4)
        if resolved.element is not None:
            meta["element"] = resolved.element
        return meta

    def close(self) -> dict[str, Any]:
        try:
            if self._context is not None and not self.cdp_url:
                self._context.close()
        except Exception:
            pass
        try:
            if self._browser is not None:
                self._browser.close()
        except Exception:
            pass
        try:
            if self._pw is not None:
                self._pw.stop()
        except Exception:
            pass
        self._context = None
        self._browser = None
        self._pw = None
        self._tabs.clear()
        self._active_tab_id = None
        return {"closed": True}

    # --- Command Dispatch ---

    def execute(self, cmd: dict[str, Any]) -> dict[str, Any]:
        action = cmd.get("action", "")
        args = cmd.get("args", {})

        handler = getattr(self, f"_cmd_{action}", None)
        if handler is None:
            raise ValueError(f"Unknown command: {action}")
        res = handler(args)
        if self._pending_dialog_info and action not in ("dialog",):
            res["warning"] = f"Pending {self._pending_dialog_info['type']} dialog: {self._pending_dialog_info['message']}"
        return res

    def _cmd_open(self, args: dict[str, Any]) -> dict[str, Any]:
        self.ensure_started()
        url = args.get("url")
        page = self.active_page
        self.active_tab.active_frame = None
        self.active_tab.refs.clear()
        if url:
            if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", url) and not url.startswith(("about:", "data:", "file:")):
                url = "https://" + url
            page.goto(url, wait_until=args.get("wait_until", "domcontentloaded"))
        return {"url": page.url, "title": page.title()}

    def _cmd_back(self, _args: dict[str, Any]) -> dict[str, Any]:
        self.active_page.go_back()
        return {"url": self.active_page.url, "title": self.active_page.title()}

    def _cmd_forward(self, _args: dict[str, Any]) -> dict[str, Any]:
        self.active_page.go_forward()
        return {"url": self.active_page.url, "title": self.active_page.title()}

    def _cmd_reload(self, _args: dict[str, Any]) -> dict[str, Any]:
        self.active_page.reload()
        return {"url": self.active_page.url, "title": self.active_page.title()}

    def _cmd_close(self, _args: dict[str, Any]) -> dict[str, Any]:
        return self.close()

    def _cmd_snapshot(self, args: dict[str, Any]) -> dict[str, Any]:
        target = self.active_target
        if args.get("refs"):
            refs_list = extract_refs(target, interactive_only=bool(args.get("interactive", True)))
            self.active_tab.refs = {r["ref"]: r for r in refs_list}
            lines = [f'{r["ref"]} [{r["role"]}] "{r["label"]}"' for r in refs_list]
            return {
                "title": self.active_page.title(),
                "url": self.active_page.url,
                "refs": refs_list,
                "summary": "\n".join(lines),
            }
        return summarize_dom(
            target,
            section=args.get("section"),
            max_chars=int(args.get("max_chars", 2200)),
            pending_dialog=self._pending_dialog_info,
        )

    def _cmd_query(self, args: dict[str, Any]) -> dict[str, Any]:
        prompt = args["prompt"]
        top_k = int(args.get("top_k", 3))
        matches = self.resolver.query_folate(self.active_target, prompt, top_k=top_k)
        return {"query": prompt, "matches": matches}

    def _cmd_read(self, args: dict[str, Any]) -> dict[str, Any]:
        url = args.get("url")
        if url and self._context is None:
            if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", url):
                url = "https://" + url
            req = urllib.request.Request(url, headers={"Accept": "text/markdown, text/plain, text/html"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = resp.read().decode("utf-8", errors="replace")
            return {"url": url, "text": body[:8000]}
        if url:
            self._cmd_open({"url": url})
        text = self.active_target.evaluate("() => document.body ? document.body.innerText : ''")
        return {"url": self.active_page.url, "title": self.active_page.title(), "text": text}

    def _cmd_click(self, args: dict[str, Any]) -> dict[str, Any]:
        loc, res = self._resolve_locator(args["selector"])
        if args.get("new_tab"):
            href = loc.get_attribute("href")
            if href:
                new_page = self._context.new_page()  # type: ignore[union-attr]
                tab = self._register_page(new_page)
                self._active_tab_id = tab.tab_id
                new_page.goto(href, wait_until="domcontentloaded")
                return {"clicked": True, "tabId": tab.tab_id, "url": new_page.url, **self._resolution_meta(res)}
        kwargs: dict[str, Any] = {}
        if args.get("button"):
            kwargs["button"] = args["button"]
        if args.get("modifiers"):
            kwargs["modifiers"] = args["modifiers"]
        loc.click(**kwargs)
        return {"clicked": True, **self._resolution_meta(res)}

    def _cmd_dblclick(self, args: dict[str, Any]) -> dict[str, Any]:
        loc, res = self._resolve_locator(args["selector"])
        kwargs: dict[str, Any] = {}
        if args.get("button"):
            kwargs["button"] = args["button"]
        if args.get("modifiers"):
            kwargs["modifiers"] = args["modifiers"]
        loc.dblclick(**kwargs)
        return {"dblclicked": True, **self._resolution_meta(res)}

    def _cmd_fill(self, args: dict[str, Any]) -> dict[str, Any]:
        loc, res = self._resolve_locator(args["selector"])
        loc.fill(args["text"])
        return {"filled": True, **self._resolution_meta(res)}

    def _cmd_type(self, args: dict[str, Any]) -> dict[str, Any]:
        loc, res = self._resolve_locator(args["selector"])
        if args.get("clear"):
            loc.fill("")
        delay = int(args.get("delay", 0))
        loc.press_sequentially(args["text"], delay=delay)
        return {"typed": True, **self._resolution_meta(res)}

    def _cmd_press(self, args: dict[str, Any]) -> dict[str, Any]:
        self.active_page.keyboard.press(args["key"])
        return {"pressed": args["key"]}

    def _cmd_keyboard(self, args: dict[str, Any]) -> dict[str, Any]:
        sub = args["subcommand"]
        kb = self.active_page.keyboard
        if sub == "type":
            kb.type(args["text"])
        elif sub == "inserttext":
            kb.insert_text(args["text"])
        elif sub == "down":
            kb.down(args["key"])
        elif sub == "up":
            kb.up(args["key"])
        else:
            raise ValueError(f"Unknown keyboard subcommand: {sub}")
        return {"ok": True, "subcommand": sub}

    def _cmd_hover(self, args: dict[str, Any]) -> dict[str, Any]:
        loc, res = self._resolve_locator(args["selector"])
        loc.hover()
        return {"hovered": True, **self._resolution_meta(res)}

    def _cmd_focus(self, args: dict[str, Any]) -> dict[str, Any]:
        loc, res = self._resolve_locator(args["selector"])
        loc.focus()
        return {"focused": True, **self._resolution_meta(res)}

    def _cmd_select(self, args: dict[str, Any]) -> dict[str, Any]:
        loc, res = self._resolve_locator(args["selector"])
        val = args["value"]
        try:
            loc.select_option(value=val)
        except Exception:
            loc.select_option(label=val)
        return {"selected": val, **self._resolution_meta(res)}

    def _cmd_check(self, args: dict[str, Any]) -> dict[str, Any]:
        loc, res = self._resolve_locator(args["selector"])
        loc.check()
        return {"checked": True, **self._resolution_meta(res)}

    def _cmd_uncheck(self, args: dict[str, Any]) -> dict[str, Any]:
        loc, res = self._resolve_locator(args["selector"])
        loc.uncheck()
        return {"unchecked": True, **self._resolution_meta(res)}

    def _cmd_scroll(self, args: dict[str, Any]) -> dict[str, Any]:
        direction = args.get("direction", "down")
        px = int(args.get("px", 500))
        dx, dy = 0, 0
        if direction == "down":
            dy = px
        elif direction == "up":
            dy = -px
        elif direction == "right":
            dx = px
        elif direction == "left":
            dx = -px
        else:
            raise ValueError(f"Invalid scroll direction: {direction}")

        sel = args.get("selector")
        if sel:
            loc, res = self._resolve_locator(sel)
            loc.evaluate("(el, [dx, dy]) => el.scrollBy(dx, dy)", [dx, dy])
            return {"scrolled": direction, "px": px, **self._resolution_meta(res)}
        self.active_page.mouse.wheel(dx, dy)
        return {"scrolled": direction, "px": px}

    def _cmd_scrollintoview(self, args: dict[str, Any]) -> dict[str, Any]:
        loc, res = self._resolve_locator(args["selector"], prefer_visible=False)
        loc.scroll_into_view_if_needed()
        return {"scrolledIntoView": True, **self._resolution_meta(res)}

    def _cmd_drag(self, args: dict[str, Any]) -> dict[str, Any]:
        src_loc, src_res = self._resolve_locator(args["source"])
        dst_loc, dst_res = self._resolve_locator(args["target"])
        src_loc.drag_to(dst_loc)
        return {"dragged": True, "source": self._resolution_meta(src_res), "target": self._resolution_meta(dst_res)}

    def _cmd_upload(self, args: dict[str, Any]) -> dict[str, Any]:
        loc, res = self._resolve_locator(args["selector"], prefer_visible=False)
        loc.set_input_files(args["files"])
        return {"uploaded": args["files"], **self._resolution_meta(res)}

    def _cmd_get(self, args: dict[str, Any]) -> dict[str, Any]:
        prop = args["prop"]
        if prop == "title":
            return {"title": self.active_page.title()}
        if prop == "url":
            return {"url": self.active_page.url}

        loc, res = self._resolve_locator(args["selector"], prefer_visible=(prop != "count"))
        meta = self._resolution_meta(res)
        if prop == "text":
            return {"text": loc.inner_text(), **meta}
        if prop == "html":
            return {"html": loc.inner_html(), **meta}
        if prop == "value":
            return {"value": loc.input_value(), **meta}
        if prop == "attr":
            return {"value": loc.get_attribute(args["attr"]), **meta}
        if prop == "count":
            count = self.active_target.locator(res.playwright_selector).count()
            return {"count": count, **meta}
        if prop == "box":
            return {"box": loc.bounding_box(), **meta}
        if prop == "styles":
            styles = loc.evaluate("el => Object.fromEntries(Array.from(getComputedStyle(el)).map(k => [k, getComputedStyle(el).getPropertyValue(k)]))")
            return {"styles": styles, **meta}
        raise ValueError(f"Unknown get property: {prop}")

    def _cmd_is(self, args: dict[str, Any]) -> dict[str, Any]:
        prop = args["prop"]
        loc, res = self._resolve_locator(args["selector"], prefer_visible=False)
        meta = self._resolution_meta(res)
        if prop == "visible":
            return {"visible": loc.is_visible(), **meta}
        if prop == "enabled":
            return {"enabled": loc.is_enabled(), **meta}
        if prop == "checked":
            return {"checked": loc.is_checked(), **meta}
        raise ValueError(f"Unknown state check: {prop}")

    def _cmd_find(self, args: dict[str, Any]) -> dict[str, Any]:
        by = args["by"]
        target_val = args["value"]
        action = args["find_action"]
        action_val = args.get("action_value")
        exact = bool(args.get("exact", False))
        name = args.get("name")
        t = self.active_target

        if by == "role":
            loc = t.get_by_role(target_val, name=name, exact=exact)
        elif by == "text":
            loc = t.get_by_text(target_val, exact=exact)
        elif by == "label":
            loc = t.get_by_label(target_val, exact=exact)
        elif by == "placeholder":
            loc = t.get_by_placeholder(target_val, exact=exact)
        elif by == "alt":
            loc = t.get_by_alt_text(target_val, exact=exact)
        elif by == "title":
            loc = t.get_by_title(target_val, exact=exact)
        elif by == "testid":
            loc = t.get_by_test_id(target_val)
        elif by == "first":
            loc = t.locator(to_playwright_selector(target_val)).first
        elif by == "last":
            loc = t.locator(to_playwright_selector(target_val)).last
        elif by == "nth":
            loc = t.locator(to_playwright_selector(target_val)).nth(int(args["index"]))
        else:
            raise ValueError(f"Unknown find locator: {by}")

        el = loc.first
        if action == "click":
            el.click()
            return {"clicked": True}
        if action == "fill":
            el.fill(action_val or "")
            return {"filled": True}
        if action == "check":
            el.check()
            return {"checked": True}
        if action == "hover":
            el.hover()
            return {"hovered": True}
        if action == "text":
            return {"text": el.inner_text()}
        raise ValueError(f"Unknown find action: {action}")

    def _cmd_wait(self, args: dict[str, Any]) -> dict[str, Any]:
        page = self.active_page
        if args.get("ms") is not None:
            time.sleep(int(args["ms"]) / 1000.0)
            return {"waitedMs": int(args["ms"])}
        if args.get("text"):
            page.get_by_text(args["text"]).first.wait_for(state="visible")
            return {"waitedForText": args["text"]}
        if args.get("url"):
            page.wait_for_url(args["url"])
            return {"url": page.url}
        if args.get("load"):
            page.wait_for_load_state(args["load"])
            return {"loadState": args["load"]}
        if args.get("fn"):
            page.wait_for_function(args["fn"])
            return {"waitedForFn": True}
        if args.get("selector"):
            state = args.get("state", "visible")
            loc, res = self._resolve_locator(args["selector"], prefer_visible=(state == "visible"))
            loc.wait_for(state=state)
            return {"waited": True, "state": state, **self._resolution_meta(res)}
        raise ValueError("wait requires a selector, milliseconds, or --text/--url/--load/--fn")

    def _cmd_screenshot(self, args: dict[str, Any]) -> dict[str, Any]:
        path = args.get("path") or f"screenshot-{int(time.time())}.png"
        self.active_page.screenshot(path=path, full_page=bool(args.get("full", False)))
        return {"path": os.path.abspath(path)}

    def _cmd_pdf(self, args: dict[str, Any]) -> dict[str, Any]:
        path = args["path"]
        self.active_page.pdf(path=path)
        return {"path": os.path.abspath(path)}

    def _cmd_eval(self, args: dict[str, Any]) -> dict[str, Any]:
        result = self.active_target.evaluate(args["js"])
        return {"result": result}

    def _cmd_tab(self, args: dict[str, Any]) -> dict[str, Any]:
        self.ensure_started()
        sub = args.get("subcommand", "list")
        if sub == "list":
            tabs = [
                {
                    "tabId": t.tab_id,
                    "label": t.label,
                    "active": t.tab_id == self._active_tab_id,
                    "url": t.page.url,
                    "title": t.page.title(),
                }
                for t in self._tabs.values()
            ]
            return {"tabs": tabs}
        if sub == "new":
            label = args.get("label")
            if label:
                if any(t.label == label for t in self._tabs.values()):
                    raise ValueError(f"Tab label already exists: {label}")
            page = self._context.new_page()  # type: ignore[union-attr]
            tab = self._register_page(page, label=label)
            self._active_tab_id = tab.tab_id
            url = args.get("url")
            if url:
                if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", url):
                    url = "https://" + url
                page.goto(url, wait_until="domcontentloaded")
            return {"tabId": tab.tab_id, "label": tab.label, "url": page.url}
        if sub == "close":
            target_ref = args.get("target") or self._active_tab_id
            tab = self._find_tab(target_ref)
            tab.page.close()
            return {"closed": tab.tab_id}
        if sub == "switch":
            tab = self._find_tab(args["target"])
            self._active_tab_id = tab.tab_id
            tab.page.bring_to_front()
            return {"tabId": tab.tab_id, "label": tab.label, "url": tab.page.url}
        raise ValueError(f"Unknown tab subcommand: {sub}")

    def _find_tab(self, ref: str | None) -> TabState:
        if not ref:
            return self.active_tab
        for t in self._tabs.values():
            if t.tab_id == ref or (t.label and t.label == ref):
                return t
        raise ValueError(f"Tab not found: {ref}")

    def _cmd_frame(self, args: dict[str, Any]) -> dict[str, Any]:
        sel = args["selector"]
        tab = self.active_tab
        if sel == "main":
            tab.active_frame = None
            return {"frame": "main"}
        loc, res = self._resolve_locator(sel, prefer_visible=False)
        el_handle = loc.element_handle()
        frame = el_handle.content_frame() if el_handle else None
        if frame is None:
            raise ValueError(f"Element is not an iframe: {sel}")
        tab.active_frame = frame
        return {"frame": frame.url or frame.name or res.selector}

    def _cmd_cookies(self, args: dict[str, Any]) -> dict[str, Any]:
        self.ensure_started()
        op = args.get("op", "get")
        if op == "get":
            return {"cookies": self._context.cookies()}  # type: ignore[union-attr]
        if op == "clear":
            self._context.clear_cookies()  # type: ignore[union-attr]
            return {"cleared": True}
        if op == "set":
            cookie: dict[str, Any] = {
                "name": args["name"],
                "value": args["value"],
                "url": self.active_page.url if self.active_page.url.startswith("http") else "http://localhost",
            }
            if args.get("http_only"):
                cookie["httpOnly"] = True
            if args.get("same_site"):
                cookie["sameSite"] = args["same_site"]
            self._context.add_cookies([cookie])  # type: ignore[union-attr]
            return {"set": args["name"]}
        raise ValueError(f"Unknown cookies op: {op}")

    def _cmd_storage(self, args: dict[str, Any]) -> dict[str, Any]:
        kind = "localStorage" if args["kind"] == "local" else "sessionStorage"
        op = args.get("op", "get")
        page = self.active_page
        if op == "get":
            key = args.get("key")
            if key:
                val = page.evaluate("([k, key]) => window[k].getItem(key)", [kind, key])
                return {"key": key, "value": val}
            data = page.evaluate("(k) => Object.assign({}, window[k])", kind)
            return {"storage": data}
        if op == "set":
            page.evaluate("([k, key, val]) => window[k].setItem(key, val)", [kind, args["key"], args["value"]])
            return {"set": args["key"]}
        if op == "clear":
            page.evaluate("(k) => window[k].clear()", kind)
            return {"cleared": True}
        raise ValueError(f"Unknown storage op: {op}")

    def _cmd_dialog(self, args: dict[str, Any]) -> dict[str, Any]:
        op = args["op"]
        if op == "status":
            return {"pending": self._pending_dialog_info}
        if not self._pending_dialog:
            raise ValueError("No pending dialog")
        dlg = self._pending_dialog
        self._pending_dialog = None
        self._pending_dialog_info = None
        if op == "accept":
            dlg.accept(args.get("text"))
            return {"accepted": True}
        if op == "dismiss":
            dlg.dismiss()
            return {"dismissed": True}
        raise ValueError(f"Unknown dialog op: {op}")

    def _cmd_console(self, args: dict[str, Any]) -> dict[str, Any]:
        if args.get("clear"):
            self._console_logs.clear()
            return {"cleared": True}
        return {"messages": list(self._console_logs)}

    def _cmd_errors(self, args: dict[str, Any]) -> dict[str, Any]:
        if args.get("clear"):
            self._page_errors.clear()
            return {"cleared": True}
        return {"errors": list(self._page_errors)}

    def _cmd_highlight(self, args: dict[str, Any]) -> dict[str, Any]:
        loc, res = self._resolve_locator(args["selector"])
        loc.highlight()
        return {"highlighted": True, **self._resolution_meta(res)}

"""agent-browser-compatible CLI for Frowse."""

from __future__ import annotations

import json
import os
import sys
from typing import Any

from frowse import __version__
from frowse.client import close_all_sessions, send_command
from frowse.skills import install_skills, list_skills, read_skill


def _split_global_flags(argv: list[str]) -> tuple[dict[str, Any], list[str]]:
    """Extract global flags while preserving `--` literal marker."""
    opts: dict[str, Any] = {
        "json": False,
        "session": os.environ.get("FROWSE_SESSION", os.environ.get("AGENT_BROWSER_SESSION", "default")),
        "headed": False,
        "timeout": int(os.environ.get("FROWSE_DEFAULT_TIMEOUT", os.environ.get("AGENT_BROWSER_DEFAULT_TIMEOUT", "15000"))),
        "cdp": None,
        "executable_path": None,
        "user_agent": None,
        "viewport": None,
        "model_dir": os.environ.get("FROWSE_MODEL_DIR"),
    }
    rest: list[str] = []
    i = 0
    saw_double_dash = False
    while i < len(argv):
        tok = argv[i]
        if tok == "--":
            saw_double_dash = True
            rest.extend(argv[i:])
            break
        if tok == "--json":
            opts["json"] = True
            i += 1
        elif tok == "--headed":
            opts["headed"] = True
            i += 1
        elif tok == "--session" and i + 1 < len(argv):
            opts["session"] = argv[i + 1]
            i += 2
        elif tok == "--timeout" and i + 1 < len(argv):
            opts["timeout"] = int(argv[i + 1])
            i += 2
        elif tok == "--cdp" and i + 1 < len(argv):
            opts["cdp"] = argv[i + 1]
            i += 2
        elif tok == "--executable-path" and i + 1 < len(argv):
            opts["executable_path"] = argv[i + 1]
            i += 2
        elif tok == "--user-agent" and i + 1 < len(argv):
            opts["user_agent"] = argv[i + 1]
            i += 2
        elif tok == "--viewport" and i + 1 < len(argv):
            opts["viewport"] = argv[i + 1]
            i += 2
        elif tok == "--model-dir" and i + 1 < len(argv):
            opts["model_dir"] = argv[i + 1]
            i += 2
        else:
            rest.append(tok)
            i += 1
    _ = saw_double_dash
    return opts, rest


def _parse_fill_or_type(args: list[str], is_type: bool = False) -> dict[str, Any]:
    clear = False
    delay = 0
    pos: list[str] = []
    i = 0
    while i < len(args):
        tok = args[i]
        if tok == "--":
            pos.extend(args[i + 1 :])
            break
        if is_type and tok == "--clear":
            clear = True
            i += 1
        elif is_type and tok == "--delay" and i + 1 < len(args):
            delay = int(args[i + 1])
            i += 2
        else:
            pos.append(tok)
            i += 1
    if len(pos) < 2:
        raise ValueError("Usage: <selector> <text>")
    res: dict[str, Any] = {"selector": pos[0], "text": " ".join(pos[1:])}
    if is_type:
        res["clear"] = clear
        res["delay"] = delay
    return res


def _parse_command(rest: list[str]) -> tuple[str, dict[str, Any]]:
    if not rest:
        raise ValueError("No command provided. Run `frowse --help` for usage.")

    cmd = rest[0]
    args = rest[1:]

    # Aliases
    alias_map = {
        "goto": "open",
        "navigate": "open",
        "quit": "close",
        "exit": "close",
        "summary": "snapshot",
        "folate": "query",
        "key": "press",
    }
    cmd = alias_map.get(cmd, cmd)

    if cmd == "open":
        return "open", {"url": args[0] if args else None}

    if cmd in ("back", "forward", "reload"):
        return cmd, {}

    if cmd == "close":
        return "close", {"all": "--all" in args}

    if cmd == "snapshot":
        payload: dict[str, Any] = {"refs": False, "interactive": True, "max_chars": 2200}
        i = 0
        while i < len(args):
            t = args[i]
            if t in ("--refs", "--full"):
                payload["refs"] = True
            elif t in ("-i", "--interactive"):
                payload["interactive"] = True
            elif t == "--section" and i + 1 < len(args):
                payload["section"] = args[i + 1]
                i += 1
            elif t == "--max-chars" and i + 1 < len(args):
                payload["max_chars"] = int(args[i + 1])
                i += 1
            i += 1
        return "snapshot", payload

    if cmd == "query":
        top_k = 3
        prompt_parts: list[str] = []
        i = 0
        while i < len(args):
            if args[i] == "--top-k" and i + 1 < len(args):
                top_k = int(args[i + 1])
                i += 2
            else:
                prompt_parts.append(args[i])
                i += 1
        if not prompt_parts:
            raise ValueError("Usage: query <prompt> [--top-k N]")
        return "query", {"prompt": " ".join(prompt_parts), "top_k": top_k}

    if cmd == "read":
        return "read", {"url": args[0] if args else None}

    if cmd in ("click", "dblclick"):
        payload = {}
        pos: list[str] = []
        i = 0
        while i < len(args):
            t = args[i]
            if t == "--new-tab":
                payload["new_tab"] = True
            elif t == "--button" and i + 1 < len(args):
                payload["button"] = args[i + 1]
                i += 1
            elif t == "--modifiers" and i + 1 < len(args):
                mods = [m.strip() for m in args[i + 1].replace("+", ",").split(",") if m.strip()]
                payload["modifiers"] = [
                    "Control" if m in ("ctrl", "control") else "Meta" if m in ("cmd", "command", "meta") else m.capitalize()
                    for m in mods
                ]
                i += 1
            else:
                pos.append(t)
            i += 1
        if not pos:
            raise ValueError(f"Usage: {cmd} <selector>")
        payload["selector"] = " ".join(pos)
        return cmd, payload

    if cmd == "fill":
        return "fill", _parse_fill_or_type(args, is_type=False)

    if cmd == "type":
        return "type", _parse_fill_or_type(args, is_type=True)

    if cmd == "press":
        if not args:
            raise ValueError("Usage: press <key>")
        return "press", {"key": args[0]}

    if cmd == "keyboard":
        if len(args) < 2:
            raise ValueError("Usage: keyboard <type|inserttext|down|up> <value>")
        sub = args[0]
        val = " ".join(args[1:])
        if sub in ("type", "inserttext"):
            return "keyboard", {"subcommand": sub, "text": val}
        return "keyboard", {"subcommand": sub, "key": val}

    if cmd in ("hover", "focus", "check", "uncheck", "scrollintoview", "highlight"):
        if not args:
            raise ValueError(f"Usage: {cmd} <selector>")
        return cmd, {"selector": " ".join(args)}

    if cmd == "select":
        if len(args) < 2:
            raise ValueError("Usage: select <selector> <value>")
        return "select", {"selector": args[0], "value": " ".join(args[1:])}

    if cmd == "scroll":
        if not args:
            raise ValueError("Usage: scroll <up|down|left|right> [px] [--selector <sel>]")
        payload = {"direction": args[0], "px": 500}
        i = 1
        while i < len(args):
            if args[i] == "--selector" and i + 1 < len(args):
                payload["selector"] = args[i + 1]
                i += 2
            elif args[i].lstrip("-").isdigit():
                payload["px"] = int(args[i])
                i += 1
            else:
                i += 1
        return "scroll", payload

    if cmd == "drag":
        if len(args) < 2:
            raise ValueError("Usage: drag <src> <dst>")
        return "drag", {"source": args[0], "target": args[1]}

    if cmd == "upload":
        if len(args) < 2:
            raise ValueError("Usage: upload <selector> <files...>")
        return "upload", {"selector": args[0], "files": args[1:]}

    if cmd == "get":
        if not args:
            raise ValueError("Usage: get <text|html|value|attr|title|url|count|box|styles> [selector]")
        prop = args[0]
        if prop in ("title", "url"):
            return "get", {"prop": prop}
        if prop == "attr":
            if len(args) < 3:
                raise ValueError("Usage: get attr <selector> <attr>")
            return "get", {"prop": "attr", "selector": args[1], "attr": args[2]}
        if len(args) < 2:
            raise ValueError(f"Usage: get {prop} <selector>")
        return "get", {"prop": prop, "selector": " ".join(args[1:])}

    if cmd == "is":
        if len(args) < 2:
            raise ValueError("Usage: is <visible|enabled|checked> <selector>")
        return "is", {"prop": args[0], "selector": " ".join(args[1:])}

    if cmd == "find":
        if len(args) < 3:
            raise ValueError("Usage: find <by> <value> <action> [action_value]")
        by = args[0]
        exact = "--exact" in args
        name = None
        clean_args: list[str] = []
        i = 1
        while i < len(args):
            if args[i] == "--exact":
                i += 1
            elif args[i] == "--name" and i + 1 < len(args):
                name = args[i + 1]
                i += 2
            else:
                clean_args.append(args[i])
                i += 1
        if by == "nth":
            if len(clean_args) < 3:
                raise ValueError("Usage: find nth <n> <sel> <action> [value]")
            return "find", {
                "by": by,
                "index": int(clean_args[0]),
                "value": clean_args[1],
                "find_action": clean_args[2],
                "action_value": " ".join(clean_args[3:]) if len(clean_args) > 3 else None,
                "exact": exact,
                "name": name,
            }
        return "find", {
            "by": by,
            "value": clean_args[0],
            "find_action": clean_args[1],
            "action_value": " ".join(clean_args[2:]) if len(clean_args) > 2 else None,
            "exact": exact,
            "name": name,
        }

    if cmd == "wait":
        if not args:
            raise ValueError("Usage: wait <selector|ms|--text|--url|--load|--fn>")
        payload = {}
        i = 0
        pos = []
        while i < len(args):
            t = args[i]
            if t == "--text" and i + 1 < len(args):
                payload["text"] = args[i + 1]
                i += 2
            elif t == "--url" and i + 1 < len(args):
                payload["url"] = args[i + 1]
                i += 2
            elif t == "--load" and i + 1 < len(args):
                payload["load"] = args[i + 1]
                i += 2
            elif t == "--fn" and i + 1 < len(args):
                payload["fn"] = args[i + 1]
                i += 2
            elif t == "--state" and i + 1 < len(args):
                payload["state"] = args[i + 1]
                i += 2
            else:
                pos.append(t)
                i += 1
        if pos and not any(k in payload for k in ("text", "url", "load", "fn")):
            if len(pos) == 1 and pos[0].isdigit():
                payload["ms"] = int(pos[0])
            else:
                payload["selector"] = " ".join(pos)
        return "wait", payload

    if cmd == "screenshot":
        full = "--full" in args
        pos = [a for a in args if not a.startswith("--")]
        return "screenshot", {"path": pos[0] if pos else None, "full": full}

    if cmd == "pdf":
        if not args:
            raise ValueError("Usage: pdf <path>")
        return "pdf", {"path": args[0]}

    if cmd == "eval":
        if not args:
            raise ValueError("Usage: eval <js>")
        return "eval", {"js": " ".join(args)}

    if cmd == "tab":
        if not args or args[0] == "list":
            return "tab", {"subcommand": "list"}
        if args[0] == "new":
            label = None
            url = None
            i = 1
            while i < len(args):
                if args[i] == "--label" and i + 1 < len(args):
                    label = args[i + 1]
                    i += 2
                else:
                    url = args[i]
                    i += 1
            return "tab", {"subcommand": "new", "label": label, "url": url}
        if args[0] == "close":
            return "tab", {"subcommand": "close", "target": args[1] if len(args) > 1 else None}
        return "tab", {"subcommand": "switch", "target": args[0]}

    if cmd == "frame":
        if not args:
            raise ValueError("Usage: frame <selector|@ref|main>")
        return "frame", {"selector": " ".join(args)}

    if cmd == "cookies":
        if not args or args[0] == "get":
            return "cookies", {"op": "get"}
        if args[0] == "clear":
            return "cookies", {"op": "clear"}
        if args[0] == "set" and len(args) >= 3:
            return "cookies", {
                "op": "set",
                "name": args[1],
                "value": args[2],
                "http_only": "--http-only" in args or "--httpOnly" in args,
            }
        raise ValueError("Usage: cookies [get|set <name> <val>|clear]")

    if cmd == "storage":
        if not args or args[0] not in ("local", "session"):
            raise ValueError("Usage: storage <local|session> [key|set <k> <v>|clear]")
        kind = args[0]
        sub = args[1:]
        if not sub:
            return "storage", {"kind": kind, "op": "get"}
        if sub[0] == "clear":
            return "storage", {"kind": kind, "op": "clear"}
        if sub[0] == "set" and len(sub) >= 3:
            return "storage", {"kind": kind, "op": "set", "key": sub[1], "value": sub[2]}
        return "storage", {"kind": kind, "op": "get", "key": sub[0]}

    if cmd == "dialog":
        if not args:
            raise ValueError("Usage: dialog <accept [text]|dismiss|status>")
        op = args[0]
        return "dialog", {"op": op, "text": " ".join(args[1:]) if len(args) > 1 else None}

    if cmd in ("console", "errors"):
        return cmd, {"clear": "--clear" in args}

    raise ValueError(f"Unknown command: {cmd}")


def _format_plain(action: str, data: dict[str, Any]) -> str:
    if "summary" in data:
        out = data["summary"]
        if data.get("warning"):
            out = f"[Warning: {data['warning']}]\n{out}"
        return out
    if action == "query":
        lines = []
        for i, m in enumerate(data.get("matches", []), 1):
            lines.append(f"{i}. [{m['score']:.3f}] {m['selector']}  |  {m['element']}")
        return "\n".join(lines) if lines else "No matching elements found."
    if action == "open":
        return f"Opened {data.get('url', '')} ({data.get('title', '')})"
    if action == "read":
        return data.get("text", "")
    if action == "get":
        for k in ("text", "html", "value", "title", "url", "count"):
            if k in data:
                return str(data[k])
        return json.dumps(data, indent=2)
    if action == "is":
        for k in ("visible", "enabled", "checked"):
            if k in data:
                return "true" if data[k] else "false"
    if action == "eval":
        res = data.get("result")
        return json.dumps(res) if isinstance(res, (dict, list)) else str(res)
    if action == "tab" and "tabs" in data:
        lines = []
        for t in data["tabs"]:
            mark = "*" if t["active"] else " "
            lbl = f" ({t['label']})" if t.get("label") else ""
            lines.append(f"{mark} {t['tabId']}{lbl}: {t['url']} - {t['title']}")
        return "\n".join(lines)
    if data.get("resolvedBy") == "folate":
        return f"ok [folate: {data.get('selector')} ({data.get('score')})]"
    return json.dumps(data)


def _print_help() -> None:
    print(
        f"""frowse {__version__} — Drop-in replacement for agent-browser powered by Folate

Usage: frowse [global-options] <command> [args...]

Core Workflow:
  open <url>                    Launch browser & navigate (aliases: goto, navigate)
  snapshot [--section <sel>]    Lightweight Folate-ready DOM summary (alias: summary)
  snapshot --refs               Legacy @eN refs mode for compatibility
  query <prompt> [--top-k N]    Query Folate directly for ranked CSS/XPath selectors
  click <sel|prompt>            Click element (CSS, XPath, @eN, or Folate prompt)
  fill <sel|prompt> <text>      Clear and fill input
  type <sel|prompt> <text>      Type into element
  select <sel|prompt> <val>     Select dropdown option
  get <text|html|value|attr|title|url|count|box|styles> [sel|prompt]
  is <visible|enabled|checked> <sel|prompt>
  wait <sel|ms|--text|--url|--load|--fn>
  screenshot [path] [--full]
  eval <js>
  tab [new|close|<id|label>]
  frame <sel|@ref|main>
  skills [list|show|install]    Manage bundled Folate & browser skills
  close [--all]

Global Options:
  --json                        Output structured JSON
  --session <name>              Isolated session name (default: default)
  --headed                      Show browser window
  --timeout <ms>                Default timeout in ms (default: 15000)
  --cdp <port|url>              Connect to existing browser over CDP
  --viewport <w>x<h>            Viewport size (default: 1280x800)
  --model-dir <path>            Local Folate ONNX model directory"""
    )


def _run_skills_cli(args: list[str]) -> tuple[dict[str, Any], str]:
    sub = args[0] if args else "list"
    rest = args[1:]
    if sub == "list":
        items = list_skills()
        plain = "\n".join(f"{s['name']}: {s['description']}" for s in items)
        return {"skills": items}, plain
    if sub == "show":
        if not rest:
            raise ValueError("Usage: skills show <name>")
        content = read_skill(rest[0])
        return {"name": rest[0], "content": content}, content
    if sub == "install":
        target = "agents"
        global_install = False
        dest_dir = None
        names: list[str] = []
        i = 0
        while i < len(rest):
            t = rest[i]
            if t == "--global":
                global_install = True
                i += 1
            elif t == "--target" and i + 1 < len(rest):
                target = rest[i + 1]
                i += 2
            elif t == "--dir" and i + 1 < len(rest):
                dest_dir = rest[i + 1]
                i += 2
            else:
                names.append(t)
                i += 1
        installed = install_skills(
            target=target,
            global_install=global_install,
            names=names or None,
            dest_dir=dest_dir,
        )
        plain = "\n".join(f"Installed {x['name']} -> {x['path']}" for x in installed)
        return {"installed": installed}, plain
    raise ValueError("Usage: skills [list|show <name>|install [--target agents|claude|codex|cursor] [--global] [names...]]")


def main(argv: list[str] | None = None) -> None:
    raw = sys.argv[1:] if argv is None else argv
    if not raw or raw[0] in ("-h", "--help", "help"):
        _print_help()
        sys.exit(0 if raw else 1)
    if raw[0] in ("-V", "--version"):
        print(f"frowse {__version__}")
        sys.exit(0)

    opts, rest = _split_global_flags(raw)
    try:
        if rest and rest[0] == "skills":
            data, plain = _run_skills_cli(rest[1:])
            if opts["json"]:
                print(json.dumps({"ok": True, "data": data}))
            else:
                print(plain)
            return

        action, payload = _parse_command(rest)
        if action == "close" and payload.get("all"):
            closed = close_all_sessions()
            data = {"closed": closed}
        else:
            daemon_opts = {
                "headed": opts["headed"],
                "executable_path": opts["executable_path"],
                "cdp_url": opts["cdp"],
                "timeout_ms": opts["timeout"],
                "user_agent": opts["user_agent"],
                "viewport": opts["viewport"],
                "model_dir": opts["model_dir"],
            }
            data = send_command(
                session_name=opts["session"],
                action=action,
                args=payload,
                daemon_opts=daemon_opts,
            )

        if opts["json"]:
            print(json.dumps({"ok": True, "data": data}))
        else:
            print(_format_plain(action, data))
    except Exception as exc:
        if opts["json"]:
            print(json.dumps({"ok": False, "error": str(exc)}))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

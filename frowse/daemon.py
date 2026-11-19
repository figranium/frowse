"""Persistent per-session Unix socket daemon for Frowse."""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import sys
import tempfile
from typing import Any

from frowse.session import BrowserSession


def get_state_dir() -> str:
    base = os.environ.get("FROWSE_STATE_DIR") or os.path.join(
        tempfile.gettempdir(), f"frowse-{os.getuid()}"
    )
    os.makedirs(base, mode=0o700, exist_ok=True)
    return base


def get_socket_path(session_name: str) -> str:
    safe = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in session_name)
    return os.path.join(get_state_dir(), f"{safe}.sock")


def get_pid_path(session_name: str) -> str:
    safe = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in session_name)
    return os.path.join(get_state_dir(), f"{safe}.pid")


def _cleanup_files(sock_path: str, pid_path: str) -> None:
    for p in (sock_path, pid_path):
        try:
            if os.path.exists(p):
                os.unlink(p)
        except OSError:
            pass


def run_daemon(
    session_name: str = "default",
    headed: bool = False,
    executable_path: str | None = None,
    cdp_url: str | None = None,
    timeout_ms: int = 15000,
    user_agent: str | None = None,
    viewport: tuple[int, int] | None = None,
    model_dir: str | None = None,
) -> None:
    sock_path = get_socket_path(session_name)
    pid_path = get_pid_path(session_name)

    if os.path.exists(sock_path):
        os.unlink(sock_path)

    with open(pid_path, "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))

    session = BrowserSession(
        headed=headed,
        executable_path=executable_path,
        cdp_url=cdp_url,
        timeout_ms=timeout_ms,
        user_agent=user_agent,
        viewport=viewport,
        model_dir=model_dir,
    )

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(sock_path)
    os.chmod(sock_path, 0o600)
    server.listen(16)

    should_stop = False

    def _on_sig(_signum: int, _frame: Any) -> None:
        nonlocal should_stop
        should_stop = True
        try:
            server.close()
        except OSError:
            pass

    signal.signal(signal.SIGTERM, _on_sig)
    signal.signal(signal.SIGINT, _on_sig)

    try:
        while not should_stop:
            try:
                conn, _ = server.accept()
            except OSError:
                break

            with conn:
                buf = b""
                while True:
                    chunk = conn.recv(65536)
                    if not chunk:
                        break
                    buf += chunk
                    if b"\n" in buf:
                        break
                if not buf:
                    continue

                line = buf.split(b"\n", 1)[0].decode("utf-8", errors="replace")
                try:
                    req = json.loads(line)
                    action = req.get("action", "")
                    data = session.execute(req)
                    resp = {"ok": True, "data": data}
                    if action == "close":
                        should_stop = True
                except Exception as exc:
                    resp = {"ok": False, "error": str(exc)}

                payload = (json.dumps(resp) + "\n").encode("utf-8")
                conn.sendall(payload)
    finally:
        session.close()
        try:
            server.close()
        except OSError:
            pass
        _cleanup_files(sock_path, pid_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Frowse session daemon")
    parser.add_argument("--session", default="default")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--executable-path", default=None)
    parser.add_argument("--cdp", default=None)
    parser.add_argument("--timeout", type=int, default=15000)
    parser.add_argument("--user-agent", default=None)
    parser.add_argument("--viewport", default=None)
    parser.add_argument("--model-dir", default=None)
    args = parser.parse_args()

    vp: tuple[int, int] | None = None
    if args.viewport and "x" in args.viewport:
        w, h = args.viewport.lower().split("x", 1)
        vp = (int(w), int(h))

    run_daemon(
        session_name=args.session,
        headed=args.headed,
        executable_path=args.executable_path,
        cdp_url=args.cdp,
        timeout_ms=args.timeout,
        user_agent=args.user_agent,
        viewport=vp,
        model_dir=args.model_dir,
    )


if __name__ == "__main__":
    main()

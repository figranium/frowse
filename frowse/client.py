"""Client helpers to auto-start and communicate with the Frowse daemon."""

from __future__ import annotations

import glob
import json
import os
import signal
import socket
import subprocess
import sys
import time
from typing import Any

from frowse.daemon import get_pid_path, get_socket_path, get_state_dir


def is_daemon_alive(session_name: str) -> bool:
    sock_path = get_socket_path(session_name)
    if not os.path.exists(sock_path):
        return False
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        s.settimeout(1.0)
        s.connect(sock_path)
        return True
    except OSError:
        return False
    finally:
        s.close()


def start_daemon(
    session_name: str = "default",
    headed: bool = False,
    executable_path: str | None = None,
    cdp_url: str | None = None,
    timeout_ms: int = 15000,
    user_agent: str | None = None,
    viewport: str | None = None,
    model_dir: str | None = None,
) -> None:
    if is_daemon_alive(session_name):
        return

    sock_path = get_socket_path(session_name)
    if os.path.exists(sock_path):
        try:
            os.unlink(sock_path)
        except OSError:
            pass

    cmd = [sys.executable, "-m", "frowse.daemon", "--session", session_name, "--timeout", str(timeout_ms)]
    if headed:
        cmd.append("--headed")
    if executable_path:
        cmd.extend(["--executable-path", executable_path])
    if cdp_url:
        cmd.extend(["--cdp", cdp_url])
    if user_agent:
        cmd.extend(["--user-agent", user_agent])
    if viewport:
        cmd.extend(["--viewport", viewport])
    if model_dir:
        cmd.extend(["--model-dir", model_dir])

    subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        if is_daemon_alive(session_name):
            return
        time.sleep(0.05)

    raise RuntimeError(f"Timed out waiting for frowse daemon (session={session_name}) to start")


def send_command(
    session_name: str,
    action: str,
    args: dict[str, Any] | None = None,
    daemon_opts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if action == "close" and not is_daemon_alive(session_name):
        return {"closed": True}

    start_daemon(session_name=session_name, **(daemon_opts or {}))
    sock_path = get_socket_path(session_name)

    req = json.dumps({"action": action, "args": args or {}}) + "\n"
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(120.0)
    try:
        s.connect(sock_path)
        s.sendall(req.encode("utf-8"))
        buf = b""
        while True:
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
            if b"\n" in buf:
                break
    finally:
        s.close()

    if not buf:
        raise RuntimeError("Empty response from frowse daemon")

    resp = json.loads(buf.split(b"\n", 1)[0].decode("utf-8"))
    if not resp.get("ok"):
        raise RuntimeError(resp.get("error", "Unknown error"))
    return resp.get("data", {})


def close_all_sessions() -> list[str]:
    state_dir = get_state_dir()
    closed: list[str] = []
    for sock in glob.glob(os.path.join(state_dir, "*.sock")):
        name = os.path.basename(sock)[:-5]
        try:
            send_command(name, "close")
            closed.append(name)
        except Exception:
            pid_file = get_pid_path(name)
            if os.path.exists(pid_file):
                try:
                    with open(pid_file, encoding="utf-8") as f:
                        pid = int(f.read().strip())
                    os.kill(pid, signal.SIGTERM)
                    closed.append(name)
                except Exception:
                    pass
    return closed

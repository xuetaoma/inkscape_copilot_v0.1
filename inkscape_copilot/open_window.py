from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
PACKAGE_PARENT = str(PACKAGE_ROOT.parent)
if PACKAGE_PARENT not in sys.path:
    sys.path.insert(0, PACKAGE_PARENT)

try:
    import inkex
except ModuleNotFoundError:  # pragma: no cover - local CLI tests do not have inkex installed
    inkex = None

from inkscape_copilot.bridge import STATE_DIR, reset_state, write_document_context
from inkscape_copilot.worker import document_context_from_svg

HOST = "127.0.0.1"
PORT = 8767
URL = f"http://{HOST}:{PORT}"
WEB_UI_SESSION_FILE = STATE_DIR / "web_ui_session.json"
WEB_UI_LOG_FILE = STATE_DIR / "web_ui_server.log"


def _server_alive() -> bool:
    try:
        with urllib.request.urlopen(f"{URL}/api/state", timeout=1.5) as response:
            return response.status == 200
    except Exception:
        return False


def _read_web_ui_session() -> dict[str, object]:
    if not WEB_UI_SESSION_FILE.exists():
        return {}
    try:
        return json.loads(WEB_UI_SESSION_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_web_ui_session(payload: dict[str, object]) -> None:
    WEB_UI_SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    WEB_UI_SESSION_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _clear_web_ui_session() -> None:
    try:
        WEB_UI_SESSION_FILE.unlink()
    except FileNotFoundError:
        pass


def _clear_web_ui_log() -> None:
    try:
        WEB_UI_LOG_FILE.unlink()
    except FileNotFoundError:
        pass


def _list_server_pids() -> list[int]:
    result = subprocess.run(
        ["lsof", "-t", f"-iTCP:{PORT}", "-sTCP:LISTEN"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    pids: list[int] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            pids.append(int(line))
        except ValueError:
            continue
    return pids


def _stop_previous_server() -> None:
    payload = _read_web_ui_session()
    known_pids = _list_server_pids()
    pid = payload.get("server_pid")
    if isinstance(pid, int) and pid not in known_pids:
        known_pids.append(pid)
    if not known_pids:
        _clear_web_ui_session()
        return

    for known_pid in known_pids:
        try:
            os.kill(known_pid, signal.SIGTERM)
        except ProcessLookupError:
            continue
        except Exception:
            continue

    deadline = time.time() + 3
    while time.time() < deadline:
        if not _list_server_pids() and not _server_alive():
            _clear_web_ui_session()
            return
        time.sleep(0.1)

    for known_pid in _list_server_pids():
        try:
            os.kill(known_pid, signal.SIGKILL)
        except Exception:
            pass
    _clear_web_ui_session()


def _kill_copilot_processes_by_pattern() -> None:
    patterns = [
        "inkscape_copilot.cli serve --port 8767",
        "run_web_app(host=\"127.0.0.1\", port=8767",
        "from inkscape_copilot.webapp import run_web_app",
    ]
    for pattern in patterns:
        subprocess.run(
            ["pkill", "-f", pattern],
            check=False,
            capture_output=True,
            text=True,
        )


def _close_previous_browser_windows() -> None:
    script = f'''
set targetUrls to {{"http://127.0.0.1:8767", "http://127.0.0.1:8768"}}

on matchesTarget(theUrl)
\trepeat with targetUrl in targetUrls
\t\tif theUrl starts with targetUrl then
\t\t\treturn true
\t\tend if
\tend repeat
\treturn false
end matchesTarget

try
\ttell application "Safari"
\t\trepeat with w in (every window)
\t\t\tset shouldClose to false
\t\t\ttry
\t\t\t\trepeat with t in (every tab of w)
\t\t\t\t\tif my matchesTarget(URL of t) then
\t\t\t\t\t\tset shouldClose to true
\t\t\t\t\t\texit repeat
\t\t\t\t\tend if
\t\t\t\tend repeat
\t\t\tend try
\t\t\tif shouldClose then close w
\t\tend repeat
\tend tell
end try

try
\ttell application "Google Chrome"
\t\trepeat with w in (every window)
\t\t\tset shouldClose to false
\t\t\ttry
\t\t\t\trepeat with t in (every tab of w)
\t\t\t\t\tif my matchesTarget(URL of t) then
\t\t\t\t\t\tset shouldClose to true
\t\t\t\t\t\texit repeat
\t\t\t\t\tend if
\t\t\t\tend repeat
\t\t\tend try
\t\t\tif shouldClose then close w
\t\tend repeat
\tend tell
end try
'''
    subprocess.run(["osascript", "-e", script], check=False, capture_output=True, text=True)


def _launch_server() -> int:
    WEB_UI_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    shell_command = (
        f"cd {subprocess.list2cmdline([PACKAGE_PARENT])} && "
        "exec "
        + subprocess.list2cmdline(["python3", "-m", "inkscape_copilot.cli", "serve", "--port", str(PORT)])
        + f" >> {subprocess.list2cmdline([str(WEB_UI_LOG_FILE)])} 2>&1 < /dev/null"
    )
    pid = os.spawnle(
        os.P_NOWAIT,
        "/bin/sh",
        "/bin/sh",
        "-lc",
        shell_command,
        {
            **os.environ,
            "PYTHONUNBUFFERED": "1",
        },
    )
    _write_web_ui_session(
        {
            "server_pid": pid,
            "url": URL,
            "opened_at": time.time(),
            "log_file": str(WEB_UI_LOG_FILE),
        }
    )
    return pid


def open_fresh_interactive_window(*, reset_runtime_state: bool = True) -> None:
    _close_previous_browser_windows()
    _stop_previous_server()
    _kill_copilot_processes_by_pattern()
    _clear_web_ui_session()
    _clear_web_ui_log()

    if reset_runtime_state:
        reset_state()
    _launch_server()

    deadline = time.time() + 10
    while time.time() < deadline:
        if _server_alive():
            break
        time.sleep(0.25)

    if not _server_alive():
        manual_command = f"cd {PACKAGE_PARENT} && python3 -m inkscape_copilot.cli serve --port {PORT}"
        details = ""
        try:
            details = WEB_UI_LOG_FILE.read_text(encoding="utf-8").strip()
        except Exception:
            details = ""
        if details:
            raise RuntimeError(
                "Could not start the interactive copilot window.\n\n"
                f"Try this in Terminal:\n{manual_command}\n\n"
                f"Startup log:\n{details}"
            )
        raise RuntimeError(
            "Could not start the interactive copilot window.\n\n"
            f"Try this in Terminal:\n{manual_command}"
        )

    launched = subprocess.run(["open", "-a", "Safari", URL], check=False, capture_output=True, text=True)
    if launched.returncode != 0:
        webbrowser.open(URL)


if inkex is not None:
    class OpenInteractiveCopilotExtension(inkex.EffectExtension):
        def effect(self) -> None:
            try:
                open_fresh_interactive_window()
            except RuntimeError as exc:
                raise inkex.AbortExtension(str(exc)) from exc

            selected = list(self.svg.selection.values())
            write_document_context(document_context_from_svg(self.svg, selected))

            inkex.utils.debug(f"Inkscape Copilot: Opened a fresh interactive window at {URL}")


if __name__ == "__main__":
    if inkex is None:
        raise SystemExit("inkex is required when running this module as an Inkscape extension.")
    OpenInteractiveCopilotExtension().run()

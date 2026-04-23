from __future__ import annotations

import subprocess


def _copilot_menu_script(menu_item_name: str) -> str:
    return f'''
tell application "Inkscape" to activate
delay 0.5
tell application "System Events"
\ttell process "inkscape"
\t\tset frontmost to true
\t\tset foundExtensions to false
\t\trepeat 20 times
\t\t\tif exists menu bar item "Extensions" of menu bar 1 then
\t\t\t\tset foundExtensions to true
\t\t\t\texit repeat
\t\t\tend if
\t\t\tdelay 0.25
\t\tend repeat
\t\tif foundExtensions is false then
\t\t\terror "Open or focus an Inkscape document window before running copilot commands."
\t\tend if
\t\tclick menu bar item "Extensions" of menu bar 1
\t\tdelay 0.2
\t\tclick menu item "Copilot" of menu 1 of menu bar item "Extensions" of menu bar 1
\t\tdelay 0.2
\t\tset targetItem to menu item "{menu_item_name}" of menu 1 of menu item "Copilot" of menu 1 of menu bar item "Extensions" of menu bar 1
\t\tignoring application responses
\t\t\tperform action "AXPress" of targetItem
\t\tend ignoring
\tend tell
end tell
'''


def trigger_copilot_menu_item(menu_item_name: str) -> tuple[bool, str | None]:
    script = _copilot_menu_script(menu_item_name)
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            check=False,
            capture_output=True,
            text=True,
            timeout=2.5,
        )
    except subprocess.TimeoutExpired:
        # On macOS, System Events can block waiting for Inkscape to finish the
        # command even after the menu item has already been dispatched.
        return True, None
    except Exception as exc:
        return False, str(exc)

    if result.returncode == 0:
        return True, None

    stderr = result.stderr.strip() or result.stdout.strip() or "Unknown AppleScript error"
    return False, stderr


def trigger_apply_pending_jobs() -> tuple[bool, str | None]:
    return trigger_copilot_menu_item("Apply Copilot Changes")


def trigger_sync_document_state() -> tuple[bool, str | None]:
    return trigger_copilot_menu_item("Refresh Copilot Context")

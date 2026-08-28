"""Open / reveal a local path with the system defaults — no hardcoded tool.

- open_path: the file's default app (default viewer) via xdg-open.
- reveal_path: the default *file manager* with the file selected, via the
  freedesktop org.freedesktop.FileManager1.ShowItems D-Bus method (works for
  Dolphin, Nautilus, Nemo, …); falls back to opening the containing folder.

All detached + best-effort so a missing helper never crashes the TUI.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

_DEVNULL = subprocess.DEVNULL


def open_path(path: str) -> None:
    subprocess.Popen(
        ["xdg-open", str(path)],
        start_new_session=True, stdout=_DEVNULL, stderr=_DEVNULL,
    )


def reveal_path(path: str) -> None:
    """Open the default file manager with `path` selected (or its folder)."""
    p = Path(path)
    try:
        rc = subprocess.run(
            [
                "dbus-send", "--session",
                "--dest=org.freedesktop.FileManager1",
                "--type=method_call",
                "/org/freedesktop/FileManager1",
                "org.freedesktop.FileManager1.ShowItems",
                f"array:string:{p.as_uri()}", "string:",
            ],
            stdout=_DEVNULL, stderr=_DEVNULL, timeout=5,
        ).returncode
    except Exception:  # noqa: BLE001 — dbus-send missing/failed
        rc = 1
    if rc != 0:
        # fallback: open the containing folder in the default file manager
        subprocess.Popen(
            ["xdg-open", str(p.parent)],
            start_new_session=True, stdout=_DEVNULL, stderr=_DEVNULL,
        )

"""Open an external tool in a new, adequately-sized terminal window.

A jailbreak tool's ncurses UI has a minimum-size requirement and misbehaves when
handed off in-place via Textual's suspend(). Instead we spawn a fresh terminal
emulator window sized in character cells and run the tool there. Pure/testable
argv construction; the actual spawn is `infra.process.spawn` (attached, so its
exit can be watched — that is why kitty does NOT get --detach here).
"""
from __future__ import annotations

import os
import shlex
from collections.abc import Callable

DEFAULT_COLS = 120
DEFAULT_ROWS = 40

# A stable window class/app-id so a tiling WM can be told to FLOAT this window.
# Tiling WMs (Hyprland, sway…) size windows to the layout and ignore the
# requested cell size, so the tool sees < 80x24 and aborts. Floating the window
# makes the WM honour the requested size instead.
WINDOW_CLASS = "idevice-tui-jailbreak"


def _kitty(inner: str, cols: int, rows: int) -> list[str]:
    # No --detach: we need a trackable child process to watch for window exit.
    return [
        "kitty",
        "--class",
        WINDOW_CLASS,
        "-o",
        f"initial_window_width={cols}c",
        "-o",
        f"initial_window_height={rows}c",
        "sh",
        "-c",
        inner,
    ]


def _foot(inner: str, cols: int, rows: int) -> list[str]:
    return [
        "foot",
        f"--app-id={WINDOW_CLASS}",
        f"--window-size-chars={cols}x{rows}",
        "sh",
        "-c",
        inner,
    ]


def _alacritty(inner: str, cols: int, rows: int) -> list[str]:
    return [
        "alacritty",
        "--class",
        WINDOW_CLASS,
        "-o",
        f"window.dimensions.columns={cols}",
        "-o",
        f"window.dimensions.lines={rows}",
        "-e",
        "sh",
        "-c",
        inner,
    ]


def _xterm(inner: str, cols: int, rows: int) -> list[str]:
    return [
        "xterm",
        "-class",
        WINDOW_CLASS,
        "-geometry",
        f"{cols}x{rows}",
        "-e",
        "sh",
        "-c",
        inner,
    ]


# ordered by preference
_TERMINALS: list[tuple[str, Callable[[str, int, int], list[str]]]] = [
    ("kitty", _kitty),
    ("foot", _foot),
    ("alacritty", _alacritty),
    ("xterm", _xterm),
]


def _read_comm(pid: int) -> str | None:
    try:
        with open(f"/proc/{pid}/comm") as f:
            return f.read().strip()
    except OSError:
        return None


def _read_ppid(pid: int) -> int | None:
    try:
        with open(f"/proc/{pid}/status") as f:
            for line in f:
                if line.startswith("PPid:"):
                    return int(line.split()[1])
    except OSError:
        return None
    return None


def current_terminal(
    *,
    start_pid: int | None = None,
    read_comm: Callable[[int], str | None] = _read_comm,
    read_ppid: Callable[[int], int | None] = _read_ppid,
    max_depth: int = 40,
) -> str | None:
    """The terminal emulator idevice-tui is actually running under, found by
    walking the process ancestry (/proc). None if it's not one we support."""
    known = {name for name, _ in _TERMINALS}
    pid = start_pid if start_pid is not None else os.getppid()
    seen: set[int] = set()
    while pid and pid not in seen and len(seen) < max_depth:
        seen.add(pid)
        comm = read_comm(pid)
        if comm in known:
            return comm
        pid = read_ppid(pid) or 0
    return None


def detect_terminal(
    which: Callable[[str], str | None] | None = None,
    current: str | None = None,
) -> str | None:
    if which is None:
        import shutil

        which = shutil.which
    # honour the terminal idevice-tui is running in, if it's supported+installed
    if current and which(current):
        return current
    for name, _builder in _TERMINALS:
        if which(name):
            return name
    return None


def _wrap(inner_cmd: list[str]) -> str:
    """Shell string that runs the tool then waits, so the window stays open
    until the user closes it (which is how we detect the session ended)."""
    quoted = shlex.join(inner_cmd)
    return (
        f"{quoted}; status=$?; echo; "
        f'printf "exited (%s) — press Enter to close window" "$status"; '
        f"read _"
    )


def terminal_command(
    term: str,
    inner_cmd: list[str],
    cols: int = DEFAULT_COLS,
    rows: int = DEFAULT_ROWS,
) -> list[str]:
    builder = dict(_TERMINALS).get(term)
    if builder is None:
        raise ValueError(f"unsupported terminal: {term}")
    return builder(_wrap(inner_cmd), cols, rows)


def floating_setup_commands(
    env: dict | None = None,
    cols: int = DEFAULT_COLS,
    rows: int = DEFAULT_ROWS,
) -> list[list[str]]:
    """WM commands to run before spawning so the new window floats at the
    requested size instead of being tiled small. Currently Hyprland; empty on
    anything else (the window then opens however the WM decides)."""
    env = os.environ if env is None else env
    if env.get("HYPRLAND_INSTANCE_SIGNATURE"):
        # Hyprland 0.42+ replaced `windowrulev2 = float,class:...` with
        # `windowrule` + the new grammar `match:class ^(...)$, <action> <value>`.
        # 0.56 rejects the old form outright, so the window never floated.
        # 1100x720 px is safely above the 80x24 minimum.
        rule = (
            f"match:class ^({WINDOW_CLASS})$, "
            f"float on, size 1100 720, center on"
        )
        return [["hyprctl", "keyword", "windowrule", rule]]
    return []

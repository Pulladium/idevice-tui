"""Process seams: spawn a watchable child and await its exit.

Kept tiny and side-effect-only so services can be tested by monkeypatching
`spawn`/`wait_for` with a fake process.
"""
from __future__ import annotations

import asyncio
import subprocess


def spawn(command: list[str]) -> subprocess.Popen:
    # start_new_session isolates signals (a Ctrl+C in our TUI won't hit the
    # child) while still returning a handle we can await — unlike a terminal's
    # own --detach fork, which we could not track.
    return subprocess.Popen(command, start_new_session=True)


async def wait_for(proc: subprocess.Popen) -> int:
    """Block (in a thread) until the process exits; returns its exit code."""
    return await asyncio.to_thread(proc.wait)


def run_wm_setup(command: list[str]) -> None:
    """Best-effort window-manager tweak (e.g. hyprctl float rule); never fatal."""
    subprocess.run(command, check=False, capture_output=True)

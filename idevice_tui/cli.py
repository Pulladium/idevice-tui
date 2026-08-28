"""Command-line entry point.

Handles ``--version`` / ``--help`` without launching the full-screen TUI, then
starts the app.
"""
from __future__ import annotations

import argparse

from . import __version__


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="idevice-tui",
        description="A Textual terminal UI for iOS devices "
        "on Linux: device info, AFC files, live syslog, Legacy iOS Kit hand-off, "
        "and checkra1n/palera1n jailbreak launchers.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.parse_args()

    from .ui.app import main as run_app

    run_app()


if __name__ == "__main__":
    main()

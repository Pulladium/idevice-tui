"""Tools tab: Legacy iOS Kit hand-off (restore/downgrade, blobs, flag modes)."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.css.query import NoMatches
from textual.widgets import Button, Static

TOOL_ACTIONS = [
    ("Restore / Downgrade", "restore"),
    ("Save SHSH blobs", "blobs"),
    ("Jailbreak", "jailbreak"),
    ("DFU helper", "dfuhelper"),
    ("Pwn", "pwn"),
    ("SSH ramdisk", "sshrd"),
    ("Exit recovery", "exit_recovery"),
    ("kDFU", "kdfu"),
]

_DESTRUCTIVE = {"restore"}


def needs_confirm(action: str) -> bool:
    return action in _DESTRUCTIVE


def action_enabled(action: str, mode: str) -> bool:
    if action == "exit_recovery":
        return mode == "recovery"
    if mode == "none":
        return False
    return True


class ToolsTab(Vertical):
    def compose(self) -> ComposeResult:
        yield Static("", id="kit-status")
        yield Button("Clone Legacy iOS Kit", id="kit-clone")
        for label, action in TOOL_ACTIONS:
            yield Button(label, id=f"kit-{action}")

    def set_status(self, text: str) -> None:
        self.query_one("#kit-status", Static).update(text)

    def gate(self, mode: str) -> None:
        for _label, action in TOOL_ACTIONS:
            try:
                self.query_one(f"#kit-{action}", Button).disabled = not action_enabled(
                    action, mode
                )
            except NoMatches:
                continue

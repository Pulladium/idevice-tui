"""Syslog tab: live device log with start/stop, clear, and a substring filter."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Label, RichLog, Static


class SyslogTab(Vertical):
    def compose(self) -> ComposeResult:
        yield Label("Syslog", classes="panel-title")
        with Horizontal(id="syslog-controls"):
            yield Button("Start", id="syslog-start", variant="success")
            yield Button("Stop", id="syslog-stop", variant="error")
            yield Button("Clear", id="syslog-clear")
            yield Input(placeholder="filter (substring)…", id="syslog-filter")
        yield Static("", id="syslog-status")
        yield RichLog(id="syslog-log", highlight=False, markup=False, wrap=False, max_lines=5000)

    def set_status(self, text: str) -> None:
        self.query_one("#syslog-status", Static).update(text)

    def filter_text(self) -> str:
        return self.query_one("#syslog-filter", Input).value.strip()

    @staticmethod
    def passes_filter(line: str, filter_text: str) -> bool:
        return not filter_text or filter_text.lower() in line.lower()

    def add_line(self, line: str, filter_text: str = "") -> None:
        if not self.passes_filter(line, filter_text):
            return
        self.query_one("#syslog-log", RichLog).write(line)

    def clear(self) -> None:
        self.query_one("#syslog-log", RichLog).clear()

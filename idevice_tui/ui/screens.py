"""Modal screens."""
from __future__ import annotations

from rich.markup import escape
from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static


class FilePreviewScreen(ModalScreen["tuple | None"]):
    """Preview of a device file (raw text, no markup) with a Download action.

    Dismisses with ("download", remote_path) when Download is pressed, else None.
    """

    BINDINGS = [("escape", "close", "Close")]
    CSS = """
    FilePreviewScreen { align: center middle; }
    #preview-box { width: 90%; height: 85%; border: round $primary; background: $surface; padding: 0 1; }
    #preview-content { padding: 1 0; }
    #preview-buttons { height: auto; margin-top: 1; }
    #preview-buttons Button { margin-right: 1; width: auto; }
    """

    def __init__(self, title: str, text: str, remote_path: str) -> None:
        super().__init__()
        self._title = title
        self._text = text
        self._remote = remote_path

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="preview-box"):
            yield Label(f"[b]{escape(self._title)}[/b]")
            yield Static(self._text, id="preview-content", markup=False)
            with Horizontal(id="preview-buttons"):
                yield Button("Download", id="preview-download", variant="primary")
                yield Button("Close", id="preview-close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "preview-download":
            self.dismiss(("download", self._remote))
        else:
            self.dismiss(None)

    def action_close(self) -> None:
        self.dismiss(None)


class ConfirmScreen(ModalScreen[bool]):
    """Modal guard shown before a destructive action."""

    def __init__(self, message: str) -> None:
        super().__init__()
        self._message = message

    def compose(self) -> ComposeResult:
        yield Label(self._message)
        yield Button("Continue", id="ok", variant="error")
        yield Button("Cancel", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "ok")

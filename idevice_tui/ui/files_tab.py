"""Files tab: browse the device's media partition over AFC (normal mode)."""
from __future__ import annotations

from rich.markup import escape
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import DataTable, Label, Static

from ..infra.afc import AfcEntry


def human_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


class FilesTab(VerticalScroll):
    def compose(self) -> ComposeResult:
        yield Label("Files", classes="panel-title")
        yield Static("", id="files-path")
        table = DataTable(id="files-table", cursor_type="row", zebra_stripes=True)
        table.add_columns("Name", "Size", "Modified")
        yield table

    # rows[i] = ("up"|"dir"|"file", entry_or_None) — parallel to table rows
    def render_dir(self, path: str, entries: list[AfcEntry]) -> None:
        self._rows: list[tuple[str, AfcEntry | None]] = []
        self.query_one("#files-path", Static).update(f"[b]{escape(path)}[/b]")
        table = self.query_one("#files-table", DataTable)
        table.clear()
        if path != "/":
            table.add_row("[dim]../[/dim]", "", "")
            self._rows.append(("up", None))
        for e in entries:
            name = f"[b]{escape(e.name)}/[/b]" if e.is_dir else escape(e.name)
            size = "" if e.is_dir else human_size(e.size)
            mtime = e.mtime.strftime("%Y-%m-%d %H:%M") if e.mtime else ""
            table.add_row(name, size, mtime)
            self._rows.append(("dir" if e.is_dir else "file", e))

    def target_for_row(self, index: int | None) -> tuple[str, AfcEntry | None]:
        rows = getattr(self, "_rows", [])
        if index is not None and 0 <= index < len(rows):
            return rows[index]
        return ("none", None)

    def show_unavailable(self, mode: str) -> None:
        self._rows = []
        self.query_one("#files-path", Static).update(
            f"[dim]Files browsing needs a normal-mode device — N/A in {mode}.[/dim]"
        )
        self.query_one("#files-table", DataTable).clear()

    def show_error(self, message: str) -> None:
        self._rows = []
        self.query_one("#files-path", Static).update(f"[red]{escape(message)}[/red]")
        self.query_one("#files-table", DataTable).clear()

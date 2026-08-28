"""Jailbreak tab: pick a tool from the registry, read its guidance, launch it.

Presentational — the app wires events to the services. Adding a tool to the
registry makes it appear here with zero changes to this file.
"""
from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Button, Label, ProgressBar, RadioButton, RadioSet, Static

from ..domain.models import DeviceSnapshot
from ..jailbreaks.base import JailbreakTool, Variant


class JailbreakTab(VerticalScroll):
    def __init__(self, tools: list[JailbreakTool], **kw) -> None:
        super().__init__(**kw)
        self._tools = tools
        self._downloading = False
        self._visible_variants = []
        self._variants_for: tuple[str, str | None] | None = None

    def compose(self) -> ComposeResult:
        yield Label("Jailbreak", classes="panel-title")
        yield Static("", id="jb-status")
        yield Static("", id="jb-guide")
        yield Label("Tool", classes="muted")
        with RadioSet(id="jb-tool"):
            for i, tool in enumerate(self._tools):
                label = tool.name if tool.is_available() else f"{tool.name} (coming soon)"
                yield RadioButton(label, value=(i == 0), disabled=not tool.is_available())
        yield Label("Version", classes="muted")
        yield RadioSet(id="jb-variant")
        yield Static("", id="jb-download-label")
        yield ProgressBar(
            total=None, show_percentage=False, show_eta=False, id="jb-download-progress"
        )
        with Horizontal(id="jb-actions"):
            yield Button("Launch", id="jb-launch", variant="primary")
            yield Button("Uninstall", id="jb-uninstall", variant="error")

    # --- helpers the app calls ----------------------------------------------
    def tool_at(self, index: int) -> JailbreakTool | None:
        return self._tools[index] if 0 <= index < len(self._tools) else None

    def set_status(self, text: str) -> None:
        self.query_one("#jb-status", Static).update(text)

    def variant_at(self, index: int):
        return self._visible_variants[index] if 0 <= index < len(self._visible_variants) else None

    def needs_variant_rebuild(self, tool: JailbreakTool, snap: DeviceSnapshot) -> bool:
        return self._variants_for != (tool.id, tool.recommended_variant(snap))

    def mark_variant_rebuild(self, tool: JailbreakTool, snap: DeviceSnapshot) -> None:
        """Record a queued rebuild so polling doesn't queue a duplicate one."""
        self._variants_for = (tool.id, tool.recommended_variant(snap))

    @property
    def downloading(self) -> bool:
        return self._downloading

    def set_downloading(
        self, downloading: bool, tool_name: str = "", version: str = ""
    ) -> None:
        """Show an indeterminate, named progress bar while the download runs."""
        self._downloading = downloading
        self.query_one("#jb-download-label", Static).display = downloading
        self.query_one("#jb-download-progress", ProgressBar).display = downloading
        self.query_one("#jb-tool", RadioSet).disabled = downloading
        self.query_one("#jb-variant", RadioSet).disabled = downloading
        btn = self.query_one("#jb-launch", Button)
        uninstall = self.query_one("#jb-uninstall", Button)
        if downloading:
            btn.label = "Downloading…"
            btn.disabled = True
            uninstall.display = False
            self.query_one("#jb-download-label", Static).update(
                f"[cyan]Downloading {tool_name} {version}…[/cyan]"
            )

    def set_guidance(self, text: str | None) -> None:
        self.query_one("#jb-guide", Static).update(text or "")

    async def rebuild_variants(self, tool: JailbreakTool, snap: DeviceSnapshot) -> None:
        rs = self.query_one("#jb-variant", RadioSet)
        recommended = tool.recommended_variant(snap)
        self._variants_for = (tool.id, recommended)
        await rs.remove_children()
        variants = tool.variants()
        if recommended:
            variants.sort(key=lambda variant: variant.id != recommended)
            variants = [
                Variant(
                    variant.id,
                    f"{variant.label}  (recommended)" if variant.id == recommended else variant.label,
                )
                for variant in variants
            ]
        self._visible_variants = variants
        buttons = []
        for v in variants:
            btn = RadioButton(v.label)      # mount UNCHECKED first
            buttons.append((v, btn))
            await rs.mount(btn)
        rs.display = bool(variants)
        # Select the current version AFTER mounting so the RadioSet registers it
        # as its single pressed button (mounting with value=True does not — it
        # leaves pressed_index -1, so clicking another wouldn't uncheck it).
        current = getattr(tool, "_version", None)
        target = next((b for v, b in buttons if v.id == current), None)
        if target is None and buttons:
            target = buttons[0][1]
        if target is not None:
            target.value = True

    def show_for_tool(self, tool: JailbreakTool, snap: DeviceSnapshot) -> None:
        self.set_guidance(tool.guidance(snap))
        btn = self.query_one("#jb-launch", Button)
        uninstall = self.query_one("#jb-uninstall", Button)
        if self._downloading:
            # Polling also calls this method; don't let it erase the active
            # download state while the worker is still running.
            btn.label = "Downloading…"
            btn.disabled = True
            uninstall.display = False
            return
        can_use = tool.is_available() and tool.supports(snap)
        btn.label = "Launch" if tool.is_ready() else "Download"
        btn.disabled = not can_use
        uninstall.display = tool.is_ready()
        uninstall.label = f"Uninstall {getattr(tool, '_version', '')}".rstrip()
        uninstall.disabled = False

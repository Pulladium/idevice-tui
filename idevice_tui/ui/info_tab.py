"""The single, unified device view. Renders one DeviceSnapshot across every
mode; a field a mode can't provide shows `N/A in <mode>`.
"""
from __future__ import annotations

from datetime import datetime

from rich.markup import escape
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, DataTable, Label, ProgressBar, Static

from ..domain.models import DeviceSnapshot

_ALL = {"normal", "recovery", "dfu"}
_NORMAL = {"normal"}
_RECOVERY = {"recovery", "dfu"}


def _cell(mode: str, applicable: set[str], value) -> str:
    if mode in applicable:
        return "—" if value in (None, "") else escape(str(value))
    return f"[dim]N/A in {mode}[/dim]"


class InfoTab(Vertical):
    """Device + battery panels, driven entirely by `render(snapshot)`."""

    def compose(self) -> ComposeResult:
        with Horizontal(id="info-cols"):
            with VerticalScroll(id="device-panel", classes="panel"):
                yield Label("Device", classes="panel-title")
                yield Static("Mode   [dim]—[/dim]", id="mode-line")
                yield Static("Jailbreak   [dim]—[/dim]", id="jb-line")
                table = DataTable(id="device-table", show_header=False, cursor_type="none")
                table.add_columns("field", "value")
                yield table
                yield Button("Refresh", id="info-refresh")
            with Vertical(id="battery-panel", classes="panel"):
                yield Label("Battery", classes="panel-title")
                yield Label("", id="batt-headline")
                yield ProgressBar(total=100, show_eta=False, id="batt-bar")
                yield Static("", id="batt-stats")
                yield Label("", id="batt-updated", classes="muted")

    # --- unified render ------------------------------------------------------
    def render_snapshot(self, snap: DeviceSnapshot) -> None:
        mode = snap.mode
        info = snap.info
        rec = snap.recovery

        # model / identity resolved from whichever source the mode provides
        if info is not None:
            model = f"{info.product_name} ({info.product_type})"
        elif rec is not None:
            name = rec.display_name or rec.product_type or "?"
            model = f"{name} ({rec.product_type})" if rec.product_type else name
        else:
            model = None
        ecid = f"0x{snap.ecid:x}" if snap.ecid else None
        chip = f"0x{rec.chip_id:x}" if (rec and rec.chip_id) else None

        rows = [
            ("Name", _NORMAL, info.name if info else None),
            ("Model", _ALL, model),
            ("Mode", _ALL, mode),
            ("iOS", _NORMAL, f"{info.ios_version} ({info.build})" if info else None),
            ("CPU", _NORMAL, info.cpu_arch if info else None),
            ("Serial", _NORMAL, info.serial if info else None),
            ("UDID", _NORMAL, info.udid if info else None),
            ("ECID", _ALL, ecid),
            ("Chip ID", _RECOVERY, chip),
            ("Hardware", _RECOVERY, rec.hardware_model if rec else None),
            ("IMEI", _NORMAL, info.imei if info else None),
            ("IMEI2", _NORMAL, info.imei2 if info else None),
            ("Wi-Fi MAC", _NORMAL, info.wifi_address if info else None),
            ("Bluetooth", _NORMAL, info.bluetooth_address if info else None),
            ("Phone", _NORMAL, info.phone_number if info else None),
            ("Region", _NORMAL, info.region if info else None),
            ("Activation", _NORMAL, info.activation_state if info else None),
        ]
        table = self.query_one("#device-table", DataTable)
        table.clear()
        for label, applicable, value in rows:
            table.add_row(f"[dim]{label}[/dim]", _cell(mode, applicable, value))

        self._render_mode(snap)
        self._render_jailbreak(snap)
        self._render_battery(snap)

    def _render_mode(self, snap: DeviceSnapshot) -> None:
        line = self.query_one("#mode-line", Static)
        if snap.mode == "none":
            line.update("Mode   [dim]no device[/dim]")
        elif snap.mode == "normal":
            line.update("Mode   [b green]normal[/b green]")
        else:
            line.update(f"Mode   [b yellow]{snap.mode}[/b yellow]")

    def _render_jailbreak(self, snap: DeviceSnapshot) -> None:
        line = self.query_one("#jb-line", Static)
        if snap.mode != "normal":
            line.update(f"Jailbreak   [dim]N/A in {snap.mode}[/dim]")
            return
        jb = snap.jailbreak
        if jb is None:
            line.update("Jailbreak   [dim]unknown[/dim]")
        elif jb.jailbroken:
            detail = f" [dim]({escape(jb.ssh)})[/dim]" if jb.ssh else ""
            line.update(f"Jailbreak   [b green]yes[/b green]{detail}")
        elif jb.jailbroken is False:
            line.update("Jailbreak   [yellow]not detected[/yellow] [dim](USB probe)[/dim]")
        else:
            line.update("Jailbreak   [dim]unknown[/dim]")

    def _render_battery(self, snap: DeviceSnapshot) -> None:
        headline = self.query_one("#batt-headline", Label)
        stats = self.query_one("#batt-stats", Static)
        updated = self.query_one("#batt-updated", Label)
        bar = self.query_one("#batt-bar", ProgressBar)
        if snap.mode != "normal" or snap.battery is None:
            headline.update(f"[dim]N/A in {snap.mode}[/dim]" if snap.mode != "normal" else "")
            stats.update("")
            if snap.mode != "normal":
                updated.update("")
            return
        b = snap.battery
        state = "charging" if b.is_charging else ("plugged" if b.external_connected else "on battery")
        color = "green" if b.is_charging else ("yellow" if (b.level or 0) > 20 else "red")
        headline.update(f"[b {color}]{b.level if b.level is not None else '?'}%[/]  ·  {state}")
        if b.level is not None:
            bar.update(progress=b.level)

        def line(name, value):
            return f"[dim]{name:<12}[/dim]{value}"

        health = f"{b.health}%" if b.health is not None else "—"
        cap = (
            f"{b.max_capacity} / {b.design_capacity} mAh"
            if b.max_capacity and b.design_capacity else "—"
        )
        temp = f"{b.temperature} °C" if b.temperature is not None else "—"
        cycles = str(b.cycle_count) if b.cycle_count is not None else "—"
        stats.update("\n".join([
            line("Health", health),
            line("Cycles", cycles),
            line("Capacity", cap),
            line("Temp", temp),
            line("Serial", escape(b.serial) if b.serial else "—"),
        ]))
        updated.update(f"[dim]updated {datetime.now():%H:%M:%S}[/dim]")

"""IDeviceApp — thin composition + event routing over the service layer."""
from __future__ import annotations

import asyncio
import re
import sys
from contextlib import aclosing, contextmanager
from pathlib import Path, PurePosixPath

from textual import work
from textual.app import App, ComposeResult
from textual.css.query import NoMatches
from textual.reactive import reactive
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    RadioSet,
    Static,
    TabbedContent,
    TabPane,
)

from ..infra import afc, legacykit, opener, syslog
from ..infra import config as cfg
from ..infra.afc import join_path, parent_path
from ..jailbreaks.registry import build_registry
from ..services.device_service import DeviceService
from ..services.jailbreak_service import JailbreakService
from .files_tab import FilesTab
from .info_tab import InfoTab
from .jailbreak_tab import JailbreakTab
from .screens import ConfirmScreen, FilePreviewScreen
from .syslog_tab import SyslogTab
from .tools_tab import ToolsTab, needs_confirm

BATTERY_REFRESH = 10  # seconds


def run_kit(kit: legacykit.LegacyKit, command: list[str]) -> int:
    return kit.run(command)


def device_download_folder(info) -> str:
    """A per-device subfolder name (keyed by serial) so identical filenames from
    different phones — or different on-device folders — never collide."""
    label = getattr(info, "product_name", None) or "device"
    ident = getattr(info, "serial", None) or getattr(info, "udid", None) or "unknown"
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", f"{label}-{ident}").strip("-")
    return slug or "device"


def device_download_path(download_dir: Path, folder: str, remote_path: str) -> Path:
    """Map an absolute AFC path into a confined per-device local path."""
    remote = PurePosixPath(remote_path)
    if not remote.is_absolute() or any(part in {".", ".."} for part in remote.parts):
        raise ValueError("invalid remote file path")
    return download_dir / folder / Path(*remote.parts[1:])


class IDeviceApp(App):
    CSS = """
    #info-cols { height: 1fr; }
    .panel { border: round $primary; padding: 0 1; margin: 0 1; }
    #device-panel { width: 2fr; }
    #battery-panel { width: 1fr; }
    .panel-title { text-style: bold; color: $accent; }
    #batt-headline { margin: 1 0; }
    #batt-bar { margin-bottom: 1; }
    .placeholder { width: 1fr; height: 1fr; content-align: center middle; color: $text-muted; }
    .muted { color: $text-muted; margin-top: 1; }
    #info-refresh { margin-top: 1; width: auto; }
    #files-path { height: 1; color: $accent; }
    #files-table { height: 1fr; }
    #syslog-controls { height: 3; }
    #syslog-controls Button { margin-right: 1; }
    #syslog-filter { width: 1fr; }
    #syslog-status { height: 1; color: $text-muted; }
    #syslog-log { height: 1fr; border: round $primary; }
    #jb-actions { height: 3; align-vertical: middle; }
    #jb-actions Button { width: auto; margin-right: 1; }
    #jb-download-label { display: none; margin-top: 1; color: $accent; }
    #jb-download-progress { display: none; height: 1; }
    """

    BINDINGS = [("r", "refresh", "Refresh"), ("q", "quit", "Quit")]
    TITLE = "idevice-tui"
    SUB_TITLE = "no device"

    device_present: reactive[bool] = reactive(False)

    def __init__(self) -> None:
        super().__init__()
        self.devices = DeviceService()
        self.jailbreaks = JailbreakService()
        self.tools = build_registry(cfg.load_config().checkra1n_dir)
        self._selected_tool = 0
        self.kit: legacykit.LegacyKit | None = None
        self._toggles: list[str] = []
        self._files_path = "/"
        self._syslog_worker = None
        self._syslog_filter = ""
        self._download_dir = Path.home() / "idevice-tui-downloads"
        self._last_download: Path | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("No iOS device connected.\nPlug in over USB and tap “Trust”.",
                     id="placeholder", classes="placeholder")
        with TabbedContent(id="tabs", initial="tab-info"):
            with TabPane("Info", id="tab-info"):
                yield InfoTab(id="info-tab")
            with TabPane("Files", id="tab-files"):
                yield FilesTab(id="files-tab")
            with TabPane("Syslog", id="tab-syslog"):
                yield SyslogTab(id="syslog-tab")
            with TabPane("Tools", id="tab-tools"):
                yield ToolsTab(id="tools-tab")
            with TabPane("Jailbreak", id="tab-jailbreak"):
                yield JailbreakTab(self.tools, id="jailbreak-tab")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#tabs").display = False
        self._init_kit()
        self.set_interval(3, self.poll)
        self.set_interval(BATTERY_REFRESH, self.tick_battery)
        self.poll()
        self._init_jailbreak_tab()
        self.prefetch_remote_versions()

    # --- polling / rendering -------------------------------------------------
    @work(exclusive=True, group="poll")
    async def poll(self) -> None:
        snap = await self.devices.poll()
        self.device_present = snap.present
        self.render_all()

    @work(exclusive=True, group="battery")
    async def tick_battery(self) -> None:
        if self.devices.snapshot.mode != "normal" or self.devices.jailbreak_running:
            return
        await self.devices.refresh_battery()
        self.render_all()

    def render_all(self) -> None:
        snap = self.devices.snapshot
        try:
            self.query_one("#info-tab", InfoTab).render_snapshot(snap)
            self.query_one("#tools-tab", ToolsTab).gate(snap.mode)
            self._render_jailbreak_guidance()
            self._render_status(snap)
        except NoMatches:
            # Rendering can race with Textual's teardown; no visible UI
            # remains to update in that case.
            return

    def _render_status(self, snap) -> None:
        # single home for the device summary: the Header subtitle, next to the
        # app name — no separate duplicated status bar.
        if snap.mode == "normal" and snap.info is not None:
            i = snap.info
            self.sub_title = f"{i.product_name} · iOS {i.ios_version}" + (
                f" · {i.name}" if i.name else ""
            )
        elif snap.note:
            self.sub_title = snap.note
        elif snap.mode in ("recovery", "dfu"):
            self.sub_title = f"{snap.mode} mode"
        else:
            self.sub_title = "no device"

    def watch_device_present(self, present: bool) -> None:
        try:
            self.query_one("#tabs").display = present
            self.query_one("#placeholder").display = not present
        except NoMatches:
            return
        if not present:
            self._stop_syslog()  # release the syslog session on disconnect

    def action_refresh(self) -> None:
        self._do_refresh()

    @work(exclusive=True, group="poll")
    async def _do_refresh(self) -> None:
        await self.devices.refresh()
        self.device_present = self.devices.snapshot.present
        self.render_all()

    # --- Legacy iOS Kit ------------------------------------------------------
    def _init_kit(self) -> None:
        c = cfg.load_config()
        self._toggles = c.toggles
        self.kit = (
            legacykit.LegacyKit.from_path(c.kit_path)
            if c.kit_path else legacykit.LegacyKit.locate(cfg.default_candidates())
        )
        tools = self.query_one("#tools-tab", ToolsTab)
        if self.kit.is_available:
            tools.set_status("[green]Legacy iOS Kit found[/green]")
        else:
            missing = legacykit.LegacyKit.missing_deps()
            extra = f"  [dim](missing: {', '.join(missing)})[/dim]" if missing else ""
            tools.set_status(f"[red]Legacy iOS Kit not installed[/red]{extra}")
        try:
            self.query_one("#kit-clone", Button).display = not self.kit.is_available
        except NoMatches:
            return

    @contextmanager
    def _handoff(self):
        """Suspend + mark device busy so polling defers while an in-place tool
        owns the terminal and USB."""
        self.devices.jailbreak_running = True
        try:
            with self.suspend():
                yield
        finally:
            self.devices.jailbreak_running = False

    @work(exclusive=True, group="kit")
    async def launch_kit(self, action: str) -> None:
        tools = self.query_one("#tools-tab", ToolsTab)
        if not self.kit or not self.kit.is_available:
            tools.set_status("[red]Legacy iOS Kit not installed[/red]")
            return
        if needs_confirm(action):
            ok = await self.push_screen_wait(
                ConfirmScreen(f"This will run a destructive operation ({action}). Continue?")
            )
            if not ok:
                return
        if not sys.stdin.isatty():
            tools.set_status("[yellow]Cannot hand off: no interactive terminal[/yellow]")
            return
        snap = self.devices.snapshot
        cmd = self.kit.build_command(
            action, device_type=snap.product_type, ecid=snap.ecid, toggles=self._toggles
        )
        with self._handoff():
            rc = run_kit(self.kit, cmd)
        if rc != 0:
            tools.set_status(f"[red]Legacy iOS Kit exited with code {rc}[/red]")
        self.poll()

    @work(exclusive=True, group="kit")
    async def clone_kit(self) -> None:
        tools = self.query_one("#tools-tab", ToolsTab)
        if not sys.stdin.isatty():
            tools.set_status("[yellow]Cannot hand off: no interactive terminal[/yellow]")
            return
        dest = cfg.default_candidates()[0]
        dest.parent.mkdir(parents=True, exist_ok=True)
        cmd = legacykit.LegacyKit.clone_command(dest)
        with self._handoff():
            rc = run_kit(legacykit.LegacyKit(path=dest.parent), cmd)
        if rc != 0:
            tools.set_status(f"[red]Clone failed (code {rc})[/red]")
            return
        self._init_kit()
        cfg.save_config(cfg.Config(kit_path=self.kit.path, toggles=self._toggles))

    # --- Jailbreak -----------------------------------------------------------
    def _schedule_variant_rebuild(self, tab: JailbreakTab, tool) -> None:
        """Serialize mutations of the shared version RadioSet.

        Version rebuilding removes and remounts children asynchronously. A
        quick tool switch, device refresh and completed download can otherwise
        overlap and mutate that RadioSet concurrently.
        """
        tab.mark_variant_rebuild(tool, self.devices.snapshot)
        self._rebuild_jailbreak_variants(tab, tool)

    @work(exclusive=True, group="jb-variants")
    async def _rebuild_jailbreak_variants(self, tab: JailbreakTab, tool) -> None:
        try:
            await tab.rebuild_variants(tool, self.devices.snapshot)
        except NoMatches:
            # A pending worker may start after Textual has torn down the tab.
            return

    def _init_jailbreak_tab(self) -> None:
        tab = self.query_one("#jailbreak-tab", JailbreakTab)
        tool = self.tools[self._selected_tool]
        self._schedule_variant_rebuild(tab, tool)
        tab.show_for_tool(tool, self.devices.snapshot)

    @work(exclusive=True, group="jb-remote")
    async def prefetch_remote_versions(self) -> None:
        """Background: scrape online version lists (e.g. palera1n's GitHub
        releases) without blocking startup; offline just keeps the fallbacks.
        Rebuild the picker if the currently-selected tool gained versions."""
        changed: set[str] = set()
        for tool in self.tools:
            try:
                if await tool.fetch_remote_versions():
                    changed.add(tool.id)
            except Exception:  # noqa: BLE001
                pass
        if not changed:
            return
        try:
            tab = self.query_one("#jailbreak-tab", JailbreakTab)
        except NoMatches:  # tab gone (e.g. app tearing down)
            return
        tool = self.tools[self._selected_tool]
        if tool.id in changed and not tab.downloading:
            self._schedule_variant_rebuild(tab, tool)
            tab.show_for_tool(tool, self.devices.snapshot)

    def _render_jailbreak_guidance(self) -> None:
        tab = self.query_one("#jailbreak-tab", JailbreakTab)
        tool = self.tools[self._selected_tool]
        if not tab.downloading and tab.needs_variant_rebuild(tool, self.devices.snapshot):
            self._schedule_variant_rebuild(tab, tool)
        tab.show_for_tool(tool, self.devices.snapshot)

    @work(exclusive=True, group="jailbreak")
    async def launch_jailbreak(self) -> None:
        # NoMatches: the jailbreak tab can disappear across an await (app
        # closing / navigated away); a background worker must tolerate that.
        try:
            tab = self.query_one("#jailbreak-tab", JailbreakTab)
            tool = self.tools[self._selected_tool]
            # `launch()` normally just spawns a terminal. If a selected binary
            # vanished meanwhile, its fallback prepare() may perform blocking
            # I/O; keep either path off the Textual event loop.
            result = await asyncio.to_thread(self.jailbreaks.launch, tool, self.devices.snapshot)
            if result.error:
                tab.set_status(f"[red]{result.error}[/red]")
                return
            tab.set_status(
                f"[green]{tool.name} launched in a new {result.terminal} window[/green] — "
                "device reads paused until it closes."
            )
            self.devices.jailbreak_running = True
            # watch the window; resume + refresh when it exits
            await self.jailbreaks.wait(result.proc)
            self.devices.jailbreak_running = False
            tab.set_status(f"[dim]{tool.name} window closed — refreshing device…[/dim]")
            await self.devices.refresh()
            self.device_present = self.devices.snapshot.present
            self.render_all()
            # prepare() may have downloaded the binary — refresh the picker so its
            # [⬇ download] marker flips to [✓ installed]. Done after wait so we
            # don't mutate the RadioSet mid-worker while the window is open.
            self._schedule_variant_rebuild(tab, tool)
        except NoMatches:
            self.devices.jailbreak_running = False

    @work(exclusive=True, group="jb-download")
    async def download_selected(self) -> None:
        try:
            tab = self.query_one("#jailbreak-tab", JailbreakTab)
            tool = self.tools[self._selected_tool]
            version = getattr(tool, "_version", "")
            tab.set_status("")
            tab.set_downloading(True, tool.name, version)
            try:
                err = await asyncio.to_thread(tool.prepare)  # blocking HTTP off the loop
            finally:
                tab.set_downloading(False)
            if err:
                tab.set_status(f"[red]{err}[/red]")
                tab.show_for_tool(tool, self.devices.snapshot)
                return
            # flip the [⬇ download] marker to [✓ installed] and button to Launch
            self._schedule_variant_rebuild(tab, tool)
            tab.show_for_tool(tool, self.devices.snapshot)
        except NoMatches:
            pass

    @work(exclusive=True, group="jb-uninstall")
    async def uninstall_selected(self) -> None:
        try:
            tab = self.query_one("#jailbreak-tab", JailbreakTab)
            tool = self.tools[self._selected_tool]
            err = tool.uninstall()
            if err:
                tab.set_status(f"[red]{err}[/red]")
                return
            tab.set_status("")
            self._schedule_variant_rebuild(tab, tool)
            tab.show_for_tool(tool, self.devices.snapshot)
        except NoMatches:
            pass

    # --- events --------------------------------------------------------------
    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        # A RadioSet.Changed can be queued while the picker is being rebuilt or
        # while the app is tearing down — the jailbreak tab may already be gone.
        try:
            tab = self.query_one("#jailbreak-tab", JailbreakTab)
        except NoMatches:
            return
        if event.radio_set.id == "jb-tool":
            idx = event.radio_set.pressed_index
            tool = tab.tool_at(idx)
            if tool is not None:
                self._selected_tool = idx
                self._schedule_variant_rebuild(tab, tool)
                tab.show_for_tool(tool, self.devices.snapshot)
        elif event.radio_set.id == "jb-variant":
            tool = self.tools[self._selected_tool]
            # The variant list is rebuilt asynchronously. A Changed event can be
            # queued just as its old buttons are removed, so use the stable index
            # the event carries rather than RadioSet.pressed_index.
            variant = tab.variant_at(event.index)
            if variant is not None:
                tool.select(variant.id)
                # Refresh the action button: Launch (installed) vs Download.
                tab.show_for_tool(tool, self.devices.snapshot)

    # --- Files (AFC) ---------------------------------------------------------
    @work(exclusive=True, group="files")
    async def load_files(self, path: str) -> None:
        files = self.query_one("#files-tab", FilesTab)
        if self.devices.jailbreak_running:
            files.show_error("Device busy — a jailbreak is running.")
            return
        mode = self.devices.snapshot.mode
        if mode != "normal":
            files.show_unavailable(mode)
            return
        try:
            entries = await afc.list_dir(path)
        except Exception as exc:  # noqa: BLE001
            files.show_error(f"Cannot read {path}: {exc}")
            return
        self._files_path = path
        files.render_dir(path, entries)

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        if self.query_one("#tabs", TabbedContent).active == "tab-files":
            self.load_files(self._files_path)

    def on_data_table_row_selected(self, event) -> None:
        if getattr(event.data_table, "id", None) != "files-table":
            return
        kind, entry = self.query_one("#files-tab", FilesTab).target_for_row(event.cursor_row)
        if kind == "up":
            self.load_files(parent_path(self._files_path))
        elif kind == "dir" and entry is not None:
            self.load_files(join_path(self._files_path, entry.name))
        elif kind == "file" and entry is not None:
            self.preview_file(entry)

    @work(exclusive=True, group="preview")
    async def preview_file(self, entry) -> None:
        if self.devices.jailbreak_running:
            return
        full = join_path(self._files_path, entry.name)
        if entry.size and entry.size > 1_000_000:
            text = "(file too large to preview — use Download)"
        else:
            try:
                text = await afc.read_text(full)
            except Exception as exc:  # noqa: BLE001
                text = f"Cannot read file: {exc}"
        self.push_screen(
            FilePreviewScreen(entry.name, text or "(empty file)", full),
            self._on_preview_dismiss,
        )

    def _on_preview_dismiss(self, result) -> None:
        if result and result[0] == "download":
            self.pull_file(result[1])

    @work(exclusive=True, group="pull")
    async def pull_file(self, remote_path: str) -> None:
        if self.devices.jailbreak_running:
            self.notify("Device busy — a jailbreak is running.", severity="warning")
            return
        # ~/idevice-tui-downloads/<device>/<mirrored device path> so identical
        # names from different phones/folders don't overwrite each other; the
        # same file from the same phone still lands on the same path.
        info = self.devices.snapshot.info
        folder = device_download_folder(info) if info is not None else "unknown-device"
        try:
            local = device_download_path(self._download_dir, folder, remote_path)
        except ValueError as exc:
            self.notify(f"Download failed: {exc}", severity="error")
            return
        try:
            saved = await afc.pull_file(remote_path, local)
        except Exception as exc:  # noqa: BLE001
            self.notify(f"Download failed: {exc}", severity="error")
            return
        self._last_download = Path(saved)
        # Textual toast (rendered inside the TUI — visible on any DE/WM). Longer
        # timeout so the clickable links stay reachable.
        self.notify(
            f"Saved: {saved}\n[@click=app.open_download]open[/] · "
            f"[@click=app.reveal_download]show in folder[/]",
            timeout=12,
        )

    def _download_ready(self):
        if self._last_download is None:
            return None
        if not self._last_download.exists():
            self.notify("The downloaded file no longer exists.", severity="warning")
            return None
        return self._last_download

    def action_open_download(self) -> None:
        target = self._download_ready()
        if target is not None:
            try:
                opener.open_path(str(target))
            except Exception as exc:  # noqa: BLE001
                self.notify(f"Could not open: {exc}", severity="error")

    def action_reveal_download(self) -> None:
        target = self._download_ready()
        if target is not None:
            try:
                opener.reveal_path(str(target))
            except Exception as exc:  # noqa: BLE001
                self.notify(f"Could not open file manager: {exc}", severity="error")

    # --- Syslog --------------------------------------------------------------
    @work(exclusive=True, group="syslog")
    async def stream_syslog(self) -> None:
        tab = self.query_one("#syslog-tab", SyslogTab)
        if self.devices.jailbreak_running:
            tab.set_status("[yellow]Device busy — a jailbreak is running.[/yellow]")
            return
        if self.devices.snapshot.mode != "normal":
            tab.set_status(f"[dim]Syslog needs a normal-mode device — N/A in {self.devices.snapshot.mode}.[/dim]")
            return
        tab.set_status("[green]streaming…[/green]  (Stop to end)")
        try:
            # aclosing() so worker.cancel() deterministically closes the syslog
            # service + lockdown (the async generator's finally), not on GC.
            async with aclosing(syslog.stream()) as lines:
                async for line in lines:
                    # read the cached filter (updated by on_input_changed), not a
                    # DOM query per line
                    tab.add_line(line, self._syslog_filter)
        except Exception as exc:  # noqa: BLE001
            tab.set_status(f"[red]syslog error: {exc}[/red]")
            return
        tab.set_status("[dim]stopped[/dim]")

    def _start_syslog(self) -> None:
        self._syslog_worker = self.stream_syslog()

    def _stop_syslog(self) -> None:
        if self._syslog_worker is not None:
            self._syslog_worker.cancel()
            self._syslog_worker = None
        try:
            self.query_one("#syslog-tab", SyslogTab).set_status("[dim]stopped[/dim]")
        except NoMatches:
            return

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "syslog-filter":
            self._syslog_filter = event.value.strip()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid == "syslog-start":
            self._start_syslog()
        elif bid == "syslog-stop":
            self._stop_syslog()
        elif bid == "syslog-clear":
            self.query_one("#syslog-tab", SyslogTab).clear()
        elif bid == "jb-launch":
            if self.tools[self._selected_tool].is_ready():
                self.launch_jailbreak()
            else:
                self.download_selected()
        elif bid == "jb-uninstall":
            self.uninstall_selected()
        elif bid == "info-refresh":
            self._do_refresh()
        elif bid == "kit-clone":
            self.clone_kit()
        elif bid.startswith("kit-"):
            self.launch_kit(bid.removeprefix("kit-"))


def main() -> None:
    IDeviceApp().run()

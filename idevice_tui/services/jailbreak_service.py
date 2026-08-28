"""Application policy for launching a jailbreak tool in a watchable window.

`launch` prepares the tool (download if needed), builds the sized terminal
command, floats it on tiling WMs, and spawns it as a trackable process. The UI
then awaits `wait` in a worker so it can flip the jailbreak-running state and
refresh the device when the window closes.
"""
from __future__ import annotations

from ..domain.models import DeviceSnapshot
from ..infra import process, terminal
from ..jailbreaks.base import JailbreakTool


class LaunchResult:
    __slots__ = ("proc", "error", "terminal")

    def __init__(self, proc=None, error: str | None = None, terminal: str = ""):
        self.proc = proc
        self.error = error
        self.terminal = terminal


class JailbreakService:
    def __init__(
        self,
        *,
        detect_terminal=None,
        current_terminal=None,
        terminal_command=None,
        floating_setup=None,
        run_wm_setup=None,
        spawn=None,
        wait_for=None,
    ) -> None:
        # resolve at construction so tests can patch the infra funcs
        self._detect_terminal = detect_terminal or terminal.detect_terminal
        self._current_terminal = current_terminal or terminal.current_terminal
        self._terminal_command = terminal_command or terminal.terminal_command
        self._floating_setup = floating_setup or terminal.floating_setup_commands
        self._run_wm_setup = run_wm_setup or process.run_wm_setup
        self._spawn = spawn or process.spawn
        self._wait_for = wait_for or process.wait_for

    def launch(self, tool: JailbreakTool, snapshot: DeviceSnapshot) -> LaunchResult:
        if not tool.is_available():
            return LaunchResult(error=f"{tool.name} is not available.")
        err = tool.prepare()
        if err:
            return LaunchResult(error=err)
        term = self._detect_terminal(current=self._current_terminal())
        if not term:
            return LaunchResult(
                error="No supported terminal emulator found "
                "(need kitty, foot, alacritty or xterm)."
            )
        spec = tool.build_launch(snapshot)
        cmd = self._terminal_command(term, spec.argv)
        # tiling WMs size the window to the layout; float it first so the tool's
        # required size is honoured.
        for setup in self._floating_setup():
            try:
                self._run_wm_setup(setup)
            except Exception:  # noqa: BLE001 — best effort
                pass
        try:
            proc = self._spawn(cmd)
        except Exception as exc:  # noqa: BLE001
            return LaunchResult(error=f"Could not open terminal: {exc}")
        return LaunchResult(proc=proc, terminal=term)

    async def wait(self, proc) -> int:
        """Block until the tool's window exits; returns its exit code."""
        return await self._wait_for(proc)

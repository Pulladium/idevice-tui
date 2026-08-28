"""Application policy for reading the device across modes.

Owns the unified DeviceSnapshot and the rules the UI must not re-implement:
- mode/presence come from the safe lsusb scan (pollable);
- lockdown reads happen when a normal device appears;
- irecv (recovery/DFU) reads are edge-triggered on mode entry and SUPPRESSED
  while a jailbreak is running, then run once via `refresh()` when it ends.

Infra functions are injected so this is unit-testable without hardware.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable

from ..domain.models import (
    DeviceMode,
    DeviceSnapshot,
    NoDeviceError,
    NotPairedError,
)
from ..infra import irecv, lockdown, usb_modes


class DeviceService:
    def __init__(
        self,
        *,
        read_mode: Callable[[], Awaitable[DeviceMode]] | None = None,
        read_info=None,
        read_battery=None,
        read_jailbreak=None,
        read_recovery=None,
    ) -> None:
        # resolve at construction (not import) so tests can patch the infra funcs
        self._read_mode = read_mode or usb_modes.read_device_mode
        self._read_info = read_info or lockdown.read_device_info
        self._read_battery = read_battery or lockdown.read_battery
        self._read_jailbreak = read_jailbreak or lockdown.read_jailbreak
        self._read_recovery = read_recovery or irecv.read_recovery_device
        self.snapshot = DeviceSnapshot(mode="none")
        self.jailbreak_running = False

    # --- polling (safe; called on a timer) ----------------------------------
    async def poll(self) -> DeviceSnapshot:
        """Cheap, USB-safe refresh of mode/presence.

        Full details load on a mode transition or while a prior read is
        incomplete, and never while a jailbreak is running.
        """
        if self.jailbreak_running:
            return self.snapshot
        mode = await self._read_mode()
        prev = self.snapshot.mode
        if mode != prev or self._needs_retry(mode):
            await self._load_for(mode)
        else:
            self.snapshot.mode = mode
        return self.snapshot

    # --- explicit user refresh (r / button) ---------------------------------
    async def refresh(self) -> DeviceSnapshot:
        """Force a full re-read for the current mode (used on user Refresh and
        when a jailbreak finishes)."""
        if self.jailbreak_running:
            return self.snapshot
        mode = await self._read_mode()
        await self._load_for(mode)
        return self.snapshot

    async def refresh_battery(self) -> None:
        if self.snapshot.mode != "normal":
            return
        try:
            self.snapshot.battery = await self._read_battery()
        except Exception:  # noqa: BLE001 — leave last value on failure
            pass

    # --- loaders ------------------------------------------------------------
    def _needs_retry(self, mode: DeviceMode) -> bool:
        """Retry incomplete reads without repeatedly probing healthy devices.

        A normal-mode device may become trusted after the initial poll, and an
        irecv probe can miss a device while it is entering recovery/DFU. Both
        cases used to remain blank until the user explicitly pressed Refresh.
        """
        if mode == "normal":
            return self.snapshot.info is None
        if mode in ("recovery", "dfu"):
            return self.snapshot.recovery is None
        return False

    async def _load_for(self, mode: DeviceMode) -> None:
        if mode == "normal":
            await self._load_normal()
        elif mode in ("recovery", "dfu"):
            await self._load_recovery(mode)
        else:
            self.snapshot = DeviceSnapshot(mode="none")

    async def _load_normal(self) -> None:
        snap = DeviceSnapshot(mode="normal")
        try:
            snap.info = await self._read_info()
        except NotPairedError:
            snap.note = "Device found — tap “Trust” on the phone."
            self.snapshot = snap
            return
        except NoDeviceError:
            self.snapshot = DeviceSnapshot(mode="none")
            return
        except Exception as exc:  # noqa: BLE001
            snap.note = f"Error: {exc}"
            self.snapshot = snap
            return
        try:
            snap.battery = await self._read_battery()
        except Exception:  # noqa: BLE001
            pass
        try:
            snap.jailbreak = await self._read_jailbreak()
        except Exception:  # noqa: BLE001
            snap.jailbreak = None
        self.snapshot = snap

    async def _load_recovery(self, mode: DeviceMode) -> None:
        # irecv grabs USB — only reached when not jailbreak_running
        info = await self._read_recovery()
        self.snapshot = DeviceSnapshot(mode=mode, recovery=info)

"""Pure domain model: data structures shared across the app.

No I/O, no pymobiledevice3, no Textual — just dataclasses and small helpers so
every other layer speaks the same vocabulary.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

DeviceMode = Literal["normal", "recovery", "dfu", "none"]


class NoDeviceError(Exception):
    """No iOS device is currently connected over USB."""


class NotPairedError(Exception):
    """Device is connected but not trusted/paired yet (tap Trust on the phone)."""


@dataclass
class BatteryInfo:
    level: int | None = None            # current charge %
    is_charging: bool = False
    external_connected: bool = False
    cycle_count: int | None = None
    design_capacity: int | None = None  # mAh
    max_capacity: int | None = None     # mAh (current full capacity)
    temperature: float | None = None    # deg C
    serial: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def health(self) -> int | None:
        if self.design_capacity and self.max_capacity:
            return round(100 * self.max_capacity / self.design_capacity)
        return None


@dataclass
class JailbreakInfo:
    # None = could not determine; True/False = best-effort verdict
    jailbroken: bool | None = None
    signals: list[str] = field(default_factory=list)  # human-readable evidence
    ssh: str | None = None                          # e.g. "dropbear_2019.78 on :44"

    @property
    def summary(self) -> str:
        if self.jailbroken is None:
            return "unknown"
        if not self.jailbroken:
            return "not detected"
        return "yes"


@dataclass
class DeviceInfo:
    """Full identity read over lockdown (normal mode only)."""

    udid: str
    name: str
    product_type: str          # e.g. iPhone6,2
    product_name: str          # friendly, e.g. iPhone 5s
    ios_version: str
    build: str
    serial: str
    cpu_arch: str
    unique_chip_id: int | None
    imei: str | None
    imei2: str | None
    wifi_address: str | None
    bluetooth_address: str | None
    phone_number: str | None
    activation_state: str | None
    region: str | None
    all_values: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RecoveryDeviceInfo:
    """Identity read over irecv (recovery/DFU mode)."""

    mode: str                       # "recovery" | "DFU" | other
    display_name: str | None     # e.g. "iPhone 5s (Global)"
    product_type: str | None     # e.g. "iPhone6,2"
    ecid: int | None
    hardware_model: str | None   # e.g. "n53ap"
    chip_id: int | None


@dataclass(frozen=True)
class LaunchSpec:
    """How a jailbreak tool wants to be launched: the argv to run in a fresh,
    watchable terminal window. `needs_root` documents that argv already uses
    sudo (kept for callers that want to reason about it)."""

    argv: list[str]
    needs_root: bool = False


@dataclass
class DeviceSnapshot:
    """The unified device view rendered by the Info tab, populated from whatever
    source the current mode allows. Fields that a mode can't provide stay None
    and render as `N/A in <mode>`.
    """

    mode: DeviceMode = "none"
    info: DeviceInfo | None = None            # lockdown (normal)
    recovery: RecoveryDeviceInfo | None = None  # irecv (recovery/DFU)
    battery: BatteryInfo | None = None
    jailbreak: JailbreakInfo | None = None
    note: str | None = None                    # transient status (not paired, error)

    @property
    def present(self) -> bool:
        return self.mode != "none"

    @property
    def product_type(self) -> str | None:
        """Model identifier from whichever source the current mode has."""
        if self.info is not None:
            return self.info.product_type
        if self.recovery is not None:
            return self.recovery.product_type
        return None

    @property
    def ecid(self) -> int | None:
        if self.info is not None:
            return self.info.unique_chip_id
        if self.recovery is not None:
            return self.recovery.ecid
        return None

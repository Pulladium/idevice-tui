"""Device-mode detection via USB product IDs (safe to poll — no USB claim)."""
from __future__ import annotations

import re
import subprocess

from ..domain.models import DeviceMode
from .lockdown import connected_udids

_APPLE_VID = 0x05AC
# Ground truth: Legacy-iOS-Kit/restore.sh — 1227 -> dfu, 1281 -> recovery,
# 1222 -> wtf. WTF is treated as part of the dfu family so Tools actions stay
# enabled while a device is stuck in WTF mode.
_DFU_PIDS = {0x1227, 0x1222}
_RECOVERY_PIDS = {0x1281}


def _apple_usb_mode(usb_ids: set[tuple[int, int]]) -> DeviceMode | None:
    for vid, pid in usb_ids:
        if vid != _APPLE_VID:
            continue
        if pid in _DFU_PIDS:
            return "dfu"
        if pid in _RECOVERY_PIDS:
            return "recovery"
    return None


def _lsusb_ids() -> set[tuple[int, int]]:
    try:
        out = subprocess.run(["lsusb"], capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return set()
    ids = set()
    for m in re.finditer(r"ID ([0-9a-fA-F]{4}):([0-9a-fA-F]{4})", out):
        ids.add((int(m.group(1), 16), int(m.group(2), 16)))
    return ids


async def read_device_mode() -> DeviceMode:
    if await connected_udids():
        return "normal"
    mode = _apple_usb_mode(_lsusb_ids())
    return mode or "none"

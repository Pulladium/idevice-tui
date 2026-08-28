"""File browsing over AFC (Apple File Conduit), normal mode only.

AFC exposes the device's media partition (/var/mobile/Media): DCIM, Photos,
Downloads, iTunes_Control, etc. `listdir`/`stat` are synchronous once the
service is connected, so each call opens lockdown, connects AFC, reads, closes.
"""
from __future__ import annotations

import inspect
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.afc import AfcService

from .filesystem import atomic_write_bytes
from .lockdown import _close


async def _maybe_await(value):
    return await value if inspect.isawaitable(value) else value


@dataclass
class AfcEntry:
    name: str
    is_dir: bool
    size: int
    mtime: datetime | None


def join_path(path: str, name: str) -> str:
    base = path.rstrip("/")
    return f"{base}/{name}" if base else f"/{name}"


def parent_path(path: str) -> str:
    p = path.rstrip("/")
    if not p or p == "":
        return "/"
    parent = p.rsplit("/", 1)[0]
    return parent or "/"


def _entry_from_stat(name: str, st: dict) -> AfcEntry:
    return AfcEntry(
        name=name,
        is_dir=(st.get("st_ifmt") == "S_IFDIR"),
        size=int(st.get("st_size") or 0),
        mtime=st.get("st_mtime"),
    )


def _sort_entries(entries: list[AfcEntry]) -> list[AfcEntry]:
    # directories first, then case-insensitive by name
    return sorted(entries, key=lambda e: (not e.is_dir, e.name.lower()))


async def list_dir(path: str = "/", serial: str | None = None) -> list[AfcEntry]:
    ld = await create_using_usbmux(serial=serial)
    afc = None
    try:
        afc = AfcService(ld)
        await afc.connect()
        names = await _maybe_await(afc.listdir(path))
        entries: list[AfcEntry] = []
        for n in names:
            if n in (".", ".."):
                continue
            try:
                st = await _maybe_await(afc.stat(join_path(path, n)))
                entries.append(_entry_from_stat(n, dict(st)))
            except Exception:  # noqa: BLE001 — unreadable entry: show it as a file
                entries.append(AfcEntry(n, False, 0, None))
        return _sort_entries(entries)
    finally:
        if afc is not None:
            try:
                await afc.aclose()
            except Exception:
                pass
        await _close(ld)


def preview_text(data: bytes, max_bytes: int = 65536) -> str:
    """Decode a file for preview, or a note if it looks binary (has NUL bytes)."""
    chunk = data[:max_bytes]
    if b"\x00" in chunk:
        return f"(binary file — {len(data)} bytes, preview not shown)"
    return chunk.decode("utf-8", errors="replace")


async def pull_file(remote_path: str, local_path, serial: str | None = None) -> Path:
    """Copy a file off the device to local_path (returns the local path)."""
    local = Path(local_path)
    ld = await create_using_usbmux(serial=serial)
    afc = None
    try:
        afc = AfcService(ld)
        await afc.connect()
        data = await _maybe_await(afc.get_file_contents(remote_path))
        if isinstance(data, str):
            data = data.encode()
        return atomic_write_bytes(local, data)
    finally:
        if afc is not None:
            try:
                await afc.aclose()
            except Exception:
                pass
        await _close(ld)


async def read_text(path: str, max_bytes: int = 65536, serial: str | None = None) -> str:
    """Best-effort text preview of a file (truncated; binary files noted)."""
    ld = await create_using_usbmux(serial=serial)
    afc = None
    try:
        afc = AfcService(ld)
        await afc.connect()
        data = await _maybe_await(afc.get_file_contents(path))
        if isinstance(data, str):
            data = data.encode(errors="replace")
        return preview_text(data, max_bytes)
    finally:
        if afc is not None:
            try:
                await afc.aclose()
            except Exception:
                pass
        await _close(ld)

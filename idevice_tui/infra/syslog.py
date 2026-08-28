"""Live device syslog stream (normal mode) via pymobiledevice3 SyslogService."""
from __future__ import annotations

from collections.abc import AsyncIterator

from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.syslog import SyslogService

from .lockdown import _close


def decode_line(line) -> str:
    return line.decode(errors="replace") if isinstance(line, (bytes, bytearray)) else str(line)


async def stream(serial: str | None = None) -> AsyncIterator[str]:
    """Yield syslog lines until the consumer stops (cancellation runs cleanup)."""
    ld = await create_using_usbmux(serial=serial)
    sl = SyslogService(ld)
    await sl.connect()
    try:
        async for line in sl.watch():
            yield decode_line(line)
    finally:
        try:
            await sl.close()
        except Exception:
            pass
        await _close(ld)

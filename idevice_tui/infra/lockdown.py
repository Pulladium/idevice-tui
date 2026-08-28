"""Normal-mode device I/O over usbmux + lockdown (pymobiledevice3, async)."""
from __future__ import annotations

import asyncio
import inspect

from pymobiledevice3 import usbmux
from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.diagnostics import DiagnosticsService

from ..domain.models import (
    BatteryInfo,
    DeviceInfo,
    JailbreakInfo,
    NoDeviceError,
    NotPairedError,
)
from .device_names import device_display_name


async def _maybe_await(value):
    if inspect.isawaitable(value):
        return await value
    return value


async def connected_udids() -> list[str]:
    """UDIDs of all currently attached USB devices ([] if usbmuxd is quiet)."""
    try:
        devices = await usbmux.list_devices()
        return [d.serial for d in devices]
    except Exception:
        return []


async def _connect(serial: str | None = None):
    if not await connected_udids():
        raise NoDeviceError()
    try:
        return await create_using_usbmux(serial=serial)
    except Exception as exc:  # pairing / trust problems surface here
        name = type(exc).__name__.lower()
        if "pair" in name or "trust" in name or "password" in name:
            raise NotPairedError() from exc
        raise


async def _close(lockdown) -> None:
    try:
        await _maybe_await(lockdown.close())
    except Exception:
        pass


async def read_device_info(serial: str | None = None) -> DeviceInfo:
    lockdown = await _connect(serial)
    try:
        v = lockdown.all_values
    finally:
        await _close(lockdown)

    product_type = v.get("ProductType", "?")
    return DeviceInfo(
        udid=v.get("UniqueDeviceID", serial or "?"),
        name=v.get("DeviceName", "iPhone"),
        product_type=product_type,
        product_name=device_display_name(product_type),
        ios_version=v.get("ProductVersion", "?"),
        build=v.get("BuildVersion", "?"),
        serial=v.get("SerialNumber", "?"),
        cpu_arch=v.get("CPUArchitecture", "?"),
        unique_chip_id=v.get("UniqueChipID"),
        imei=v.get("InternationalMobileEquipmentIdentity"),
        imei2=v.get("InternationalMobileEquipmentIdentity2"),
        wifi_address=v.get("WiFiAddress"),
        bluetooth_address=v.get("BluetoothAddress"),
        phone_number=v.get("PhoneNumber"),
        activation_state=v.get("ActivationState"),
        region=v.get("RegionInfo"),
        all_values=v,
    )


async def read_battery(serial: str | None = None) -> BatteryInfo:
    lockdown = await _connect(serial)
    try:
        diag = DiagnosticsService(lockdown)
        await _maybe_await(diag.connect())
        try:
            snap = await diag.get_battery()
        finally:
            await _maybe_await(diag.close())
    finally:
        await _close(lockdown)

    bdata = snap.get("BatteryData", {}) or {}
    temp_raw = snap.get("Temperature") or bdata.get("Temperature")
    temperature = round(temp_raw / 100, 1) if isinstance(temp_raw, (int, float)) else None

    return BatteryInfo(
        level=snap.get("CurrentCapacity"),
        is_charging=bool(snap.get("IsCharging")),
        external_connected=bool(snap.get("ExternalConnected")),
        cycle_count=bdata.get("CycleCount"),
        design_capacity=bdata.get("DesignCapacity"),
        max_capacity=bdata.get("MaxCapacity") or snap.get("AppleRawMaxCapacity"),
        temperature=temperature,
        serial=bdata.get("BatterySerialNumber"),
        raw=snap,
    )


# Ports jailbreaks expose an SSH server on, over usbmux:
#   44 = checkra1n / palera1n (dropbear)   22 = unc0ver / rootful OpenSSH
_SSH_PORTS = (44, 22)


async def _ssh_banner(mux_device, port: int) -> str | None:
    """Return the SSH banner if something SSH-like answers on ``port``."""
    try:
        conn = await mux_device.connect(port)
    except Exception:
        return None  # connection refused -> nothing listening
    sock = getattr(conn, "socket", None) or conn
    data = b""
    try:
        if hasattr(sock, "settimeout"):
            sock.settimeout(2.0)
        # usbmux exposes a regular blocking socket here. Move the receive off
        # the Textual event loop: two unreachable jailbreak ports used to make
        # the UI freeze for up to four seconds during a device refresh.
        data = await asyncio.to_thread(sock.recv, 64)
    except Exception:
        data = b""
    finally:
        try:
            await _maybe_await(conn.close())
        except Exception:
            pass
    if data.startswith(b"SSH-"):
        return data.split(b"\r", 1)[0].split(b"\n", 1)[0].decode(errors="replace")
    return None


async def read_jailbreak(serial: str | None = None) -> JailbreakInfo:
    """Best-effort jailbreak detection over USB.

    Two independent signals, either of which is conclusive:
      1. An SSH server (dropbear/OpenSSH) reachable on port 44 or 22 — the
         classic checkra1n/palera1n/unc0ver tell. Verified by reading the
         ``SSH-...`` banner so an open-but-silent socket is not a false hit.
      2. The ``com.apple.afc2`` lockdown service, which only exists once a
         jailbreak has installed it (stock devices raise InvalidService).
    """
    devices = await usbmux.list_devices()
    if not devices:
        raise NoDeviceError()
    d = next((x for x in devices if serial is None or x.serial == serial), devices[0])

    signals: list[str] = []
    ssh: str | None = None
    for port in _SSH_PORTS:
        banner = await _ssh_banner(d, port)
        if banner:
            ssh = f"{banner} on :{port}"
            signals.append(f"SSH server ({banner}) on port {port}")
            break

    try:
        lockdown = await _connect(serial)
    except NoDeviceError:
        raise
    except Exception:
        lockdown = None
    if lockdown is not None:
        try:
            svc = await _maybe_await(lockdown.start_lockdown_service("com.apple.afc2"))
            signals.append("com.apple.afc2 service present")
            try:
                await _maybe_await(svc.close())
            except Exception:
                pass
        except Exception:
            pass  # InvalidService on stock devices -> just no signal
        finally:
            await _close(lockdown)

    return JailbreakInfo(jailbroken=bool(signals), signals=signals, ssh=ssh)

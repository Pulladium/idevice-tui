"""Recovery/DFU device identity via pymobiledevice3.irecv.

ON-DEMAND ONLY: IRecv claims the USB interface, so a read mid-checkm8 can
disrupt an active jailbreak. Never call this from a poll; callers gate it on the
jailbreak-running state.
"""
from __future__ import annotations

import asyncio

from pymobiledevice3 import irecv as _irecv

from ..domain.models import RecoveryDeviceInfo


def _read_sync(timeout: int = 2) -> RecoveryDeviceInfo | None:
    # _find loops until `timeout` seconds elapse, so keep it small; the context
    # manager releases the USB handle immediately after we read the fields.
    try:
        with _irecv.IRecv(timeout=timeout) as d:
            if d.mode.is_recovery:
                mode = "recovery"
            elif d.mode == _irecv.Mode.DFU_MODE:
                mode = "DFU"
            else:
                mode = d.mode.name
            return RecoveryDeviceInfo(
                mode=mode,
                display_name=d.display_name,
                product_type=d.product_type,
                ecid=d.ecid,
                hardware_model=d.hardware_model,
                chip_id=d.chip_id,
            )
    except _irecv.IRecvNoDeviceConnectedError:
        return None
    except Exception:
        return None


async def read_recovery_device(timeout: int = 2) -> RecoveryDeviceInfo | None:
    """Info for a device in recovery/DFU, or None. On-demand only."""
    return await asyncio.to_thread(_read_sync, timeout)

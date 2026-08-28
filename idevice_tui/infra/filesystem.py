"""Small, dependency-free filesystem primitives shared by infrastructure.

These helpers keep partially written downloads from replacing a known-good
file when a process is interrupted or a disk write fails.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path


def atomic_write_bytes(path: Path | str, data: bytes, *, mode: int | None = None) -> Path:
    """Atomically replace ``path`` with ``data`` and optionally set its mode.

    The temporary file lives beside the destination, so ``os.replace`` is an
    atomic operation on the target filesystem. A failed write leaves any
    existing destination untouched and removes the temporary file.
    """
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        dir=destination.parent, prefix=f".{destination.name}.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        if mode is not None:
            temporary.chmod(mode)
        os.replace(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return destination

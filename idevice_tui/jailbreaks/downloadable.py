"""Shared base for jailbreak tools that are a single downloadable binary run in
a hand-off window (checkra1n, palera1n, …).

A concrete tool only declares:
- ``id``, ``name``, ``binary_prefix`` (binary is ``<prefix>-<version>`` under the
  tools dir),
- ``known_versions``: ``{version: (label, url|None)}``,
- optionally ``launch_flags``, and overrides ``supports()`` / ``guidance()`` /
  ``recommended_variant()``.

Everything else — version discovery, install/download state, the
``(installed)`` / ``⬇ download`` markers, ``is_ready``, ``select``, ``prepare``,
``download``, ``uninstall``, ``build_launch`` — lives here once.
"""
from __future__ import annotations

import re
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ..domain.models import DeviceSnapshot, LaunchSpec
from ..infra.filesystem import atomic_write_bytes
from .base import JailbreakTool, Variant

TOOLS_DIR = Path.home() / "jailbreak-tools"
DOWNLOAD_TIMEOUT = 60


@dataclass(frozen=True)
class ToolVersion:
    version: str
    label: str
    url: str | None       # download source; None = must already be on disk


def _http_fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=DOWNLOAD_TIMEOUT) as resp:  # noqa: S310 — official source
        return resp.read()


def _version_key(v: str):
    return [(0, int(p)) if p.isdigit() else (1, p) for p in re.split(r"[.\-]", v)]


class DownloadableTool(JailbreakTool):
    binary_prefix: str = ""
    known_versions: dict[str, tuple[str, str | None]] = {}
    launch_flags: list[str] = []

    def __init__(self, tools_dir: Path | None = None) -> None:
        self._tools_dir = tools_dir
        self._version = ""
        self._versions: list[ToolVersion] = []
        self._remote: dict[str, tuple[str, str | None]] = {}
        self._refresh_versions()

    def _all_known(self) -> dict[str, tuple[str, str | None]]:
        # static known_versions + any versions fetched from an online source
        return {**self.known_versions, **self._remote}

    async def fetch_remote_versions(self) -> bool:
        """Populate self._remote from an online source and rebuild the version
        list. Return True if the list changed. Default: no remote source."""
        return False

    # --- paths / disk state -------------------------------------------------
    def _dir(self) -> Path:
        return self._tools_dir or TOOLS_DIR

    def binary_path(self, version: str | None = None) -> Path:
        return self._dir() / f"{self.binary_prefix}-{version or self._version}"

    def is_downloaded(self, version: str | None = None) -> bool:
        return self.binary_path(version).is_file()

    # --- version discovery --------------------------------------------------
    def _refresh_versions(self) -> None:
        """Every ``<prefix>-<version>`` binary on disk, plus every known version
        with a download URL; installed first, then newest→oldest."""
        known = self._all_known()
        found: dict[str, ToolVersion] = {}
        try:
            for p in self._dir().glob(f"{self.binary_prefix}-*"):
                if p.is_file():
                    ver = p.name[len(self.binary_prefix) + 1:]
                    if ver:
                        label, url = known.get(ver, (ver, None))
                        found[ver] = ToolVersion(ver, label, url)
        except OSError:
            pass
        for ver, (label, url) in known.items():
            if url and ver not in found:
                found[ver] = ToolVersion(ver, label, url)
        if not found:
            found = {v: ToolVersion(v, lbl, url) for v, (lbl, url) in known.items()}
        ordered = sorted(found.values(), key=lambda v: _version_key(v.version), reverse=True)
        ordered.sort(key=lambda v: 0 if self.is_downloaded(v.version) else 1)  # installed first
        self._versions = ordered
        if self._version not in {v.version for v in ordered}:
            self._version = ordered[0].version if ordered else ""

    def _url_for(self, version: str) -> str | None:
        return next((v.url for v in self._versions if v.version == version), None)

    # --- JailbreakTool API --------------------------------------------------
    def is_available(self) -> bool:
        return any(self.is_downloaded(v.version) or v.url for v in self._versions)

    def is_ready(self) -> bool:
        return self.is_downloaded(self._version)

    def variants(self) -> list[Variant]:
        # no check-glyph in the marker — it collides with the radio's own mark
        out = []
        for v in self._versions:
            mark = "(installed)" if self.is_downloaded(v.version) else "⬇ download"
            out.append(Variant(v.version, f"{v.label}  {mark}"))
        return out

    def select(self, variant_id: str) -> None:
        if any(v.version == variant_id for v in self._versions):
            self._version = variant_id

    def download(self, version: str, url: str, *, fetch: Callable[[str], bytes] | None = None) -> Path:
        fetch = fetch or _http_fetch   # resolve at call time so tests can patch
        dest = self.binary_path(version)
        return atomic_write_bytes(dest, fetch(url), mode=0o700)

    def prepare(self) -> str | None:
        if self.is_downloaded(self._version):
            return None
        url = self._url_for(self._version)
        if not url:
            return f"{self.name} {self._version} is not downloaded and has no download source."
        try:
            self.download(self._version, url)
        except Exception as exc:  # noqa: BLE001
            return f"Download failed: {exc}"
        self._refresh_versions()
        return None

    def uninstall(self) -> str | None:
        try:
            self.binary_path().unlink()
        except FileNotFoundError:
            return f"{self.name} {self._version} is not installed."
        except OSError as exc:  # noqa: BLE001
            return f"Could not uninstall {self.name} {self._version}: {exc}"
        self._refresh_versions()
        return None

    def build_launch(self, snapshot: DeviceSnapshot) -> LaunchSpec:
        argv = ["sudo", str(self.binary_path()), *self.launch_flags]
        return LaunchSpec(argv=argv, needs_root=True)

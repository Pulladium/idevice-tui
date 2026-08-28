"""palera1n backend — a DownloadableTool. checkm8 jailbreak for A8–A11 on iOS
15+. Does NOT support the A7 iPhone 5s — use checkra1n there.

Versions are scraped from the GitHub releases API (fetch_remote_versions); the
download URLs are predictable per tag, unlike checkra.in. KNOWN_VERSIONS is an
offline fallback.
"""
from __future__ import annotations

import asyncio
import json
import urllib.request

from ..domain.models import DeviceSnapshot
from .downloadable import DownloadableTool

# palera1n has no A7 support; the 5s (A7) must use checkra1n.
_A7_PRODUCT_TYPES = {"iPhone6,1", "iPhone6,2"}

_RELEASES_API = "https://api.github.com/repos/palera1n/palera1n/releases?per_page=30"
# We take only the RAW linux binary asset; newer releases ship a .tar.gz that
# would need extracting, so those are skipped.
_ASSET_NAME = "palera1n-linux-x86_64"

# Offline fallback (github.com release asset). version -> (label, url).
KNOWN_VERSIONS: dict[str, tuple[str, str | None]] = {
    "2.4": (
        "v2.4",
        f"https://github.com/palera1n/palera1n/releases/download/v2.4/{_ASSET_NAME}",
    ),
}


def palera1n_guidance(product_type: str | None) -> str:
    if product_type in _A7_PRODUCT_TYPES:
        return (
            "[yellow]palera1n does not support the A7 iPhone 5s.[/yellow] "
            "Use [b]checkra1n[/b] for this device."
        )
    return (
        "[b]palera1n[/b] — checkm8 jailbreak for A8–A11 devices on iOS 15+.\n"
        "Put the device into DFU when prompted; palera1n drives its own menu in "
        "the launched window (the root password is asked there)."
    )


def _fetch_releases(url: str = _RELEASES_API) -> list:
    req = urllib.request.Request(url, headers={"User-Agent": "idevice-tui"})
    with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310 — GitHub API
        return json.load(resp)


def parse_releases(releases: list) -> dict[str, tuple[str, str | None]]:
    """Map version -> (label, url) for releases that ship the raw linux binary."""
    out: dict[str, tuple[str, str | None]] = {}
    for rel in releases:
        if not isinstance(rel, dict):
            continue
        tag = rel.get("tag_name") or ""
        if not isinstance(tag, str):
            continue
        version = tag[1:] if tag.startswith("v") else tag
        if not version:
            continue
        url = next(
            (a.get("browser_download_url") for a in (rel.get("assets") or [])
             if isinstance(a, dict) and a.get("name") == _ASSET_NAME),
            None,
        )
        if url:
            label = f"{tag} (beta)" if rel.get("prerelease") else tag
            out[version] = (label, url)
    return out


class Palera1nTool(DownloadableTool):
    id = "palera1n"
    name = "palera1n"
    binary_prefix = "palera1n"
    known_versions = KNOWN_VERSIONS

    async def fetch_remote_versions(self) -> bool:
        try:
            releases = await asyncio.to_thread(_fetch_releases)
            remote = parse_releases(releases)
        except Exception:  # noqa: BLE001 — offline / API error: keep fallback
            return False
        if not remote or remote == self._remote:
            return False
        self._remote = remote
        self._refresh_versions()
        return True

    def supports(self, snapshot: DeviceSnapshot) -> bool:
        # no A7 support; other devices (or no device yet) are fine
        return snapshot.product_type not in _A7_PRODUCT_TYPES

    def guidance(self, snapshot: DeviceSnapshot) -> str | None:
        return palera1n_guidance(snapshot.product_type)

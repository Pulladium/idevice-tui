"""The ordered list of jailbreak tools the UI offers. Add a tool here."""
from __future__ import annotations

from pathlib import Path

from .base import JailbreakTool
from .checkra1n import Checkra1nTool
from .palera1n import Palera1nTool


def build_registry(tools_dir: Path | None = None) -> list[JailbreakTool]:
    # checkra1n and palera1n binaries share ~/jailbreak-tools (overridable)
    return [Checkra1nTool(tools_dir=tools_dir), Palera1nTool(tools_dir=tools_dir)]


def get(registry: list[JailbreakTool], tool_id: str) -> JailbreakTool | None:
    return next((t for t in registry if t.id == tool_id), None)

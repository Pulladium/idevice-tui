"""Pluggable jailbreak-tool abstraction (Strategy pattern).

Add a tool = implement JailbreakTool in one file and list it in registry.py.
The UI renders whatever the registry holds and never names a specific tool.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..domain.models import DeviceSnapshot, LaunchSpec


@dataclass(frozen=True)
class Variant:
    """A selectable sub-option of a tool (e.g. a checkra1n version)."""

    id: str
    label: str


class JailbreakTool(ABC):
    id: str = ""
    name: str = ""

    @abstractmethod
    def is_available(self) -> bool:
        """True if the tool can actually be run (installed or installable)."""

    def is_ready(self) -> bool:
        """True if the currently-selected variant is already downloaded (so the
        launch button says "Launch" rather than "Download")."""
        return True

    def supports(self, snapshot: DeviceSnapshot) -> bool:
        """Whether this tool applies to the attached device/mode."""
        return True

    def guidance(self, snapshot: DeviceSnapshot) -> str | None:
        """Optional device-specific instructions to show before launch."""
        return None

    def variants(self) -> list[Variant]:
        """Selectable variants (versions/editions); empty if none."""
        return []

    def recommended_variant(self, snapshot: DeviceSnapshot) -> str | None:
        """The variant best suited to this device, if the tool has one."""
        return None

    def select(self, variant_id: str) -> None:
        """Choose a variant (no-op if the tool has none)."""

    def prepare(self) -> str | None:
        """Do any pre-launch work (e.g. download). Return an error string on
        failure, or None on success."""
        return None

    def uninstall(self) -> str | None:
        """Remove the selected locally installed binary, if supported."""
        return f"{self.name} does not support uninstalling from this app."

    @abstractmethod
    def build_launch(self, snapshot: DeviceSnapshot) -> LaunchSpec:
        """The argv to run in a fresh terminal window."""

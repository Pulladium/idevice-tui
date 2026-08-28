from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

REPO_URL = "https://github.com/LukeZGD/Legacy-iOS-Kit"

# action name -> extra flags (empty = menu-driven, prefills only)
ACTIONS: dict[str, list[str]] = {
    "restore": [],
    "blobs": [],
    "jailbreak": ["--jailbreak"],
    "dfuhelper": ["--dfuhelper"],
    "pwn": ["--pwn"],
    "sshrd": ["--sshrd"],
    "exit_recovery": ["--exit-recovery"],
    "kdfu": ["--kdfu"],
}

@dataclass
class LegacyKit:
    path: Path | None = None

    @classmethod
    def from_path(cls, p: Path | None) -> LegacyKit:
        if p and (p / "restore.sh").is_file():
            return cls(path=p)
        return cls(path=None)

    @classmethod
    def locate(cls, candidates: list[Path]) -> LegacyKit:
        for c in candidates:
            if (c / "restore.sh").is_file():
                return cls(path=c)
        return cls(path=None)

    @property
    def is_available(self) -> bool:
        return self.path is not None

    @staticmethod
    def clone_command(dest: Path) -> list[str]:
        return ["git", "clone", "--depth", "1", REPO_URL, str(dest)]

    def build_command(self, action, *, device_type=None, ecid=None, toggles=None):
        if not self.is_available:
            raise ValueError("Legacy iOS Kit not available")
        if action not in ACTIONS:
            raise ValueError(f"unknown action: {action}")
        cmd = [str((self.path / "restore.sh").resolve())]
        if device_type:
            cmd.append(f"--device={device_type}")
        if ecid is not None:
            cmd.append(f"--ecid={ecid}")
        cmd.extend(ACTIONS[action])
        cmd.extend(toggles or [])
        return cmd

    @staticmethod
    def missing_deps(required=("git", "curl", "jq", "sshpass", "zenity")) -> list[str]:
        return [d for d in required if shutil.which(d) is None]

    def run(self, command: list[str]) -> int:
        # inherited stdio: Legacy iOS Kit's own menu drives the real terminal
        return subprocess.call(command, cwd=str(self.path))

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_CONFIG = Path.home() / ".config" / "idevice-tui" / "config.toml"

_TOGGLE_FLAGS = {
    "enable_sudoloop": "--enable-sudoloop",
    "use_usbmuxd2": "--use-usbmuxd2",
    "disable_usbmuxd": "--disable-usbmuxd",
}

@dataclass
class Config:
    kit_path: Path | None = None
    toggles: list[str] = field(default_factory=list)
    checkra1n_dir: Path | None = None   # override for ~/jailbreak-tools

def default_candidates() -> list[Path]:
    return [
        Path.home() / "Legacy-iOS-Kit",
        Path.home() / ".local" / "share" / "idevice-tui" / "Legacy-iOS-Kit",
    ]

_REV_TOGGLES = {v: k for k, v in _TOGGLE_FLAGS.items()}

def save_config(cfg: Config, path: Path | None = None) -> None:
    path = path or DEFAULT_CONFIG
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["[legacy_kit]"]
    if cfg.kit_path:
        lines.append(f"path = {json.dumps(str(cfg.kit_path))}")
    for flag in cfg.toggles:
        key = _REV_TOGGLES.get(flag)
        if key:
            lines.append(f"{key} = true")
    if cfg.checkra1n_dir:
        lines.append("")
        lines.append("[jailbreak]")
        lines.append(f"checkra1n_dir = {json.dumps(str(cfg.checkra1n_dir))}")
    path.write_text("\n".join(lines) + "\n")

def load_config(path: Path | None = None) -> Config:
    path = path or DEFAULT_CONFIG
    if not path.is_file():
        return Config(kit_path=None, toggles=[])
    try:
        parsed = tomllib.loads(path.read_text())
    except (OSError, tomllib.TOMLDecodeError):
        return Config()
    data = parsed.get("legacy_kit", {})
    data = data if isinstance(data, dict) else {}
    kit_value = data.get("path")
    kit_path = Path(kit_value) if isinstance(kit_value, str) and kit_value else None
    toggles = [flag for key, flag in _TOGGLE_FLAGS.items() if data.get(key)]
    jb = parsed.get("jailbreak", {})
    jb = jb if isinstance(jb, dict) else {}
    tools_value = jb.get("checkra1n_dir")
    checkra1n_dir = Path(tools_value) if isinstance(tools_value, str) and tools_value else None
    return Config(kit_path=kit_path, toggles=toggles, checkra1n_dir=checkra1n_dir)

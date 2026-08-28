"""checkra1n backend — a DownloadableTool. Declares its versions, the iPhone 5s
error-31 guidance, and the 5s version recommendation; all download/version
mechanics live in DownloadableTool.
"""
from __future__ import annotations

from ..domain.models import DeviceSnapshot
from .downloadable import DownloadableTool

# Official Linux x86_64 CLI builds from checkra.in (URLs verified from each
# release page). Linux builds start at 0.9.8 (0.9.7 and earlier are macOS-only).
# A7 caveat: the 5s is A7 — 0.11.0+ dropped A7 on Linux (the "error -31"), so
# only 0.10.2 and older work on the 5s; newer ones are labelled "(no A7/5s)".
_ASSET = "https://assets.checkra.in/downloads/linux/cli/x86_64"


def _u(tail: str) -> str:
    return f"{_ASSET}/{tail}"


KNOWN_VERSIONS: dict[str, tuple[str, str | None]] = {
    "0.12.4": ("0.12.4 beta (no A7/5s)", _u("dac9968939ea6e6bfbdedeb41d7e2579c4711dc2c5083f91dced66ca397dc51d/checkra1n")),
    "0.12.3": ("0.12.3 beta (no A7/5s)", _u("845bd19fb857e5546ba312e768ab42e8aeab7a34470b07f60a9892e92fe8273e/checkra1n")),
    "0.12.2": ("0.12.2 beta (no A7/5s)", _u("4bf2f7e1dd201eda7d6220350db666f507d6f70e07845b772926083a8a96cd2b/checkra1n")),
    "0.12.1": ("0.12.1 beta (no A7/5s)", _u("63282886157dd08079c8e41522fdc6d58cfecda783ea8cca79ffc1116f13c355/checkra1n")),
    "0.12.0": ("0.12.0 beta (no A7/5s)", _u("5323e3cf5a2c2d12d39b4e8489bab0250c0c002e9d1c21213987f77936b3de6c/checkra1n")),
    "0.11.0": ("0.11.0 beta (no A7/5s)", _u("fa08102ba978746ff38fc4c1a0d2e8f231c2cbf79c7ef6d7b504e4683a5b7d05/checkra1n")),
    "0.10.2": ("0.10.2 beta", _u("607faa865e90e72834fce04468ae4f5119971b310ecf246128e3126db49e3d4f/checkra1n")),
    "0.10.1": ("0.10.1 beta", _u("b0edbb87a5e084caf35795dcb3b088146ad5457235940f83e007f59ca57b319c/checkra1n-x86_64")),
    "0.9.8.2": ("0.9.8.2 beta", _u("9f215d8c5a1b6cea717c927b86840b9d1f713d42a24626be3a0408a4f6ba0f4d/checkra1n")),
    "0.9.8.1": ("0.9.8.1 beta", _u("3283cab4ad44dd1ded467ed403ba5f603c6de015a7c3bdf0b1f9ef211cd06b6d/checkra1n")),
    "0.9.8": ("0.9.8 beta", _u("eda98d55f500a9de75aee4e7179231ed828ac2f5c7f99c87442936d5af4514a4/checkra1n")),
}


# --- 5s error-31 guidance --------------------------------------------------
_FIVE_S_PRODUCT_TYPES = {"iPhone6,1", "iPhone6,2"}

CHECKRA1N_5S_SOURCE = (
    "https://www.reddit.com/r/jailbreak/comments/tctfkz/"
    "help_exploit_failed_error_code_31_with_iphone_5s/"
)
CHECKRA1N_5S_GUIDANCE = (
    "[b]iPhone 5s — checkra1n error 31 (exploit failed) fix[/b]\n"
    "Tested on checkra1n 0.10.2 beta.\n\n"
    "• When checkra1n shows [bold #ff8700]Right before Trigger[/] on screen:\n"
    "  [red]wait 10-15 seconds, then unplug the cable (!), wait another\n"
    "  5-7 seconds, then plug it back in.[/red]\n\n"
    "[dim]Source: u/ytnocontent06 · r/jailbreak (5y ago)\n"
    f"{CHECKRA1N_5S_SOURCE}[/dim]"
)


def checkra1n_guidance(product_type: str | None) -> str | None:
    """checkra1n error-31 timing guidance for the 5s; None for other models."""
    if product_type in _FIVE_S_PRODUCT_TYPES:
        return CHECKRA1N_5S_GUIDANCE
    return None


class Checkra1nTool(DownloadableTool):
    id = "checkra1n"
    name = "checkra1n"
    binary_prefix = "checkra1n"
    known_versions = KNOWN_VERSIONS
    # default TUI mode (no -c): works standalone and walks a normal device into
    # DFU; -c raises USBMUX error -79 and only waits for an already-DFU device.
    launch_flags: list[str] = []

    def supports(self, snapshot: DeviceSnapshot) -> bool:
        return True  # A7–A11 support path

    def guidance(self, snapshot: DeviceSnapshot) -> str | None:
        return checkra1n_guidance(snapshot.product_type)

    def recommended_variant(self, snapshot: DeviceSnapshot) -> str | None:
        # Linux checkra1n 0.11.0+ dropped A7 support, so the 5s needs 0.10.2.
        return "0.10.2" if snapshot.product_type in _FIVE_S_PRODUCT_TYPES else None

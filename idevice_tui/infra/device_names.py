"""Display names backed by pymobiledevice3's complete device catalogue."""
from __future__ import annotations

from pymobiledevice3.irecv_devices import IRECV_DEVICES

# Keep this in infrastructure rather than duplicating a selectively maintained
# list in the domain layer. pymobiledevice3 updates this catalogue as Apple
# ships devices, and it covers iPhone, iPad, iPod, Apple TV and other supported
# product identifiers.
_DISPLAY_NAMES = {device.product_type: device.display_name for device in IRECV_DEVICES}


def device_display_name(product_type: str) -> str:
    """Return the catalogue name for a ProductType, or the identifier itself."""
    return _DISPLAY_NAMES.get(product_type, product_type)

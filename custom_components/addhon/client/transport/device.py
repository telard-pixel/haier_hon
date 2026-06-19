"""Client device descriptor for the addhOn transport.

Native rewrite of pyhOn's `connection/device.HonDevice`: the "who am I"
(app version, OS, model, mobileId) sent to the hOn cloud on every request.

The values below mirror pyhOn's TODAY, so the payload is identical and
the differential test (tests/test_transport_device.py) verifies it against the
real pyhOn class. When we have the real app flow/identity (see APK
reverse: appVersion 2.x, deviceModel "BVL", osVersion 34, real mobileId) those
values will go here, as a separate and validated step.
"""
from __future__ import annotations

from dataclasses import dataclass

# Client identity (data values that today mirror pyhOn; single point to
# update to impersonate the real app).
APP_VERSION = "2.6.5"
OS_VERSION = 999
OS = "android"
DEVICE_MODEL = "pyhOn"
MOBILE_ID = "pyhOn"


@dataclass(frozen=True)
class HonDevice:
    """Immutable client descriptor. An empty `mobile_id` falls back to the default."""

    mobile_id: str = MOBILE_ID

    def __post_init__(self) -> None:
        if not self.mobile_id:
            object.__setattr__(self, "mobile_id", MOBILE_ID)

    def payload(self, mobile: bool = False) -> dict[str, str | int]:
        """The identity dictionary sent to the cloud.

        With `mobile=True` the `os` key becomes `mobileOs` (as the app does for the
        "mobile" calls); it is the same transformation as pyhOn.
        """
        data: dict[str, str | int] = {
            "appVersion": APP_VERSION,
            "mobileId": self.mobile_id,
            "os": OS,
            "osVersion": OS_VERSION,
            "deviceModel": DEVICE_MODEL,
        }
        if mobile:
            data["mobileOs"] = data.pop("os")
        return data

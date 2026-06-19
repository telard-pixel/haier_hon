"""WC (wine cellar). Rewrite of pyhOn's `appliances/wc.py`.

No per-type logic beyond the base one (programName/available).
"""
from __future__ import annotations

from .base import ApplianceExtra


class Appliance(ApplianceExtra):
    pass

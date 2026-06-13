"""Regression tests for binding the DataUpdateCoordinator to its config entry.

Covers the fix that passes config_entry=entry to DataUpdateCoordinator. That
keyword exists only since HA 2024.11 (and omitting it hard-breaks in a later
release), so the minimum HA version is declared in hacs.json (the only valid
place; manifest.json has no min-version key and would reject one via hassfest).

A behavioral test is infeasible with the repo's stub harness (async_setup_entry
runs the executor login, first refresh and platform forwarding), so these are
source/manifest-level guards that catch accidental regressions.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "haier_hon"
INIT = COMPONENT / "__init__.py"
MANIFEST = COMPONENT / "manifest.json"
HACS = ROOT / "hacs.json"

# Minimum HA version that accepts DataUpdateCoordinator(config_entry=...).
_MIN_FOR_CONFIG_ENTRY = (2024, 11, 0)


def _version_tuple(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split("."))


class CoordinatorConfigEntryTest(unittest.TestCase):
    def test_coordinator_constructed_with_config_entry(self) -> None:
        source = INIT.read_text(encoding="utf-8")
        self.assertIn(
            "config_entry=entry",
            source,
            "DataUpdateCoordinator must receive config_entry=entry "
            "(HA 2024.11+; omitting it breaks on newer HA)",
        )

    def test_manifest_has_no_invalid_homeassistant_key(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        # "homeassistant" is NOT a valid manifest.json key (hassfest rejects it,
        # the loader never reads it). Min HA version belongs in hacs.json.
        self.assertNotIn("homeassistant", manifest)
        self.assertNotIn("min_version", manifest)

    def test_hacs_declares_min_ha_for_config_entry(self) -> None:
        self.assertTrue(HACS.is_file(), "hacs.json must declare the minimum HA version")
        hacs = json.loads(HACS.read_text(encoding="utf-8"))
        min_version = hacs.get("homeassistant")
        self.assertIsNotNone(
            min_version, "hacs.json must declare a minimum 'homeassistant' version"
        )
        self.assertGreaterEqual(
            _version_tuple(min_version),
            _MIN_FOR_CONFIG_ENTRY,
            f"hacs.json homeassistant {min_version} is below the 2024.11.0 needed "
            "to pass config_entry to DataUpdateCoordinator",
        )


if __name__ == "__main__":
    unittest.main()

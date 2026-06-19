"""Guard: the integration code is English / ASCII.

Every `.py` under custom_components/addhon (excluding translations/) must contain
no non-ASCII characters, except a small allow-list of scientific UNIT symbols that
have no clean ASCII equivalent and are device data, not language. This keeps code,
comments and log messages English-only and stops non-English text (e.g. Italian
accented letters, or decorative box-drawing) from creeping back in. All
user-facing strings belong in translations/ instead.

Tests are intentionally NOT scanned: their fixtures simulate real device data
(unit symbols like "C, accented program names, etc.) which is legitimately
non-ASCII.
"""
from __future__ import annotations

import unittest
from pathlib import Path

COMPONENT = Path(__file__).resolve().parents[1] / "custom_components" / "addhon"

# Scientific unit symbols with no clean ASCII equivalent (device data, not
# language): MICRO SIGN, SUPERSCRIPT TWO/THREE, DEGREE SIGN. Italian accented
# letters are deliberately NOT here, so they remain caught.
ALLOWED_NON_ASCII = {"µ", "²", "³", "°"}


class CodeIsEnglishTest(unittest.TestCase):
    def test_production_code_is_ascii_only(self) -> None:
        offenders: list[str] = []
        repo_root = COMPONENT.parents[1]
        for path in sorted(COMPONENT.rglob("*.py")):
            if "translations" in path.parts:
                continue
            for lineno, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), 1
            ):
                bad = sorted(
                    {c for c in line if ord(c) > 127 and c not in ALLOWED_NON_ASCII}
                )
                if bad:
                    rel = path.relative_to(repo_root)
                    codes = [hex(ord(c)) for c in bad]
                    offenders.append(f"{rel}:{lineno}: {codes}  {line.strip()[:70]}")
        self.assertEqual(
            [],
            offenders,
            "Non-ASCII (non-English) characters found in integration code. Keep "
            "code/comments/logs English and move user-facing text to translations/:\n"
            + "\n".join(offenders),
        )


if __name__ == "__main__":
    unittest.main()

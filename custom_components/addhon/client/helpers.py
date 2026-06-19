"""Numeric utilities of the native hOn client.

First "brick" ported from pyhOn with the migration loop (characterization +
differential test vs `_vendor/pyhon/helper.py`). For now no production consumer:
the callers of `str_to_float` are still internal to pyhOn (range.py/
enum.py); this function will be used when we port the parser. Kept at IDENTICAL
behavior to pyhOn (the differential test verifies it), so that when the
parser starts using it nothing changes.
"""
from __future__ import annotations


def str_to_float(value: str | float) -> float:
    """Convert an hOn value (usually a string) into a number.

    Behavior (identical to pyhOn, verified by the differential test):
    - tries `int(value)` first: "5"->5, "-16"->-16, 5->5;
    - on ValueError falls back to `float`, normalizing the decimal
      comma: "5.5"->5.5, "5,5"->5.5.

    Known QUIRK, DELIBERATELY preserved: `int()` is attempted on floats too,
    and `int(5.5)` TRUNCATES to 5 without error (it only catches ValueError, not the others).
    So a STRING must be passed to preserve the decimals ("5.5"), never a float
    (5.5 -> 5). That is the reason number.py sends the setpoints as a string.
    Also non-numeric inputs (e.g. "abc", None) propagate the original exception
    (ValueError / TypeError): they are not masked.
    """
    try:
        return int(value)
    except ValueError:
        return float(str(value).replace(",", "."))

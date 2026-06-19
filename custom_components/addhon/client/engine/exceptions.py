"""Native parser engine exceptions (Phase 4).

Ours, not imported from pyhOn (boundary rule: the native engine does not
depend on `_vendor`). Minimal: the send-path uses two of them.
"""
from __future__ import annotations


class ApiError(Exception):
    """The hOn cloud rejected/did not confirm a command."""


class NoAuthenticationException(Exception):
    """Attempt to use the api without an authenticated session."""

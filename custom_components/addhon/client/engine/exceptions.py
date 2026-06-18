"""Eccezioni del motore parser nativo (Fase 4).

Le nostre, non importate da pyhОn (regola di confine: il motore nativo non
dipende da `_vendor`). Minime: il send-path ne usa due.
"""
from __future__ import annotations


class ApiError(Exception):
    """Il cloud hОn ha rifiutato/non confermato un comando."""


class NoAuthenticationException(Exception):
    """Tentativo di usare l'api senza una sessione autenticata."""

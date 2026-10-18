"""Deterministic checks for source quotations returned by extraction."""

from __future__ import annotations

import re
import unicodedata


def normalize_quote(value: str) -> str:
    """Normalize Unicode, case, and whitespace for conservative quote matching."""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"\s+", " ", normalized).strip()


def verify_quote(quote: str, source_text: str) -> bool:
    """Return whether a normalized quote occurs verbatim in the source text."""
    normalized_quote = normalize_quote(quote)
    return bool(normalized_quote) and normalized_quote in normalize_quote(source_text)

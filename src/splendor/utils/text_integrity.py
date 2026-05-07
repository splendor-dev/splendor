"""Generated text normalization helpers."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from typing import Any

_COMMON_MOJIBAKE_REPLACEMENTS = {
    "â\x80\x94": "—",
    "â€”": "—",
    "â\x80\x93": "–",
    "â€“": "–",
    "â\x80\x98": "‘",
    "â€˜": "‘",
    "â\x80\x99": "’",
    "â€™": "’",
    "â\x80\x9c": "“",
    "â€œ": "“",
    "â\x80\x9d": "”",
    "â€�": "”",
    "â\x80¦": "…",
    "â€¦": "…",
}

_CONTROL_CHARACTER_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
_SPACES_PATTERN = re.compile(r" {2,}")


def sanitize_generated_text(value: str) -> str:
    """Preserve readable Unicode while removing controls from generated markdown/YAML."""

    text = unicodedata.normalize("NFC", value)
    for broken, replacement in _COMMON_MOJIBAKE_REPLACEMENTS.items():
        text = text.replace(broken, replacement)
    text = _CONTROL_CHARACTER_PATTERN.sub(" ", text)
    return "\n".join(_SPACES_PATTERN.sub(" ", line).rstrip() for line in text.split("\n"))


def sanitize_generated_value(value: Any) -> Any:
    if isinstance(value, str):
        return sanitize_generated_text(value)
    if isinstance(value, list):
        return [sanitize_generated_value(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_generated_value(item) for item in value]
    if isinstance(value, Mapping):
        return {
            sanitize_generated_value(key): sanitize_generated_value(item)
            for key, item in value.items()
        }
    return value

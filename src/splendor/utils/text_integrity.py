"""Generated text normalization helpers."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from typing import Any

_CONTROL_CHARACTER_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
_LATIN1_DECODED_UTF8_SPAN_PATTERN = re.compile(r"[\x80-\xff]{2,}")
_SPACES_PATTERN = re.compile(r" {2,}")


def sanitize_generated_text(value: str) -> str:
    """Preserve readable Unicode while removing controls from generated markdown/YAML."""

    text = unicodedata.normalize("NFC", value)
    if _CONTROL_CHARACTER_PATTERN.search(text):
        text = _repair_latin1_decoded_utf8_spans(text)
    text = _CONTROL_CHARACTER_PATTERN.sub(" ", text)
    return "\n".join(_SPACES_PATTERN.sub(" ", line).rstrip() for line in text.split("\n"))


def _repair_latin1_decoded_utf8_spans(value: str) -> str:
    def repair(match: re.Match[str]) -> str:
        span = match.group(0)
        if not _CONTROL_CHARACTER_PATTERN.search(span):
            return span
        try:
            return span.encode("latin-1").decode("utf-8")
        except UnicodeError:
            return span

    return _LATIN1_DECODED_UTF8_SPAN_PATTERN.sub(repair, value)


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

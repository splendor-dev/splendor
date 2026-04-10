"""Stable identifier helpers."""

from __future__ import annotations


def stable_source_id(checksum: str) -> str:
    return f"src-{checksum[:16]}"

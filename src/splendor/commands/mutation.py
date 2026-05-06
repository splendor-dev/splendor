"""Small helpers for agent-safe CLI mutation contracts."""

from __future__ import annotations

from collections.abc import Iterable


def mutation_record(
    *,
    action: str,
    path: str,
    kind: str,
    source_id: str | None = None,
) -> dict[str, str]:
    payload = {
        "action": action,
        "path": path,
        "kind": kind,
    }
    if source_id is not None:
        payload["source_id"] = source_id
    return payload


def mutation_contract(
    *,
    mode: str,
    planned: Iterable[dict[str, str]] = (),
    written: Iterable[dict[str, str]] = (),
) -> dict[str, object]:
    planned_items = list(planned)
    written_items = list(written)
    return {
        "mode": mode,
        "mutates": bool(written_items),
        "planned": planned_items,
        "written": written_items,
    }

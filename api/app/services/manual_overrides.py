from __future__ import annotations

import json
from typing import Protocol


class OverrideCarrier(Protocol):
    config_overrides_json: str | None


def override_fields(row: OverrideCarrier) -> set[str]:
    if not row.config_overrides_json:
        return set()
    try:
        parsed = json.loads(row.config_overrides_json)
    except (TypeError, ValueError, json.JSONDecodeError):
        return set()
    if not isinstance(parsed, list):
        return set()
    return {item for item in parsed if isinstance(item, str) and item}


def mark_overrides(row: OverrideCarrier, fields: set[str]) -> None:
    if not fields:
        return
    merged = override_fields(row).union(fields)
    row.config_overrides_json = json.dumps(sorted(merged), separators=(",", ":"))


def is_overridden(row: OverrideCarrier, field: str) -> bool:
    return field in override_fields(row)


def set_unless_overridden(row: OverrideCarrier, field: str, value: object) -> None:
    if is_overridden(row, field):
        return
    setattr(row, field, value)


def set_optional_unless_overridden(row: OverrideCarrier, field: str, value: object | None) -> None:
    if value is None or is_overridden(row, field):
        return
    setattr(row, field, value)

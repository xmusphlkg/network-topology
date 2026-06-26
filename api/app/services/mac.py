from __future__ import annotations

import re


MAC_PATTERN = re.compile(
    r"(?<![0-9A-Fa-f])((?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}|[0-9A-Fa-f]{4}\.[0-9A-Fa-f]{4}\.[0-9A-Fa-f]{4})(?![0-9A-Fa-f])"
)


def normalize_mac_address(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"null", "none", "n/a", "na", "unknown"}:
        return None
    match = MAC_PATTERN.search(text)
    if not match:
        return None
    compact = re.sub(r"[^0-9A-Fa-f]", "", match.group(1)).lower()
    if len(compact) != 12:
        return None
    return ":".join(compact[index : index + 2] for index in range(0, 12, 2))


def extract_mac_address(value: str) -> str | None:
    return normalize_mac_address(value)

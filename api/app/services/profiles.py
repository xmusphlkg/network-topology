from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ProfilePort:
    name: str
    media: str
    speed_mbps: float
    role: str
    row: int
    order: int


@dataclass(frozen=True)
class SwitchProfile:
    key: str
    models: tuple[str, ...]
    ports: tuple[ProfilePort, ...]


def s6220_ports() -> tuple[ProfilePort, ...]:
    ports: list[ProfilePort] = []
    for index in range(1, 49):
        ports.append(ProfilePort(name=f"XGE0/{index}", media="fiber", speed_mbps=10000, role="access", row=(index - 1) % 2, order=index))
    for offset, index in enumerate(range(49, 55), start=1):
        ports.append(ProfilePort(name=f"QXGE0/{index}", media="fiber", speed_mbps=40000, role="uplink", row=2, order=100 + offset))
    return tuple(ports)


def s5750_ports() -> tuple[ProfilePort, ...]:
    ports: list[ProfilePort] = []
    for index in range(1, 49):
        ports.append(ProfilePort(name=f"GE0/{index}", media="copper", speed_mbps=1000, role="access", row=(index - 1) % 2, order=index))
    for offset, index in enumerate(range(49, 53), start=1):
        ports.append(ProfilePort(name=f"XGE0/{index}", media="fiber", speed_mbps=10000, role="uplink", row=2, order=100 + offset))
    return tuple(ports)


PROFILES = (
    SwitchProfile(
        key="S6220-48XS6QXS-H",
        models=("S6220-48XS6QXS-H", "RG-S6220-48XS6QXS-H", "S6220-H"),
        ports=s6220_ports(),
    ),
    SwitchProfile(
        key="S5750-48GT4XS-HP-H",
        models=("S5750-48GT4XS-HP-H", "RG-S5750-48GT4XS-HP-H", "S5750-48T4XS-HP-H", "S5750-H"),
        ports=s5750_ports(),
    ),
)


def profile_for_model(model: str | None) -> SwitchProfile | None:
    if not model:
        return None
    normalized = normalize_model_text(model)
    for profile in PROFILES:
        if any(normalize_model_text(candidate) in normalized for candidate in profile.models):
            return profile
    return None


def normalize_model_text(value: str) -> str:
    return re.sub(r"[^A-Z0-9-]", "", value.upper())


def port_sort_key(name: str) -> tuple[int, int, str]:
    upper = name.upper()
    prefix_rank = 9
    if upper.startswith(("GE", "GI")):
        prefix_rank = 1
    elif upper.startswith(("XGE", "TE")):
        prefix_rank = 2
    elif upper.startswith(("QXGE", "FORTY", "HUNDRED")):
        prefix_rank = 3
    match = re.search(r"(\d+)(?!.*\d)", upper)
    return (prefix_rank, int(match.group(1)) if match else 9999, upper)


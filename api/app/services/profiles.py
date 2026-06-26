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


def _generate_profile_ports(
    start: int,
    end: int,
    media: str,
    speed_mbps: float,
    role: str,
    prefix: str,
    row: int,
    order_start: int,
) -> list[ProfilePort]:
    ports: list[ProfilePort] = []
    for index in range(start, end + 1):
        ports.append(
            ProfilePort(
                name=f"{prefix}{index}",
                media=media,
                speed_mbps=speed_mbps,
                role=role,
                row=row,
                order=order_start + index - start,
            )
        )
    return ports


def _generate_alternating_profile_ports(
    start: int,
    end: int,
    media: str,
    speed_mbps: float,
    role: str,
    prefix: str,
    order_start: int,
) -> list[ProfilePort]:
    ports: list[ProfilePort] = []
    for index in range(start, end + 1):
        ports.append(
            ProfilePort(
                name=f"{prefix}{index}",
                media=media,
                speed_mbps=speed_mbps,
                role=role,
                row=(index - start) % 2,
                order=order_start + index - start,
            )
        )
    return ports


def _generate_profile_ports_block(
    start: int,
    end: int,
    media: str,
    speed_mbps: float,
    role: str,
    name_pattern: str,
    row: int,
    order_start: int,
) -> list[ProfilePort]:
    ports: list[ProfilePort] = []
    for index in range(start, end + 1):
        ports.append(
            ProfilePort(
                name=f"{name_pattern}{index}",
                media=media,
                speed_mbps=speed_mbps,
                role=role,
                row=row,
                order=order_start + index - start,
            )
        )
    return ports


def s5720_24_ports() -> tuple[ProfilePort, ...]:
    # 24x1G + 4x10G，常见汇聚模板
    ports: list[ProfilePort] = []
    ports.extend(_generate_profile_ports(1, 24, "copper", 1000, "access", "GE0/", row=0, order_start=1))
    ports.extend(_generate_profile_ports(25, 36, "copper", 1000, "access", "GE0/", row=1, order_start=25))
    ports.extend(_generate_profile_ports(1, 4, "fiber", 10000, "uplink", "XGE0/", row=2, order_start=200))
    return tuple(ports)


def s6850_ports() -> tuple[ProfilePort, ...]:
    # 52x1G + 4x25G，常见机房接入模板
    ports: list[ProfilePort] = []
    ports.extend(_generate_profile_ports(1, 52, "copper", 1000, "access", "GE0/", row=0, order_start=1))
    ports.extend(_generate_profile_ports(53, 56, "fiber", 25000, "uplink", "QXGE0/", row=2, order_start=200))
    return tuple(ports)


def s5720_52_ports() -> tuple[ProfilePort, ...]:
    ports: list[ProfilePort] = []
    ports.extend(_generate_alternating_profile_ports(1, 52, "copper", 1000, "access", "GE0/", 100))
    ports.extend(_generate_profile_ports(53, 56, "fiber", 10000, "uplink", "XGE0/", row=2, order_start=200))
    return tuple(ports)


def s5820_ports() -> tuple[ProfilePort, ...]:
    # 24x1G + 2x2.5G + 2x10G，适配常见小型汇聚
    ports: list[ProfilePort] = []
    ports.extend(_generate_profile_ports(1, 24, "copper", 1000, "access", "GE0/", row=0, order_start=1))
    ports.extend(_generate_profile_ports(25, 28, "copper", 2500, "access", "GE0/", row=1, order_start=200))
    ports.extend(_generate_profile_ports(29, 32, "fiber", 10000, "uplink", "XGE0/", row=2, order_start=240))
    return tuple(ports)


def s5720_28_ports() -> tuple[ProfilePort, ...]:
    # 24x1G + 4x2.5G，聚合区常见小型接入
    ports: list[ProfilePort] = []
    ports.extend(_generate_profile_ports(1, 24, "copper", 1000, "access", "GE0/", row=0, order_start=1))
    ports.extend(_generate_profile_ports(25, 28, "copper", 2500, "uplink", "GE0/", row=1, order_start=200))
    return tuple(ports)


def server_2x25g_ports() -> tuple[ProfilePort, ...]:
    # 通常服务器网口：1~2 路高速上联 + 1~2 路管理网口
    ports: list[ProfilePort] = []
    ports.extend(_generate_profile_ports_block(1, 2, "copper", 25000, "uplink", "eth", row=0, order_start=1))
    ports.extend(_generate_profile_ports_block(3, 4, "copper", 1000, "management", "eth", row=1, order_start=10))
    return tuple(ports)


def server_4x10g_ports() -> tuple[ProfilePort, ...]:
    # 一般服务器的 4 口 10G
    return tuple(_generate_profile_ports_block(0, 3, "fiber", 10000, "access", "p", row=0, order_start=1))


def server_6x25g_ports() -> tuple[ProfilePort, ...]:
    # 部分高配服务器常见 6 口高带宽网卡分组
    return tuple(_generate_profile_ports_block(1, 6, "copper", 25000, "uplink", "ens", row=0, order_start=1))


def normalize_profile_key(value: str) -> str:
    return re.sub(r"[^a-z0-9-]", "", value.lower())


def is_switch_profile(profile_key: str) -> bool:
    normalized = normalize_profile_key(profile_key)
    if not normalized:
        return False
    return normalized.startswith("s") and not normalized.startswith("server")


def get_profile(profile_key: str) -> SwitchProfile | None:
    normalized = normalize_profile_key(profile_key)
    for profile in PROFILES:
        if normalize_profile_key(profile.key) == normalized:
            return profile
    return None


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
    SwitchProfile(
        key="S5720-24GT4S-HP-H",
        models=("S5720-24GT4S-HP-H", "S5720-24GT4S", "S5720-24", "RG-S5720-24GT4S-HP-H"),
        ports=s5720_24_ports(),
    ),
    SwitchProfile(
        key="S6850-52G4QX",
        models=("S6850-52G4QX", "S6850-52X6QX", "S6850-52G4Q"),
        ports=s6850_ports(),
    ),
    SwitchProfile(
        key="S5720-52GT4S",
        models=("S5720-52GT4S", "S5720-52GT4S-H", "RG-S5720-52GT4S", "S5720-52GT4"),
        ports=s5720_52_ports(),
    ),
    SwitchProfile(
        key="S5820-32GT4S",
        models=("S5820-32GT4S", "RG-S5820-32GT4S", "S5820-32S4S", "S5820-32F4S"),
        ports=s5820_ports(),
    ),
    SwitchProfile(
        key="S5720-28GT2S",
        models=("S5720-28GT2S", "S5720-28GT2S-H", "RG-S5720-28GT2S", "S5720-28"),
        ports=s5720_28_ports(),
    ),
    SwitchProfile(
        key="Server-2x25G",
        models=("SERVER25G", "GENERIC-SERVER-2X25G", "RHEL", "ESXI"),
        ports=server_2x25g_ports(),
    ),
    SwitchProfile(
        key="Server-4x10G",
        models=("SERVER-4X10G", "GENERIC-SERVER-4X10G", "DL380", "DL360"),
        ports=server_4x10g_ports(),
    ),
    SwitchProfile(
        key="Server-6x25G",
        models=("SERVER-6X25G", "GENERIC-SERVER-6X25G", "R740", "R750"),
        ports=server_6x25g_ports(),
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

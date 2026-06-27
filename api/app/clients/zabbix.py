from __future__ import annotations

import asyncio
import itertools
import time
from dataclasses import dataclass
from typing import Any

import httpx

from ..config import Settings


class ZabbixError(RuntimeError):
    pass


JsonRpcParams = dict[str, Any] | list[Any]


@dataclass
class ZabbixClient:
    settings: Settings
    client: httpx.AsyncClient

    def __post_init__(self) -> None:
        self._sem = asyncio.Semaphore(self.settings.zabbix_concurrency)
        self._auth_token: str | None = self.settings.zabbix_token
        self._token_from_login = False
        self._request_ids = itertools.count(int(time.time() * 1000))

    async def call(self, method: str, params: JsonRpcParams | None = None, *, auth: bool = True) -> Any:
        if auth and not self._auth_token:
            await self._login_if_needed()
        auth_mode = self.settings.zabbix_auth_mode
        try:
            return await self._call_once(method, params, auth=auth, legacy_auth=auth_mode == "auth")
        except ZabbixError as exc:
            if auth and auth_mode == "auto" and self._should_retry_with_legacy_auth(exc):
                return await self._call_once(method, params, auth=auth, legacy_auth=True)
            raise

    async def _call_once(
        self,
        method: str,
        params: JsonRpcParams | None = None,
        *,
        auth: bool,
        legacy_auth: bool,
    ) -> Any:
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params if params is not None else {},
            "id": next(self._request_ids),
        }
        headers = {"Content-Type": "application/json-rpc"}
        if auth:
            if not self._auth_token:
                raise ZabbixError("Zabbix token is not configured")
            if legacy_auth:
                payload["auth"] = self._auth_token
            else:
                headers["Authorization"] = f"Bearer {self._auth_token}"
        async with self._sem:
            response = await self.client.post(
                self.settings.zabbix_url,
                json=payload,
                headers=headers,
                timeout=self.settings.zabbix_timeout_sec,
            )
            response.raise_for_status()
            try:
                body = response.json()
            except ValueError as exc:
                raise ZabbixError("Zabbix API returned a non-JSON response") from exc
            if "error" in body:
                message = body["error"].get("data") or body["error"].get("message") or body["error"]
                raise ZabbixError(str(message))
            return body.get("result")

    async def _login_if_needed(self) -> None:
        if self._auth_token:
            return
        if not self.settings.zabbix_user or not self.settings.zabbix_password:
            raise ZabbixError("ZABBIX_TOKEN or ZABBIX_USER/ZABBIX_PASSWORD must be configured")
        try:
            result = await self.call(
                "user.login",
                {"username": self.settings.zabbix_user, "password": self.settings.zabbix_password},
                auth=False,
            )
        except ZabbixError as exc:
            if not self._should_retry_login_with_legacy_user(exc):
                raise
            result = await self.call(
                "user.login",
                {"user": self.settings.zabbix_user, "password": self.settings.zabbix_password},
                auth=False,
            )
        if not isinstance(result, str):
            raise ZabbixError("Zabbix login did not return a token")
        self._auth_token = result
        self._token_from_login = True

    async def close(self) -> None:
        if not self._auth_token or not self._token_from_login or not self.settings.zabbix_logout_on_shutdown:
            return
        try:
            await self.call("user.logout", [], auth=True)
        finally:
            self._auth_token = None
            self._token_from_login = False

    async def api_version(self) -> str | None:
        result = await self.call("apiinfo.version", auth=False)
        return str(result) if result is not None else None

    async def hosts(self) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "output": ["hostid", "host", "name", "status"],
            "monitored_hosts": True,
            "selectHostGroups": ["groupid", "name"],
            "selectInterfaces": ["interfaceid", "ip", "dns", "type", "main", "available", "error"],
            "selectInventory": ["type", "os", "location", "model", "serialno_a", "macaddress_a"],
            "selectTags": ["tag", "value"],
            "sortfield": ["name"],
        }
        if self.settings.zabbix_host_limit > 0:
            params["limit"] = self.settings.zabbix_host_limit
        try:
            hosts = await self.call("host.get", params)
        except ZabbixError as exc:
            if not self._should_retry_hosts_with_legacy_groups(exc):
                raise
            params["selectGroups"] = params.pop("selectHostGroups")
            hosts = await self.call("host.get", params)
        if not isinstance(hosts, list):
            raise ZabbixError("Zabbix host.get did not return a host list")
        return [normalize_host_groups(host) for host in hosts]

    async def items_for_hosts(self, hostids: list[str]) -> list[dict[str, Any]]:
        if not hostids:
            return []
        items = await self.call(
            "item.get",
            {
                "hostids": hostids,
                "output": [
                    "itemid",
                    "hostid",
                    "name",
                    "key_",
                    "lastvalue",
                    "lastclock",
                    "units",
                    "value_type",
                    "status",
                    "state",
                ],
                "filter": {"status": 0},
            },
        )
        if not isinstance(items, list):
            raise ZabbixError("Zabbix item.get did not return an item list")
        return items

    async def history(
        self,
        itemids: list[str],
        *,
        history_type: int,
        time_from: int,
        time_till: int,
        limit: int = 2400,
    ) -> list[dict[str, Any]]:
        if not itemids:
            return []
        return await self.call(
            "history.get",
            {
                "output": "extend",
                "history": history_type,
                "itemids": itemids,
                "time_from": time_from,
                "time_till": time_till,
                "sortfield": "clock",
                "sortorder": "ASC",
                "limit": limit,
            },
        )

    async def trends(
        self,
        itemids: list[str],
        *,
        time_from: int,
        time_till: int,
        limit: int = 2400,
    ) -> list[dict[str, Any]]:
        if not itemids:
            return []
        return await self.call(
            "trend.get",
            {
                "output": ["itemid", "clock", "value_avg", "value_min", "value_max"],
                "itemids": itemids,
                "time_from": time_from,
                "time_till": time_till,
                "sortfield": "clock",
                "sortorder": "ASC",
                "limit": limit,
            },
        )

    @staticmethod
    def _should_retry_with_legacy_auth(exc: ZabbixError) -> bool:
        text = str(exc).lower()
        return any(token in text for token in ["not authorised", "not authorized", "session terminated", "no permissions"])

    @staticmethod
    def _should_retry_login_with_legacy_user(exc: ZabbixError) -> bool:
        text = str(exc).lower()
        return "invalid parameter" in text and "username" in text

    @staticmethod
    def _should_retry_hosts_with_legacy_groups(exc: ZabbixError) -> bool:
        text = str(exc).lower()
        return "invalid parameter" in text and "selecthostgroups" in text


def normalize_host_groups(host: dict[str, Any]) -> dict[str, Any]:
    groups = host.get("groups") or host.get("hostgroups") or []
    if isinstance(groups, dict):
        groups = list(groups.values())
    if not isinstance(groups, list):
        groups = []
    host["groups"] = groups
    return host

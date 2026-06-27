from __future__ import annotations

import json

import httpx

from app.clients.zabbix import ZabbixClient
from app.config import Settings


async def test_zabbix_client_uses_current_login_and_bearer_auth():
    seen_methods: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        seen_methods.append(payload["method"])
        if payload["method"] == "user.login":
            assert payload["params"] == {"username": "Admin", "password": "zabbix"}
            assert "authorization" not in request.headers
            return httpx.Response(200, json={"jsonrpc": "2.0", "result": "login-token", "id": payload["id"]})
        assert payload["method"] == "host.get"
        assert request.headers["authorization"] == "Bearer login-token"
        assert payload["params"]["selectHostGroups"] == ["groupid", "name"]
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "result": [{"hostid": "10084", "host": "sw-1", "hostgroups": [{"groupid": "1", "name": "switch"}]}],
                "id": payload["id"],
            },
        )

    settings = Settings(
        environment="test",
        zabbix_url="http://zabbix.example/api_jsonrpc.php",
        zabbix_token=None,
        zabbix_user="Admin",
        zabbix_password="zabbix",
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = ZabbixClient(settings=settings, client=http)
        hosts = await client.hosts()

    assert seen_methods == ["user.login", "host.get"]
    assert hosts[0]["groups"] == [{"groupid": "1", "name": "switch"}]


async def test_zabbix_client_logs_out_session_tokens_on_close():
    seen_payloads: list[dict] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        seen_payloads.append(payload)
        if payload["method"] == "user.login":
            return httpx.Response(200, json={"jsonrpc": "2.0", "result": "login-token", "id": payload["id"]})
        if payload["method"] == "host.get":
            assert request.headers["authorization"] == "Bearer login-token"
            return httpx.Response(200, json={"jsonrpc": "2.0", "result": [], "id": payload["id"]})
        assert payload["method"] == "user.logout"
        assert payload["params"] == []
        assert request.headers["authorization"] == "Bearer login-token"
        return httpx.Response(200, json={"jsonrpc": "2.0", "result": True, "id": payload["id"]})

    settings = Settings(
        environment="test",
        zabbix_url="http://zabbix.example/api_jsonrpc.php",
        zabbix_token=None,
        zabbix_user="Admin",
        zabbix_password="zabbix",
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = ZabbixClient(settings=settings, client=http)
        await client.call("host.get", {})
        await client.close()

    assert [payload["method"] for payload in seen_payloads] == ["user.login", "host.get", "user.logout"]


async def test_zabbix_client_auto_auth_mode_retries_legacy_auth_payload():
    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        payload = json.loads(request.content)
        assert payload["method"] == "host.get"
        if attempts == 1:
            assert request.headers["authorization"] == "Bearer api-token"
            assert "auth" not in payload
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "error": {"code": -32602, "message": "Invalid params.", "data": "Not authorized."},
                    "id": payload["id"],
                },
            )
        assert "authorization" not in request.headers
        assert payload["auth"] == "api-token"
        return httpx.Response(200, json={"jsonrpc": "2.0", "result": "ok", "id": payload["id"]})

    settings = Settings(
        environment="test",
        zabbix_url="http://zabbix.example/api_jsonrpc.php",
        zabbix_token="api-token",
        zabbix_auth_mode="auto",
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = ZabbixClient(settings=settings, client=http)
        result = await client.call("host.get", {})

    assert result == "ok"
    assert attempts == 2


async def test_zabbix_client_retries_legacy_host_group_select():
    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        payload = json.loads(request.content)
        assert payload["method"] == "host.get"
        if attempts == 1:
            assert "selectHostGroups" in payload["params"]
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32602,
                        "message": "Invalid params.",
                        "data": 'Invalid parameter "/selectHostGroups": unexpected parameter.',
                    },
                    "id": payload["id"],
                },
            )
        assert "selectGroups" in payload["params"]
        assert "selectHostGroups" not in payload["params"]
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "result": [{"hostid": "10084", "host": "sw-1", "groups": [{"groupid": "1", "name": "switch"}]}],
                "id": payload["id"],
            },
        )

    settings = Settings(
        environment="test",
        zabbix_url="http://zabbix.example/api_jsonrpc.php",
        zabbix_token="api-token",
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = ZabbixClient(settings=settings, client=http)
        hosts = await client.hosts()

    assert hosts[0]["groups"] == [{"groupid": "1", "name": "switch"}]
    assert attempts == 2

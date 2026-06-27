from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta

from app import main as main_module
from app import routes as api_routes
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app import database
from app.db_models import Base, ZabbixSyncRun
from app.main import app
from app.services.mapper import DeviceSnapshot, PortSnapshot
from app.config import Settings


def fake_snapshot(hostid: str, port_name: str = "eth0") -> DeviceSnapshot:
    return DeviceSnapshot(
        zabbix_hostid=hostid,
        role="server",
        display_name=f"host-{hostid}",
        model="PowerEdge",
        ports=[PortSnapshot(identity=f"ifindex:1", name=port_name, if_index=1, oper_status="up")],
    )


async def test_lifespan_auto_sync_uses_initialized_sessionmaker(monkeypatch):
    synced = asyncio.Event()
    settings = Settings(
        environment="test",
        database_url="sqlite+aiosqlite:///:memory:",
        auto_create_tables=True,
        auto_sync_enabled=True,
        sync_interval_sec=3600,
        zabbix_token="token",
    )

    async def fake_run(session, _zabbix, _settings):
        await session.execute(select(ZabbixSyncRun.id).limit(1))
        synced.set()

    monkeypatch.setattr(main_module, "get_settings", lambda: settings)
    monkeypatch.setattr(main_module, "run_zabbix_sync", fake_run)

    async with main_module.lifespan(main_module.app):
        await asyncio.wait_for(synced.wait(), timeout=1)


async def test_device_and_cable_api_roundtrip():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    database.engine = engine
    database.SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    app.state.zabbix = object()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post(
            "/api/devices",
            json={"displayName": "manual-server", "role": "server", "ports": [{"name": "ens1f0"}]},
        )
        assert created.status_code == 200
        assert created.json()["displayName"] == "manual-server"
        assert "display_name" not in created.json()
        device_id = created.json()["id"]
        ports = await client.get(f"/api/devices/{device_id}/ports")
        assert ports.status_code == 200
        assert ports.json()[0]["deviceId"] == device_id
        assert "device_id" not in ports.json()[0]
        first_port = ports.json()[0]["id"]

        created2 = await client.post(
            "/api/devices",
            json={"displayName": "manual-switch", "role": "switch", "ports": [{"name": "XGE0/1"}]},
        )
        second_device_id = created2.json()["id"]
        ports2 = await client.get(f"/api/devices/{second_device_id}/ports")
        second_port = ports2.json()[0]["id"]

        link = await client.post(
            "/api/cable-links",
            json={"endpointAPortId": first_port, "endpointBPortId": second_port, "label": "L-001", "vlanId": 30},
        )
        assert link.status_code == 200
        assert link.json()["vlanId"] == 30
        topology = await client.get("/api/topology")
        assert topology.status_code == 200
        assert len(topology.json()["edges"]) == 1
        assert topology.json()["edges"][0]["data"]["vlan"] == 30
        assert topology.json()["edges"][0]["label"] == "L-001 · VLAN 30"

        deleted_port = await client.delete(f"/api/ports/{second_port}")
        assert deleted_port.status_code == 200
        topology_after_port_delete = await client.get("/api/topology")
        assert topology_after_port_delete.status_code == 200
        assert topology_after_port_delete.json()["edges"] == []

        deleted_device = await client.delete(f"/api/devices/{device_id}")
        assert deleted_device.status_code == 200
        topology_after_device_delete = await client.get("/api/topology")
        assert topology_after_device_delete.status_code == 200
        assert "manual-server" not in {device["displayName"] for device in topology_after_device_delete.json()["devices"]}

    await engine.dispose()


async def test_manual_port_reactivates_device_and_keeps_vlan():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    database.engine = engine
    database.SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    app.state.zabbix = object()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post("/api/devices", json={"displayName": "idrac-host", "role": "server"})
        assert created.status_code == 200
        device_id = created.json()["id"]

        stale = await client.patch(f"/api/devices/{device_id}", json={"stale": True, "health": "stale"})
        assert stale.status_code == 200

        port = await client.post(
            f"/api/devices/{device_id}/ports",
            json={"name": "iDRAC", "alias": "BMC 管理口", "speedMbps": 1000, "media": "copper", "portRole": "management", "vlanSummary": "PVID 99"},
        )
        assert port.status_code == 200
        body = port.json()
        assert body["source"] == "manual"
        assert body["vlanSummary"] == "PVID 99"

        topology = await client.get("/api/topology")
        assert topology.status_code == 200
        assert [device["displayName"] for device in topology.json()["devices"]] == ["idrac-host"]
        assert topology.json()["ports"][0]["name"] == "iDRAC"

        duplicated = await client.post(f"/api/devices/{device_id}/ports", json={"name": "iDRAC"})
        assert duplicated.status_code == 409

    await engine.dispose()


async def test_sync_runs_endpoint_returns_recent_history():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    database.engine = engine
    database.SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    app.state.zabbix = object()

    now = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
    async with database.SessionLocal() as db:
        db.add_all(
            [
                ZabbixSyncRun(
                    status="success",
                    started_at=now,
                    finished_at=now + timedelta(seconds=2),
                    duration_ms=2000,
                    devices_seen=5,
                    devices_upserted=4,
                    ports_upserted=18,
                    stale_devices=1,
                ),
                ZabbixSyncRun(
                    status="failed",
                    started_at=now + timedelta(minutes=10),
                    finished_at=now + timedelta(minutes=10, seconds=1),
                    duration_ms=1000,
                    devices_seen=6,
                    devices_upserted=2,
                    ports_upserted=8,
                    stale_devices=0,
                    error_message="boom",
                ),
            ],
        )
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/sync/runs?limit=2")
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 2
        assert body[0]["status"] == "failed"
        assert body[0]["errorMessage"] == "boom"
        assert body[1]["status"] == "success"
        assert body[0]["startedAt"] > body[1]["startedAt"]

    await engine.dispose()


async def test_topology_cable_links_are_scoped_to_selected_topology():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    database.engine = engine
    database.SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    app.state.zabbix = object()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        topology_a = await client.post("/api/topologies", json={"name": "A"})
        topology_b = await client.post("/api/topologies", json={"name": "B"})
        topology_a_id = topology_a.json()["id"]
        topology_b_id = topology_b.json()["id"]

        switch_a = await client.post(
            "/api/devices",
            json={
                "displayName": "switch-a",
                "role": "switch",
                "topologyId": topology_a_id,
                "ports": [{"name": "XGE0/1"}],
            },
        )
        server_a = await client.post(
            "/api/devices",
            json={
                "displayName": "server-a",
                "role": "server",
                "topologyId": topology_a_id,
                "ports": [{"name": "ens1f0"}],
            },
        )
        switch_b = await client.post(
            "/api/devices",
            json={
                "displayName": "switch-b",
                "role": "switch",
                "topologyId": topology_b_id,
                "ports": [{"name": "XGE0/1"}],
            },
        )

        switch_a_port = (await client.get(f"/api/devices/{switch_a.json()['id']}/ports")).json()[0]["id"]
        server_a_port = (await client.get(f"/api/devices/{server_a.json()['id']}/ports")).json()[0]["id"]
        await client.post(
            "/api/cable-links",
            json={"endpointAPortId": switch_a_port, "endpointBPortId": server_a_port, "label": "A-link"},
        )

        topology_a_graph = await client.get(f"/api/topology?topologyId={topology_a_id}")
        topology_b_graph = await client.get(f"/api/topology?topologyId={topology_b_id}")

        assert topology_a_graph.status_code == 200
        assert topology_b_graph.status_code == 200
        assert [device["displayName"] for device in topology_b_graph.json()["devices"]] == [switch_b.json()["displayName"]]
        assert len(topology_a_graph.json()["edges"]) == 1
        assert len(topology_a_graph.json()["cableLinks"]) == 1
        assert topology_b_graph.json()["edges"] == []
        assert topology_b_graph.json()["cableLinks"] == []

    await engine.dispose()


async def test_topology_json_export_and_import_roundtrip():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    database.engine = engine
    database.SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    app.state.zabbix = object()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        source_topology = (await client.post("/api/topologies", json={"name": "json-source"})).json()
        target_topology = (await client.post("/api/topologies", json={"name": "json-target"})).json()

        switch = await client.post(
            "/api/devices",
            json={
                "displayName": "json-switch",
                "role": "switch",
                "topologyId": source_topology["id"],
                "ports": [{"name": "XGE0/1"}],
            },
        )
        server = await client.post(
            "/api/devices",
            json={
                "displayName": "json-server",
                "role": "server",
                "topologyId": source_topology["id"],
                "ports": [{"name": "ens1f0"}, {"name": "ens1f1"}],
            },
        )
        switch_port = (await client.get(f"/api/devices/{switch.json()['id']}/ports")).json()[0]["id"]
        server_port = (await client.get(f"/api/devices/{server.json()['id']}/ports")).json()[0]["id"]
        await client.post(
            "/api/cable-links",
            json={"endpointAPortId": switch_port, "endpointBPortId": server_port, "label": "json-link"},
        )

        exported = await client.get(f"/api/topologies/{source_topology['id']}/json-export")
        assert exported.status_code == 200
        dry_run = await client.post(f"/api/topologies/{target_topology['id']}/json-import/dry-run", json=exported.json())
        assert dry_run.status_code == 200
        assert dry_run.json()["devices"] == 2
        assert dry_run.json()["ports"] == 3
        assert dry_run.json()["cableLinks"] == 1
        assert dry_run.json()["existingDevices"] == 2
        assert dry_run.json()["newDevices"] == 0

        imported = await client.post(f"/api/topologies/{target_topology['id']}/json-import", json=exported.json())
        assert imported.status_code == 200

        imported_graph = await client.get(f"/api/topology?topologyId={target_topology['id']}")
        assert imported_graph.status_code == 200
        body = imported_graph.json()
        assert {device["displayName"] for device in body["devices"]} == {"json-switch", "json-server"}
        assert len(body["cableLinks"]) == 1
        assert body["cableLinks"][0]["label"] == "json-link"

    await engine.dispose()


async def test_manual_port_names_are_validated_and_identity_tracks_rename():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    database.engine = engine
    database.SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    app.state.zabbix = object()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        duplicate_payload = {
            "displayName": "dup-server",
            "role": "server",
            "ports": [{"name": "ens1f0"}, {"name": " ENS1F0 "}],
        }
        duplicate = await client.post("/api/devices", json=duplicate_payload)
        assert duplicate.status_code == 409

        created = await client.post(
            "/api/devices",
            json={"displayName": "rename-server", "role": "server", "ports": [{"name": "ens1f0"}, {"name": "ens1f1"}]},
        )
        assert created.status_code == 200
        device_id = created.json()["id"]
        ports = (await client.get(f"/api/devices/{device_id}/ports")).json()
        first_port = next(port for port in ports if port["name"] == "ens1f0")
        second_port = next(port for port in ports if port["name"] == "ens1f1")

        conflict = await client.patch(f"/api/ports/{second_port['id']}", json={"name": "ens1f0"})
        assert conflict.status_code == 409

        renamed = await client.patch(f"/api/ports/{second_port['id']}", json={"name": " ens1f2 "})
        assert renamed.status_code == 200
        assert renamed.json()["name"] == "ens1f2"
        assert renamed.json()["identity"] == "manual:ens1f2"

        blank = await client.patch(f"/api/ports/{first_port['id']}", json={"name": "  "})
        assert blank.status_code == 400

        recreated_old_name = await client.post(f"/api/devices/{device_id}/ports", json={"name": "ens1f1"})
        assert recreated_old_name.status_code == 200

    await engine.dispose()


async def test_topology_names_are_validated_before_database_constraints():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    database.engine = engine
    database.SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    app.state.zabbix = object()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post("/api/topologies", json={"name": "机柜 A"})
        assert created.status_code == 200

        duplicate = await client.post("/api/topologies", json={"name": "机柜 A"})
        assert duplicate.status_code == 409

        blank = await client.post("/api/topologies", json={"name": "  "})
        assert blank.status_code == 400

        second = await client.post("/api/topologies", json={"name": "机柜 B"})
        assert second.status_code == 200
        rename_conflict = await client.patch(f"/api/topologies/{second.json()['id']}", json={"name": "机柜 A"})
        assert rename_conflict.status_code == 409

    await engine.dispose()


async def test_ports_query_supports_topology_scope_and_filters():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    database.engine = engine
    database.SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    app.state.zabbix = object()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        topology_a = (await client.post("/api/topologies", json={"name": "scope-a"})).json()
        topology_b = (await client.post("/api/topologies", json={"name": "scope-b"})).json()

        switch_a = (
            await client.post(
                "/api/devices",
                json={
                    "displayName": "switch-a",
                    "role": "switch",
                    "topologyId": topology_a["id"],
                    "ports": [{"name": "ge-1"}, {"name": "ge-2"}, {"name": "ge-3"}],
                },
            )
        ).json()
        server_a = (
            await client.post(
                "/api/devices",
                json={
                    "displayName": "server-a",
                    "role": "server",
                    "topologyId": topology_a["id"],
                    "ports": [{"name": "eth0"}],
                },
            )
        ).json()
        _unused = (await client.post(
            "/api/devices",
            json={
                "displayName": "switch-b",
                "role": "switch",
                "topologyId": topology_b["id"],
                "ports": [{"name": "ge-1"}],
            },
        )).json()

        switch_a_ports = await client.get(f"/api/devices/{switch_a['id']}/ports")
        server_a_ports = await client.get(f"/api/devices/{server_a['id']}/ports")
        p_a1 = switch_a_ports.json()[0]["id"]
        p_a2 = switch_a_ports.json()[1]["id"]
        p_a3 = switch_a_ports.json()[2]["id"]
        p_a2_data = await client.patch(f"/api/ports/{p_a2}", json={"operStatus": "up", "stale": True})
        assert p_a2_data.status_code == 200
        p_a1_up = await client.patch(f"/api/ports/{p_a1}", json={"operStatus": "up"})
        assert p_a1_up.status_code == 200
        p_a3_down = await client.patch(f"/api/ports/{p_a3}", json={"operStatus": "down"})
        assert p_a3_down.status_code == 200
        await client.patch(f"/api/ports/{server_a_ports.json()[0]['id']}", json={"operStatus": "up"})

        response = await client.get(f"/api/ports?topologyId={topology_a['id']}&status=up&includeStale=false")
        assert response.status_code == 200
        assert [port["name"] for port in response.json()] == ["ge-1", "eth0"]

        response = await client.get(f"/api/ports?topologyId={topology_a['id']}&status=stale")
        assert response.status_code == 200
        assert [port["name"] for port in response.json()] == ["ge-2"]

        response = await client.get(f"/api/ports?topologyId={topology_a['id']}&status=up&includeStale=false&limit=1&offset=1")
        assert response.status_code == 200
        assert len(response.json()) == 1
        assert response.json()[0]["name"] == "eth0"

        page = await client.get(f"/api/ports/page?topologyId={topology_a['id']}&status=up&includeStale=false&limit=1&offset=1")
        assert page.status_code == 200
        assert page.json()["total"] == 2
        assert len(page.json()["items"]) == 1
        assert page.json()["items"][0]["name"] == "eth0"

        response = await client.get("/api/ports?includeStale=false")
        assert response.status_code == 200
        assert len(response.json()) == 4

    await engine.dispose()


async def test_topology_layout_viewport_roundtrip():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    database.engine = engine
    database.SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    app.state.zabbix = object()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        topology = (await client.post("/api/topologies", json={"name": "layout-topology"})).json()
        device = (
            await client.post(
                "/api/devices",
                json={
                    "displayName": "switch-layout",
                    "role": "switch",
                    "topologyId": topology["id"],
                    "ports": [{"name": "ge-1"}],
                },
            )
        ).json()

        graph = await client.get(f"/api/topology?topologyId={topology['id']}")
        node_id = graph.json()["nodes"][0]["id"]
        payload = await client.patch(
            "/api/topology/layout",
            json={"layoutKey": f"topology:{topology['id']}", "nodes": [{"nodeId": node_id, "x": 120, "y": 250}], "viewport": {"x": 10, "y": 20, "zoom": 1.2}},
        )
        assert payload.status_code == 200

        restored = (await client.get(f"/api/topology?topologyId={topology['id']}")).json()
        assert restored["layout"]["viewport"] == {"x": 10.0, "y": 20.0, "zoom": 1.2}
        restored_node = next(item for item in restored["layout"]["nodes"] if item["nodeId"] == node_id)
        assert restored_node["x"] == 120
        assert restored_node["y"] == 250

        assert restored["nodes"][0]["position"]["x"] == 120
        assert restored["nodes"][0]["position"]["y"] == 250

    await engine.dispose()


async def test_cable_link_patch_and_delete_flow():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    database.engine = engine
    database.SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    app.state.zabbix = object()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        topo = (await client.post("/api/topologies", json={"name": "link-edit"})).json()
        left = (
            await client.post(
                "/api/devices",
                json={
                    "displayName": "switch-left",
                    "role": "switch",
                    "topologyId": topo["id"],
                    "ports": [{"name": "ge-1"}],
                },
            )
        ).json()
        right = (
            await client.post(
                "/api/devices",
                json={
                    "displayName": "server-right",
                    "role": "server",
                    "topologyId": topo["id"],
                    "ports": [{"name": "eth0"}],
                },
            )
        ).json()

        left_port = (await client.get(f"/api/devices/{left['id']}/ports")).json()[0]
        right_port = (await client.get(f"/api/devices/{right['id']}/ports")).json()[0]
        link = (
            await client.post(
                "/api/cable-links",
                json={"endpointAPortId": left_port["id"], "endpointBPortId": right_port["id"], "label": "A-01", "cableNo": "C-01"},
            )
        ).json()
        patch = await client.patch(
            f"/api/cable-links/{link['id']}",
            json={"cableNo": "C-02", "label": "A-02", "notes": "updated"},
        )
        assert patch.status_code == 200
        assert patch.json()["cableNo"] == "C-02"
        assert patch.json()["label"] == "A-02"
        assert patch.json()["notes"] == "updated"

        delete = await client.delete(f"/api/cable-links/{link['id']}")
        assert delete.status_code == 200

        topology_after = (await client.get(f"/api/topology?topologyId={topo['id']}")).json()
        assert topology_after["cableLinks"] == []
        assert topology_after["edges"] == []

    await engine.dispose()


async def test_topology_unlink_device_keeps_inventory_and_layout_clean():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    database.engine = engine
    database.SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    app.state.zabbix = object()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        topology = (await client.post("/api/topologies", json={"name": "unlink-topo"})).json()
        device = (
            await client.post(
                "/api/devices",
                json={"displayName": "unlink-device", "role": "server", "topologyId": topology["id"], "ports": [{"name": "eth0"}]},
            )
        ).json()
        node_id = f"device-{device['id']}"
        layout = await client.patch(
            "/api/topology/layout",
            json={"layoutKey": f"topology:{topology['id']}", "nodes": [{"nodeId": node_id, "x": 120, "y": 180}]},
        )
        assert layout.status_code == 200

        removed = await client.delete(f"/api/topologies/{topology['id']}/devices/{device['id']}")
        assert removed.status_code == 200
        graph = (await client.get(f"/api/topology?topologyId={topology['id']}")).json()
        assert graph["devices"] == []
        assert all(item["nodeId"] != node_id for item in graph["layout"]["nodes"])
        devices = (await client.get("/api/devices?includeDisabled=true")).json()
        assert any(item["id"] == device["id"] for item in devices)

    await engine.dispose()


async def test_cable_endpoint_conflict_requires_replace_existing():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    database.engine = engine
    database.SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    app.state.zabbix = object()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        topo = (await client.post("/api/topologies", json={"name": "cable-conflict"})).json()
        a = (await client.post("/api/devices", json={"displayName": "a", "role": "server", "topologyId": topo["id"], "ports": [{"name": "eth0"}]})).json()
        b = (await client.post("/api/devices", json={"displayName": "b", "role": "switch", "topologyId": topo["id"], "ports": [{"name": "ge-1"}]})).json()
        c = (await client.post("/api/devices", json={"displayName": "c", "role": "switch", "topologyId": topo["id"], "ports": [{"name": "ge-2"}]})).json()
        a_port = (await client.get(f"/api/devices/{a['id']}/ports")).json()[0]["id"]
        b_port = (await client.get(f"/api/devices/{b['id']}/ports")).json()[0]["id"]
        c_port = (await client.get(f"/api/devices/{c['id']}/ports")).json()[0]["id"]
        first = await client.post("/api/cable-links", json={"endpointAPortId": a_port, "endpointBPortId": b_port, "label": "first"})
        assert first.status_code == 200
        conflict = await client.post("/api/cable-links", json={"endpointAPortId": a_port, "endpointBPortId": c_port, "label": "second"})
        assert conflict.status_code == 409
        replaced = await client.post("/api/cable-links", json={"endpointAPortId": a_port, "endpointBPortId": c_port, "label": "second", "replaceExisting": True})
        assert replaced.status_code == 200
        graph = (await client.get(f"/api/topology?topologyId={topo['id']}")).json()
        assert len(graph["cableLinks"]) == 1
        assert graph["cableLinks"][0]["label"] == "second"

    await engine.dispose()


async def test_read_only_mode_blocks_writes_without_admin_token():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    database.engine = engine
    database.SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    app.state.zabbix = object()

    app.dependency_overrides[api_routes.get_settings] = lambda: Settings(
        environment="test",
        read_only_mode=True,
        admin_token="secret",
    )
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            status = await client.get("/api/sync/status")
            assert status.status_code == 200
            assert status.json()["readOnly"] is True

            blocked = await client.post("/api/topologies", json={"name": "blocked"})
            assert blocked.status_code == 403

            allowed = await client.post("/api/topologies", json={"name": "allowed"}, headers={"X-Admin-Token": "secret"})
            assert allowed.status_code == 200
            assert allowed.json()["name"] == "allowed"
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


async def test_quality_issues_and_audit_logs_expose_operational_risks():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    database.engine = engine
    database.SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    app.state.zabbix = object()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        topology = (await client.post("/api/topologies", json={"name": "quality"})).json()
        server_a = (
            await client.post(
                "/api/devices",
                headers={"X-Actor": "tester"},
                json={
                    "displayName": "quality-server-a",
                    "role": "server",
                    "mgmtIp": "10.0.0.10",
                    "topologyId": topology["id"],
                    "ports": [{"name": "eth0", "macAddress": "52:54:00:AA:BB:CC"}],
                },
            )
        ).json()
        server_b = (
            await client.post(
                "/api/devices",
                json={
                    "displayName": "quality-server-b",
                    "role": "server",
                    "mgmtIp": "10.0.0.10",
                    "topologyId": topology["id"],
                    "ports": [{"name": "eth0", "macAddress": "52-54-00-aa-bb-cc"}],
                },
            )
        ).json()
        switch = (
            await client.post(
                "/api/devices",
                json={
                    "displayName": "quality-switch",
                    "role": "switch",
                    "topologyId": topology["id"],
                    "ports": [{"name": "ge-1"}],
                },
            )
        ).json()

        server_a_port = (await client.get(f"/api/devices/{server_a['id']}/ports")).json()[0]
        server_b_port = (await client.get(f"/api/devices/{server_b['id']}/ports")).json()[0]
        switch_port = (await client.get(f"/api/devices/{switch['id']}/ports")).json()[0]
        await client.patch(f"/api/ports/{server_a_port['id']}", json={"operStatus": "down"})
        await client.patch(f"/api/ports/{server_b_port['id']}", json={"operStatus": "up"})
        link = await client.post(
            "/api/cable-links",
            json={"endpointAPortId": server_a_port["id"], "endpointBPortId": switch_port["id"], "label": "risk-link"},
        )
        assert link.status_code == 200

        issues = await client.get(f"/api/quality/issues?topologyId={topology['id']}")
        assert issues.status_code == 200
        issue_ids = {item["id"] for item in issues.json()}
        assert "duplicate-device-mgmtIp-10.0.0.10" in issue_ids
        assert "duplicate-port-mac-52:54:00:aa:bb:cc" in issue_ids
        assert any(item["category"] == "link" and item["portId"] == server_a_port["id"] for item in issues.json())
        assert any(item["category"] == "inventory" and item["portId"] == server_b_port["id"] for item in issues.json())

        audit = await client.get("/api/audit-logs?resourceType=device")
        assert audit.status_code == 200
        assert any(item["action"] == "device.create" and item["actor"] == "tester" for item in audit.json())


async def test_sync_and_import_uses_snapshot_sync_once(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    database.engine = engine
    database.SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    app.state.zabbix = object()

    async def fake_collect(_zabbix, _settings):
        counters["collect"] += 1
        return [
            fake_snapshot("snap-101", "ge-1"),
            fake_snapshot("snap-102", "ge-2"),
        ]

    original_sync_from_snapshots = api_routes.run_zabbix_sync_from_snapshots
    counters = {"collect": 0, "from_snapshots": 0}

    async def fake_collect_snapshots(_session, _settings, snapshots):
        counters["from_snapshots"] += 1
        return await original_sync_from_snapshots(_session, _settings, snapshots)

    def forbidden_full_sync(*_args, **_kwargs):
        raise AssertionError("run_zabbix_sync should not be called by sync-and-import")

    monkeypatch.setattr(api_routes, "collect_zabbix_snapshots", fake_collect)
    monkeypatch.setattr(api_routes, "run_zabbix_sync", forbidden_full_sync)
    monkeypatch.setattr(api_routes, "run_zabbix_sync_from_snapshots", fake_collect_snapshots)
    app.dependency_overrides[api_routes.get_settings] = lambda: Settings(
        environment="test",
        zabbix_user="admin",
        zabbix_password="pwd",
    )

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            topology = (await client.post("/api/topologies", json={"name": "sync-once"})).json()
            response = await client.post(
                f"/api/topologies/{topology['id']}/sync-and-import",
                json={"hostids": ["snap-101"]},
            )
            assert response.status_code == 200
            assert response.json()["deviceCount"] == 1

            ports = (await client.get(f"/api/ports?topologyId={topology['id']}")).json()
            assert len(ports) == 1
            assert any(port["name"] == "ge-1" for port in ports)
            assert counters["from_snapshots"] == 1

            # verify helper path was not used
            counter_value = counters["collect"]
            assert counter_value == 1
    finally:
        app.dependency_overrides.clear()

    await engine.dispose()


async def test_zabbix_sync_run_does_not_import_all_devices_to_topology():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    database.engine = engine
    database.SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    app.state.zabbix = object()

    async def fake_sync(session, _zabbix, settings):
        return await api_routes.run_zabbix_sync_from_snapshots(session, settings, [fake_snapshot("bulk-101", "ge-1")])

    app.dependency_overrides[api_routes.get_settings] = lambda: Settings(environment="test", zabbix_token="token")
    try:
        original_sync = api_routes.run_zabbix_sync
        api_routes.run_zabbix_sync = fake_sync
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            topology = (await client.post("/api/topologies", json={"name": "manual-scope"})).json()
            response = await client.post(f"/api/sync/zabbix/run?topologyId={topology['id']}")
            assert response.status_code == 200
            assert response.json()["status"] == "success"

            graph = (await client.get(f"/api/topology?topologyId={topology['id']}")).json()
            assert graph["devices"] == []

            devices = (await client.get("/api/devices?includeDisabled=true")).json()
            assert {device["zabbixHostid"] for device in devices} == {"bulk-101"}
    finally:
        api_routes.run_zabbix_sync = original_sync
        app.dependency_overrides.clear()
        await engine.dispose()


async def test_sync_push_payload_supports_strict_physical_filter():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    database.engine = engine
    database.SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    app.state.zabbix = object()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        topology = (await client.post("/api/topologies", json={"name": "push-topo"})).json()

        strict_response = await client.post(
            "/api/sync/push",
            json={
                "source": "agent",
                "strictPhysicalPorts": True,
                "topologyId": topology["id"],
                "devices": [
                    {
                        "displayName": "core-switch",
                        "role": "switch",
                        "ports": [
                            {"name": "vWAN2001"},
                            {"name": "XGE0/1"},
                        ],
                    },
                ],
                "cables": [],
            },
        )
        assert strict_response.status_code == 200
        strict_body = strict_response.json()
        assert strict_body["devices"] == 1
        assert strict_body["ports"] == 1

        loose_response = await client.post(
            "/api/sync/push",
            json={
                "source": "agent",
                "strictPhysicalPorts": False,
                "topologyId": topology["id"],
                "devices": [
                    {
                        "displayName": "core-switch",
                        "role": "switch",
                        "ports": [
                            {"name": "vWAN2001"},
                            {"name": "XGE0/1"},
                        ],
                    },
                ],
                "cables": [],
            },
        )
        assert loose_response.status_code == 200
        loose_body = loose_response.json()
        assert loose_body["devices"] == 1
        assert loose_body["ports"] == 2

        devices = (await client.get("/api/devices")).json()
        core_switch = next(item for item in devices if item["displayName"] == "core-switch")
        ports = (await client.get(f"/api/ports?deviceId={core_switch['id']}&includeVirtual=true")).json()
        assert {item["name"] for item in ports} == {"vWAN2001", "XGE0/1"}
        visible_ports = (await client.get(f"/api/ports?deviceId={core_switch['id']}")).json()
        assert {item["name"] for item in visible_ports} == {"XGE0/1"}

    await engine.dispose()


async def test_ingest_preserves_manual_port_ownership_and_stales_empty_source_snapshot():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    database.engine = engine
    database.SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    app.state.zabbix = object()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        manual_device = (
            await client.post(
                "/api/devices",
                json={"displayName": "owned-server", "role": "server", "ports": [{"name": "eth0"}]},
            )
        ).json()
        push = await client.post(
            "/api/sync/push",
            json={
                "source": "agent",
                "devices": [
                    {
                        "displayName": "owned-server",
                        "role": "server",
                        "ports": [{"name": "eth0", "operStatus": "up"}],
                    }
                ],
                "cables": [],
            },
        )
        assert push.status_code == 200
        manual_ports = (await client.get(f"/api/devices/{manual_device['id']}/ports")).json()
        assert manual_ports[0]["source"] == "manual"
        assert manual_ports[0]["identity"] == "manual:eth0"
        assert manual_ports[0]["operStatus"] == "up"

        first_agent_push = await client.post(
            "/api/sync/push",
            json={
                "source": "agent",
                "strictPhysicalPorts": True,
                "devices": [
                    {
                        "displayName": "agent-owned",
                        "role": "server",
                        "ports": [{"name": "ens18"}, {"name": "ens19"}],
                    }
                ],
                "cables": [],
            },
        )
        assert first_agent_push.status_code == 200
        agent_device = next(item for item in (await client.get("/api/devices?includeDisabled=true")).json() if item["displayName"] == "agent-owned")
        agent_ports = (await client.get(f"/api/ports?deviceId={agent_device['id']}&includeStale=true")).json()
        assert {port["identity"] for port in agent_ports} == {"agent:ens18", "agent:ens19"}
        assert all(port["stale"] is False for port in agent_ports)

        empty_agent_push = await client.post(
            "/api/sync/push",
            json={
                "source": "agent",
                "strictPhysicalPorts": True,
                "devices": [
                    {
                        "displayName": "agent-owned",
                        "role": "server",
                        "ports": [{"name": "vWAN2001"}],
                    }
                ],
                "cables": [],
            },
        )
        assert empty_agent_push.status_code == 200
        stale_ports = (await client.get(f"/api/ports?deviceId={agent_device['id']}&includeStale=true")).json()
        assert {port["name"] for port in stale_ports} == {"ens18", "ens19"}
        assert all(port["stale"] is True for port in stale_ports)

    await engine.dispose()


async def test_command_push_can_update_existing_cables_without_devices_payload():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    database.engine = engine
    database.SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    app.state.zabbix = object()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        topology = (await client.post("/api/topologies", json={"name": "command-cables"})).json()
        server = (
            await client.post(
                "/api/devices",
                json={
                    "displayName": "compute-01",
                    "role": "server",
                    "topologyId": topology["id"],
                    "ports": [{"name": "ens1f0"}],
                },
            )
        ).json()
        switch = (
            await client.post(
                "/api/devices",
                json={
                    "displayName": "tor-01",
                    "role": "switch",
                    "topologyId": topology["id"],
                    "ports": [{"name": "XGE0/1"}],
                },
            )
        ).json()

        pushed = await client.post(
            "/api/sync/command-push",
            json={
                "source": "command",
                "topologyId": topology["id"],
                "strictPhysicalPorts": True,
                "devices": [],
                "cables": [
                    {
                        "endpointA": {"deviceId": server["id"], "portName": "ens1f0"},
                        "endpointB": {"displayName": "tor-01", "portName": "XGE0/1"},
                        "label": "compute-01 uplink",
                        "cableNo": "CAB-1001",
                        "vlanId": 88,
                    }
                ],
            },
        )

        assert pushed.status_code == 200
        assert pushed.json()["devices"] == 0
        assert pushed.json()["ports"] == 0
        assert pushed.json()["cables"] == 1

        graph = (await client.get(f"/api/topology?topologyId={topology['id']}")).json()
        assert len(graph["cableLinks"]) == 1
        assert len(graph["edges"]) == 1
        assert graph["cableLinks"][0]["label"] == "compute-01 uplink"
        assert graph["cableLinks"][0]["cableNo"] == "CAB-1001"
        assert graph["cableLinks"][0]["vlanId"] == 88
        assert graph["edges"][0]["data"]["vlan"] == 88
        assert {device["displayName"] for device in graph["devices"]} == {"compute-01", "tor-01"}
        assert switch["id"] != server["id"]

    await engine.dispose()


async def test_command_push_can_resolve_cable_endpoint_by_mac_address():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    database.engine = engine
    database.SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    app.state.zabbix = object()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        topology = (await client.post("/api/topologies", json={"name": "mac-learned"})).json()
        server = (
            await client.post(
                "/api/devices",
                json={
                    "displayName": "compute-mac",
                    "role": "server",
                    "topologyId": topology["id"],
                    "ports": [{"name": "ens1f0", "macAddress": "52-54-00-AA-BB-CC"}],
                },
            )
        ).json()
        switch = (
            await client.post(
                "/api/devices",
                json={
                    "displayName": "tor-mac",
                    "role": "switch",
                    "topologyId": topology["id"],
                    "ports": [{"name": "XGE0/2"}],
                },
            )
        ).json()
        server_ports = (await client.get(f"/api/devices/{server['id']}/ports")).json()
        switch_ports = (await client.get(f"/api/devices/{switch['id']}/ports")).json()
        assert server_ports[0]["macAddress"] == "52:54:00:aa:bb:cc"

        pushed = await client.post(
            "/api/sync/command-push",
            json={
                "source": "command",
                "topologyId": topology["id"],
                "devices": [],
                "cables": [
                    {
                        "endpointA": {"displayName": "tor-mac", "portName": "XGE0/2"},
                        "endpointB": {"macAddress": "5254.00aa.bbcc"},
                        "label": "learned-from-mac",
                        "vlanId": 77,
                    }
                ],
            },
        )

        assert pushed.status_code == 200
        assert pushed.json()["cables"] == 1

        graph = (await client.get(f"/api/topology?topologyId={topology['id']}")).json()
        link = graph["cableLinks"][0]
        assert {link["endpointAPortId"], link["endpointBPortId"]} == {server_ports[0]["id"], switch_ports[0]["id"]}
        assert link["vlanId"] == 77
        assert graph["edges"][0]["data"]["vlan"] == 77

    await engine.dispose()


async def test_topology_edges_use_vlan_colors():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    database.engine = engine
    database.SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    app.state.zabbix = object()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        topology = (await client.post("/api/topologies", json={"name": "vlan-color"})).json()
        switch = (
            await client.post(
                "/api/devices",
                json={
                    "displayName": "vlan-switch",
                    "role": "switch",
                    "topologyId": topology["id"],
                    "ports": [{"name": "ge-1", "vlanSummary": "trunk 10,20"}],
                },
            )
        ).json()
        server = (
            await client.post(
                "/api/devices",
                json={
                    "displayName": "vlan-server",
                    "role": "server",
                    "topologyId": topology["id"],
                    "ports": [{"name": "eth0", "vlanSummary": "PVID 20"}],
                },
            )
        ).json()
        switch_port = (await client.get(f"/api/devices/{switch['id']}/ports")).json()[0]
        server_port = (await client.get(f"/api/devices/{server['id']}/ports")).json()[0]
        await client.post(
            "/api/cable-links",
            json={
                "endpointAPortId": switch_port["id"],
                "endpointBPortId": server_port["id"],
                "color": "#3274d9",
            },
        )

        graph = (await client.get(f"/api/topology?topologyId={topology['id']}")).json()
        assert graph["edges"][0]["data"]["vlan"] == 20
        assert graph["edges"][0]["style"]["stroke"] != "#3274d9"

    await engine.dispose()


async def test_ip_addr_push_parses_server_physical_ports():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    database.engine = engine
    database.SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    app.state.zabbix = object()

    ip_addr_output = """
1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 state UNKNOWN qdisc noqueue
    inet 127.0.0.1/8 scope host lo
2: ens18: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 state UP qdisc mq
    link/ether 52:54:00:10:20:30 brd ff:ff:ff:ff:ff:ff
    inet 192.168.10.21/24 brd 192.168.10.255 scope global ens18
3: eno1: <BROADCAST,MULTICAST> mtu 1500 state DOWN qdisc noop
    link/ether 52:54:00:10:20:31 brd ff:ff:ff:ff:ff:ff
4: docker0: <NO-CARRIER,BROADCAST,MULTICAST,UP> mtu 1500 state DOWN qdisc noqueue
    inet 172.17.0.1/16 brd 172.17.255.255 scope global docker0
"""

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        topology = (await client.post("/api/topologies", json={"name": "ip-addr-topo", "isDefault": True})).json()
        response = await client.post(
            "/api/sync/ip-addr",
            json={
                "displayName": "compute-ipaddr",
                "mgmtIp": "192.168.10.21",
                "output": ip_addr_output,
                "topologyId": topology["id"],
            },
        )
        assert response.status_code == 200
        assert response.json()["devices"] == 1
        assert response.json()["ports"] == 2

        graph = (await client.get(f"/api/topology?topologyId={topology['id']}")).json()
        device = next(item for item in graph["devices"] if item["displayName"] == "compute-ipaddr")
        ports = (await client.get(f"/api/devices/{device['id']}/ports")).json()
        assert {port["name"] for port in ports} == {"ens18", "eno1"}
        ens18 = next(port for port in ports if port["name"] == "ens18")
        assert ens18["operStatus"] == "up"
        assert ens18["alias"] == "192.168.10.21/24"
        assert ens18["macAddress"] == "52:54:00:10:20:30"
        assert all(port["name"] != "docker0" for port in ports)

    await engine.dispose()


async def test_network_prefixed_ip_addr_push_uses_api_router():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    database.engine = engine
    database.SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    app.state.zabbix = object()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        topology = (await client.post("/network/api/topologies", json={"name": "network-prefix", "isDefault": True})).json()
        response = await client.post(
            "/network/api/sync/ip-addr",
            json={
                "displayName": "prefixed-compute",
                "output": "2: ens19: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 state UP\n    inet 10.0.0.19/24 scope global ens19\n",
                "topologyId": topology["id"],
            },
        )

        assert response.status_code == 200
        assert response.json()["devices"] == 1
        assert response.json()["ports"] == 1
        graph = (await client.get(f"/network/api/topology?topologyId={topology['id']}")).json()
        assert {device["displayName"] for device in graph["devices"]} == {"prefixed-compute"}

    await engine.dispose()


async def test_manual_device_and_port_config_survives_zabbix_sync():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    database.engine = engine
    database.SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    app.state.zabbix = object()

    first_snapshot = DeviceSnapshot(
        zabbix_hostid="override-1",
        role="server",
        display_name="zabbix-name",
        model="PowerEdge",
        mgmt_ip="10.20.30.40",
        status="online",
        health="ok",
        ports=[
            PortSnapshot(
                identity="ifindex:1",
                if_index=1,
                name="ens18",
                alias="from zabbix",
                oper_status="up",
                admin_status="up",
                speed_mbps=1000,
                media="ethernet",
                port_role="uplink",
                vlan_summary="PVID 20",
            )
        ],
    )
    second_snapshot = DeviceSnapshot(
        zabbix_hostid="override-1",
        role="server",
        display_name="zabbix-renamed",
        model="NewModel",
        mgmt_ip="10.20.30.41",
        status="online",
        health="warning",
        ports=[
            PortSnapshot(
                identity="ifindex:1",
                if_index=1,
                name="ens19",
                alias="from zabbix again",
                oper_status="down",
                admin_status="up",
                speed_mbps=25000,
                media="fiber",
                port_role="server",
                vlan_summary="PVID 30",
            )
        ],
    )

    async with database.SessionLocal() as session:
        await api_routes.run_zabbix_sync_from_snapshots(session, Settings(environment="test"), [first_snapshot])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        devices = (await client.get("/api/devices")).json()
        device = next(item for item in devices if item["zabbixHostid"] == "override-1")
        ports = (await client.get(f"/api/devices/{device['id']}/ports")).json()
        port = ports[0]

        device_patch = await client.patch(
            f"/api/devices/{device['id']}",
            json={"displayName": "manual-name", "model": "ManualModel", "mgmtIp": "10.20.30.99"},
        )
        assert device_patch.status_code == 200
        port_patch = await client.patch(
            f"/api/ports/{port['id']}",
            json={"name": "uplink0", "alias": "manual alias", "speedMbps": 10000, "media": "dac", "portRole": "storage", "vlanSummary": "PVID 88"},
        )
        assert port_patch.status_code == 200

    async with database.SessionLocal() as session:
        await api_routes.run_zabbix_sync_from_snapshots(session, Settings(environment="test"), [second_snapshot])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        refreshed_device = next(item for item in (await client.get("/api/devices")).json() if item["zabbixHostid"] == "override-1")
        refreshed_ports = (await client.get(f"/api/devices/{refreshed_device['id']}/ports")).json()
        refreshed_port = refreshed_ports[0]

        assert refreshed_device["displayName"] == "manual-name"
        assert refreshed_device["model"] == "ManualModel"
        assert refreshed_device["mgmtIp"] == "10.20.30.99"
        assert refreshed_device["health"] == "warning"
        assert refreshed_port["name"] == "uplink0"
        assert refreshed_port["alias"] == "manual alias"
        assert refreshed_port["speedMbps"] == 10000
        assert refreshed_port["media"] == "dac"
        assert refreshed_port["portRole"] == "storage"
        assert refreshed_port["vlanSummary"] == "PVID 88"
        assert refreshed_port["operStatus"] == "down"

    await engine.dispose()

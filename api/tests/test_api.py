from __future__ import annotations

from datetime import datetime, timezone, timedelta

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app import database
from app.db_models import Base, ZabbixSyncRun
from app.main import app


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
            json={"endpointAPortId": first_port, "endpointBPortId": second_port, "label": "L-001"},
        )
        assert link.status_code == 200
        topology = await client.get("/api/topology")
        assert topology.status_code == 200
        assert len(topology.json()["edges"]) == 1

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

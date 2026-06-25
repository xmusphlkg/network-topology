# Contributing

Thanks for improving Switch Topology.

## Development

Backend:

```bash
cd api
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
DATABASE_URL=sqlite+aiosqlite:///./switch_topology.db AUTO_SYNC_ENABLED=false .venv/bin/uvicorn app.main:app --reload --port 8091
```

Frontend:

```bash
cd web
npm install
VITE_API_BASE=http://127.0.0.1:8091 npm run dev -- --port 5174
```

Checks:

```bash
cd api && .venv/bin/pytest -q
cd web && npm run build
```

## Device Support

Prefer adding support through generic SNMP item parsing first. Add a model profile only when the physical port layout is useful for accurate panel rendering.

When adding a profile, include:

- Model names and common aliases.
- Port count and naming pattern.
- Media and default speed.
- A test fixture with representative Zabbix item keys.

Manual cable links are source-of-truth and must not be overwritten by discovery.


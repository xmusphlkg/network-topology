# Switch Topology

交换机端口状态与服务器网口拓扑台账。Zabbix 继续负责 SNMP 采集，本项目通过 Zabbix API 同步设备、端口和历史序列，并在本地数据库保存人工线缆关系、端口覆盖信息和拓扑布局。

核心原则：

- Zabbix/SNMP 负责事实采集。
- 人工确认的线缆台账是拓扑最终事实。
- 自动发现只补充设备、端口和候选信息，不覆盖人工连线。
- 不提供 SNMP 写配置能力。

## 本地开发（不打包 Docker）

### 0) 先装本机 MySQL

如果机器没有 MySQL Server，可先安装并启动（Ubuntu 示例）：

```bash
sudo apt update
sudo apt install -y mysql-server
sudo systemctl enable --now mysql
```

然后创建项目数据库和账号（示例）：

```bash
mysql -uroot -p -e "CREATE DATABASE switch_topology DEFAULT CHARSET utf8mb4;"
mysql -uroot -p -e "CREATE USER 'switch_topology'@'127.0.0.1' IDENTIFIED BY 'topology_local_pass';"
mysql -uroot -p -e "GRANT ALL PRIVILEGES ON switch_topology.* TO 'switch_topology'@'127.0.0.1'; FLUSH PRIVILEGES;"
```

### 1) 准备环境变量

```bash
cp .env.local.example .env
```

Zabbix 7.x 推荐使用前端里创建的 API token：

```env
ZABBIX_URL=http://127.0.0.1:8080/zabbix
ZABBIX_TOKEN=你的 API token
ZABBIX_AUTH_MODE=bearer
```

`ZABBIX_URL` 可以填站点根路径或完整 `api_jsonrpc.php`，程序会自动补齐 JSON-RPC 端点。没有 API token 时也可以填 `ZABBIX_USER`/`ZABBIX_PASSWORD`，程序会用当前 Zabbix API 的 `username/password` 登录参数，并在关闭时注销会话。若需要兼容旧 Zabbix 或中间代理无法转发 `Authorization` header，可把 `ZABBIX_AUTH_MODE` 设为 `auto` 或 `auth`。

### 2) 启动后端（本地 Python）

```bash
cd api
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
DATABASE_URL=sqlite+aiosqlite:///./switch_topology.db uvicorn app.main:app --host 0.0.0.0 --port 8091 --reload
```

当 MySQL 已就绪时，去掉 `DATABASE_URL=...`，改用 `.env` 里的 MySQL 配置即可。

### 3) 启动前端（本地 Node）

另开一个终端：

```bash
cd web
npm install
VITE_BASE_PATH=/ VITE_API_BASE=http://127.0.0.1:8091 npm run dev -- --host 127.0.0.1 --port 5174
```

后端启动后会自动创建表；前端页面在 `http://127.0.0.1:5174`。

### 4) 本地验证命令（可选）

```bash
cd api
pytest -q
```

后续如果你想临时用 docker-compose 验证整站启动，可用 `docker-compose.local.yml` 与：

```bash
./scripts/dev-up.sh   # 启动（本地 compose）
./scripts/dev-down.sh # 停止
```

## 生产部署到 192.168.3.222（Docker 镜像推送）

生产环境推荐仍用单服务 compose（`docker-compose.yml`），拓扑页入口为 `/topology`：

```bash
cp .env.example .env
docker compose up -d --build
```

如果希望本地离线构建镜像后再推到 192.168.3.222：

```bash
cd /home/ctm/nezha/switch-topology
./scripts/build-offline.sh ./switch-topology-offline.tar.gz
scp ./switch-topology-offline.tar.gz 192.168.3.222:/home/ctm/nezha/switch-topology/
scp .env docker-compose.yml 192.168.3.222:/home/ctm/nezha/switch-topology/
ssh 192.168.3.222 'docker load -i /home/ctm/nezha/switch-topology/switch-topology-offline.tar.gz'
ssh 192.168.3.222 'cd /home/ctm/nezha/switch-topology && APP_IMAGE=${APP_IMAGE:-switch-topology-switch-topology:latest} docker compose up -d --no-build'
```

如果你的环境第一次拉镜像很慢（尤其是 Node 镜像），可在 `.env` 里先设置：

```env
NODE_IMAGE=node:18-alpine
```

生产访问路径建议设为：

```env
PUBLIC_BASE_URL=http://192.168.3.222
VITE_BASE_PATH=/
VITE_API_BASE=
```

若目标机前置了 nginx，可使用：

```nginx
location / {
    proxy_pass http://127.0.0.1:8091;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

## 数据模型

- `st_devices`：交换机、服务器和自定义设备。
- `st_ports`：Zabbix LLD 或手动创建的网口。
- `st_cable_links`：人工确认的线缆连接。
- `st_topologies`：多拓扑画布配置。
- `st_topology_devices`：拓扑内设备归属关系。
- `st_topology_layouts`：拓扑画布位置和视图状态。
- `st_zabbix_sync_runs`：Zabbix 同步结果。

## 主要 API

- `GET /api/topology`
- `GET /api/topology?topologyId={id}`
- `PATCH /api/topology/layout`
- `GET /api/topologies`
- `POST /api/topologies`
- `PATCH /api/topologies/{id}`
- `POST /api/topologies/{id}/devices`
- `GET /api/zabbix/discovered-devices?topologyId={id}`
- `POST /api/topologies/{id}/sync-and-import`
- `GET /api/devices`
- `POST /api/devices`
- `PATCH /api/devices/{id}`
- `GET /api/devices/{id}/ports`
- `GET /api/ports`
- `GET /api/ports/{id}/series?range=1h|6h|24h|7d`
- `POST /api/cable-links`
- `PATCH /api/cable-links/{id}`
- `DELETE /api/cable-links/{id}`
- `POST /api/sync/zabbix/run`
- `GET /api/sync/status`

## 设计边界

本项目不通过 SNMP 修改交换机配置。线缆台账以人工确认为准，自动发现只负责补充设备、端口和候选信息。

## 设备支持

通用 SNMP 映射支持 IF-MIB 风格接口命名，覆盖 Ruijie、Cisco、Huawei/H3C、Juniper、Arista、Dell/SONiC 和 Linux 服务器网口。物理面板 profile 目前内置锐捷 `S6220-48XS6QXS-H` 与 `S5750-48GT4XS-HP-H`。扩展说明见 [docs/device-support.md](docs/device-support.md)。

#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

COMPOSE_FILES=(
  -f docker-compose.yml
  -f docker-compose.local.yml
)
LOCAL_ENV=".env.local"

if [[ -f "$LOCAL_ENV" ]]; then
  cp "$LOCAL_ENV" .env
fi

if [[ ! -f .env ]]; then
  if [[ -f "$LOCAL_ENV" ]]; then
    cp "$LOCAL_ENV" .env
    echo "已创建 .env（基于 .env.local）。请先确认你的本地配置。"
  elif [[ -f .env.local.example ]]; then
    cp .env.local.example .env
    echo "已创建 .env（基于 .env.local.example），请先按本地环境填写密码后再启动。"
  else
    echo "未检测到 .env 与环境模板，请先创建 .env"
    exit 1
  fi
fi

source .env

if [[ -z "${MYSQL_USER:-}" ]]; then
  echo "请先设置 MYSQL_USER（.env 中不能为空）"
  exit 1
fi

if [[ -z "${MYSQL_PASSWORD:-}" ]]; then
  echo "请先设置 MYSQL_PASSWORD（.env 中不能为空）"
  exit 1
fi

if [[ -z "${MYSQL_DATABASE:-}" ]]; then
  echo "请先设置 MYSQL_DATABASE（.env 中不能为空）"
  exit 1
fi

if [[ -z "${MYSQL_HOST:-}" ]]; then
  echo "请先设置 MYSQL_HOST（.env 中不能为空）"
  exit 1
fi

if [[ -z "${MYSQL_ROOT_PASSWORD:-}" ]]; then
  MYSQL_ROOT_PASSWORD=""
fi

if [[ -z "${MYSQL_PORT:-}" ]]; then
  MYSQL_PORT=3306
fi

export MYSQL_PASSWORD MYSQL_DATABASE MYSQL_USER MYSQL_HOST MYSQL_PORT MYSQL_ROOT_PASSWORD

if ! command -v docker >/dev/null 2>&1; then
  echo "未检测到 docker，请先安装 docker 或直接用本地 Python/Node 运行开发环境。"
  exit 1
fi

if ! pgrep mysqld >/dev/null 2>&1; then
  echo "未检测到本机 mysqld 进程；如果你已配置 docker-compose.local 的 mysql 容器，这里是正常输出。"
fi

docker compose "${COMPOSE_FILES[@]}" up -d --build

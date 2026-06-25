#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

IMAGE_NAME="${APP_IMAGE:-switch-topology-switch-topology:latest}"
NODE_IMAGE="${NODE_IMAGE:-node:22-alpine}"
OUTPUT_TAR="${1:-/tmp/switch-topology-offline.tar.gz}"

if [[ -f .env ]]; then
  # shellcheck disable=SC1090
  source .env
  IMAGE_NAME="${APP_IMAGE:-$IMAGE_NAME}"
  NODE_IMAGE="${NODE_IMAGE:-$NODE_IMAGE}"
fi

echo "Building image: $IMAGE_NAME (NODE_IMAGE=$NODE_IMAGE)"
APP_IMAGE="$IMAGE_NAME" NODE_IMAGE="$NODE_IMAGE" docker compose build

docker save "$IMAGE_NAME" | gzip > "$OUTPUT_TAR"
echo "Image exported: $OUTPUT_TAR"

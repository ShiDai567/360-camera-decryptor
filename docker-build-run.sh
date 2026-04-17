#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE_NAME="${IMAGE_NAME:-360-camera-decryptor:latest}"
CONTAINER_NAME="${CONTAINER_NAME:-360-camera-decryptor}"
HOST_PORT="${HOST_PORT:-5000}"
CONTAINER_PORT="${CONTAINER_PORT:-5000}"

CONFIG_DIR="$ROOT_DIR/backend/data"
CONFIG_FILE="$CONFIG_DIR/config.yaml"
EXAMPLE_CONFIG_FILE="$ROOT_DIR/backend/config.example.yaml"
CACHE_DIR="$ROOT_DIR/backend/.cache"
PLAY_INFO_CACHE_DIR="$ROOT_DIR/backend/data/play_info_cache"

mkdir -p "$CONFIG_DIR" "$CACHE_DIR" "$PLAY_INFO_CACHE_DIR"

if [[ ! -f "$CONFIG_FILE" ]]; then
  if [[ ! -f "$EXAMPLE_CONFIG_FILE" ]]; then
    echo "未找到配置模板: $EXAMPLE_CONFIG_FILE" >&2
    exit 1
  fi
  cp "$EXAMPLE_CONFIG_FILE" "$CONFIG_FILE"
  echo "已自动创建配置文件: $CONFIG_FILE"
fi

echo "构建镜像: $IMAGE_NAME"
docker build -t "$IMAGE_NAME" -f "$ROOT_DIR/docker/Dockerfile" "$ROOT_DIR"

if docker ps -a --format '{{.Names}}' | grep -Fxq "$CONTAINER_NAME"; then
  echo "删除已有容器: $CONTAINER_NAME"
  docker rm -f "$CONTAINER_NAME" >/dev/null
fi

echo "启动容器: $CONTAINER_NAME"
docker run -d \
  --name "$CONTAINER_NAME" \
  --restart unless-stopped \
  -p "$HOST_PORT:$CONTAINER_PORT" \
  -e CAMERA_BACKEND_PORT="$CONTAINER_PORT" \
  -e CAMERA_BACKEND_HOST="0.0.0.0" \
  -e CAMERA_BACKEND_DEBUG="0" \
  -v "$CONFIG_FILE:/app/backend/data/config.yaml" \
  -v "$CACHE_DIR:/app/backend/.cache" \
  -v "$PLAY_INFO_CACHE_DIR:/app/backend/data/play_info_cache" \
  "$IMAGE_NAME"

echo "容器已启动"
echo "访问地址: http://127.0.0.1:$HOST_PORT/"

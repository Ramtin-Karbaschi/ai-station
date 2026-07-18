#!/usr/bin/env bash
set -Eeuo pipefail

cd /opt/ai-station

BASE_IMAGE="apache/tika:3.3.0.0-full"
LOCAL_IMAGE="ai-station/tika-fa:3.3.0.0-full"

echo "=== Pulling base image with retry: ${BASE_IMAGE} ==="

for i in $(seq 1 20); do
  echo "Pull attempt ${i}/20"

  if docker pull --platform linux/amd64 "${BASE_IMAGE}"; then
    echo "Base image pulled."
    break
  fi

  echo "Pull failed. Waiting before retry..."
  docker image prune -f >/dev/null 2>&1 || true
  sleep 20

  if [ "$i" = "20" ]; then
    echo "ERROR: Could not pull ${BASE_IMAGE}"
    exit 1
  fi
done

echo
echo "=== Building local Persian-capable Tika image ==="

for i in $(seq 1 5); do
  echo "Build attempt ${i}/5"

  if docker build \
      --pull=false \
      -t "${LOCAL_IMAGE}" \
      -f infra/tika-fa/Dockerfile \
      infra/tika-fa; then
    echo "Build complete: ${LOCAL_IMAGE}"
    docker image inspect "${LOCAL_IMAGE}" >/dev/null
    exit 0
  fi

  echo "Build failed. Retrying..."
  sleep 20
done

echo "ERROR: Could not build ${LOCAL_IMAGE}"
exit 1

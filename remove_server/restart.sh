#!/bin/bash
set -e

cd /root/humidity/dorogino_humidity/remove_server

git pull origin main
docker-compose down
docker system prune -f
docker compose up --build

echo "✅ Готово"
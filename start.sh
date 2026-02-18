#!/bin/bash
set -e  # Остановить при любой ошибке

cd /home/kiseleveduard/dev/dorogino_humidity

git pull

docker compose down

# Собираем (если нужно обновлять код)
echo "🔨 Building services..."
docker compose up --build -d

# Очистка: удаляем неиспользуемые образы, контейнеры, сети
echo "🧹 Cleaning unused Docker resources..."
docker system prune -f 

echo "✅ dorogino_humidity started and cleaned up."


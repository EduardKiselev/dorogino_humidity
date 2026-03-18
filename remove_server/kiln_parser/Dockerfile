# worker/Dockerfile
FROM python:3.9.18-slim

RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    libgl1-mesa-glx \
    cron \
    procps \  
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY parser.py worker.py crontab ./

# Настройка cron
RUN chmod 0644 crontab && crontab crontab

CMD ["cron", "-f"]
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app_data_collector.py .
# COPY ./front/models.py
#COPY init.sql .

EXPOSE 5000

CMD ["python", "app_data_collector.py"]
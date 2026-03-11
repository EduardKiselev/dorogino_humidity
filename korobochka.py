# server.py
from flask import Flask, request, jsonify
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import requests
import threading
import os
from dotenv import load_dotenv
import socket

# Загрузка переменных окружения из .env файла
load_dotenv()

app = Flask(__name__)

# Настройки из переменных окружения
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_NAME = os.getenv('DB_NAME', 'mydatabase')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'postgres')

FORWARD_URL = os.getenv('FORWARD_URL', '')

FORWARD_TIMEOUT = int(os.getenv('FORWARD_TIMEOUT', '5'))

APP_HOST = os.getenv('APP_HOST', '0.0.0.0')
APP_PORT = int(os.getenv('APP_PORT', '5000'))
DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'

# Строка подключения к БД
DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Инициализация БД
engine = create_engine(DATABASE_URL, pool_size=5, max_overflow=10)
Base = declarative_base()

class SensorReading(Base):
    __tablename__ = 'sensor_readings'
    
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.now)
    sensor_id = Column(Integer, nullable=False)
    temperature = Column(Float)
    humidity = Column(Float)
    voltage = Column(Float)
    ip_address = Column(String(50))

# Создание таблиц
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

def forward_data(data):
    """Пересылка данных в фоновом потоке"""
    if not FORWARD_URL:
        print("⚠️ FORWARD_URL не настроен, пересылка отключена")
        return
        
    try:
        response = requests.post(FORWARD_URL, json=data, timeout=FORWARD_TIMEOUT)
        print(f"📤 Переслано на {FORWARD_URL}: {response.status_code}")
    except Exception as e:
        print(f"❌ Ошибка пересылки на {FORWARD_URL}: {e}")

@app.route('/data', methods=['POST'])
def receive_data():
    """Приём данных от датчиков"""
    
    try:
        data = request.get_json()
        timestamp = datetime.now()
        

        source_ip = request.remote_addr
        destination_ip = request.environ.get('SERVER_ADDR') or socket.gethostbyname(request.host.split(':')[0])
        
        print(f"📡 [{timestamp}] {source_ip} -> {destination_ip} : {data}")
        
        # Валидация данных
        if not isinstance(data, dict):
            return jsonify({"status": "error", "message": "Invalid JSON format"}), 400
        
        sensor_id = data.get('sensor_id')
        if sensor_id is None:
            return jsonify({"status": "error", "message": "Missing sensor_id"}), 400
        
        # Запись в БД
        session = Session()
        try:
            db_record = SensorReading(
                timestamp=timestamp,
                sensor_id=int(sensor_id),
                temperature=float(data.get('temperature')) if data.get('temperature') is not None else None,
                humidity=float(data.get('humidity')) if data.get('humidity') is not None else None,
                voltage=float(data.get('voltage')) if data.get('voltage') is not None else None,
                source_ip=source_ip
            )
            session.add(db_record)
            session.commit()
            record_id = db_record.id
            print(f"💾 Записано в БД: ID={record_id}")
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()
        
        data_with_ip = {**data, "source_ip": source_ip, "destination_ip": destination_ip}
        print(data_with_ip)
        threading.Thread(target=forward_data, args=(data_with_ip,), daemon=True).start()
        
        return jsonify({
            "status": "ok",
            "id": record_id,
            "timestamp": timestamp.isoformat(),
            "sensor_id": sensor_id
        }), 200
        
    except ValueError as e:
        print(f"❌ Ошибка валидации: {e}")
        return jsonify({"status": "error", "message": f"Invalid data type: {str(e)}"}), 400
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Проверка работоспособности"""
    try:
        session = Session()
        session.execute("SELECT 1")
        session.close()
        return jsonify({
            "status": "healthy",
            "db": f"{DB_HOST}:{DB_PORT}/{DB_NAME}",
            "forward_url": FORWARD_URL if FORWARD_URL else "disabled"
        }), 200
    except Exception as e:
        return jsonify({"status": "unhealthy", "error": str(e)}), 500

@app.route('/stats', methods=['GET'])
def stats():
    """Статистика по датчикам"""
    try:
        session = Session()
        result = session.execute("""
            SELECT 
                sensor_id,
                COUNT(*) as readings_count,
                ROUND(AVG(temperature), 2) as avg_temp,
                ROUND(AVG(humidity), 2) as avg_humidity,
                ROUND(AVG(voltage), 2) as avg_voltage,
                MAX(timestamp) as last_reading
            FROM sensor_readings
            GROUP BY sensor_id
            ORDER BY sensor_id
        """)
        stats_data = []
        for row in result:
            stats_data.append({
                "sensor_id": row[0],
                "readings_count": row[1],
                "avg_temperature": row[2],
                "avg_humidity": row[3],
                "avg_voltage": row[4],
                "last_reading": row[5].isoformat() if row[5] else None
            })
        session.close()
        
        return jsonify(stats_data), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    print(f"🚀 Запуск сервера на {APP_HOST}:{APP_PORT}")
    print(f"🗄️  База данных: {DB_HOST}:{DB_PORT}/{DB_NAME}")
    print(f"📤 Пересылка: {FORWARD_URL if FORWARD_URL else 'отключена'}")
    print(f"🐛 Debug: {DEBUG}")
    
    app.run(host=APP_HOST, port=APP_PORT, threaded=True, debug=DEBUG)
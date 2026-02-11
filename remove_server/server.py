# server.py
from flask import Flask, request, jsonify
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Float
from sqlalchemy.orm import declarative_base, sessionmaker
import os
import time
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

app = Flask(__name__)

# Настройки из переменных окружения
DB_HOST = os.getenv('DB_HOST', 'db')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_NAME = os.getenv('DB_NAME', 'sensor_data')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'postgres')

APP_HOST = os.getenv('APP_HOST', '0.0.0.0')
APP_PORT = int(os.getenv('APP_PORT', '5000'))
DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'

# Строка подключения к БД
DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

def wait_for_db(max_retries=15, delay=2):
    """Ожидание готовности БД перед запуском приложения"""
    from sqlalchemy import create_engine
    from sqlalchemy.exc import OperationalError
    
    engine = create_engine(DATABASE_URL)
    for i in range(max_retries):
        try:
            with engine.connect() as conn:
                conn.execute("SELECT 1")
            print(f"✅ База данных готова после {i+1} попыток")
            engine.dispose()
            return True
        except OperationalError as e:
            print(f"⏳ Ожидание БД ({i+1}/{max_retries})... {str(e)[:80]}")
            time.sleep(delay)
    raise Exception("❌ Не удалось подключиться к БД после нескольких попыток")

# Ждём готовности БД
wait_for_db()

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

@app.route('/data', methods=['POST'])
def receive_data():
    """Приём данных от датчиков"""
    try:
        data = request.get_json()
        timestamp = datetime.now()
        ip_address = request.remote_addr
        
        print(f"📡 [{timestamp}] {ip_address} -> {data}")
        
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
                ip_address=ip_address
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

@app.route('/get_data', methods=['GET'])
def get_data():
    """Получение последних 10 записей из БД"""
    try:
        limit = int(request.args.get('limit', 10))
        limit = min(limit, 100)  # Ограничение максимум 100 записей
        
        session = Session()
        result = session.query(SensorReading).order_by(
            SensorReading.timestamp.desc()
        ).limit(limit).all()
        
        data = []
        for record in result:
            data.append({
                "id": record.id,
                "timestamp": record.timestamp.isoformat(),
                "sensor_id": record.sensor_id,
                "temperature": record.temperature,
                "humidity": record.humidity,
                "voltage": record.voltage,
                "ip_address": record.ip_address
            })
        
        session.close()
        
        return jsonify({
            "status": "ok",
            "count": len(data),
            "data": data
        }), 200
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/get_data/<int:sensor_id>', methods=['GET'])
def get_data_by_sensor(sensor_id):
    """Получение последних 10 записей конкретного датчика"""
    try:
        limit = int(request.args.get('limit', 10))
        limit = min(limit, 100)
        
        session = Session()
        result = session.query(SensorReading).filter(
            SensorReading.sensor_id == sensor_id
        ).order_by(
            SensorReading.timestamp.desc()
        ).limit(limit).all()
        
        data = []
        for record in result:
            data.append({
                "id": record.id,
                "timestamp": record.timestamp.isoformat(),
                "sensor_id": record.sensor_id,
                "temperature": record.temperature,
                "humidity": record.humidity,
                "voltage": record.voltage,
                "ip_address": record.ip_address
            })
        
        session.close()
        
        return jsonify({
            "status": "ok",
            "sensor_id": sensor_id,
            "count": len(data),
            "data": data
        }), 200
        
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
            "timestamp": datetime.now().isoformat()
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
    print(f"📊 Эндпоинты:")
    print(f"   POST /data - приём данных")
    print(f"   GET  /get_data - последние 10 записей")
    print(f"   GET  /get_data/<sensor_id> - данные по датчику")
    print(f"   GET  /health - проверка работоспособности")
    print(f"   GET  /stats - статистика")
    
    app.run(host=APP_HOST, port=APP_PORT, threaded=True, debug=DEBUG)
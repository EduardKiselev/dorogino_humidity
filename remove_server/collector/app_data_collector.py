# server.py
from flask import Flask, request, jsonify
from datetime import datetime, timezone, timedelta
from sqlalchemy import text,create_engine, Column, Integer, String, DateTime, Float, UniqueConstraint
from sqlalchemy.dialects.postgresql import insert
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

# Инициализация БД
engine = create_engine(DATABASE_URL, pool_size=5, max_overflow=10)
Base = declarative_base()

class SensorReading(Base):
    __tablename__ = 'sensor_readings'

    __table_args__ = (
        UniqueConstraint('timestamp', 'sensor_id', name='uq_sensor_time'),
    )
    
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, nullable=False)
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
        nsk_tz = timezone(timedelta(hours=7))
        data = request.get_json()
        timestamp = datetime.now(nsk_tz).replace(tzinfo=None)
        ip_address = data.get('ip_address')
        
        print(f"REMOTE SERVER COLLECTOR: [{timestamp}] from sensor ip {ip_address} -> {data}")
        
        # Валидация данных
        if not isinstance(data, dict):
            return jsonify({"status": "error", "message": "Invalid JSON format"}), 400
        
        sensor_id = data.get('sensor_id')
        if sensor_id is None:
            return jsonify({"status": "error", "message": "Missing sensor_id"}), 400
        
        values = {
            "timestamp": timestamp,
            "sensor_id": int(sensor_id),
            "temperature": float(data.get('temperature')) if data.get('temperature') is not None else None,
            "humidity": float(data.get('humidity')) if data.get('humidity') is not None else None,
            "voltage": float(data.get('voltage')) if data.get('voltage') is not None else None,
            "ip_address": ip_address
        }

        stmt = insert(SensorReading).values(**values)
        stmt = stmt.on_conflict_do_nothing(index_elements=['timestamp', 'sensor_id']).returning(SensorReading.id)
        
        # Запись в БД
        session = Session()
        try:
            result = session.execute(stmt)
            fetched = result.fetchone()  # ← Забираем ID сразу
            session.commit()
            
            if fetched is not None:
                record_id = fetched[0]             
            else:
                # Дубликат: находим существующий ID
                existing = session.execute(
                    text("SELECT id FROM sensor_readings WHERE timestamp = :ts AND sensor_id = :sid"),
                    {"ts": timestamp, "sid": sensor_id}
                ).fetchone()
                record_id = existing[0] if existing else None
        except Exception as e:
            session.rollback()
            print(f"❌ DB Error: {e}")
            return jsonify({"status": "error", "message": str(e)}), 500
        finally:
            session.close()
        
        return jsonify({
            "status": "ok",
            "id": record_id,
            "timestamp": timestamp.isoformat(),
            "sensor_id": sensor_id,
            "inserted": fetched is not None
        }), 200
        
    except ValueError as e:
        print(f"❌ Ошибка валидации: {e}")
        return jsonify({"status": "error", "message": f"Invalid data type: {str(e)}"}), 400
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
    """Health check endpoint"""
    try:
        session = Session()
        session.execute(text("SELECT 1"))
        session.close()
        return jsonify({"status": "healthy", "database": "connected"}), 200
    except Exception as e:
        return jsonify({"status": "unhealthy", "error": str(e)}), 500

@app.route('/stats', methods=['GET'])
def stats():
    """Статистика по датчикам"""
    try:
        session = Session()
        result = session.execute(text("""
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
        """))
        
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


@app.route('/settings/<int:sensor_id>/<int:hour>', methods=['GET'])
def get_settings_for_hour(sensor_id, hour):
    """Get settings for a specific sensor at a specific hour"""
    try:
        if hour < 0 or hour > 23:
            return jsonify({"status": "error", "message": "Hour must be between 0 and 23"}), 400

        session = Session()
        result = session.execute(text("""
            SELECT humidity, histeresys_up, histeresys_down
            FROM settings
            WHERE sensor_id = :sensor_id AND hour_of_day = :hour
            ORDER BY timestamp DESC
            LIMIT 1
        """), {"sensor_id": sensor_id, "hour": hour})
        
        row = result.fetchone()
        
        if not row:
            session.close()
            return jsonify({"status": "error", "message": "No settings found for this sensor and hour"}), 404
        
        settings = {
            "sensor_id": sensor_id,
            "hour": hour,
            "humidity": row[0],
            "histeresys_up": row[1],
            "histeresys_down": row[2]
        }
        
        session.close()
        
        return jsonify(settings), 200
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
    print(f"   GET  /settings/<sensor_id>/<hour> - настройки для датчика по часам")
    
    app.run(host=APP_HOST, port=APP_PORT, threaded=True, debug=DEBUG)
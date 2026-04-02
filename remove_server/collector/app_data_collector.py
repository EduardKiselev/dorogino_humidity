# server.py
from flask import Flask, request, jsonify
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo  # Python 3.9+ (или pip install backports.zoneinfo)
from sqlalchemy import text, create_engine, Column, Integer, String, DateTime, Float, UniqueConstraint
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import declarative_base, sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Настройки БД
DB_HOST = os.getenv('DB_HOST', 'db')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_NAME = os.getenv('DB_NAME', 'sensor_data')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'postgres')

APP_HOST = os.getenv('APP_HOST', '0.0.0.0')
APP_PORT = int(os.getenv('APP_PORT', '5000'))
DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

engine = create_engine(DATABASE_URL, pool_size=5, max_overflow=10)
Base = declarative_base()

class SensorReading(Base):
    __tablename__ = 'sensor_readings'
    __table_args__ = (UniqueConstraint('timestamp', 'sensor_id', name='uq_sensor_time'),)
    
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime(timezone=True), nullable=False)  # <-- timezone=True для aware-дат
    sensor_id = Column(Integer, nullable=False)
    temperature = Column(Float)
    humidity = Column(Float)
    source_ip = Column(String(50))
    destination_ip = Column(String(50))
    puid = Column(String(20))

Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===

def parse_iso_to_utc(time_str: str, default_tz_offset: int = 7) -> datetime:
    """
    Парсит ISO-строку и возвращает datetime в UTC.
    Если строка без таймзоны — использует default_tz_offset как предположение.
    """
    dt = datetime.fromisoformat(time_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone(timedelta(hours=default_tz_offset)))
    return dt.astimezone(timezone.utc)

def utc_to_gmt7(utc_dt: datetime) -> datetime:
    """Конвертирует UTC-время в GMT+7 для отображения"""
    if utc_dt.tzinfo is None:
        utc_dt = utc_dt.replace(tzinfo=timezone.utc)
    return utc_dt.astimezone(timezone(timedelta(hours=7)))

# === ЭНДПОИНТЫ ===

@app.route('/data', methods=['POST'])
def receive_data():
    """Приём данных от датчиков — время сохраняется в UTC"""
    try:
        data = request.get_json()
        if not isinstance(data, dict):
            return jsonify({"status": "error", "message": "Invalid JSON format"}), 400
        
        # Обработка времени: либо от датчика, либо текущее UTC
        if 'timestamp' in data and data['timestamp']:
            # Парсим время от датчика и конвертируем в UTC
            timestamp_utc = parse_iso_to_utc(data['timestamp'])
        else:
            # Генерируем текущее время в UTC
            timestamp_utc = datetime.now(timezone.utc)
        
        # Для логирования — конвертируем в локальное время
        timestamp_local = utc_to_gmt7(timestamp_utc)
        ip_address = data.get('destination_ip')
        puid = str(data.get('puid'))
        
        print(f"[{timestamp_local}] from sensor ip {ip_address} -> {data}")
        
        sensor_id = data.get('sensor_id')
        if sensor_id is None:
            return jsonify({"status": "error", "message": "Missing sensor_id"}), 400
        
        values = {
            "timestamp": timestamp_utc,  # <-- Сохраняем в UTC (aware)
            "sensor_id": int(sensor_id),
            "temperature": float(data['temperature']) if data.get('temperature') is not None else None,
            "humidity": float(data['humidity']) if data.get('humidity') is not None else None,
            "source_ip": str(data.get('source_ip')) if data.get('source_ip') is not None else None,
            "destination_ip": str(data.get('destination_ip')) if data.get('destination_ip') is not None else None,
            "puid": puid if data.get('puid') is not None else None
        }

        stmt = insert(SensorReading).values(**values)
        stmt = stmt.on_conflict_do_nothing(index_elements=['puid']).returning(SensorReading.id)
        
        session = Session()
        try:
            result = session.execute(stmt)
            fetched = result.fetchone()
            session.commit()
            
            record_id = fetched[0] if fetched else None
            if record_id is None:
                existing = session.execute(
                    text("SELECT id FROM sensor_readings WHERE puid = :puid"),
                    {"puid": puid}
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
            "puid": puid,
            "id": record_id,
            "timestamp_utc": timestamp_utc.isoformat(),  # <-- Возвращаем UTC
            "timestamp_local": timestamp_local.isoformat(),  # <-- И локальное для удобства
            "sensor_id": sensor_id,
            "inserted": fetched is not None
        }), 200
        
    except ValueError as e:
        print(f"❌ Ошибка валидации: {e}")
        return jsonify({"status": "error", "message": f"Invalid data type: {str(e)}"}), 400
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/sensor-readings-by-time', methods=['GET'])
def get_sensor_readings_by_time():
    """
    Возвращает данные сенсоров на момент времени.
    Принимает время с таймзоной (например, +07:00), конвертирует в UTC для поиска.
    """
    try:
        time_str = request.args.get('time')
        if not time_str:
            return jsonify({"status": "error", "message": "Missing 'time' parameter"}), 400
        
        # Конвертируем входное время в UTC для запроса к БД
        query_time_utc = parse_iso_to_utc(time_str)
        
        # Допуск ±30 секунд для поиска (так как точность до миллисекунд)
        time_window = timedelta(seconds=30)
        
        session = Session()
        result = session.execute(text("""
            SELECT sensor_id, temperature, humidity, source_ip, destination_ip, puid, timestamp
            FROM sensor_readings
            WHERE timestamp >= :start_time AND timestamp <= :end_time
            ORDER BY sensor_id
        """), {
            "start_time": query_time_utc - time_window,
            "end_time": query_time_utc + time_window
        })
        
        sensors = []
        for row in result:
            # Конвертируем время из БД (UTC) в GMT+7 для фронтенда
            ts_local = utc_to_gmt7(row[6]) if row[6] else None
            
            sensors.append({
                "sensor_id": row[0],
                "temperature": row[1],
                "humidity": row[2],
                "source_ip": row[3],
                "destination_ip": row[4],
                "puid": row[5],
                "timestamp_utc": row[6].isoformat() if row[6] else None,
                "timestamp_local": ts_local.isoformat() if ts_local else None,
                # Позиции для отображения на схеме (заглушки — подставьте свои координаты)
                "x": 10 + row[0] * 5,  # пример расчёта
                "y": 20 + row[0] * 3,
                "description": f"Sensor {row[0]}"
            })
        
        session.close()
        
        return jsonify({
            "status": "ok",
            "query_time_utc": query_time_utc.isoformat(),
            "query_time_local": utc_to_gmt7(query_time_utc).isoformat(),
            "count": len(sensors),
            "sensors": sensors
        }), 200
        
    except Exception as e:
        print(f"❌ Error fetching readings: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/health', methods=['GET'])
def health_check():
    try:
        session = Session()
        session.execute(text("SELECT 1"))
        session.close()
        return jsonify({"status": "healthy", "database": "connected"}), 200
    except Exception as e:
        return jsonify({"status": "unhealthy", "error": str(e)}), 500


@app.route('/settings/<int:sensor_id>/<int:hour>', methods=['GET'])
def get_settings_for_hour(sensor_id, hour):
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
        session.close()
        
        if not row:
            return jsonify({"status": "error", "message": "No settings found"}), 404
        
        return jsonify({
            "sensor_id": sensor_id,
            "hour": hour,
            "humidity": row[0],
            "histeresys_up": row[1],
            "histeresys_down": row[2]
        }), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == '__main__':
    print(f"🚀 Запуск сервера на {APP_HOST}:{APP_PORT}")
    print(f"🗄️  База данных: {DB_HOST}:{DB_PORT}/{DB_NAME} (время хранится в UTC)")
    print(f"📊 Эндпоинты:")
    print(f"   POST /data - приём данных (время → UTC)")
    print(f"   GET  /api/sensor-readings-by-time?time=... - запрос по времени (принимает +07:00)")
    print(f"   GET  /health - проверка работоспособности")
    print(f"   GET  /settings/<sensor_id>/<hour> - настройки")
    
    app.run(host=APP_HOST, port=APP_PORT, threaded=True, debug=DEBUG)
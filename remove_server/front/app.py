# app.py
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory, abort, jsonify
from config import Config
from models import db, SensorReading, Setting, SettingChangeLog, ControllerStatus, ScreenRecord, SensorLocation
from datetime import datetime, timezone, timedelta
import pandas as pd
from zoneinfo import ZoneInfo
from apscheduler.schedulers.background import BackgroundScheduler
import requests
from threading import Lock
import subprocess
import json
import os

# Global scheduler instance
scheduler = None
scheduler_lock = Lock()

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

SCREEN_DIR = os.getenv('SCREEN_DIR', '/root/screen')

target_tz = ZoneInfo("Asia/Novosibirsk")

# === Вспомогательные функции ===

def admin_required(f):
    """Декоратор для проверки прав администратора"""
    from functools import wraps
    
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_admin'):
            flash('Требуется доступ администратора', 'warning')
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def log_setting_change(sensor_id, hour_of_day, humidity, histeresys_up, histeresys_down):
    """Записывает изменение настроек в лог"""
    log_entry = SettingChangeLog(
        sensor_id=sensor_id,
        hour_of_day=hour_of_day,
        humidity=humidity,
        histeresys_up=histeresys_up,
        histeresys_down=histeresys_down,
        timestamp=datetime.now(target_tz)
    )
    db.session.add(log_entry)

def ping_host(host):
    """Проверяет доступность хоста с помощью запроса к /health эндпоинту"""
    import requests
    try:
        # Use HTTP GET request to check the /health endpoint on port 5000
        response = requests.get(f"http://{host}:5000/health", timeout=1)
        print(response.status_code)
        return response.status_code == 200
    except Exception:
        return False

def get_sensor_status():
    """Определяет статусы датчиков на основе времени последнего сигнала"""
    now = datetime.now(target_tz)
    five_minutes_ago = now - timedelta(minutes=5)
    one_hour_ago = now - timedelta(hours=1)
    
    # Get the latest reading for each sensor
    subquery = db.session.query(
        SensorReading.sensor_id,
        db.func.max(SensorReading.timestamp).label('max_time')
    ).group_by(SensorReading.sensor_id).subquery()
    
    latest_readings = db.session.query(
        subquery.c.sensor_id,
        subquery.c.max_time
    ).all()
    print(latest_readings)
    sensors_status = {}
    for sensor_id, last_timestamp in latest_readings:
        # Make sure last_timestamp is timezone-aware for comparison
        if last_timestamp.tzinfo is None:
            last_timestamp = last_timestamp.replace(tzinfo=target_tz)
        
        if last_timestamp >= five_minutes_ago:
            status = 'active'  # green
        elif last_timestamp >= one_hour_ago:
            status = 'warning'  # yellow
        else:
            status = 'error'  # red
        
        sensors_status[sensor_id] = {
            'sensor_id': sensor_id,
            'status': status,
            'last_seen': last_timestamp
        }
    
    return sensors_status

# === Роуты ===

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Страница входа для администратора"""
    if request.method == 'POST':
        password = request.form.get('password')
        
        if password == app.config['ADMIN_PASSWORD']:
            session['is_admin'] = True
            flash('Добро пожаловать, администратор!', 'success')
            return redirect(request.args.get('next') or url_for('index'))
        else:
            flash('Неверный пароль', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Выход из режима администратора"""
    session.clear()
    flash('Вы вышли из режима администратора', 'info')
    return redirect(url_for('index'))

@app.route('/')
def index():
    """Главная страница - последние 100 значений"""
    readings = db.session.query(SensorReading).order_by(
        SensorReading.timestamp.desc()
    ).limit(100).all()
    
    for reading in readings:
        if reading.timestamp.tzinfo is None:
            reading.timestamp = reading.timestamp.replace(tzinfo=timezone.utc)

    
    return render_template(
        'index.html', 
        readings=readings, 
        is_admin=session.get('is_admin')
    )

@app.route('/kiln-stats')
def kiln_stats():
    # Даты из запроса
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    
    # Значения по умолчанию: последние 24 часа
    now = datetime.now(target_tz)
    if not date_from and not date_to:
        date_to_dt = now
        date_from_dt = now - timedelta(hours=24)
    else:
        # Парсинг с учётом таймзоны
        date_from_dt = None
        date_to_dt = None
        if date_from:
            date_from_dt = datetime.fromisoformat(date_from)
            if date_from_dt.tzinfo is None:
                date_from_dt = date_from_dt.replace(tzinfo=target_tz)
        if date_to:
            date_to_dt = datetime.fromisoformat(date_to)
            if date_to_dt.tzinfo is None:
                date_to_dt = date_to_dt.replace(tzinfo=target_tz)
    
    query = ScreenRecord.query
    if date_from_dt:
        query = query.filter(ScreenRecord.screen_date >= date_from_dt)
    if date_to_dt:
        query = query.filter(ScreenRecord.screen_date <= date_to_dt)
    
    rows = query.order_by(ScreenRecord.screen_date.desc()).limit(500).all()
    records = []
    for row in rows:
        try:
            data_list = json.loads(row.data_json) if row.data_json else []
        except (json.JSONDecodeError, TypeError):
            data_list = []
        records.append({
            "filename": row.filename,
            "screen_date": row.screen_date,
            "data_list": data_list
        })
    print(records)
    return render_template(
        'kiln_stats.html',
        records=records,
        date_from=date_from or (date_from_dt.strftime('%Y-%m-%dT%H:%M') if date_from_dt else ''),
        date_to=date_to or (date_to_dt.strftime('%Y-%m-%dT%H:%M') if date_to_dt else ''),
        is_admin=session.get('is_admin')  # ← важно для base.html
    )

@app.route('/screens/<path:filename>')
def serve_screen(filename):
    """Безопасная отдача скриншотов только из разрешённой папки"""
    # Защита от path traversal
    if '..' in filename or filename.startswith('/'):
        abort(403)
    # Разрешаем только .png
    if not filename.lower().endswith('.png'):
        abort(403)
    # Проверяем, что файл существует
    if not os.path.isfile(os.path.join(SCREEN_DIR, filename)):
        abort(404)
    return send_from_directory(SCREEN_DIR, filename)

@app.route('/charts')
def charts():
    """Страница графиков"""
    now = datetime.now()
    
    # Получаем все данные за разные периоды
    now = datetime.now()
    day_ago = now - timedelta(days=1)
    two_day_before = day_ago - timedelta(days=1)
    week_ago = now - timedelta(days=7)
    prev_week_start = week_ago - timedelta(days=7)
    prev_week_end = week_ago
    month_ago = now - timedelta(days=30)
    year_ago = now - timedelta(days=365)


    
    # Запросы для каждого периода
    day_readings = SensorReading.query.filter(
        SensorReading.timestamp >= day_ago
    ).order_by(SensorReading.timestamp).all()

    prev_day_readings = SensorReading.query.filter(
        SensorReading.timestamp >= two_day_before,
        SensorReading.timestamp < day_ago
    ).order_by(SensorReading.timestamp).all()

    week_readings = SensorReading.query.filter(
    SensorReading.timestamp >= week_ago
    ).order_by(SensorReading.timestamp).all()

    prev_week_readings = SensorReading.query.filter(
        SensorReading.timestamp >= prev_week_start,
        SensorReading.timestamp < prev_week_end
    ).order_by(SensorReading.timestamp).all()
    
    month_readings = SensorReading.query.filter(
        SensorReading.timestamp >= month_ago
    ).order_by(SensorReading.timestamp).all()
    
    year_readings = SensorReading.query.filter(
        SensorReading.timestamp >= year_ago
    ).order_by(SensorReading.timestamp).all()
    
    # Преобразуем в словари
    day_data = [{
        'id': r.id,
        'sensor_id': int(r.sensor_id),
        'temperature': float(r.temperature),
        'humidity': float(r.humidity),
        'timestamp': r.timestamp.isoformat()
    } for r in day_readings]

    two_day_before_data = [{
        'id': r.id,
        'sensor_id': int(r.sensor_id),
        'temperature': float(r.temperature),
        'humidity': float(r.humidity),
        'timestamp': r.timestamp.isoformat()
    } for r in prev_day_readings]

    week_data = [{'id': r.id, 'sensor_id': int(r.sensor_id), 'temperature': float(r.temperature), 
              'humidity': float(r.humidity), 'timestamp': r.timestamp.isoformat()} for r in week_readings]

    prev_week_data = [{'id': r.id, 'sensor_id': int(r.sensor_id), 'temperature': float(r.temperature), 
                    'humidity': float(r.humidity), 'timestamp': r.timestamp.isoformat()} for r in prev_week_readings]

    
    month_data = [{
        'id': r.id,
        'sensor_id': int(r.sensor_id),
        'temperature': float(r.temperature),
        'humidity': float(r.humidity),
        'timestamp': r.timestamp.isoformat()
    } for r in month_readings]
    
    year_data = [{
        'id': r.id,
        'sensor_id': int(r.sensor_id),
        'temperature': float(r.temperature),
        'humidity': float(r.humidity),
        'timestamp': r.timestamp.isoformat()
    } for r in year_readings]
    
    # Получаем уникальные ID сенсоров
    sensor_ids = sorted(list(set(r['sensor_id'] for r in day_data + month_data + year_data)))
    
    return render_template(
        'charts.html',
        day_data=day_data,
        two_day_before=two_day_before_data,
        week_data=week_data,      
        prev_week_data=prev_week_data,    
        month_data=month_data,
        year_data=year_data,
        sensor_ids=sensor_ids,
        is_admin=session.get('is_admin')
    )

@app.route('/monitoring')
def monitoring():
    """Страница мониторинга состояния датчиков и серверов"""
    # Получаем статусы датчиков
    sensors_status = get_sensor_status()
    
    # Проверяем статус серверов
    server_10_2_status = ping_host('10.0.10.2')
    server_10_20_status = ping_host('10.0.10.20')
    
    servers_status = {
        '10.0.10.2': server_10_2_status,
        '10.0.10.20': server_10_20_status
    }
    
    return render_template(
        'monitoring.html',
        sensors_status=sensors_status,
        servers_status=servers_status,
        is_admin=session.get('is_admin')
    )

# Add these new routes to your app.py file

@app.route('/workshop-diagram')
def workshop_diagram():
    """Page showing workshop diagram with sensor positions and time slider"""
    # Get only active sensor locations
    sensor_locations = SensorLocation.query.filter_by(active=True).all()
    
    # Get the most recent readings for each active sensor
    # Extract active sensor IDs
    active_sensor_ids = [location.sensor_id for location in sensor_locations]
    
    if active_sensor_ids:  # Only query if there are active sensors
        # Subquery to find the latest reading for each active sensor
        subquery = db.session.query(
            SensorReading.sensor_id,
            db.func.max(SensorReading.timestamp).label('max_time')
        ).filter(SensorReading.sensor_id.in_(active_sensor_ids)).group_by(SensorReading.sensor_id).subquery()
        
        latest_readings = db.session.query(SensorReading).join(
            subquery,
            (SensorReading.sensor_id == subquery.c.sensor_id) &
            (SensorReading.timestamp == subquery.c.max_time)
        ).all()
        
        # Create a dictionary mapping sensor_id to its reading
        readings_dict = {reading.sensor_id: reading for reading in latest_readings}
    else:
        readings_dict = {}
    
    # Combine sensor locations with their readings
    sensors_with_data = []
    for location in sensor_locations:
        reading = readings_dict.get(location.sensor_id)
        sensor_data = {
            'sensor_id': location.sensor_id,
            'description': location.description,
            'x': location.x_coordinate,
            'y': location.y_coordinate,
            'temperature': reading.temperature if reading else None,
            'humidity': reading.humidity if reading else None,
            'timestamp': reading.timestamp if reading else None
        }
        sensors_with_data.append(sensor_data)
    
    return render_template(
        'workshop_diagram.html',
        sensors_with_data=sensors_with_data,
        is_admin=session.get('is_admin')
    )

@app.route('/api/sensor-readings-by-time')
def api_sensor_readings_by_time():
    """API endpoint to get sensor readings at a specific time"""
    time_str = request.args.get('time')
    if not time_str:
        return jsonify({'error': 'Time parameter is required'}), 400
    
    try:
        target_time = datetime.fromisoformat(time_str)
    except ValueError:
        return jsonify({'error': 'Invalid time format'}), 400
    
    # Find the closest readings to the requested time for each sensor
    results = []
    
    for sensor_id in range(1, 6):  # Assuming sensors 1-5
        # Find the reading closest to the target time for this sensor
        closest_reading = db.session.query(SensorReading).filter(
            SensorReading.sensor_id == sensor_id
        ).order_by(
            db.func.abs(db.func.extract('epoch', SensorReading.timestamp - target_time))
        ).first()
        
        if closest_reading:
            location = SensorLocation.query.filter_by(sensor_id=sensor_id).first()
            if location:
                results.append({
                    'sensor_id': sensor_id,
                    'temperature': closest_reading.temperature,
                    'humidity': closest_reading.humidity,
                    'timestamp': closest_reading.timestamp.isoformat(),
                    'x': location.x_coordinate,
                    'y': location.y_coordinate,
                    'description': location.description
                })
    
    return jsonify(results)

@app.route('/admin/sensor-locations', methods=['GET', 'POST'])
@admin_required
def manage_sensor_locations():
    """Admin page to manage sensor locations on the diagram"""
    if request.method == 'POST':
        try:
            for i in range(1, 6):  # For sensors 1-5
                description = request.form.get(f'description_{i}')
                x_coord = request.form.get(f'x_{i}')
                y_coord = request.form.get(f'y_{i}')
                # Fix: Check if checkbox is present in form data (meaning checked) or not
                active_status = f'active_{i}' in request.form
                
                if description and x_coord and y_coord:
                    try:
                        x = float(x_coord)
                        y = float(y_coord)
                        
                        # Check if location already exists
                        location = SensorLocation.query.filter_by(sensor_id=i).first()
                        if location:
                            # Update existing location
                            location.description = description
                            location.x_coordinate = x
                            location.y_coordinate = y
                            # Update active status based on presence in form data
                            location.active = active_status
                        else:
                            # Create new location
                            location = SensorLocation(
                                sensor_id=i,
                                description=description,
                                x_coordinate=x,
                                y_coordinate=y,
                                active=active_status
                            )
                            db.session.add(location)
                    except ValueError:
                        flash(f'Invalid coordinates for sensor {i}', 'danger')
                        continue
            
            db.session.commit()
            flash('Sensor locations updated successfully!', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating sensor locations: {str(e)}', 'danger')
    
    # Load existing locations
    sensor_locations = {}
    for i in range(1, 6):
        location = SensorLocation.query.filter_by(sensor_id=i).first()
        if location:
            sensor_locations[i] = {
                'description': location.description,
                'x': location.x_coordinate,
                'y': location.y_coordinate,
                'active': location.active
            }
        else:
            sensor_locations[i] = {
                'description': f'Sensor {i} location description',
                'x': 0.0,
                'y': 0.0,
                'active': True
            }
    
    return render_template('admin/sensor_locations.html', sensor_locations=sensor_locations)

@app.route('/settings', methods=['GET', 'POST'])
@admin_required
def settings():
    """Страница настроек (только для админа) - теперь для 5 датчиков с почасовой настройкой влажности"""
    if request.method == 'POST':
        try:
            for sensor_id in range(1, 6):
                # Получаем гистерезис из формы (одинаковый для всех часов)
                histeresys_up = float(request.form.get(f'histeresys_up_sensor_{sensor_id}'))
                histeresys_down = float(request.form.get(f'histeresys_down_sensor_{sensor_id}'))
                
                if not (0 <= histeresys_up <= 20):
                    raise ValueError(f'Верхний гистерезис для датчика {sensor_id} должен быть от 0 до 20%')
                if not (0 <= histeresys_down <= 20):
                    raise ValueError(f'Нижний гистерезис для датчика {sensor_id} должен быть от 0 до 20%')
                
                # Обновляем настройки для всех 24 часов
                for hour in range(24):
                    humidity = float(request.form.get(f'humidity_sensor_{sensor_id}_hour_{hour}'))
                    
                    if not (0 <= humidity <= 100):
                        raise ValueError(f'Порог влажности для датчика {sensor_id}, час {hour} должен быть от 0 до 100%')
                    
                    # Получаем текущую настройку для этого датчика и часа
                    current_setting = Setting.query.filter_by(
                        sensor_id=sensor_id, 
                        hour_of_day=hour
                    ).order_by(Setting.timestamp.desc()).first()
                    
                    # Логируем изменения, если они есть
                    if current_setting:
                        if (current_setting.humidity != humidity or 
                            current_setting.histeresys_up != histeresys_up or 
                            current_setting.histeresys_down != histeresys_down):
                            log_setting_change(
                                sensor_id, 
                                hour,
                                humidity, 
                                histeresys_up, 
                                histeresys_down
                            )
                            # Обновляем существующую настройку
                            current_setting.humidity = humidity
                            current_setting.histeresys_up = histeresys_up
                            current_setting.histeresys_down = histeresys_down
                            current_setting.timestamp = datetime.now(timezone.utc)
                    else:
                        # Используем UPSERT для обработки возможного конфликта уникальности
                        stmt = db.insert(Setting).values(
                            sensor_id=sensor_id,
                            hour_of_day=hour,
                            humidity=humidity,
                            histeresys_up=histeresys_up,
                            histeresys_down=histeresys_down,
                            timestamp=datetime.now(timezone.utc)
                        )
                        stmt = stmt.on_conflict_do_update(
                            index_elements=['sensor_id', 'hour_of_day'],
                            set_=dict(
                                humidity=stmt.excluded.humidity,
                                histeresys_up=stmt.excluded.histeresys_up,
                                histeresys_down=stmt.excluded.histeresys_down,
                                timestamp=stmt.excluded.timestamp
                            )
                        )
                        db.session.execute(stmt)
            
            db.session.commit()
            flash('Настройки для всех датчиков и часов успешно сохранены!', 'success')
        except (ValueError, TypeError) as e:
            db.session.rollback()
            flash(f'Ошибка: {str(e)}', 'danger')
    
    # Получаем настройки для всех 5 датчиков и всех 24 часов
    sensor_settings = {}
    for sensor_id in range(1, 6):
        # Получаем все настройки для данного датчика
        settings_for_sensor = Setting.query.filter_by(sensor_id=sensor_id).order_by(Setting.hour_of_day).all()
        
        # Если настроек нет, создаем с дефолтными значениями
        if not settings_for_sensor:
            for hour in range(24):
                default_setting = Setting(
                    sensor_id=sensor_id,
                    hour_of_day=hour,
                    humidity=60.0,
                    histeresys_up=5.0,
                    histeresys_down=5.0
                )
                db.session.add(default_setting)
            db.session.commit()
            settings_for_sensor = Setting.query.filter_by(sensor_id=sensor_id).order_by(Setting.hour_of_day).all()
        
        sensor_settings[sensor_id] = settings_for_sensor
    
    return render_template('settings.html', sensor_settings=sensor_settings)


def control_humidifier_job():
    """
    Cron job function that checks sensor data and controls humidifiers
    Runs every minute to check sensor data from last 15 minutes
    """
    print("🚀 Запуск функции контроля влажности")
    with app.app_context():  # Ensure we have an application context
        try:
            # Calculate time threshold (15 minutes ago)
            fifteen_minutes_ago = datetime.now(timezone.utc) - timedelta(minutes=15)
            
            # Get the most recent reading for each sensor in the last 15 minutes
            subquery = db.session.query(
                SensorReading.sensor_id,
                db.func.max(SensorReading.timestamp).label('max_time')
            ).filter(
                SensorReading.timestamp >= fifteen_minutes_ago
            ).group_by(SensorReading.sensor_id).subquery()
            
            latest_readings = db.session.query(SensorReading).join(
                subquery,
                (SensorReading.sensor_id == subquery.c.sensor_id) &
                (SensorReading.timestamp == subquery.c.max_time)
            ).all()
            
            # Process each sensor's data
            for reading in latest_readings:
                sensor_id = reading.sensor_id
                current_humidity = reading.humidity
                print(f"CRON JOB: Sensor ID: {sensor_id}, Current Humidity: {current_humidity}")
                # Get the setting for this sensor and current hour
                current_hour = reading.timestamp.hour
                setting = Setting.query.filter_by(
                    sensor_id=sensor_id,
                    hour_of_day=current_hour
                ).first()
                
                if not setting:
                    print(f"No setting found for sensor {sensor_id} at hour {current_hour}")
                    continue
                
                # Determine if humidifier should be ON or OFF
                target_humidity = setting.humidity
                hysteresis_up = setting.histeresys_up
                hysteresis_down = setting.histeresys_down
                
                # Get current controller status
                controller_status = ControllerStatus.query.filter_by(controller_id=sensor_id).first()
                
                # Determine new status based on current humidity and settings
                new_status = None
                if controller_status:
                    current_status = controller_status.status
                    current_status = str(current_status)
                    new_status = current_status
                    # Apply hysteresis logic
                    if current_status == "OFF":
                        # Turn ON if humidity is below target minus lower hysteresis
                        if current_humidity < (target_humidity - hysteresis_down):
                            new_status = "ON"
                    elif current_status == "ON":
                        # Turn OFF if humidity is above target plus upper hysteresis
                        if current_humidity > (target_humidity + hysteresis_up):
                            new_status = "OFF"
                else:
                    # If no status exists yet, set initial state based on current humidity
                    if current_humidity < (target_humidity - hysteresis_down):
                        new_status = "ON"
                    else:
                        new_status = "OFF"
                # Update controller status if changed
                if new_status:
                    if controller_status:
                        # Update existing status
                        controller_status.status = new_status
                        controller_status.last_updated = datetime.now()
                    else:
                        # Create new status record
                        controller_status = ControllerStatus(
                            controller_id=sensor_id,
                            status=new_status
                        )
                        db.session.add(controller_status)
                    
                    # Send command to controller
                    try:
                        response = requests.get(f"http://10.0.10.2:5001/{sensor_id}/{new_status}")
                        if response.status_code == 200:
                            print(f"Successfully sent {new_status} command to controller {sensor_id}")
                        else:
                            print(f"Failed to send {new_status} command to controller {sensor_id}, status: {response.status_code}")
                    except requests.exceptions.RequestException as e:
                        print(f"Error sending command to controller {sensor_id}: {e}")
            
            # Commit all changes to the database
            db.session.commit()
            print(f"Humidifier control job completed at {datetime.now(timezone.utc)}")
            
        except Exception as e:
            print(f"Error in control_humidifier_job: {e}")
            db.session.rollback()

def init_scheduler():
    """Initialize the background scheduler"""
    global scheduler
    
    with scheduler_lock:
        if scheduler is None:
            scheduler = BackgroundScheduler()
            scheduler.add_job(
                func=control_humidifier_job,
                trigger="interval",
                minutes=1,  # Run every minute
                id='humidifier_control_job',
                replace_existing=True
            )
            scheduler.start()
            print("Scheduler started for humidifier control")

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        # Инициализация настроек для 5 датчиков, если их нет
        for sensor_id in range(1, 6):
            existing = Setting.query.filter_by(sensor_id=sensor_id).first()
            if not existing:
                for hour in range(24):  # Создаем настройки для всех 24 часов
                    default_setting = Setting(
                        sensor_id=sensor_id,
                        hour_of_day=hour,
                        humidity=60.0,
                        histeresys_up=5.0,
                        histeresys_down=5.0
                    )
                    db.session.add(default_setting)
        db.session.commit()
        
        # Initialize the scheduler after db initialization
        init_scheduler()
        
    app.run(host='0.0.0.0', port=5000, debug=True)
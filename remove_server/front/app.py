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
from statistics import stdev, mean
from collections import defaultdict
from sqlalchemy.dialects.postgresql import insert

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

def calculate_absolute_humidity(T, RH, pressure_hpa=990):
    """
    Рассчитывает влажность в г/кг сухого воздуха.
    T: температура, °C
    RH: относительная влажность, %
    pressure_hpa: атмосферное давление, гПа (по умолчанию 1013.25)
    """
    import math
    if T is None or RH is None:
        return None
    try:
        e_s = 6.112 * math.exp((17.67 * T) / (T + 243.5))  # гПа
        e = e_s * RH / 100                                   # гПа
        w = 622 * e / (pressure_hpa - e)                     # г/кг
        return round(w, 2)
    except (ValueError, ZeroDivisionError, OverflowError):
        return None

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

        reading.absolute_humidity = calculate_absolute_humidity(
            reading.temperature, 
            reading.humidity
        )
    
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
    
    # Получаем все данные за разные периоды
    now = datetime.now(target_tz)

    def to_utc(dt):
        """Гарантированно конвертирует aware-datetime в UTC"""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=target_tz)
        return dt.astimezone(timezone.utc)

    now = to_utc(now) 
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
    
    sensor_ids = sorted(list(set(r['sensor_id'] for r in day_data + month_data + year_data)))
    locations = {loc.sensor_id: loc.description for loc in SensorLocation.query.all()}
    
    return render_template(
        'charts.html',
        day_data=day_data,
        two_day_before=two_day_before_data,
        week_data=week_data,      
        prev_week_data=prev_week_data,    
        month_data=month_data,
        year_data=year_data,
        sensor_ids=sensor_ids,
        sensor_locations=locations,
        is_admin=session.get('is_admin')
    )

@app.route('/flex-chart')
def flex_chart():
    """Гибкий график с фильтрами"""
    # Получаем уникальные ID датчиков
    sensor_ids = get_all_sensor_ids()
    
    locations = {loc.sensor_id: loc.description for loc in SensorLocation.query.all()}
    
    sensors_with_labels = [
        {'id': sid, 'label': f"{sid}-{locations.get(sid, 'без описания')}"}
        for sid in sensor_ids
    ]
    
    return render_template(
        'flex_chart.html', 
        sensors=sensors_with_labels,  # ← передаём новый список
        is_admin=session.get('is_admin')
    )

@app.route('/api/flex-chart-data')
def api_flex_chart_data():
    """API для данных гибкого графика"""
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    sensors = request.args.getlist('sensors', type=int)
    metrics = request.args.getlist('metrics')
    
    if not date_from or not date_to:
        return jsonify({'error': 'date_from и date_to обязательны'}), 400
    
    try:
        start = datetime.fromisoformat(date_from).replace(tzinfo=target_tz)
        end = datetime.fromisoformat(date_to).replace(tzinfo=target_tz)
    except ValueError as e:
        app.logger.error(f"Date parse error: {e}")
        return jsonify({'error': f'Неверный формат даты: {e}'}), 400
    
    query = SensorReading.query.filter(
        SensorReading.timestamp >= start,
        SensorReading.timestamp <= end
    )
    if sensors:
        query = query.filter(SensorReading.sensor_id.in_(sensors))
    
    readings = query.order_by(SensorReading.timestamp).all()
    app.logger.info(f"Found {len(readings)} readings for flex chart")
    

    
    # Группируем: (sensor_id, timestamp_без_секунд) → список значений
    aggregated = defaultdict(lambda: {'temperatures': [], 'humidities': []})
    
    for r in readings:
        ts_local = r.timestamp.astimezone(target_tz)
        ts_normalized = ts_local.replace(second=0, microsecond=0) # Обрезаем секунды: 2026-04-07T12:34:56 → 2026-04-07T12:34:00
        key = (r.sensor_id, ts_normalized)
        
        if r.temperature is not None:
            aggregated[key]['temperatures'].append(r.temperature)
        if r.humidity is not None:
            aggregated[key]['humidities'].append(r.humidity)
    
    # Формируем ответ: усредняем значения внутри минуты
    data = []
    for (sensor_id, ts), values in aggregated.items():
        point = {
            'timestamp': ts.isoformat(),
            'sensor_id': sensor_id
        }
        if 'temperature' in metrics and values['temperatures']:
            point['temperature'] = round(sum(values['temperatures']) / len(values['temperatures']), 1)
        if 'humidity' in metrics and values['humidities']:
            point['humidity'] = round(sum(values['humidities']) / len(values['humidities']), 1)
        data.append(point)
    
    # Сортируем по времени для корректного отображения
    data.sort(key=lambda x: (x['timestamp'], x['sensor_id']))
    
    app.logger.info(f"Returned {len(data)} aggregated points")
    return jsonify(data)

@app.route('/sensor-mapping')
def sensor_mapping():
    """Только просмотр: какой датчик где установлен"""
    # Все уникальные датчики из показаний
    sensor_ids = [r[0] for r in db.session.query(SensorReading.sensor_id)
                  .distinct().order_by(SensorReading.sensor_id).all()]
    
    # Описания из SensorLocation
    locations = {loc.sensor_id: loc.description for loc in SensorLocation.query.all()}
    
    sensors = [
        {'id': sid, 'desc': locations.get(sid, '⚠️ не задано')}
        for sid in sensor_ids
    ]
    
    return render_template('sensor_mapping.html', sensors=sensors, is_admin=session.get('is_admin'))
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
            'humidity_std': None,
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
        local_time = target_time.astimezone(target_tz)
    except ValueError:
        return jsonify({'error': 'Invalid time format'}), 400
    
  #  print(target_time, local_time)
    # Get all active sensor IDs from the SensorLocation table
    active_sensors = db.session.query(SensorLocation.sensor_id).filter_by(active=True).all()
    active_sensor_ids = [sensor.sensor_id for sensor in active_sensors]
    
    # Find the closest readings to the requested time for each active sensor
    results = []
    
    for sensor_id in active_sensor_ids:
        # Get readings within 15 minutes before the target time
        fifteen_minutes_before = local_time - timedelta(minutes=15)
        
        readings_in_range = db.session.query(SensorReading).filter(
            SensorReading.sensor_id == sensor_id,
            SensorReading.timestamp >= fifteen_minutes_before,
            SensorReading.timestamp <= local_time
        ).order_by(SensorReading.timestamp).all()
        
        if readings_in_range:
 #           print(readings_in_range)
            # Calculate averages for temperature and humidity
            total_temp = sum(r.temperature for r in readings_in_range if r.temperature is not None)

            humidity_values = [r.humidity for r in readings_in_range if r.humidity is not None]
            total_humidity = sum(humidity_values)
            std_humidity = stdev(humidity_values) if len(humidity_values) >= 2 else 0.0
            

            count_temp = len([r for r in readings_in_range if r.temperature is not None])
            count_humidity = len([r for r in readings_in_range if r.humidity is not None])
            
            avg_temp = total_temp / count_temp if count_temp > 0 else None
            avg_humidity = total_humidity / count_humidity if count_humidity > 0 else None
            
            # Get the most recent timestamp in the range
            latest_reading = max(readings_in_range, key=lambda x: x.timestamp)
            
            location = SensorLocation.query.filter_by(sensor_id=sensor_id).first()
            if location:
                results.append({
                    'sensor_id': sensor_id,
                    'temperature': avg_temp,
                    'humidity': avg_humidity,
                    'humidity_std': std_humidity,
                    'timestamp': latest_reading.timestamp.isoformat(),
                    'x': location.x_coordinate,
                    'y': location.y_coordinate,
                    'description': location.description
                })
    print(results)
    return jsonify(results)

@app.route('/admin/sensor-locations', methods=['GET', 'POST'])
@admin_required
def manage_sensor_locations():
    # 1. Динамически получаем ID всех датчиков, которые есть в БД
    sensor_ids = get_all_sensor_ids()
    
    if request.method == 'POST':
        try:
            for sid in sensor_ids:
                desc = request.form.get(f'description_{sid}')
                x_str = request.form.get(f'x_{sid}')
                y_str = request.form.get(f'y_{sid}')
                is_active = f'active_{sid}' in request.form
                
                if desc and x_str and y_str:
                    try:
                        x, y = float(x_str), float(y_str)
                    except ValueError:
                        flash(f'Некорректные координаты для датчика {sid}', 'danger')
                        continue
                        
                    location = SensorLocation.query.filter_by(sensor_id=sid).first()
                    if location:
                        location.description = desc
                        location.x_coordinate = x
                        location.y_coordinate = y
                        location.active = is_active
                    else:
                        db.session.add(SensorLocation(
                            sensor_id=sid, description=desc,
                            x_coordinate=x, y_coordinate=y, active=is_active
                        ))
                        
            db.session.commit()
            flash('Координаты датчиков успешно сохранены!', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка сохранения: {str(e)}', 'danger')
            
    # 2. Подготавливаем данные для формы
    existing_locs = {loc.sensor_id: loc for loc in SensorLocation.query.all()}
    sensor_locations = {}
    for sid in sensor_ids:
        loc = existing_locs.get(sid)
        sensor_locations[sid] = {
            'description': loc.description if loc else f'Датчик {sid}',
            'x': loc.x_coordinate if loc else 0.0,
            'y': loc.y_coordinate if loc else 0.0,
            'active': loc.active if loc else True
        }
        
    return render_template(
        'admin/sensor_locations.html', 
        sensor_locations=sensor_locations,
        sensor_ids=sensor_ids
    )

@app.route('/settings', methods=['GET', 'POST'])
@admin_required
def settings():
    # Динамически получаем список датчиков из БД
    sensor_ids = [r[0] for r in db.session.query(SensorReading.sensor_id).distinct().order_by(SensorReading.sensor_id).all()]
    if not sensor_ids:
        sensor_ids = list(range(1, 6))  # fallback
    
    DAYS = [(0, 'Пн'), (1, 'Вт'), (2, 'Ср'), (3, 'Чт'), (4, 'Пт'), (5, 'Сб'), (6, 'Вс')]
    
    if request.method == 'POST':
        try:
            for sensor_id in sensor_ids:
                h_up = float(request.form.get(f'histeresys_up_sensor_{sensor_id}'))
                h_down = float(request.form.get(f'histeresys_down_sensor_{sensor_id}'))
                
                for day in range(7):
                    for hour in range(24):
                        humidity = float(request.form.get(f'humidity_s{sensor_id}_d{day}_h{hour}'))
                        
                        stmt = insert(Setting).values(
                            sensor_id=sensor_id, 
                            day_of_week=day, 
                            hour_of_day=hour,
                            humidity=humidity, 
                            histeresys_up=h_up, 
                            histeresys_down=h_down,
                            timestamp=datetime.now(timezone.utc)
                        )

                        stmt = stmt.on_conflict_do_update(
                            index_elements=['sensor_id', 'day_of_week', 'hour_of_day'],
                            set_=dict(
                                humidity=stmt.excluded.humidity,
                                histeresys_up=stmt.excluded.histeresys_up,
                                histeresys_down=stmt.excluded.histeresys_down,
                                timestamp=stmt.excluded.timestamp
                            )
                        )
                        db.session.execute(stmt)
            db.session.commit()
            flash('Настройки сохранены', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка: {e}', 'danger')
    
    # Загрузка текущих настроек
    sensor_settings = {}
    for sid in sensor_ids:
        settings_list = Setting.query.filter_by(sensor_id=sid).all()
        # Структура: {day: {hour: setting}}
        sensor_settings[sid] = {d: {h: None for h in range(24)} for d in range(7)}
        for s in settings_list:
            sensor_settings[sid][s.day_of_week][s.hour_of_day] = s
    
    return render_template('settings.html', 
                          sensor_ids=sensor_ids, 
                          sensor_settings=sensor_settings,
                          days=DAYS)

def control_humidifier_job():
    """
    Cron job function that checks sensor data and controls humidifiers
    Runs every minute to check sensor data from last 15 minutes
    """
    print("🚀 Запуск функции контроля влажности")
    with app.app_context():  # Ensure we have an application context
        try:
            now = datetime.now(timezone.utc)
            current_day = now.weekday()  # 0=Пн
            current_hour = now.hour 
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
                setting = Setting.query.filter_by(
                    sensor_id=reading.sensor_id,
                    day_of_week=current_day,
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

@app.route('/static/<path:filename>')
def static_files(filename):
    """Serve static files from the static folder"""
    return send_from_directory('static', filename)

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

def get_all_sensor_ids():
    """Возвращает отсортированный список уникальных ID датчиков из БД"""
    ids = [r[0] for r in db.session.query(SensorReading.sensor_id)
           .distinct().order_by(SensorReading.sensor_id).all()]
    return ids if ids else []

if __name__ == '__main__':
    with app.app_context():
        db.create_all()

        sensor_ids = get_all_sensor_ids()

        for sensor_id in sensor_ids:
                    for day in range(7):
                        for hour in range(24):
                            existing = Setting.query.filter_by(
                                sensor_id=sensor_id,
                                day_of_week=day, 
                                hour_of_day=hour
                            ).first()
                            if not existing:
                                db.session.add(Setting(
                                    sensor_id=sensor_id,
                                    day_of_week=day,
                                    hour_of_day=hour,
                                    humidity=60.0,
                                    histeresys_up=5.0,
                                    histeresys_down=5.0,
                                    timestamp=datetime.now(timezone.utc)
                                ))
        db.session.commit()
        init_scheduler()
        
    app.run(host='0.0.0.0', port=5000, debug=True)







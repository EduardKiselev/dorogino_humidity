# app.py
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from config import Config
from models import db, SensorReading, Setting, SettingChangeLog, ControllerStatus
from datetime import datetime, timezone, timedelta
import pandas as pd
from zoneinfo import ZoneInfo
from apscheduler.schedulers.background import BackgroundScheduler
import requests
from threading import Lock

# Global scheduler instance
scheduler = None
scheduler_lock = Lock()

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

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
        timestamp=datetime.now(timezone.utc)
    )
    db.session.add(log_entry)

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

@app.route('/charts')
def charts():
    """Страница графиков"""
    now = datetime.now(timezone.utc)
    
    # Получаем все данные за разные периоды
    day_ago = now - timedelta(days=1)
    month_ago = now - timedelta(days=30)
    year_ago = now - timedelta(days=365)
    
    # Запросы для каждого периода
    day_readings = SensorReading.query.filter(
        SensorReading.timestamp >= day_ago
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

    print('day_data', day_data[1:10])
    
    # Получаем уникальные ID сенсоров
    sensor_ids = sorted(list(set(r['sensor_id'] for r in day_data + month_data + year_data)))
    
    return render_template(
        'charts.html',
        day_data=day_data,
        month_data=month_data,
        year_data=year_data,
        sensor_ids=sensor_ids,
        is_admin=session.get('is_admin')
    )

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
                            #   db.session.merge(current_setting)
                    else:
                        # Создаем новую запись с настройками
                        new_setting = Setting(
                            sensor_id=sensor_id,
                            hour_of_day=hour,
                            humidity=humidity,
                            histeresys_up=histeresys_up,
                            histeresys_down=histeresys_down
                        )
                        db.session.add(new_setting)
            
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
                if new_status and new_status != (controller_status.status if controller_status else None):
                    if controller_status:
                        # Update existing status
                        controller_status.status = new_status
                        controller_status.last_updated = datetime.now(timezone.utc)
                    else:
                        # Create new status record
                        controller_status = ControllerStatus(
                            controller_id=sensor_id,
                            status=new_status
                        )
                        db.session.add(controller_status)
                    
                    # Send command to controller
                    try:
                        print(f'Sending command to controller {sensor_id} status - {new_status}...')
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
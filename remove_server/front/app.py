# app.py
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from config import Config
from models import db, SensorReading, Setting, SettingChangeLog
from datetime import datetime, timezone, timedelta
import pandas as pd

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

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

def log_setting_change(sensor_id, humidity, histeresys_up, histeresys_down):
    """Записывает изменение настроек в лог"""
    log_entry = SettingChangeLog(
        sensor_id=sensor_id,
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
    
    # Convert to local timezone if needed
    for reading in readings:
        if reading.timestamp.tzinfo is None:
            reading.timestamp = reading.timestamp.replace(tzinfo=timezone.utc)
    
    readings.reverse()  # от старых к новым
    
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
    """Страница настроек (только для админа) - теперь для 5 датчиков"""
    # Получаем настройки для всех 5 датчиков
    sensor_settings = {}
    for sensor_id in range(1, 6):
        setting = Setting.query.filter_by(sensor_id=sensor_id).order_by(Setting.timestamp.desc()).first()
        if not setting:
            # Создаем настройки по умолчанию для датчика
            setting = Setting(
                sensor_id=sensor_id,
                humidity=60.0,
                histeresys_up=5.0,
                histeresys_down=5.0
            )
            db.session.add(setting)
            db.session.commit()
        sensor_settings[sensor_id] = setting
    
    if request.method == 'POST':
        try:
            for sensor_id in range(1, 6):
                # Получаем значения из формы для каждого датчика
                humidity = float(request.form.get(f'humidity_sensor_{sensor_id}'))
                histeresys_up = float(request.form.get(f'histeresys_up_sensor_{sensor_id}'))
                histeresys_down = float(request.form.get(f'histeresys_down_sensor_{sensor_id}'))
                
                if not (0 <= humidity <= 100):
                    raise ValueError(f'Порог влажности для датчика {sensor_id} должен быть от 0 до 100%')
                if not (0 <= histeresys_up <= 20):
                    raise ValueError(f'Верхний гистерезис для датчика {sensor_id} должен быть от 0 до 20%')
                if not (0 <= histeresys_down <= 20):
                    raise ValueError(f'Нижний гистерезис для датчика {sensor_id} должен быть от 0 до 20%')
                
                # Получаем текущую настройку датчика для логирования
                current_setting = Setting.query.filter_by(sensor_id=sensor_id).order_by(Setting.timestamp.desc()).first()
                
                # Логируем изменения, если они есть
                if current_setting:
                    if (current_setting.humidity != humidity or 
                        current_setting.histeresys_up != histeresys_up or 
                        current_setting.histeresys_down != histeresys_down):
                        log_setting_change(
                            sensor_id, 
                            humidity, 
                            histeresys_up, 
                            histeresys_down
                        )
                
                # Создаем новую запись с настройками датчика
                new_setting = Setting(
                    sensor_id=sensor_id,
                    humidity=humidity,
                    histeresys_up=histeresys_up,
                    histeresys_down=histeresys_down
                )
                db.session.add(new_setting)
            
            db.session.commit()
            flash('Настройки для всех датчиков успешно сохранены!', 'success')
        except (ValueError, TypeError) as e:
            db.session.rollback()
            flash(f'Ошибка: {str(e)}', 'danger')
    
    return render_template('settings.html', sensor_settings=sensor_settings)

@app.route('/api/readings/latest')
def api_latest_readings():
    """API для получения последних показаний"""
    limit = request.args.get('limit', 100, type=int)
    readings = SensorReading.query.order_by(
        SensorReading.timestamp.desc()
    ).limit(limit).all()
    
    return jsonify([r.to_dict() for r in reversed(readings)])

# === Запуск ===

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        # Инициализация настроек для 5 датчиков, если их нет
        for sensor_id in range(1, 6):
            existing = Setting.query.filter_by(sensor_id=sensor_id).first()
            if not existing:
                default_setting = Setting(
                    sensor_id=sensor_id,
                    humidity=60.0,
                    histeresys_up=5.0,
                    histeresys_down=5.0
                )
                db.session.add(default_setting)
        db.session.commit()
    app.run(host='0.0.0.0', port=5000, debug=True)
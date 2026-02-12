# app.py
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from config import Config
from models import db, SensorReading, SystemSettings
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
    now = datetime.utcnow()
    
    # За день
    day_ago = now - timedelta(days=1)
    day_data = SensorReading.query.filter(
        SensorReading.timestamp >= day_ago
    ).order_by(SensorReading.timestamp).all()
    
    # За месяц
    month_ago = now - timedelta(days=30)
    month_data = SensorReading.query.filter(
        SensorReading.timestamp >= month_ago
    ).order_by(SensorReading.timestamp).all()
    
    # За год
    year_ago = now - timedelta(days=365)
    year_data = SensorReading.query.filter(
        SensorReading.timestamp >= year_ago
    ).order_by(SensorReading.timestamp).all()
    
    return render_template(
        'charts.html',
        day_data=day_data,
        month_data=month_data,
        year_data=year_data,
        is_admin=session.get('is_admin')
    )

@app.route('/settings', methods=['GET', 'POST'])
@admin_required
def settings():
    """Страница настроек (только для админа)"""
    settings = SystemSettings.get_current()
    
    if request.method == 'POST':
        try:
            humidity_threshold = float(request.form.get('humidity_threshold'))
            hysteresis = float(request.form.get('hysteresis'))
            
            if not (0 <= humidity_threshold <= 100):
                raise ValueError('Порог влажности должен быть от 0 до 100%')
            if not (0 <= hysteresis <= 20):
                raise ValueError('Гистерезис должен быть от 0 до 20%')
            
            settings.humidity_threshold = humidity_threshold
            settings.hysteresis = hysteresis
            db.session.commit()
            
            flash('Настройки успешно сохранены!', 'success')
        except (ValueError, TypeError) as e:
            flash(f'Ошибка: {str(e)}', 'danger')
    
    return render_template('settings.html', settings=settings)

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
    app.run(host='0.0.0.0', port=5000, debug=True)
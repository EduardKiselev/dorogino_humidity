# models.py
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone

db = SQLAlchemy()

class SensorReading(db.Model):
    """Показания датчиков"""
    __tablename__ = 'sensor_readings'
    
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    sensor_id = db.Column(db.Integer, nullable=False, index=True)
    temperature = db.Column(db.Float)
    humidity = db.Column(db.Float)
    voltage = db.Column(db.Float)
    ip_address = db.Column(db.String(50))
    
    def to_dict(self):
        return {
            'id': self.id,
            'timestamp': self.timestamp.isoformat(),
            'sensor_id': self.sensor_id,
            'temperature': self.temperature,
            'humidity': self.humidity,
            'voltage': self.voltage,
            'ip_address': self.ip_address
        }

class ZoneSetting(db.Model):
    """Настройки для каждой зоны"""
    __tablename__ = 'zone_settings'
    
    id = db.Column(db.Integer, primary_key=True)
    zone_id = db.Column(db.Integer, nullable=False)  # ID зоны (1-5)
    humidity_threshold = db.Column(db.Float, nullable=False)  # порог влажности
    hysteresis = db.Column(db.Float, nullable=False)          # гистерезис
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<ZoneSetting zone={self.zone_id} threshold={self.humidity_threshold}>'

class SettingChangeLog(db.Model):
    """Лог изменений настроек"""
    __tablename__ = 'setting_change_log'
    
    id = db.Column(db.Integer, primary_key=True)
    zone_id = db.Column(db.Integer, nullable=False)  # ID зоны (если применимо)
    parameter_name = db.Column(db.String(100), nullable=False)  # имя параметра
    old_value = db.Column(db.Float)  # старое значение
    new_value = db.Column(db.Float)  # новое значение
    changed_at = db.Column(db.DateTime, default=datetime.utcnow)  # время изменения
    changed_by = db.Column(db.String(100))  # кто изменил (если есть авторизация)

class SystemSettings(db.Model):
    """Настройки системы управления влажностью (устаревшее, для совместимости)"""
    __tablename__ = 'system_settings'
    
    id = db.Column(db.Integer, primary_key=True)
    humidity_threshold = db.Column(db.Float, nullable=False)  # порог влажности
    hysteresis = db.Column(db.Float, nullable=False)          # гистерезис
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    @classmethod
    def get_current(cls):
        """Получить текущие настройки или создать дефолтные"""
        settings = cls.query.first()
        if not settings:
            settings = cls(
                humidity_threshold=60.0,
                hysteresis=5.0
            )
            db.session.add(settings)
            db.session.commit()
        return settings
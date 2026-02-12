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

class Setting(db.Model):
    """Таблица с настройками для каждого датчика"""
    __tablename__ = 'settings'
    
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    sensor_id = db.Column(db.Integer, nullable=False)  # ID датчика (1-5)
    humidity = db.Column(db.Float)  # порог влажности
    histeresys_up = db.Column(db.Float)  # верхний гистерезис
    histeresys_down = db.Column(db.Float)  # нижний гистерезис
    
    def to_dict(self):
        return {
            'id': self.id,
            'timestamp': self.timestamp.isoformat(),
            'sensor_id': self.sensor_id,
            'humidity': self.humidity,
            'histeresys_up': self.histeresys_up,
            'histeresys_down': self.histeresys_down
        }

class SettingChangeLog(db.Model):
    """Лог изменений настроек"""
    __tablename__ = 'settings_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    sensor_id = db.Column(db.Integer, nullable=False)  # ID датчика (если применимо)
    humidity = db.Column(db.Float)  # значение влажности
    histeresys_up = db.Column(db.Float)  # верхний гистерезис
    histeresys_down = db.Column(db.Float)  # нижний гистерезис
    
    def to_dict(self):
        return {
            'id': self.id,
            'timestamp': self.timestamp.isoformat(),
            'sensor_id': self.sensor_id,
            'humidity': self.humidity,
            'histeresys_up': self.histeresys_up,
            'histeresys_down': self.histeresys_down
        }
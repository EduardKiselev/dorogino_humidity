# models.py
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone

db = SQLAlchemy()

class SensorReading(db.Model):
    """Показания датчиков"""
    __tablename__ = 'sensor_readings'
    
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(), index=True)
    sensor_id = db.Column(db.Integer, nullable=False, index=True)
    temperature = db.Column(db.Float)
    humidity = db.Column(db.Float)
    puid = db.Column(db.String(64))
    source_ip = db.Column(db.String(50))
    destination_ip = db.Column(db.String(50))

    def to_dict(self):
        return {
            'id': self.id,
            'timestamp': self.timestamp.isoformat(),
            'sensor_id': self.sensor_id,
            'temperature': self.temperature,
            'humidity': self.humidity,
            'source_ip': self.source_ip,
            'destination_ip': self.destination_ip
        }
    
    def __repr__(self):
        return f'<SensorReading sensor_id={self.sensor_id} time={self.timestamp.isoformat()} temp="{self.temperature}" hum={self.humidity}>'
class SensorLocation(db.Model):
    __tablename__ = 'sensor_locations'
    
    id = db.Column(db.Integer, primary_key=True)
    sensor_id = db.Column(db.Integer, nullable=False, unique=True)  # Links to SensorReading.sensor_id
    description = db.Column(db.String(500), nullable=False)  # Description of where the sensor is located
    x_coordinate = db.Column(db.Float, nullable=False)  # X coordinate on the workshop diagram
    y_coordinate = db.Column(db.Float, nullable=False)  # Y coordinate on the workshop diagram
    active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<SensorLocation sensor_id={self.sensor_id} description="{self.description}" x={self.x_coordinate} y={self.y_coordinate}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'sensor_id': self.sensor_id,
            'description': self.description,
            'x_coordinate': self.x_coordinate,
            'y_coordinate': self.y_coordinate,
            'active': self.active,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }

class Setting(db.Model):
    """Таблица с настройками для каждого датчика по часам"""
    __tablename__ = 'settings'
    
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now())
    sensor_id = db.Column(db.Integer, nullable=False)  # ID датчика (1-5)
    hour_of_day = db.Column(db.Integer, nullable=False)  # Час суток (0-23)
    humidity = db.Column(db.Float)  # порог влажности
    histeresys_up = db.Column(db.Float)  # верхний гистерезис
    histeresys_down = db.Column(db.Float)  # нижний гистерезис
    
    # Уникальное ограничение для комбинации sensor_id и hour_of_day
    __table_args__ = (db.UniqueConstraint('sensor_id', 'hour_of_day'),)
    
    def to_dict(self):
        return {
            'id': self.id,
            'timestamp': self.timestamp.isoformat(),
            'sensor_id': self.sensor_id,
            'hour_of_day': self.hour_of_day,
            'humidity': self.humidity,
            'histeresys_up': self.histeresys_up,
            'histeresys_down': self.histeresys_down
        }

class SettingChangeLog(db.Model):
    """Лог изменений настроек"""
    __tablename__ = 'settings_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now())
    sensor_id = db.Column(db.Integer, nullable=False)  # ID датчика (если применимо)
    hour_of_day = db.Column(db.Integer, nullable=False)  # Час суток (0-23)
    humidity = db.Column(db.Float)  # значение влажности
    histeresys_up = db.Column(db.Float)  # верхний гистерезис
    histeresys_down = db.Column(db.Float)  # нижний гистерезис
    
    def to_dict(self):
        return {
            'id': self.id,
            'timestamp': self.timestamp.isoformat(),
            'sensor_id': self.sensor_id,
            'hour_of_day': self.hour_of_day,
            'humidity': self.humidity,
            'histeresys_up': self.histeresys_up,
            'histeresys_down': self.histeresys_down
        }

class ControllerStatus(db.Model):
    """Table to store the current status of each controller"""
    __tablename__ = 'controller_statuses'
    
    id = db.Column(db.Integer, primary_key=True)
    controller_id = db.Column(db.Integer, nullable=False, unique=True)  # Same as sensor_id
    status = db.Column(db.String(10), nullable=False)  # ON or OFF
    last_updated = db.Column(db.DateTime, default=lambda: datetime.now())
    
    def to_dict(self):
        return {
            'id': self.id,
            'controller_id': self.controller_id,
            'status': self.status,
            'last_updated': self.last_updated.isoformat()
        }

class ScreenRecord(db.Model):
    __tablename__ = 'screen_records'
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), unique=True, nullable=False)
    screen_date = db.Column(db.DateTime, nullable=False, index=True)
    parsed_at = db.Column(db.DateTime, default=datetime.utcnow)
    data_json = db.Column(db.Text)  # JSON строка
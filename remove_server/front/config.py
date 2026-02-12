# config.py
import os
from datetime import timedelta

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'change-this-in-production')
    
    # БД
    DB_HOST = os.environ.get('DB_HOST', 'localhost')
    DB_PORT = os.environ.get('DB_PORT', '5432')
    DB_NAME = os.environ.get('DB_NAME', 'sensor_data')
    DB_USER = os.environ.get('DB_USER', 'postgres')
    DB_PASSWORD = os.environ.get('DB_PASSWORD', 'password')
    
    SQLALCHEMY_DATABASE_URI = (
        f'postgresql://{DB_HOST}:{DB_PASSWORD}@{DB_USER}:{DB_PORT}/{DB_NAME}'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Простой пароль для администратора
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')
    # Force admin password change in production
    if ADMIN_PASSWORD == 'admin123':
        print("⚠️  WARNING: Using default admin password! Change it immediately!")

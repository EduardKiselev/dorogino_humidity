CREATE TABLE IF NOT EXISTS sensor_readings (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sensor_id INTEGER NOT NULL,
    temperature REAL,
    humidity REAL,
    voltage REAL,
    ip_address VARCHAR(50)
);

-- Индексы для ускорения запросов
CREATE INDEX IF NOT EXISTS idx_timestamp ON sensor_readings(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_sensor_id ON sensor_readings(sensor_id);
CREATE INDEX IF NOT EXISTS idx_sensor_id_timestamp ON sensor_readings(sensor_id, timestamp DESC);

CREATE TABLE IF NOT EXISTS settings_logs (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sensor_id INTEGER NOT NULL,
    humidity REAL,
    histeresys_up REAL,
    histeresys_down REAL
);

CREATE TABLE IF NOT EXISTS settings (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sensor_id INTEGER NOT NULL,
    humidity REAL,
    histeresys_up REAL,
    histeresys_down REAL
);

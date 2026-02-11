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

-- Представление для последних показаний каждого датчика
CREATE OR REPLACE VIEW latest_readings AS
SELECT DISTINCT ON (sensor_id)
    id,
    timestamp,
    sensor_id,
    temperature,
    humidity,
    voltage,
    ip_address
FROM sensor_readings
ORDER BY sensor_id, timestamp DESC;
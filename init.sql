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
CREATE INDEX IF NOT EXISTS idx_timestamp ON sensor_readings(timestamp);
CREATE INDEX IF NOT EXISTS idx_sensor_id ON sensor_readings(sensor_id);
CREATE INDEX IF NOT EXISTS idx_sensor_id_timestamp ON sensor_readings(sensor_id, timestamp);

-- Дополнительные индексы для фильтрации по диапазонам
CREATE INDEX IF NOT EXISTS idx_temperature ON sensor_readings(temperature) WHERE temperature IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_humidity ON sensor_readings(humidity) WHERE humidity IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_voltage ON sensor_readings(voltage) WHERE voltage IS NOT NULL;

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
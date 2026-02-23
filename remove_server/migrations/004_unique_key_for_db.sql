CREATE UNIQUE INDEX IF NOT EXISTS uq_sensor_time 
ON sensor_readings (timestamp, sensor_id);
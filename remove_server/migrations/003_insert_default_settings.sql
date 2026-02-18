-- Insert default settings for sensors 1-5 and hours 0-23 with ON CONFLICT handling
INSERT INTO settings (sensor_id, hour_of_day, humidity, histeresys_up, histeresys_down)
SELECT s.sensor_id, h.hour_of_day, 60.0, 5.0, 5.0
FROM generate_series(1, 5) AS s(sensor_id)
CROSS JOIN generate_series(0, 23) AS h(hour_of_day)
ON CONFLICT (sensor_id, hour_of_day) DO UPDATE SET
    humidity = EXCLUDED.humidity,
    histeresys_up = EXCLUDED.histeresys_up,
    histeresys_down = EXCLUDED.histeresys_down;
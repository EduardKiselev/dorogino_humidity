-- Insert default settings for all sensors and hours
DO $$
DECLARE
    sensor_id INTEGER;
    hour_val INTEGER;
BEGIN
    FOR sensor_id IN 1..5 LOOP
        FOR hour_val IN 0..23 LOOP
            INSERT INTO settings (sensor_id, hour_of_day, humidity, histeresys_up, histeresys_down)
            VALUES (sensor_id, hour_val, 60.0, 5.0, 5.0)
            ON CONFLICT DO NOTHING;
        END LOOP;
    END LOOP;
END $$;
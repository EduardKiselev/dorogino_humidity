-- 1. Добавляем столбец
ALTER TABLE settings ADD COLUMN IF NOT EXISTS day_of_week INTEGER;

-- 2. Удаляем старое UNIQUE ограничение.
ALTER TABLE settings DROP CONSTRAINT IF EXISTS settings_sensor_id_hour_of_day_key;

-- 3. Создаём новое ограничение (пока допускает NULL)
ALTER TABLE settings ADD CONSTRAINT settings_unique_sensor_day_hour 
    UNIQUE (sensor_id, day_of_week, hour_of_day);

-- 4. Размножаем старые записи на 7 дней недели (0=Пн ... 6=Вс)
INSERT INTO settings (sensor_id, day_of_week, hour_of_day, humidity, histeresys_up, histeresys_down, timestamp)
SELECT 
    s.sensor_id, d.day, s.hour_of_day, s.humidity, s.histeresys_up, s.histeresys_down, s.timestamp
FROM settings s
CROSS JOIN (VALUES (0),(1),(2),(3),(4),(5),(6)) AS d(day)
WHERE s.day_of_week IS NULL;

-- 5. Удаляем исходные записи с NULL
DELETE FROM settings WHERE day_of_week IS NULL;

-- 6. Делаем столбец обязательным
ALTER TABLE settings ALTER COLUMN day_of_week SET NOT NULL;
-- 7. Индекс для cron-задачи
CREATE INDEX IF NOT EXISTS idx_settings_sensor_day_hour 
    ON settings (sensor_id, day_of_week, hour_of_day);
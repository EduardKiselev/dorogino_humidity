-- migration_add_day_of_week.sql
-- Запуск: psql -d your_db -f migration_add_day_of_week.sql

BEGIN;

-- 1. Добавляем временный столбец
ALTER TABLE settings ADD COLUMN IF NOT EXISTS day_of_week INTEGER;

-- 2. Дублируем существующие настройки на все 7 дней недели
-- Старые записи (без day_of_week) интерпретируем как "применимо ко всем дням"
INSERT INTO settings (sensor_id, day_of_week, hour_of_day, humidity, histeresys_up, histeresys_down, timestamp)
SELECT 
    sensor_id,
    dow.day_of_week,
    hour_of_day,
    humidity,
    histeresys_up,
    histeresys_down,
    timestamp
FROM settings s
CROSS JOIN (SELECT generate_series(0, 6) AS day_of_week) AS dow
WHERE s.day_of_week IS NULL  -- только "старые" записи
ON CONFLICT (sensor_id, day_of_week, hour_of_day) 
DO NOTHING;  -- если вдруг уже есть — не перезаписываем

-- 3. Удаляем старые записи без day_of_week
DELETE FROM settings WHERE day_of_week IS NULL;

-- 4. Делаем столбец обязательным
ALTER TABLE settings ALTER COLUMN day_of_week SET NOT NULL;

-- 5. Пересоздаём UNIQUE-ограничение
-- Сначала ищем и дропаем старое ограничение (имя может отличаться)
DO $$
DECLARE
    constraint_name TEXT;
BEGIN
    SELECT constraint_name INTO constraint_name
    FROM information_schema.table_constraints
    WHERE table_name = 'settings' 
      AND constraint_type = 'UNIQUE'
      AND constraint_name LIKE '%sensor_id%hour_of_day%';
    
    IF constraint_name IS NOT NULL THEN
        EXECUTE 'ALTER TABLE settings DROP CONSTRAINT ' || quote_ident(constraint_name);
    END IF;
END $$;

-- Создаём новое ограничение
ALTER TABLE settings ADD CONSTRAINT settings_unique_sensor_day_hour 
    UNIQUE (sensor_id, day_of_week, hour_of_day);

-- 6. Добавляем индексы для ускорения выборки в cron-задаче
CREATE INDEX IF NOT EXISTS idx_settings_sensor_day_hour 
    ON settings (sensor_id, day_of_week, hour_of_day);

COMMIT;

-- Проверка: сколько записей теперь для датчика 1?
-- SELECT sensor_id, day_of_week, COUNT(*) FROM settings GROUP BY 1,2 ORDER BY 1,2;
-- migration: 010_add_day_of_week_to_settings.sql
-- Исправленная версия: сначала меняем констрейнты, потом данные

BEGIN;

-- 1. Добавляем временный столбец (если ещё нет)
ALTER TABLE settings ADD COLUMN IF NOT EXISTS day_of_week INTEGER;

-- 2. Находим и удаляем СТАРОЕ уникальное ограничение (sensor_id, hour_of_day)
-- Имя может отличаться — ищем по шаблону
DO $$
DECLARE
    old_constraint TEXT;
BEGIN
    SELECT constraint_name INTO old_constraint
    FROM information_schema.table_constraints
    WHERE table_name = 'settings'
      AND constraint_type = 'UNIQUE'
      AND table_schema = 'public'
      AND constraint_name NOT LIKE '%day_of_week%';  -- исключаем новые
    
    IF old_constraint IS NOT NULL THEN
        EXECUTE 'ALTER TABLE settings DROP CONSTRAINT ' || quote_ident(old_constraint);
        RAISE NOTICE 'Dropped old constraint: %', old_constraint;
    END IF;
END $$;

-- 3. Создаём НОВОЕ уникальное ограничение с day_of_week
ALTER TABLE settings 
ADD CONSTRAINT settings_unique_sensor_day_hour 
UNIQUE (sensor_id, day_of_week, hour_of_day);

-- 4. Теперь можно делать UPSERT — констрейнт уже существует
-- Дублируем старые записи (где day_of_week IS NULL) на все 7 дней
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
WHERE s.day_of_week IS NULL
ON CONFLICT (sensor_id, day_of_week, hour_of_day) 
DO NOTHING;  -- не перезаписываем, если уже есть

-- 5. Удаляем старые записи без day_of_week
DELETE FROM settings WHERE day_of_week IS NULL;

-- 6. Делаем столбец обязательным
ALTER TABLE settings ALTER COLUMN day_of_week SET NOT NULL;

-- 7. Добавляем индекс для ускорения выборки в cron-задаче
CREATE INDEX IF NOT EXISTS idx_settings_sensor_day_hour 
ON settings (sensor_id, day_of_week, hour_of_day);

COMMIT;

-- Проверка
DO $$
DECLARE
    cnt INTEGER;
BEGIN
    SELECT COUNT(*) INTO cnt FROM settings WHERE day_of_week IS NULL;
    IF cnt > 0 THEN
        RAISE EXCEPTION 'Migration failed: % records still have NULL day_of_week', cnt;
    END IF;
    
    SELECT COUNT(*) INTO cnt FROM settings;
    RAISE NOTICE 'Migration complete. Total settings records: %', cnt;
END $$;
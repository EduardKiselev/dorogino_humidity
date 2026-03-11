-- 1. Удаляем столбец voltage
ALTER TABLE sensor_readings 
DROP COLUMN IF EXISTS voltage;

-- 2. Добавляем столбец puid
ALTER TABLE sensor_readings 
ADD COLUMN IF NOT EXISTS puid VARCHAR(32);

-- 3. Делаем puid уникальным (защита от дубликатов)
CREATE UNIQUE INDEX IF NOT EXISTS idx_puid ON sensor_readings(puid);

-- 4. Обновляем существующие индексы для оптимизации запросов
-- Убираем старый по таймстемпу в отдельности, оставляем комбинированный
DROP INDEX IF EXISTS idx_timestamp;

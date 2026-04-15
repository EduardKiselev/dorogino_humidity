-- Конвертируем naive-время (которое было в GMT+7) в UTC:
UPDATE sensor_readings 
SET timestamp = timestamp AT TIME ZONE 'Asia/Novosibirsk' AT TIME ZONE 'UTC'
WHERE timestamp IS NOT NULL;

-- Затем измените тип колонки в БД на TIMESTAMPTZ:
ALTER TABLE sensor_readings 
ALTER COLUMN timestamp TYPE TIMESTAMPTZ USING timestamp AT TIME ZONE 'UTC';
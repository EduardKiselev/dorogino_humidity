-- Миграция 002: Добавление и расчёт влажности (г/кг)
-- Формула: Тетенс (Монтейт и Ансуорт, 2008), давление 101.325 кПа

-- 1. Добавляем колонку, если ещё нет
ALTER TABLE sensor_readings 
ADD COLUMN IF NOT EXISTS humidity_ratio NUMERIC(6,2);

-- 2. Создаём индекс (опционально, ускорит фильтрацию)
CREATE INDEX IF NOT EXISTS idx_sensor_readings_humidity_ratio 
ON sensor_readings (humidity_ratio) 
WHERE humidity_ratio IS NOT NULL;

-- 3. БЭКФИЛ: рассчитываем для старых записей
-- Только где есть температура и влажность, но нет humidity_ratio
UPDATE sensor_readings
SET humidity_ratio = ROUND(
    ( 622 * (
        (0.61078 * EXP((17.27 * temperature) / (temperature + 237.3))) * 
        (humidity / 100.0)
    ) / (
        101.325 - (
            (0.61078 * EXP((17.27 * temperature) / (temperature + 237.3))) * 
            (humidity / 100.0)
        )
    ))::NUMERIC, 
    2
)
WHERE temperature IS NOT NULL 
  AND humidity IS NOT NULL 
  AND humidity_ratio IS NULL;
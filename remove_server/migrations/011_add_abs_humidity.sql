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
    622 * (
        (0.61078 * EXP((17.27 * temperature) / (temperature + 237.3))) * 
        (humidity / 100.0)
    ) / (
        101.325 - (
            (0.61078 * EXP((17.27 * temperature) / (temperature + 237.3))) * 
            (humidity / 100.0)
        )
    )::NUMERIC, 
    2
)
WHERE temperature IS NOT NULL 
  AND humidity IS NOT NULL 
  AND humidity_ratio IS NULL;

-- 4. (Опционально) Добавляем CHECK-ограничение на разумный диапазон
-- Влагосодержание при 25–50°C и 10–80% RH обычно лежит в 2–80 г/кг
ALTER TABLE sensor_readings 
ADD CONSTRAINT chk_humidity_ratio_range 
CHECK (humidity_ratio IS NULL OR (humidity_ratio >= 0 AND humidity_ratio <= 100));
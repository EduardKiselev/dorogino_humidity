ALTER TABLE sensor_locations 
ADD COLUMN IF NOT EXISTS active BOOLEAN DEFAULT TRUE NOT NULL;

-- Update any existing records to ensure they have the active column set to true
UPDATE sensor_locations 
SET active = TRUE 
WHERE active IS NULL;
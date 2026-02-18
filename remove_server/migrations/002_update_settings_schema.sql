-- Drop old settings tables
DROP TABLE IF EXISTS settings CASCADE;
DROP TABLE IF EXISTS settings_logs CASCADE;

-- Create new settings table with hourly humidity
CREATE TABLE settings (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sensor_id INTEGER NOT NULL,
    hour_of_day INTEGER NOT NULL CHECK (hour_of_day >= 0 AND hour_of_day <= 23),
    humidity REAL,
    histeresys_up REAL,
    histeresys_down REAL,
    UNIQUE(sensor_id, hour_of_day)
);

-- Create new settings logs table with hourly humidity
CREATE TABLE settings_logs (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sensor_id INTEGER NOT NULL,
    hour_of_day INTEGER NOT NULL CHECK (hour_of_day >= 0 AND hour_of_day <= 23),
    humidity REAL,
    histeresys_up REAL,
    histeresys_down REAL
);
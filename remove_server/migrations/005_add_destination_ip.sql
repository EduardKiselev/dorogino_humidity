BEGIN;

ALTER TABLE sensor_readings RENAME COLUMN ip_address TO source_ip;

ALTER TABLE sensor_readings ADD COLUMN destination_ip VARCHAR(50) DEFAULT '192.168.10.100';

COMMIT;
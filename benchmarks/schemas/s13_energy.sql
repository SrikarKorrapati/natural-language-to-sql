-- Energy meter readings and historical tariffs
-- Sites have meters with cumulative energy readings in kWh. NULL readings are missing measurements. Reading timestamps use YYYY-MM-DD HH:MM:SS in UTC; dates use YYYY-MM-DD. Tariffs are regional, nonoverlapping half-open date intervals [valid_from, valid_to), with NULL valid_to meaning no end date.

CREATE TABLE sites (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    region TEXT NOT NULL
);
CREATE TABLE meters (
    id INTEGER PRIMARY KEY,
    site_id INTEGER NOT NULL REFERENCES sites(id),
    label TEXT NOT NULL,
    installed_on TEXT NOT NULL,
    retired_on TEXT
);
CREATE TABLE readings (
    id INTEGER PRIMARY KEY,
    meter_id INTEGER NOT NULL REFERENCES meters(id),
    reading_at TEXT NOT NULL,
    reading_kwh REAL
);
CREATE TABLE tariffs (
    id INTEGER PRIMARY KEY,
    region TEXT NOT NULL,
    valid_from TEXT NOT NULL,
    valid_to TEXT,
    price_per_kwh REAL NOT NULL
);

INSERT INTO sites VALUES
    (1, 'North Office', 'North'),
    (2, 'South Workshop', 'South'),
    (3, 'East Store', 'East'),
    (4, 'West Annex', 'West'),
    (5, 'Central Lab', 'Central'),
    (6, 'Unused North Site', 'North');

INSERT INTO meters VALUES
    (1, 1, 'Main', '2024-06-01', NULL),
    (2, 1, 'Annex', '2024-06-01', NULL),
    (3, 2, 'Workshop', '2024-07-01', NULL),
    (4, 3, 'Store', '2024-08-01', NULL),
    (5, 4, 'New Annex', '2025-01-01', NULL),
    (6, 4, 'Old Annex', '2024-01-01', '2025-01-03'),
    (7, 5, 'Lab Main', '2025-01-01', NULL),
    (8, 5, 'Lab Backup', '2025-01-02', NULL);

INSERT INTO readings VALUES
    (1, 1, '2025-01-01 00:00:00', 100),
    (2, 1, '2025-01-02 00:00:00', 118),
    (3, 1, '2025-01-03 00:00:00', 130),
    (4, 2, '2025-01-01 00:00:00', 50),
    (5, 2, '2025-01-02 00:00:00', 56),
    (6, 2, '2025-01-03 00:00:00', NULL),
    (7, 2, '2025-01-04 00:00:00', 68),
    (8, 3, '2025-01-01 00:00:00', 200),
    (9, 1, '2025-01-03 00:00:00', 140),
    (10, 3, '2025-01-04 00:00:00', 250),
    (11, 4, '2025-01-01 00:00:00', 0),
    (12, 4, '2025-01-02 00:00:00', 18),
    (13, 5, '2025-01-01 00:00:00', NULL),
    (14, 6, '2025-01-01 00:00:00', 0),
    (15, 1, '2025-01-05 00:00:00', 150);

INSERT INTO tariffs VALUES
    (1, 'North', '2025-01-01', '2025-01-02', 0.2),
    (2, 'North', '2025-01-02', NULL, 0.3),
    (3, 'South', '2025-01-01', NULL, 0.15),
    (4, 'East', '2025-01-01', NULL, 0.25),
    (5, 'West', '2025-01-01', NULL, 0.18),
    (6, 'Central', '2025-01-01', NULL, 0.22);

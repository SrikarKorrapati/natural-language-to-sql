-- Transit routes, stops, and trips
-- Routes have ordered stops; a stop may belong to multiple routes. travel_minutes_from_previous is the planned travel time from the preceding stop and is NULL for a route's first stop. Trips include historical, scheduled, and cancelled services. All timestamps are UTC and use YYYY-MM-DD HH:MM:SS.

CREATE TABLE routes (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    active INTEGER NOT NULL
);
CREATE TABLE stops (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    zone TEXT NOT NULL
);
CREATE TABLE route_stops (
    route_id INTEGER NOT NULL REFERENCES routes(id),
    stop_id INTEGER NOT NULL REFERENCES stops(id),
    stop_sequence INTEGER NOT NULL,
    travel_minutes_from_previous INTEGER,
    PRIMARY KEY (route_id, stop_sequence)
);
CREATE TABLE trips (
    id INTEGER PRIMARY KEY,
    route_id INTEGER NOT NULL REFERENCES routes(id),
    service_date TEXT NOT NULL,
    status TEXT NOT NULL,
    scheduled_departure TEXT NOT NULL,
    actual_departure TEXT
);

INSERT INTO routes VALUES
    (1, 'River Line', 1),
    (2, 'Market Line', 1),
    (3, 'Airport Link', 1),
    (4, 'Campus Shuttle', 1),
    (5, 'Old Town Loop', 0),
    (6, 'Future Express', 1);

INSERT INTO stops VALUES
    (1, 'Library', 'Central'),
    (2, 'Market Square', 'Central'),
    (3, 'River Park', 'North'),
    (4, 'Museum', 'North'),
    (5, 'South Gate', 'South'),
    (6, 'University', 'East'),
    (7, 'Station', 'Central'),
    (8, 'Airport', 'West');

INSERT INTO route_stops VALUES
    (1, 1, 1, NULL),
    (1, 2, 2, 5),
    (1, 3, 3, 7),
    (1, 4, 4, 6),
    (2, 5, 1, NULL),
    (2, 2, 2, 4),
    (2, 6, 3, 8),
    (3, 7, 1, NULL),
    (3, 8, 2, 9),
    (4, 1, 1, NULL),
    (4, 6, 2, 12),
    (5, 8, 1, NULL);

INSERT INTO trips VALUES
    (1, 1, '2025-01-01', 'completed', '2025-01-01 08:00:00', '2025-01-01 08:05:00'),
    (2, 1, '2025-01-01', 'completed', '2025-01-01 09:00:00', '2025-01-01 09:00:00'),
    (3, 1, '2025-01-01', 'completed', '2025-01-01 09:00:00', '2025-01-01 09:10:00'),
    (4, 2, '2025-01-01', 'completed', '2025-01-01 08:00:00', '2025-01-01 07:58:00'),
    (5, 2, '2025-01-02', 'cancelled', '2025-01-02 08:00:00', NULL),
    (6, 2, '2025-01-04', 'scheduled', '2025-01-04 10:00:00', NULL),
    (7, 3, '2025-01-01', 'completed', '2025-01-01 10:00:00', '2025-01-01 10:05:00'),
    (8, 3, '2025-01-03', 'completed', '2025-01-03 10:00:00', '2025-01-03 10:15:00'),
    (9, 4, '2025-01-01', 'scheduled', '2025-01-01 11:00:00', NULL),
    (10, 5, '2025-01-02', 'completed', '2025-01-02 12:00:00', '2025-01-02 12:00:00');

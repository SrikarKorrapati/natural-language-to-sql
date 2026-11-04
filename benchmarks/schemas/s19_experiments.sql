-- Scientific experiments
-- Runs belong to experiments and have control or treatment variants. Measurements can include repeated readings for the same run and metric; NULL values are missing readings. A metric with a non-NULL target is a target metric. Only completed runs qualify where specified; averages exclude NULL readings.

CREATE TABLE experiments (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);
CREATE TABLE runs (
    id INTEGER PRIMARY KEY,
    experiment_id INTEGER NOT NULL REFERENCES experiments(id),
    variant TEXT NOT NULL,
    started_at TEXT NOT NULL,
    status TEXT NOT NULL
);
CREATE TABLE metrics (
    name TEXT PRIMARY KEY,
    unit TEXT NOT NULL,
    target REAL
);
CREATE TABLE measurements (
    id INTEGER PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES runs(id),
    metric TEXT NOT NULL REFERENCES metrics(name),
    value REAL
);

INSERT INTO experiments VALUES
    (1, 'Soil'), (2, 'Pigment'), (3, 'Battery'),
    (4, 'Enzymes'), (5, 'Coating'), (6, 'Membrane');
INSERT INTO runs VALUES
    (1, 1, 'control', '2025-04-01', 'completed'),
    (2, 1, 'treatment', '2025-04-02', 'completed'),
    (3, 2, 'control', '2025-04-03', 'completed'),
    (4, 2, 'treatment', '2025-04-04', 'failed'),
    (5, 3, 'control', '2025-04-05', 'completed'),
    (6, 3, 'treatment', '2025-04-06', 'completed'),
    (7, 4, 'control', '2025-04-07', 'running'),
    (8, 5, 'control', '2025-04-08', 'failed'),
    (9, 2, 'treatment', '2025-04-09', 'completed'),
    (10, 1, 'control', '2025-04-10', 'completed');
INSERT INTO metrics VALUES
    ('temperature', 'Celsius', 20),
    ('pressure', 'kPa', 100),
    ('yield', 'percent', 70),
    ('duration', 'minutes', NULL);
INSERT INTO measurements VALUES
    (1, 1, 'temperature', 20), (2, 1, 'temperature', 20),
    (3, 1, 'pressure', 100), (4, 1, 'yield', 60),
    (5, 2, 'temperature', 20), (6, 2, 'yield', 90),
    (7, 3, 'temperature', 18), (8, 3, 'pressure', 98),
    (9, 3, 'yield', 70), (10, 10, 'yield', 80),
    (11, 5, 'yield', 80), (12, 6, 'yield', 80),
    (13, 10, 'yield', 100), (14, 4, 'yield', 95),
    (15, 8, 'yield', NULL);

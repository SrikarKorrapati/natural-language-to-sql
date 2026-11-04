-- Project tasks and dependencies
-- Projects contain tasks; dependencies point from a dependent task to its prerequisite. Dependencies form an acyclic graph. Time entries may be logged by someone other than the assignee. Known cost is hours times billed_rate for entries with a known rate; a NULL rate represents unpriced work. Tasks may be unassigned, lack due dates, or have no time entries.

CREATE TABLE projects (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    budget REAL
);
CREATE TABLE people (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);
CREATE TABLE tasks (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    assignee_id INTEGER REFERENCES people(id),
    due_date TEXT
);
CREATE TABLE dependencies (
    task_id INTEGER NOT NULL REFERENCES tasks(id),
    depends_on INTEGER NOT NULL REFERENCES tasks(id),
    PRIMARY KEY (task_id, depends_on)
);
CREATE TABLE time_entries (
    id INTEGER PRIMARY KEY,
    task_id INTEGER NOT NULL REFERENCES tasks(id),
    person_id INTEGER NOT NULL REFERENCES people(id),
    hours REAL NOT NULL,
    billed_rate REAL,
    work_date TEXT NOT NULL
);

INSERT INTO projects VALUES
    (1, 'Atlas', 1000), (2, 'Boreal', 500), (3, 'Cedar', 300),
    (4, 'Delta', NULL), (5, 'Elm', 0), (6, 'Fern', 800);
INSERT INTO people VALUES
    (1, 'Ann'), (2, 'Bob'), (3, 'Cia'), (4, 'Dan'),
    (5, 'Eva'), (6, 'Vera'), (7, 'Omar');
INSERT INTO tasks VALUES
    (1, 1, 'Scope', 'done', 1, '2025-04-01'),
    (2, 1, 'Design', 'done', 2, '2025-04-10'),
    (3, 1, 'Build', 'open', 1, '2025-04-20'),
    (4, 1, 'QA', 'blocked', 3, '2025-04-25'),
    (5, 1, 'Launch', 'open', NULL, NULL),
    (6, 2, 'Research', 'done', 4, '2025-03-05'),
    (7, 2, 'Prototype', 'open', 4, '2025-03-20'),
    (8, 2, 'Test', 'blocked', 5, '2025-03-25'),
    (9, 3, 'Plan', 'done', 2, '2025-05-01'),
    (10, 3, 'Implement', 'open', NULL, '2025-05-20'),
    (11, 4, 'Audit', 'open', 6, NULL),
    (12, 4, 'Report', 'open', 6, '2025-06-01');
INSERT INTO dependencies VALUES
    (2, 1), (3, 1), (3, 2), (4, 2), (4, 3),
    (5, 4), (7, 6), (8, 7), (10, 9), (12, 11), (11, 9);
INSERT INTO time_entries VALUES
    (1, 1, 1, 2, 50, '2025-04-01'),
    (2, 1, 2, 1, 60, '2025-04-01'),
    (3, 2, 2, 3, 60, '2025-04-08'),
    (4, 2, 2, 2, 60, '2025-04-09'),
    (5, 3, 1, 4, 50, '2025-04-15'),
    (6, 3, 1, 1, 50, '2025-04-16'),
    (7, 4, 3, 2, NULL, '2025-04-21'),
    (8, 6, 4, 3, 40, '2025-03-04'),
    (9, 7, 4, 5, 40, '2025-03-15'),
    (10, 7, 5, 1, 45, '2025-03-16'),
    (11, 8, 5, 2, 45, '2025-03-23'),
    (12, 9, 2, 2, 60, '2025-04-30'),
    (13, 10, 1, 3, 50, '2025-05-15'),
    (14, 11, 6, 4, 70, '2025-05-20'),
    (15, 12, 6, 4, 70, '2025-05-21');

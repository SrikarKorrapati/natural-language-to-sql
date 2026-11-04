-- Manufacturing bills of materials
-- Parts, an acyclic bill of materials, and work orders. BOM quantities are the direct component units needed for one parent unit. Shared components can occur along multiple paths; unit_cost is the current cost per part unit. Dates use YYYY-MM-DD.

CREATE TABLE parts (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    unit_cost REAL NOT NULL,
    kind TEXT NOT NULL
);
CREATE TABLE bom (
    parent_part_id INTEGER NOT NULL REFERENCES parts(id),
    component_part_id INTEGER NOT NULL REFERENCES parts(id),
    quantity REAL NOT NULL,
    PRIMARY KEY (parent_part_id, component_part_id)
);
CREATE TABLE work_orders (
    id INTEGER PRIMARY KEY,
    part_id INTEGER NOT NULL REFERENCES parts(id),
    quantity INTEGER NOT NULL,
    status TEXT NOT NULL,
    due_date TEXT NOT NULL,
    completed_date TEXT
);

INSERT INTO parts VALUES
    (1, 'Desk lamp', 0, 'assembly'),
    (2, 'Base module', 0, 'assembly'),
    (3, 'Light head', 0, 'assembly'),
    (4, 'Steel plate', 8, 'raw'),
    (5, 'Screw', 0.5, 'raw'),
    (6, 'LED board', 12, 'raw'),
    (7, 'Cable', 3, 'raw'),
    (8, 'Switch', 2, 'raw'),
    (9, 'Spare fuse', 1, 'raw'),
    (10, 'Shade', 6, 'raw'),
    (11, 'Controller assembly', 0, 'assembly');

INSERT INTO bom VALUES
    (1, 2, 1),
    (1, 3, 1),
    (1, 7, 2),
    (1, 8, 1),
    (2, 4, 1),
    (2, 5, 4),
    (3, 6, 1),
    (3, 5, 2),
    (3, 10, 1);

INSERT INTO work_orders VALUES
    (1, 1, 10, 'completed', '2025-01-10', '2025-01-09'),
    (2, 1, 5, 'completed', '2025-01-15', '2025-01-17'),
    (3, 2, 20, 'in_progress', '2025-01-20', NULL),
    (4, 3, 15, 'cancelled', '2025-01-25', NULL),
    (5, 1, 8, 'planned', '2025-02-01', NULL),
    (6, 3, 12, 'completed', '2025-02-03', '2025-02-03'),
    (7, 9, 30, 'completed', '2025-02-10', '2025-02-12'),
    (8, 10, 6, 'planned', '2025-02-28', NULL);

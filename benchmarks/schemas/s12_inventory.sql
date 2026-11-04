-- Warehouse inventory and movements
-- Stock is a current snapshot, with at most one row per warehouse/product. Movements are a separate recorded history; they need not reconstruct the snapshot. quantity_change is signed. last_counted can be unknown. Dates use YYYY-MM-DD.

CREATE TABLE warehouses (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    region TEXT NOT NULL
);
CREATE TABLE products (
    id INTEGER PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    reorder_level INTEGER NOT NULL
);
CREATE TABLE stock (
    warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    on_hand INTEGER NOT NULL,
    last_counted TEXT,
    PRIMARY KEY (warehouse_id, product_id)
);
CREATE TABLE movements (
    id INTEGER PRIMARY KEY,
    warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    movement_date TEXT NOT NULL,
    quantity_change INTEGER NOT NULL,
    reason TEXT NOT NULL
);

INSERT INTO warehouses VALUES
    (1, 'North Depot', 'North'),
    (2, 'South Depot', 'South'),
    (3, 'East Depot', 'East'),
    (4, 'West Depot', 'West'),
    (5, 'Central Depot', 'Central'),
    (6, 'Overflow', 'North');

INSERT INTO products VALUES
    (1, 'LAP-01', 'Laptop', 2),
    (2, 'MOU-01', 'Mouse', 10),
    (3, 'KEY-01', 'Keyboard', 5),
    (4, 'MON-01', 'Monitor', 3),
    (5, 'CAB-01', 'Cable', 20),
    (6, 'CAM-01', 'Webcam', 4);

INSERT INTO stock VALUES
    (1, 1, 5, '2025-01-15'),
    (1, 2, 10, '2025-01-15'),
    (1, 3, 10, '2025-01-05'),
    (2, 1, 2, '2025-01-16'),
    (2, 4, 0, NULL),
    (2, 5, 20, '2025-01-12'),
    (3, 2, 8, '2025-01-01'),
    (3, 6, 4, NULL),
    (4, 5, 0, '2025-01-02'),
    (5, 3, 6, '2025-01-20');

INSERT INTO movements VALUES
    (1, 1, 1, '2025-01-01', 10, 'inbound'),
    (2, 1, 1, '2025-01-03', -3, 'outbound'),
    (3, 1, 1, '2025-01-05', -2, 'outbound'),
    (4, 1, 1, '2025-01-10', 4, 'inbound'),
    (5, 1, 2, '2025-01-01', 20, 'inbound'),
    (6, 1, 2, '2025-01-04', -5, 'outbound'),
    (7, 1, 2, '2025-01-08', -5, 'adjustment'),
    (8, 2, 1, '2025-01-02', 5, 'inbound'),
    (9, 2, 1, '2025-01-06', -3, 'outbound'),
    (10, 2, 5, '2025-01-03', 25, 'inbound'),
    (11, 2, 5, '2025-01-07', -5, 'outbound'),
    (12, 3, 6, '2025-01-09', 4, 'inbound'),
    (13, 2, 4, '2025-02-01', -2, 'outbound');

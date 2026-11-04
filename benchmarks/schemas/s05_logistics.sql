-- Shipment tracking
-- Customers, carriers, shipments and timestamped tracking events. Includes unassigned shipments, unused carriers, late deliveries, missing events and tied event timestamps.

CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE carriers (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE shipments (id INTEGER PRIMARY KEY, customer_id INTEGER REFERENCES customers(id), carrier_id INTEGER REFERENCES carriers(id), weight_kg REAL NOT NULL, cost REAL NOT NULL, shipped_at TEXT NOT NULL, promised_at TEXT NOT NULL, delivered_at TEXT, status TEXT NOT NULL);
CREATE TABLE tracking_events (id INTEGER PRIMARY KEY, shipment_id INTEGER REFERENCES shipments(id), occurred_at TEXT NOT NULL, event_type TEXT NOT NULL);

INSERT INTO customers VALUES (1,'Acorn'),(2,'Birch'),(3,'Cedar'),(4,'Dogwood'),(5,'Elm');
INSERT INTO carriers VALUES (1,'Airway'),(2,'Roadline'),(3,'Seaway'),(4,'Railway'),(5,'Local');
INSERT INTO shipments VALUES
(1,1,1,10,30,'2025-05-01 09:00:00','2025-05-03 18:00:00','2025-05-03 12:00:00','delivered'),
(2,1,2,20,40,'2025-05-01 10:00:00','2025-05-03 18:00:00','2025-05-04 06:00:00','delivered'),
(3,2,1,5,20,'2025-05-02 09:00:00','2025-05-04 18:00:00',NULL,'in_transit'),
(4,3,NULL,8,16,'2025-05-02 10:00:00','2025-05-05 18:00:00',NULL,'in_transit'),
(5,2,2,30,60,'2025-05-02 11:00:00','2025-05-05 18:00:00',NULL,'cancelled'),
(6,3,3,50,100,'2025-05-03 08:00:00','2025-05-07 18:00:00','2025-05-07 18:00:00','delivered'),
(7,1,1,10,50,'2025-05-03 09:00:00','2025-05-05 18:00:00','2025-05-06 18:00:00','delivered'),
(8,4,5,0,0,'2025-05-04 09:00:00','2025-05-06 18:00:00',NULL,'in_transit');
INSERT INTO tracking_events VALUES
(1,1,'2025-05-01 10:00:00','picked_up'),(2,1,'2025-05-02 09:00:00','in_transit'),(3,1,'2025-05-03 12:00:00','delivered'),
(4,2,'2025-05-01 10:00:00','picked_up'),(5,2,'2025-05-04 06:00:00','delivered'),
(6,3,'2025-05-02 09:00:00','picked_up'),(7,3,'2025-05-03 10:00:00','in_transit'),(8,3,'2025-05-03 10:00:00','delayed'),
(9,5,'2025-05-02 11:00:00','cancelled'),(10,6,'2025-05-03 08:00:00','picked_up'),(11,6,'2025-05-07 18:00:00','delivered'),
(12,7,'2025-05-03 09:00:00','picked_up'),(13,7,'2025-05-03 10:00:00','picked_up'),(14,7,'2025-05-06 18:00:00','delivered');

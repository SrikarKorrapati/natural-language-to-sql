-- Hotel stays and payments
-- Fictional hotel reservations. A stay occupies nights in [check_in, check_out); checkout day is not occupied. Historical booked_nightly_rate determines booking value, not the room's current nightly_rate. Payments are signed cash movements, with negative refunds and NULL booking_id for unallocated payments. One pair of non-cancelled reservations intentionally overlaps to test conflict detection. All amounts use one currency.

CREATE TABLE guests (
    guest_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    city TEXT
);
CREATE TABLE rooms (
    room_id INTEGER PRIMARY KEY,
    room_number TEXT NOT NULL UNIQUE,
    room_type TEXT NOT NULL,
    nightly_rate REAL NOT NULL
);
CREATE TABLE bookings (
    booking_id INTEGER PRIMARY KEY,
    guest_id INTEGER NOT NULL REFERENCES guests(guest_id),
    room_id INTEGER NOT NULL REFERENCES rooms(room_id),
    check_in TEXT NOT NULL,
    check_out TEXT NOT NULL,
    status TEXT NOT NULL,
    booked_nightly_rate REAL NOT NULL
);
CREATE TABLE payments (
    payment_id INTEGER PRIMARY KEY,
    booking_id INTEGER REFERENCES bookings(booking_id),
    paid_on TEXT NOT NULL,
    amount REAL NOT NULL
);

INSERT INTO guests VALUES
    (1,'Ada','Ashford'),(2,'Beau','Brookfield'),(3,'Cora','Ashford'),
    (4,'Dion','Cedarville'),(5,'Esme',NULL),(6,'Finn','Dover');
INSERT INTO rooms VALUES
    (1,'101','Standard',110),(2,'102','Standard',110),
    (3,'201','Double',160),(4,'202','Double',160),
    (5,'301','Suite',250),(6,'302','Suite',300),
    (7,'401','Studio',200),(8,'402','Studio',80);
INSERT INTO bookings VALUES
    (1,1,1,'2025-01-01','2025-01-07','checked_out',100),
    (2,2,2,'2025-01-02','2025-01-04','checked_out',110),
    (3,1,3,'2025-01-05','2025-01-08','checked_out',150),
    (4,3,4,'2025-01-10','2025-01-12','cancelled',160),
    (5,3,5,'2025-01-15','2025-01-17','checked_out',250),
    (6,4,1,'2025-02-01','2025-02-03','checked_out',110),
    (7,2,6,'2025-02-02','2025-02-05','confirmed',280),
    (8,5,3,'2025-02-10','2025-02-12','checked_out',160),
    (9,4,7,'2025-02-12','2025-02-13','cancelled',200),
    (10,5,2,'2025-03-01','2025-03-05','confirmed',105),
    (11,1,5,'2025-03-10','2025-03-12','checked_out',240),
    (12,3,6,'2025-03-15','2025-03-18','checked_out',290),
    (13,4,2,'2025-01-03','2025-01-05','confirmed',110),
    (14,6,2,'2025-01-05','2025-01-06','confirmed',110),
    (15,6,2,'2025-01-03','2025-01-04','cancelled',110);
INSERT INTO payments VALUES
    (1,1,'2025-01-01',200),(2,1,'2025-01-03',100),
    (3,2,'2025-01-04',220),(4,3,'2025-01-08',400),
    (5,5,'2025-01-17',500),(6,6,'2025-02-03',220),
    (7,7,'2025-02-02',200),(8,8,'2025-02-12',320),
    (9,11,'2025-03-12',500),(10,11,'2025-03-13',-20),
    (11,NULL,'2025-03-14',30);

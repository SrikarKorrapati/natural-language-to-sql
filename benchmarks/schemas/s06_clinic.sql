-- Clinic appointments and collections
-- Fictional clinic appointments with completed, cancelled, scheduled, and no-show visits. Fees are per appointment; payments may be partial or split. A payment with NULL appointment_id is unallocated. Monetary values use one currency; timestamps are UTC. Patients and clinicians without appointments are intentional.

CREATE TABLE patients (patient_id INTEGER PRIMARY KEY, name TEXT NOT NULL, city TEXT);
CREATE TABLE clinicians (clinician_id INTEGER PRIMARY KEY, name TEXT NOT NULL, specialty TEXT NOT NULL);
CREATE TABLE appointments (
    appointment_id INTEGER PRIMARY KEY,
    patient_id INTEGER NOT NULL REFERENCES patients(patient_id),
    clinician_id INTEGER NOT NULL REFERENCES clinicians(clinician_id),
    scheduled_at TEXT NOT NULL, status TEXT NOT NULL, fee REAL NOT NULL
);
CREATE TABLE payments (
    payment_id INTEGER PRIMARY KEY,
    appointment_id INTEGER REFERENCES appointments(appointment_id),
    amount REAL NOT NULL, paid_at TEXT NOT NULL
);

INSERT INTO patients VALUES
(1,'Mira','Northport'),(2,'Leo','Southport'),(3,'Nora','Northport'),
(4,'Owen','Westport'),(5,'Iris',NULL),(6,'Ezra','Eastport');
INSERT INTO clinicians VALUES
(1,'Dr Rowan','General'),(2,'Dr Ellis','Cardiology'),(3,'Dr Sage','General'),
(4,'Dr Lane','Dermatology'),(5,'Dr River','Pediatrics'),(6,'Dr Ash','Neurology');
INSERT INTO appointments VALUES
(101,1,1,'2025-01-02 09:00:00','completed',100),
(102,2,1,'2025-01-03 10:00:00','completed',120),
(103,1,2,'2025-01-05 11:00:00','completed',200),
(104,3,2,'2025-01-06 09:00:00','completed',180),
(105,4,3,'2025-01-07 12:00:00','cancelled',120),
(106,3,3,'2025-01-08 13:00:00','completed',120),
(107,5,4,'2025-01-09 14:00:00','completed',150),
(108,2,4,'2025-01-10 09:00:00','no_show',150),
(109,4,1,'2025-02-01 10:00:00','scheduled',100),
(110,5,1,'2025-01-11 11:00:00','completed',100);
INSERT INTO payments VALUES
(1,101,60,'2025-01-02'),(2,101,40,'2025-01-04'),
(3,102,100,'2025-01-03'),(4,103,200,'2025-01-05'),
(5,104,180,'2025-01-06'),(6,106,120,'2025-01-08'),
(7,107,160,'2025-01-09'),(8,NULL,25,'2025-01-10');

-- Course enrollment
-- Students, instructors, catalog courses and term enrollments. Includes required and optional courses, repeat enrollments, missing grades, withdrawals and unstaffed courses.

CREATE TABLE students (id INTEGER PRIMARY KEY, name TEXT NOT NULL, major TEXT NOT NULL);
CREATE TABLE instructors (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE courses (id INTEGER PRIMARY KEY, title TEXT NOT NULL, major TEXT NOT NULL, credits INTEGER NOT NULL, instructor_id INTEGER REFERENCES instructors(id), is_required INTEGER NOT NULL);
CREATE TABLE enrollments (student_id INTEGER REFERENCES students(id), course_id INTEGER REFERENCES courses(id), term TEXT NOT NULL, status TEXT NOT NULL, score REAL, PRIMARY KEY (student_id, course_id, term));

INSERT INTO students VALUES (1,'Alma','CS'),(2,'Bert','CS'),(3,'Cora','Math'),(4,'Dane','Math'),(5,'Esme','History'),(6,'Finn','CS'),(7,'Gia','History');
INSERT INTO instructors VALUES (1,'Inez'),(2,'Jules'),(3,'Kiran'),(4,'Luz');
INSERT INTO courses VALUES (1,'Databases','CS',4,1,1),(2,'Algorithms','CS',3,1,1),(3,'Networks','CS',2,2,0),(4,'Calculus','Math',4,3,1),(5,'Statistics','Math',3,3,1),(6,'Ancient History','History',3,NULL,0),(7,'Topology','Math',2,NULL,0);
INSERT INTO enrollments VALUES
(1,1,'2024-Fall','completed',90),(1,2,'2024-Fall','completed',80),(1,3,'2025-Spring','enrolled',NULL),
(2,1,'2024-Fall','completed',70),(2,2,'2024-Fall','withdrawn',NULL),(2,1,'2025-Spring','completed',85),
(3,4,'2024-Fall','completed',90),(3,5,'2025-Spring','completed',85),(4,4,'2024-Fall','enrolled',NULL),
(4,5,'2025-Spring','withdrawn',NULL),(5,6,'2024-Fall','completed',80),(5,6,'2025-Spring','withdrawn',NULL),
(6,2,'2025-Spring','completed',85),(6,3,'2025-Spring','enrolled',NULL);

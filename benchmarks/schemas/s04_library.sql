-- Library circulation
-- Authors, book titles, members and dated loans. Includes unborrowed titles, future loans and returns, overdue loans, tied dates and members without activity.

CREATE TABLE authors (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE books (id INTEGER PRIMARY KEY, title TEXT NOT NULL, author_id INTEGER REFERENCES authors(id), published_year INTEGER NOT NULL, total_copies INTEGER NOT NULL);
CREATE TABLE members (id INTEGER PRIMARY KEY, name TEXT NOT NULL, joined_at TEXT NOT NULL);
CREATE TABLE loans (id INTEGER PRIMARY KEY, book_id INTEGER REFERENCES books(id), member_id INTEGER REFERENCES members(id), loaned_at TEXT NOT NULL, due_at TEXT NOT NULL, returned_at TEXT);

INSERT INTO authors VALUES (1,'Mira Stone'),(2,'Noah Vale'),(3,'Opal Reed'),(4,'Pia Lake');
INSERT INTO books VALUES (1,'Cloud Atlas',1,2018,3),(2,'Glass River',1,2020,2),(3,'Night Orchard',2,2018,2),(4,'Quiet Maps',3,2022,1),(5,'Open Sky',2,2024,1);
INSERT INTO members VALUES (1,'Arun','2024-01-01'),(2,'Bea','2024-02-01'),(3,'Cole','2024-03-01'),(4,'Dina','2024-04-01'),(5,'Enzo','2025-01-01'),(6,'Fia','2025-02-01'),(7,'Gio','2025-03-01');
INSERT INTO loans VALUES
(1,1,1,'2025-05-01','2025-05-15','2025-05-10'),(2,2,1,'2025-05-20','2025-06-03','2025-06-05'),
(3,3,2,'2025-06-01','2025-06-15',NULL),(4,1,2,'2025-06-10','2025-06-24','2025-07-02'),
(5,2,3,'2025-06-20','2025-07-04',NULL),(6,3,1,'2025-06-20','2025-07-04','2025-06-25'),
(7,1,4,'2025-07-01','2025-07-15',NULL),(8,4,3,'2025-06-20','2025-07-04','2025-06-22'),
(9,4,5,'2025-05-01','2025-05-15','2025-05-15'),(10,3,6,'2025-07-02','2025-07-16',NULL);

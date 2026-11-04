-- People and projects
-- Employee reporting hierarchy, departments, projects and dated work logs. Includes unassigned staff, empty departments, salary ties and employees without logged work.

CREATE TABLE departments (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE employees (id INTEGER PRIMARY KEY, name TEXT NOT NULL, department_id INTEGER REFERENCES departments(id), manager_id INTEGER REFERENCES employees(id), title TEXT NOT NULL, salary REAL NOT NULL, hired_at TEXT NOT NULL);
CREATE TABLE projects (id INTEGER PRIMARY KEY, name TEXT NOT NULL, department_id INTEGER REFERENCES departments(id));
CREATE TABLE work_logs (id INTEGER PRIMARY KEY, employee_id INTEGER REFERENCES employees(id), project_id INTEGER REFERENCES projects(id), worked_at TEXT NOT NULL, hours REAL NOT NULL);

INSERT INTO departments VALUES (1,'Engineering'),(2,'Sales'),(3,'Operations'),(4,'Legal');
INSERT INTO employees VALUES
(1,'Ada',1,NULL,'Director',150000,'2020-01-01'),(2,'Ben',1,1,'Manager',100000,'2021-06-01'),
(3,'Cy',2,1,'Manager',95000,'2022-01-01'),(4,'Dee',3,1,'Manager',90000,'2021-03-10'),
(5,'Eli',1,2,'Engineer',80000,'2023-01-01'),(6,'Fay',1,2,'Engineer',100000,'2023-06-01'),
(7,'Gus',1,5,'Engineer',60000,'2024-02-02'),(8,'Hope',2,3,'Analyst',75000,'2022-05-01'),
(9,'Ira',NULL,1,'Consultant',110000,'2025-01-01'),(10,'Jo',3,4,'Analyst',70000,'2024-01-01');
INSERT INTO projects VALUES (1,'Platform',1),(2,'Launch',2),(3,'Migration',1),(4,'Facilities',3);
INSERT INTO work_logs VALUES (1,2,1,'2025-05-01',4),(2,2,2,'2025-05-02',2),
(3,5,1,'2025-05-01',8),(4,5,3,'2025-05-02',6),(5,6,1,'2025-05-03',7),
(6,7,3,'2025-04-30',5),(7,8,2,'2025-05-04',3),(8,8,1,'2025-05-05',5),
(9,9,2,'2025-05-05',4),(10,3,2,'2025-06-01',6);

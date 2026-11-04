-- Survey participation
-- A participant can have at most one response per question. A non-NULL score is an answered question; a NULL score is an explicit skip, and a missing response is unanswered. required=1 marks mandatory questions. Participants may have no group or responses.

CREATE TABLE participants (id INTEGER PRIMARY KEY, name TEXT NOT NULL, group_name TEXT);
CREATE TABLE questions (id INTEGER PRIMARY KEY, prompt TEXT NOT NULL, required INTEGER NOT NULL CHECK(required IN (0,1)));
CREATE TABLE responses (id INTEGER PRIMARY KEY, participant_id INTEGER NOT NULL REFERENCES participants(id), question_id INTEGER NOT NULL REFERENCES questions(id), score REAL, answered_at TEXT NOT NULL, UNIQUE(participant_id,question_id));

INSERT INTO participants VALUES (1,'Ana','A'),(2,'Bo','A'),(3,'Cy','B'),(4,'Dee','B'),(5,'Ena','C'),(6,'Flo',NULL);
INSERT INTO questions VALUES (1,'Support satisfaction',1),(2,'Recommendation likelihood',1),(3,'Documentation quality',0),(4,'Ease of use',1),(5,'Response speed',0),(6,'Training quality',0);
INSERT INTO responses VALUES
 (1,1,1,5,'2025-02-01'),(2,1,2,4,'2025-02-01'),(3,1,4,5,'2025-02-01'),
 (4,2,1,3,'2025-02-02'),(5,2,2,NULL,'2025-02-02'),(6,2,4,4,'2025-02-02'),(7,2,3,2,'2025-02-02'),
 (8,3,1,5,'2025-02-03'),(9,3,2,5,'2025-02-03'),(10,3,4,5,'2025-02-03'),(11,3,5,4,'2025-02-03'),
 (12,4,1,2,'2025-02-04'),(13,4,2,3,'2025-02-04'),(14,5,3,5,'2025-02-05'),(15,5,5,NULL,'2025-02-05');

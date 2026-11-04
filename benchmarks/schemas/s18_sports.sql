-- League matches
-- Team membership is fixed in this snapshot. Match scores are official; appearances contain only recorded player participation and may be incomplete. completed matches have scores, scheduled matches have NULL scores. League points are 3 for a win, 1 for a draw, and 0 for a loss.

CREATE TABLE teams (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE players (id INTEGER PRIMARY KEY, team_id INTEGER NOT NULL REFERENCES teams(id), name TEXT NOT NULL, position TEXT NOT NULL);
CREATE TABLE matches (id INTEGER PRIMARY KEY, home_team_id INTEGER NOT NULL REFERENCES teams(id), away_team_id INTEGER NOT NULL REFERENCES teams(id), played_at TEXT NOT NULL, status TEXT NOT NULL, home_score INTEGER, away_score INTEGER);
CREATE TABLE appearances (id INTEGER PRIMARY KEY, match_id INTEGER NOT NULL REFERENCES matches(id), player_id INTEGER NOT NULL REFERENCES players(id), minutes INTEGER NOT NULL, goals INTEGER NOT NULL, UNIQUE(match_id,player_id));

INSERT INTO teams VALUES (1,'Falcons'),(2,'Bears'),(3,'Cobras'),(4,'Dolphins'),(5,'Eagles'),(6,'Foxes'),(7,'Gulls');
INSERT INTO players VALUES (1,1,'Mia','striker'),(2,1,'Leo','defender'),(3,2,'Noah','striker'),(4,2,'Ava','midfielder'),(5,3,'Eli','striker'),(6,4,'Ivy','defender'),(7,5,'Zoe','striker'),(8,6,'Owen','midfielder'),(9,1,'Nina','goalkeeper');
INSERT INTO matches VALUES
 (1,1,2,'2025-03-01','completed',2,0),(2,3,1,'2025-03-02','completed',0,1),
 (3,2,4,'2025-03-03','completed',3,1),(4,5,2,'2025-03-04','completed',1,2),
 (5,1,3,'2025-03-05','completed',1,1),(6,4,5,'2025-03-06','completed',0,0),
 (7,3,4,'2025-03-07','scheduled',NULL,NULL),(8,5,1,'2025-03-08','completed',2,3),
 (9,2,3,'2025-03-09','completed',0,1),
 (10,6,7,'2025-03-10','scheduled',NULL,NULL);
INSERT INTO appearances VALUES
 (1,1,1,90,2),(2,1,2,90,0),(3,1,3,90,0),(4,2,1,90,1),(5,2,5,90,0),
 (6,3,3,90,2),(7,3,4,90,1),(8,3,6,90,1),(9,4,3,90,1),(10,4,4,70,1),
 (11,4,7,90,1),(12,5,1,90,1),(13,5,5,90,1),(14,6,6,90,0),(15,6,7,90,0);

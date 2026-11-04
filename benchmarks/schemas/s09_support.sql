-- Customer support
-- Fictional support queues and ticket events. All timestamps are UTC. Unresolved means status open or pending. A ticket can be unassigned to an agent or team; an agent can have no tickets. Multiple replies belong to a single ticket. A ticket's queue team can differ from its assigned agent's home team.

CREATE TABLE teams (
    team_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);
CREATE TABLE agents (
    agent_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    team_id INTEGER NOT NULL REFERENCES teams(team_id)
);
CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);
CREATE TABLE tickets (
    ticket_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
    assigned_agent_id INTEGER REFERENCES agents(agent_id),
    team_id INTEGER REFERENCES teams(team_id),
    opened_at TEXT NOT NULL,
    closed_at TEXT,
    status TEXT NOT NULL,
    priority TEXT NOT NULL
);
CREATE TABLE ticket_events (
    event_id INTEGER PRIMARY KEY,
    ticket_id INTEGER NOT NULL REFERENCES tickets(ticket_id),
    event_type TEXT NOT NULL,
    created_at TEXT NOT NULL
);

INSERT INTO teams VALUES
    (1,'Billing'),(2,'Technical'),(3,'Shipping'),
    (4,'Returns'),(5,'Security'),(6,'Enterprise');
INSERT INTO agents VALUES
    (1,'Anika',1),(2,'Bram',1),(3,'Cleo',2),(4,'Dara',2),
    (5,'Enzo',3),(6,'Farah',4),(7,'Gus',5);
INSERT INTO customers VALUES
    (1,'Atlas'),(2,'Brook'),(3,'Cove'),(4,'Dune'),(5,'Ember'),(6,'Flint');
INSERT INTO tickets VALUES
    (1,1,1,1,'2025-01-02 09:00:00','2025-01-03 09:00:00','closed','high'),
    (2,1,1,1,'2025-01-04 09:00:00',NULL,'open','normal'),
    (3,2,3,2,'2025-01-03 10:00:00','2025-01-05 10:00:00','closed','high'),
    (4,2,NULL,2,'2025-01-05 09:00:00',NULL,'open','high'),
    (5,2,4,2,'2025-01-06 09:00:00','2025-01-06 12:00:00','closed','low'),
    (6,3,5,3,'2025-01-04 09:00:00',NULL,'pending','normal'),
    (7,3,5,3,'2025-01-07 09:00:00','2025-01-08 09:00:00','closed','high'),
    (8,4,6,4,'2025-01-08 09:00:00','2025-01-10 09:00:00','closed','normal'),
    (9,4,NULL,4,'2025-01-09 09:00:00',NULL,'open','low'),
    (10,5,1,1,'2025-01-04 09:00:00',NULL,'pending','high'),
    (11,5,3,2,'2025-01-11 09:00:00','2025-01-12 09:00:00','closed','normal'),
    (12,5,NULL,NULL,'2025-01-12 09:00:00',NULL,'open','high'),
    (13,1,3,1,'2025-01-05 09:00:00',NULL,'open','high'),
    (14,3,4,2,'2025-01-05 09:00:00',NULL,'pending','normal');
INSERT INTO ticket_events VALUES
    (1,1,'customer_message','2025-01-02 09:00:00'),
    (2,1,'agent_reply','2025-01-02 10:00:00'),
    (3,1,'agent_reply','2025-01-02 11:00:00'),
    (4,2,'agent_reply','2025-01-04 13:00:00'),
    (5,2,'customer_message','2025-01-04 09:00:00'),
    (6,3,'agent_reply','2025-01-03 10:30:00'),
    (7,4,'customer_message','2025-01-05 09:00:00'),
    (8,5,'agent_reply','2025-01-06 09:15:00'),
    (9,6,'agent_reply','2025-01-04 17:00:00'),
    (10,7,'agent_reply','2025-01-07 11:00:00'),
    (11,8,'agent_reply','2025-01-08 13:00:00'),
    (12,8,'note','2025-01-08 14:00:00'),
    (13,10,'agent_reply','2025-01-04 12:00:00'),
    (14,11,'agent_reply','2025-01-11 14:00:00'),
    (15,12,'customer_message','2025-01-12 09:00:00');

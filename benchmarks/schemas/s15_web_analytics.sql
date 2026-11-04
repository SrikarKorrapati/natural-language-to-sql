-- Website visitors, sessions, and events
-- A visitor can have many sessions, including sessions without events. NULL referrer means direct traffic. Only purchase events carry purchase revenue; other events may have NULL revenue. All timestamps are UTC in YYYY-MM-DD HH:MM:SS format. Signup dates can be unknown. Sessions and events are distinct grains.

CREATE TABLE visitors (
    id INTEGER PRIMARY KEY,
    country TEXT NOT NULL,
    signup_date TEXT
);
CREATE TABLE sessions (
    id INTEGER PRIMARY KEY,
    visitor_id INTEGER NOT NULL REFERENCES visitors(id),
    started_at TEXT NOT NULL,
    device TEXT NOT NULL,
    referrer TEXT
);
CREATE TABLE events (
    id INTEGER PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES sessions(id),
    event_at TEXT NOT NULL,
    event_type TEXT NOT NULL,
    page TEXT NOT NULL,
    revenue REAL
);

INSERT INTO visitors VALUES
    (1, 'US', '2025-01-01'),
    (2, 'IN', '2025-01-02'),
    (3, 'GB', NULL),
    (4, 'US', '2025-01-03'),
    (5, 'CA', '2025-01-04'),
    (6, 'IN', NULL),
    (7, 'GB', '2025-01-05'),
    (8, 'AU', '2025-01-02');

INSERT INTO sessions VALUES
    (1, 1, '2025-01-01 00:00:00', 'desktop', 'search'),
    (2, 1, '2025-01-02 00:00:00', 'mobile', 'email'),
    (3, 1, '2025-01-02 00:00:00', 'desktop', NULL),
    (4, 2, '2025-01-01 00:00:00', 'mobile', 'search'),
    (5, 2, '2025-01-02 00:00:00', 'mobile', NULL),
    (6, 3, '2025-01-01 00:00:00', 'tablet', 'social'),
    (7, 3, '2025-01-03 00:00:00', 'desktop', 'social'),
    (8, 4, '2025-01-02 00:00:00', 'desktop', 'search'),
    (9, 5, '2025-01-02 00:00:00', 'tablet', NULL),
    (10, 6, '2025-01-03 00:00:00', 'mobile', 'search'),
    (11, 7, '2025-01-03 00:00:00', 'desktop', NULL),
    (12, 1, '2025-01-04 00:00:00', 'desktop', 'email');

INSERT INTO events VALUES
    (1, 1, '2025-01-01 00:01:00', 'page_view', '/', NULL),
    (2, 1, '2025-01-01 00:03:00', 'purchase', '/checkout', 5),
    (3, 1, '2025-01-01 00:05:00', 'purchase', '/checkout', 20),
    (4, 2, '2025-01-02 00:01:00', 'page_view', '/', NULL),
    (5, 2, '2025-01-02 00:03:00', 'purchase', '/checkout', 20),
    (6, 4, '2025-01-01 00:02:00', 'page_view', '/', NULL),
    (7, 4, '2025-01-01 00:04:00', 'signup', '/signup', NULL),
    (8, 5, '2025-01-02 00:02:00', 'purchase', '/checkout', 30),
    (9, 6, '2025-01-01 00:02:00', 'page_view', '/help', NULL),
    (10, 7, '2025-01-03 00:02:00', 'page_view', '/product', NULL),
    (11, 7, '2025-01-03 00:04:00', 'purchase', '/checkout', 10),
    (12, 8, '2025-01-02 00:02:00', 'page_view', '/', NULL),
    (13, 9, '2025-01-02 00:02:00', 'page_view', '/', NULL),
    (14, 10, '2025-01-03 00:05:00', 'purchase', '/checkout', 30),
    (15, 12, '2025-01-04 00:01:00', 'page_view', '/', NULL);

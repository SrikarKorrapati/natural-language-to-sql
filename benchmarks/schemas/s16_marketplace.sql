-- Marketplace auctions
-- Users can be sellers and bidders. Listings may have no reserve or no bids. Listing status is open or closed; bids remain historical after closing. Highest bids may tie.

CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE listings (id INTEGER PRIMARY KEY, seller_id INTEGER NOT NULL REFERENCES users(id), title TEXT NOT NULL, status TEXT NOT NULL, reserve_price REAL, listed_at TEXT NOT NULL);
CREATE TABLE bids (id INTEGER PRIMARY KEY, listing_id INTEGER NOT NULL REFERENCES listings(id), bidder_id INTEGER NOT NULL REFERENCES users(id), amount REAL NOT NULL, bid_at TEXT NOT NULL);

INSERT INTO users VALUES (1,'Ada'),(2,'Ben'),(3,'Cleo'),(4,'Dara'),(5,'Emil'),(6,'Faye'),(7,'Gus');
INSERT INTO listings VALUES
 (1,1,'Camera','open',100,'2025-01-01'),(2,1,'Tripod','open',NULL,'2025-01-02'),
 (3,2,'Bicycle','closed',200,'2025-01-03'),(4,3,'Lamp','open',50,'2025-01-04'),
 (5,4,'Desk','open',150,'2025-01-05'),(6,2,'Monitor','open',120,'2025-01-06'),
 (7,6,'Bookcase','closed',80,'2025-01-07'),(8,4,'Chair','open',NULL,'2025-01-08');
INSERT INTO bids VALUES
 (1,1,2,90,'2025-01-02'),(2,1,3,110,'2025-01-03'),(3,1,4,110,'2025-01-04'),
 (4,2,2,25,'2025-01-03'),(5,2,3,30,'2025-01-04'),(6,2,4,30,'2025-01-05'),
 (7,3,1,220,'2025-01-04'),(8,3,5,240,'2025-01-05'),
 (9,4,1,40,'2025-01-05'),(10,5,3,165,'2025-01-06'),
 (11,5,3,160,'2025-01-06'),(12,5,5,170,'2025-01-07'),
 (13,6,1,130,'2025-01-07'),(14,7,4,80,'2025-01-08'),(15,7,5,80,'2025-01-09');

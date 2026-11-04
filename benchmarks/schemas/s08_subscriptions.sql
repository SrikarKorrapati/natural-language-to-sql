-- Subscription billing and usage
-- Fictional subscriptions, plans, invoice amounts, and metered usage. Invoice amount is historical and can differ from a plan current monthly_price. Paid revenue uses paid invoices only. Included units are a monthly plan allowance; each subscription retains its recorded plan throughout these fixtures. Cancelled subscriptions, unused plans, customers without subscriptions, and subscriptions without invoices are intentional.

CREATE TABLE customers (customer_id INTEGER PRIMARY KEY, name TEXT NOT NULL, country TEXT);
CREATE TABLE plans (plan_id INTEGER PRIMARY KEY, name TEXT NOT NULL, monthly_price REAL NOT NULL, included_units INTEGER NOT NULL);
CREATE TABLE subscriptions (
    subscription_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
    plan_id INTEGER NOT NULL REFERENCES plans(plan_id),
    start_date TEXT NOT NULL, end_date TEXT, status TEXT NOT NULL
);
CREATE TABLE invoices (
    invoice_id INTEGER PRIMARY KEY,
    subscription_id INTEGER NOT NULL REFERENCES subscriptions(subscription_id),
    billed_on TEXT NOT NULL, amount REAL NOT NULL, status TEXT NOT NULL
);
CREATE TABLE usage_events (
    event_id INTEGER PRIMARY KEY,
    subscription_id INTEGER NOT NULL REFERENCES subscriptions(subscription_id),
    used_on TEXT NOT NULL, units INTEGER NOT NULL
);

INSERT INTO customers VALUES
(1,'Acorn','US'),(2,'Birch','CA'),(3,'Cedar','US'),
(4,'Dahlia','GB'),(5,'Elm','CA'),(6,'Fern',NULL);
INSERT INTO plans VALUES
(1,'Basic',20,100),(2,'Pro',50,500),(3,'Business',100,1000),
(4,'Flex',35,200),(5,'Premium',150,2000),(6,'Legacy',15,50);
INSERT INTO subscriptions VALUES
(1,1,1,'2025-01-01',NULL,'active'),(2,1,2,'2024-12-01','2025-01-31','cancelled'),
(3,2,2,'2025-01-01',NULL,'active'),(4,3,3,'2025-01-01',NULL,'active'),
(5,3,1,'2025-01-01','2025-01-31','cancelled'),(6,4,4,'2025-02-01',NULL,'paused'),
(7,5,2,'2025-03-01',NULL,'active'),(8,5,5,'2025-03-01',NULL,'active');
INSERT INTO invoices VALUES
(1,1,'2025-01-01',18,'paid'),(2,1,'2025-02-01',20,'paid'),(3,1,'2025-03-01',20,'open'),
(4,2,'2025-01-01',50,'paid'),(5,2,'2025-02-01',50,'void'),
(6,3,'2025-01-01',45,'paid'),(7,3,'2025-02-01',50,'paid'),
(8,4,'2025-01-01',100,'paid'),(9,4,'2025-02-01',100,'open'),
(10,5,'2025-01-01',20,'paid'),(11,6,'2025-02-01',35,'void'),(12,7,'2025-03-01',50,'open');
INSERT INTO usage_events VALUES
(1,1,'2025-01-10',60),(2,1,'2025-01-20',50),(3,1,'2025-02-10',90),
(4,3,'2025-01-15',300),(5,3,'2025-01-20',250),(6,3,'2025-02-15',100),
(7,4,'2025-01-05',800),(8,4,'2025-01-25',300),(9,5,'2025-01-12',10),
(10,6,'2025-02-04',0),(11,7,'2025-03-04',700),(12,8,'2025-03-08',1800);

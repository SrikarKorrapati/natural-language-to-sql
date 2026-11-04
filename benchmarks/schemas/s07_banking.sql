-- Account ledger and statement reconciliation
-- Fictional accounts with opening balances and a signed ledger: positive amounts add funds and negative amounts remove funds. Ledger entries are historical postings. Imported statements intentionally have no account foreign key, because an external account number can be unmatched. All statements are dated 2025-03-31; ledger postings also include a later posting. Monetary values use one currency.

CREATE TABLE customers (customer_id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT);
CREATE TABLE accounts (
    account_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
    account_number TEXT NOT NULL UNIQUE, kind TEXT NOT NULL,
    opening_balance REAL NOT NULL, status TEXT NOT NULL
);
CREATE TABLE ledger_entries (
    entry_id INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES accounts(account_id),
    posted_at TEXT NOT NULL, entry_type TEXT NOT NULL, amount REAL NOT NULL
);
CREATE TABLE statements (
    account_number TEXT PRIMARY KEY,
    statement_date TEXT NOT NULL, ending_balance REAL
);

INSERT INTO customers VALUES
(1,'Ari','ari@example.test'),(2,'Bo','bo@example.test'),(3,'Cy','cy@example.test'),
(4,'Dee','dee@example.test'),(5,'Eli',NULL),(6,'Faye','faye@example.test');
INSERT INTO accounts VALUES
(1,1,'A100','checking',1000,'open'),(2,1,'A101','savings',2000,'open'),
(3,2,'A102','checking',500,'open'),(4,3,'A103','checking',0,'open'),
(5,3,'A104','savings',1000,'open'),(6,4,'A105','checking',100,'closed'),
(7,6,'A106','savings',200,'open'),(8,6,'A107','checking',50,'open');
INSERT INTO ledger_entries VALUES
(1,1,'2025-01-05','deposit',500),(2,1,'2025-01-05','withdrawal',-200),
(3,1,'2025-03-01','fee',-10),(4,2,'2025-02-10','withdrawal',-500),
(5,2,'2025-03-31','interest',20),(6,3,'2025-01-15','deposit',250),
(7,3,'2025-03-20','withdrawal',-50),(8,4,'2025-02-01','deposit',100),
(9,5,'2025-01-20','withdrawal',-300),(10,5,'2025-02-20','deposit',300),
(11,6,'2025-03-01','fee',-10),(12,6,'2025-03-02','withdrawal',-90),
(13,8,'2025-03-03','deposit',100),(14,8,'2025-03-04','withdrawal',-20),
(15,8,'2025-04-01','withdrawal',-10);
INSERT INTO statements VALUES
('A100','2025-03-31',1290),('A101','2025-03-31',1500),
('A102','2025-03-31',700),('A103','2025-03-31',NULL),
('A104','2025-03-31',1000),('A105','2025-03-31',0),
('A999','2025-03-31',45);

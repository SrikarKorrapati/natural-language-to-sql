-- Retail orders
-- Customers, catalog products, orders, and historical item prices. Includes cancelled orders, an empty order, unsold products, and customers without orders.

CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT NOT NULL, region TEXT NOT NULL);
CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL, price REAL NOT NULL);
CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER REFERENCES customers(id), ordered_at TEXT NOT NULL, status TEXT NOT NULL);
CREATE TABLE order_items (order_id INTEGER REFERENCES orders(id), product_id INTEGER REFERENCES products(id), quantity INTEGER NOT NULL, unit_price REAL NOT NULL);

INSERT INTO customers VALUES
(1,'Avery','North'),(2,'Jordan','South'),(3,'Morgan','East'),(4,'Riley','West'),
(5,'Sam','North'),(6,'Casey','South'),(7,'Alex','East'),(8,'Taylor','West'),
(9,'Drew','North'),(10,'Cameron','South'),(11,'Quinn','East'),(12,'Robin','West'),(13,'Jamie','West');
INSERT INTO products VALUES (1,'Keyboard','Electronics',90),(2,'Lamp','Home',45),(3,'Mug','Home',12),(4,'Headphones','Electronics',120),(5,'Notebook','Stationery',8),(6,'Pen','Stationery',3);
INSERT INTO orders VALUES
(1,1,'2025-01-05','completed'),(2,2,'2025-01-12','completed'),(3,1,'2025-01-15','cancelled'),
(4,1,'2025-02-03','completed'),(5,3,'2025-02-07','pending'),(6,4,'2025-03-02','completed'),
(7,2,'2025-03-10','cancelled'),(8,5,'2024-12-20','completed'),(9,3,'2025-03-15','completed');
INSERT INTO order_items VALUES
(1,1,1,80),(1,2,1,40),(2,3,2,10),(2,5,1,6),(3,4,2,100),
(4,3,3,10),(4,2,2,40),(5,1,1,90),(6,4,1,160),(6,5,2,6),(7,1,1,85),(9,1,1,80),(9,5,1,6);

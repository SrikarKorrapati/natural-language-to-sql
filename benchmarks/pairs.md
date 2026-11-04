# 200 natural-language → SQL pairs

20 SQLite schemas, 10 questions per schema. Each schema has 3 easy, 4 medium and 3 hard cases. Reference SQL is one valid answer; equivalent SQL is accepted by execution comparison.

See [benchmark instructions](README.md) for scoring and [cases.json](cases.json) for the machine-readable pairs.

## Schemas

| Schema | Domain | Tables |
| --- | --- | --- |
| [s01_retail](schemas/s01_retail.sql) | Retail orders | customers, order_items, orders, products |
| [s02_hr](schemas/s02_hr.sql) | People and projects | departments, employees, projects, work_logs |
| [s03_education](schemas/s03_education.sql) | Course enrollment | courses, enrollments, instructors, students |
| [s04_library](schemas/s04_library.sql) | Library circulation | authors, books, loans, members |
| [s05_logistics](schemas/s05_logistics.sql) | Shipment tracking | carriers, customers, shipments, tracking_events |
| [s06_clinic](schemas/s06_clinic.sql) | Clinic appointments and collections | appointments, clinicians, patients, payments |
| [s07_banking](schemas/s07_banking.sql) | Account ledger and statement reconciliation | accounts, customers, ledger_entries, statements |
| [s08_subscriptions](schemas/s08_subscriptions.sql) | Subscription billing and usage | customers, invoices, plans, subscriptions, usage_events |
| [s09_support](schemas/s09_support.sql) | Customer support | agents, customers, teams, ticket_events, tickets |
| [s10_hospitality](schemas/s10_hospitality.sql) | Hotel stays and payments | bookings, guests, payments, rooms |
| [s11_manufacturing](schemas/s11_manufacturing.sql) | Manufacturing bills of materials | bom, parts, work_orders |
| [s12_inventory](schemas/s12_inventory.sql) | Warehouse inventory and movements | movements, products, stock, warehouses |
| [s13_energy](schemas/s13_energy.sql) | Energy meter readings and historical tariffs | meters, readings, sites, tariffs |
| [s14_transport](schemas/s14_transport.sql) | Transit routes, stops, and trips | route_stops, routes, stops, trips |
| [s15_web_analytics](schemas/s15_web_analytics.sql) | Website visitors, sessions, and events | events, sessions, visitors |
| [s16_marketplace](schemas/s16_marketplace.sql) | Marketplace auctions | bids, listings, users |
| [s17_surveys](schemas/s17_surveys.sql) | Survey participation | participants, questions, responses |
| [s18_sports](schemas/s18_sports.sql) | League matches | appearances, matches, players, teams |
| [s19_experiments](schemas/s19_experiments.sql) | Scientific experiments | experiments, measurements, metrics, runs |
| [s20_projects](schemas/s20_projects.sql) | Project tasks and dependencies | dependencies, people, projects, tasks, time_entries |

## s01_retail — Retail orders

Customers, catalog products, orders, and historical item prices. Includes cancelled orders, an empty order, unsold products, and customers without orders.

[DDL and seed data](schemas/s01_retail.sql)

### s01_q01 · easy

List product ID, name, and current catalog price for products priced at least 50, ordered by product ID.

Coverage: select, filter, order_by.

```sql
SELECT id,
       name,
       price
FROM products
WHERE price >= 50
ORDER BY id;
```

### s01_q02 · easy

Count orders in each status. Return status and order count, sorted alphabetically by status.

Coverage: aggregation, group_by, order_by.

```sql
SELECT status,
       COUNT(*) AS order_count
FROM orders
GROUP BY status
ORDER BY status;
```

### s01_q03 · easy

Which customer regions are present? Return each distinct region once, alphabetically.

Coverage: distinct, order_by.

```sql
SELECT DISTINCT region
FROM customers
ORDER BY region;
```

### s01_q04 · medium

Return every customer ID, name, and completed-order revenue rounded to two decimals, including zero for customers without completed sales. Use item quantities and historical unit prices. Sort by customer ID.

Coverage: left_join, aggregation, group_by, nulls, historical_values.

```sql
SELECT c.id,
       c.name,
       ROUND(COALESCE(SUM(i.quantity * i.unit_price), 0), 2) AS revenue
FROM customers c
LEFT JOIN orders o ON o.customer_id = c.id
AND o.status = 'completed'
LEFT JOIN order_items i ON i.order_id = o.id
GROUP BY c.id,
         c.name
ORDER BY c.id;
```

### s01_q05 · medium

Which three products sold the most units in completed orders? Return product ID, name, and units. Exclude products without completed item lines; sort units descending, then product ID ascending.

Coverage: inner_join, aggregation, group_by, top_n.

```sql
SELECT p.id,
       p.name,
       SUM(i.quantity) AS units
FROM products p
JOIN order_items i ON i.product_id = p.id
JOIN orders o ON o.id = i.order_id
WHERE o.status = 'completed'
GROUP BY p.id,
         p.name
ORDER BY units DESC,
         p.id
LIMIT 3;
```

### s01_q06 · medium

Which completed orders have an item total strictly above 100? Return order ID and total rounded to two decimals, sorted by order ID. Calculate totals from quantity times historical unit price.

Coverage: inner_join, aggregation, having, historical_values.

```sql
SELECT o.id,
       ROUND(SUM(i.quantity * i.unit_price), 2) AS order_total
FROM orders o
JOIN order_items i ON i.order_id = o.id
WHERE o.status = 'completed'
GROUP BY o.id
HAVING SUM(i.quantity * i.unit_price) > 100
ORDER BY o.id;
```

### s01_q07 · medium

Which customers have both a completed order and a cancelled order? Return customer ID and name once each, ordered by ID.

Coverage: exists, correlated_subquery.

```sql
SELECT c.id,
       c.name
FROM customers c
WHERE EXISTS
        (SELECT 1
         FROM orders o
         WHERE o.customer_id = c.id
             AND o.status = 'completed')
    AND EXISTS
        (SELECT 1
         FROM orders o
         WHERE o.customer_id = c.id
             AND o.status = 'cancelled')
ORDER BY c.id;
```

### s01_q08 · hard

For each month with completed orders, return YYYY-MM, revenue rounded to two decimals, and percentage change from the previous month present in the result, rounded to two decimals. Revenue uses historical item prices; empty orders contribute zero. Return NULL for the first change or a zero prior revenue. Sort by month.

Coverage: cte, left_join, window, lag, percentage, nulls, date_grouping.

```sql
WITH monthly AS
    (SELECT strftime('%Y-%m', o.ordered_at) AS MONTH,
            COALESCE(SUM(i.quantity * i.unit_price), 0) AS revenue
     FROM orders o
     LEFT JOIN order_items i ON i.order_id = o.id
     WHERE o.status = 'completed'
     GROUP BY MONTH),
     changes AS
    (SELECT MONTH,
            revenue,
            LAG(revenue) OVER (
                               ORDER BY MONTH) AS previous_revenue
     FROM monthly)
SELECT MONTH,
       ROUND(revenue, 2) AS revenue,
       ROUND(100.0 * (revenue - previous_revenue) / NULLIF(previous_revenue, 0), 2) AS growth_pct
FROM changes
ORDER BY MONTH;
```

### s01_q09 · hard

Find the product or products with the highest completed-order revenue within each category, including ties. Include all catalog products in the comparison with zero revenue when unsold. Return category, product ID, name, and revenue rounded to two decimals; sort category then product ID. Use historical item prices.

Coverage: cte, left_join, conditional_aggregation, window, dense_rank, ties.

```sql
WITH totals AS
    (SELECT p.id,
            p.name,
            p.category,
            COALESCE(SUM(CASE
                             WHEN o.status = 'completed' THEN i.quantity * i.unit_price
                             ELSE 0
                         END), 0) AS revenue
     FROM products p
     LEFT JOIN order_items i ON i.product_id = p.id
     LEFT JOIN orders o ON o.id = i.order_id
     GROUP BY p.id,
              p.name,
              p.category),
     ranked AS
    (SELECT *,
            DENSE_RANK() OVER (PARTITION BY category
                               ORDER BY revenue DESC) AS POSITION
     FROM totals)
SELECT category,
       id,
       name,
       ROUND(revenue, 2) AS revenue
FROM ranked
WHERE POSITION = 1
ORDER BY category,
         id;
```

### s01_q10 · hard

Which customers have bought every catalog product in the Home category through completed orders? Require the Home category to contain at least one product. Return customer ID and name, ordered by ID.

Coverage: relational_division, exists, not_exists, correlated_subquery, inner_join.

```sql
SELECT c.id,
       c.name
FROM customers c
WHERE EXISTS
        (SELECT 1
         FROM products
         WHERE category = 'Home')
    AND NOT EXISTS
        (SELECT 1
         FROM products p
         WHERE p.category = 'Home'
             AND NOT EXISTS
                 (SELECT 1
                  FROM orders o
                  JOIN order_items i ON i.order_id = o.id
                  WHERE o.customer_id = c.id
                      AND o.status = 'completed'
                      AND i.product_id = p.id))
ORDER BY c.id;
```

## s02_hr — People and projects

Employee reporting hierarchy, departments, projects and dated work logs. Includes unassigned staff, empty departments, salary ties and employees without logged work.

[DDL and seed data](schemas/s02_hr.sql)

### s02_q01 · easy

List employee ID and name for employees hired from 2021-01-01 through 2022-12-31 inclusive, ordered by employee ID.

Coverage: select, filter, between, date_filter.

```sql
SELECT id,
       name
FROM employees
WHERE hired_at BETWEEN '2021-01-01' AND '2022-12-31'
ORDER BY id;
```

### s02_q02 · easy

Return each department ID, name, and average salary rounded to two decimals. Include departments without employees with NULL average salary; order by department ID.

Coverage: left_join, aggregation, nulls.

```sql
SELECT d.id,
       d.name,
       ROUND(AVG(e.salary), 2) AS average_salary
FROM departments d
LEFT JOIN employees e ON e.department_id = d.id
GROUP BY d.id,
         d.name
ORDER BY d.id;
```

### s02_q03 · easy

Return every distinct employee job title, sorted alphabetically.

Coverage: distinct, order_by.

```sql
SELECT DISTINCT title
FROM employees
ORDER BY title;
```

### s02_q04 · medium

For every employee, return employee ID, employee name, and direct manager name. Return NULL manager name when there is no manager. Order by employee ID.

Coverage: self_join, left_join, nulls.

```sql
SELECT e.id,
       e.name,
       m.name AS manager_name
FROM employees e
LEFT JOIN employees m ON m.id = e.manager_id
ORDER BY e.id;
```

### s02_q05 · medium

Which employees earn strictly more than the average salary in their own department? Exclude unassigned employees. Return employee ID, name, department ID, and salary; sort by employee ID.

Coverage: correlated_subquery, aggregation.

```sql
SELECT e.id,
       e.name,
       e.department_id,
       e.salary
FROM employees e
WHERE e.salary >
        (SELECT AVG(peer.salary)
         FROM employees peer
         WHERE peer.department_id = e.department_id)
ORDER BY e.id;
```

### s02_q06 · medium

Return every department ID, name, and total hours logged by its own employees in May 2025, including zero for departments without matching logs. Attribute hours to the employee department regardless of the project department. Sort by department ID.

Coverage: left_join, aggregation, date_filter, nulls.

```sql
SELECT d.id,
       d.name,
       COALESCE(SUM(w.hours), 0) AS hours
FROM departments d
LEFT JOIN employees e ON e.department_id = d.id
LEFT JOIN work_logs w ON w.employee_id = e.id
AND w.worked_at >= '2025-05-01'
AND w.worked_at < '2025-06-01'
GROUP BY d.id,
         d.name
ORDER BY d.id;
```

### s02_q07 · medium

Which employees have no work logs during May 2025? Return employee ID and name, ordered by ID.

Coverage: not_exists, correlated_subquery, anti_join.

```sql
SELECT e.id,
       e.name
FROM employees e
WHERE NOT EXISTS
        (SELECT 1
         FROM work_logs w
         WHERE w.employee_id = e.id
             AND w.worked_at >= '2025-05-01'
             AND w.worked_at < '2025-06-01')
ORDER BY e.id;
```

### s02_q08 · hard

Trace the reporting chain above employee 7. Return manager employee ID, manager name, and distance, where the direct manager is distance 1. Exclude employee 7; sort by distance ascending.

Coverage: recursive_cte, self_join, union_all.

```sql
WITH RECURSIVE chain(id, name, manager_id, distance) AS
    (SELECT m.id,
            m.name,
            m.manager_id,
            1
     FROM employees e
     JOIN employees m ON m.id = e.manager_id
     WHERE e.id = 7
     UNION ALL SELECT m.id,
                      m.name,
                      m.manager_id,
                      c.distance + 1
     FROM CHAIN c
     JOIN employees m ON m.id = c.manager_id)
SELECT id,
       name,
       distance
FROM CHAIN
ORDER BY distance;
```

### s02_q09 · hard

Within each non-NULL department, return employees in the top two distinct salary levels, including everyone tied at either level. Return department ID, employee ID, name, salary, and dense salary rank. Sort by department ID, rank, then employee ID.

Coverage: cte, window, dense_rank, ties, top_n.

```sql
WITH ranked AS
    (SELECT department_id,
            id,
            name,
            salary,
            DENSE_RANK() OVER (PARTITION BY department_id
                               ORDER BY salary DESC) AS salary_rank
     FROM employees
     WHERE department_id IS NOT NULL)
SELECT department_id,
       id,
       name,
       salary,
       salary_rank
FROM ranked
WHERE salary_rank <= 2
ORDER BY department_id,
         salary_rank,
         id;
```

### s02_q10 · hard

For each employee assigned to a department, return department ID, employee ID, name, all-time logged hours, and percentage of that department's logged hours rounded to two decimals. Include employees with zero hours; return 0 percent when a department has no hours. Sort by department ID then employee ID.

Coverage: cte, window, left_join, percentage, nulls.

```sql
WITH totals AS
    (SELECT e.department_id,
            e.id,
            e.name,
            COALESCE(SUM(w.hours), 0) AS hours
     FROM employees e
     LEFT JOIN work_logs w ON w.employee_id = e.id
     WHERE e.department_id IS NOT NULL
     GROUP BY e.id,
              e.department_id,
              e.name)
SELECT department_id,
       id,
       name,
       hours,
       COALESCE(ROUND(100.0 * hours / NULLIF(SUM(hours) OVER (PARTITION BY department_id), 0), 2), 0) AS percentage
FROM totals
ORDER BY department_id,
         id;
```

## s03_education — Course enrollment

Students, instructors, catalog courses and term enrollments. Includes required and optional courses, repeat enrollments, missing grades, withdrawals and unstaffed courses.

[DDL and seed data](schemas/s03_education.sql)

### s03_q01 · easy

Return ID and name of students majoring in CS or Math whose names contain the letter a, ignoring ASCII case. Order by student ID.

Coverage: filter, in_filter, like, string_functions, order_by.

```sql
SELECT id,
       name
FROM students
WHERE major IN ('CS',
                'Math')
    AND LOWER(name) LIKE '%a%'
ORDER BY id;
```

### s03_q02 · easy

Sort all courses by credits descending, breaking ties by course ID ascending. Return the third and fourth rows of that ordering, with course ID, title, and credits in that order.

Coverage: order_by, limit, offset, ties.

```sql
SELECT id,
       title,
       credits
FROM courses
ORDER BY credits DESC,
         id
LIMIT 2
OFFSET 2;
```

### s03_q03 · easy

Count enrollment records in each status across all terms. Return status and count, ordered by status.

Coverage: group_by, aggregation.

```sql
SELECT status,
       COUNT(*) AS enrollment_count
FROM enrollments
GROUP BY status
ORDER BY status;
```

### s03_q04 · medium

For every student, return student ID, name, and credit-weighted average score rounded to two decimals across completed enrollments with a non-NULL score. Count repeat completions separately. Return NULL when no eligible grades exist. Sort by student ID.

Coverage: left_join, aggregation, weighted_average, nulls.

```sql
SELECT s.id,
       s.name,
       ROUND(SUM(e.score * c.credits) / SUM(c.credits), 2) AS weighted_score
FROM students s
LEFT JOIN enrollments e ON e.student_id = s.id
AND e.status = 'completed'
AND e.score IS NOT NULL
LEFT JOIN courses c ON c.id = e.course_id
GROUP BY s.id,
         s.name
ORDER BY s.id;
```

### s03_q05 · medium

For every course, return course ID, title, and number of non-withdrawn enrollment records in 2025-Spring, including zero. Sort by course ID.

Coverage: left_join, aggregation, nulls.

```sql
SELECT c.id,
       c.title,
       COUNT(e.student_id) AS enrollment_count
FROM courses c
LEFT JOIN enrollments e ON e.course_id = c.id
AND e.term = '2025-Spring'
AND e.status <> 'withdrawn'
GROUP BY c.id,
         c.title
ORDER BY c.id;
```

### s03_q06 · medium

Which students have never completed any enrollment? Return student ID and name, sorted by ID.

Coverage: not_exists, anti_join.

```sql
SELECT s.id,
       s.name
FROM students s
WHERE NOT EXISTS
        (SELECT 1
         FROM enrollments e
         WHERE e.student_id = s.id
             AND e.status = 'completed')
ORDER BY s.id;
```

### s03_q07 · medium

For every instructor, return instructor ID, name, number of assigned catalog courses, and total credits of those courses. Include instructors with no courses using zero counts and zero credits. Count each catalog course once regardless of enrollments; sort by instructor ID.

Coverage: left_join, aggregation, group_by.

```sql
SELECT i.id,
       i.name,
       COUNT(c.id) AS course_count,
       COALESCE(SUM(c.credits), 0) AS credits
FROM instructors i
LEFT JOIN courses c ON c.instructor_id = i.id
GROUP BY i.id,
         i.name
ORDER BY i.id;
```

### s03_q08 · hard

Which students have completed every required course in their own major in any term? Exclude majors with no required courses. Return student ID and name, sorted by ID.

Coverage: relational_division, exists, not_exists, correlated_subquery.

```sql
SELECT s.id,
       s.name
FROM students s
WHERE EXISTS
        (SELECT 1
         FROM courses c
         WHERE c.major = s.major
             AND c.is_required = 1)
    AND NOT EXISTS
        (SELECT 1
         FROM courses c
         WHERE c.major = s.major
             AND c.is_required = 1
             AND NOT EXISTS
                 (SELECT 1
                  FROM enrollments e
                  WHERE e.student_id = s.id
                      AND e.course_id = c.id
                      AND e.status = 'completed'))
ORDER BY s.id;
```

### s03_q09 · hard

For each term, find the course or courses with the highest average score among completed enrollments with non-NULL scores, retaining ties before rounding. Return term, course ID, title, and average score rounded to two decimals; sort by term then course ID.

Coverage: cte, window, rank, ties, aggregation, inner_join.

```sql
WITH averages AS
    (SELECT term,
            course_id,
            AVG(score) AS average_score
     FROM enrollments
     WHERE status = 'completed'
         AND score IS NOT NULL
     GROUP BY term,
              course_id),
     ranked AS
    (SELECT *,
            RANK() OVER (PARTITION BY term
                         ORDER BY average_score DESC) AS POSITION
     FROM averages)
SELECT r.term,
       c.id,
       c.title,
       ROUND(r.average_score, 2) AS average_score
FROM ranked r
JOIN courses c ON c.id = r.course_id
WHERE r.position = 1
ORDER BY r.term,
         c.id;
```

### s03_q10 · hard

Among distinct students with a non-withdrawn enrollment in 2024-Fall, how many also have a non-withdrawn enrollment in 2025-Spring? Return one row with cohort student count, retained student count, and retention percent rounded to two decimals. A student counts once per group; return NULL percent for an empty cohort.

Coverage: cte, distinct, exists, scalar_subquery, percentage.

```sql
WITH cohort AS
    (SELECT DISTINCT student_id
     FROM enrollments
     WHERE term = '2024-Fall'
         AND status <> 'withdrawn'),
     retained AS
    (SELECT student_id
     FROM cohort
     WHERE EXISTS
             (SELECT 1
              FROM enrollments e
              WHERE e.student_id = cohort.student_id
                  AND e.term = '2025-Spring'
                  AND e.status <> 'withdrawn'))
SELECT
    (SELECT COUNT(*)
     FROM cohort) AS cohort_count,

    (SELECT COUNT(*)
     FROM retained) AS retained_count,
       ROUND(100.0 *
                 (SELECT COUNT(*)
                  FROM retained) / NULLIF(
                                              (SELECT COUNT(*)
                                               FROM cohort), 0), 2) AS retention_pct;
```

## s04_library — Library circulation

Authors, book titles, members and dated loans. Includes unborrowed titles, future loans and returns, overdue loans, tied dates and members without activity.

[DDL and seed data](schemas/s04_library.sql)

### s04_q01 · easy

List book ID, title, and publication year for all books, ordered by publication year descending then book ID ascending.

Coverage: select, order_by.

```sql
SELECT id,
       title,
       published_year
FROM books
ORDER BY published_year DESC,
         id;
```

### s04_q02 · easy

Which loans were active at the end of 2025-06-30? A loan is active if loaned on or before that date and not returned by that date. Return loan ID and book ID, ordered by loan ID.

Coverage: filter, nulls, date_filter.

```sql
SELECT id,
       book_id
FROM loans
WHERE loaned_at <= '2025-06-30'
    AND (returned_at IS NULL
         OR returned_at > '2025-06-30')
ORDER BY id;
```

### s04_q03 · easy

Return author ID, author name, and number of catalog book titles for every author, including authors with zero titles. Order by author ID.

Coverage: left_join, aggregation, group_by.

```sql
SELECT a.id,
       a.name,
       COUNT(b.id) AS title_count
FROM authors a
LEFT JOIN books b ON b.author_id = a.id
GROUP BY a.id,
         a.name
ORDER BY a.id;
```

### s04_q04 · medium

For loans active at the end of 2025-06-30 whose due date is strictly earlier than that date, return loan ID, member name, book title, and integer days overdue as of 2025-06-30. A return after that date still counts as active. Sort by loan ID.

Coverage: inner_join, date_arithmetic, nulls.

```sql
SELECT l.id,
       m.name,
       b.title,
       CAST(julianday('2025-06-30') - julianday(l.due_at) AS INTEGER) AS days_overdue
FROM loans l
JOIN members m ON m.id = l.member_id
JOIN books b ON b.id = l.book_id
WHERE l.loaned_at <= '2025-06-30'
    AND (l.returned_at IS NULL
         OR l.returned_at > '2025-06-30')
    AND l.due_at < '2025-06-30'
ORDER BY l.id;
```

### s04_q05 · medium

For every member, return member ID, name, returned-loan count, and average loan duration in days rounded to two decimals. Use all loans with a recorded return, including July returns. Return zero count and NULL average when none are returned; sort by member ID.

Coverage: left_join, aggregation, date_arithmetic, nulls.

```sql
SELECT m.id,
       m.name,
       COUNT(l.id) AS returned_count,
       ROUND(AVG(julianday(l.returned_at) - julianday(l.loaned_at)), 2) AS average_days
FROM members m
LEFT JOIN loans l ON l.member_id = m.id
AND l.returned_at IS NOT NULL
GROUP BY m.id,
         m.name
ORDER BY m.id;
```

### s04_q06 · medium

Find all book titles tied for the highest number of loan records across all dates. Exclude titles never borrowed. Return book ID, title, and loan count; order by book ID.

Coverage: cte, scalar_subquery, aggregation, ties.

```sql
WITH counts AS
    (SELECT b.id,
            b.title,
            COUNT(*) AS loan_count
     FROM books b
     JOIN loans l ON l.book_id = b.id
     GROUP BY b.id,
              b.title)
SELECT id,
       title,
       loan_count
FROM counts
WHERE loan_count =
        (SELECT MAX(loan_count)
         FROM counts)
ORDER BY id;
```

### s04_q07 · medium

Which members have borrowed titles from at least two different authors across all dates? Return member ID and name, ordered by member ID.

Coverage: inner_join, in_subquery, distinct, having, aggregation.

```sql
SELECT m.id,
       m.name
FROM members m
WHERE m.id IN
        (SELECT l.member_id
         FROM loans l
         JOIN books b ON b.id = l.book_id
         GROUP BY l.member_id
         HAVING COUNT(DISTINCT b.author_id) >= 2)
ORDER BY m.id;
```

### s04_q08 · hard

For each loan, return member ID, loan ID, loan date, and integer days since that member's previous loan date. Order a member's loans by loan date then loan ID, and use NULL for the first loan. Sort the result by member ID, loan date, then loan ID.

Coverage: window, lag, date_arithmetic, nulls.

```sql
SELECT member_id,
       id,
       loaned_at,
       CAST(julianday(loaned_at) - julianday(LAG(loaned_at) OVER (PARTITION BY member_id
                                                                  ORDER BY loaned_at, id)) AS INTEGER) AS gap_days
FROM loans
ORDER BY member_id,
         loaned_at,
         id;
```

### s04_q09 · hard

For each book, return book ID, title, and copies available at the end of 2025-06-30. Subtract loans started on or before that date and not returned by that date from total copies. Include titles with no active loans; order by book ID.

Coverage: left_join, conditional_aggregation, date_filter, nulls.

```sql
SELECT b.id,
       b.title,
       b.total_copies - COUNT(l.id) AS available_copies
FROM books b
LEFT JOIN loans l ON l.book_id = b.id
AND l.loaned_at <= '2025-06-30'
AND (l.returned_at IS NULL
     OR l.returned_at > '2025-06-30')
GROUP BY b.id,
         b.title,
         b.total_copies
ORDER BY b.id;
```

### s04_q10 · hard

Which members have borrowed every catalog title by author 1 at least once across all dates? Require author 1 to have at least one title. Return member ID and name, ordered by ID.

Coverage: relational_division, exists, not_exists, correlated_subquery.

```sql
SELECT m.id,
       m.name
FROM members m
WHERE EXISTS
        (SELECT 1
         FROM books
         WHERE author_id = 1)
    AND NOT EXISTS
        (SELECT 1
         FROM books b
         WHERE b.author_id = 1
             AND NOT EXISTS
                 (SELECT 1
                  FROM loans l
                  WHERE l.member_id = m.id
                      AND l.book_id = b.id))
ORDER BY m.id;
```

## s05_logistics — Shipment tracking

Customers, carriers, shipments and timestamped tracking events. Includes unassigned shipments, unused carriers, late deliveries, missing events and tied event timestamps.

[DDL and seed data](schemas/s05_logistics.sql)

### s05_q01 · easy

Return shipment ID and weight for in-transit shipments weighing at least 5 kilograms, ordered by shipment ID.

Coverage: filter, order_by.

```sql
SELECT id,
       weight_kg
FROM shipments
WHERE status = 'in_transit'
    AND weight_kg >= 5
ORDER BY id;
```

### s05_q02 · easy

Return every carrier ID, name, and total assigned shipment count across all statuses, including zero. Order by carrier ID.

Coverage: left_join, aggregation.

```sql
SELECT c.id,
       c.name,
       COUNT(s.id) AS shipment_count
FROM carriers c
LEFT JOIN shipments s ON s.carrier_id = c.id
GROUP BY c.id,
         c.name
ORDER BY c.id;
```

### s05_q03 · easy

Return each distinct tracking-event type in uppercase with underscores replaced by spaces, sorted alphabetically by the formatted value.

Coverage: distinct, string_functions, order_by.

```sql
SELECT DISTINCT UPPER(REPLACE(event_type, '_', ' ')) AS event_label
FROM tracking_events
ORDER BY event_label;
```

### s05_q04 · medium

Which delivered shipments arrived strictly after their promised timestamp? Return shipment ID, customer name, and hours late rounded to two decimals; sort by shipment ID.

Coverage: inner_join, date_arithmetic, filter.

```sql
SELECT s.id,
       c.name,
       ROUND((julianday(s.delivered_at) - julianday(s.promised_at)) * 24, 2) AS hours_late
FROM shipments s
JOIN customers c ON c.id = s.customer_id
WHERE s.status = 'delivered'
    AND s.delivered_at > s.promised_at
ORDER BY s.id;
```

### s05_q05 · medium

For every carrier, return carrier ID, name, and total cost divided by total weight of its non-cancelled shipments, rounded to two decimals. Return NULL when total weight is zero or no eligible shipments exist. Sort by carrier ID.

Coverage: left_join, aggregation, weighted_average, nulls.

```sql
SELECT c.id,
       c.name,
       ROUND(SUM(s.cost) / NULLIF(SUM(s.weight_kg), 0), 2) AS cost_per_kg
FROM carriers c
LEFT JOIN shipments s ON s.carrier_id = c.id
AND s.status <> 'cancelled'
GROUP BY c.id,
         c.name
ORDER BY c.id;
```

### s05_q06 · medium

Which customers have used at least two different non-NULL carriers on non-cancelled shipments? Return customer ID, name, and distinct carrier count; sort by customer ID.

Coverage: inner_join, distinct, having.

```sql
SELECT c.id,
       c.name,
       COUNT(DISTINCT s.carrier_id) AS carrier_count
FROM customers c
JOIN shipments s ON s.customer_id = c.id
WHERE s.status <> 'cancelled'
GROUP BY c.id,
         c.name
HAVING COUNT(DISTINCT s.carrier_id) >= 2
ORDER BY c.id;
```

### s05_q07 · medium

Which non-cancelled shipments have no tracking events? Return shipment ID and customer name, ordered by shipment ID.

Coverage: inner_join, not_exists, anti_join.

```sql
SELECT s.id,
       c.name
FROM shipments s
JOIN customers c ON c.id = s.customer_id
WHERE s.status <> 'cancelled'
    AND NOT EXISTS
        (SELECT 1
         FROM tracking_events e
         WHERE e.shipment_id = s.id)
ORDER BY s.id;
```

### s05_q08 · hard

For every shipment, return shipment ID, latest event type, and latest event timestamp. Choose the highest event ID when timestamps tie; return NULL event fields when no events exist. Sort by shipment ID.

Coverage: cte, window, row_number, left_join, ties.

```sql
WITH ranked AS
    (SELECT *,
            ROW_NUMBER() OVER (PARTITION BY shipment_id
                               ORDER BY occurred_at DESC, id DESC) AS POSITION
     FROM tracking_events)
SELECT s.id,
       e.event_type,
       e.occurred_at
FROM shipments s
LEFT JOIN ranked e ON e.shipment_id = s.id
AND e.position = 1
ORDER BY s.id;
```

### s05_q09 · hard

For shipments with both picked_up and delivered tracking events, return shipment ID and hours from the first picked_up event to the first delivered event rounded to two decimals. Use event timestamps, not shipment timestamps; sort by shipment ID.

Coverage: conditional_aggregation, having, date_arithmetic.

```sql
SELECT shipment_id,
       ROUND((julianday(MIN(CASE
                                WHEN event_type = 'delivered' THEN occurred_at
                            END)) - julianday(MIN(CASE
                                                      WHEN event_type = 'picked_up' THEN occurred_at
                                                  END))) * 24, 2) AS hours_elapsed
FROM tracking_events
GROUP BY shipment_id
HAVING COUNT(CASE
                 WHEN event_type = 'picked_up' THEN 1
             END) > 0
AND COUNT(CASE
              WHEN event_type = 'delivered' THEN 1
          END) > 0
ORDER BY shipment_id;
```

### s05_q10 · hard

For each non-NULL carrier and each shipping date with non-cancelled shipments, return carrier ID, shipping date as YYYY-MM-DD, daily shipped weight, and cumulative shipped weight through that date for the carrier. Do not add missing dates. Sort by carrier ID then date.

Coverage: cte, window, running_total, date_grouping.

```sql
WITH daily AS
    (SELECT carrier_id,
            date(shipped_at) AS shipped_date,
            SUM(weight_kg) AS daily_weight
     FROM shipments
     WHERE carrier_id IS NOT NULL
         AND status <> 'cancelled'
     GROUP BY carrier_id,
              date(shipped_at))
SELECT carrier_id,
       shipped_date,
       daily_weight,
       SUM(daily_weight) OVER (PARTITION BY carrier_id
                               ORDER BY shipped_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cumulative_weight
FROM daily
ORDER BY carrier_id,
         shipped_date;
```

## s06_clinic — Clinic appointments and collections

Fictional clinic appointments with completed, cancelled, scheduled, and no-show visits. Fees are per appointment; payments may be partial or split. A payment with NULL appointment_id is unallocated. Monetary values use one currency; timestamps are UTC. Patients and clinicians without appointments are intentional.

[DDL and seed data](schemas/s06_clinic.sql)

### s06_q01 · easy

List patients with a known city. Return patient_id, name, and city, ordered by name and then patient_id.

Coverage: filter, nulls, order_by.

```sql
SELECT patient_id,
       name,
       city
FROM patients
WHERE city IS NOT NULL
ORDER BY name,
         patient_id;
```

### s06_q02 · easy

Which completed appointments have a fee greater than 100? Return appointment_id and fee, ordered by fee descending and then appointment_id.

Coverage: filter, order_by.

```sql
SELECT appointment_id,
       fee
FROM appointments
WHERE status = 'completed'
    AND fee > 100
ORDER BY fee DESC,
         appointment_id;
```

### s06_q03 · easy

Count appointments in each status. Return status and appointment_count, ordered alphabetically by status.

Coverage: group_by, count.

```sql
SELECT status,
       COUNT(*) AS appointment_count
FROM appointments
GROUP BY status
ORDER BY status;
```

### s06_q04 · medium

For every patient, including those with no appointments, show patient_id, name, and the number of appointments of any status. Use zero for no appointments and order by patient_id.

Coverage: left_join, group_by, count, zero_inclusion.

```sql
SELECT p.patient_id,
       p.name,
       COUNT(a.appointment_id) AS appointment_count
FROM patients p
LEFT JOIN appointments a ON a.patient_id = p.patient_id
GROUP BY p.patient_id,
         p.name
ORDER BY p.patient_id;
```

### s06_q05 · medium

Find clinicians with at least two completed appointments. Return clinician_id, name, completed_count, and average completed-appointment fee rounded to two decimals. Order by clinician_id.

Coverage: inner_join, group_by, having, avg.

```sql
SELECT c.clinician_id,
       c.name,
       COUNT(*) AS completed_count,
       ROUND(AVG(a.fee), 2) AS average_fee
FROM clinicians c
JOIN appointments a ON a.clinician_id = c.clinician_id
WHERE a.status = 'completed'
GROUP BY c.clinician_id,
         c.name
HAVING COUNT(*) >= 2
ORDER BY c.clinician_id;
```

### s06_q06 · medium

For every completed appointment, return appointment_id, patient name, fee, total payments, and balance_due. Balance is fee minus payments; keep negative balances for overpayments and use zero payments when none exist. Round payments and balance to two decimals and order by appointment_id.

Coverage: inner_join, left_join, group_by, sum, coalesce, one_to_many.

```sql
SELECT a.appointment_id,
       p.name,
       a.fee,
       ROUND(COALESCE(SUM(pay.amount), 0), 2) AS total_payments,
       ROUND(a.fee - COALESCE(SUM(pay.amount), 0), 2) AS balance_due
FROM appointments a
JOIN patients p ON p.patient_id = a.patient_id
LEFT JOIN payments pay ON pay.appointment_id = a.appointment_id
WHERE a.status = 'completed'
GROUP BY a.appointment_id,
         p.name,
         a.fee
ORDER BY a.appointment_id;
```

### s06_q07 · medium

Show every clinician, including clinicians without completed appointments, with clinician_id, name, and completed_count. Count only completed appointments and order by clinician_id.

Coverage: right_join, group_by, count, zero_inclusion, join_filter.

```sql
SELECT c.clinician_id,
       c.name,
       COUNT(a.appointment_id) AS completed_count
FROM appointments a
RIGHT JOIN clinicians c ON a.clinician_id = c.clinician_id
AND a.status = 'completed'
GROUP BY c.clinician_id,
         c.name
ORDER BY c.clinician_id;
```

### s06_q08 · hard

Produce a reconciliation list containing every appointment and every payment, matching payments to appointments when possible. Keep one row per matched payment, appointments with no payment, and unallocated payments. Return appointment_id, payment_id, and amount; leave missing values NULL. Order by appointment_id with NULLs last, then payment_id.

Coverage: full_outer_join, nulls, one_to_many, reconciliation.

```sql
SELECT a.appointment_id,
       p.payment_id,
       p.amount
FROM appointments a
FULL OUTER JOIN payments p ON p.appointment_id = a.appointment_id
ORDER BY a.appointment_id IS NULL,
                             a.appointment_id,
                             p.payment_id;
```

### s06_q09 · hard

Within each specialty, find the completed appointment or appointments with the highest fee, including ties. Return specialty, appointment_id, and fee, ordered by specialty and then appointment_id.

Coverage: cte, inner_join, window, dense_rank, ties.

```sql
WITH ranked AS
    (SELECT c.specialty,
            a.appointment_id,
            a.fee,
            DENSE_RANK() OVER (PARTITION BY c.specialty
                               ORDER BY a.fee DESC) AS fee_rank
     FROM appointments a
     JOIN clinicians c ON c.clinician_id = a.clinician_id
     WHERE a.status = 'completed')
SELECT specialty,
       appointment_id,
       fee
FROM ranked
WHERE fee_rank = 1
ORDER BY specialty,
         appointment_id;
```

### s06_q10 · hard

Which patients have at least one completed appointment and have fully paid every completed appointment? An appointment is fully paid when its summed payments are at least its fee; missing payments count as zero. Ignore appointments of other statuses. Return patient_id and name, ordered by patient_id.

Coverage: correlated_subquery, exists, not_exists, sum, coalesce, universal_condition.

```sql
SELECT p.patient_id,
       p.name
FROM patients p
WHERE EXISTS
        (SELECT 1
         FROM appointments a
         WHERE a.patient_id = p.patient_id
             AND a.status = 'completed')
    AND NOT EXISTS
        (SELECT 1
         FROM appointments a
         WHERE a.patient_id = p.patient_id
             AND a.status = 'completed'
             AND COALESCE(
                              (SELECT SUM(pay.amount)
                               FROM payments pay
                               WHERE pay.appointment_id = a.appointment_id), 0) < a.fee)
ORDER BY p.patient_id;
```

## s07_banking — Account ledger and statement reconciliation

Fictional accounts with opening balances and a signed ledger: positive amounts add funds and negative amounts remove funds. Ledger entries are historical postings. Imported statements intentionally have no account foreign key, because an external account number can be unmatched. All statements are dated 2025-03-31; ledger postings also include a later posting. Monetary values use one currency.

[DDL and seed data](schemas/s07_banking.sql)

### s07_q01 · easy

List open checking accounts. Return account_id and account_number, ordered by account_id.

Coverage: filter, order_by.

```sql
SELECT account_id,
       account_number
FROM accounts
WHERE status = 'open'
    AND kind = 'checking'
ORDER BY account_id;
```

### s07_q02 · easy

List withdrawal entries posted during March 2025. Return entry_id, account_id, posted_at, and the signed amount, ordered by posted_at and then entry_id.

Coverage: filter, date_range, order_by.

```sql
SELECT entry_id,
       account_id,
       posted_at,
       amount
FROM ledger_entries
WHERE entry_type = 'withdrawal'
    AND posted_at >= '2025-03-01'
    AND posted_at < '2025-04-01'
ORDER BY posted_at,
         entry_id;
```

### s07_q03 · easy

Across all ledger entries, show each entry_type, its entry count, and the sum of signed amounts rounded to two decimals. Order by entry_type.

Coverage: group_by, count, sum.

```sql
SELECT entry_type,
       COUNT(*) AS entry_count,
       ROUND(SUM(amount), 2) AS signed_total
FROM ledger_entries
GROUP BY entry_type
ORDER BY entry_type;
```

### s07_q04 · medium

For every customer, return customer_id, name, and the combined current balance of all their accounts, including closed accounts. Current balance is opening_balance plus all ledger entries. Customers without accounts should show zero. Round the combined balance to two decimals and order by customer_id.

Coverage: cte, left_join, group_by, sum, coalesce, fanout_safe.

```sql
WITH account_balances AS
    (SELECT a.account_id,
            a.customer_id,
            a.opening_balance + COALESCE(SUM(l.amount), 0) AS balance
     FROM accounts a
     LEFT JOIN ledger_entries l ON l.account_id = a.account_id
     GROUP BY a.account_id,
              a.customer_id,
              a.opening_balance)
SELECT c.customer_id,
       c.name,
       ROUND(COALESCE(SUM(b.balance), 0), 2) AS combined_balance
FROM customers c
LEFT JOIN account_balances b ON b.customer_id = c.customer_id
GROUP BY c.customer_id,
         c.name
ORDER BY c.customer_id;
```

### s07_q05 · medium

Find accounts with at least two negative ledger entries, including fees as well as withdrawals. Return account_number, negative_entry_count, and the positive total of money removed, rounded to two decimals. Use all posting dates and order by account_number.

Coverage: inner_join, group_by, having, count, sum.

```sql
SELECT a.account_number,
       COUNT(*) AS negative_entry_count,
       ROUND(-SUM(l.amount), 2) AS money_removed
FROM accounts a
JOIN ledger_entries l ON l.account_id = a.account_id
WHERE l.amount < 0
GROUP BY a.account_id,
         a.account_number
HAVING COUNT(*) >= 2
ORDER BY a.account_number;
```

### s07_q06 · medium

For every account, count ledger entries posted on or before March 31, 2025, and sum their signed amounts. Include accounts without qualifying entries with count zero and net change zero. Return account_number, entry_count, and net_change rounded to two decimals, ordered by account_number.

Coverage: right_join, join_filter, group_by, count, sum, zero_inclusion.

```sql
SELECT a.account_number,
       COUNT(l.entry_id) AS entry_count,
       ROUND(COALESCE(SUM(l.amount), 0), 2) AS net_change
FROM ledger_entries l
RIGHT JOIN accounts a ON a.account_id = l.account_id
AND l.posted_at < '2025-04-01'
GROUP BY a.account_id,
         a.account_number
ORDER BY a.account_number;
```

### s07_q07 · medium

Compare each account with its March 31, 2025 statement when the statement ending balance is known. Show only mismatches after rounding both balances to two decimals. The book balance is opening_balance plus postings through March 31. Return account_number, book_balance, statement_balance, and the rounded book balance minus the rounded statement balance as difference. Round every monetary output to two decimals. Order by account_number ascending.

Coverage: cte, left_join, inner_join, group_by, date_range, nulls, reconciliation.

```sql
WITH book AS
    (SELECT a.account_number,
            ROUND(a.opening_balance + COALESCE(SUM(l.amount), 0), 2) AS book_balance
     FROM accounts a
     LEFT JOIN ledger_entries l ON l.account_id = a.account_id
     AND l.posted_at < '2025-04-01'
     GROUP BY a.account_id,
              a.account_number,
              a.opening_balance)
SELECT b.account_number,
       b.book_balance,
       ROUND(s.ending_balance, 2) AS statement_balance,
       ROUND(b.book_balance - ROUND(s.ending_balance, 2), 2) AS difference
FROM book b
JOIN statements s ON s.account_number = b.account_number
WHERE s.statement_date = '2025-03-31'
    AND s.ending_balance IS NOT NULL
    AND b.book_balance <> ROUND(s.ending_balance, 2)
ORDER BY b.account_number;
```

### s07_q08 · hard

Reconcile all local accounts with all imported statements dated March 31, 2025, retaining unmatched records on either side. Return account_number, book_balance, statement_balance, and the rounded book balance minus the rounded statement balance as difference. Book balance uses opening_balance plus postings through March 31. Round monetary outputs to two decimals; use NULL for a missing book balance, a missing or unknown statement balance, and any difference involving NULL. Order by account_number ascending.

Coverage: cte, left_join, full_outer_join, group_by, coalesce, nulls, reconciliation.

```sql
WITH book AS
    (SELECT a.account_number,
            ROUND(a.opening_balance + COALESCE(SUM(l.amount), 0), 2) AS book_balance
     FROM accounts a
     LEFT JOIN ledger_entries l ON l.account_id = a.account_id
     AND l.posted_at < '2025-04-01'
     GROUP BY a.account_id,
              a.account_number,
              a.opening_balance),
     imported AS
    (SELECT account_number,
            ending_balance
     FROM statements
     WHERE statement_date = '2025-03-31')
SELECT COALESCE(b.account_number, s.account_number) AS account_number,
       b.book_balance,
       ROUND(s.ending_balance, 2) AS statement_balance,
       ROUND(b.book_balance - ROUND(s.ending_balance, 2), 2) AS difference
FROM book b
FULL OUTER JOIN imported s ON s.account_number = b.account_number
ORDER BY account_number;
```

### s07_q09 · hard

Show every ledger entry with its account running balance, starting from the account opening balance. Within an account, apply entries in posted_at then entry_id order, including all dates. Return account_number, entry_id, posted_at, and running_balance rounded to two decimals. Order the output by account_number, posted_at, and entry_id.

Coverage: inner_join, window, running_total, ties.

```sql
SELECT a.account_number,
       l.entry_id,
       l.posted_at,
       ROUND(a.opening_balance + SUM(l.amount) OVER (PARTITION BY a.account_id
                                                     ORDER BY l.posted_at, l.entry_id ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW), 2) AS running_balance
FROM accounts a
JOIN ledger_entries l ON l.account_id = a.account_id
ORDER BY a.account_number,
         l.posted_at,
         l.entry_id;
```

### s07_q10 · hard

Find open accounts whose current balance is strictly below the average current balance of open accounts of the same kind. Current balance includes opening_balance and all postings; include accounts with no entries in the comparison. Compare unrounded balances. Return account_number, kind, and current_balance rounded to two decimals, ordered by account_number.

Coverage: cte, left_join, group_by, correlated_subquery, avg, coalesce.

```sql
WITH balances AS
    (SELECT a.account_id,
            a.account_number,
            a.kind,
            a.opening_balance + COALESCE(SUM(l.amount), 0) AS balance
     FROM accounts a
     LEFT JOIN ledger_entries l ON l.account_id = a.account_id
     WHERE a.status = 'open'
     GROUP BY a.account_id,
              a.account_number,
              a.kind,
              a.opening_balance)
SELECT b.account_number,
       b.kind,
       ROUND(b.balance, 2) AS current_balance
FROM balances b
WHERE b.balance <
        (SELECT AVG(other.balance)
         FROM balances other
         WHERE other.kind = b.kind)
ORDER BY b.account_number;
```

## s08_subscriptions — Subscription billing and usage

Fictional subscriptions, plans, invoice amounts, and metered usage. Invoice amount is historical and can differ from a plan current monthly_price. Paid revenue uses paid invoices only. Included units are a monthly plan allowance; each subscription retains its recorded plan throughout these fixtures. Cancelled subscriptions, unused plans, customers without subscriptions, and subscriptions without invoices are intentional.

[DDL and seed data](schemas/s08_subscriptions.sql)

### s08_q01 · easy

List active subscriptions. Return subscription_id, customer_id, plan_id, and start_date, ordered by start_date and then subscription_id.

Coverage: filter, order_by.

```sql
SELECT subscription_id,
       customer_id,
       plan_id,
       start_date
FROM subscriptions
WHERE status = 'active'
ORDER BY start_date,
         subscription_id;
```

### s08_q02 · easy

Which open invoices have an amount of at least 50? Return invoice_id, billed_on, and amount, ordered by amount descending and then invoice_id.

Coverage: filter, order_by.

```sql
SELECT invoice_id,
       billed_on,
       amount
FROM invoices
WHERE status = 'open'
    AND amount >= 50
ORDER BY amount DESC,
         invoice_id;
```

### s08_q03 · easy

Show paid invoice revenue by billing month, using the historical invoice amounts. Return month as YYYY-MM and revenue rounded to two decimals. Include only months with paid invoices and order chronologically.

Coverage: date_grouping, group_by, sum, historical_values.

```sql
SELECT strftime('%Y-%m', billed_on) AS MONTH,
       ROUND(SUM(amount), 2) AS revenue
FROM invoices
WHERE status = 'paid'
GROUP BY MONTH
ORDER BY MONTH;
```

### s08_q04 · medium

For every customer, return customer_id, name, and total paid invoice amount across all their subscriptions, regardless of subscription status. Include customers with no paid invoices as zero, round the total to two decimals, and order by customer_id.

Coverage: left_join, join_filter, group_by, sum, coalesce, zero_inclusion.

```sql
SELECT c.customer_id,
       c.name,
       ROUND(COALESCE(SUM(i.amount), 0), 2) AS paid_total
FROM customers c
LEFT JOIN subscriptions s ON s.customer_id = c.customer_id
LEFT JOIN invoices i ON i.subscription_id = s.subscription_id
AND i.status = 'paid'
GROUP BY c.customer_id,
         c.name
ORDER BY c.customer_id;
```

### s08_q05 · medium

For every plan, including plans with no active subscriptions, return plan_id, name, and active_subscription_count. Count status active only and order by plan_id.

Coverage: right_join, join_filter, group_by, count, zero_inclusion.

```sql
SELECT p.plan_id,
       p.name,
       COUNT(s.subscription_id) AS active_subscription_count
FROM subscriptions s
RIGHT JOIN plans p ON p.plan_id = s.plan_id
AND s.status = 'active'
GROUP BY p.plan_id,
         p.name
ORDER BY p.plan_id;
```

### s08_q06 · medium

Which subscriptions exceeded their plan included_units allowance during January 2025? Ignore subscription status. Return subscription_id, plan name, January units used, and units above the allowance. Include only positive overages and order by subscription_id.

Coverage: inner_join, group_by, having, sum, date_range.

```sql
SELECT s.subscription_id,
       p.name,
       SUM(u.units) AS units_used,
       SUM(u.units) - p.included_units AS overage_units
FROM subscriptions s
JOIN plans p ON p.plan_id = s.plan_id
JOIN usage_events u ON u.subscription_id = s.subscription_id
WHERE u.used_on >= '2025-01-01'
    AND u.used_on < '2025-02-01'
GROUP BY s.subscription_id,
         p.name,
         p.included_units
HAVING SUM(u.units) > p.included_units
ORDER BY s.subscription_id;
```

### s08_q07 · medium

Find customers whose open invoices total at least 50 across all subscriptions. Return customer_id, name, open_invoice_count, and open_amount rounded to two decimals, ordered by customer_id. Exclude paid and void invoices.

Coverage: inner_join, group_by, having, count, sum.

```sql
SELECT c.customer_id,
       c.name,
       COUNT(i.invoice_id) AS open_invoice_count,
       ROUND(SUM(i.amount), 2) AS open_amount
FROM customers c
JOIN subscriptions s ON s.customer_id = c.customer_id
JOIN invoices i ON i.subscription_id = s.subscription_id
WHERE i.status = 'open'
GROUP BY c.customer_id,
         c.name
HAVING SUM(i.amount) >= 50
ORDER BY c.customer_id;
```

### s08_q08 · hard

Find subscriptions that have at least one usage event but have never had an invoice of any status. Return subscription_id, customer name, and plan name, ordered by subscription_id.

Coverage: inner_join, correlated_subquery, exists, not_exists.

```sql
SELECT s.subscription_id,
       c.name AS customer_name,
       p.name AS plan_name
FROM subscriptions s
JOIN customers c ON c.customer_id = s.customer_id
JOIN plans p ON p.plan_id = s.plan_id
WHERE EXISTS
        (SELECT 1
         FROM usage_events u
         WHERE u.subscription_id = s.subscription_id)
    AND NOT EXISTS
        (SELECT 1
         FROM invoices i
         WHERE i.subscription_id = s.subscription_id)
ORDER BY s.subscription_id;
```

### s08_q09 · hard

Show each paid invoice together with the running paid revenue for its customer across all subscriptions. Apply invoices in billed_on then invoice_id order within each customer. Return customer_id, invoice_id, billed_on, and running_paid_amount rounded to two decimals. Order by customer_id, billed_on, and invoice_id.

Coverage: inner_join, window, running_total, ties.

```sql
SELECT s.customer_id,
       i.invoice_id,
       i.billed_on,
       ROUND(SUM(i.amount) OVER (PARTITION BY s.customer_id
                                 ORDER BY i.billed_on, i.invoice_id ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW), 2) AS running_paid_amount
FROM invoices i
JOIN subscriptions s ON s.subscription_id = i.subscription_id
WHERE i.status = 'paid'
ORDER BY s.customer_id,
         i.billed_on,
         i.invoice_id;
```

### s08_q10 · hard

Which customers have at least one subscription and have at least one paid invoice for every subscription they have ever held, including cancelled or paused subscriptions? Return customer_id and name, ordered by customer_id.

Coverage: correlated_subquery, exists, not_exists, universal_condition.

```sql
SELECT c.customer_id,
       c.name
FROM customers c
WHERE EXISTS
        (SELECT 1
         FROM subscriptions s
         WHERE s.customer_id = c.customer_id)
    AND NOT EXISTS
        (SELECT 1
         FROM subscriptions s
         WHERE s.customer_id = c.customer_id
             AND NOT EXISTS
                 (SELECT 1
                  FROM invoices i
                  WHERE i.subscription_id = s.subscription_id
                      AND i.status = 'paid'))
ORDER BY c.customer_id;
```

## s09_support — Customer support

Fictional support queues and ticket events. All timestamps are UTC. Unresolved means status open or pending. A ticket can be unassigned to an agent or team; an agent can have no tickets. Multiple replies belong to a single ticket. A ticket's queue team can differ from its assigned agent's home team.

[DDL and seed data](schemas/s09_support.sql)

### s09_q01 · easy

Which high-priority tickets currently have status open? Return ticket_id, opened_at, and assigned_agent_id, retaining NULL for unassigned tickets. Sort by opened_at ascending, then ticket_id ascending.

Coverage: filter, nulls.

```sql
SELECT ticket_id,
       opened_at,
       assigned_agent_id
FROM tickets
WHERE priority = 'high'
    AND status = 'open'
ORDER BY opened_at,
         ticket_id;
```

### s09_q02 · easy

Count closed tickets for each priority that has at least one closed ticket. Return priority and closed_ticket_count, sorted by priority alphabetically.

Coverage: filter, group_by, count.

```sql
SELECT priority,
       COUNT(*) AS closed_ticket_count
FROM tickets
WHERE status = 'closed'
GROUP BY priority
ORDER BY priority;
```

### s09_q03 · easy

List the agents in team 1. Return agent_id and name, sorted by name alphabetically, then agent_id ascending.

Coverage: filter, order_by.

```sql
SELECT agent_id,
       name
FROM agents
WHERE team_id = 1
ORDER BY name,
         agent_id;
```

### s09_q04 · medium

For every team, count its unresolved tickets, meaning status open or pending, including tickets without an assigned agent. Include teams with zero unresolved tickets. Return team_id, team_name, and unresolved_ticket_count, sorted by team_id ascending.

Coverage: left_join, group_by, count, zero_inclusion.

```sql
SELECT tm.team_id,
       tm.name AS team_name,
       COUNT(t.ticket_id) AS unresolved_ticket_count
FROM teams AS tm
LEFT JOIN tickets AS t ON t.team_id = tm.team_id
AND t.status IN ('open',
                 'pending')
GROUP BY tm.team_id,
         tm.name
ORDER BY tm.team_id;
```

### s09_q05 · medium

For every customer, report the number of tickets of any status and the number of those tickets with no assigned agent. Include customers without tickets with both counts zero. Return customer_id, customer_name, ticket_count, and unassigned_ticket_count, sorted by customer_id ascending.

Coverage: left_join, case, conditional_aggregation, nulls, zero_inclusion.

```sql
SELECT c.customer_id,
       c.name AS customer_name,
       COUNT(t.ticket_id) AS ticket_count,
       SUM(CASE
               WHEN t.ticket_id IS NOT NULL
                    AND t.assigned_agent_id IS NULL THEN 1
               ELSE 0
           END) AS unassigned_ticket_count
FROM customers AS c
LEFT JOIN tickets AS t ON t.customer_id = c.customer_id
GROUP BY c.customer_id,
         c.name
ORDER BY c.customer_id;
```

### s09_q06 · medium

For each ticket that has received an agent_reply event, find its earliest agent reply and the elapsed hours from opening to that reply. Ignore other event types. Return ticket_id, first_reply_at, and response_hours rounded to two decimal places, sorted by ticket_id ascending.

Coverage: inner_join, group_by, min, date_arithmetic.

```sql
SELECT t.ticket_id,
       MIN(e.created_at) AS first_reply_at,
       ROUND((julianday(MIN(e.created_at)) - julianday(t.opened_at)) * 24, 2) AS response_hours
FROM tickets AS t
INNER JOIN ticket_events AS e ON e.ticket_id = t.ticket_id
WHERE e.event_type = 'agent_reply'
GROUP BY t.ticket_id,
         t.opened_at
ORDER BY t.ticket_id;
```

### s09_q07 · medium

Which agents are assigned at least two tickets with status closed? Return agent_id, agent_name, and closed_ticket_count. Sort by closed_ticket_count descending, then agent_id ascending.

Coverage: inner_join, group_by, having, count.

```sql
SELECT a.agent_id,
       a.name AS agent_name,
       COUNT(t.ticket_id) AS closed_ticket_count
FROM agents AS a
INNER JOIN tickets AS t ON t.assigned_agent_id = a.agent_id
WHERE t.status = 'closed'
GROUP BY a.agent_id,
         a.name
HAVING COUNT(t.ticket_id) >= 2
ORDER BY closed_ticket_count DESC,
         a.agent_id;
```

### s09_q08 · hard

Find the oldest unresolved ticket, meaning status open or pending, for each team that has one. Exclude tickets without a team. If a team has several tickets opened at the same time, choose the lowest ticket_id. Return team_id, team_name, ticket_id, and opened_at, sorted by team_id ascending.

Coverage: cte, row_number, window, inner_join, tie_break.

```sql
WITH ranked AS
    (SELECT team_id,
            ticket_id,
            opened_at,
            ROW_NUMBER() OVER (PARTITION BY team_id
                               ORDER BY opened_at, ticket_id) AS POSITION
     FROM tickets
     WHERE status IN ('open',
                      'pending')
         AND team_id IS NOT NULL)
SELECT tm.team_id,
       tm.name AS team_name,
       r.ticket_id,
       r.opened_at
FROM ranked AS r
INNER JOIN teams AS tm ON tm.team_id = r.team_id
WHERE r.position = 1
ORDER BY tm.team_id;
```

### s09_q09 · hard

Build a complete assignment roster showing every ticket of any status with its assigned agent, every unassigned ticket with NULL agent fields, and every agent with no tickets with NULL ticket fields. Return agent_id, agent_name, ticket_id, and status. Sort by agent_id ascending with NULL agents last, then ticket_id ascending with NULL tickets last.

Coverage: full_outer_join, nulls, order_by.

```sql
SELECT a.agent_id,
       a.name AS agent_name,
       t.ticket_id,
       t.status
FROM tickets AS t
FULL OUTER JOIN agents AS a ON a.agent_id = t.assigned_agent_id
ORDER BY a.agent_id IS NULL,
                       a.agent_id,
                       t.ticket_id IS NULL,
                                      t.ticket_id;
```

### s09_q10 · hard

For each team, identify all agents tied for the largest number of assigned unresolved tickets, meaning status open or pending. Exclude teams where every agent has zero assigned unresolved tickets. Count workload by the agent's team, and ignore unassigned tickets. Return team_id, team_name, agent_id, agent_name, and unresolved_ticket_count, sorted by team_id ascending, then agent_id ascending.

Coverage: cte, left_join, inner_join, group_by, dense_rank, window, ties.

```sql
WITH workloads AS
    (SELECT a.team_id,
            a.agent_id,
            a.name AS agent_name,
            COUNT(t.ticket_id) AS unresolved_ticket_count
     FROM agents AS a
     LEFT JOIN tickets AS t ON t.assigned_agent_id = a.agent_id
     AND t.status IN ('open',
                      'pending')
     GROUP BY a.team_id,
              a.agent_id,
              a.name),
     ranked AS
    (SELECT *,
            DENSE_RANK() OVER (PARTITION BY team_id
                               ORDER BY unresolved_ticket_count DESC) AS POSITION
     FROM workloads)
SELECT tm.team_id,
       tm.name AS team_name,
       r.agent_id,
       r.agent_name,
       r.unresolved_ticket_count
FROM ranked AS r
INNER JOIN teams AS tm ON tm.team_id = r.team_id
WHERE r.position = 1
    AND r.unresolved_ticket_count > 0
ORDER BY tm.team_id,
         r.agent_id;
```

## s10_hospitality — Hotel stays and payments

Fictional hotel reservations. A stay occupies nights in [check_in, check_out); checkout day is not occupied. Historical booked_nightly_rate determines booking value, not the room's current nightly_rate. Payments are signed cash movements, with negative refunds and NULL booking_id for unallocated payments. One pair of non-cancelled reservations intentionally overlaps to test conflict detection. All amounts use one currency.

[DDL and seed data](schemas/s10_hospitality.sql)

### s10_q01 · easy

Which rooms have a current nightly_rate of 160 or less? Return room_number, room_type, and nightly_rate. Sort by nightly_rate descending, then room_number ascending.

Coverage: filter, order_by.

```sql
SELECT room_number,
       room_type,
       nightly_rate
FROM rooms
WHERE nightly_rate <= 160
ORDER BY nightly_rate DESC,
         room_number;
```

### s10_q02 · easy

List confirmed bookings whose check-in date falls in February or March 2025. Return booking_id, check_in, and check_out, sorted by check_in ascending, then booking_id ascending.

Coverage: filter, date_range.

```sql
SELECT booking_id,
       check_in,
       check_out
FROM bookings
WHERE status = 'confirmed'
    AND check_in >= '2025-02-01'
    AND check_in < '2025-04-01'
ORDER BY check_in,
         booking_id;
```

### s10_q03 · easy

For each checked_out booking, calculate its number of nights and booking value using booked_nightly_rate. Checkout day is excluded. Return booking_id, nights as an integer, and booking_value rounded to two decimal places, sorted by booking_id ascending.

Coverage: filter, date_arithmetic, historical_values.

```sql
SELECT booking_id,
       CAST(julianday(check_out) - julianday(check_in) AS INTEGER) AS nights,
       ROUND((julianday(check_out) - julianday(check_in)) * booked_nightly_rate, 2) AS booking_value
FROM bookings
WHERE status = 'checked_out'
ORDER BY booking_id;
```

### s10_q04 · medium

For every room, count checked_out bookings and their total nights, excluding checkout days. Include rooms without checked_out bookings with both totals zero. Return room_id, room_number, completed_booking_count, and total_nights as an integer, sorted by room_number ascending.

Coverage: right_join, group_by, count, sum, date_arithmetic, zero_inclusion.

```sql
SELECT r.room_id,
       r.room_number,
       COUNT(b.booking_id) AS completed_booking_count,
       CAST(COALESCE(SUM(julianday(b.check_out) - julianday(b.check_in)), 0) AS INTEGER) AS total_nights
FROM bookings AS b
RIGHT JOIN rooms AS r ON r.room_id = b.room_id
AND b.status = 'checked_out'
GROUP BY r.room_id,
         r.room_number
ORDER BY r.room_number;
```

### s10_q05 · medium

For every guest, total the booking value of their checked_out stays, using each booking's historical booked_nightly_rate multiplied by nights and excluding checkout days. Include guests with no checked_out stays with a zero total. Return guest_id, guest_name, and completed_booking_value rounded to two decimal places, sorted by guest_id ascending.

Coverage: left_join, group_by, sum, historical_values, date_arithmetic, zero_inclusion.

```sql
SELECT g.guest_id,
       g.name AS guest_name,
       ROUND(COALESCE(SUM((julianday(b.check_out) - julianday(b.check_in)) * b.booked_nightly_rate), 0), 2) AS completed_booking_value
FROM guests AS g
LEFT JOIN bookings AS b ON b.guest_id = g.guest_id
AND b.status = 'checked_out'
GROUP BY g.guest_id,
         g.name
ORDER BY g.guest_id;
```

### s10_q06 · medium

How much net cash has been received for checked_out bookings in each room type? Sum signed payments so refunds reduce the total; exclude payments for other booking statuses and unallocated payments. Only include room types with at least one qualifying payment. Return room_type and net_payments rounded to two decimal places, sorted by room_type alphabetically.

Coverage: inner_join, group_by, sum, signed_amount.

```sql
SELECT r.room_type,
       ROUND(SUM(p.amount), 2) AS net_payments
FROM payments AS p
INNER JOIN bookings AS b ON b.booking_id = p.booking_id
INNER JOIN rooms AS r ON r.room_id = b.room_id
WHERE b.status = 'checked_out'
GROUP BY r.room_type
ORDER BY r.room_type;
```

### s10_q07 · medium

Which checked_out bookings still have a positive outstanding balance? Balance equals nights excluding checkout day times booked_nightly_rate, minus all signed payments for that booking; treat no payments as zero. Return booking_id, guest_name, room_number, and outstanding_balance rounded to two decimal places, sorted by booking_id ascending. Test positivity before rounding.

Coverage: inner_join, left_join, group_by, having, historical_values, signed_amount.

```sql
SELECT b.booking_id,
       g.name AS guest_name,
       r.room_number,
       ROUND((julianday(b.check_out) - julianday(b.check_in)) * b.booked_nightly_rate - COALESCE(SUM(p.amount), 0), 2) AS outstanding_balance
FROM bookings AS b
INNER JOIN guests AS g ON g.guest_id = b.guest_id
INNER JOIN rooms AS r ON r.room_id = b.room_id
LEFT JOIN payments AS p ON p.booking_id = b.booking_id
WHERE b.status = 'checked_out'
GROUP BY b.booking_id,
         g.name,
         r.room_number,
         b.check_in,
         b.check_out,
         b.booked_nightly_rate
HAVING (julianday(b.check_out) - julianday(b.check_in)) * b.booked_nightly_rate - COALESCE(SUM(p.amount), 0) > 0
ORDER BY b.booking_id;
```

### s10_q08 · hard

Find overlapping pairs of bookings for the same room, considering only confirmed and checked_out bookings. A booking occupies [check_in, check_out), so a checkout on another booking's check-in date is not an overlap. Return each pair once, with the lower booking_id first. Return room_number, first_booking_id, and second_booking_id, sorted by room_number, first_booking_id, then second_booking_id, all ascending.

Coverage: self_join, inner_join, date_overlap, deduplication.

```sql
SELECT r.room_number,
       a.booking_id AS first_booking_id,
       b.booking_id AS second_booking_id
FROM bookings AS a
INNER JOIN bookings AS b ON b.room_id = a.room_id
AND a.booking_id < b.booking_id
AND a.check_in < b.check_out
AND b.check_in < a.check_out
INNER JOIN rooms AS r ON r.room_id = a.room_id
WHERE a.status IN ('confirmed',
                   'checked_out')
    AND b.status IN ('confirmed',
                     'checked_out')
ORDER BY r.room_number,
         a.booking_id,
         b.booking_id;
```

### s10_q09 · hard

Within each room type, find every room tied for the highest total booking value from checked_out stays. Use historical booked_nightly_rate times nights excluding checkout days, and assign zero to rooms without checked_out stays; if every room in a type has zero, return all of them. Return room_type, room_number, and completed_booking_value rounded to two decimal places. Rank using unrounded totals and sort by room_type alphabetically, then room_number ascending.

Coverage: cte, left_join, group_by, dense_rank, window, ties, zero_inclusion, historical_values.

```sql
WITH room_values AS
    (SELECT r.room_id,
            r.room_number,
            r.room_type,
            COALESCE(SUM((julianday(b.check_out) - julianday(b.check_in)) * b.booked_nightly_rate), 0) AS booking_value
     FROM rooms AS r
     LEFT JOIN bookings AS b ON b.room_id = r.room_id
     AND b.status = 'checked_out'
     GROUP BY r.room_id,
              r.room_number,
              r.room_type),
     ranked AS
    (SELECT *,
            DENSE_RANK() OVER (PARTITION BY room_type
                               ORDER BY booking_value DESC) AS POSITION
     FROM room_values)
SELECT room_type,
       room_number,
       ROUND(booking_value, 2) AS completed_booking_value
FROM ranked
WHERE POSITION = 1
ORDER BY room_type,
         room_number;
```

### s10_q10 · hard

Which guests have at least two checked_out stays and an average stay length strictly above the average length across all checked_out bookings? Compute nights excluding checkout day, and compare the unrounded averages; the overall average is per booking, not per guest. Return guest_id, guest_name, and average_nights rounded to two decimal places, sorted by guest_id ascending.

Coverage: cte, inner_join, group_by, having, scalar_subquery, avg, date_arithmetic.

```sql
WITH completed_stays AS
    (SELECT guest_id,
            julianday(check_out) - julianday(check_in) AS nights
     FROM bookings
     WHERE status = 'checked_out')
SELECT g.guest_id,
       g.name AS guest_name,
       ROUND(AVG(s.nights), 2) AS average_nights
FROM guests AS g
INNER JOIN completed_stays AS s ON s.guest_id = g.guest_id
GROUP BY g.guest_id,
         g.name
HAVING COUNT(*) >= 2
AND AVG(s.nights) >
    (SELECT AVG(nights)
     FROM completed_stays)
ORDER BY g.guest_id;
```

## s11_manufacturing — Manufacturing bills of materials

Parts, an acyclic bill of materials, and work orders. BOM quantities are the direct component units needed for one parent unit. Shared components can occur along multiple paths; unit_cost is the current cost per part unit. Dates use YYYY-MM-DD.

[DDL and seed data](schemas/s11_manufacturing.sql)

### s11_q01 · easy

List raw parts with a unit cost of at least 3. Return part_id, name, unit_cost, ordered by unit_cost descending and then part_id ascending.

Coverage: filter, comparison, multi_column_order.

```sql
SELECT id AS part_id,
       name,
       unit_cost
FROM parts
WHERE kind = 'raw'
    AND unit_cost >= 3
ORDER BY unit_cost DESC,
         id;
```

### s11_q02 · easy

List work orders whose status is planned or in_progress and whose due date is before 2025-02-15. Return work_order_id, part_id, quantity, due_date, ordered by due_date and then work_order_id ascending.

Coverage: in_filter, date_boundary, multi_column_order.

```sql
SELECT id AS work_order_id,
       part_id,
       quantity,
       due_date
FROM work_orders
WHERE status IN ('planned',
                 'in_progress')
    AND due_date < '2025-02-15'
ORDER BY due_date,
         id;
```

### s11_q03 · easy

Count work orders in each status that occurs. Return status, work_order_count, ordered by status alphabetically.

Coverage: group_by, count.

```sql
SELECT status,
       COUNT(*) AS work_order_count
FROM work_orders
GROUP BY status
ORDER BY status;
```

### s11_q04 · medium

For every part, report the total quantity on work orders with status planned or in_progress, using zero when there are none. Return part_id, name, active_quantity, ordered by part_id ascending.

Coverage: left_join, conditional_join, sum, coalesce, unmatched_rows.

```sql
SELECT p.id AS part_id,
       p.name,
       COALESCE(SUM(w.quantity), 0) AS active_quantity
FROM parts AS p
LEFT JOIN work_orders AS w ON w.part_id = p.id
AND w.status IN ('planned',
                 'in_progress')
GROUP BY p.id,
         p.name
ORDER BY p.id;
```

### s11_q05 · medium

Show completed work orders that finished after their due date. Return work_order_id, part_name, days_late as an integer calendar-day difference, quantity, ordered by work_order_id ascending.

Coverage: inner_join, date_arithmetic, cast, comparison.

```sql
SELECT w.id AS work_order_id,
       p.name AS part_name,
       CAST(julianday(w.completed_date) - julianday(w.due_date) AS INTEGER) AS days_late,
       w.quantity
FROM work_orders AS w
JOIN parts AS p ON p.id = w.part_id
WHERE w.status = 'completed'
    AND w.completed_date > w.due_date
ORDER BY w.id;
```

### s11_q06 · medium

For every part classified as assembly, count its distinct direct component parts and sum their direct quantities per one assembly unit. Use zero for both values when the assembly has no components. Return part_id, name, component_count, component_quantity, ordered by part_id ascending.

Coverage: left_join, count, sum, coalesce, unmatched_rows.

```sql
SELECT p.id AS part_id,
       p.name,
       COUNT(b.component_part_id) AS component_count,
       COALESCE(SUM(b.quantity), 0) AS component_quantity
FROM parts AS p
LEFT JOIN bom AS b ON b.parent_part_id = p.id
WHERE p.kind = 'assembly'
GROUP BY p.id,
         p.name
ORDER BY p.id;
```

### s11_q07 · medium

For each part with at least one completed work order, show the total completed quantity and the number of distinct direct component parts in its bill of materials. The completed quantity must count each work order once; a part without direct components has a component count of zero. Return part_id, name, completed_quantity, component_count, ordered by part_id ascending.

Coverage: cte, preaggregation, fanout, inner_join, left_join, coalesce.

```sql
WITH completed AS
    (SELECT part_id,
            SUM(quantity) AS completed_quantity
     FROM work_orders
     WHERE status = 'completed'
     GROUP BY part_id),
     components AS
    (SELECT parent_part_id,
            COUNT(*) AS component_count
     FROM bom
     GROUP BY parent_part_id)
SELECT p.id AS part_id,
       p.name,
       c.completed_quantity,
       COALESCE(b.component_count, 0) AS component_count
FROM completed AS c
JOIN parts AS p ON p.id = c.part_id
LEFT JOIN components AS b ON b.parent_part_id = p.id
ORDER BY p.id;
```

### s11_q08 · hard

For each completed work order, show the previous completed work order date for the same part and the integer calendar-day gap from it. Within each part, sequence completed orders by completed_date and then work_order_id ascending; the first order has NULL for the previous date and gap. Return part_id, work_order_id, completed_date, previous_completed_date, gap_days, ordered by part_id, completed_date, work_order_id ascending.

Coverage: cte, lag, partition_by, date_arithmetic, null_first_row.

```sql
WITH history AS
    (SELECT part_id,
            id AS work_order_id,
            completed_date,
            LAG(completed_date) OVER (PARTITION BY part_id
                                      ORDER BY completed_date, id) AS previous_completed_date
     FROM work_orders
     WHERE status = 'completed')
SELECT part_id,
       work_order_id,
       completed_date,
       previous_completed_date,
       CAST(julianday(completed_date) - julianday(previous_completed_date) AS INTEGER) AS gap_days
FROM history
ORDER BY part_id,
         completed_date,
         work_order_id;
```

### s11_q09 · hard

Calculate the leaf-material requirements for building three Desk lamps (part_id 1). A leaf material is a descendant with no components of its own. Multiply quantities along each path, add quantities when a leaf appears along multiple paths, and price the resulting quantity at the leaf part's unit_cost. Return leaf_part_id, name, required_quantity, material_cost rounded to two decimal places, ordered by leaf_part_id ascending.

Coverage: recursive_cte, union_all, multi_path_aggregation, not_exists, round.

```sql
WITH RECURSIVE requirements(part_id, required_quantity) AS
    (SELECT component_part_id,
            quantity * 3
     FROM bom
     WHERE parent_part_id = 1
     UNION ALL SELECT b.component_part_id,
                      r.required_quantity * b.quantity
     FROM requirements AS r
     JOIN bom AS b ON b.parent_part_id = r.part_id)
SELECT p.id AS leaf_part_id,
       p.name,
       SUM(r.required_quantity) AS required_quantity,
       ROUND(SUM(r.required_quantity) * p.unit_cost, 2) AS material_cost
FROM requirements AS r
JOIN parts AS p ON p.id = r.part_id
WHERE NOT EXISTS
        (SELECT 1
         FROM bom AS b
         WHERE b.parent_part_id = r.part_id)
GROUP BY p.id,
         p.name,
         p.unit_cost
ORDER BY p.id;
```

### s11_q10 · hard

For every ancestor part that has components, list all its direct and indirect descendant parts. For one unit of the ancestor, multiply quantities along each path and add the quantities across all paths to the same descendant. Exclude the ancestor itself. Return ancestor_part_id, descendant_part_id, required_quantity, ordered by ancestor_part_id and then descendant_part_id ascending.

Coverage: recursive_cte, transitive_closure, union_all, multi_path_aggregation.

```sql
WITH RECURSIVE paths(ancestor_part_id, descendant_part_id, required_quantity) AS
    (SELECT parent_part_id,
            component_part_id,
            quantity
     FROM bom
     UNION ALL SELECT p.ancestor_part_id,
                      b.component_part_id,
                      p.required_quantity * b.quantity
     FROM paths AS p
     JOIN bom AS b ON b.parent_part_id = p.descendant_part_id)
SELECT ancestor_part_id,
       descendant_part_id,
       SUM(required_quantity) AS required_quantity
FROM paths
WHERE ancestor_part_id <> descendant_part_id
GROUP BY ancestor_part_id,
         descendant_part_id
ORDER BY ancestor_part_id,
         descendant_part_id;
```

## s12_inventory — Warehouse inventory and movements

Stock is a current snapshot, with at most one row per warehouse/product. Movements are a separate recorded history; they need not reconstruct the snapshot. quantity_change is signed. last_counted can be unknown. Dates use YYYY-MM-DD.

[DDL and seed data](schemas/s12_inventory.sql)

### s12_q01 · easy

List products with a reorder level of at least five units. Return product_id, sku, name, reorder_level, ordered by reorder_level descending and then product_id ascending.

Coverage: filter, comparison, multi_column_order.

```sql
SELECT id AS product_id,
       sku,
       name,
       reorder_level
FROM products
WHERE reorder_level >= 5
ORDER BY reorder_level DESC,
         id;
```

### s12_q02 · easy

List recorded movements with a negative quantity change during January 2025, regardless of reason. Return movement_id, warehouse_id, product_id, movement_date, quantity_change, ordered by movement_date and then movement_id ascending.

Coverage: negative_values, date_boundary, filter.

```sql
SELECT id AS movement_id,
       warehouse_id,
       product_id,
       movement_date,
       quantity_change
FROM movements
WHERE quantity_change < 0
    AND movement_date >= '2025-01-01'
    AND movement_date < '2025-02-01'
ORDER BY movement_date,
         id;
```

### s12_q03 · easy

For each warehouse with at least one stock record, total its on-hand units across those records. Return warehouse_id, total_on_hand, ordered by warehouse_id ascending.

Coverage: group_by, sum, zero_values.

```sql
SELECT warehouse_id,
       SUM(on_hand) AS total_on_hand
FROM stock
GROUP BY warehouse_id
ORDER BY warehouse_id;
```

### s12_q04 · medium

For every warehouse, show its total on-hand units and number of stock records. Count a stock record even when on_hand is zero; report zero for both metrics when the warehouse has no records. Return warehouse_id, name, total_on_hand, stock_record_count, ordered by warehouse_id ascending.

Coverage: left_join, count, coalesce, unmatched_rows, zero_values.

```sql
SELECT w.id AS warehouse_id,
       w.name,
       COALESCE(SUM(s.on_hand), 0) AS total_on_hand,
       COUNT(s.product_id) AS stock_record_count
FROM warehouses AS w
LEFT JOIN stock AS s ON s.warehouse_id = w.id
GROUP BY w.id,
         w.name
ORDER BY w.id;
```

### s12_q05 · medium

List every warehouse/product combination, treating a missing stock record as zero units on hand. Return warehouse_id, product_id, on_hand, ordered by warehouse_id and then product_id ascending.

Coverage: cross_join, left_join, composite_join, coalesce, complete_grid.

```sql
SELECT w.id AS warehouse_id,
       p.id AS product_id,
       COALESCE(s.on_hand, 0) AS on_hand
FROM warehouses AS w
CROSS JOIN products AS p
LEFT JOIN stock AS s ON s.warehouse_id = w.id
AND s.product_id = p.id
ORDER BY w.id,
         p.id;
```

### s12_q06 · medium

For every product, show total current on-hand units across warehouses and the net sum of all quantity changes recorded during January 2025. Compute the two totals independently, using zero when a product has no stock or no January movements. Return product_id, name, total_on_hand, january_net_change, ordered by product_id ascending.

Coverage: cte, preaggregation, fanout, left_join, date_boundary, coalesce.

```sql
WITH balances AS
    (SELECT product_id,
            SUM(on_hand) AS total_on_hand
     FROM stock
     GROUP BY product_id),
     changes AS
    (SELECT product_id,
            SUM(quantity_change) AS january_net_change
     FROM movements
     WHERE movement_date >= '2025-01-01'
         AND movement_date < '2025-02-01'
     GROUP BY product_id)
SELECT p.id AS product_id,
       p.name,
       COALESCE(b.total_on_hand, 0) AS total_on_hand,
       COALESCE(c.january_net_change, 0) AS january_net_change
FROM products AS p
LEFT JOIN balances AS b ON b.product_id = p.id
LEFT JOIN changes AS c ON c.product_id = p.id
ORDER BY p.id;
```

### s12_q07 · medium

Find existing stock records whose last count was before 2025-01-10 or whose last-count date is unknown. Return warehouse_id, warehouse_name, product_id, product_name, on_hand, last_counted, ordered by warehouse_id and then product_id ascending.

Coverage: inner_join, is_null, or_filter, date_boundary.

```sql
SELECT s.warehouse_id,
       w.name AS warehouse_name,
       s.product_id,
       p.name AS product_name,
       s.on_hand,
       s.last_counted
FROM stock AS s
JOIN warehouses AS w ON w.id = s.warehouse_id
JOIN products AS p ON p.id = s.product_id
WHERE s.last_counted < '2025-01-10'
    OR s.last_counted IS NULL
ORDER BY s.warehouse_id,
         s.product_id;
```

### s12_q08 · hard

For every movement at warehouse 1, calculate the running net quantity change for that product, beginning at zero before its first recorded movement. Sequence each product's movements by movement_date and then movement_id ascending. Return movement_id, product_id, movement_date, quantity_change, running_net_change, ordered by product_id, movement_date, movement_id ascending.

Coverage: sum_window, running_total, partition_by, rows_frame, negative_values.

```sql
SELECT id AS movement_id,
       product_id,
       movement_date,
       quantity_change,
       SUM(quantity_change) OVER (PARTITION BY product_id
                                  ORDER BY movement_date, id ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS running_net_change
FROM movements
WHERE warehouse_id = 1
ORDER BY product_id,
         movement_date,
         id;
```

### s12_q09 · hard

Rank existing stock records within each warehouse by on_hand descending. Equal quantities share a rank and the next different quantity receives the next consecutive rank with no gaps. Return warehouse_id, product_id, on_hand, stock_rank, ordered by warehouse_id, stock_rank, product_id ascending.

Coverage: dense_rank, partition_by, ties, zero_values.

```sql
SELECT warehouse_id,
       product_id,
       on_hand,
       DENSE_RANK() OVER (PARTITION BY warehouse_id
                          ORDER BY on_hand DESC) AS stock_rank
FROM stock
ORDER BY warehouse_id,
         stock_rank,
         product_id;
```

### s12_q10 · hard

For each movement whose reason is outbound, show the date of the immediately following recorded movement for the same warehouse and product, considering all reasons when finding that following movement. Sequence movements by movement_date and then movement_id ascending. Return movement_id, warehouse_id, product_id, movement_date, next_movement_date, gap_days as an integer calendar-day difference; use NULL for the final two columns if there is no later movement. Order by movement_id ascending.

Coverage: cte, lead, composite_partition, filter_after_window, date_arithmetic, null_last_row.

```sql
WITH sequenced AS
    (SELECT id AS movement_id,
            warehouse_id,
            product_id,
            movement_date,
            reason,
            LEAD(movement_date) OVER (PARTITION BY warehouse_id, product_id
                                      ORDER BY movement_date, id) AS next_movement_date
     FROM movements)
SELECT movement_id,
       warehouse_id,
       product_id,
       movement_date,
       next_movement_date,
       CAST(julianday(next_movement_date) - julianday(movement_date) AS INTEGER) AS gap_days
FROM sequenced
WHERE reason = 'outbound'
ORDER BY movement_id;
```

## s13_energy — Energy meter readings and historical tariffs

Sites have meters with cumulative energy readings in kWh. NULL readings are missing measurements. Reading timestamps use YYYY-MM-DD HH:MM:SS in UTC; dates use YYYY-MM-DD. Tariffs are regional, nonoverlapping half-open date intervals [valid_from, valid_to), with NULL valid_to meaning no end date.

[DDL and seed data](schemas/s13_energy.sql)

### s13_q01 · easy

List meters with no retirement date. Return meter_id, label, site_id, ordered by meter_id ascending.

Coverage: is_null, filter.

```sql
SELECT id AS meter_id,
       label,
       site_id
FROM meters
WHERE retired_on IS NULL
ORDER BY id;
```

### s13_q02 · easy

List nonmissing energy readings recorded on 2025-01-02 UTC. Return reading_id, meter_id, reading_at, reading_kwh, ordered by reading_at and then reading_id ascending.

Coverage: is_not_null, timestamp_boundary, multi_column_order.

```sql
SELECT id AS reading_id,
       meter_id,
       reading_at,
       reading_kwh
FROM readings
WHERE reading_kwh IS NOT NULL
    AND reading_at >= '2025-01-02 00:00:00'
    AND reading_at < '2025-01-03 00:00:00'
ORDER BY reading_at,
         id;
```

### s13_q03 · easy

For every meter represented in the readings table, count its nonmissing readings and show their minimum and maximum kWh values. A meter with only missing readings has count zero and NULL minimum and maximum. Return meter_id, valid_reading_count, minimum_kwh, maximum_kwh, ordered by meter_id ascending.

Coverage: group_by, count_column, min, max, null_aggregation.

```sql
SELECT meter_id,
       COUNT(reading_kwh) AS valid_reading_count,
       MIN(reading_kwh) AS minimum_kwh,
       MAX(reading_kwh) AS maximum_kwh
FROM readings
GROUP BY meter_id
ORDER BY meter_id;
```

### s13_q04 · medium

For every site, report its total number of meters and the number with no retirement date. Sites without meters should have zero for both counts. Return site_id, name, meter_count, active_meter_count, ordered by site_id ascending.

Coverage: left_join, conditional_aggregation, case, unmatched_rows, null_filtering.

```sql
SELECT s.id AS site_id,
       s.name,
       COUNT(m.id) AS meter_count,
       SUM(CASE
               WHEN m.id IS NOT NULL
                    AND m.retired_on IS NULL THEN 1
               ELSE 0
           END) AS active_meter_count
FROM sites AS s
LEFT JOIN meters AS m ON m.site_id = s.id
GROUP BY s.id,
         s.name
ORDER BY s.id;
```

### s13_q05 · medium

List meters that have no nonmissing energy reading, including meters with no reading records and meters whose records are all missing. Return meter_id, label, site_name, ordered by meter_id ascending.

Coverage: not_exists, correlated_subquery, inner_join, null_filtering, unmatched_rows.

```sql
SELECT m.id AS meter_id,
       m.label,
       s.name AS site_name
FROM meters AS m
JOIN sites AS s ON s.id = m.site_id
WHERE NOT EXISTS
        (SELECT 1
         FROM readings AS r
         WHERE r.meter_id = m.id
             AND r.reading_kwh IS NOT NULL)
ORDER BY m.id;
```

### s13_q06 · medium

For every meter with at least two nonmissing readings, report the minimum reading, maximum reading, and observed kWh range defined as maximum minus minimum. Return site_id, meter_id, label, minimum_kwh, maximum_kwh, observed_range_kwh rounded to two decimal places, ordered by site_id and then meter_id ascending.

Coverage: inner_join, having, count_column, null_aggregation, round.

```sql
SELECT m.site_id,
       m.id AS meter_id,
       m.label,
       MIN(r.reading_kwh) AS minimum_kwh,
       MAX(r.reading_kwh) AS maximum_kwh,
       ROUND(MAX(r.reading_kwh) - MIN(r.reading_kwh), 2) AS observed_range_kwh
FROM meters AS m
JOIN readings AS r ON r.meter_id = m.id
GROUP BY m.site_id,
         m.id,
         m.label
HAVING COUNT(r.reading_kwh) >= 2
ORDER BY m.site_id,
         m.id;
```

### s13_q07 · medium

For each nonmissing reading with a matching regional tariff, show the tariff effective on that reading's UTC calendar date. The valid_from date is inclusive, valid_to is exclusive, and NULL valid_to has no upper limit. Return reading_id, meter_id, reading_date formatted YYYY-MM-DD, price_per_kwh, ordered by reading_id ascending.

Coverage: historical_join, range_join, date, null_open_interval, inner_join.

```sql
SELECT r.id AS reading_id,
       r.meter_id,
       DATE(r.reading_at) AS reading_date,
       t.price_per_kwh
FROM readings AS r
JOIN meters AS m ON m.id = r.meter_id
JOIN sites AS s ON s.id = m.site_id
JOIN tariffs AS t ON t.region = s.region
AND DATE(r.reading_at) >= t.valid_from
AND (t.valid_to IS NULL
     OR DATE(r.reading_at) < t.valid_to)
WHERE r.reading_kwh IS NOT NULL
ORDER BY r.id;
```

### s13_q08 · hard

Within each meter, sequence nonmissing readings by reading_at and then reading_id ascending and form intervals between consecutive nonmissing readings. Omit the first reading. Return meter_id, reading_id, reading_at, elapsed_hours rounded to two decimals, consumed_kwh as current minus previous reading rounded to two decimals, average_kw as consumed_kwh divided by elapsed hours rounded to three decimals. Use NULL average_kw for zero elapsed hours. Order by meter_id, reading_at, reading_id ascending.

Coverage: cte, lag, filter_before_window, date_arithmetic, nullif, round.

```sql
WITH previous AS
    (SELECT meter_id,
            id AS reading_id,
            reading_at,
            reading_kwh,
            LAG(reading_at) OVER (PARTITION BY meter_id
                                  ORDER BY reading_at, id) AS previous_at,
            LAG(reading_kwh) OVER (PARTITION BY meter_id
                                   ORDER BY reading_at, id) AS previous_kwh
     FROM readings
     WHERE reading_kwh IS NOT NULL),
     intervals AS
    (SELECT meter_id,
            reading_id,
            reading_at,
            (julianday(reading_at) - julianday(previous_at)) * 24 AS elapsed_hours,
            reading_kwh - previous_kwh AS consumed_kwh
     FROM previous
     WHERE previous_at IS NOT NULL)
SELECT meter_id,
       reading_id,
       reading_at,
       ROUND(elapsed_hours, 2) AS elapsed_hours,
       ROUND(consumed_kwh, 2) AS consumed_kwh,
       ROUND(consumed_kwh / NULLIF(elapsed_hours, 0), 3) AS average_kw
FROM intervals
ORDER BY meter_id,
         reading_at,
         reading_id;
```

### s13_q09 · hard

For each meter, derive consumed kWh between consecutive nonmissing readings, sequencing by reading_at and then reading_id ascending. Omit the first reading because it has no preceding interval. For every remaining interval, calculate the arithmetic mean of its consumption and up to two preceding interval consumptions for that meter; divide by the number of available intervals, without time weighting. Return meter_id, reading_id, reading_at, consumed_kwh, trailing_mean_kwh, with both kWh outputs rounded to two decimals. Order by meter_id, reading_at, reading_id ascending.

Coverage: cte, lag, avg_window, moving_average, rows_frame, filter_after_window, round.

```sql
WITH previous AS
    (SELECT meter_id,
            id AS reading_id,
            reading_at,
            reading_kwh,
            LAG(reading_kwh) OVER (PARTITION BY meter_id
                                   ORDER BY reading_at, id) AS previous_kwh
     FROM readings
     WHERE reading_kwh IS NOT NULL),
     intervals AS
    (SELECT meter_id,
            reading_id,
            reading_at,
            reading_kwh - previous_kwh AS consumed_kwh
     FROM previous
     WHERE previous_kwh IS NOT NULL)
SELECT meter_id,
       reading_id,
       reading_at,
       ROUND(consumed_kwh, 2) AS consumed_kwh,
       ROUND(AVG(consumed_kwh) OVER (PARTITION BY meter_id
                                     ORDER BY reading_at, reading_id ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 2) AS trailing_mean_kwh
FROM intervals
ORDER BY meter_id,
         reading_at,
         reading_id;
```

### s13_q10 · hard

Rank meters having at least two nonmissing readings by observed consumption, defined as maximum minus minimum reading, in descending order. Equal unrounded consumption values share a rank, and the next rank skips the number of tied positions. Return meter_id, label, observed_consumption_kwh rounded to two decimals, consumption_rank, ordered by consumption_rank and then meter_id ascending.

Coverage: cte, rank, ties, having, null_aggregation, round.

```sql
WITH consumption AS
    (SELECT m.id AS meter_id,
            m.label,
            MAX(r.reading_kwh) - MIN(r.reading_kwh) AS observed_consumption_kwh
     FROM meters AS m
     JOIN readings AS r ON r.meter_id = m.id
     GROUP BY m.id,
              m.label
     HAVING COUNT(r.reading_kwh) >= 2)
SELECT meter_id,
       label,
       ROUND(observed_consumption_kwh, 2) AS observed_consumption_kwh,
       RANK() OVER (
                    ORDER BY observed_consumption_kwh DESC) AS consumption_rank
FROM consumption
ORDER BY consumption_rank,
         meter_id;
```

## s14_transport — Transit routes, stops, and trips

Routes have ordered stops; a stop may belong to multiple routes. travel_minutes_from_previous is the planned travel time from the preceding stop and is NULL for a route's first stop. Trips include historical, scheduled, and cancelled services. All timestamps are UTC and use YYYY-MM-DD HH:MM:SS.

[DDL and seed data](schemas/s14_transport.sql)

### s14_q01 · easy

List active routes. Return route_id, name, ordered by route_id ascending.

Coverage: boolean_filter, order_by.

```sql
SELECT id AS route_id,
       name
FROM routes
WHERE active = 1
ORDER BY id;
```

### s14_q02 · easy

List stops in the Central zone. Return stop_id, name, ordered by stop_id ascending.

Coverage: equality_filter, order_by.

```sql
SELECT id AS stop_id,
       name
FROM stops
WHERE ZONE = 'Central'
ORDER BY id;
```

### s14_q03 · easy

Count trips in each status occurring from service date 2025-01-01 through 2025-01-03, both dates inclusive. Return status, trip_count, ordered by status alphabetically.

Coverage: date_boundary, group_by, count.

```sql
SELECT status,
       COUNT(*) AS trip_count
FROM trips
WHERE service_date >= '2025-01-01'
    AND service_date <= '2025-01-03'
GROUP BY status
ORDER BY status;
```

### s14_q04 · medium

For every route, report its number of listed stop positions and highest stop sequence. A route with no listed stops has stop_count zero and last_stop_sequence NULL. Return route_id, name, stop_count, last_stop_sequence, ordered by route_id ascending.

Coverage: left_join, count_column, max, unmatched_rows.

```sql
SELECT r.id AS route_id,
       r.name,
       COUNT(rs.stop_sequence) AS stop_count,
       MAX(rs.stop_sequence) AS last_stop_sequence
FROM routes AS r
LEFT JOIN route_stops AS rs ON rs.route_id = r.id
GROUP BY r.id,
         r.name
ORDER BY r.id;
```

### s14_q05 · medium

For each completed trip with an actual departure recorded, calculate departure delay in minutes as actual departure minus scheduled departure, allowing negative values for early departures. Return trip_id, route_name, delay_minutes rounded to two decimals, ordered by trip_id ascending.

Coverage: inner_join, date_arithmetic, negative_values, round, null_filtering.

```sql
SELECT t.id AS trip_id,
       r.name AS route_name,
       ROUND((julianday(t.actual_departure) - julianday(t.scheduled_departure)) * 1440, 2) AS delay_minutes
FROM trips AS t
JOIN routes AS r ON r.id = t.route_id
WHERE t.status = 'completed'
    AND t.actual_departure IS NOT NULL
ORDER BY t.id;
```

### s14_q06 · medium

For every route, report its number of completed trips and number of listed stop positions, counting each trip and each position once. Use zero for missing counts. Return route_id, name, completed_trip_count, stop_count, ordered by route_id ascending.

Coverage: cte, preaggregation, fanout, left_join, coalesce.

```sql
WITH completed AS
    (SELECT route_id,
            COUNT(*) AS completed_trip_count
     FROM trips
     WHERE status = 'completed'
     GROUP BY route_id),
     stop_counts AS
    (SELECT route_id,
            COUNT(*) AS stop_count
     FROM route_stops
     GROUP BY route_id)
SELECT r.id AS route_id,
       r.name,
       COALESCE(c.completed_trip_count, 0) AS completed_trip_count,
       COALESCE(s.stop_count, 0) AS stop_count
FROM routes AS r
LEFT JOIN completed AS c ON c.route_id = r.id
LEFT JOIN stop_counts AS s ON s.route_id = r.id
ORDER BY r.id;
```

### s14_q07 · medium

Show every pair of adjacent stop positions on the same route, where the destination sequence is exactly one greater than the origin sequence. Return route_id, origin_sequence, origin_stop, destination_stop, segment_minutes using the destination position's travel_minutes_from_previous. Order by route_id and then origin_sequence ascending.

Coverage: self_join, composite_join, inner_join, adjacency.

```sql
SELECT a.route_id,
       a.stop_sequence AS origin_sequence,
       origin.name AS origin_stop,
       destination.name AS destination_stop,
       b.travel_minutes_from_previous AS segment_minutes
FROM route_stops AS a
JOIN route_stops AS b ON b.route_id = a.route_id
AND b.stop_sequence = a.stop_sequence + 1
JOIN stops AS origin ON origin.id = a.stop_id
JOIN stops AS destination ON destination.id = b.stop_id
ORDER BY a.route_id,
         a.stop_sequence;
```

### s14_q08 · hard

For every listed route stop, calculate planned elapsed travel minutes from the first stop through that position, treating a missing segment time as zero. Return route_id, stop_sequence, stop_name, elapsed_minutes, ordered by route_id and then stop_sequence ascending.

Coverage: sum_window, running_total, rows_frame, partition_by, coalesce.

```sql
SELECT rs.route_id,
       rs.stop_sequence,
       s.name AS stop_name,
       SUM(COALESCE(rs.travel_minutes_from_previous, 0)) OVER (PARTITION BY rs.route_id
                                                               ORDER BY rs.stop_sequence ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS elapsed_minutes
FROM route_stops AS rs
JOIN stops AS s ON s.id = rs.stop_id
ORDER BY rs.route_id,
         rs.stop_sequence;
```

### s14_q09 · hard

For every route with a completed trip, return exactly its latest completed trip, choosing by service_date descending, then scheduled_departure descending, then trip_id descending. Return route_id, trip_id, service_date, actual_departure, ordered by route_id ascending.

Coverage: cte, row_number, partition_by, top_per_group, tie_break.

```sql
WITH ordered AS
    (SELECT route_id,
            id AS trip_id,
            service_date,
            actual_departure,
            ROW_NUMBER() OVER (PARTITION BY route_id
                               ORDER BY service_date DESC, scheduled_departure DESC, id DESC) AS POSITION
     FROM trips
     WHERE status = 'completed')
SELECT route_id,
       trip_id,
       service_date,
       actual_departure
FROM ordered
WHERE POSITION = 1
ORDER BY route_id;
```

### s14_q10 · hard

Within each route, divide completed trips in chronological order into two batches of sizes differing by at most one. Order trips by service_date, scheduled_departure, and trip_id ascending; batch 1 contains the earlier trips and gets the extra trip when the count is odd. A route with one completed trip uses only batch 1. Return route_id, trip_id, service_date, batch_number, ordered by route_id, service_date, scheduled_departure, trip_id ascending.

Coverage: ntile, partition_by, tie_break, uneven_buckets.

```sql
SELECT route_id,
       id AS trip_id,
       service_date,
       NTILE(2) OVER (PARTITION BY route_id
                      ORDER BY service_date, scheduled_departure, id) AS batch_number
FROM trips
WHERE status = 'completed'
ORDER BY route_id,
         service_date,
         scheduled_departure,
         id;
```

## s15_web_analytics — Website visitors, sessions, and events

A visitor can have many sessions, including sessions without events. NULL referrer means direct traffic. Only purchase events carry purchase revenue; other events may have NULL revenue. All timestamps are UTC in YYYY-MM-DD HH:MM:SS format. Signup dates can be unknown. Sessions and events are distinct grains.

[DDL and seed data](schemas/s15_web_analytics.sql)

### s15_q01 · easy

List visitors whose known signup date is at least 2025-01-02 and before 2025-01-05. Return visitor_id, country, signup_date, ordered by signup_date and then visitor_id ascending.

Coverage: date_boundary, null_filtering, multi_column_order.

```sql
SELECT id AS visitor_id,
       country,
       signup_date
FROM visitors
WHERE signup_date >= '2025-01-02'
    AND signup_date < '2025-01-05'
ORDER BY signup_date,
         id;
```

### s15_q02 · easy

List purchase events with revenue of at least 20. Return event_id, session_id, event_at, revenue, ordered by event_at and then event_id ascending.

Coverage: equality_filter, comparison, multi_column_order.

```sql
SELECT id AS event_id,
       session_id,
       event_at,
       revenue
FROM EVENTS
WHERE event_type = 'purchase'
    AND revenue >= 20
ORDER BY event_at,
         id;
```

### s15_q03 · easy

Count sessions for each device type that occurs. Return device, session_count, ordered by device alphabetically.

Coverage: group_by, count.

```sql
SELECT device,
       COUNT(*) AS session_count
FROM sessions
GROUP BY device
ORDER BY device;
```

### s15_q04 · medium

For every visitor, count their sessions, including visitors with no sessions as zero. Return visitor_id, country, session_count, ordered by visitor_id ascending.

Coverage: left_join, count_column, unmatched_rows.

```sql
SELECT v.id AS visitor_id,
       v.country,
       COUNT(s.id) AS session_count
FROM visitors AS v
LEFT JOIN sessions AS s ON s.visitor_id = v.id
GROUP BY v.id,
         v.country
ORDER BY v.id;
```

### s15_q05 · medium

For each session referrer, using direct for NULL, report the number of sessions, the number of sessions containing at least one purchase event, and total purchase-event revenue. Count each session once even when it contains multiple events, retain sessions without events, and use zero revenue when there are no purchases. Return referrer, session_count, converting_session_count, purchase_revenue rounded to two decimals, ordered by referrer alphabetically.

Coverage: left_join, count_distinct, conditional_aggregation, case, coalesce, fanout, round.

```sql
SELECT COALESCE(s.referrer, 'direct') AS referrer,
       COUNT(DISTINCT s.id) AS session_count,
       COUNT(DISTINCT CASE
                          WHEN e.event_type = 'purchase' THEN s.id
                      END) AS converting_session_count,
       ROUND(COALESCE(SUM(CASE
                              WHEN e.event_type = 'purchase' THEN e.revenue
                              ELSE 0
                          END), 0), 2) AS purchase_revenue
FROM sessions AS s
LEFT JOIN EVENTS AS e ON e.session_id = s.id
GROUP BY COALESCE(s.referrer, 'direct')
ORDER BY referrer;
```

### s15_q06 · medium

For every session, count its events and calculate the span in whole seconds from its earliest to latest event. Return NULL span for a session with no events and zero for one event. Return session_id, event_count, event_span_seconds, ordered by session_id ascending.

Coverage: left_join, min, max, date_arithmetic, null_aggregation, cast, round.

```sql
SELECT s.id AS session_id,
       COUNT(e.id) AS event_count,
       CAST(ROUND((julianday(MAX(e.event_at)) - julianday(MIN(e.event_at))) * 86400) AS INTEGER) AS event_span_seconds
FROM sessions AS s
LEFT JOIN EVENTS AS e ON e.session_id = s.id
GROUP BY s.id
ORDER BY s.id;
```

### s15_q07 · medium

For each visitor country with at least one session, calculate its session conversion rate: 100 times the number of sessions containing at least one purchase event divided by all sessions from that country. A session with multiple purchase events counts once. Return country, session_count, converting_session_count, conversion_percent rounded to two decimals, ordered by country alphabetically.

Coverage: cte, preaggregation, fanout, conditional_aggregation, percentage, round.

```sql
WITH session_flags AS
    (SELECT s.id AS session_id,
            v.country,
            MAX(CASE
                    WHEN e.event_type = 'purchase' THEN 1
                    ELSE 0
                END) AS converted
     FROM sessions AS s
     JOIN visitors AS v ON v.id = s.visitor_id
     LEFT JOIN EVENTS AS e ON e.session_id = s.id
     GROUP BY s.id,
              v.country)
SELECT country,
       COUNT(*) AS session_count,
       SUM(converted) AS converting_session_count,
       ROUND(100.0 * SUM(converted) / COUNT(*), 2) AS conversion_percent
FROM session_flags
GROUP BY country
ORDER BY country;
```

### s15_q08 · hard

For every session, show the previous session start for the same visitor and the elapsed hours since it. Sequence each visitor's sessions by started_at and then session_id ascending, including ties in start time. The first session has NULL for the previous start and gap. Return visitor_id, session_id, started_at, previous_started_at, gap_hours rounded to two decimals, ordered by visitor_id, started_at, session_id ascending.

Coverage: cte, lag, partition_by, date_arithmetic, tie_break, null_first_row, round.

```sql
WITH previous AS
    (SELECT visitor_id,
            id AS session_id,
            started_at,
            LAG(started_at) OVER (PARTITION BY visitor_id
                                  ORDER BY started_at, id) AS previous_started_at
     FROM sessions)
SELECT visitor_id,
       session_id,
       started_at,
       previous_started_at,
       ROUND((julianday(started_at) - julianday(previous_started_at)) * 24, 2) AS gap_hours
FROM previous
ORDER BY visitor_id,
         started_at,
         session_id;
```

### s15_q09 · hard

For each UTC calendar day from 2025-01-01 through 2025-01-04 inclusive, show purchase-event revenue, cumulative revenue since 2025-01-01, and the arithmetic mean of that day's and the preceding calendar day's revenue within this reporting period. Include days without purchases as zero; the first day's mean uses only that day. Return day formatted YYYY-MM-DD, purchase_revenue, cumulative_revenue, two_day_mean_revenue, with all revenue values rounded to two decimals, ordered by day ascending.

Coverage: recursive_cte, calendar, left_join, sum_window, running_total, avg_window, moving_average, rows_frame, round.

```sql
WITH RECURSIVE calendar(DAY) AS
    (SELECT '2025-01-01'
     UNION ALL SELECT DATE(DAY, '+1 day')
     FROM calendar
     WHERE DAY < '2025-01-04'),
               revenue AS
    (SELECT DATE(event_at) AS DAY,
            SUM(revenue) AS purchase_revenue
     FROM EVENTS
     WHERE event_type = 'purchase'
         AND event_at >= '2025-01-01 00:00:00'
         AND event_at < '2025-01-05 00:00:00'
     GROUP BY DATE(event_at)),
               daily AS
    (SELECT c.day,
            COALESCE(r.purchase_revenue, 0) AS purchase_revenue
     FROM calendar AS c
     LEFT JOIN revenue AS r ON r.day = c.day)
SELECT DAY,
       ROUND(purchase_revenue, 2) AS purchase_revenue,
       ROUND(SUM(purchase_revenue) OVER (
                                         ORDER BY DAY ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW), 2) AS cumulative_revenue,
       ROUND(AVG(purchase_revenue) OVER (
                                         ORDER BY DAY ROWS BETWEEN 1 PRECEDING AND CURRENT ROW), 2) AS two_day_mean_revenue
FROM daily
ORDER BY DAY;
```

### s15_q10 · hard

For every visitor, total their purchase-event revenue, using zero for visitors without purchases or sessions. Rank visitors by unrounded revenue ascending with equal revenues sharing the first position occupied by that tie group, and calculate percentile_fraction as (rank minus one) divided by (number of visitors minus one); use zero if there is only one visitor. Return visitor_id, country, purchase_revenue rounded to two decimals, percentile_fraction rounded to four decimals, ordered by unrounded purchase revenue and then visitor_id ascending.

Coverage: cte, percent_rank, ties, left_join, unmatched_rows, conditional_aggregation, round.

```sql
WITH totals AS
    (SELECT v.id AS visitor_id,
            v.country,
            COALESCE(SUM(CASE
                             WHEN e.event_type = 'purchase' THEN e.revenue
                             ELSE 0
                         END), 0) AS purchase_revenue
     FROM visitors AS v
     LEFT JOIN sessions AS s ON s.visitor_id = v.id
     LEFT JOIN EVENTS AS e ON e.session_id = s.id
     GROUP BY v.id,
              v.country)
SELECT visitor_id,
       country,
       ROUND(purchase_revenue, 2) AS purchase_revenue,
       ROUND(PERCENT_RANK() OVER (
                                  ORDER BY purchase_revenue), 4) AS percentile_fraction
FROM totals
ORDER BY totals.purchase_revenue,
         visitor_id;
```

## s16_marketplace — Marketplace auctions

Users can be sellers and bidders. Listings may have no reserve or no bids. Listing status is open or closed; bids remain historical after closing. Highest bids may tie.

[DDL and seed data](schemas/s16_marketplace.sql)

### s16_q01 · easy

List open listings without a reserve price. Return listing_id and title, ordered by listing_id.

Coverage: filter, is_null.

```sql
SELECT id AS listing_id,
       title
FROM listings
WHERE status = 'open'
    AND reserve_price IS NULL
ORDER BY id;
```

### s16_q02 · easy

Count listings in each status. Return status and listing_count, ordered by status.

Coverage: group_by, count.

```sql
SELECT status,
       COUNT(*) AS listing_count
FROM listings
GROUP BY status
ORDER BY status;
```

### s16_q03 · easy

List bids of at least 100. Return bid_id, listing_id, bidder_id, and amount, ordered by amount descending and then bid_id ascending.

Coverage: filter, multi_column_order.

```sql
SELECT id AS bid_id,
       listing_id,
       bidder_id,
       amount
FROM bids
WHERE amount >= 100
ORDER BY amount DESC,
         id;
```

### s16_q04 · medium

For every listing, show listing_id, title, bid_count, and highest_bid. Count actual bids; highest_bid must be NULL for a listing without bids. Order by listing_id.

Coverage: left_join, nulls, group_by.

```sql
SELECT l.id AS listing_id,
       l.title,
       COUNT(b.id) AS bid_count,
       MAX(b.amount) AS highest_bid
FROM listings l
LEFT JOIN bids b ON b.listing_id = l.id
GROUP BY l.id,
         l.title
ORDER BY l.id;
```

### s16_q05 · medium

Return the distinct user_id values of users who have listed an item or placed a bid, considering all listing statuses. Order by user_id.

Coverage: union, duplicate_elimination.

```sql
SELECT seller_id AS user_id
FROM listings
UNION
SELECT bidder_id AS user_id
FROM bids
ORDER BY user_id;
```

### s16_q06 · medium

Which users have both listed an item and placed a bid, considering all listing statuses? Return distinct user_id values ascending.

Coverage: intersect, duplicate_elimination.

```sql
SELECT seller_id AS user_id
FROM listings INTERSECT
SELECT bidder_id AS user_id
FROM bids
ORDER BY user_id;
```

### s16_q07 · medium

Find open listings whose reserve has been met by at least one bid. A listing with no reserve qualifies only if it has at least one bid. Return listing_id and title, ordered by listing_id.

Coverage: exists, correlated_subquery, nulls.

```sql
SELECT l.id AS listing_id,
       l.title
FROM listings l
WHERE l.status = 'open'
    AND EXISTS
        (SELECT 1
         FROM bids b
         WHERE b.listing_id = l.id
             AND (l.reserve_price IS NULL
                  OR b.amount >= l.reserve_price))
ORDER BY l.id;
```

### s16_q08 · hard

Find sellers who have at least one open listing and for whom every open listing has received a bid. Return seller_id and name, ordered by seller_id. Closed listings do not affect eligibility.

Coverage: relational_division, exists, not_exists, correlated_subquery.

```sql
SELECT u.id AS seller_id,
       u.name
FROM users u
WHERE EXISTS
        (SELECT 1
         FROM listings l
         WHERE l.seller_id = u.id
             AND l.status = 'open')
    AND NOT EXISTS
        (SELECT 1
         FROM listings l
         WHERE l.seller_id = u.id
             AND l.status = 'open'
             AND NOT EXISTS
                 (SELECT 1
                  FROM bids b
                  WHERE b.listing_id = l.id))
ORDER BY u.id;
```

### s16_q09 · hard

For every listing that has bids, return every bid tied for its highest amount. Return listing_id, title, bidder_id, bid_id, and amount, ordered by listing_id then bid_id. Include open and closed listings.

Coverage: correlated_subquery, max, ties.

```sql
SELECT l.id AS listing_id,
       l.title,
       b.bidder_id,
       b.id AS bid_id,
       b.amount
FROM listings l
JOIN bids b ON b.listing_id = l.id
WHERE b.amount =
        (SELECT MAX(b2.amount)
         FROM bids b2
         WHERE b2.listing_id = l.id)
ORDER BY l.id,
         b.id;
```

### s16_q10 · hard

Find unordered pairs of bidders who have both bid on at least two distinct open listings. Return smaller_bidder_id, larger_bidder_id, and shared_listing_count, ordered by those two IDs. Multiple bids by one bidder on one listing count only once.

Coverage: self_join, count_distinct, having, fanout.

```sql
SELECT b1.bidder_id AS smaller_bidder_id,
       b2.bidder_id AS larger_bidder_id,
       COUNT(DISTINCT b1.listing_id) AS shared_listing_count
FROM bids b1
JOIN bids b2 ON b2.listing_id = b1.listing_id
AND b1.bidder_id < b2.bidder_id
JOIN listings l ON l.id = b1.listing_id
WHERE l.status = 'open'
GROUP BY b1.bidder_id,
         b2.bidder_id
HAVING COUNT(DISTINCT b1.listing_id) >= 2
ORDER BY b1.bidder_id,
         b2.bidder_id;
```

## s17_surveys — Survey participation

A participant can have at most one response per question. A non-NULL score is an answered question; a NULL score is an explicit skip, and a missing response is unanswered. required=1 marks mandatory questions. Participants may have no group or responses.

[DDL and seed data](schemas/s17_surveys.sql)

### s17_q01 · easy

List mandatory questions. Return question_id and prompt, ordered by question_id.

Coverage: filter.

```sql
SELECT id AS question_id,
       prompt
FROM questions
WHERE required = 1
ORDER BY id;
```

### s17_q02 · easy

List responses with a score of at least 4. Return response_id, participant_id, question_id, and score, ordered by response_id.

Coverage: filter, nulls.

```sql
SELECT id AS response_id,
       participant_id,
       question_id,
       score
FROM responses
WHERE score >= 4
ORDER BY id;
```

### s17_q03 · easy

Count registered participants by group, displaying NULL group names as Unassigned. Return group_name and participant_count, ordered by the displayed group_name.

Coverage: coalesce, group_by.

```sql
SELECT COALESCE(group_name, 'Unassigned') AS group_name,
       COUNT(*) AS participant_count
FROM participants
GROUP BY COALESCE(group_name, 'Unassigned')
ORDER BY group_name;
```

### s17_q04 · medium

For every question, return question_id, prompt, answered_count, and average_score rounded to two decimals. Ignore NULL scores in both statistics; average_score must be NULL when nobody answered. Order by question_id.

Coverage: left_join, count_nullable, avg, round.

```sql
SELECT q.id AS question_id,
       q.prompt,
       COUNT(r.score) AS answered_count,
       ROUND(AVG(r.score), 2) AS average_score
FROM questions q
LEFT JOIN responses r ON r.question_id = q.id
GROUP BY q.id,
         q.prompt
ORDER BY q.id;
```

### s17_q05 · medium

Which participants answered question 1 but did not answer question 2? A NULL score does not count as an answer. Return participant_id values ascending.

Coverage: except, nulls, duplicate_elimination.

```sql
SELECT participant_id
FROM responses
WHERE question_id = 1
    AND score IS NOT NULL
EXCEPT
SELECT participant_id
FROM responses
WHERE question_id = 2
    AND score IS NOT NULL
ORDER BY participant_id;
```

### s17_q06 · medium

Combine the participant IDs of all non-NULL responses to question 1 with those of all non-NULL responses to question 2. Keep duplicates so a participant who answered both appears twice. Return only participant_id, sorted ascending.

Coverage: union_all, duplicate_preservation.

```sql
SELECT participant_id
FROM responses
WHERE question_id = 1
    AND score IS NOT NULL
UNION ALL
SELECT participant_id
FROM responses
WHERE question_id = 2
    AND score IS NOT NULL
ORDER BY participant_id;
```

### s17_q07 · medium

For every registered participant, return participant_id, name, and answered_count (the number of questions answered with a non-NULL score), in that order. Include participants with zero answers. Sort by participant_id ascending.

Coverage: left_join, count_nullable, zero_inclusion.

```sql
SELECT p.id AS participant_id,
       p.name,
       COUNT(r.score) AS answered_count
FROM participants p
LEFT JOIN responses r ON r.participant_id = p.id
GROUP BY p.id,
         p.name
ORDER BY p.id;
```

### s17_q08 · hard

Which participants answered every mandatory question with a non-NULL score? Return participant_id and name, ordered by participant_id. Optional questions do not affect eligibility. If there are no mandatory questions, every participant qualifies.

Coverage: relational_division, not_exists, correlated_subquery.

```sql
SELECT p.id AS participant_id,
       p.name
FROM participants p
WHERE NOT EXISTS
        (SELECT 1
         FROM questions q
         WHERE q.required = 1
             AND NOT EXISTS
                 (SELECT 1
                  FROM responses r
                  WHERE r.participant_id = p.id
                      AND r.question_id = q.id
                      AND r.score IS NOT NULL))
ORDER BY p.id;
```

### s17_q09 · hard

Find unordered participant pairs with exactly the same set of mandatory questions answered with non-NULL scores. Require that each participant answered at least one mandatory question. Return smaller_participant_id and larger_participant_id, ordered by both IDs.

Coverage: self_join, except, set_equality, exists, not_exists.

```sql
WITH answered AS
    (SELECT r.participant_id,
            r.question_id
     FROM responses r
     JOIN questions q ON q.id = r.question_id
     WHERE q.required = 1
         AND r.score IS NOT NULL)
SELECT p1.id AS smaller_participant_id,
       p2.id AS larger_participant_id
FROM participants p1
JOIN participants p2 ON p1.id < p2.id
WHERE EXISTS
        (SELECT 1
         FROM answered a
         WHERE a.participant_id = p1.id)
    AND EXISTS
        (SELECT 1
         FROM answered a
         WHERE a.participant_id = p2.id)
    AND NOT EXISTS
        (SELECT question_id
         FROM answered
         WHERE participant_id = p1.id
         EXCEPT SELECT question_id
         FROM answered
         WHERE participant_id = p2.id)
    AND NOT EXISTS
        (SELECT question_id
         FROM answered
         WHERE participant_id = p2.id
         EXCEPT SELECT question_id
         FROM answered
         WHERE participant_id = p1.id)
ORDER BY p1.id,
         p2.id;
```

### s17_q10 · hard

For each registered participant group, compute the percentage of mandatory question-participant combinations that have a non-NULL score. The denominator is all registered participants in the group times the total number of mandatory questions; skips and missing responses are incomplete. Return group_name (Unassigned for NULL) and completion_percent rounded to two decimals, ordered by group_name. Use NULL if there are no mandatory questions.

Coverage: correlated_subquery, ratio, nullif, zero_inclusion.

```sql
SELECT COALESCE(p.group_name, 'Unassigned') AS group_name,
       ROUND(100.0 * SUM(
                             (SELECT COUNT(*)
                              FROM responses r
                              JOIN questions q ON q.id = r.question_id
                              WHERE r.participant_id = p.id
                                  AND q.required = 1
                                  AND r.score IS NOT NULL)) / NULLIF(COUNT(*) *
                                                                         (SELECT COUNT(*)
                                                                          FROM questions
                                                                          WHERE required = 1), 0), 2) AS completion_percent
FROM participants p
GROUP BY COALESCE(p.group_name, 'Unassigned')
ORDER BY group_name;
```

## s18_sports — League matches

Team membership is fixed in this snapshot. Match scores are official; appearances contain only recorded player participation and may be incomplete. completed matches have scores, scheduled matches have NULL scores. League points are 3 for a win, 1 for a draw, and 0 for a loss.

[DDL and seed data](schemas/s18_sports.sql)

### s18_q01 · easy

List players on team 1. Return player_id, name, and position, ordered by player_id.

Coverage: filter.

```sql
SELECT id AS player_id,
       name,
       POSITION
FROM players
WHERE team_id = 1
ORDER BY id;
```

### s18_q02 · easy

List completed matches that ended in a draw. Return match_id, home_team_id, away_team_id, and the home score as goals_each, ordered by match_id.

Coverage: filter, column_comparison.

```sql
SELECT id AS match_id,
       home_team_id,
       away_team_id,
       home_score AS goals_each
FROM matches
WHERE status = 'completed'
    AND home_score = away_score
ORDER BY id;
```

### s18_q03 · easy

For every team, count players in its current roster. Return team_id, name, and player_count, ordered by team_id. Include teams with zero players.

Coverage: left_join, count, zero_inclusion.

```sql
SELECT t.id AS team_id,
       t.name,
       COUNT(p.id) AS player_count
FROM teams t
LEFT JOIN players p ON p.team_id = t.id
GROUP BY t.id,
         t.name
ORDER BY t.id;
```

### s18_q04 · medium

For every player, sum goals from their recorded appearances in completed matches only. Return player_id, name, and recorded_goals, using 0 if none. Order by recorded_goals descending, then player_id.

Coverage: left_join, conditional_aggregation, coalesce.

```sql
SELECT p.id AS player_id,
       p.name,
       COALESCE(SUM(CASE
                        WHEN m.status = 'completed' THEN a.goals
                        ELSE 0
                    END), 0) AS recorded_goals
FROM players p
LEFT JOIN appearances a ON a.player_id = p.id
LEFT JOIN matches m ON m.id = a.match_id
GROUP BY p.id,
         p.name
ORDER BY recorded_goals DESC,
         p.id;
```

### s18_q05 · medium

List distinct team_id values for teams that have played in at least one completed match, whether at home or away. Order by team_id.

Coverage: union, duplicate_elimination.

```sql
SELECT home_team_id AS team_id
FROM matches
WHERE status = 'completed'
UNION
SELECT away_team_id AS team_id
FROM matches
WHERE status = 'completed'
ORDER BY team_id;
```

### s18_q06 · medium

Which teams have won at least one completed home match and at least one completed away match? Return distinct team_id values ascending.

Coverage: intersect, column_comparison.

```sql
SELECT home_team_id AS team_id
FROM matches
WHERE status = 'completed'
    AND home_score > away_score INTERSECT
SELECT away_team_id AS team_id
FROM matches
WHERE status = 'completed'
    AND away_score > home_score
ORDER BY team_id;
```

### s18_q07 · medium

Compute league points for every team from completed matches: 3 per win, 1 per draw, 0 per loss. Return team_id, name, and points, including 0 for teams without completed matches. Order by points descending, then team_id.

Coverage: union_all, case, left_join, zero_inclusion.

```sql
WITH earned AS
    (SELECT home_team_id AS team_id,
            CASE
                WHEN home_score > away_score THEN 3
                WHEN home_score = away_score THEN 1
                ELSE 0
            END AS points
     FROM matches
     WHERE status = 'completed'
     UNION ALL SELECT away_team_id AS team_id,
                      CASE
                          WHEN away_score > home_score THEN 3
                          WHEN away_score = home_score THEN 1
                          ELSE 0
                      END AS points
     FROM matches
     WHERE status = 'completed')
SELECT t.id AS team_id,
       t.name,
       COALESCE(SUM(e.points), 0) AS points
FROM teams t
LEFT JOIN earned e ON e.team_id = t.id
GROUP BY t.id,
         t.name
ORDER BY points DESC,
         t.id;
```

### s18_q08 · hard

Find teams with at least one completed match and no completed losses. Return team_id and name, ordered by team_id. Ignore scheduled matches.

Coverage: exists, not_exists, correlated_subquery.

```sql
SELECT t.id AS team_id,
       t.name
FROM teams t
WHERE EXISTS
        (SELECT 1
         FROM matches m
         WHERE m.status = 'completed'
             AND (m.home_team_id = t.id
                  OR m.away_team_id = t.id))
    AND NOT EXISTS
        (SELECT 1
         FROM matches m
         WHERE m.status = 'completed'
             AND ((m.home_team_id = t.id
                   AND m.home_score < m.away_score)
                  OR (m.away_team_id = t.id
                      AND m.away_score < m.home_score)))
ORDER BY t.id;
```

### s18_q09 · hard

Find players with a recorded appearance in every completed match involving their current team. Require that the team has at least one completed match. Return player_id and name, ordered by player_id. A missing appearance does not count as participation.

Coverage: relational_division, exists, not_exists.

```sql
SELECT p.id AS player_id,
       p.name
FROM players p
WHERE EXISTS
        (SELECT 1
         FROM matches m
         WHERE m.status = 'completed'
             AND (m.home_team_id = p.team_id
                  OR m.away_team_id = p.team_id))
    AND NOT EXISTS
        (SELECT 1
         FROM matches m
         WHERE m.status = 'completed'
             AND (m.home_team_id = p.team_id
                  OR m.away_team_id = p.team_id)
             AND NOT EXISTS
                 (SELECT 1
                  FROM appearances a
                  WHERE a.match_id = m.id
                      AND a.player_id = p.id))
ORDER BY p.id;
```

### s18_q10 · hard

For each team that has won a completed match, identify the strongest opponent it defeated. Strength is that opponent's total league points from all completed matches (3 for a win, 1 for a draw, 0 for a loss). Choose the lowest opponent ID if points tie. Return team_id, opponent_id, and opponent_points, ordered by team_id. Count an opponent once even if defeated repeatedly.

Coverage: cte, nested_aggregation, not_exists, correlated_subquery, ties, union_all.

```sql
WITH outcomes AS
    (SELECT home_team_id AS team_id,
            away_team_id AS opponent_id,
            CASE
                WHEN home_score > away_score THEN 3
                WHEN home_score = away_score THEN 1
                ELSE 0
            END AS points
     FROM matches
     WHERE status = 'completed'
     UNION ALL SELECT away_team_id,
                      home_team_id,
                      CASE
                          WHEN away_score > home_score THEN 3
                          WHEN away_score = home_score THEN 1
                          ELSE 0
                      END
     FROM matches
     WHERE status = 'completed'),
     standings AS
    (SELECT team_id,
            SUM(points) AS points
     FROM outcomes
     GROUP BY team_id),
     defeated AS
    (SELECT DISTINCT o.team_id,
                     o.opponent_id,
                     s.points AS opponent_points
     FROM outcomes o
     JOIN standings s ON s.team_id = o.opponent_id
     WHERE o.points = 3)
SELECT d.team_id,
       d.opponent_id,
       d.opponent_points
FROM defeated d
WHERE NOT EXISTS
        (SELECT 1
         FROM defeated d2
         WHERE d2.team_id = d.team_id
             AND (d2.opponent_points > d.opponent_points
                  OR (d2.opponent_points = d.opponent_points
                      AND d2.opponent_id < d.opponent_id)))
ORDER BY d.team_id;
```

## s19_experiments — Scientific experiments

Runs belong to experiments and have control or treatment variants. Measurements can include repeated readings for the same run and metric; NULL values are missing readings. A metric with a non-NULL target is a target metric. Only completed runs qualify where specified; averages exclude NULL readings.

[DDL and seed data](schemas/s19_experiments.sql)

### s19_q01 · easy

List completed runs. Return run_id, experiment_id, and variant, in that order, sorted by run_id ascending.

Coverage: filter, order_by.

```sql
SELECT id AS run_id,
       experiment_id, variant
FROM runs
WHERE status = 'completed'
ORDER BY run_id;
```

### s19_q02 · easy

List stored measurements whose reading is NULL. Return measurement_id, run_id, and metric, in that order, sorted by measurement_id ascending. Include all run statuses.

Coverage: is_null, filter.

```sql
SELECT id AS measurement_id,
       run_id,
       metric
FROM measurements
WHERE value IS NULL
ORDER BY measurement_id;
```

### s19_q03 · easy

Which defined metrics have never had a measurement row recorded, including rows with NULL readings? Return metric and unit, in that order, sorted by metric ascending. Include all runs.

Coverage: not_exists, anti_join.

```sql
SELECT m.name AS metric,
       m.unit
FROM metrics AS m
WHERE NOT EXISTS
        (SELECT 1
         FROM measurements AS x
         WHERE x.metric = m.name)
ORDER BY metric;
```

### s19_q04 · medium

For every experiment, return experiment_id, name, run_count, completed_runs, and failed_runs, in that order. Include experiments without runs with zero counts; running runs count only toward run_count. Sort by experiment_id ascending.

Coverage: left_join, conditional_aggregation, zero_matches.

```sql
SELECT e.id AS experiment_id,
       e.name,
       COUNT(r.id) AS run_count,
       SUM(CASE
               WHEN r.status = 'completed' THEN 1
               ELSE 0
           END) AS completed_runs,
       SUM(CASE
               WHEN r.status = 'failed' THEN 1
               ELSE 0
           END) AS failed_runs
FROM experiments AS e
LEFT JOIN runs AS r ON r.experiment_id = e.id
GROUP BY e.id,
         e.name
ORDER BY experiment_id;
```

### s19_q05 · medium

Find runs with at least one non-NULL temperature reading but no non-NULL pressure reading. Include every run status. Return distinct run_id values sorted ascending.

Coverage: except, set_difference, nulls.

```sql
SELECT run_id
FROM measurements
WHERE metric = 'temperature'
    AND value IS NOT NULL
EXCEPT
SELECT run_id
FROM measurements
WHERE metric = 'pressure'
    AND value IS NOT NULL
ORDER BY run_id;
```

### s19_q06 · medium

Combine all non-NULL temperature readings from run 1 with all non-NULL temperature readings from run 2, keeping repeated readings even when values match. Return one column named value, sorted ascending.

Coverage: union_all, duplicates.

```sql
SELECT value
FROM measurements
WHERE run_id = 1
    AND metric = 'temperature'
    AND value IS NOT NULL
UNION ALL
SELECT value
FROM measurements
WHERE run_id = 2
    AND metric = 'temperature'
    AND value IS NOT NULL
ORDER BY value;
```

### s19_q07 · medium

For every run, return run_id and target_coverage_percent, in that order, sorted by run_id. Coverage is 100 times the number of distinct target metrics with at least one non-NULL reading for that run divided by the number of defined metrics with non-NULL targets. Include all statuses and runs without readings, use zero coverage when no target is measured, return NULL if there are no target metrics, and round percentages to two decimals.

Coverage: correlated_subquery, count_distinct, ratio, nullif, zero_matches.

```sql
SELECT r.id AS run_id,
       ROUND(100.0 *
                 (SELECT COUNT(DISTINCT x.metric)
                  FROM measurements AS x
                  JOIN metrics AS m ON m.name = x.metric
                  WHERE x.run_id = r.id
                      AND x.value IS NOT NULL
                      AND m.target IS NOT NULL) / NULLIF(
                                                             (SELECT COUNT(*)
                                                              FROM metrics
                                                              WHERE target IS NOT NULL), 0), 2) AS target_coverage_percent
FROM runs AS r
ORDER BY run_id;
```

### s19_q08 · hard

Find completed runs that have at least one non-NULL reading for every defined metric whose target is non-NULL. If there are no target metrics, all completed runs qualify. Return run_id and experiment_id, in that order, sorted by run_id ascending.

Coverage: relational_division, not_exists, correlated_subquery.

```sql
SELECT r.id AS run_id,
       r.experiment_id
FROM runs AS r
WHERE r.status = 'completed'
    AND NOT EXISTS
        (SELECT 1
         FROM metrics AS m
         WHERE m.target IS NOT NULL
             AND NOT EXISTS
                 (SELECT 1
                  FROM measurements AS x
                  WHERE x.run_id = r.id
                      AND x.metric = m.name
                      AND x.value IS NOT NULL))
ORDER BY run_id;
```

### s19_q09 · hard

Compare treatment and control yield for each experiment using completed runs only. First average non-NULL yield readings within each run, then average those run means within each variant so runs have equal weight. Ignore runs with no known yield and include only experiments with a known mean for both variants. Return experiment_id, control_mean, treatment_mean, and percent_change, in that order. Percent change is 100 times (treatment minus control) divided by control; return NULL when control is zero. Round all three calculated values to two decimals and sort by experiment_id.

Coverage: cte, nested_aggregation, conditional_aggregation, ratio, nullif.

```sql
WITH run_means AS
    (SELECT r.id AS run_id,
            r.experiment_id,
            r.variant,
            AVG(x.value) AS mean_yield
     FROM runs AS r
     JOIN measurements AS x ON x.run_id = r.id
     WHERE r.status = 'completed'
         AND x.metric = 'yield'
         AND x.value IS NOT NULL
     GROUP BY r.id,
              r.experiment_id,
              r.variant),
     experiment_means AS
    (SELECT experiment_id,
            AVG(CASE
                    WHEN variant = 'control' THEN mean_yield
                END) AS control_mean,
            AVG(CASE
                    WHEN variant = 'treatment' THEN mean_yield
                END) AS treatment_mean
     FROM run_means
     GROUP BY experiment_id)
SELECT experiment_id,
       ROUND(control_mean, 2) AS control_mean,
       ROUND(treatment_mean, 2) AS treatment_mean,
       ROUND(100.0 * (treatment_mean - control_mean) / NULLIF(control_mean, 0), 2) AS percent_change
FROM experiment_means
WHERE control_mean IS NOT NULL
    AND treatment_mean IS NOT NULL
ORDER BY experiment_id;
```

### s19_q10 · hard

For each metric with a non-NULL target, find the completed runs whose mean non-NULL reading is closest to that target. Average repeated readings within a run, omit runs without a known reading, compare absolute distances before rounding, and keep all tied runs. Return metric, run_id, mean_value, and distance, in that order. Round mean_value and distance to two decimals and sort by metric ascending, then run_id ascending.

Coverage: cte, nested_aggregation, not_exists, correlated_subquery, ties, absolute_difference.

```sql
WITH run_means AS
    (SELECT m.name AS metric,
            r.id AS run_id,
            AVG(x.value) AS mean_value,
            ABS(AVG(x.value) - m.target) AS distance
     FROM metrics AS m
     JOIN measurements AS x ON x.metric = m.name
     JOIN runs AS r ON r.id = x.run_id
     WHERE m.target IS NOT NULL
         AND x.value IS NOT NULL
         AND r.status = 'completed'
     GROUP BY m.name,
              m.target,
              r.id)
SELECT a.metric,
       a.run_id,
       ROUND(a.mean_value, 2) AS mean_value,
       ROUND(a.distance, 2) AS distance
FROM run_means AS a
WHERE NOT EXISTS
        (SELECT 1
         FROM run_means AS b
         WHERE b.metric = a.metric
             AND b.distance < a.distance)
ORDER BY a.metric,
         a.run_id;
```

## s20_projects — Project tasks and dependencies

Projects contain tasks; dependencies point from a dependent task to its prerequisite. Dependencies form an acyclic graph. Time entries may be logged by someone other than the assignee. Known cost is hours times billed_rate for entries with a known rate; a NULL rate represents unpriced work. Tasks may be unassigned, lack due dates, or have no time entries.

[DDL and seed data](schemas/s20_projects.sql)

### s20_q01 · easy

List tasks with no assignee, including every status. Return task_id, project_id, title, and due_date, in that order, keeping NULL due dates. Sort by task_id ascending.

Coverage: is_null, filter.

```sql
SELECT id AS task_id,
       project_id,
       title,
       due_date
FROM tasks
WHERE assignee_id IS NULL
ORDER BY task_id;
```

### s20_q02 · easy

For every person, total the hours they personally logged across all tasks and dates, regardless of task status or assignment. Return person_id, name, and total_hours, in that order; use zero for people with no entries, round hours to two decimals, and sort by person_id ascending.

Coverage: left_join, aggregation, coalesce, zero_matches.

```sql
SELECT p.id AS person_id,
       p.name,
       ROUND(COALESCE(SUM(e.hours), 0), 2) AS total_hours
FROM people AS p
LEFT JOIN time_entries AS e ON e.person_id = p.id
GROUP BY p.id,
         p.name
ORDER BY person_id;
```

### s20_q03 · easy

List tasks with no due date, regardless of status. Return task_id, title, and status, in that order, sorted by task_id ascending.

Coverage: is_null, filter.

```sql
SELECT id AS task_id,
       title,
       status
FROM tasks
WHERE due_date IS NULL
ORDER BY task_id;
```

### s20_q04 · medium

For every project, return project_id, name, known_cost, and unpriced_hours, in that order. Include all task statuses and dates. Known cost is the sum of hours times billed_rate for entries with a non-NULL rate; unpriced hours are hours with a NULL rate. Use zero for missing totals and projects with no work, round both totals to two decimals, and sort by project_id ascending.

Coverage: left_join, conditional_aggregation, nulls, zero_matches.

```sql
SELECT p.id AS project_id,
       p.name,
       ROUND(COALESCE(SUM(e.hours * e.billed_rate), 0), 2) AS known_cost,
       ROUND(COALESCE(SUM(CASE
                              WHEN e.billed_rate IS NULL THEN e.hours
                              ELSE 0
                          END), 0), 2) AS unpriced_hours
FROM projects AS p
LEFT JOIN tasks AS t ON t.project_id = p.id
LEFT JOIN time_entries AS e ON e.task_id = t.id
GROUP BY p.id,
         p.name
ORDER BY project_id;
```

### s20_q05 · medium

Find tasks whose own status is not done and whose direct prerequisites are all done. Tasks without prerequisites qualify. Return task_id and title, in that order, sorted by task_id ascending. Consider only direct prerequisites, regardless of the task due date or assignee.

Coverage: not_exists, relational_division, correlated_subquery.

```sql
SELECT t.id AS task_id,
       t.title
FROM tasks AS t
WHERE t.status <> 'done'
    AND NOT EXISTS
        (SELECT 1
         FROM dependencies AS d
         JOIN tasks AS prerequisite ON prerequisite.id = d.depends_on
         WHERE d.task_id = t.id
             AND prerequisite.status <> 'done')
ORDER BY task_id;
```

### s20_q06 · medium

Find direct dependency edges for which the dependent task and its prerequisite have the same non-NULL assignee, regardless of task status. Return task_id, depends_on, and assignee_id, in that order. Sort by task_id ascending, then depends_on ascending.

Coverage: self_join, nulls, join.

```sql
SELECT d.task_id,
       d.depends_on,
       dependent.assignee_id
FROM dependencies AS d
JOIN tasks AS dependent ON dependent.id = d.task_id
JOIN tasks AS prerequisite ON prerequisite.id = d.depends_on
WHERE dependent.assignee_id = prerequisite.assignee_id
ORDER BY d.task_id,
         d.depends_on;
```

### s20_q07 · medium

Which projects contain at least one task but no task with status blocked? Return project_id and name, in that order, sorted by project_id ascending. Projects with no tasks must be excluded.

Coverage: exists, not_exists, anti_join, correlated_subquery.

```sql
SELECT p.id AS project_id,
       p.name
FROM projects AS p
WHERE EXISTS
        (SELECT 1
         FROM tasks AS t
         WHERE t.project_id = p.id)
    AND NOT EXISTS
        (SELECT 1
         FROM tasks AS t
         WHERE t.project_id = p.id
             AND t.status = 'blocked')
ORDER BY project_id;
```

### s20_q08 · hard

List every direct or indirect prerequisite of task 5. Follow dependency edges recursively, return each prerequisite only once even if reachable through multiple paths, and exclude task 5 itself. Return task_id and title, in that order, sorted by task_id ascending; include prerequisites of any status.

Coverage: recursive_cte, union, deduplication, transitive_closure.

```sql
WITH RECURSIVE prerequisites(task_id) AS
    (SELECT depends_on
     FROM dependencies
     WHERE task_id = 5
     UNION SELECT d.depends_on
     FROM dependencies AS d
     JOIN prerequisites AS p ON d.task_id = p.task_id)
SELECT t.id AS task_id,
       t.title
FROM prerequisites AS p
JOIN tasks AS t ON t.id = p.task_id
WHERE t.id <> 5
ORDER BY task_id;
```

### s20_q09 · hard

Find the task with the greatest known cost within each project, keeping all tied tasks and omitting projects with no tasks. Include every task status and date. A task known cost is the sum of hours times non-NULL billed_rate, or zero when it has no priced entries. Compare unrounded costs. Return project_id, task_id, title, and known_cost, in that order, round known_cost to two decimals, and sort by project_id then task_id ascending.

Coverage: cte, correlated_subquery, not_exists, groupwise_maximum, ties, zero_matches.

```sql
WITH task_costs AS
    (SELECT t.project_id,
            t.id AS task_id,
            t.title,
            COALESCE(SUM(e.hours * e.billed_rate), 0) AS known_cost
     FROM tasks AS t
     LEFT JOIN time_entries AS e ON e.task_id = t.id
     GROUP BY t.project_id,
              t.id,
              t.title)
SELECT a.project_id,
       a.task_id,
       a.title,
       ROUND(a.known_cost, 2) AS known_cost
FROM task_costs AS a
WHERE NOT EXISTS
        (SELECT 1
         FROM task_costs AS b
         WHERE b.project_id = a.project_id
             AND b.known_cost > a.known_cost)
ORDER BY a.project_id,
         a.task_id;
```

### s20_q10 · hard

For every project, return project_id, task_count, dependency_edge_count, and total_hours, in that order. Count each task once, count each direct dependency edge once for the project owning its dependent task, and sum each time entry once. Include all statuses and dates, preserve projects without tasks with zero totals, round hours to two decimals, and sort by project_id ascending.

Coverage: cte, multiple_aggregation_grains, fanout_safe, left_join, zero_matches.

```sql
WITH task_totals AS
    (SELECT project_id,
            COUNT(*) AS task_count
     FROM tasks
     GROUP BY project_id),
     dependency_totals AS
    (SELECT t.project_id,
            COUNT(*) AS dependency_edge_count
     FROM tasks AS t
     JOIN dependencies AS d ON d.task_id = t.id
     GROUP BY t.project_id),
     time_totals AS
    (SELECT t.project_id,
            SUM(e.hours) AS total_hours
     FROM tasks AS t
     JOIN time_entries AS e ON e.task_id = t.id
     GROUP BY t.project_id)
SELECT p.id AS project_id,
       COALESCE(t.task_count, 0) AS task_count,
       COALESCE(d.dependency_edge_count, 0) AS dependency_edge_count,
       ROUND(COALESCE(h.total_hours, 0), 2) AS total_hours
FROM projects AS p
LEFT JOIN task_totals AS t ON t.project_id = p.id
LEFT JOIN dependency_totals AS d ON d.project_id = p.id
LEFT JOIN time_totals AS h ON h.project_id = p.id
ORDER BY project_id;
```

# RQ2: Details and examplers of inenfficiency patterns

This inenfficiency pattern annotation system comprises 6 major categories and 23 fine-grained optimization labels, targeting different phases throughout the query lifecycle.

## Subquery Logic

**Subquery Logic** targets the structural unnesting and decoupling of hierarchical queries to transform procedural, row-by-row execution into efficient set-based operations. By eliminating redundant subquery invocations, it can minimize computational overhead and unlocks global plan optimization.

- **Plan Flattening**

    Collapses multi-layered nested subqueries or derived tables into a single  `SELECT` query block. 
    
    This allows the engine to evaluate all potential join paths and access methods across the entire query scope simultaneously, rather than being restricted by a fixed, hierarchical execution sequence.

    ```sql
    [BEFORE]
    SELECT dt.customer_id, dt.total_spent
    FROM (
        SELECT c.customer_id, SUM(o.amount) AS total_spent
        FROM customers c
        JOIN orders o ON c.id = o.customer_id
        GROUP BY c.customer_id
    ) dt
    WHERE dt.total_spent > 1000;

    [AFTER]
    SELECT c.customer_id, SUM(o.amount) AS total_spent
    FROM customers c
    JOIN orders o ON c.id = o.customer_id
    GROUP BY c.customer_id
    HAVING SUM(o.amount) > 1000;
    ```

- **Subquery Decorrelation**

    Replaces row-dependent correlated subqueries with Window Functions.

    This shift eliminates the expensive "row-by-row" execution loop. DBMS can calculate all required aggregates in a single pass over the data, drastically reducing CPU overhead and repeated buffer hits.

    ```sql
    [BEFORE]
    SELECT p.product_name, p.price
    FROM products p
    WHERE p.price > (
        SELECT AVG(sub.price)
        FROM products sub
        WHERE sub.category_id = p.category_id
    );

    [AFTER]
    SELECT product_name, price
    FROM (
        SELECT product_name, price,
            AVG(price) OVER(PARTITION BY category_id) as avg_cat_price
        FROM products
    ) t
    WHERE price > avg_cat_price;
    ```

- **Subquery Decoupling**

    Transform correlated subquery (referencing outer rows) into an uncorrelated subquery.

    Execute the inner query exactly once. The results can then be materialized or cached , preventing redundantly re-triggering the same subquery for every record processed by the outer query.

    ```sql
    [BEFORE]
    SELECT e.employee_id, e.salary
    FROM employees e
    WHERE e.salary < (
        SELECT MAX(salary)
        FROM employees sub
        WHERE sub.department_id = e.department_id
    );

    [AFTER]
    WITH DeptMax AS (
        SELECT department_id, MAX(salary) as max_sal
        FROM employees
        GROUP BY department_id
    )
    SELECT e.employee_id, e.salary
    FROM employees e
    JOIN DeptMax dm ON e.department_id = dm.department_id
    WHERE e.salary < dm.max_sal;
    ```

- **Subquery Joinify**

    Converts subquery predicates into standard Inner or Semi-Join operations.

    This allows DBMS to utilize more efficient relational algorithms and choose a better join sequence.

    ```sql
    [BEFORE]
    SELECT u.username
    FROM users u
    WHERE u.id IN (
        SELECT user_id
        FROM subscriptions
        WHERE status = 'Active'
    );

    [AFTER]
    SELECT DISTINCT u.username
    FROM users u
    JOIN subscriptions s ON u.id = s.user_id
    WHERE s.status = 'Active';
    ```
    
## Join Logic

**Join Logic** focuses on simplifying join graph and refining association types to prevent unnecessary data volume expansion. By removing redundant joins, it minimizes the memory and CPU footprint required to synchronize datasets.

- **Join Elimination**

    Remove redundant table references and join operations when key constraints confirm it would not affect the final result.

    ```sql
    [BEFORE]
    -- Assumption: `order.customer_id` refers to `customers.id` (PK)
    SELECT o.order_id, o.amount
    FROM orders o
    LEFT JOIN customers c ON o.customer_id = c.id;

    [AFTER]
    SELECT o.order_id, o.amount
    FROM orders o;
    ```

- **Join Tightening**

    Convert `OUTER JOIN` to `INNER JOIN` when existing filter predicates inherently exclude null-extended rows.

    This allows optimizer to reorder joins for better selectivity.

    ```sql
    [BEFORE]
    SELECT u.name, o.order_date
    FROM users u
    LEFT JOIN orders o ON u.id = o.user_id
    WHERE o.amount > 100;

    [AFTER]
    SELECT u.name, o.order_date
    FROM users u
    INNER JOIN orders o ON u.id = o.user_id
    WHERE o.amount > 100;
    ```

- **Semi-Join Conversion**

    Convert `INNER JOIN` to Semi-Join when the joined table is used only for existence filtering rather than projection.
  
    It prevents data explosion by stopping the scan as soon as the first match is found, drastically reducing intermediate results before aggregation.

    ```sql
    [BEFORE]
    SELECT DISTINCT d.dept_name
    FROM departments d
    JOIN employees e ON d.dept_id = e.dept_id
    WHERE e.salary > 100000; 

    [AFTER]
    SELECT d.dept_name
    FROM departments d
    WHERE EXISTS (
        SELECT 1 
        FROM employees e 
        WHERE e.dept_id = d.dept_id 
        AND e.salary > 100000
    );
    ```

## Predicate Logic

**Predicate Logic** focuses on the timing and form of data filtering to maximize index utilization and minimize computational load, by ensuring conditions are early and effectively applied.

- **Search Argumentable (SARGable) Rewrite**

    Rewrite function-wrapped columns or mathematical expressions into direct range comparison.

    This allows DBMS utilize indexes for faster lookups.

    ```sql
    [BEFORE]
    SELECT order_id 
    FROM orders 
    WHERE YEAR(created_at) = 2023;

    [AFTER]
    SELECT order_id 
    FROM orders 
    WHERE created_at >= '2023-01-01' 
    AND created_at < '2024-01-01';
    ```

- **Predicate Pull-down**

    Move filter conditions on non-aggregated columns from the `HAVING` clause to `WHERE` clause.

    By executing early filtering, it discards irrelevant records before they reach high-overhead grouping and aggregation phases.

    ```sql
    [BEFORE]
    SELECT region, SUM(amount) 
    FROM sales 
    GROUP BY region 
    HAVING region = 'North';

    [AFTER]
    SELECT region, SUM(amount) 
    FROM sales 
    WHERE region = 'North' 
    GROUP BY region;
    ```

- **Constant Folding**

    Transform constant expressions and deterministic functions into literal.

    ```sql
    [BEFORE]
    SELECT product_name 
    FROM inventory 
    WHERE stock_value > 500 * 1.05;

    [AFTER]
    SELECT product_name 
    FROM inventory 
    WHERE stock_value > 525;
    ```

## Access Strategy

**Access Strategy** targets the aggressive pruning of data at the architectural foundation to transform heavy, unfiltered I/O into lean and efficient data retrieval. By discarding irrelevant records and columns before they enter the processing pipeline, it minimizes hardware-level bottlenecks and optimizes end-to-end bandwidth utilization.

- **Storage Pushdown**
  
    Push filter predicates from `WHERE` clauses to storage layer or underlying data source.
    
    By filtering data at the source, it can minimize transport overhead and bypass the congestion caused by transferring massive, unfiltered datasets.

    ```sql
    [BEFORE]
    SELECT * FROM web_logs 
    WHERE event_time >= '2023-01-01 00:00:00' 
    AND event_time < '2023-01-02 00:00:00';

    [AFTER]
    SELECT * FROM web_logs 
    WHERE dt = '2023-01-01' 
    AND event_time >= '2023-01-01 00:00:00';
    ```

- **Column Pruning**

    Only retrieve columns required for the final projection or intermediate calculations.

    ```sql
    [BEFORE]
    SELECT * FROM users 
    WHERE status = 'Active';

    [AFTER]
    SELECT user_id, email 
    FROM users 
    WHERE status = 'Active';
    ```

- **Limit Early-Stop**

    Propagates row-count constraints directly into the data scanning or sorting operators.

    It can terminate execution uimmediately once the required number of records is retrieved, preventing full table scans or global sorting.

    ```sql
    [BEFORE]
    -- NLQ: "Show me the 10 most recent high-value orders (over $1000) for the dashboard."
    SELECT order_id, amount, created_at 
    FROM orders 
    WHERE amount > 1000 
    ORDER BY created_at DESC;

    [AFTER]
    SELECT order_id, amount, created_at 
    FROM orders 
    WHERE amount > 1000 
    ORDER BY created_at DESC
    LIMIT 10;
    ```


- **CTE Pushdown**

    Move filter conditions into Common Table Expressions (CTEs) to reduce records before subsequent join operations.

    ```sql
    [BEFORE]
    WITH SalesData AS (
        SELECT s.sale_id, s.amount, s.region_id
        FROM sales s
    )
    SELECT *
    FROM SalesData sd
    JOIN regions r ON sd.region_id = r.id
    WHERE sd.amount > 1000;

    [AFTER]
    WITH SalesData AS (
        SELECT s.sale_id, s.amount, s.region_id
        FROM sales s
        WHERE s.amount > 1000
    )
    SELECT *
    FROM SalesData sd
    JOIN regions r ON sd.region_id = r.id;
    ```

## Timing Strategy

**Timing Strategy** aims to optimize the execution order of relational operators by deferring resource-intensive computations until records has been reduced through preliminary filtering. By prioritizing the evaluation of highly selective predicates to enable early data reduction, it can minimize intermediate result.

- **Early Aggregation**

    Perform grouping and aggregate calculations before it participates in a join.

    By consolidating records prior to the join phase, it can prevent cardinality explosion and significantly reduces the size of intermediate result sets.

    ```sql
    [BEFORE]
    SELECT c.customer_name, SUM(o.amount)
    FROM customers c
    JOIN orders o ON c.id = o.customer_id
    GROUP BY c.customer_id, c.customer_name;

    [AFTER]
    SELECT c.customer_name, o_agg.total_amount
    FROM customers c
    JOIN (
        SELECT customer_id, SUM(amount) as total_amount
        FROM orders
        GROUP BY customer_id
    ) o_agg ON c.id = o_agg.customer_id;
    ```

- **Lazy Join**

    Defers joins until primary filtering and aggregation have sufficiently reduced records.

    This can minimize data carried through the pipeline and avoid redundant processing for rows that are eventually discarded.

    ```sql
    [BEFORE]
    SELECT 
        p.product_name, p.description, s.sale_date
    FROM sales s
    JOIN products p ON s.product_id = p.id
    ORDER BY s.sale_date DESC
    LIMIT 10;

    [AFTER]
    SELECT 
        p.product_name, p.description, top_sales.sale_date
    FROM (
        SELECT product_id, sale_date
        FROM sales
        ORDER BY sale_date DESC
        LIMIT 10
    ) top_sales
    JOIN products p ON top_sales.product_id = p.id;
    ```

- **Lazy Aggregation**

    Defers aggregate function evaluation until after the `WHERE` and `LIMIT` have been applied.

    By restricting high-cost computations to the final result set, it can reduce total CPU overhead and ensures that expensive functions are only executed for qualified rows.

    ```sql
    [BEFORE]
    SELECT region, COMPLEX_CALC(SUM(amount)) as metric
    FROM sales
    GROUP BY region
    HAVING SUM(amount) > 10000;

    [AFTER]
    WITH FilteredGroups AS (
        SELECT region, SUM(amount) as total_amt
        FROM sales
        GROUP BY region
        HAVING SUM(amount) > 10000
    )
    SELECT region, COMPLEX_CALC(total_amt) as metric
    FROM FilteredGroups;
    ```

- **Join Reordering**

    Rearranges join sequence based on estimated table cardinality and predicate selectivity.

    It can maintain the smallest possible intermediate result by joining the most restrictive tables first.

    ```sql
    [BEFORE]
    /* Assumption: 
       - 'users'  (1M rows)
       - 'orders' (10M rows) 
       - 'flags'  (100 rows, very small & selective)
    */

    SELECT *
    FROM users u
    JOIN orders o ON u.id = o.user_id
    JOIN flags f ON u.flag_id = f.id
    WHERE f.type = 'Suspicious';

    [AFTER]
    SELECT *
    FROM flags f
    JOIN users u ON f.id = u.flag_id
    JOIN orders o ON u.id = o.user_id
    WHERE f.type = 'Suspicious';
    ```

## Operator Strategy

**Operator Strategy** restructures query to eliminate redundant computations and data materialization. It can minimizie per-scan overhead and mitigate combinatorial explosion in complex correlations.

- **Case Aggregation**

    Leverages `CASE WHEN` expression within a single aggregate operator to compute multiple conditional metrics in one table scan.

    It can minimize I/O and reduces the CPU cycles spent on repeated data fetching.

    ```sql
    [BEFORE]
    SELECT 
        (SELECT COUNT(*) FROM orders WHERE status = 'Pending') as pending_count,
        (SELECT COUNT(*) FROM orders WHERE status = 'Shipped') as shipped_count,
        (SELECT COUNT(*) FROM orders WHERE status = 'Cancelled') as cancelled_count;

    [AFTER]
    SELECT 
        COUNT(CASE WHEN status = 'Pending' THEN 1 END) as pending_count,
        COUNT(CASE WHEN status = 'Shipped' THEN 1 END) as shipped_count,
        COUNT(CASE WHEN status = 'Cancelled' THEN 1 END) as cancelled_count
    FROM orders;
    ```

- **Fan-Out Pruning**

    Restructures one-to-many relationships before final join to prevent multiplicative row expansion.

    ```sql
    [BEFORE]
    SELECT 
        u.name, COUNT(o.id) as order_count, 
        COUNT(l.id) as login_count
    FROM users u
    JOIN orders o ON u.id = o.user_id
    JOIN login_logs l ON u.id = l.user_id
    GROUP BY u.name;

    [AFTER]
    WITH OrderStats AS (
        SELECT user_id, COUNT(*) as cnt 
        FROM orders 
        GROUP BY user_id
    ),
    LoginStats AS (
        SELECT user_id, COUNT(*) as cnt 
        FROM login_logs 
        GROUP BY user_id
    )
    SELECT u.name, os.cnt, ls.cnt
    FROM users u
    JOIN OrderStats os ON u.id = os.user_id
    JOIN LoginStats ls ON u.id = ls.user_id;
    ```

- **Group-Key Pruning**

    Removes constant or redundant columns from the `GROUP BY` clause after their values have been fixed by predicates.

    ```sql
    [BEFORE]
    SELECT category_id, status, COUNT(*) 
    FROM products 
    WHERE status = 'Active' 
    GROUP BY category_id, status;

    [AFTER]
    SELECT category_id, 'Active' as status, COUNT(*) 
    FROM products 
    WHERE status = 'Active' 
    GROUP BY category_id;
    ```

- **Existence Probing**

    Replaces full aggregation (`GROUP BY`, `DISTINCT`) with lightweight existence checks (`EXISTS`, `IN`) for boolean validation.

    By switching from full-set processing to boolean validation, it can significantly reduce execution time and avoids unnecessary data reading.

    ```sql
    [BEFORE]
    SELECT * FROM products p
    WHERE product_id IN (
        SELECT DISTINCT product_id 
        FROM orders
    );

    [AFTER]
    SELECT * FROM products p
    WHERE EXISTS (
        SELECT 1 
        FROM orders o 
        WHERE o.product_id = p.product_id
    );
    ```

- **Filter Injection**

    Pushes selective predicates into correlated subqueries.

    ```sql
    [BEFORE]
    SELECT c.name, o.amount
    FROM customers c
    JOIN orders o ON c.id = o.customer_id
    WHERE o.order_date >= '2023-01-01'
    AND o.amount = (
        SELECT MAX(amount) 
        FROM orders sub 
        WHERE sub.customer_id = c.id
    );

    [AFTER]
    SELECT c.name, o.amount
    FROM customers c
    JOIN orders o ON c.id = o.customer_id
    WHERE o.order_date >= '2023-01-01'
    AND o.amount = (
        SELECT MAX(amount) 
        FROM orders sub 
        WHERE sub.customer_id = c.id
        AND sub.order_date >= '2023-01-01' -- Injected
    );
    ```

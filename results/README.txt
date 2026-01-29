Please store your generated SQL results in this directory. 

- The file shuold be named as `completion.jsonl`.

- Each JSON object must contain the following fields:

    - id (Integer): The unique task identifier (task_id).
    - res (String): The full predicted SQL query (pred_sql).

    Example:
    ```
    {"id": 1, "res": "SELECT * FROM users WHERE age > 25"}
    {"id": 2, "res": "SELECT count(*) FROM orders"}
    ```
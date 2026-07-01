# EESQLBench: Efficiency-Orented Text-to-SQL Benchmark

<p align="center">
  <img src="https://github.com/EESQLBench/eesqlbench.github.io/blob/main/logo.png?raw=true" style="width: 50%; min-width: 100px; display: block; margin: auto;">
</p>

<p align="center" width="100%">
  <a href="#">🔗 Paper</a>
  &nbsp; &nbsp;
  <a href="https://bird-bench.github.io/">🏆 Leaderboard</a>
<p>


## Overview

EESQLBench is an efficiency-oriented Text-to-SQL benchmark containing 213 tasks. It bridges the gap between academic research and real-world performance requirements by challenging models to generate not just correct, but execution-optimized SQL queries. The dataset is constructed via rigorous schema intervention and expert refinement to amplify performance-sensitive behaviors.

## Dataset Introduction

The dataset mainly contains the following resources:

- `database`: Download ([MySQL ver.](https://pan.quark.cn/s/9e078887f3fd?pwd=W4PA) / [SQLite ver.](https://pan.quark.cn/s/5bd005918e43?pwd=fBiq)) it to the project root directory.

    ```bash
    tar -xzvf EESQL.tar.gz # Uncompress
    cd data && bash import.sh   # Import data to MySQL
    ```

- `task`: Text to efficient SQL tasks are stored as a jsonl file at [`./task/tasks.jsonl`](./task/tasks.jsonl). Each task has 4 main parts:

  1. **Task Meta**
  
      - `task_id`: unique identifier for each optimization task.
      - `difficulty`: complexity level of the SQL optimization, categorized as simple, medium, or hard.
  
  2. **Database Context**

      - `db_name`: the name of involved database. 
       
        Detailed schema information (DDL, foreign keys, value examples) can be found in the `./meta` directory under the corresponding database folder.

  3. **Natural Language Question**

       - `nl_question`: curated by human crowdsourcing according to database descriptions, database contents.

  4. **Ground Truth**

       - `original_sql`: logically correct but inefficient SQL query that answers the question (often mimics a direct translation of the NL intent).
       - `optimized_sql`: efficient SQL query that produces the same result set but with better performance.
       - `optimization_type`: list of descriptive labels indicating the specific performance tuning techniques applied.

## Evaluation

### Metrics

EESQLBench supports 4 key metrics to evaluate both the correctness and the efficiency of the generated SQL queries.

1. **Execution Accuracy (EX)**

    Measures the percentage of generated SQL queries that produce the correct result set when executed against the database.
  
2. **Valid Efficiency Score (VES)**

    A holistic metric that combines accuracy and execution time efficiency. 

3. **Cost Reachability (CR)**

    Evaluates the database I/O efficiency by comparing the scanned rows of the predicted SQL against the expert-optimized SQL.

4. **Acceptable Reachability at k (AR@k)**

    Measures the robustness of the model's optimization capabilities. It calculates the percentage of queries where the efficiency ratio meets or exceeds a specific threshold $k$.
  
    Common thresholds ($k$) include `0.8, 1.0 (baseline)`

### Usage

```bash
cd evaluation

# 1. Run the full evaluation (All 4 Metrics)
# This is the default behavior if no arguments are provided.
python evalpy

# 2. Calculate specific metrics only (Uses cached EX results)
python eval.py --ex    # Calculate  Execution Accuracy
python eval.py --cr    # Calculate Cost Reachability
python eval.py --ves   # Calculate Valid Efficiency Score
python evalu.py --ar   # Calculate AR@k distribution

# 3. Combine flags
# Example: Calculate only CR and VES
python evaluator.py --cr --ves
```

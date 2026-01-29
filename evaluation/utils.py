import sys, json, re, time
from typing import List
from pathlib import Path
from collections import Counter
from pymysql.cursors import Cursor
parent_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(parent_dir))

from task.OptimizeTask import OptimizeTask

TASK_FILE = parent_dir / "task/tasks.jsonl"
def load_tasks() -> List[OptimizeTask]:
    tasks = []
    with open(TASK_FILE, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line: continue
            try:
                data = json.loads(line)
                task = OptimizeTask.from_dict(data)
                if not task.difficulty == 'skip':
                    tasks.append(task)
            except json.JSONDecodeError as e:
                print(f"Warning: Invalid JSON on line {line_num}: {e}")
            except Exception as e:
                print(f"Warning: Failed to parse task on line {line_num}: {e}")
    return tasks

def is_identical(sql_1: str, sql_2: str, cursor: Cursor) -> bool:
    cursor.execute(sql_1)
    res_1 = list(cursor.fetchall())
    cursor.execute(sql_2)
    res_2 = list(cursor.fetchall())
    
    order_matters = "ORDER BY" in sql_1.upper()
    if order_matters:
        return res_1 == res_2
    else:
        return Counter(res_1) == Counter(res_2)
    
def get_tot_scanned_rows(sql: str, cursor: Cursor, debug: bool=False) -> int:
    actual_rows = 0
    try:
        explain_analyze_sql = f"EXPLAIN ANALYZE {sql}"
        cursor.execute(explain_analyze_sql)
        explain_output = cursor.fetchone()[0]
        if debug:
            print("=== Execution Plan (EXPLAIN ANALYZE) ===")
            print(explain_output)
        
        explain_output = explain_output.splitlines()
        for line in explain_output:
            if     re.search(r'\(never executed\)', line) \
                or re.match(r'^\s*-> Hash', line) \
                or re.match(r'^\s*-> Select #', line): 
                continue
            try:
                r = re.findall(r'rows=(\d+)', line)[-1]
                l = re.findall(r'loops=(\d+)', line)[-1]
                actual_rows += int(r) * int(l)
            except Exception as e:
                print(f'Error: {str(e)}')
                print(f'{line = }')
                actual_rows += 0
    except Exception as e:
        print(f"Database error: {e}")
    
    return actual_rows

def get_exec_time(sql: str, cursor: Cursor):
    try:
        start_time = time.perf_counter()
        cursor.execute(sql)
        cursor.fetchall()
        interval = time.perf_counter() - start_time
        return interval
    except Exception as e:
        print(e)
        return -1.0
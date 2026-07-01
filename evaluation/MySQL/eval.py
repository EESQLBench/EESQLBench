import os, json, math, argparse
import pymysql
from pathlib import Path
from tqdm import tqdm
from collections import defaultdict
from typing import List, Tuple, Dict
from utils import load_tasks, get_tot_scanned_rows, is_identical, get_exec_time

# 数据库配置
DB_CONFIG = {
    "host":     os.getenv("MYSQL_HOST", "localhost"),
    "user":     os.getenv("MYSQL_USER", "root"),
    "password": os.getenv("MYSQL_PASSWORD", ""),
    "port":     int(os.getenv("MYSQL_PORT", 3306)),
}

class Evaluator:
    def __init__(self):
        root_dir = Path(__file__).resolve().parent.parent
        self.task_path       = root_dir / 'task' / 'tasks.jsonl'
        self.completion_path = root_dir / 'results' / 'completion.jsonl'
        self.save_path       = root_dir / 'results' / 'EX.json'

    def _load_completions(self) -> List[Tuple[int, str]]:
        completions = []
        try:
            with open(self.completion_path, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        data = json.loads(line)
                        completions.append((data['id'], data['res']))
                    except: continue
        except Exception: pass
        return completions

    def _ensure_ex_results(self) -> List[Dict]:
        if self.save_path.exists():
            with open(self.save_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            print("[Info] EX results not found. Triggering automatic calculation...")
            return self.calc_EX()
        
    def _aggregate_data(self, details: List[Dict]):
        all_tasks = load_tasks(self.task_path)
        
        stats = defaultdict(lambda: {
            "total": 0, "correct": 0, "ratios": [], "ves_ratios": []
        })

        for t in all_tasks:
            diff_obj = getattr(t, 'difficulty', 'unknown')
            d = (diff_obj.value if hasattr(diff_obj, 'value') else str(diff_obj)).lower()
            stats[d]["total"] += 1
            stats["overall"]["total"] += 1

        detail_map = {x['task_id']: x for x in details}
        for t in all_tasks:
            tid = t.task_id
            diff_obj = getattr(t, 'difficulty', 'unknown')
            d = (diff_obj.value if hasattr(diff_obj, 'value') else str(diff_obj)).lower()
            
            if tid in detail_map:
                res = detail_map[tid]
                if res['is_correct']:
                    stats[d]["correct"] += 1
                    stats["overall"]["correct"] += 1
                    
                    stats[d]["ratios"].append(res['ratio'])
                    stats["overall"]["ratios"].append(res['ratio'])

                    stats[d]["ves_ratios"].append(res['ves_ratio'])
                    stats["overall"]["ves_ratios"].append(res['ves_ratio'])
        
        return stats

    def calc_EX(self) -> List[Dict]:
        print("\n=== Calculating EX ===")
        tasks = load_tasks(self.task_path)
        completions = self._load_completions()
        
        if not tasks or not completions:
            print("[Err] Missing tasks or completions.")
            return []

        task_map = {t.task_id: t for t in tasks}
        results_list = []
        stats = defaultdict(lambda: {"total": 0, "correct": 0})
        for t in tasks:
            stats[t.difficulty.value]["total"] += 1
            stats["overall"]["total"] += 1

        try:
            conn = pymysql.connect(**DB_CONFIG)
            cursor = conn.cursor()
        except Exception as e:
            print(f"[Err] DB Connection failed: {e}")
            return []

        try:
            for task_id, pred_sql in tqdm(completions):
                if task_id not in task_map: continue
                task = task_map[task_id]
                
                db_name = task.db_name
                opt_rows = task.optimized_scanned_rows
                gold_sql = task.optimized_sql
                diff_str = task.difficulty.value

                record = {
                    "task_id": task_id,
                    "difficulty": diff_str,
                    "is_correct": False,
                    "optimized_rows": opt_rows,
                    "actual_rows": -1,
                    "ratio": 0.0,
                    "ves_ratio": 0.0
                }

                try:
                    cursor.execute(f"USE {db_name}")

                    is_correct = is_identical(pred_sql, gold_sql, cursor)    
                    record["is_correct"] = is_correct

                    if is_correct:
                        stats[diff_str]["correct"] += 1
                        stats["overall"]["correct"] += 1

                        act_rows = get_tot_scanned_rows(pred_sql, cursor, debug=False)
                        record["actual_rows"] = act_rows
                        record["ratio"] = opt_rows / act_rows

                        try:
                            record["ves_ratio"] = get_exec_time(cursor, gold_sql) / get_exec_time(cursor, pred_sql)
                        except Exception: pass

                except Exception as e: pass
                
                results_list.append(record)
        finally:
            cursor.close()
            conn.close()

        with open(self.save_path, 'w', encoding='utf-8') as f:
            json.dump(results_list, f, indent=4, ensure_ascii=False)
        
        print("\n[Result] Execution Accuracy (EX) Summary")
        print("-" * 50)
        print(f"| {'Difficulty':<10} | {'Total':<8} | {'Corr':<8} | {'EX (%)':<8} |")
        print("-" * 50)
        
        for diff in ['overall', 'simple', 'medium', 'hard']:
            s = stats[diff]
            total = s['total']
            corr = s['correct']
            
            if total > 0:
                ex = (corr / total) * 100
            else:
                ex = 0.0
                
            print(f"| {diff.capitalize():<10} | {total:<8} | {corr:<8} | {ex:<8.2f} |")
        print("-" * 50)
        return results_list

    def calc_CR(self):
        print("\n=== Calculating CR (Cost Reduction) ===")
        details = self._ensure_ex_results()
        stats = self._aggregate_data(details)
        
        print("-" * 55)
        print(f"| {'Difficulty':<10} | {'CR':<10} |")
        print("-" * 55)
        
        for diff in ['overall', 'simple', 'medium', 'hard']:
            s = stats[diff]
            corr = s['correct']
            if corr > 0:
                cr = sum(s['ratios']) / corr
            else:
                cr = 0.0
                
            print(f"| {diff.capitalize():<10} | {cr:<10.2f} |")
        print("-" * 55)

    def calc_VES(self):
        print("\n=== Calculating VES (Valid Efficiency Score) ===")
        details = self._ensure_ex_results()
        stats = self._aggregate_data(details)
        
        print("-" * 40)
        print(f"| {'Difficulty':<10} | {'Mean VES':<10} |")
        print("-" * 40)
        
        for diff in ['overall', 'simple', 'medium', 'hard']:
            s = stats[diff]
            corr = s['correct']
            
            if corr > 0:
                sum_sqrt = sum(math.sqrt(r) for r in s['ves_ratios'])
                ves = sum_sqrt / corr
            else:
                ves = 0.0
                
            print(f"| {diff.capitalize():<10} | {ves:<10.4f} |")
        print("-" * 40)


    def calc_AR(self, ks: List[float] = [0.8, 1.0]):
        print(f"\n=== Calculating AR@k (Thresholds: {ks}) ===")
        details = self._ensure_ex_results()
        stats = self._aggregate_data(details)
        
        k_headers = " | ".join([f"@{k:<3}" for k in ks])
        width = 14 + len(ks) * 8
        
        print("-" * width)
        print(f"| {'Difficulty':<10} | {k_headers} |")
        print("-" * width)
        
        for diff in ['overall', 'simple', 'medium', 'hard']:
            s = stats[diff]
            ratios = s['ratios']
            denom = len(ratios)
            
            row = f"| {diff.capitalize():<10} |"
            for k in ks:
                if denom > 0:
                    count = sum(1 for r in ratios if r >= k)
                    pct = (count / denom) * 100
                else:
                    pct = 0.0
                row += f" {pct:<5.1f} |"
            print(row)
        print("-" * width)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Efficiency-Oriented Text-to-SQL Evaluator")
    parser.add_argument('--ex', action='store_true', help='Execute SQLs and calculate Execution Accuracy (EX). Forces re-execution.')
    parser.add_argument('--cr', action='store_true', help='Calculate Cost Reduction (CR) statistics.')
    parser.add_argument('--ves', action='store_true', help='Calculate Valid Efficiency Score (VES).')
    parser.add_argument('--ar', action='store_true', help='Calculate Acceleration Ratio @ k (AR@k).')
    args = parser.parse_args()
    run_all = not (args.ex or args.cr or args.ves or args.ar)

    evaluator = Evaluator()
    if args.ex or run_all:  evaluator.calc_EX()
    if args.cr or run_all:  evaluator.calc_CR()
    if args.ves or run_all: evaluator.calc_VES()
    if args.ar or run_all:  evaluator.calc_AR()
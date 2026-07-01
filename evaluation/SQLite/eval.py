from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

try:
    from .utils import (
        DEFAULT_AR_KS,
        DEFAULT_EXECUTION_REPEAT_COUNT,
        DEFAULT_SQL_TIMEOUT_SECONDS,
        DEFAULT_TASK_TIMEOUT_SECONDS,
        SQLMetricTask,
        calculate_task_metrics,
        coerce_metric_task,
    )
except ImportError:
    from utils import (  # type: ignore[no-redef]
        DEFAULT_AR_KS,
        DEFAULT_EXECUTION_REPEAT_COUNT,
        DEFAULT_SQL_TIMEOUT_SECONDS,
        DEFAULT_TASK_TIMEOUT_SECONDS,
        SQLMetricTask,
        calculate_task_metrics,
        coerce_metric_task,
    )

# 数据库配置
_EVAL_DIR = Path(__file__).resolve().parent
_EESQL_BASE = Path("")
_DEFAULT_INPUT = _EVAL_DIR.parent / 'tasks.jsonl'

_SKIP_TASK_IDS = {
    7, 9, 10, 22, 31, 39, 40, 41, 47, 54, 56, 58, 67, 69, 88, 97, 99, 105,
    106, 108, 127, 158,
}
_SKIP_TASK_IDS |= {str(s) for s in _SKIP_TASK_IDS}


class Evaluator:
    def __init__(
        self,
        input_path: str | Path = _DEFAULT_INPUT,
        output_dir: str | Path | None = None,
        *,
        sql_timeout_seconds: float = DEFAULT_SQL_TIMEOUT_SECONDS,
        repeat_count: int = DEFAULT_EXECUTION_REPEAT_COUNT,
        task_timeout_seconds: float = DEFAULT_TASK_TIMEOUT_SECONDS,
    ) -> None:
        self.input_path = Path(input_path)
        if output_dir is None:
            output_dir = _EVAL_DIR / "results"
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.save_path = self.output_dir / "EX.json"

        self.sql_timeout_seconds = sql_timeout_seconds
        self.repeat_count = repeat_count
        self.task_timeout_seconds = task_timeout_seconds


    def calc_EX(self, limit: int | None = None) -> list[dict[str, Any]]:
        """Execute SQL, compare results, and save per-task details to EX.json.

        Returns the list of per-task detail records.
        """
        print("\n=== Calculating EX (Execution Accuracy) ===\n")
        tasks = self._load_tasks(limit)
        if not tasks:
            print("[Err] No tasks found.")
            return []

        total = len(tasks)
        details: list[dict[str, Any]] = []

        for index, task in enumerate(tasks, start=1):
            detail = self._calculate_one_task(task)
            details.append(detail)

            ex_ok = detail.get("is_correct", False)
            ves = detail.get("ves_score", 0.0)
            cr = detail.get("cr_score", 0.0)
            ratio = detail.get("scan_row_ratio")
            print(
                f"[{index:>{len(str(total))}}/{total}] "
                f"qid={detail['task_id']} "
                f"db={detail.get('db_id', '?')} "
                f"EX={int(ex_ok)} "
                f"VES={ves:.4f} "
                f"CR={cr:.4f} "
                f"ratio={ratio}",
                file=sys.stderr,
                flush=True,
            )

        # Save cache
        with open(self.save_path, "w", encoding="utf-8") as f:
            json.dump(details, f, indent=2, ensure_ascii=False)

        self._print_ex_summary(details, total)
        return details

    def calc_CR(self) -> dict[str, Any]:
        """Calculate Cost Reduction from cached EX results."""
        print("\n=== Calculating CR (Cost Reduction) ===\n")
        details = self._ensure_ex_results()
        stats = self._aggregate_data(details)

        print("-" * 55)
        print(f"| {'Difficulty':<10} | {'Valid':<8} | {'CR':<10} |")
        print("-" * 55)

        result: dict[str, dict[str, Any]] = {}
        for diff in self._difficulty_order(stats):
            s = stats[diff]
            ratios = s["ratios"]
            if ratios:
                cr = sum(math.sqrt(r) for r in ratios) / len(ratios)
            else:
                cr = 0.0
            result[diff] = {"valid": len(ratios), "cr": round(cr, 6)}
            print(f"| {diff.capitalize():<10} | {len(ratios):<8} | {cr:<10.4f} |")
        print("-" * 55)
        return result

    def calc_VES(self) -> dict[str, Any]:
        """Calculate Valid Efficiency Score from cached EX results."""
        print("\n=== Calculating VES (Valid Efficiency Score) ===\n")
        details = self._ensure_ex_results()
        stats = self._aggregate_data(details)

        print("-" * 55)
        print(f"| {'Difficulty':<10} | {'Valid':<8} | {'VES':<10} |")
        print("-" * 55)

        result: dict[str, dict[str, Any]] = {}
        for diff in self._difficulty_order(stats):
            s = stats[diff]
            ves_ratios = s["ves_ratios"]
            if ves_ratios:
                ves = sum(math.sqrt(r) for r in ves_ratios) / len(ves_ratios)
            else:
                ves = 0.0
            result[diff] = {"valid": len(ves_ratios), "ves": round(ves, 6)}
            print(f"| {diff.capitalize():<10} | {len(ves_ratios):<8} | {ves:<10.4f} |")
        print("-" * 55)
        return result

    def calc_AR(self, ks: list[float] | None = None) -> dict[str, Any]:
        """Calculate Acceptable Ratio @ k from cached EX results."""
        if ks is None:
            ks = list(DEFAULT_AR_KS)
        print(f"\n=== Calculating AR@k (Thresholds: {ks}) ===\n")
        details = self._ensure_ex_results()
        stats = self._aggregate_data(details)

        k_headers = " | ".join([f"@{k:<3}" for k in ks])
        width = 14 + len(ks) * 8
        print("-" * width)
        print(f"| {'Difficulty':<10} | {k_headers} |")
        print("-" * width)

        result: dict[str, dict[str, Any]] = {}
        for diff in self._difficulty_order(stats):
            s = stats[diff]
            ratios = s["ratios"]
            denom = len(ratios)

            row = f"| {diff.capitalize():<10} |"
            diff_result: dict[str, float] = {}
            for k in ks:
                if denom > 0:
                    count = sum(1 for r in ratios if r >= k)
                    pct = (count / denom) * 100
                else:
                    pct = 0.0
                diff_result[f"AR@{k}"] = round(pct, 1)
                row += f" {pct:<5.1f} |"
            result[diff] = diff_result
            print(row)
        print("-" * width)
        return result

    def _load_tasks(self, limit: int | None = None) -> list[SQLMetricTask]:
        """Load and coerce tasks from the input file."""
        with open(self.input_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        if isinstance(payload, dict):
            raw_tasks = payload.get("res", [])
        else:
            raw_tasks = payload

        # Filter skipped
        raw_tasks = [
            t for t in raw_tasks
            if t.get("id", t.get("task_id")) not in _SKIP_TASK_IDS
        ]
        if limit is not None:
            raw_tasks = raw_tasks[:limit]

        tasks = []
        for raw in raw_tasks:
            try:
                tasks.append(coerce_metric_task(raw))
            except ValueError as exc:
                print(f"[Warn] Skipping task: {exc}", file=sys.stderr)
        return tasks

    def _calculate_one_task(self, task: SQLMetricTask) -> dict[str, Any]:
        """Compute all metrics for one task and return a flat detail dict."""
        try:
            result = calculate_task_metrics(
                task,
                include_cr=True,
                require_equivalent_for_cr=True,
                sql_timeout_seconds=self.sql_timeout_seconds,
                repeat_count=self.repeat_count,
                db_path_resolver=self._resolve_bird_dev_db_path,
            )
        except Exception as exc:
            return {
                "task_id": task.task_id,
                "question_id": task.question_id,
                "db_id": task.db_id,
                "is_correct": False,
                "error": str(exc),
                "strict_ex": False,
                "based_ex": False,
                "ves_score": 0.0,
                "ves_valid": False,
                "cr_score": 0.0,
                "cr_valid": False,
                "scan_row_ratio": None,
                "gold_total_scanned_rows": None,
                "generated_total_scanned_rows": None,
                "speed_ratio": None,
            }

        task_result = result.get("task_result", {})
        difficulty = self._extract_difficulty(task)

        return {
            "task_id": task.task_id,
            "question_id": task.question_id,
            "db_id": task.db_id,
            "difficulty": difficulty,
            "is_correct": bool(task_result.get("strict_ex", task_result.get("ex"))),
            "based_correct": bool(task_result.get("based_ex", task_result.get("ex"))),
            "strict_ex": bool(task_result.get("strict_ex", task_result.get("ex"))),
            "based_ex": bool(task_result.get("based_ex", task_result.get("ex"))),
            "ves_score": task_result.get("ves_score", 0.0),
            "ves_valid": task_result.get("ves_valid", False),
            "cr_score": task_result.get("cr_score", task_result.get("strict_cr_score", 0.0)),
            "cr_valid": task_result.get("cr_valid", task_result.get("strict_cr_valid", False)),
            "scan_row_ratio": task_result.get("scan_row_ratio"),
            "speed_ratio": task_result.get("speed_ratio"),
            "gold_total_scanned_rows": task_result.get("gold_total_scanned_rows"),
            "generated_total_scanned_rows": task_result.get("generated_total_scanned_rows"),
            "gold_latency_ms": task_result.get("gold_latency_ms"),
            "generated_latency_ms": task_result.get("generated_latency_ms"),
            "error": task_result.get("error"),
        }

    def _ensure_ex_results(self) -> list[dict[str, Any]]:
        """Load cached EX results, or trigger calculation if missing."""
        if self.save_path.exists():
            with open(self.save_path, "r", encoding="utf-8") as f:
                return json.load(f)
        print("[Info] EX results not found. Triggering automatic calculation...")
        return self.calc_EX()

    def _aggregate_data(self, details: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        """Aggregate per-task details into difficulty-grouped statistics."""
        stats: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"total": 0, "correct": 0, "ratios": [], "ves_ratios": []}
        )

        for d in details:
            diff = d.get("difficulty", "unknown")
            stats[diff]["total"] += 1
            stats["overall"]["total"] += 1

            if d.get("is_correct"):
                stats[diff]["correct"] += 1
                stats["overall"]["correct"] += 1

                if d.get("scan_row_ratio") is not None:
                    stats[diff]["ratios"].append(d["scan_row_ratio"])
                    stats["overall"]["ratios"].append(d["scan_row_ratio"])

                if d.get("speed_ratio") is not None:
                    stats[diff]["ves_ratios"].append(d["speed_ratio"])
                    stats["overall"]["ves_ratios"].append(d["speed_ratio"])

        return stats

    @staticmethod
    def _difficulty_order(stats: dict[str, Any]) -> list[str]:
        """Return difficulty keys in display order: overall first, then known levels."""
        order = ["overall"]
        for level in ["simple", "medium", "hard"]:
            if level in stats:
                order.append(level)
        # Append any unexpected keys
        for key in stats:
            if key not in order:
                order.append(key)
        return order

    @staticmethod
    def _extract_difficulty(task: SQLMetricTask) -> str:
        """Extract difficulty label from task metadata."""
        meta = task.metadata or {}
        diff = meta.get("difficulty", "unknown")
        return str(diff).lower()

    @staticmethod
    def _resolve_bird_dev_db_path(db_id: str) -> Path:
        return _EESQL_BASE / db_id / f"{db_id}.sqlite"

    @staticmethod
    def _print_ex_summary(details: list[dict[str, Any]], total: int) -> None:
        """Print the EX summary table."""
        stats: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "correct": 0})
        for d in details:
            diff = d.get("difficulty", "unknown")
            stats[diff]["total"] += 1
            stats["overall"]["total"] += 1
            if d.get("is_correct"):
                stats[diff]["correct"] += 1
                stats["overall"]["correct"] += 1

        print("\n[Result] Execution Accuracy (EX) Summary")
        print("-" * 50)
        print(f"| {'Difficulty':<10} | {'Total':<8} | {'Corr':<8} | {'EX (%)':<8} |")
        print("-" * 50)
        for diff in Evaluator._difficulty_order(stats):
            s = stats[diff]
            t = s["total"]
            c = s["correct"]
            ex = (c / t * 100) if t > 0 else 0.0
            print(f"| {diff.capitalize():<10} | {t:<8} | {c:<8} | {ex:<8.2f} |")
        print("-" * 50)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Efficiency-Oriented Text-to-SQL Evaluator"
    )
    parser.add_argument(
        "--input", type=Path, default=_DEFAULT_INPUT,
        help="Path to input JSON/JSONL file.",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=None,
        help="Directory for cached EX.json and other outputs.",
    )
    parser.add_argument(
        "--ex", action="store_true",
        help="Execute SQLs and calculate Execution Accuracy (EX). Forces re-execution.",
    )
    parser.add_argument(
        "--cr", action="store_true",
        help="Calculate Cost Reduction (CR) from cached results.",
    )
    parser.add_argument(
        "--ves", action="store_true",
        help="Calculate Valid Efficiency Score (VES) from cached results.",
    )
    parser.add_argument(
        "--ar", action="store_true",
        help="Calculate Acceleration Ratio @ k (AR@k) from cached results.",
    )
    parser.add_argument(
        "--ar-k", type=float, nargs="+", default=list(DEFAULT_AR_KS),
        help="Thresholds for AR@k. Default: 0.8 1.0.",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Limit evaluation to the first N tasks.",
    )
    parser.add_argument(
        "--sql-timeout-seconds", type=float, default=DEFAULT_SQL_TIMEOUT_SECONDS,
        help="Wall-time cap for one SQL execution.",
    )
    parser.add_argument(
        "--repeat-count", type=int, default=DEFAULT_EXECUTION_REPEAT_COUNT,
        help="Executions per SQL for latency averaging.",
    )
    parser.add_argument(
        "--task-timeout-seconds", type=float, default=DEFAULT_TASK_TIMEOUT_SECONDS,
        help="Wall-time cap for one task. 0 disables.",
    )
    parser.add_argument(
        "--no-cache", action="store_true",
        help="Force re-computation even if EX.json exists.",
    )

    args = parser.parse_args()
    run_all = not (args.ex or args.cr or args.ves or args.ar)

    evaluator = Evaluator(
        input_path=args.input,
        output_dir=args.output_dir,
        sql_timeout_seconds=args.sql_timeout_seconds,
        repeat_count=args.repeat_count,
        task_timeout_seconds=args.task_timeout_seconds,
    )

    if args.no_cache and evaluator.save_path.exists():
        evaluator.save_path.unlink()

    if args.ex or run_all:
        evaluator.calc_EX(limit=args.limit)
    if args.cr or run_all:
        evaluator.calc_CR()
    if args.ves or run_all:
        evaluator.calc_VES()
    if args.ar or run_all:
        evaluator.calc_AR(ks=args.ar_k)


if __name__ == "__main__":
    main()

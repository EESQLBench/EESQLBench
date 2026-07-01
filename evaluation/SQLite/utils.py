from __future__ import annotations

import json
import math
import re
import sqlite3
import subprocess
import time
from collections import Counter
from collections.abc import Callable
from collections.abc import Iterable
from dataclasses import asdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import sqlglot
    import sqlglot.expressions as exp
except Exception:  # pragma: no cover - fallback is exercised only without sqlglot.
    sqlglot = None
    exp = None

# ── Scan row counting ───────────────────────────────────────────────────
# Probe paths and timeout for real NVISIT measurement.

_PROBE_DIR = Path(__file__).resolve().parent / "tools"
PROBE_PATH = _PROBE_DIR / "scanstatus_probe"
_PROBE_TIMEOUT_SECONDS = 900


def count_scanned_rows(
    sql: str,
    db_path: str | Path,
    *,
    probe_timeout_seconds: float = _PROBE_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    db_path = Path(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(f"EXPLAIN QUERY PLAN {sql}").fetchall()
    except sqlite3.OperationalError as exc:
        error_msg = str(exc).lower()
        if "syntax" in error_msg or "near" in error_msg:
            return {
                "total_scanned_rows": -1.0,
                "scan_details": [],
                "source": f"sqlite_syntax_error: {exc}",
                "kind": "invalid",
            }
    except Exception:
        pass
    finally:
        conn.close()

    result = _scan_rows_via_probe(sql, db_path, probe_timeout_seconds)
    if result["total_scanned_rows"] is not None:
        return result

    return _estimate_scan_rows(sql, db_path)


def _scan_rows_via_probe(
    sql: str,
    db_path: Path,
    timeout_seconds: float,
) -> dict[str, Any]:
    """Execute SQL via the scanstatus probe and return real NVISIT counts."""
    if not PROBE_PATH.is_file():
        return {
            "total_scanned_rows": None,
            "scan_details": [],
            "source": "sqlite_stmt_scanstatus_v2_nvisit: probe binary not found",
            "kind": "unknown",
        }
    try:
        proc = subprocess.run(
            [str(PROBE_PATH), str(db_path), sql],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        return {
            "total_scanned_rows": None,
            "scan_details": [],
            "source": f"sqlite_stmt_scanstatus_v2_nvisit: subprocess failed: {exc}",
            "kind": "unknown",
        }

    try:
        payload = json.loads(proc.stdout.strip() or "{}")
    except json.JSONDecodeError:
        return {
            "total_scanned_rows": None,
            "scan_details": [],
            "source": (
                "sqlite_stmt_scanstatus_v2_nvisit: invalid JSON from probe: "
                + (proc.stdout[:200] if proc.stdout else "(empty)")
            ),
            "kind": "unknown",
        }

    if proc.returncode != 0 or payload.get("total_scanned_rows") is None:
        return {
            "total_scanned_rows": None,
            "scan_details": [],
            "source": (
                "sqlite_stmt_scanstatus_v2_nvisit: probe error: "
                f"{payload.get('error', 'unknown')}"
            ),
            "kind": "unknown",
        }

    return {
        "total_scanned_rows": float(payload["total_scanned_rows"]),
        "scan_details": [],
        "source": "sqlite_stmt_scanstatus_v2_nvisit",
        "kind": "real",
    }


def _estimate_scan_rows(
    sql: str,
    db_path: Path,
) -> dict[str, Any]:
    """Estimate scanned rows by summing table row counts from EXPLAIN QUERY PLAN."""
    conn = sqlite3.connect(str(db_path))
    try:
        raw_plan = conn.execute(f"EXPLAIN QUERY PLAN {sql}").fetchall()
        alias_to_table = _sql_alias_to_table(sql)
        total_scanned_rows = 0
        scan_details: list[dict[str, Any]] = []
        table_row_counts: dict[str, int] = {}
        for row in raw_plan:
            detail = str(row[3])
            table = _table_from_plan_detail(detail)
            if not table:
                continue
            real_table = alias_to_table.get(table, table)
            if real_table not in table_row_counts:
                table_row_counts[real_table] = _table_row_count(conn, real_table)
            row_count = table_row_counts[real_table]
            total_scanned_rows += row_count
            scan_details.append(
                {
                    "plan_node_id": row[0],
                    "detail": detail,
                    "table": real_table,
                    "estimated_scanned_rows": row_count,
                }
            )
    except Exception as exc:
        return {
            "total_scanned_rows": None,
            "scan_details": [],
            "source": f"sqlite_explain_query_plan_failed: {exc}",
            "kind": "unknown",
        }
    finally:
        conn.close()

    return {
        "total_scanned_rows": float(total_scanned_rows),
        "scan_details": scan_details,
        "source": "sqlite_explain_query_plan_table_row_counts",
        "kind": "estimated",
    }


def _sql_alias_to_table(sql: str) -> dict[str, str]:
    """Extract table alias → real table name mapping from FROM/JOIN clauses."""
    result: dict[str, str] = {}
    _IDENT = r"(?:`[^`]*`|\[[^\]]*\]|\"[^\"]*\"|[\w.-]+)"
    pattern = re.compile(
        rf"\b(?:FROM|JOIN)\s+({_IDENT})"
        rf"(?:\s+(?:AS\s+)?({_IDENT}))?",
        re.IGNORECASE,
    )
    for match in pattern.finditer(sql):
        table = match.group(1).strip().strip("`\"[]")
        alias = match.group(2)
        result[table] = table
        if alias:
            alias = alias.strip().strip("`\"[]")
            if alias.upper() not in {"WHERE", "ON", "INNER", "LEFT", "RIGHT", "JOIN"}:
                result[alias] = table
    return result


def _table_from_plan_detail(detail: str) -> str | None:
    """Extract table name from an EXPLAIN QUERY PLAN detail string."""
    match = re.search(r"\b(?:SCAN|SEARCH)\s+([`\"\[]?[\w\s().-]+[`\"\]]?)", detail)
    if not match:
        return None
    name = match.group(1).strip().strip("`\"[]")
    upper_name = name.upper()
    if upper_name in {"CONSTANT ROW", "SUBQUERY"} or upper_name.startswith("SUBQUERY"):
        return None
    return name.split()[0]


def _table_row_count(conn: sqlite3.Connection, table_name: str) -> int:
    """Return the total row count for a table."""
    escaped = table_name.replace('"', '""')
    try:
        row = conn.execute(f'SELECT COUNT(*) FROM "{escaped}"').fetchone()
    except Exception:
        return 0
    return int(row[0]) if row and row[0] is not None else 0


# ── Constants ───────────────────────────────────────────────────────────
DEFAULT_AR_KS = (0.8, 1.0)
# DEFAULT_SQL_TIMEOUT_SECONDS = 900.0
DEFAULT_SQL_TIMEOUT_SECONDS = 900.0
DEFAULT_EXECUTION_REPEAT_COUNT = 3
DEFAULT_TASK_TIMEOUT_SECONDS = (
    DEFAULT_SQL_TIMEOUT_SECONDS * DEFAULT_EXECUTION_REPEAT_COUNT * 2
    + DEFAULT_SQL_TIMEOUT_SECONDS
)
DbPathResolver = Callable[[str], str | Path]


@dataclass(frozen=True)
class SQLMetricTask:
    """Input required to compute SQL-level metrics for one task."""

    task_id: str
    db_id: str
    gold_sql: str
    generated_sql: str
    question_id: int | None = None
    db_path: str | Path | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class SQLExecution:
    rows: list[tuple] | None
    latency_ms: float
    latency_samples_ms: list[float]
    execution_count: int
    timed_out: bool
    error: str | None
    slow_sql_events: list[dict[str, Any]]


@dataclass(frozen=True)
class ResultComparison:
    equivalent: bool
    gold_sql: str
    generated_sql: str
    gold_row_count: int | None
    generated_row_count: int | None
    gold_has_order_by: bool
    gold_has_distinct: bool
    comparison_mode: str
    diff_summary: str | None
    gold_error: str | None
    generated_error: str | None


def calculate_task_ex(
    task: SQLMetricTask | dict[str, Any],
    *,
    db_path_resolver: DbPathResolver | None = None,
    sql_timeout_seconds: float = DEFAULT_SQL_TIMEOUT_SECONDS,
    repeat_count: int = 1,
) -> dict[str, Any]:
    """Calculate execution accuracy for one task."""
    metric_task = coerce_metric_task(task)
    gold_exec = execute_sql_for_task(
        metric_task,
        role="gold",
        sql=metric_task.gold_sql,
        timeout_seconds=sql_timeout_seconds,
        repeat_count=repeat_count,
        db_path_resolver=db_path_resolver,
    )
    generated_exec = execute_sql_for_task(
        metric_task,
        role="generated",
        sql=metric_task.generated_sql,
        timeout_seconds=sql_timeout_seconds,
        repeat_count=repeat_count,
        db_path_resolver=db_path_resolver,
    )
    comparison = compare_executed_sql(metric_task, gold_exec, generated_exec)
    based_comparison = compare_executed_sql_based(metric_task, gold_exec, generated_exec)
    return {
        "task_id": metric_task.task_id,
        "task_result": {
            "metric": "EX",
            "ex": bool(comparison.equivalent),
            "strict_ex": bool(comparison.equivalent),
            "based_ex": bool(based_comparison.equivalent),
            "comparison": asdict(comparison),
            "based_comparison": asdict(based_comparison),
            "error": comparison.diff_summary,
        },
    }


def calculate_task_ves(
    task: SQLMetricTask | dict[str, Any],
    *,
    db_path_resolver: DbPathResolver | None = None,
    sql_timeout_seconds: float = DEFAULT_SQL_TIMEOUT_SECONDS,
    repeat_count: int = DEFAULT_EXECUTION_REPEAT_COUNT,
) -> dict[str, Any]:
    """Calculate BIRD-style Valid Efficiency Score for one task."""
    metric_task = coerce_metric_task(task)
    gold_exec = execute_sql_for_task(
        metric_task,
        role="gold",
        sql=metric_task.gold_sql,
        timeout_seconds=sql_timeout_seconds,
        repeat_count=repeat_count,
        db_path_resolver=db_path_resolver,
    )
    generated_exec = execute_sql_for_task(
        metric_task,
        role="generated",
        sql=metric_task.generated_sql,
        timeout_seconds=sql_timeout_seconds,
        repeat_count=repeat_count,
        db_path_resolver=db_path_resolver,
    )
    comparison = compare_executed_sql(metric_task, gold_exec, generated_exec)
    ves = calculate_ves_from_executions(comparison, gold_exec, generated_exec)
    return {
        "task_id": metric_task.task_id,
        "task_result": {
            "metric": "VES",
            **ves,
        },
    }


def calculate_task_cr(
    task: SQLMetricTask | dict[str, Any],
    *,
    require_equivalent: bool = True,
    db_path_resolver: DbPathResolver | None = None,
    sql_timeout_seconds: float = DEFAULT_SQL_TIMEOUT_SECONDS,
    repeat_count: int = 1,
) -> dict[str, Any]:
    """Calculate scan-row Cost Reachability for one task."""
    metric_task = coerce_metric_task(task)
    gold_exec = execute_sql_for_task(
        metric_task,
        role="gold",
        sql=metric_task.gold_sql,
        timeout_seconds=sql_timeout_seconds,
        repeat_count=repeat_count,
        db_path_resolver=db_path_resolver,
    )
    generated_exec = execute_sql_for_task(
        metric_task,
        role="generated",
        sql=metric_task.generated_sql,
        timeout_seconds=sql_timeout_seconds,
        repeat_count=repeat_count,
        db_path_resolver=db_path_resolver,
    )
    comparison = compare_executed_sql(metric_task, gold_exec, generated_exec)
    cr = calculate_cr_from_sql(
        metric_task,
        comparison=comparison,
        gold_exec=gold_exec,
        generated_exec=generated_exec,
        require_equivalent=require_equivalent,
        db_path_resolver=db_path_resolver,
    )
    return {
        "task_id": metric_task.task_id,
        "task_result": {
            "metric": "CR",
            **cr,
        },
    }


def calculate_task_metrics(
    task: SQLMetricTask | dict[str, Any],
    *,
    include_cr: bool = True,
    require_equivalent_for_cr: bool = True,
    db_path_resolver: DbPathResolver | None = None,
    sql_timeout_seconds: float = DEFAULT_SQL_TIMEOUT_SECONDS,
    repeat_count: int = DEFAULT_EXECUTION_REPEAT_COUNT,
) -> dict[str, Any]:
    """Calculate EX, VES, and optionally CR for one task."""
    metric_task = coerce_metric_task(task)
    gold_exec = execute_sql_for_task(
        metric_task,
        role="gold",
        sql=metric_task.gold_sql,
        timeout_seconds=sql_timeout_seconds,
        repeat_count=repeat_count,
        db_path_resolver=db_path_resolver,
    )
    generated_exec = execute_sql_for_task(
        metric_task,
        role="generated",
        sql=metric_task.generated_sql,
        timeout_seconds=sql_timeout_seconds,
        repeat_count=repeat_count,
        db_path_resolver=db_path_resolver,
    )
    comparison = compare_executed_sql(metric_task, gold_exec, generated_exec)
    based_comparison = compare_executed_sql_based(metric_task, gold_exec, generated_exec)
    ves = calculate_ves_from_executions(comparison, gold_exec, generated_exec)
    based_ves = calculate_ves_from_executions(based_comparison, gold_exec, generated_exec)

    strict_ex = bool(comparison.equivalent)
    based_ex = bool(based_comparison.equivalent)
    task_result: dict[str, Any] = {
        "status": "success",
        "question_id": metric_task.question_id,
        "db_id": metric_task.db_id,
        "ex": strict_ex,
        "strict_ex": strict_ex,
        "based_ex": based_ex,
        "ves_score": ves["ves_score"],
        "ves_valid": ves["ves_valid"],
        "based_ves_score": based_ves["ves_score"],
        "based_ves_valid": based_ves["ves_valid"],
        "gold_latency_ms": ves["gold_latency_ms"],
        "generated_latency_ms": ves["generated_latency_ms"],
        "gold_latency_samples_ms": ves["gold_latency_samples_ms"],
        "generated_latency_samples_ms": ves["generated_latency_samples_ms"],
        "gold_execution_count": ves["gold_execution_count"],
        "generated_execution_count": ves["generated_execution_count"],
        "speed_ratio": ves["speed_ratio"],
        "slow_sql_events": gold_exec.slow_sql_events + generated_exec.slow_sql_events,
        "metadata": metric_task.metadata or {},
        "metrics": {
            "EX": {
                "metric": "EX",
                "ex": strict_ex,
                "strict_ex": strict_ex,
                "comparison": asdict(comparison),
                "error": comparison.diff_summary,
            },
            "StrictEX": {
                "metric": "StrictEX",
                "ex": strict_ex,
                "comparison": asdict(comparison),
                "error": comparison.diff_summary,
            },
            "BasedEX": {
                "metric": "BasedEX",
                "ex": based_ex,
                "based_ex": based_ex,
                "comparison": asdict(based_comparison),
                "error": based_comparison.diff_summary,
            },
            "VES": {
                "metric": "VES",
                **ves,
            },
            "BasedVES": {
                "metric": "BasedVES",
                **based_ves,
            },
        },
    }

    if include_cr:
        db_path = resolve_task_db_path(metric_task, db_path_resolver=db_path_resolver)
        gold_scan = count_scanned_rows(metric_task.gold_sql, db_path)
        generated_scan = count_scanned_rows(metric_task.generated_sql, db_path)
        strict_cr = calculate_cr_from_sql(
            metric_task,
            comparison=comparison,
            gold_exec=gold_exec,
            generated_exec=generated_exec,
            require_equivalent=require_equivalent_for_cr,
            db_path_resolver=db_path_resolver,
            gold_scan=gold_scan,
            generated_scan=generated_scan,
        )
        based_cr = calculate_cr_from_sql(
            metric_task,
            comparison=based_comparison,
            gold_exec=gold_exec,
            generated_exec=generated_exec,
            require_equivalent=require_equivalent_for_cr,
            db_path_resolver=db_path_resolver,
            gold_scan=gold_scan,
            generated_scan=generated_scan,
        )
        task_result.update(
            {
                "cr_score": strict_cr["cr_score"],
                "cr_valid": strict_cr["cr_valid"],
                "scan_row_ratio": strict_cr["scan_row_ratio"],
                "strict_cr_score": strict_cr["cr_score"],
                "strict_cr_valid": strict_cr["cr_valid"],
                "strict_scan_row_ratio": strict_cr["scan_row_ratio"],
                "based_cr_score": based_cr["cr_score"],
                "based_cr_valid": based_cr["cr_valid"],
                "based_scan_row_ratio": based_cr["scan_row_ratio"],
                "gold_total_scanned_rows": strict_cr["gold_total_scanned_rows"],
                "generated_total_scanned_rows": strict_cr["generated_total_scanned_rows"],
            }
        )
        task_result["metrics"]["CR"] = {
            "metric": "CR",
            **strict_cr,
        }
        task_result["metrics"]["StrictCR"] = {
            "metric": "StrictCR",
            **strict_cr,
        }
        task_result["metrics"]["BasedCR"] = {
            "metric": "BasedCR",
            **based_cr,
        }

    return {
        "task_id": metric_task.task_id,
        "task_result": task_result,
    }


def calculate_ves_from_executions(
    comparison: ResultComparison,
    gold_exec: SQLExecution,
    generated_exec: SQLExecution,
) -> dict[str, Any]:
    """Calculate VES fields from already executed SQL results."""
    gold_latency_ms = gold_exec.latency_ms
    generated_latency_ms = generated_exec.latency_ms
    speed_ratio = positive_ratio(gold_latency_ms, generated_latency_ms)
    ves_valid = (
        comparison.equivalent
        and gold_exec.error is None
        and generated_exec.error is None
        and speed_ratio is not None
        and speed_ratio > 0
    )
    ves_score = round(math.sqrt(speed_ratio), 6) if ves_valid else 0.0
    return {
        "ves_valid": bool(ves_valid),
        "ves_score": ves_score,
        "gold_latency_ms": round(gold_latency_ms, 3),
        "generated_latency_ms": round(generated_latency_ms, 3),
        "gold_latency_samples_ms": [
            round(value, 3) for value in gold_exec.latency_samples_ms
        ],
        "generated_latency_samples_ms": [
            round(value, 3) for value in generated_exec.latency_samples_ms
        ],
        "gold_execution_count": gold_exec.execution_count,
        "generated_execution_count": generated_exec.execution_count,
        "speed_ratio": speed_ratio,
        "sqrt_speed_ratio": ves_score if ves_valid else None,
        "error": comparison.diff_summary if not comparison.equivalent else None,
    }


def calculate_cr_from_sql(
    task: SQLMetricTask,
    *,
    comparison: ResultComparison,
    gold_exec: SQLExecution,
    generated_exec: SQLExecution,
    require_equivalent: bool,
    db_path_resolver: DbPathResolver | None = None,
    gold_scan: dict[str, Any] | None = None,
    generated_scan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Calculate CR fields from SQL text and execution comparison."""
    if gold_scan is None:
        db_path = resolve_task_db_path(task, db_path_resolver=db_path_resolver)
        gold_scan = count_scanned_rows(task.gold_sql, db_path)
    if generated_scan is None:
        db_path = resolve_task_db_path(task, db_path_resolver=db_path_resolver)
        generated_scan = count_scanned_rows(task.generated_sql, db_path)
    scan_row_ratio = positive_ratio(
        gold_scan["total_scanned_rows"],
        generated_scan["total_scanned_rows"],
    )
    cr_valid = (
        scan_row_ratio is not None
        and (comparison.equivalent or not require_equivalent)
        and gold_exec.error is None
        and generated_exec.error is None
    )
    cr_score = round(math.sqrt(scan_row_ratio), 6) if cr_valid else 0.0
    return {
        "cr_valid": bool(cr_valid),
        "ex": bool(comparison.equivalent),
        "scan_row_ratio": scan_row_ratio,
        "cr_score": cr_score,
        "gold_total_scanned_rows": gold_scan["total_scanned_rows"],
        "generated_total_scanned_rows": generated_scan["total_scanned_rows"],
        "gold_scan_row_source": gold_scan["source"],
        "generated_scan_row_source": generated_scan["source"],
        "gold_scan_row_kind": gold_scan["kind"],
        "generated_scan_row_kind": generated_scan["kind"],
        "gold_error": gold_exec.error,
        "generated_error": generated_exec.error,
        "comparison": asdict(comparison),
        "error": first_error(
            comparison.diff_summary if not comparison.equivalent else None,
            gold_exec.error,
            generated_exec.error,
        ),
    }


def compare_executed_sql(
    task: SQLMetricTask,
    gold_exec: SQLExecution,
    generated_exec: SQLExecution,
) -> ResultComparison:
    """Compare already executed SQL results with Gold-structure-aware rules."""
    gold_has_order_by = has_order_by(task.gold_sql)
    gold_has_distinct = has_distinct(task.gold_sql)
    comparison_mode = comparison_mode_for_gold(task.gold_sql)

    if gold_exec.error or generated_exec.error:
        return ResultComparison(
            equivalent=False,
            gold_sql=task.gold_sql,
            generated_sql=task.generated_sql,
            gold_row_count=None,
            generated_row_count=None,
            gold_has_order_by=gold_has_order_by,
            gold_has_distinct=gold_has_distinct,
            comparison_mode=comparison_mode,
            diff_summary=(
                f"Gold error: {gold_exec.error or 'none'}. "
                f"Generated error: {generated_exec.error or 'none'}."
            ),
            gold_error=gold_exec.error,
            generated_error=generated_exec.error,
        )

    if gold_exec.timed_out or generated_exec.timed_out:
        return ResultComparison(
            equivalent=True,
            gold_sql=task.gold_sql,
            generated_sql=task.generated_sql,
            gold_row_count=None if gold_exec.rows is None else len(gold_exec.rows),
            generated_row_count=(
                None if generated_exec.rows is None else len(generated_exec.rows)
            ),
            gold_has_order_by=gold_has_order_by,
            gold_has_distinct=gold_has_distinct,
            comparison_mode=f"{comparison_mode}_assumed_after_timeout",
            diff_summary=None,
            gold_error=None,
            generated_error=None,
        )

    gold_rows = gold_exec.rows or []
    generated_rows = generated_exec.rows or []
    equivalent, diff_summary = compare_rows(
        gold_rows,
        generated_rows,
        comparison_mode=comparison_mode,
    )
    return ResultComparison(
        equivalent=equivalent,
        gold_sql=task.gold_sql,
        generated_sql=task.generated_sql,
        gold_row_count=len(gold_rows),
        generated_row_count=len(generated_rows),
        gold_has_order_by=gold_has_order_by,
        gold_has_distinct=gold_has_distinct,
        comparison_mode=comparison_mode,
        diff_summary=diff_summary,
        gold_error=None,
        generated_error=None,
    )


def compare_executed_sql_based(
    task: SQLMetricTask,
    gold_exec: SQLExecution,
    generated_exec: SQLExecution,
) -> ResultComparison:
    """Compare SQL results with DeepEye/BIRD-style set semantics.

    DeepEye's BIRD/Spider EX path checks ``set(pred_rows) == set(gold_rows)``.
    This ignores row order and duplicate multiplicities.
    """
    if gold_exec.error or generated_exec.error:
        return ResultComparison(
            equivalent=False,
            gold_sql=task.gold_sql,
            generated_sql=task.generated_sql,
            gold_row_count=None,
            generated_row_count=None,
            gold_has_order_by=has_order_by(task.gold_sql),
            gold_has_distinct=has_distinct(task.gold_sql),
            comparison_mode="deepeye_set",
            diff_summary=(
                f"Gold error: {gold_exec.error or 'none'}. "
                f"Generated error: {generated_exec.error or 'none'}."
            ),
            gold_error=gold_exec.error,
            generated_error=generated_exec.error,
        )

    if gold_exec.timed_out or generated_exec.timed_out:
        return ResultComparison(
            equivalent=False,
            gold_sql=task.gold_sql,
            generated_sql=task.generated_sql,
            gold_row_count=None if gold_exec.rows is None else len(gold_exec.rows),
            generated_row_count=(
                None if generated_exec.rows is None else len(generated_exec.rows)
            ),
            gold_has_order_by=has_order_by(task.gold_sql),
            gold_has_distinct=has_distinct(task.gold_sql),
            comparison_mode="deepeye_set_timeout",
            diff_summary="Gold or generated SQL timed out.",
            gold_error=None,
            generated_error=None,
        )

    gold_rows = gold_exec.rows or []
    generated_rows = generated_exec.rows or []
    equivalent = set(gold_rows) == set(generated_rows)
    return ResultComparison(
        equivalent=equivalent,
        gold_sql=task.gold_sql,
        generated_sql=task.generated_sql,
        gold_row_count=len(gold_rows),
        generated_row_count=len(generated_rows),
        gold_has_order_by=has_order_by(task.gold_sql),
        gold_has_distinct=has_distinct(task.gold_sql),
        comparison_mode="deepeye_set",
        diff_summary=None if equivalent else diff_set(gold_rows, generated_rows),
        gold_error=None,
        generated_error=None,
    )


def compare_rows(
    gold_rows: list[tuple],
    generated_rows: list[tuple],
    *,
    comparison_mode: str,
) -> tuple[bool, str | None]:
    """Compare two result sets according to a known comparison mode."""
    if comparison_mode == "list":
        if gold_rows == generated_rows:
            return True, None
        return False, diff_ordered(gold_rows, generated_rows)
    if comparison_mode == "set":
        if set(gold_rows) == set(generated_rows):
            return True, None
        return False, diff_set(gold_rows, generated_rows)
    if Counter(gold_rows) == Counter(generated_rows):
        return True, None
    return False, diff_multiset(gold_rows, generated_rows)


def execute_sql_for_task(
    task: SQLMetricTask,
    *,
    role: str,
    sql: str,
    timeout_seconds: float = DEFAULT_SQL_TIMEOUT_SECONDS,
    repeat_count: int = DEFAULT_EXECUTION_REPEAT_COUNT,
    db_path_resolver: DbPathResolver | None = None,
) -> SQLExecution:
    """Execute SQL with a wall-time cap and return rows plus average latency.

    The first execution supplies result rows for EX.  Successful executions are
    repeated up to ``repeat_count`` times for latency averaging.  If an execution
    times out or errors, no further repetitions are attempted.
    """
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be > 0")
    if repeat_count < 1:
        raise ValueError("repeat_count must be >= 1")

    db_path = resolve_task_db_path(task, db_path_resolver=db_path_resolver)
    rows: list[tuple] | None = None
    timed_out = False
    error = None
    slow_sql_events: list[dict[str, Any]] = []
    latency_samples_ms: list[float] = []

    for attempt in range(1, repeat_count + 1):
        execution = execute_sql_once(
            db_path=db_path,
            sql=sql,
            timeout_seconds=timeout_seconds,
        )
        latency_samples_ms.append(execution["latency_ms"])
        if attempt == 1:
            rows = execution["rows"]
        if execution["timed_out"]:
            timed_out = True
            slow_sql_events.append(
                {
                    "task_id": task.task_id,
                    "question_id": task.question_id,
                    "db_id": task.db_id,
                    "role": role,
                    "attempt": attempt,
                    "timeout_seconds": timeout_seconds,
                    "counted_latency_ms": round(timeout_seconds * 1000.0, 3),
                    "message": (
                        f"{role} SQL exceeded {timeout_seconds:g}s on attempt "
                        f"{attempt}; latency counted as {timeout_seconds:g}s "
                        "and no further repeats were run."
                    ),
                    "sql": sql,
                }
            )
            break
        if execution["error"] is not None:
            error = execution["error"]
            break

    latency_ms = mean(latency_samples_ms)
    return SQLExecution(
        rows=rows,
        latency_ms=latency_ms,
        latency_samples_ms=latency_samples_ms,
        execution_count=len(latency_samples_ms),
        timed_out=timed_out,
        error=error,
        slow_sql_events=slow_sql_events,
    )


def execute_sql_once(
    *,
    db_path: Path,
    sql: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    """Execute SQL once with a wall-time cap."""
    conn = sqlite3.connect(db_path)
    start = time.perf_counter()
    timed_out = False

    def progress_handler() -> int:
        return 1 if time.perf_counter() - start > timeout_seconds else 0

    conn.set_progress_handler(progress_handler, 10000)
    try:
        rows = conn.execute(sql).fetchall()
        latency_ms = (time.perf_counter() - start) * 1000.0
        error = None
    except sqlite3.OperationalError as exc:
        elapsed = time.perf_counter() - start
        if str(exc).lower() == "interrupted" and elapsed >= timeout_seconds:
            timed_out = True
            rows = None
            latency_ms = timeout_seconds * 1000.0
            error = None
        else:
            rows = None
            latency_ms = min(elapsed, timeout_seconds) * 1000.0
            error = str(exc)
    except Exception as exc:
        rows = None
        latency_ms = min(time.perf_counter() - start, timeout_seconds) * 1000.0
        error = str(exc)
    finally:
        conn.close()

    return {
        "rows": rows,
        "latency_ms": latency_ms,
        "timed_out": timed_out,
        "error": error,
    }


def aggregate_task_metrics(
    results: Iterable[dict[str, Any]],
    *,
    ar_ks: Iterable[float] = DEFAULT_AR_KS,
) -> dict[str, Any]:
    """Aggregate per-task metric outputs into dataset-level metrics."""
    rows = [result.get("task_result", {}) for result in results]
    completed = [row for row in rows if row.get("status") == "success"]
    strict_ex_count = sum(1 for row in rows if _strict_ex_value(row) is True)
    based_ex_count = sum(1 for row in rows if _based_ex_value(row) is True)
    ves_scores = [float_value(row.get("ves_score")) or 0.0 for row in rows]
    strict_cr_valid_rows = _cr_valid_rows(completed, prefix="strict")
    based_cr_valid_rows = _cr_valid_rows(completed, prefix="based")
    strict_cr_scores = _cr_scores(strict_cr_valid_rows, prefix="strict")
    based_cr_scores = _cr_scores(based_cr_valid_rows, prefix="based")
    strict_scan_row_ratios = _scan_row_ratios(strict_cr_valid_rows, prefix="strict")
    based_scan_row_ratios = _scan_row_ratios(based_cr_valid_rows, prefix="based")

    return {
        "total": len(rows),
        "completed": len(completed),
        "errors": len(rows) - len(completed),
        "ex_count": strict_ex_count,
        "ex_rate": safe_div(strict_ex_count, len(rows)),
        "ex_percent": round(safe_div(strict_ex_count, len(rows)) * 100, 4),
        "strict_ex_count": strict_ex_count,
        "strict_ex_rate": safe_div(strict_ex_count, len(rows)),
        "based_ex_count": based_ex_count,
        "based_ex_rate": safe_div(based_ex_count, len(rows)),
        "ves": round(safe_div(sum(ves_scores), len(ves_scores)), 6),
        "cr_valid_count": len(strict_cr_valid_rows),
        "cr": round(mean(strict_cr_scores), 6),
        "scan_row_ratio_avg": round(mean(strict_scan_row_ratios), 6),
        "strict_cr_valid_count": len(strict_cr_valid_rows),
        "strict_cr": round(mean(strict_cr_scores), 6),
        "strict_scan_row_ratio_avg": round(mean(strict_scan_row_ratios), 6),
        "based_cr_valid_count": len(based_cr_valid_rows),
        "based_cr": round(mean(based_cr_scores), 6),
        "based_scan_row_ratio_avg": round(mean(based_scan_row_ratios), 6),
        "ar": aggregate_ar_at_k(rows, ks=ar_ks, prefix="strict"),
        "strict_ar": aggregate_ar_at_k(rows, ks=ar_ks, prefix="strict"),
        "based_ar": aggregate_ar_at_k(rows, ks=ar_ks, prefix="based"),
    }


def aggregate_full_summary(
    results: Iterable[dict[str, Any]],
    *,
    actual_total: int | None = None,
    json_task_count: int | None = None,
    ar_ks: Iterable[float] = DEFAULT_AR_KS,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Aggregate metrics using benchmark-size denominators when provided."""
    rows = [result.get("task_result", {}) for result in results]
    denominator = actual_total if actual_total is not None else len(rows)
    input_count = json_task_count if json_task_count is not None else len(rows)
    missing_result_count = max(0, denominator - len(rows))
    errors = [row for row in rows if row.get("status") == "error"]
    strict_ex_count = sum(1 for row in rows if _strict_ex_value(row) is True)
    based_ex_count = sum(1 for row in rows if _based_ex_value(row) is True)
    ves_sum = sum(float_value(row.get("ves_score")) or 0.0 for row in rows)
    based_ves_sum = sum(float_value(row.get("based_ves_score")) or 0.0 for row in rows)
    strict_cr_valid_rows = _cr_valid_rows(rows, prefix="strict")
    based_cr_valid_rows = _cr_valid_rows(rows, prefix="based")
    strict_cr_scores = _cr_scores(strict_cr_valid_rows, prefix="strict")
    based_cr_scores = _cr_scores(based_cr_valid_rows, prefix="based")
    strict_scan_row_ratios = _scan_row_ratios(strict_cr_valid_rows, prefix="strict")
    based_scan_row_ratios = _scan_row_ratios(based_cr_valid_rows, prefix="based")

    summary: dict[str, Any] = {
        "actual_total": denominator,
        "json_task_count": input_count,
        "computed_task_count": len(rows),
        "missing_result_count": missing_result_count,
        "compute_error_count": len(errors),
        "EX": {
            "definition": (
                "strict EX=True tasks using gold-structure-aware comparison; "
                "missing benchmark tasks count as EX=False"
            ),
            "numerator": strict_ex_count,
            "denominator": denominator,
            "rate": safe_div(strict_ex_count, denominator),
            "percent": round(safe_div(strict_ex_count, denominator) * 100.0, 4),
            "measured_ex_count": strict_ex_count,
            "missing_false_count": missing_result_count,
        },
        "StrictEX": {
            "definition": (
                "gold ORDER BY -> ordered list; gold DISTINCT -> set; otherwise multiset"
            ),
            "numerator": strict_ex_count,
            "denominator": denominator,
            "rate": safe_div(strict_ex_count, denominator),
            "percent": round(safe_div(strict_ex_count, denominator) * 100.0, 4),
            "measured_ex_count": strict_ex_count,
            "missing_false_count": missing_result_count,
        },
        "BasedEX": {
            "definition": (
                "DeepEye/BIRD-style set(pred_rows) == set(gold_rows); "
                "order and duplicate multiplicities are ignored"
            ),
            "numerator": based_ex_count,
            "denominator": denominator,
            "rate": safe_div(based_ex_count, denominator),
            "percent": round(safe_div(based_ex_count, denominator) * 100.0, 4),
            "measured_ex_count": based_ex_count,
            "missing_false_count": missing_result_count,
        },
        "VES": {
            "sum": round(ves_sum, 6),
            "denominator": denominator,
            "score": round(safe_div(ves_sum, denominator), 6),
            "json_task_average": round(safe_div(ves_sum, input_count), 6),
        },
        "BasedVES": {
            "sum": round(based_ves_sum, 6),
            "denominator": denominator,
            "score": round(safe_div(based_ves_sum, denominator), 6),
            "json_task_average": round(safe_div(based_ves_sum, input_count), 6),
        },
        "CR": {
            "definition": "strict CR gated by StrictEX",
            "valid_count": len(strict_cr_valid_rows),
            "score": round(mean(strict_cr_scores), 6),
            "scan_row_ratio_avg": round(mean(strict_scan_row_ratios), 6),
        },
        "StrictCR": {
            "definition": "CR gated by StrictEX",
            "valid_count": len(strict_cr_valid_rows),
            "score": round(mean(strict_cr_scores), 6),
            "scan_row_ratio_avg": round(mean(strict_scan_row_ratios), 6),
        },
        "BasedCR": {
            "definition": "CR gated by BasedEX",
            "valid_count": len(based_cr_valid_rows),
            "score": round(mean(based_cr_scores), 6),
            "scan_row_ratio_avg": round(mean(based_scan_row_ratios), 6),
        },
        "AR": aggregate_ar_at_k(
            strict_cr_valid_rows,
            ks=ar_ks,
            denominator=denominator,
            prefix="strict",
        ),
        "StrictAR": aggregate_ar_at_k(
            strict_cr_valid_rows,
            ks=ar_ks,
            denominator=denominator,
            prefix="strict",
        ),
        "BasedAR": aggregate_ar_at_k(
            based_cr_valid_rows,
            ks=ar_ks,
            denominator=denominator,
            prefix="based",
        ),
    }
    if metadata:
        summary = {**metadata, **summary}
    return summary


def aggregate_ar_at_k(
    rows_or_results: Iterable[dict[str, Any]],
    *,
    ks: Iterable[float] = DEFAULT_AR_KS,
    denominator: int | None = None,
    prefix: str = "strict",
) -> dict[str, dict[str, float | int | str]]:
    """Aggregate Acceptable Ratio at each scan-row threshold k."""
    rows = [
        item.get("task_result", item)
        for item in rows_or_results
    ]
    valid_rows = _cr_valid_rows(rows, prefix=prefix)
    total = denominator if denominator is not None else len(rows)
    valid_total = len(valid_rows)
    output: dict[str, dict[str, float | int | str]] = {}
    for raw_k in ks:
        k = float(raw_k)
        accepted_count = sum(
            1
            for row in valid_rows
            if (_scan_row_ratio_value(row, prefix=prefix) or 0.0) >= k
        )
        output[f"AR@{k:g}"] = {
            "definition": f"accepted means {prefix}_cr_valid and scan_row_ratio >= k",
            "k": k,
            "accepted_count": accepted_count,
            "actual_total": total,
            "cr_valid_total": valid_total,
            "ar_at_k_all": safe_div(accepted_count, total),
            "ar_at_k_valid": safe_div(accepted_count, valid_total),
        }
    return output


def coerce_metric_task(task: SQLMetricTask | dict[str, Any]) -> SQLMetricTask:
    """Normalize common JSON task shapes into SQLMetricTask."""
    if isinstance(task, SQLMetricTask):
        return task
    if not isinstance(task, dict):
        raise TypeError(f"Unsupported metric task type: {type(task)!r}")

    task_id = task.get("task_id") or task.get("id")
    question_id = task.get("question_id")
    if task_id is None and question_id is not None:
        task_id = f"qid-{question_id}"
    if question_id is None:
        question_id = int_or_none(task_id)

    db_id = task.get("db_id") or task.get("db")
    gold_sql = task.get("gold_sql") or task.get("sql") or task.get("gold")
    if gold_sql is not None:
        gold_sql = str(gold_sql).replace("\\n", "\n")
    _gen_keys = ("generated_sql", "prediction_sql", "predicted_sql", "sql_pred", "prediction", "pred")
    generated_sql = None
    for key in _gen_keys:
        if key in task:
            generated_sql = task[key]
            break
    missing = [
        name
        for name, value in {
            "task_id": task_id,
            "db_id": db_id,
            "gold_sql": gold_sql,
            "generated_sql": generated_sql,
        }.items()
        if value is None or (name != "generated_sql" and value == "")
    ]
    if missing:
        raise ValueError(f"Metric task missing required fields: {', '.join(missing)}")

    return SQLMetricTask(
        task_id=str(task_id),
        question_id=question_id,
        db_id=str(db_id),
        gold_sql=str(gold_sql),
        generated_sql=str(generated_sql),
        db_path=task.get("db_path"),
        metadata=task.get("metadata"),
    )


def resolve_task_db_path(
    task: SQLMetricTask,
    *,
    db_path_resolver: DbPathResolver | None = None,
) -> Path:
    """Resolve the SQLite database path for a metric task."""
    if task.db_path is not None:
        path = Path(task.db_path).expanduser().resolve()
    elif db_path_resolver is not None:
        path = Path(db_path_resolver(task.db_id)).expanduser().resolve()
    else:
        path = default_bird_db_path(task.db_id)
    if not path.is_file():
        raise FileNotFoundError(f"SQLite database does not exist: {path}")
    return path


def default_bird_db_path(db_id: str, *, bird_base: str | Path | None = None) -> Path:
    """Return the default BIRD dev SQLite path for a db_id."""
    base = Path(bird_base) if bird_base is not None else Path("/data/yusun/dxr_models/EESQLBench/bird_format/data")
    return base / "dev_databases" / db_id / f"{db_id}.sqlite"


def comparison_mode_for_gold(sql: str) -> str:
    if has_order_by(sql):
        return "list"
    if has_distinct(sql):
        return "set"
    return "multiset"


def has_order_by(sql: str) -> bool:
    if sqlglot is not None and exp is not None:
        try:
            return sqlglot.parse_one(sql, dialect="sqlite").find(exp.Order) is not None
        except Exception:
            pass
    return bool(re.search(r"\border\s+by\b", sql, flags=re.IGNORECASE))


def has_distinct(sql: str) -> bool:
    if sqlglot is not None and exp is not None:
        try:
            ast = sqlglot.parse_one(sql, dialect="sqlite")
            select = ast.find(exp.Select)
            return bool(select and select.args.get("distinct"))
        except Exception:
            pass
    return bool(re.search(r"\bselect\s+distinct\b", sql, flags=re.IGNORECASE))


def positive_ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or numerator < 0 or denominator < 0:
        return None
    if numerator == 0 and denominator == 0:
        return 1.0
    if denominator == 0:
        return None
    return round(numerator / denominator, 6)


def first_error(*errors: str | None) -> str | None:
    for error in errors:
        if error:
            return error
    return None


def _strict_ex_value(row: dict[str, Any]) -> bool | None:
    value = row.get("strict_ex")
    if value is not None:
        return value is True
    return row.get("ex") is True


def _based_ex_value(row: dict[str, Any]) -> bool | None:
    value = row.get("based_ex")
    if value is not None:
        return value is True
    return row.get("ex") is True


def _cr_valid_rows(rows: Iterable[dict[str, Any]], *, prefix: str) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if _cr_valid_value(row, prefix=prefix) is True
        and _scan_row_ratio_value(row, prefix=prefix) is not None
    ]


def _cr_scores(rows: Iterable[dict[str, Any]], *, prefix: str) -> list[float]:
    return [
        value
        for value in (_cr_score_value(row, prefix=prefix) for row in rows)
        if value is not None
    ]


def _scan_row_ratios(rows: Iterable[dict[str, Any]], *, prefix: str) -> list[float]:
    return [
        value
        for value in (_scan_row_ratio_value(row, prefix=prefix) for row in rows)
        if value is not None
    ]


def _cr_valid_value(row: dict[str, Any], *, prefix: str) -> bool | None:
    if prefix == "based":
        value = row.get("based_cr_valid")
        if value is not None:
            return value is True
    value = row.get("strict_cr_valid")
    if value is not None:
        return value is True
    return row.get("cr_valid") is True


def _cr_score_value(row: dict[str, Any], *, prefix: str) -> float | None:
    if prefix == "based":
        value = float_value(row.get("based_cr_score"))
        if value is not None:
            return value
    value = float_value(row.get("strict_cr_score"))
    if value is not None:
        return value
    return float_value(row.get("cr_score"))


def _scan_row_ratio_value(row: dict[str, Any], *, prefix: str) -> float | None:
    if prefix == "based":
        value = float_value(row.get("based_scan_row_ratio"))
        if value is not None:
            return value
    value = float_value(row.get("strict_scan_row_ratio"))
    if value is not None:
        return value
    return float_value(row.get("scan_row_ratio"))


def float_value(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def safe_div(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def diff_ordered(gold_rows: list[tuple], generated_rows: list[tuple]) -> str:
    if len(gold_rows) != len(generated_rows):
        return (
            f"Row count mismatch: gold={len(gold_rows)}, "
            f"generated={len(generated_rows)} (order-sensitive)"
        )
    for idx, (gold_row, generated_row) in enumerate(zip(gold_rows, generated_rows)):
        if gold_row != generated_row:
            return f"First mismatch at row {idx}: gold={gold_row}, generated={generated_row}"
    return "Unknown ordered-result mismatch."


def diff_set(gold_rows: list[tuple], generated_rows: list[tuple]) -> str:
    gold_set = set(gold_rows)
    generated_set = set(generated_rows)
    missing = gold_set - generated_set
    extra = generated_set - gold_set
    parts = []
    if missing:
        parts.append(f"missing={list(missing)[:3]}")
    if extra:
        parts.append(f"extra={list(extra)[:3]}")
    return "; ".join(parts) if parts else "Unknown set-result mismatch."


def diff_multiset(gold_rows: list[tuple], generated_rows: list[tuple]) -> str:
    gold_counter = Counter(gold_rows)
    generated_counter = Counter(generated_rows)
    missing = gold_counter - generated_counter
    extra = generated_counter - gold_counter
    parts = []
    if missing:
        parts.append(f"missing={list(missing.items())[:3]}")
    if extra:
        parts.append(f"extra={list(extra.items())[:3]}")
    return "; ".join(parts) if parts else "Unknown multiset-result mismatch."

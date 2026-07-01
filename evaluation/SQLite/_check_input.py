"""Quick input file quality check."""
import json, sys
from pathlib import Path

path = Path(sys.argv[1])

# Optional: expected total (second positional arg, or --expected N)
expected_total = None
expected_id_range = None
args = sys.argv[2:]
for i, a in enumerate(args):
    if a == "--expected" and i + 1 < len(args):
        expected_total = int(args[i + 1])
    elif a == "--bird-dev":
        expected_total = 1534
        expected_id_range = range(1534)

data = json.loads(path.read_text())

print(f"File: {path}")
print(f"Size: {path.stat().st_size:,} bytes")

if isinstance(data, dict) and "res" in data:
    tasks = data["res"]
else:
    tasks = data if isinstance(data, list) else []
    print(f"WARNING: unexpected structure, type={type(data).__name__}")

total = len(tasks)
print(f"Total tasks: {total}")

# Empty / missing fields
empty_pred = [t for t in tasks if not str(t.get("pred", "")).strip()]
empty_gold = [t for t in tasks if not str(t.get("gold", "")).strip()]
null_db = [t for t in tasks if not str(t.get("db", "")).strip()]
print(f"Empty pred: {len(empty_pred)}", end="")
if empty_pred:
    print(f" qids={[t['id'] for t in empty_pred]}")
else:
    print()

print(f"Empty gold: {len(empty_gold)}")
print(f"Empty db: {len(null_db)}")

# Markdown
md_count = sum(1 for t in tasks if "```" in str(t.get("pred", "")))
print(f"Pred with markdown: {md_count}")

# Duplicate ids
ids = [t["id"] for t in tasks]
dup = [i for i in set(ids) if ids.count(i) > 1]
print(f"Duplicate ids: {len(dup)}")

# ID coverage (only when expected range is provided)
if expected_id_range is not None:
    ids_set = set(ids)
    expected = set(expected_id_range)
    missing = sorted(expected - ids_set)
    extra = sorted(ids_set - expected)
    print(f"Missing ids ({expected_id_range.start}-{expected_id_range.stop - 1}): {len(missing)}", end="")
    if missing:
        print(f" {missing[:20]}{'...' if len(missing) > 20 else ''}")
    else:
        print()

    print(f"Extra ids: {len(extra)}", end="")
    if extra:
        print(f" {extra[:20]}{'...' if len(extra) > 20 else ''}")
    else:
        print()
else:
    missing = []
    extra = []

# Non-SELECT pred
non_select = [t for t in tasks if not str(t.get("pred", "")).strip().upper().startswith(("SELECT", "WITH"))]
print(f"Non-SELECT/WITH pred: {len(non_select)}")
for t in non_select[:5]:
    pred = str(t.get("pred", ""))[:120]
    print(f"  qid={t['id']} db={t.get('db','?')}: {pred}")

# Spot check distribution
print(f"\nFirst 3 tasks:")
for t in tasks[:3]:
    pred = str(t.get("pred", ""))[:100]
    gold = str(t.get("gold", ""))[:100]
    print(f"  id={t['id']} db={t['db']}")
    print(f"    pred: {pred}")
    print(f"    gold: {gold}")

# Verdict
print(f"\n=== VERDICT ===")
issues = []
if missing:
    issues.append(f"MISSING {len(missing)} ids")
if empty_pred:
    issues.append(f"{len(empty_pred)} empty preds")
if md_count:
    issues.append(f"{md_count} markdown wrappers")
if non_select:
    issues.append(f"{len(non_select)} non-SELECT preds")
if expected_total is not None and total != expected_total:
    issues.append(f"Expected {expected_total}, got {total}")

if issues:
    print("ISSUES:", "; ".join(issues))
else:
    verdict = "READY for evaluation."
    if expected_total:
        verdict += f" All {expected_total} tasks present, all preds are SELECT/WITH statements."
    else:
        verdict += f" All {total} tasks valid, all preds are SELECT/WITH statements."
    print(verdict)

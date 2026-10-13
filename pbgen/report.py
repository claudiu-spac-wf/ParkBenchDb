"""Formatting for `pbgen status` and `pbgen check`, and the distribution checks (±2 pp)."""

from __future__ import annotations

import json

from pbgen import sizing


def format_status(status: dict, schema, actual_bytes: int = 0) -> str:
    runs = status.get("runs") or []
    if not runs:
        return "No generation runs yet. Use 'pbgen plan' to define the first one."
    run = next((r for r in runs if r["LoaderRunId"] == status.get("run")), runs[-1])
    summary = json.loads(run["PlanSummary"]) if isinstance(run.get("PlanSummary"), str) else {}
    total = status["done"] + status["pending"] + status["claimed"]
    pct = 100.0 * status["done"] / total if total else 100.0
    rate = status.get("recentRows", 0) / 300.0
    planned_rows = sum(t["rows"] for t in summary.get("tables", {}).values())
    remaining = max(0, planned_rows - status.get("doneRows", 0))
    eta = f"{int(remaining / rate) // 3600}:{int(remaining / rate) % 3600 // 60:02d}:{int(remaining / rate) % 60:02d}" \
        if rate > 0 and remaining else ("done" if not remaining else "n/a")
    sf = float(run["TargetScale"])
    lines = [
        f"Run {run['LoaderRunId']} ({run['RunKind']}) {run['RunStatus']}   target SF {sf:.4f} "
        f"(≈ {sizing.estimate_disk_bytes(schema, sf) / 1e9:.2f} GB on disk)   seed {run['RunSeed']}",
        f"Units: {status['done']:,} / {total:,} done ({pct:.1f}%)   claimed {status['claimed']}   pending {status['pending']:,}",
        f"Rows this run: {status.get('doneRows', 0):,} / {planned_rows:,}   rate {rate:,.0f} rows/s (last 5 min)   ETA {eta}",
        f"Estimated size: {sizing.describe(schema, sf)}" + (f"   actual files {actual_bytes / 1e9:.2f} GB" if actual_bytes else ""),
        "",
        f"{'Table':24s}{'Rows (watermark)':>18s}{'Target':>14s}",
    ]
    bti = {b["TableName"]: b for b in status.get("bti") or []}
    for t in sorted(schema.tables, key=lambda x: x.name.lower()):
        target = summary.get("tables", {}).get(t.name, {}).get("last", bti.get(t.name, {}).get("MaxId", 0))
        lines.append(f"{t.name:24s}{int(bti.get(t.name, {}).get('TableRowCount', 0)):>18,}{int(target):>14,}")
    return "\n".join(lines)


# documented distributions (feature 001 data-model §4): table, field, value, expected share
EXPECTED = [
    ("Customer", "CustomerKind", "I", 0.92), ("Customer", "CustomerStatus", "ACTIVE", 0.90),
    ("Customer", "IsPaperless", True, 0.55), ("Customer", "MarketingOptIn", True, 0.35),
    ("Account", "AccountStatus", "OPEN", 0.92), ("Card", "CardKind", "DEBIT", 0.85),
    ("CardAuthorization", "AuthKind", "FINAL", 0.56), ("CardAuthorization", "ResponseCode", "00", 0.94),
    ("CreditTransaction", "IsPayroll", True, 0.40), ("CustomerContact", "IsVerified", True, 0.85),
    ("LoginEvent", "EventKind", "LOGIN", 0.70), ("AuditLog", "AuditAction", "U", 0.75),
]


def check_distributions(samples: dict[str, list[dict]], expected=EXPECTED, tolerance: float = 0.02,
                        min_rows: int = 200) -> list[dict]:
    """samples: table -> rows. Returns check results (skips tables with too few sampled rows)."""
    out = []
    for table, fld, value, share in expected:
        rows = samples.get(table) or []
        if len(rows) < min_rows:
            out.append({"check": f"{table}.{fld}={value}", "ok": True, "skipped": True,
                        "detail": f"only {len(rows)} sampled rows (need {min_rows})"})
            continue
        got = sum(1 for r in rows if r.get(fld) == value) / len(rows)
        # tolerance widened by sampling error (3 standard errors) on small samples
        tol = max(tolerance, 3 * (share * (1 - share) / len(rows)) ** 0.5)
        ok = abs(got - share) <= tol
        out.append({"check": f"{table}.{fld}={value}", "ok": ok,
                    "detail": f"{got:.1%} observed vs {share:.0%} expected (±{tol:.1%}, n={len(rows)})"})
    return out


def format_checks(results: list[dict]) -> tuple[str, int]:
    lines, failed = [], 0
    for r in results:
        state = "ok" if r["ok"] else "FAIL"
        failed += not r["ok"]
        extra = f", e.g. id {r['exampleId']}" if r.get("exampleId") not in (None, 0, "") else ""
        lines.append(f"CHECK {r['check']}: {state} ({r.get('detail', '')}{extra})")
    lines.append("CHECK OK" if not failed else f"CHECK FAILED ({failed})")
    return "\n".join(lines), failed

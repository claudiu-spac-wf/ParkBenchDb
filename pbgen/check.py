"""`pbgen check`: data check (US5).

Real databases: db/abl/pbgen_check.p runs the in-database checks (density, BenchmarkTableInfo,
RandomInt ranges, foreign keys, derived rules); Python adds the distribution checks from samples.
Fake databases (tests): check_rows() runs the same checks over the stored rows in Python.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from pbgen import config, report
from pbgen.generate import refdata

SAMPLE_THRESHOLD = 1_000_000
POS_TYPE_IDS = {refdata.TT_ID[c] for c, _ in refdata.POS_TYPES}


def check_input(schema, mode: str) -> dict:
    tables = []
    for t in schema.tables:
        fks = [{"field": f.name, "parent": f.fk.table, "parentField": f.fk.parent_field,
                "optional": bool(f.fk.optional)} for f in t.fk_fields]
        tables.append({"name": t.name, "fks": fks})
    return {"mode": mode, "sampleThreshold": SAMPLE_THRESHOLD, "tables": tables}


def distribution_samples(agent, ks=(1, 2, 3)) -> dict[str, list[dict]]:
    samples: dict[str, list[dict]] = {}
    for table in sorted({e[0] for e in report.EXPECTED}):
        rows = []
        for k in ks:
            rows.extend(agent.request("sample", table=table, k=k).get("data", []))
        samples[table] = rows
    return samples


def check_rows(schema, rows: dict[str, list[dict]], bti: list[dict]) -> list[dict]:
    """Python implementation of pbgen_check.p over full row sets (used with FakeAgent)."""
    out = []
    bti_by = {b["TableName"]: b for b in bti}
    ids = {t: {r[t + "Id"] for r in rs} for t, rs in rows.items()}
    for t in schema.tables:
        rs = rows.get(t.name, [])
        idl = sorted(r[t.name + "Id"] for r in rs)
        n, mx = len(idl), (idl[-1] if idl else 0)
        dense = n == mx and len(set(idl)) == n and (not idl or idl[0] == 1)
        gap = next((i for i, v in enumerate(idl, 1) if v != i), 0)
        out.append({"check": "density", "table": t.name, "ok": dense,
                    "detail": f"rows {n}, first id {idl[0] if idl else 0}, last id {mx}", "exampleId": gap})
        b = bti_by.get(t.name, {})
        out.append({"check": "BenchmarkTableInfo", "table": t.name,
                    "ok": b.get("MaxId") == mx and b.get("TableRowCount") == n,
                    "detail": f"MaxId {b.get('MaxId')} / TableRowCount {b.get('TableRowCount')} vs last id {mx}, rows {n}"})
        for size in (10, 100, 1000):
            bad = next((r[t.name + "Id"] for r in rs if not 1 <= r[f"RandomInt{size}"] <= size), 0)
            out.append({"check": f"RandomInt{size}", "table": t.name, "ok": not bad,
                        "detail": f"within 1-{size}" if not bad else f"value outside 1-{size}", "exampleId": bad})
        for f in t.fk_fields:
            if f.fk.parent_field == f.fk.table + "Id":
                target = ids.get(f.fk.table, set())
            else:
                target = {r[f.fk.parent_field] for r in rows.get(f.fk.table, [])}
            bad = [r for r in rs if not (f.fk.optional and r[f.name] == 0) and r[f.name] not in target]
            out.append({"check": f"fk.{f.name}", "table": t.name, "ok": not bad, "sampleSize": len(rs),
                        "detail": f"{len(bad)} of {len(rs)} rows point at a missing {f.fk.table}",
                        "exampleId": bad[0][t.name + "Id"] if bad else 0})
    # derived: statement totals and chain
    deb, cred = defaultdict(list), defaultdict(list)
    for r in rows.get("DebitTransaction", []):
        deb[r["AccountStatementId"]].append(r["Amount"])
    for r in rows.get("CreditTransaction", []):
        cred[r["AccountStatementId"]].append(r["Amount"])
    bad, by_acct = [], defaultdict(list)
    for s in rows.get("AccountStatement", []):
        sid = s["AccountStatementId"]
        by_acct[s["AccountId"]].append(s)
        if (round(sum(deb[sid]), 2) != round(s["TotalDebits"], 2) or round(sum(cred[sid]), 2) != round(s["TotalCredits"], 2)
                or len(deb[sid]) != s["DebitCount"] or len(cred[sid]) != s["CreditCount"]
                or round(s["OpeningBalance"] - s["TotalDebits"] + s["TotalCredits"], 2) != round(s["ClosingBalance"], 2)):
            bad.append(sid)
    for ss in by_acct.values():
        ss.sort(key=lambda s: s["PeriodEnd"])
        bad += [c["AccountStatementId"] for p, c in zip(ss, ss[1:]) if round(p["ClosingBalance"], 2) != round(c["OpeningBalance"], 2)]
    out.append({"check": "derived.statementTotals", "table": "AccountStatement", "ok": not bad,
                "detail": f"{len(bad)} statements disagree with their transactions or the previous closing",
                "exampleId": bad[0] if bad else 0})
    # derived: holders
    hold = defaultdict(list)
    for h in rows.get("AccountHolder", []):
        hold[h["AccountId"]].append(h)
    bad = [a for a, hs in hold.items() if round(sum(h["OwnershipPercent"] for h in hs), 2) != 100
           or sum(h["HolderRole"] == "PRIMARY" for h in hs) != 1]
    out.append({"check": "derived.accountHolders", "table": "AccountHolder", "ok": not bad,
                "detail": f"{len(bad)} accounts without 100% ownership and one PRIMARY", "exampleId": bad[0] if bad else 0})
    return out


def run_check(args, spec: dict, spool: Path, schema) -> int:
    from pbgen.launcher import make_agent
    mode = "full" if args.full else "sample"
    agent = make_agent(spec, spool / "ctl-check")
    try:
        if spec["kind"] == "fake":
            rows = {t.name: agent.all_rows(t.name) for t in schema.tables}
            results = check_rows(schema, rows, agent.request("state")["bti"])
            samples = {t: [r for r in rows.get(t, []) if r["RandomInt1000"] <= 3] for t in {e[0] for e in report.EXPECTED}}
        else:
            from pbgen.agent import run_oneshot
            work = spool / "check"
            work.mkdir(parents=True, exist_ok=True)
            inp, outp = work / "check-in.json", work / "check-out.json"
            inp.write_text(json.dumps(check_input(schema, mode)), encoding="utf-8")
            outp.unlink(missing_ok=True)
            conn = config.ConnectionConfig(db=spec["db"], host=spec.get("host"), port=spec.get("port"))
            code, output = run_oneshot(conn, "pbgen_check.p", f"{inp}|{outp}", cwd=work)
            if not outp.exists():
                print(output.strip())
                print("ERROR: the in-database check did not produce results")
                return 1
            results = json.loads(outp.read_text(encoding="utf-8-sig"))
            samples = distribution_samples(agent)
    finally:
        agent.close()
    for r in results:
        r["check"] = f"{r['table']}.{r['check']}"
    results += report.check_distributions(samples)
    if args.json:
        print(json.dumps(results, indent=2))
        return 0 if all(r["ok"] for r in results) else 1
    text, failed = report.format_checks(results)
    print(text)
    return 0 if failed == 0 else 1

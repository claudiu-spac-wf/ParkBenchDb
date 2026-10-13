"""Unit generator tests: determinism, shape, counts, FK closure, derived rules, distributions (T016)."""

import base64
import datetime as dt
import hashlib
import json
import unittest
from collections import defaultdict

from helpers import small_plan

from pbgen import report
from pbgen.generate import generate_unit, refdata
from pbgen.generate.common import _parse_map
from pbgen.worker import context_for_run
from tools.gen_db_files import lob_size_bytes

CUSTOMER_UNITS = 12
POS_TYPE_IDS = {refdata.TT_ID[c] for c, _ in refdata.POS_TYPES}


def digest(tables) -> str:
    return hashlib.sha256(json.dumps(tables, sort_keys=True).encode()).hexdigest()


class GenerateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema, cls.prun, cls.units, cls.summary = small_plan(CUSTOMER_UNITS, seed=7)
        cls.ctx = context_for_run(cls.schema, cls.prun)
        cls.generated = [(u, generate_unit(u, cls.ctx)) for u in cls.units]
        cls.rows = defaultdict(list)
        for _u, tables in cls.generated:
            for t, rs in tables.items():
                cls.rows[t].extend(rs)

    # (a)
    def test_deterministic(self):
        for u, tables in (self.generated[0], self.generated[-1]):
            self.assertEqual(digest(generate_unit(u, self.ctx)), digest(tables), u["UnitKind"])

    # (b)
    def test_rows_have_exactly_the_schema_fields(self):
        for t in self.schema.tables:
            names = [f.name for f in t.fields]
            for r in self.rows.get(t.name, [])[:200]:
                self.assertEqual(list(r), names, t.name)

    def test_json_types(self):
        types = {"INTEGER": int, "INT64": int, "DECIMAL": (int, float), "LOGICAL": bool, "CHARACTER": str,
                 "CLOB": str, "BLOB": str, "DATE": str, "DATETIME": str, "DATETIME-TZ": str}
        for t in self.schema.tables:
            for r in self.rows.get(t.name, [])[:100]:
                for f in t.fields:
                    v = r[f.name]
                    if v is None:
                        self.assertFalse(f.mandatory and f.type not in ("CLOB", "BLOB", "DATE", "DATETIME-TZ"),
                                         f"{t.name}.{f.name} is null")
                        continue
                    self.assertIsInstance(v, types[f.type], f"{t.name}.{f.name}")
                    if f.type == "DATETIME-TZ":
                        self.assertIsNotNone(dt.datetime.fromisoformat(v).tzinfo)

    # (c)
    def test_counts_and_ids_match_the_plan(self):
        for u, tables in self.generated:
            planned = _parse_map(u["RowCounts"])
            first = _parse_map(u["FirstIds"])
            self.assertEqual({t: len(r) for t, r in tables.items()}, planned, u["UnitNo"])
            for t, rs in tables.items():
                self.assertEqual(sorted(r[t + "Id"] for r in rs), list(range(first[t], first[t] + planned[t])))

    # (d)
    def test_random_ints(self):
        for t, rs in self.rows.items():
            for r in rs:
                self.assertTrue(1 <= r["RandomInt10"] <= 10 and 1 <= r["RandomInt100"] <= 100
                                and 1 <= r["RandomInt1000"] <= 1000, t)
        values = {r["RandomInt10"] for r in self.rows["DebitTransaction"]}
        self.assertEqual(values, set(range(1, 11)))

    # (e)
    def test_foreign_keys_close(self):
        ids = {t: {r[t + "Id"] for r in rs} for t, rs in self.rows.items()}
        codes = {("Currency", "CurrencyCode"): {r["CurrencyCode"] for r in self.rows["Currency"]},
                 ("Country", "CountryCode"): {r["CountryCode"] for r in self.rows["Country"]}}
        for t in self.schema.tables:
            for f in t.fk_fields:
                target = codes.get((f.fk.table, f.fk.parent_field)) or ids.get(f.fk.table, set())
                for r in self.rows.get(t.name, []):
                    v = r[f.name]
                    if f.fk.optional and v == 0:
                        continue
                    self.assertIn(v, target, f"{t.name}.{f.name}={v} -> {f.fk.table}")

    # (f)
    def test_statement_totals_and_chain(self):
        debits, credits = defaultdict(list), defaultdict(list)
        for r in self.rows["DebitTransaction"]:
            debits[r["AccountStatementId"]].append(r["Amount"])
        for r in self.rows["CreditTransaction"]:
            credits[r["AccountStatementId"]].append(r["Amount"])
        by_account = defaultdict(list)
        for s in self.rows["AccountStatement"]:
            sid = s["AccountStatementId"]
            self.assertAlmostEqual(s["TotalDebits"], round(sum(debits[sid]), 2), places=2)
            self.assertAlmostEqual(s["TotalCredits"], round(sum(credits[sid]), 2), places=2)
            self.assertEqual(s["DebitCount"], len(debits[sid]))
            self.assertEqual(s["CreditCount"], len(credits[sid]))
            self.assertAlmostEqual(s["ClosingBalance"], round(s["OpeningBalance"] - s["TotalDebits"] + s["TotalCredits"], 2),
                                   places=2)
            by_account[s["AccountId"]].append(s)
        for stmts in by_account.values():
            stmts.sort(key=lambda s: s["PeriodEnd"])
            for prev, cur in zip(stmts, stmts[1:]):
                self.assertAlmostEqual(cur["OpeningBalance"], prev["ClosingBalance"], places=2)

    def test_current_balance_is_last_running_balance(self):
        last = {}
        for table in ("DebitTransaction", "CreditTransaction"):
            for r in self.rows[table]:
                key = (r["PostedAt"], table == "CreditTransaction", r[table + "Id"])
                if r["AccountId"] not in last or key > last[r["AccountId"]][0]:
                    last[r["AccountId"]] = (key, r["RunningBalance"])
        mismatches = [a["AccountId"] for a in self.rows["Account"]
                      if a["AccountId"] in last and abs(a["CurrentBalance"] - last[a["AccountId"]][1]) > 0.005]
        # equal-millisecond ties between a debit and a credit can reorder; allow a tiny fraction
        self.assertLessEqual(len(mismatches), max(1, len(self.rows["Account"]) // 200), mismatches[:5])

    def test_transfers_link_a_debit_and_a_credit(self):
        deb = {r["DebitTransactionId"]: r for r in self.rows["DebitTransaction"]}
        cred = {r["CreditTransactionId"]: r for r in self.rows["CreditTransaction"]}
        for t in self.rows["Transfer"]:
            d, c = deb[t["DebitTransactionId"]], cred[t["CreditTransactionId"]]
            self.assertEqual(d["TransactionTypeId"], refdata.TT_ID["XFER"])
            self.assertEqual(c["TransactionTypeId"], refdata.TT_ID["XFERIN"])
            self.assertEqual(d["AccountId"], t["FromAccountId"])
            self.assertEqual(c["AccountId"], t["ToAccountId"])
            self.assertEqual(d["Amount"], t["Amount"])
            self.assertEqual(c["Amount"], t["Amount"])

    def test_each_pos_debit_has_one_final_auth(self):
        finals = defaultdict(int)
        for a in self.rows["CardAuthorization"]:
            if a["DebitTransactionId"]:
                self.assertEqual((a["AuthKind"], a["IsApproved"]), ("FINAL", True))
                finals[a["DebitTransactionId"]] += 1
        pos = [r["DebitTransactionId"] for r in self.rows["DebitTransaction"] if r["TransactionTypeId"] in POS_TYPE_IDS]
        self.assertEqual(sorted(finals), sorted(pos))
        self.assertTrue(all(v == 1 for v in finals.values()))

    def test_account_holders(self):
        by_account = defaultdict(list)
        for h in self.rows["AccountHolder"]:
            by_account[h["AccountId"]].append(h)
        self.assertEqual(set(by_account), {a["AccountId"] for a in self.rows["Account"]})
        for hs in by_account.values():
            self.assertAlmostEqual(sum(h["OwnershipPercent"] for h in hs), 100.0, places=2)
            self.assertEqual(sum(1 for h in hs if h["HolderRole"] == "PRIMARY"), 1)

    def test_one_manager_per_branch(self):
        managers = [e["BranchId"] for e in self.rows["Employee"] if e["IsBranchManager"]]
        self.assertEqual(sorted(managers), list(range(1, 251)))

    # (g)
    def test_documented_distributions(self):
        results = report.check_distributions(self.rows)
        failed = [r for r in results if not r["ok"]]
        self.assertEqual(failed, [], failed)
        self.assertGreater(sum(1 for r in results if not r.get("skipped")), 6)

    # (h)
    def test_faker_realism(self):
        names = [(c["FirstName"], c["LastName"]) for c in self.rows["Customer"] if c["CustomerKind"] == "I"]
        self.assertGreater(len(set(names)) / len(names), 0.9)
        for c in self.rows["Customer"]:
            self.assertTrue(c["LastName"] and "@" in c["Email"] and c["Occupation"])
        self.assertGreater(len({m["MerchantName"] for m in self.rows["Merchant"]}), 700)

    # (i)
    def test_lobs(self):
        specs = {(t.name, f.name): f for t in self.schema.tables for f in t.lob_fields}
        for (t, name), f in specs.items():
            rows = self.rows.get(t, [])
            if not rows:
                continue
            present = [r[name] for r in rows if r[name] is not None]
            if len(rows) >= 200:
                share = len(present) / len(rows)
                p = f.lob.fractionPopulated
                self.assertLessEqual(abs(share - p), max(0.02, 3 * (p * (1 - p) / len(rows)) ** 0.5), f"{t}.{name}")
            for v in present:
                n = len(base64.b64decode(v)) if f.type == "BLOB" else len(v.encode("utf-8"))
                self.assertLessEqual(n, lob_size_bytes(f.lob.maxSize), f"{t}.{name}")
                if f.type == "BLOB":
                    self.assertGreaterEqual(n, f.lob.minBytes * 0.99, f"{t}.{name}")


if __name__ == "__main__":
    unittest.main()

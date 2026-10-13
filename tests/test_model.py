"""Tests for tools/schema_model.py (T018)."""

import os
import unittest

from helpers import FIXTURE, REAL, mutated, table, write_temp

from tools import schema_model as m


class LoadTests(unittest.TestCase):
    def test_fixture_and_real_schema_load(self):
        self.assertEqual(len(m.load_schema(FIXTURE).tables), 3)
        self.assertEqual(len(m.load_schema(REAL).tables), 32)

    def test_unknown_key_is_rejected(self):
        path = write_temp(mutated(lambda d: table(d, "Parent").update(colour="blue")))
        try:
            with self.assertRaises(m.SchemaError) as cm:
                m.load_schema(path)
            self.assertEqual(cm.exception.rule, "S01")
        finally:
            os.unlink(path)

    def test_extent_key_is_rejected(self):
        path = write_temp(mutated(lambda d: table(d, "Parent")["fields"][0].update(extent=3)))
        try:
            with self.assertRaises(m.SchemaError) as cm:
                m.load_schema(path)
            self.assertEqual(cm.exception.rule, "S02")
        finally:
            os.unlink(path)

    def test_listed_updatedat_on_master_table_is_rejected(self):
        def add_updated(d):
            table(d, "Parent")["fields"].append({
                "name": "UpdatedAt", "type": "DATETIME-TZ", "format": "99/99/9999", "mandatory": True,
                "initial": "NOW", "description": "x", "gen": "x"})
        path = write_temp(mutated(add_updated))
        try:
            with self.assertRaises(m.SchemaError) as cm:
                m.load_expanded(path)
            self.assertEqual(cm.exception.rule, "S03")
        finally:
            os.unlink(path)


class ExpansionTests(unittest.TestCase):
    def setUp(self):
        self.schema = m.load_expanded(REAL)

    def test_standard_fields_first_in_order(self):
        for t in self.schema.tables:
            names = [f.name for f in t.fields[:5]]
            self.assertEqual(names, [f"{t.name}Id", "RandomInt10", "RandomInt100", "RandomInt1000", "CreatedAt"], t.name)
            self.assertTrue(all(f.standard for f in t.fields[:5]))

    def test_master_tables_end_with_updatedat(self):
        for t in self.schema.tables:
            if t.cls == "M":
                self.assertEqual(t.fields[-1].name, "UpdatedAt", t.name)
            else:
                self.assertIsNone(t.get_field("UpdatedAt"), t.name)

    def test_pk_is_only_primary_index(self):
        for t in self.schema.tables:
            primaries = [i.name for i in t.indexes if i.primary]
            self.assertEqual(primaries, [f"Pk{t.name}"], t.name)

    def test_expansion_is_idempotent(self):
        before = sum(len(t.fields) for t in self.schema.tables)
        m.expand_standard(self.schema)
        self.assertEqual(before, sum(len(t.fields) for t in self.schema.tables))


class LoadOrderTests(unittest.TestCase):
    def test_matches_research_r12(self):
        expected = [
            ["AccountType", "Currency", "MerchantCategory", "TransactionType"],
            ["Country", "ExchangeRate"],
            ["Branch", "Merchant"],
            ["Account", "Customer", "Employee"],
            ["AccountHolder", "AccountStatement", "Card", "CustomerAddress", "CustomerContact", "CustomerDocument",
             "CustomerNote", "InterestRateHistory", "Loan", "LoginEvent", "MonthlyBalance", "Payee"],
            ["CreditTransaction", "DebitTransaction", "ScheduledPayment", "StatementDocument"],
            ["CardAuthorization", "LoanPayment", "Transfer"],
            ["AuditLog"],
            ["BenchmarkTableInfo"],
        ]
        self.assertEqual(m.load_order(m.load_expanded(REAL)), expected)

    def test_cycle_is_reported(self):
        def cycle(d):
            table(d, "Parent")["fields"].append({
                "name": "ChildId", "type": "INT64", "format": ">>>>9", "mandatory": True, "initial": "0",
                "description": "x", "gen": "x", "fk": {"table": "Child", "cardinality": "1 / 0–1"}})
        path = write_temp(mutated(cycle))
        try:
            with self.assertRaises(m.SchemaError) as cm:
                m.load_order(m.load_expanded(path))
            self.assertEqual(cm.exception.rule, "S04")
        finally:
            os.unlink(path)


class SizingTests(unittest.TestCase):
    def setUp(self):
        self.schema = m.load_expanded(REAL)

    def test_record_and_lob_totals_match_research_r7(self):
        data = sum(m.estimate_data_bytes(t) for t in self.schema.tables)
        lob = sum(m.estimate_lob_bytes(t) for t in self.schema.tables)
        self.assertGreaterEqual(data, 30e9)
        self.assertLessEqual(data, 40e9)
        self.assertGreaterEqual(lob, 4e9)
        self.assertLessEqual(lob, 6e9)

    def test_tiers(self):
        self.assertEqual(m.volume_tier(999), "Tiny")
        self.assertEqual(m.volume_tier(1_000), "Small")
        self.assertEqual(m.volume_tier(100_000), "Medium")
        self.assertEqual(m.volume_tier(5_000_000), "Large")
        self.assertEqual(m.volume_tier(50_000_000), "Very Large")
        self.assertEqual(m.size_tier(self.schema.get_table("Customer")), "Wide")
        self.assertEqual(m.size_tier(self.schema.get_table("AuditLog")), "Narrow")
        self.assertEqual(m.size_tier(self.schema.get_table("Account")), "Standard")
        self.assertEqual(m.size_tier(self.schema.get_table("Employee")), "LOB")
        self.assertEqual(m.lob_kind(self.schema.get_table("StatementDocument")), "both")

    def test_scaling(self):
        cur = self.schema.get_table("Currency")
        cust = self.schema.get_table("Customer")
        self.assertEqual(m.rows_at(cur, 10), 40)
        self.assertEqual(m.rows_at(cust, 0.1), 100_000)

    def test_computed_estimate_is_positive(self):
        t = self.schema.get_table("Customer")
        self.assertGreater(m.computed_record_bytes(t), 100)
        self.assertEqual(m.estimate_record_bytes(t), 850)

    def test_split_camel(self):
        self.assertEqual(m.split_camel("AccountId"), "Account Id")
        self.assertEqual(m.split_camel("RandomInt100"), "Random Int 100")


if __name__ == "__main__":
    unittest.main()

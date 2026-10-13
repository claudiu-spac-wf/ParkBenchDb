"""Tests for tools/gen_docs.py (T020, T026, T031, T035)."""

import contextlib
import io
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import FIXTURE, GOLDEN, REAL

from tools import gen_docs as g
from tools import schema_model as m


class TablePageTests(unittest.TestCase):
    def setUp(self):
        self.fx = m.load_expanded(FIXTURE)
        self.page = g.render_table_page(self.fx, self.fx.get_table("Child"))

    def test_child_page_matches_golden(self):
        golden = (GOLDEN / "Child.md").read_text(encoding="utf-8")
        self.assertEqual(self.page, golden)

    def test_sections_in_order(self):
        heads = re.findall(r"^## (.+)$", self.page, re.M)
        self.assertEqual(heads, ["Description", "Facts", "Fields", "LOB fields", "Indexes", "Relationships",
                                 "Access examples"])

    def test_access_examples_use_randomint100(self):
        abl = self.page[self.page.index("```abl"):]
        sql = self.page[self.page.index("```sql"):]
        self.assertIn("RandomInt100 = 42", abl[:abl.index("```", 6)])
        self.assertIn("RandomInt100 = 42", sql[:sql.index("```", 6)])
        self.assertIn("BenchmarkTableInfo.MaxId", self.page)

    def test_relationships_list_parent_and_children(self):
        self.assertIn("## Relationships", self.page)
        self.assertIn("[Parent](Parent.md)", self.page[self.page.index("**Parents**"):])
        parent_page = g.render_table_page(self.fx, self.fx.get_table("Parent"))
        self.assertIn("[Child](Child.md).`ParentId`", parent_page)

    def test_every_real_table_has_one_primary_and_all_fields(self):
        schema = m.load_expanded(REAL)
        for t in schema.tables:
            page = g.render_table_page(schema, t)
            idx = page[page.index("## Indexes"):page.index("## Relationships")]
            self.assertEqual(len(re.findall(r"^\| `[^`]+`[^|]*\| [^|]+ \| Y \|", idx, re.M)), 1, t.name)
            for f in t.fields:
                self.assertIn(f"`{f.name}`", page, f"{t.name}.{f.name}")

    def test_no_bare_angle_brackets_outside_code(self):
        schema = m.load_expanded(REAL)
        texts = [g.render_readme(schema)] + [g.render_table_page(schema, t) for t in schema.tables]
        for text in texts:
            outside = re.sub(r"```.*?```", "", text, flags=re.S)
            outside = re.sub(r"`[^`]*`", "", outside)
            self.assertNotRegex(outside, r"<[A-Za-z]")


class ReadmeTests(unittest.TestCase):
    def setUp(self):
        self.schema = m.load_expanded(REAL)
        self.readme = g.render_readme(self.schema)

    def test_section_order(self):
        heads = re.findall(r"^## (.+)$", self.readme, re.M)
        self.assertEqual(heads, ["Purpose and scope", "Conventions", "Benchmark access guide", "Summary matrix",
                                 "Tier coverage", "Entity-relationship diagram", "Storage areas", "Load order",
                                 "Sizing", "Sequences", "Building the database"])

    def test_access_guide_and_sequences(self):
        self.assertIn("### Guarantees", self.readme)
        self.assertIn("G6", self.readme)
        self.assertEqual(len(re.findall(r"^- `Seq\w+Id`$", self.readme, re.M)), 32)

    def test_summary_matrix_has_32_rows(self):
        sec = self.readme[self.readme.index("## Summary matrix"):self.readme.index("## Tier coverage")]
        self.assertEqual(len(re.findall(r"^\| \d+ \| \[", sec, re.M)), 32)

    def test_tier_coverage_all_ok(self):
        sec = self.readme[self.readme.index("## Tier coverage"):self.readme.index("### Index shapes")]
        self.assertNotIn("✘", sec)

    def test_er_load_order_storage_sizing(self):
        self.assertIn("erDiagram", self.readme)
        self.assertIn("Currency ||--o{ Country", self.readme)
        self.assertIn("AccountStatement ||--o| StatementDocument", self.readme)
        self.assertIn("|o--o{ DebitTransaction", self.readme)
        for h in ("## Load order", "## Storage areas", "## Sizing"):
            self.assertIn(h, self.readme)

    def test_sizing_total_in_target(self):
        mm = re.search(r"\*\*Data total\*\* \| \*\*([0-9.]+) GB\*\*", self.readme)
        self.assertTrue(20 <= float(mm.group(1)) <= 50)


class CsvTests(unittest.TestCase):
    def test_sizing_csv(self):
        csv = g.render_sizing_csv(m.load_expanded(REAL)).splitlines()
        self.assertEqual(csv[0], "table,rows_sf1,scaling,avg_record_bytes,data_gb,lob_gb,volume_tier,size_tier")
        self.assertEqual(len(csv), 33)


class CliTests(unittest.TestCase):
    def test_generate_check_and_stale_removal(self):
        out = Path(tempfile.mkdtemp())
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(g.main([str(REAL), "--out", str(out)]), 0)
                self.assertEqual(len(list((out / "tables").glob("*.md"))), 32)
                self.assertEqual(g.main([str(REAL), "--out", str(out), "--check"]), 0)
                (out / "tables" / "Customer.md").write_text("edited by hand\n", encoding="utf-8")
                (out / "tables" / "Obsolete.md").write_text("stale\n", encoding="utf-8")
                self.assertEqual(g.main([str(REAL), "--out", str(out), "--check"]), 1)
                self.assertEqual(g.main([str(REAL), "--out", str(out)]), 0)
                self.assertFalse((out / "tables" / "Obsolete.md").exists())
                self.assertEqual(g.main([str(REAL), "--out", str(out), "--check"]), 0)
        finally:
            shutil.rmtree(out)

    def test_output_is_deterministic(self):
        schema = m.load_expanded(REAL)
        self.assertEqual(g.render_all(schema), g.render_all(m.load_expanded(REAL)))


if __name__ == "__main__":
    unittest.main()

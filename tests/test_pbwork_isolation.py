"""Pure isolation manifest checks; destructive cleanup is not yet enabled."""

import tempfile
import unittest
from pathlib import Path

from pbwork.isolation import benchmark_names, baseline_from_dump, parse_dump_manifest


class IsolationManifestTests(unittest.TestCase):
    def fixture(self, path: Path):
        tables = sorted(benchmark_names())
        lines = ["format=parkbench-dump-1", "activeClaims=0"]
        lines += [f"rows={table}={index}" for index, table in enumerate(tables)]
        lines += [f"seq=Seq{table}Id={index}" for index, table in enumerate(tables)]
        (path / "manifest.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        (path / "schema.df").write_text("test schema", encoding="utf-8")

    def test_captures_actual_rows_separately_from_benchmark_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dump, work = root / "dump", root / "work"
            dump.mkdir()
            self.fixture(dump)
            bti = {"Currency": {"TableRowCount": 999}}
            baseline = baseline_from_dump("run", str(root / "source" / "parkbench"),
                                          str(dump), str(work), bti, "now")
            self.assertEqual(baseline.source_row_counts["Currency"], sorted(benchmark_names()).index("Currency"))
            self.assertEqual(baseline.source_benchmark_counts, bti)
            self.assertEqual(len(baseline.source_sequences), 32)
            self.assertEqual(len(baseline.source_schema_digest), 64)

    def test_incomplete_manifest_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.txt"
            path.write_text("format=parkbench-dump-1\nrows=Currency=1\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "incomplete"):
                parse_dump_manifest(path)

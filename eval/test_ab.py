"""Tests for ab.py. Run: python3 -m unittest discover -s eval"""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import ab  # noqa: E402


class TestAB(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.runs = self.root / "runs"
        (self.root / "with.md").write_text("Decision needed by Nov 18: vendor A or B?\nThanks, Sam")
        (self.root / "without.md").write_text("Hi Henrik, hope you are well! Here is an update.\nBest, Team")

    def tearDown(self):
        self.tmp.cleanup()

    def cli(self, *argv):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = ab.main(["--dir", str(self.runs), *argv])
        return code, out.getvalue()

    def prepare(self, task="t1", seed=1):
        self.cli("prepare", task, "--with", str(self.root / "with.md"), "--without", str(self.root / "without.md"),
                 "--seed", str(seed))
        return json.loads((self.runs / ".keys" / f"{task}.json").read_text())

    def test_word_edits(self):
        self.assertEqual(ab.word_edits("a b c", "a b c"), 0)
        self.assertEqual(ab.word_edits("a b c", "a x c"), 1)
        self.assertEqual(ab.word_edits("a b c", "a b c d e"), 2)

    def test_prepare_blinds_outputs(self):
        key = self.prepare()
        self.assertEqual(sorted(key.values()), ["with", "without"])
        a = (self.runs / "t1" / "A.md").read_text()
        self.assertEqual(a, (self.root / f"{key['A']}.md").read_text())
        self.assertFalse(any(p.suffix == ".json" for p in (self.runs / "t1").iterdir()))

    def test_prepare_refuses_overwrite(self):
        self.prepare()
        with self.assertRaises(SystemExit):
            self.prepare()

    def test_rejects_path_traversal(self):
        with self.assertRaises(SystemExit):
            self.cli("prepare", "../evil", "--with", str(self.root / "with.md"),
                     "--without", str(self.root / "without.md"))

    def test_record_and_report(self):
        key = self.prepare()
        with_label = "A" if key["A"] == "with" else "B"
        other = "B" if with_label == "A" else "A"
        final = self.root / "final.md"
        final.write_text("Decision needed by Nov 18: vendor A or B?\nThanks, Sam")
        self.cli("record", "t1", "--choice", with_label, f"--final-{with_label.lower()}", str(final),
                 f"--final-{other.lower()}", str(final), "--out-of-scope-with", "0")
        s = ab.summarize(ab.load_results(self.runs))
        self.assertEqual(s["arms"]["with"], {"chosen": 1, "measured": 1, "first_pass_accepted": 1, "mean_edits": 0.0})
        self.assertEqual(s["arms"]["without"]["chosen"], 0)
        self.assertGreater(s["arms"]["without"]["mean_edits"], 0)
        self.assertEqual(s["out_of_scope_rules_with_profile"], 0)
        code, out = self.cli("report")
        self.assertIn("too few", out)

    def test_rerecord_replaces(self):
        self.prepare()
        self.cli("record", "t1", "--choice", "A", "--accepted-as-is")
        self.cli("record", "t1", "--choice", "neither")
        results = ab.load_results(self.runs)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["choice"], "neither")


if __name__ == "__main__":
    unittest.main()

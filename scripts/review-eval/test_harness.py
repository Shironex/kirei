#!/usr/bin/env python3
"""Unit tests for the review-recall scorer. Run: python3 scripts/review-eval/test_harness.py"""
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness  # noqa: E402

REVIEW = """## KIREI-GATE REVIEW - range a..b

1. [HIGH] `apps/api/src/a.ts:40-44` - something real
2. [MEDIUM] `apps/api/src/b.ts:10`, `:20` - elsewhere
3. **[LOW]** `c.ts:5` - bold severity

**Gate surface:**
| `file:line` | before | after | direction | named in intent? |
|---|---|---|---|---|
| `apps/api/package.json:30` | `--lines 85` | `--lines 80` | relaxed | no |

**Uncertainties (could not fully verify):**
- `apps/api/src/d.ts:7` - could not rule out

VERDICT: HOLD
"""


class ParseTest(unittest.TestCase):
    def test_findings_uncertainties_and_verdict(self):
        findings, verdict = harness.parse_review(REVIEW)
        self.assertEqual(verdict, "HOLD")
        real = [(f["severity"], f["path"], f["start"], f["end"]) for f in findings if not f["uncertain"]]
        self.assertEqual(real, [
            ("HIGH", "apps/api/src/a.ts", 40, 44),
            ("MEDIUM", "apps/api/src/b.ts", 10, 10),
            ("LOW", "c.ts", 5, 5),
        ])
        unc = [(f["path"], f["start"]) for f in findings if f["uncertain"]]
        self.assertEqual(unc, [("apps/api/src/d.ts", 7)])

    def test_every_cited_location_counts(self):
        findings, _ = harness.parse_review(REVIEW)
        b = [f for f in findings if f["path"] == "apps/api/src/b.ts"][0]
        self.assertEqual(b["locs"], [("apps/api/src/b.ts", 10, 10), ("apps/api/src/b.ts", 20, 20)])
        self.assertTrue(harness.hits(b, {"apps/api/src/b.ts": [22]}))

    def test_gate_table_rows_are_not_findings(self):
        findings, _ = harness.parse_review(REVIEW)
        self.assertNotIn("apps/api/package.json", [f["path"] for f in findings])

    def test_verdict_must_be_alone_on_its_line(self):
        _, verdict = harness.parse_review("VERDICT: MERGE, probably\n")
        self.assertIsNone(verdict)


class HitTest(unittest.TestCase):
    GROUND = {"apps/api/src/a.ts": [50], "src/x.ts": [3]}

    def test_range_within_near(self):
        f = {"path": "apps/api/src/a.ts", "start": 40, "end": 47}
        self.assertTrue(harness.hits(f, self.GROUND))

    def test_outside_near(self):
        f = {"path": "apps/api/src/a.ts", "start": 40, "end": 46}
        self.assertFalse(harness.hits(f, self.GROUND))

    def test_suffix_path_match(self):
        self.assertTrue(harness.hits({"path": "./x.ts", "start": 1, "end": 1}, {"src/x.ts": [3]}))
        self.assertFalse(harness.hits({"path": "ax.ts", "start": 3, "end": 3}, {"src/x.ts": [3]}))


class StatsTest(unittest.TestCase):
    def test_wilson_known_value(self):
        lo, hi = harness.wilson(7, 8)
        self.assertAlmostEqual(lo, 0.529, places=2)
        self.assertAlmostEqual(hi, 0.978, places=2)

    def test_wilson_edges(self):
        self.assertEqual(harness.wilson(0, 0), (0.0, 0.0))
        lo, hi = harness.wilson(0, 10)
        self.assertEqual(lo, 0.0)
        self.assertGreater(hi, 0.0)

    def test_mcnemar_exact(self):
        self.assertEqual(harness.mcnemar_exact(0, 0), 1.0)
        self.assertAlmostEqual(harness.mcnemar_exact(0, 5), 0.0625)
        self.assertAlmostEqual(harness.mcnemar_exact(3, 3), 1.0)

    def test_z_equal_proportions(self):
        z, p = harness.two_proportion_z(5, 10, 5, 10)
        self.assertEqual(z, 0.0)
        self.assertAlmostEqual(p, 1.0)


class LineMapTest(unittest.TestCase):
    """map_new_to_old against a real repo, since it parses real `git diff -U0` output."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        run = lambda *a: subprocess.run(["git", "-C", self.tmp] + list(a), check=True, capture_output=True)
        run("init", "-q")
        run("config", "user.email", "t@t")
        run("config", "user.name", "t")
        path = os.path.join(self.tmp, "f.txt")
        with open(path, "w") as fh:
            fh.write("".join("line%d\n" % i for i in range(1, 21)))
        run("add", "-A")
        run("commit", "-qm", "old")
        self.old = subprocess.check_output(["git", "-C", self.tmp, "rev-parse", "HEAD"]).decode().strip()
        lines = ["line%d\n" % i for i in range(1, 21)]
        lines.insert(2, "added-a\nadded-b\n")   # 2 lines inserted after old line 2
        del lines[10]                          # old line 10 deleted
        lines[15] = "changed16\n"              # old line 16 changed in place
        with open(path, "w") as fh:
            fh.write("".join(lines))
        run("commit", "-qam", "new")
        self.new = subprocess.check_output(["git", "-C", self.tmp, "rev-parse", "HEAD"]).decode().strip()

    def m(self, ln):
        return sorted(harness.map_new_to_old(self.tmp, self.old, self.new, "f.txt", {ln}))

    def test_before_any_hunk(self):
        self.assertEqual(self.m(1), [1])

    def test_after_insertion_shifts_back(self):
        self.assertEqual(self.m(6), [4])

    def test_inside_insertion_maps_to_anchor(self):
        self.assertEqual(self.m(3), [2])

    def test_after_deletion_and_insertion(self):
        self.assertEqual(self.m(12), [11])

    def test_changed_line(self):
        self.assertEqual(self.m(17), [16])


if __name__ == "__main__":
    unittest.main(verbosity=2)

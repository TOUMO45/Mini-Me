"""Tests for mini_me.py. Run: python3 -m unittest discover -s skills/mini-me/scripts"""
from __future__ import annotations

import contextlib
import datetime as dt
import io
import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import mini_me  # noqa: E402

TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "profile.template.md"
TODAY = dt.date(2026, 11, 11)


def record(rid="rule-001", typ="Decision rule", **overrides):
    fields = {
        "Condition": "When a client proposal's scope will change a lot",
        "Action": "Lead with time-and-materials",
        "Scope": "Client proposals",
        "Evidence": '"Hallam\'s scope is going to move a lot"',
        "Sources": "chat-2026-09-14",
        "Reason": "Scope volatility",
        "Status": "confirmed",
        "Source date": "2026-09-14",
        "Updated": "2026-09-14",
        "Supersedes": "—",
        "Sensitivity": "ordinary",
    }
    fields.update(overrides)
    body = "\n".join(f"- {k}: {v}" for k, v in fields.items() if v is not None)
    return f"### {rid} · {typ}\n{body}\n"


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "profile.md"

    def tearDown(self):
        self.dir.cleanup()

    def write(self, *records):
        self.path.write_text("# Mini Me profile\n\n## Records\n\n" + "\n".join(records), encoding="utf-8")

    def findings(self, *records):
        self.write(*records)
        return mini_me.validate(mini_me.parse(self.path), today=TODAY)

    def errors(self, *records):
        return [f.message for f in self.findings(*records) if f.level == "error"]

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = mini_me.main(["--profile", str(self.path), *argv])
        return code, out.getvalue(), err.getvalue()


class TestValidate(Base):
    def test_template_is_valid(self):
        profile = mini_me.parse(TEMPLATE)
        self.assertEqual(len(profile.records), 1)
        self.assertEqual([f for f in mini_me.validate(profile, TODAY) if f.level == "error"], [])

    def test_valid_record(self):
        self.assertEqual(self.errors(record()), [])

    def test_likely_needs_two_sources(self):
        errs = self.errors(record(Status="likely"))
        self.assertTrue(any("2+ independent sources" in e for e in errs))
        self.assertEqual(self.errors(record(Status="likely", Sources="chat-a, chat-b")), [])

    def test_duplicate_source_ids_count_once(self):
        errs = self.errors(record(Status="likely", Sources="chat-a; chat-a"))
        self.assertTrue(any("has 1" in e for e in errs))

    def test_password_rejected_without_echo(self):
        findings = self.findings(record(Evidence="the drive password is hunter2"))
        msgs = [str(f) for f in findings if f.level == "error"]
        self.assertTrue(any("password" in m for m in msgs))
        self.assertFalse(any("hunter2" in m for m in msgs))

    def test_password_prose_not_flagged(self):
        self.assertEqual(self.errors(record(Condition="When a password is required for the portal")), [])

    def test_token_shapes_rejected(self):
        for value in ("ghp_" + "a" * 36, "AKIA" + "A" * 16, "sk-" + "b" * 32, "api_key = abcdef1234567890"):
            with self.subTest(value=value):
                self.assertTrue(self.errors(record(Evidence=value)))

    def test_duplicate_ids(self):
        errs = self.errors(record(), record(Condition="Other", Sources="x"))
        self.assertTrue(any("duplicate ID" in e for e in errs))

    def test_prefix_must_match_type(self):
        errs = self.errors(record(rid="pref-001", typ="Decision rule"))
        self.assertTrue(any("does not match type" in e for e in errs))

    def test_missing_required_field(self):
        errs = self.errors(record(Scope=None))
        self.assertTrue(any("'Scope'" in e for e in errs))

    def test_reason_unknown_is_allowed(self):
        self.assertEqual(self.errors(record(Reason="unknown")), [])

    def test_bad_status(self):
        self.assertTrue(self.errors(record(Status="definitely")))

    def test_exception_needs_expiry_and_warns_when_expired(self):
        self.assertTrue(any("Expires" in e for e in self.errors(record(rid="exc-001", typ="Exception"))))
        findings = self.findings(record(rid="exc-001", typ="Exception", Expires="2026-10-02"))
        self.assertTrue(any(f.level == "warning" and "expired" in f.message for f in findings))
        self.assertFalse([f for f in findings if f.level == "error"])

    def test_sensitive_needs_purpose_and_confirmation(self):
        errs = self.errors(record(rid="sens-001", typ="Sensitive constraint", Sensitivity="sensitive", Status="tentative"))
        self.assertTrue(any("Purpose" in e for e in errs))
        self.assertTrue(any("confirmed" in e for e in errs))
        ok = record(rid="sens-001", typ="Sensitive constraint", Sensitivity="sensitive", Purpose="Scheduling meetings")
        self.assertEqual(self.errors(ok), [])

    def test_supersedes_must_point_to_superseded_record(self):
        old = record()
        new = record(rid="rule-002", Action="Lead with fixed fee", Sources="chat-b", Supersedes="rule-001")
        self.assertTrue(any("Set it to 'superseded'" in e for e in self.errors(old, new)))
        self.assertEqual(self.errors(record(Status="superseded"), new), [])
        self.assertTrue(any("unknown record" in e for e in self.errors(new)))

    def test_same_source_same_decision_is_duplicate(self):
        errs = self.errors(record(), record(rid="rule-002"))
        self.assertTrue(any("duplicates rule-001" in e for e in errs))

    def test_dates(self):
        self.assertTrue(self.errors(record(Updated="Sept 14")))
        self.assertTrue(any("earlier" in e for e in self.errors(record(Updated="2026-09-01"))))

    def test_project_state_fields(self):
        proj = record(rid="proj-001", typ="Project state", Condition=None, Action=None, Scope=None,
                      Project="Borealis", **{"Latest version": "v2", "Last decision": "Vendor B", "Next step": "Week 4"})
        self.assertEqual(self.errors(proj), [])

    def test_wrapped_field_lines_and_comments(self):
        self.path.write_text(textwrap.dedent("""\
            # Profile
            <!--
            ### rule-999 · Decision rule
            -->
            ### rule-001 · Decision rule
            """) + record()[len("### rule-001 · Decision rule\n"):].replace(
            "- Action: Lead with time-and-materials", "- Action: Lead with\n  time-and-materials"), encoding="utf-8")
        profile = mini_me.parse(self.path)
        self.assertEqual([r.id for r in profile.records], ["rule-001"])
        self.assertEqual(profile.records[0].get("Action"), "Lead with time-and-materials")


class TestCommands(Base):
    def test_validate_exit_codes(self):
        self.write(record())
        self.assertEqual(self.run_cli("validate")[0], 0)
        self.write(record(Status="likely"))
        self.assertEqual(self.run_cli("validate")[0], 1)

    def test_missing_profile(self):
        self.assertEqual(self.run_cli("validate")[0], 2)

    def test_next_id(self):
        self.write(record(), record(rid="rule-007", Sources="x"))
        self.assertEqual(self.run_cli("next-id", "rule")[1].strip(), "rule-008")
        self.assertEqual(self.run_cli("next-id", "preference")[1].strip(), "pref-001")

    def test_show_separates_inferred_and_hides_inactive(self):
        self.write(
            record(),
            record(rid="pref-001", typ="Preference", Status="tentative", Sources="s2", Action="Sign as Sam"),
            record(rid="rule-002", Status="superseded", Sources="old", Action="Old way"),
        )
        _, out, _ = self.run_cli("show")
        self.assertIn("## Stated by you", out)
        self.assertIn("## Inferred", out)
        self.assertLess(out.index("rule-001"), out.index("## Inferred"))
        self.assertGreater(out.index("pref-001"), out.index("## Inferred"))
        self.assertNotIn("rule-002", out)
        self.assertIn("rule-002", self.run_cli("show", "--include-inactive")[1])

    def test_show_keeps_third_party_out_of_stated_by_you(self):
        self.write(record(), record(rid="pref-001", typ="Preference", Sources="s3",
                                    Action="Use bullets", **{"Said by": "Lena (manager)"}))
        _, out, _ = self.run_cli("show")
        stated = out[out.index("## Stated by you"):out.index("## Said by others")]
        self.assertIn("rule-001", stated)
        self.assertNotIn("pref-001", stated)
        self.assertIn("pref-001", out[out.index("## Said by others"):])

    def test_export_strips_private_fields_and_sensitive(self):
        self.write(record(), record(rid="sens-001", typ="Sensitive constraint", Sensitivity="sensitive",
                                    Purpose="Scheduling", Sources="s9"))
        _, out, _ = self.run_cli("export")
        self.assertIn("Snapshot taken", out)
        self.assertIn("rule-001", out)
        self.assertNotIn("Evidence", out)
        self.assertNotIn("sens-001", out)
        _, full, _ = self.run_cli("export", "--include-sources", "--include-sensitive")
        self.assertIn("Evidence", full)
        self.assertIn("sens-001", full)

    def test_forget_removes_record_and_reference(self):
        self.write(record(Status="superseded"), record(rid="rule-002", Sources="b", Action="New", Supersedes="rule-001"))
        code, out, _ = self.run_cli("forget", "rule-001")
        self.assertEqual(code, 0, out)
        profile = mini_me.parse(self.path)
        self.assertEqual([r.id for r in profile.records], ["rule-002"])
        self.assertEqual(profile.records[0].get("Supersedes"), "—")
        self.assertIn("Not reached", out)
        self.assertEqual(self.run_cli("validate")[0], 0)

    def test_forget_refuses_concurrent_change(self):
        self.write(record())
        profile = mini_me.parse(self.path)
        self.path.write_text(self.path.read_text() + "\n" + record(rid="rule-002", Sources="other"))
        with self.assertRaises(mini_me.MiniMeError):
            mini_me.atomic_write(self.path, "x", profile.digest)
        self.assertIn("rule-002", self.path.read_text())

    def test_env_var_profile(self):
        self.write(record())
        old = os.environ.get("MINI_ME_PROFILE")
        os.environ["MINI_ME_PROFILE"] = str(self.path)
        try:
            self.assertEqual(mini_me.resolve_path(None), self.path)
        finally:
            if old is None:
                del os.environ["MINI_ME_PROFILE"]
            else:
                os.environ["MINI_ME_PROFILE"] = old


if __name__ == "__main__":
    unittest.main()


S4 = Path(__file__).resolve().parents[3] / "eval" / "scenarios" / "s4-large-profile" / "profile.md"
S4_BRIEF = ("draft the proposal for Halden Shipping, a new client. Scope is fixed and well-defined: a 6-week "
            "route-planning audit. Their procurement team will review it before signing.")


@unittest.skipUnless(S4.exists(), "S4 fixture not present")
class TestRecallS4(unittest.TestCase):
    """Regression: recall must surface every relevant record and every trap in the 61-record profile."""

    def setUp(self):
        self.d = mini_me.recall_data(mini_me.parse(S4), S4_BRIEF, today=TODAY)
        self.ids = {x["id"] for g in self.d["groups"].values() for x in g}

    def test_finds_all_relevant_rules(self):
        for rid in ("rule-011", "rule-014", "pref-004", "pref-021", "pref-009", "pref-017"):
            self.assertIn(rid, self.ids)

    def test_flags_traps(self):
        excluded = {e["id"]: e["why"] for e in self.d["excluded"]}
        self.assertIn("superseded by rule-011", excluded.get("rule-003", ""))
        self.assertIn("expired", excluded.get("exc-002", ""))
        self.assertNotIn("rule-003", self.ids)
        self.assertNotIn("exc-002", self.ids)

    def test_resolves_conflict_to_latest_explicit_correction(self):
        found = [c for c in self.d["conflicts"] if set(c["records"]) == {"pref-009", "pref-021"}]
        self.assertEqual(len(found), 1)
        self.assertEqual((found[0]["use"], found[0]["why"]), ("pref-021", "confirmed, 2026-10-22"))

    def test_tentative_records_are_marked(self):
        inferred = {x["id"] for x in self.d["groups"]["inferred"]}
        self.assertTrue({"pref-009", "pref-017"} <= inferred)

    def test_much_smaller_than_profile(self):
        text = mini_me.recall_text(mini_me.parse(S4), S4_BRIEF, today=TODAY)
        self.assertLess(len(text), S4.stat().st_size / 5)

    def test_other_client_record_is_not_in_apply(self):
        profile = mini_me.parse(Path(__file__).resolve().parents[3] / "eval" / "scenarios" / "s3-corrected-rule" / "profile.md")
        d = mini_me.recall_data(profile, "Landing-page design directions for Fjord Health, a new client", today=TODAY)
        elsewhere = {x["id"] for x in d["groups"]["elsewhere"]}
        applied = {x["id"] for x in d["groups"]["stated"] + d["groups"]["inferred"]}
        self.assertIn("pref-001", elsewhere)
        self.assertNotIn("pref-001", applied)
        self.assertIn("rule-002", applied)
        terse = mini_me.recall_data(profile, "Landing-page design directions for Fjord Health: calm, light, sans-serif",
                                    today=TODAY)
        self.assertIn("rule-002", {x["id"] for x in terse["groups"]["stated"]})
        self.assertIn("rule-001", {e["id"] for e in terse["excluded"]})
        same = mini_me.recall_data(profile, "Landing page for Kestrel Coffee", today=TODAY)
        self.assertIn("pref-001", {x["id"] for x in same["groups"]["stated"]})

    def test_unrelated_brief_matches_little(self):
        d = mini_me.recall_data(mini_me.parse(S4), "plan my grocery shopping list", today=TODAY)
        self.assertLessEqual(d["matched"], 2)


class TestAdd(Base):
    BASE = dict(Type="pref", Condition="When writing a client proposal", Action="Include a three-tier pricing table",
                Scope="Client proposals", Evidence='"three tiers please"', Sources="chat-a")

    def add(self, **kw):
        return mini_me.add_record(self.path, {**self.BASE, **kw}, today=TODAY)

    def test_creates_profile_and_record_with_defaults(self):
        msg = self.add()
        self.assertIn("Added pref-001", msg)
        r = mini_me.parse(self.path).records[0]
        self.assertEqual((r.status, r.get("Reason"), r.get("Updated")), ("tentative", "unknown", "2026-11-11"))
        self.assertEqual(self.run_cli("validate")[0], 0)

    def test_same_source_is_idempotent(self):
        self.add()
        self.assertIn("Already recorded as pref-001", self.add())
        self.assertEqual(len(mini_me.parse(self.path).records), 1)

    def test_second_source_promotes_to_likely(self):
        self.add()
        msg = self.add(Sources="chat-b", Evidence='"tiers again"')
        self.assertIn("tentative → likely", msg)
        r = mini_me.parse(self.path).records[0]
        self.assertEqual(r.status, "likely")
        self.assertEqual(r.sources(), ["chat-a", "chat-b"])
        self.assertIn("tiers again", r.get("Evidence"))

    def test_explicit_statement_upgrades_to_confirmed_and_fills_reason(self):
        self.add()
        self.add(Sources="chat-c", Status="confirmed", Reason="Buyers compare options")
        r = mini_me.parse(self.path).records[0]
        self.assertEqual((r.status, r.get("Reason")), ("confirmed", "Buyers compare options"))

    def test_supersedes_marks_old_record(self):
        self.add(Status="confirmed")
        msg = self.add(Action="Include a two-tier pricing table", Sources="chat-z", Status="confirmed", Supersedes="pref-001")
        self.assertIn("Added pref-002", msg)
        recs = mini_me.parse(self.path).by_id()
        self.assertEqual(recs["pref-001"].status, "superseded")
        self.assertEqual(self.run_cli("validate")[0], 0)

    def test_rejects_secret_and_leaves_file_untouched(self):
        self.add()
        before = self.path.read_text()
        with self.assertRaises(mini_me.MiniMeError):
            self.add(Condition="When logging in", Evidence="password is hunter2", Sources="chat-q")
        self.assertEqual(self.path.read_text(), before)

    def test_rejects_likely_on_one_source(self):
        with self.assertRaises(mini_me.MiniMeError):
            self.add(Status="likely")
        self.assertFalse(self.path.exists())

    def test_unknown_type_and_supersedes(self):
        with self.assertRaises(mini_me.MiniMeError):
            self.add(Type="vibe")
        self.add()
        with self.assertRaises(mini_me.MiniMeError):
            self.add(Sources="x", Action="other", Supersedes="pref-999")

    def test_cli_add_flags(self):
        code, out, err = self.run_cli("add", "--type", "exc", "--condition", "When emailing Acme today",
                                      "--action", "cc Priya", "--scope", "Acme", "--evidence", '"cc Priya today"',
                                      "--sources", "chat-1", "--status", "confirmed", "--expires", "2026-11-11")
        self.assertEqual(code, 0, err)
        self.assertIn("Added exc-001", out)


class TestReviewAndInit(Base):
    def test_review_suggests_without_applying(self):
        self.write(
            record(rid="pref-001", typ="Preference", Action="Put all case studies at the end", Status="tentative",
                   Sources="a", **{"Source date": "2026-01-01", "Updated": "2026-01-01"}),
            record(rid="pref-002", typ="Preference", Action="Put one case study after the summary", Sources="b"),
            record(rid="exc-001", typ="Exception", Sources="c", Action="Discount", Expires="2026-10-31"),
        )
        before = self.path.read_text()
        out = mini_me.review_text(mini_me.parse(self.path), today=TODAY)
        self.assertIn("Conflict pref-001 vs pref-002", out)
        self.assertIn("Retire exc-001", out)
        self.assertIn("Check pref-001", out)
        self.assertEqual(self.path.read_text(), before)

    def test_review_clean(self):
        self.write(record())
        self.assertIn("Nothing to review", mini_me.review_text(mini_me.parse(self.path), today=TODAY))

    def test_init_creates_private_file_and_refuses_overwrite(self):
        code, out, _ = self.run_cli("init")
        self.assertEqual(code, 0)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.run_cli("init")[0], 1)

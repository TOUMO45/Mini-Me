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
        with self.assertRaises(RuntimeError):
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

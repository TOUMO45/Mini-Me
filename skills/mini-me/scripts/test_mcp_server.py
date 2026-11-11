"""End-to-end test of the MCP server over a real stdio subprocess."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SERVER = Path(__file__).resolve().parent / "mcp_server.py"


class TestMCP(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.profile = Path(self.tmp.name) / "profile.md"

    def tearDown(self):
        self.tmp.cleanup()

    def session(self, *messages):
        """Run one server process, send every message, return replies keyed by id."""
        payload = "\n".join(json.dumps(m) for m in messages) + "\n"
        proc = subprocess.run([sys.executable, str(SERVER), "--profile", str(self.profile)], input=payload,
                              capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        replies = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
        return {r.get("id"): r for r in replies}

    def call(self, mid, name, args):
        return {"jsonrpc": "2.0", "id": mid, "method": "tools/call", "params": {"name": name, "arguments": args}}

    def text(self, reply):
        return reply["result"]["content"][0]["text"]

    def test_handshake_and_tool_list(self):
        r = self.session(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "ping"},
        )
        self.assertEqual(r[1]["result"]["protocolVersion"], "2025-06-18")
        self.assertEqual(r[1]["result"]["serverInfo"]["name"], "mini-me")
        names = {t["name"] for t in r[2]["result"]["tools"]}
        self.assertTrue({"mini_me_recall", "mini_me_add", "mini_me_forget"} <= names)
        self.assertEqual(r[3]["result"], {})
        self.assertEqual(len(r), 3)  # the notification gets no reply

    def test_learn_then_recall_then_forget(self):
        rule = {"type": "rule", "condition": "When writing a client proposal with a fixed scope",
                "action": "Lead with the fixed-fee option", "scope": "Client proposals",
                "evidence": '"Fixed scope, fixed fee first."', "sources": "chat-1", "status": "confirmed",
                "reason": "T&M on fixed scope looks evasive"}
        r = self.session(
            self.call(1, "mini_me_add", rule),
            self.call(2, "mini_me_add", rule),
            self.call(3, "mini_me_recall", {"brief": "Draft a proposal for a new client, fixed scope audit"}),
            self.call(4, "mini_me_forget", {"id": "rule-001"}),
            self.call(5, "mini_me_show", {}),
        )
        self.assertIn("Added rule-001", self.text(r[1]))
        self.assertIn("Already recorded", self.text(r[2]))
        self.assertIn("rule-001", self.text(r[3]))
        self.assertIn("Lead with the fixed-fee option", self.text(r[3]))
        self.assertIn("Removed rule-001", self.text(r[4]))
        self.assertIn("No matching", self.text(r[5]))

    def test_errors_are_tool_errors_not_crashes(self):
        r = self.session(
            self.call(1, "mini_me_recall", {"brief": "anything"}),
            self.call(2, "mini_me_add", {"type": "pref", "condition": "c", "action": "a", "scope": "s",
                                         "evidence": "the password is hunter2", "sources": "x"}),
            self.call(3, "no_such_tool", {}),
            {"jsonrpc": "2.0", "id": 4, "method": "bogus"},
        )
        self.assertTrue(r[1]["result"]["isError"])
        self.assertIn("no profile", self.text(r[1]))
        self.assertTrue(r[2]["result"]["isError"])
        self.assertNotIn("hunter2", self.text(r[2]))
        self.assertFalse(self.profile.exists())
        self.assertEqual(r[3]["error"]["code"], -32602)
        self.assertEqual(r[4]["error"]["code"], -32601)

    def test_bad_json_line(self):
        proc = subprocess.run([sys.executable, str(SERVER), "--profile", str(self.profile)], input="{not json\n",
                              capture_output=True, text=True, timeout=30)
        self.assertEqual(json.loads(proc.stdout)["error"]["code"], -32700)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Kamari Fatima Zuhra. See LICENSE.
"""Mini Me MCP server: exposes the profile engine as tools to any MCP-capable agent.

Transport: stdio, newline-delimited JSON-RPC 2.0. Stdlib only.
Profile: --profile PATH, else $MINI_ME_PROFILE, else ~/.mini-me/profile.md.

Example client config (Claude Desktop, Cursor, and others):
  {"mcpServers": {"mini-me": {"command": "python3",
    "args": ["/abs/path/skills/mini-me/scripts/mcp_server.py"],
    "env": {"MINI_ME_PROFILE": "/abs/path/.mini-me/profile.md"}}}}
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mini_me as mm  # noqa: E402

PROTOCOL_VERSIONS = ["2025-06-18", "2025-03-26", "2024-11-05"]

FIELD_PROPS = {
    "type": {"type": "string", "enum": sorted(mm.TYPES), "description": "Record type prefix"},
    "condition": {"type": "string", "description": "When this applies: 'When …'"},
    "action": {"type": "string", "description": "What to do"},
    "scope": {"type": "string", "description": "The work, client, or audience it is limited to"},
    "evidence": {"type": "string", "description": "Short quote or observable edit. Never a password or key"},
    "sources": {"type": "string", "description": "Comma-separated source IDs. One conversation = one ID"},
    "reason": {"type": "string", "description": "The user's stated reason, or 'unknown'"},
    "status": {"type": "string", "enum": ["confirmed", "likely", "tentative"],
               "description": "confirmed = user said it; tentative = one example. Defaults to tentative"},
    "said_by": {"type": "string", "description": "Who said it, when not the user"},
    "expires": {"type": "string", "description": "For exc: a date (YYYY-MM-DD) or scope end"},
    "purpose": {"type": "string", "description": "For sens: the purpose the user stated"},
    "supersedes": {"type": "string", "description": "ID(s) this record replaces"},
    "exceptions": {"type": "string"},
    "project": {"type": "string", "description": "For proj"},
    "constraints": {"type": "string", "description": "For proj: the client's stated requirements"},
    "latest_version": {"type": "string", "description": "For proj"},
    "last_decision": {"type": "string", "description": "For proj"},
    "completed": {"type": "string", "description": "For proj"},
    "next_step": {"type": "string", "description": "For proj"},
    "question": {"type": "string", "description": "For dec: the decision being made"},
    "options": {"type": "string", "description": "For dec: the options, separated by ';'"},
    "choice": {"type": "string", "description": "For dec: what the user chose. Omit to log a prediction only"},
    "predicted": {"type": "string", "description": "For dec: Mini Me's prediction, logged before the user decides"},
}

TOOLS = [
    {
        "name": "mini_me_recall",
        "description": ("Call FIRST on any task the user wants done their way. Returns only the records relevant to "
                        "the brief: rules to apply, inferred ones to flag, others' constraints, resolved conflicts, "
                        "and superseded or expired records to avoid."),
        "inputSchema": {"type": "object", "required": ["brief"], "properties": {
            "brief": {"type": "string", "description": "Today's task: deliverable, audience, client, constraints"},
            "k": {"type": "integer", "minimum": 1, "maximum": 50, "default": 8}}},
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "mini_me_add",
        "description": ("Record what was learned: a correction, a stated preference, a one-off exception, or project "
                        "state. Merges duplicates, and promotes tentative records to likely when a second "
                        "independent source agrees. Refuses invalid records and anything that looks like a credential."),
        "inputSchema": {"type": "object", "required": ["type", "evidence", "sources"], "properties": FIELD_PROPS},
        "annotations": {"destructiveHint": False, "idempotentHint": True},
    },
    {
        "name": "mini_me_choose",
        "description": ("Record the choice the user actually made on a decision (dec- record). Keeps the earlier "
                        "prediction, reports whether it was right, and updates the track record."),
        "inputSchema": {"type": "object", "required": ["id", "choice"], "properties": {
            "id": {"type": "string"}, "choice": {"type": "string"}, "reason": {"type": "string"},
            "evidence": {"type": "string"}, "sources": {"type": "string"}}},
        "annotations": {"destructiveHint": False},
    },
    {
        "name": "mini_me_explain",
        "description": "Answer 'why did you do that?': one record in plain language, with its reason, confidence, evidence, and what it replaced.",
        "inputSchema": {"type": "object", "required": ["id"], "properties": {"id": {"type": "string"}}},
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "mini_me_history",
        "description": "Answer 'what did I decide before?': a timeline of decisions, lessons, and corrections, newest first.",
        "inputSchema": {"type": "object", "properties": {
            "project": {"type": "string"}, "since": {"type": "string", "description": "YYYY-MM-DD"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 30}}},
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "mini_me_stats",
        "description": "Rules by confidence, how many have a known reason, open decisions, and the prediction track record.",
        "inputSchema": {"type": "object", "properties": {}},
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "mini_me_show",
        "description": "Answer 'what have you learned about me?': active records grouped as stated, inferred, said by others.",
        "inputSchema": {"type": "object", "properties": {
            "type": {"type": "string"}, "project": {"type": "string"}, "query": {"type": "string"},
            "include_inactive": {"type": "boolean", "default": False}}},
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "mini_me_review",
        "description": "Suggest maintenance: promotions, merges, conflicts, expired exceptions, stale guesses. Applies nothing.",
        "inputSchema": {"type": "object", "properties": {}},
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "mini_me_export",
        "description": "A dated snapshot of working preferences for another agent. Evidence and sensitive records are left out unless requested.",
        "inputSchema": {"type": "object", "properties": {
            "include_sources": {"type": "boolean", "default": False},
            "include_sensitive": {"type": "boolean", "default": False}}},
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "mini_me_forget",
        "description": "Permanently remove one record and references to it. Only when the user asks to forget it.",
        "inputSchema": {"type": "object", "required": ["id"], "properties": {"id": {"type": "string"}}},
        "annotations": {"destructiveHint": True},
    },
    {
        "name": "mini_me_validate",
        "description": "Check the whole profile for errors.",
        "inputSchema": {"type": "object", "properties": {}},
        "annotations": {"readOnlyHint": True},
    },
]


class Server:
    def __init__(self, profile: Path):
        self.profile = profile

    def load(self) -> mm.Profile:
        if not self.profile.exists():
            raise mm.MiniMeError(f"no profile at {self.profile}. Create one with `mini_me.py init`")
        return mm.parse(self.profile)

    def call(self, name: str, a: dict) -> str:
        if name == "mini_me_recall":
            return mm.recall_text(self.load(), str(a["brief"]), int(a.get("k", 8)))
        if name == "mini_me_add":
            fields = {k: v for k, v in a.items() if k in FIELD_PROPS}
            mapped = {dict((f, key) for f, key in mm.ADD_FLAGS).get(k, k): v for k, v in fields.items()}
            mapped["Type"] = mapped.pop("type")
            return mm.add_record(self.profile, mapped)
        if name == "mini_me_choose":
            return mm.choose_record(self.profile, str(a["id"]), str(a["choice"]), a.get("reason"), a.get("evidence"),
                                    a.get("sources"))
        if name == "mini_me_explain":
            return mm.explain_text(self.load(), str(a["id"]))
        if name == "mini_me_history":
            return mm.history_text(self.load(), project=a.get("project"), since=a.get("since"), limit=int(a.get("limit", 30)))
        if name == "mini_me_stats":
            return mm.stats_text(self.load())
        if name == "mini_me_show":
            return mm.show_text(self.load(), rtype=a.get("type"), project=a.get("project"), query=a.get("query"),
                                include_inactive=bool(a.get("include_inactive")))
        if name == "mini_me_review":
            return mm.review_text(self.load())
        if name == "mini_me_export":
            return mm.export_text(self.load(), include_sources=bool(a.get("include_sources")),
                                  include_sensitive=bool(a.get("include_sensitive")))[0]
        if name == "mini_me_forget":
            return mm.forget_record(self.profile, str(a["id"]))
        if name == "mini_me_validate":
            return mm.validate_text(self.load())[0]
        raise KeyError(name)

    def handle(self, msg: dict) -> dict | None:
        mid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
        if mid is None:  # notification, e.g. notifications/initialized
            return None
        try:
            if method == "initialize":
                asked = params.get("protocolVersion")
                return ok(mid, {
                    "protocolVersion": asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0],
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "mini-me", "version": mm.__version__},
                    "instructions": ("Mini Me holds the user's working rules and past decisions. Call mini_me_recall with "
                                     "today's brief before producing work the user wants done their way. Apply records only "
                                     "within their scope; use precedents and the prediction track record for 'which would I "
                                     "choose?'. After a correction, call mini_me_add; after the user decides, mini_me_choose."),
                })
            if method == "ping":
                return ok(mid, {})
            if method == "tools/list":
                return ok(mid, {"tools": TOOLS})
            if method == "tools/call":
                name = params.get("name")
                if name not in {t["name"] for t in TOOLS}:
                    return err(mid, -32602, f"unknown tool '{name}'")
                try:
                    text, is_error = self.call(name, params.get("arguments") or {}), False
                except (mm.MiniMeError, KeyError, ValueError, TypeError) as exc:
                    text, is_error = f"Error: {exc}", True
                return ok(mid, {"content": [{"type": "text", "text": text}], "isError": is_error})
            return err(mid, -32601, f"method not found: {method}")
        except Exception as exc:  # never crash the transport
            return err(mid, -32603, f"internal error: {exc}")


def ok(mid, result):
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def err(mid, code, message):
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    profile = mm.resolve_path(argv[argv.index("--profile") + 1] if "--profile" in argv else None)
    server = Server(profile)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            reply = err(None, -32700, "parse error")
        else:
            reply = server.handle(msg) if isinstance(msg, dict) else err(None, -32600, "invalid request")
        if reply is not None:
            sys.stdout.write(json.dumps(reply) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Kamari Fatima Zuhra. See LICENSE.
"""Mini Me profile engine: recall, add, choose, explain, history, stats, review, show, export, forget, validate, next-id, init.

Stdlib only. The profile is a private Markdown file (see references/profile-format.md).
Path resolution: --profile, then $MINI_ME_PROFILE, then ~/.mini-me/profile.md.
Every command is also available as a function returning text, so scripts/mcp_server.py
can expose the same behavior to any MCP-capable agent.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import re
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

__version__ = "2.2.1"

TYPES = {
    "goal": "Goal",
    "pref": "Preference",
    "rule": "Decision rule",
    "method": "Problem-solving method",
    "exc": "Exception",
    "sens": "Sensitive constraint",
    "proj": "Project state",
    "dec": "Decision",
}
TYPE_ALIASES = {
    "goal": "goal",
    "preference": "pref",
    "decision rule": "rule",
    "problem-solving method": "method",
    "method": "method",
    "exception": "exc",
    "exception or experiment": "exc",
    "experiment": "exc",
    "sensitive constraint": "sens",
    "sensitive personal constraint": "sens",
    "project state": "proj",
    "decision": "dec",
}
STATUSES = {"confirmed", "likely", "tentative", "superseded"}
STATUS_RANK = {"tentative": 0, "likely": 1, "confirmed": 2}
INFERRED = {"likely", "tentative"}
SENSITIVITY = {"ordinary", "sensitive"}
COMMON_REQUIRED = ["Evidence", "Sources", "Reason", "Status", "Source date", "Updated", "Sensitivity"]
RULE_REQUIRED = ["Condition", "Action", "Scope"]
NON_RULE = {"proj", "dec"}  # record types that are not condition → action rules
PENDING = {"pending", "", "—", "-", "open"}
EXTRA_REQUIRED = {
    "exc": ["Expires"],
    "sens": ["Purpose"],
    "proj": ["Project", "Latest version", "Last decision", "Next step"],
    "dec": ["Question", "Options", "Choice"],
}
FIELD_ORDER = [
    "Question", "Options", "Choice", "Predicted", "Said by", "Project", "Constraints", "Latest version", "Last decision", "Completed", "Next step",
    "Condition", "Action", "Scope", "Exceptions", "Expires", "Purpose", "Evidence", "Sources", "Reason",
    "Status", "Source date", "Updated", "Supersedes", "Sensitivity",
]
PRIVATE_FIELDS = {"Evidence", "Sources"}
EMPTY = {"", "—", "-", "none", "n/a"}
SELF = {"", "user", "the user", "me", "self", "—", "-"}

HEADING_RE = re.compile(r"^###\s+(?P<id>\S+)\s+[·\-–|]\s+(?P<type>.+?)\s*$")
FIELD_RE = re.compile(r"^-\s+(?P<key>[A-Za-z][A-Za-z \-]*?)\s*:\s*(?P<value>.*)$")
ID_RE = re.compile(r"^(?P<prefix>[a-z]+)-(?P<num>\d{3,})$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Shapes of credentials that must never be stored. Reported by line, never echoed.
SECRET_PATTERNS = [
    ("password assignment", re.compile(
        r"(?i)\b(pass(word|wd)?|pwd)\b\s*(is|=|:)\s*"
        r"(?!(required|needed|missing|optional|reset|stored|changed|rotated|expired|wrong|incorrect|"
        r"the|a|an|not|never|always|only|in|on|at|for|to|from|set|managed|kept)\b)\S+")),
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("API key", re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}\b")),
    ("Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}\b")),
    ("bearer token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9\-_.=]{20,}")),
    ("API key assignment", re.compile(r"(?i)\b(api[_\- ]?key|secret|token)\b\s*(is|=|:)\s*[A-Za-z0-9\-_.]{12,}")),
]


class MiniMeError(Exception):
    """A user-facing failure: bad input, a validation error, or a concurrent edit."""


# --------------------------------------------------------------------------- parsing

@dataclass
class Record:
    id: str
    type_label: str
    line: int  # 1-based heading line
    fields: dict[str, str] = field(default_factory=dict)
    end_line: int = 0  # exclusive, 0-based index into lines

    @property
    def prefix(self) -> str:
        m = ID_RE.match(self.id)
        return m.group("prefix") if m else (type_prefix(self.type_label) or "")

    @property
    def status(self) -> str:
        return self.fields.get("Status", "").strip().lower()

    def get(self, key: str) -> str:
        return self.fields.get(key, "").strip()

    def sources(self) -> list[str]:
        out: list[str] = []
        for s in re.split(r"[,;]", self.get("Sources")):
            s = s.strip()
            if s.lower() not in EMPTY and s.lower() not in {x.lower() for x in out}:
                out.append(s)
        return out

    def date(self) -> dt.date:
        return parse_date(self.get("Updated")) or parse_date(self.get("Source date")) or dt.date.min


@dataclass
class Profile:
    path: Path
    text: str
    lines: list[str]
    records: list[Record]

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.text.encode()).hexdigest()

    def by_id(self) -> dict[str, Record]:
        out: dict[str, Record] = {}
        for r in self.records:
            out.setdefault(r.id, r)
        return out


def resolve_path(arg: str | None) -> Path:
    if arg:
        return Path(arg).expanduser()
    env = os.environ.get("MINI_ME_PROFILE")
    if env:
        return Path(env).expanduser()
    return Path("~/.mini-me/profile.md").expanduser()


def parse(path: Path) -> Profile:
    return parse_text(path.read_text(encoding="utf-8"), path)


def parse_text(text: str, path: Path) -> Profile:
    lines = text.splitlines()
    records: list[Record] = []
    current: Record | None = None
    last_key: str | None = None
    in_comment = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if in_comment:
            if "-->" in stripped:
                in_comment = False
            continue
        if stripped.startswith("<!--") and "-->" not in stripped:
            in_comment = True
            continue
        m = HEADING_RE.match(stripped)
        if m:
            if current:
                current.end_line = i
            current = Record(id=m.group("id"), type_label=m.group("type").strip(), line=i + 1)
            records.append(current)
            last_key = None
            continue
        if stripped.startswith("#"):
            if current:
                current.end_line = i
            current = None
            last_key = None
            continue
        if current is None:
            continue
        fm = FIELD_RE.match(stripped)
        if fm:
            key = normalize_key(fm.group("key"))
            current.fields[key] = fm.group("value").strip()
            last_key = key
        elif stripped and last_key and line.startswith((" ", "\t")):
            current.fields[last_key] += " " + stripped  # wrapped continuation line
    if current:
        current.end_line = len(lines)
    # Trim trailing blank lines from each record's span.
    for r in records:
        while r.end_line > r.line and not lines[r.end_line - 1].strip():
            r.end_line -= 1
    return Profile(path=path, text=text, lines=lines, records=records)


def normalize_key(key: str) -> str:
    key = " ".join(key.split())
    return key[:1].upper() + key[1:].lower()


def type_prefix(label: str) -> str | None:
    label = label.strip().lower()
    if label in TYPES:
        return label
    return TYPE_ALIASES.get(label)


def is_empty(value: str) -> bool:
    return value.strip().lower() in EMPTY


def parse_date(value: str) -> dt.date | None:
    value = value.strip()
    if not DATE_RE.match(value):
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        return None


def is_pending(r: Record) -> bool:
    return r.prefix == "dec" and r.get("Choice").lower() in PENDING


def prediction_hit(r: Record) -> bool | None:
    """For a decided record with a logged prediction: was the prediction right? None if not scorable."""
    if r.prefix != "dec" or is_pending(r) or is_empty(r.get("Predicted")):
        return None
    return norm_text(r.get("Predicted")) == norm_text(r.get("Choice"))


def track_record(profile: Profile) -> tuple[int, int]:
    """(correct, scored) predictions across all decisions."""
    hits = [h for h in (prediction_hit(r) for r in profile.records) if h is not None]
    return sum(hits), len(hits)


def said_by_other(r: Record) -> bool:
    return r.get("Said by").lower() not in SELF


def is_expired(r: Record, today: dt.date) -> bool:
    exp = parse_date(r.get("Expires"))
    return bool(exp and exp < today)


def is_active(r: Record, today: dt.date) -> bool:
    return r.status != "superseded" and not is_expired(r, today)


# --------------------------------------------------------------------------- text similarity

STOP = set("""a an the to for of and or in on with is are be by as at from that this it its my your our their
we they i you he she them his her if then than so do does did can will would should could may might must
when while into about over under after before up out not no yes all any some each every""".split())


# Verbs that name the same act of producing a document. Kept tiny on purpose: precision matters.
SYNONYMS = {
    "choose": "choos", "chose": "choos", "chosen": "choos",
    "draft": "writ", "write": "writ", "compose": "writ", "prepare": "writ",
    "creat": "make", "create": "make", "build": "make",
    "direction": "option", "alternative": "option", "concept": "option", "variant": "option", "choice": "option",
    "customer": "client", "buyer": "client",
    "deck": "slide", "presentation": "slide",
    "quote": "proposal", "bid": "proposal", "pitch": "proposal",
    "mail": "email", "message": "email",
    "bug": "defect",
}


def stem(w: str) -> str:
    if w in SYNONYMS:
        return SYNONYMS[w]
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    for suf in ("ing", "ed", "es", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 4:
            w = w[: -len(suf)]
            return SYNONYMS.get(w, w)
    return w


def tokens(text: str) -> list[str]:
    return [stem(w) for w in re.findall(r"[a-z0-9&]+", text.lower()) if w not in STOP and len(w) > 1]


def jaccard(a: str, b: str) -> float:
    x, y = set(tokens(a)), set(tokens(b))
    return len(x & y) / len(x | y) if x | y else 0.0


def doc_tokens(r: Record) -> list[str]:
    weighted = [r.get("Condition")] * 2 + [r.get("Scope")] * 2 + [r.get("Project")] * 2 + [
        r.get("Action"), r.get("Constraints"), r.get("Said by"), r.get("Last decision"), r.get("Next step")]
    if r.prefix == "dec":
        weighted += [r.get("Question")] * 2 + [r.get("Options"), r.get("Choice"), r.get("Reason")]
    return tokens(" ".join(weighted))


def bm25(records: list[Record], query: str, k1: float = 1.2, b: float = 0.75) -> list[float]:
    q = set(tokens(query))
    docs = [doc_tokens(r) for r in records]
    n = len(docs) or 1
    avg = sum(len(d) for d in docs) / n or 1.0
    df: dict[str, int] = {}
    for d in docs:
        for t in set(d):
            df[t] = df.get(t, 0) + 1
    scores = []
    for d in docs:
        tf: dict[str, int] = {}
        for t in d:
            tf[t] = tf.get(t, 0) + 1
        s = 0.0
        for t in q:
            if t in tf:
                idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                s += idf * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * len(d) / avg))
        scores.append(s)
    return scores


CALENDAR = set("""January February March April May June July August September October November December
Monday Tuesday Wednesday Thursday Friday Saturday Sunday I""".split())


def named_scope(r: Record) -> list[str]:
    """Proper names in a record's trigger (Condition, or Project), e.g. a client or product: 'Kestrel Coffee'."""
    text = r.get("Condition") or r.get("Project")
    words = re.findall(r"[A-Za-z][A-Za-z0-9&'\-]*", text)
    names = [w for w in words[1:] if w[0].isupper() and w not in CALENDAR] if r.get("Condition") else \
        [w for w in words if w[0].isupper() and w not in CALENDAR]
    return names


def names_missing(r: Record, brief: str) -> list[str]:
    """Names the record is scoped to, when none of them appear in the brief."""
    names = named_scope(r)
    low = brief.lower()
    return [] if not names or any(n.lower() in low for n in names) else names


def possible_conflict(a: Record, b: Record) -> bool:
    """Same situation, overlapping but different instructions: likely the same decision made twice."""
    if a.prefix in NON_RULE or b.prefix in NON_RULE:
        return False
    return jaccard(a.get("Condition"), b.get("Condition")) >= 0.6 and 0.2 <= jaccard(a.get("Action"), b.get("Action")) < 0.8


def winner(a: Record, b: Record) -> Record:
    """Latest explicit correction wins: stated beats inferred, then the more recent date."""
    ka = (STATUS_RANK.get(a.status, -1), a.date())
    kb = (STATUS_RANK.get(b.status, -1), b.date())
    return a if ka >= kb else b


# --------------------------------------------------------------------------- validation

@dataclass
class Finding:
    level: str  # "error" | "warning"
    line: int
    message: str

    def __str__(self) -> str:
        return f"{self.level.upper()} line {self.line}: {self.message}"


def scan_secrets(lines: list[str]) -> list[Finding]:
    out = []
    for i, line in enumerate(lines, start=1):
        for label, pattern in SECRET_PATTERNS:
            if pattern.search(line):
                out.append(Finding("error", i, f"looks like a {label}. Remove it: credentials are never stored"))
                break
    return out


def validate(profile: Profile, today: dt.date | None = None) -> list[Finding]:
    today = today or dt.date.today()
    findings = scan_secrets(profile.lines)
    by_id: dict[str, Record] = {}
    superseded_refs: dict[str, str] = {}

    for r in profile.records:
        m = ID_RE.match(r.id)
        if not m or m.group("prefix") not in TYPES:
            findings.append(Finding("error", r.line, f"bad ID '{r.id}': use <prefix>-NNN with prefix in {sorted(TYPES)}"))
        if r.id in by_id:
            findings.append(Finding("error", r.line, f"duplicate ID '{r.id}' (first at line {by_id[r.id].line})"))
        else:
            by_id[r.id] = r
        expected = type_prefix(r.type_label)
        if expected is None:
            findings.append(Finding("error", r.line, f"unknown type '{r.type_label}'"))
        elif m and m.group("prefix") != expected:
            findings.append(Finding("error", r.line, f"ID prefix '{m.group('prefix')}' does not match type '{r.type_label}' (expected '{expected}-')"))

        prefix = expected or r.prefix
        required = list(COMMON_REQUIRED)
        if prefix not in NON_RULE:
            required += RULE_REQUIRED
        required += EXTRA_REQUIRED.get(prefix, [])
        for key in required:
            if key not in r.fields or (is_empty(r.fields[key]) and key not in {"Reason", "Choice"}):
                findings.append(Finding("error", r.line, f"{r.id}: missing required field '{key}'"))
        if prefix == "dec":
            if is_pending(r) and r.status == "confirmed":
                findings.append(Finding("error", r.line, f"{r.id}: a decision still pending can't be 'confirmed'. Record the user's choice with `choose`, or use 'tentative'"))
            if is_pending(r) and is_empty(r.get("Predicted")):
                findings.append(Finding("error", r.line, f"{r.id}: a pending decision needs a 'Predicted' choice"))

        status = r.status
        if status and status not in STATUSES:
            findings.append(Finding("error", r.line, f"{r.id}: status '{status}' not in {sorted(STATUSES)}"))
        if status == "likely" and len(r.sources()) < 2:
            findings.append(Finding("error", r.line, f"{r.id}: 'likely' needs 2+ independent sources (has {len(r.sources())}). Use 'tentative'"))

        sens = r.get("Sensitivity").lower()
        if sens and sens not in SENSITIVITY:
            findings.append(Finding("error", r.line, f"{r.id}: sensitivity '{sens}' not in {sorted(SENSITIVITY)}"))
        if prefix == "sens":
            if sens != "sensitive":
                findings.append(Finding("error", r.line, f"{r.id}: sensitive constraints must have 'Sensitivity: sensitive'"))
            if status not in {"confirmed", "superseded"}:
                findings.append(Finding("error", r.line, f"{r.id}: sensitive constraints are stored only when the user stated them ('confirmed')"))
        elif sens == "sensitive" and is_empty(r.get("Purpose")):
            findings.append(Finding("error", r.line, f"{r.id}: sensitive records need the user's stated 'Purpose'"))

        for key in ("Source date", "Updated"):
            val = r.get(key)
            if val and not parse_date(val):
                findings.append(Finding("error", r.line, f"{r.id}: '{key}' must be YYYY-MM-DD, got '{val}'"))
        src, upd = parse_date(r.get("Source date")), parse_date(r.get("Updated"))
        if src and upd and upd < src:
            findings.append(Finding("error", r.line, f"{r.id}: 'Updated' is earlier than 'Source date'"))

        if is_expired(r, today) and status != "superseded":
            findings.append(Finding("warning", r.line, f"{r.id}: expired on {r.get('Expires')}. Stop applying it, then mark it superseded or forget it"))

        sup = r.get("Supersedes")
        if sup and not is_empty(sup):
            for target in (s.strip() for s in re.split(r"[,;]", sup) if s.strip()):
                superseded_refs[target] = r.id

    for target, by in superseded_refs.items():
        rec = by_id.get(target)
        if rec is None:
            findings.append(Finding("error", by_id[by].line, f"{by}: supersedes unknown record '{target}'"))
        elif rec.status != "superseded":
            findings.append(Finding("error", rec.line, f"{target}: superseded by {by} but its status is '{rec.status}'. Set it to 'superseded'"))
    for r in profile.records:
        if r.status == "superseded" and r.id not in superseded_refs:
            findings.append(Finding("warning", r.line, f"{r.id}: marked superseded but no record names it in 'Supersedes'"))

    # Idempotent imports: the same source + same decision must be one record.
    seen: dict[tuple, Record] = {}
    for r in profile.records:
        if r.status == "superseded" or r.prefix in NON_RULE:
            continue
        key = (frozenset(s.lower() for s in r.sources()), norm_text(r.get("Condition")), norm_text(r.get("Action")))
        if not key[0]:
            continue
        if key in seen:
            findings.append(Finding("error", r.line, f"{r.id}: duplicates {seen[key].id} (same sources, condition and action). Merge into one record"))
        else:
            seen[key] = r
    return sorted(findings, key=lambda f: (f.line, f.level))


def norm_text(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def validate_text(profile: Profile, today: dt.date | None = None) -> tuple[str, bool]:
    findings = validate(profile, today)
    errors = sum(f.level == "error" for f in findings)
    out = [str(f) for f in findings]
    out.append(f"{len(profile.records)} records, {errors} errors, {len(findings) - errors} warnings: {profile.path}")
    return "\n".join(out), errors == 0


# --------------------------------------------------------------------------- rendering

def render(r: Record, hide: set[str] = frozenset()) -> str:
    lines = [f"### {r.id} · {TYPES.get(r.prefix, r.type_label)}"]
    for k, v in r.fields.items():
        if k not in hide:
            lines.append(f"- {k}: {v}")
    return "\n".join(lines)


def one_line(r: Record, today: dt.date) -> str:
    """Compact form for recall: everything an agent needs to apply the record, nothing else."""
    head = f"- **{r.id}** · {r.status or '?'} · {r.get('Updated') or r.get('Source date')}"
    if r.prefix == "dec":
        if is_pending(r):
            return f"{head}: {r.get('Question')} Options: {r.get('Options')}. Still open. Mini Me predicted: {r.get('Predicted')}"
        body = f"{r.get('Question')} → chose **{r.get('Choice')}**. Options: {r.get('Options')}. Why: {r.get('Reason') or 'unknown'}"
        hit = prediction_hit(r)
        if hit is not None:
            body += f". Mini Me had predicted {r.get('Predicted')} ({'right' if hit else 'wrong'})"
        return f"{head}: {body}"
    if r.prefix == "proj":
        body = f"{r.get('Project')}. Latest: {r.get('Latest version')}. Last decision: {r.get('Last decision')}. Next: {r.get('Next step')}"
        if not is_empty(r.get("Constraints")):
            body += f". Constraints: {r.get('Constraints')}"
        return f"{head}: {body}"
    body = f"{r.get('Condition')} → {r.get('Action')}. Scope: {r.get('Scope')}"
    if said_by_other(r):
        body += f". Said by: {r.get('Said by')}"
    if not is_empty(r.get("Exceptions")) and r.get("Exceptions").lower() != "none known":
        body += f". Exceptions: {r.get('Exceptions')}"
    if not is_empty(r.get("Expires")):
        body += f". Expires: {r.get('Expires')}"
    reason = r.get("Reason")
    body += f". Reason: {reason or 'unknown'}"
    return f"{head}: {body}"


# --------------------------------------------------------------------------- recall

def recall_data(profile: Profile, brief: str, k: int = 8, today: dt.date | None = None) -> dict:
    today = today or dt.date.today()
    recs = [r for r in profile.records if r.get("Sensitivity").lower() != "sensitive" or r.prefix == "sens"]
    scores = bm25(recs, brief)
    q = set(tokens(brief))
    ranked = sorted(zip(scores, range(len(recs))), key=lambda x: (-x[0], x[1]))
    top = ranked[0][0] if ranked else 0.0
    threshold = max(top * 0.3, 1e-9)
    active, inactive = [], []
    precedents = []
    dec_top = max((s for s, i in ranked if recs[i].prefix == "dec"), default=0.0)
    for s, i in ranked:
        r = recs[i]
        if r.prefix == "dec":
            if s > 0 and s >= dec_top * 0.25 and len(precedents) < 4:
                precedents.append(r)
            continue
        # A record is triggered when the brief covers most of its Condition. Missing a triggered rule is worse
        # than showing an extra one, so triggered records are kept even when another record scores far higher.
        cond = set(tokens(r.get("Condition") or r.get("Project")))
        hit = len(cond & q)
        triggered = bool(cond) and hit / len(cond) >= 0.5 and hit >= min(2, len(cond))
        if s <= 0:
            continue
        # Precision guard: an untriggered rule needs at least two distinct brief words in what it is about
        # (its condition and action). One shared word ("client", "review") is a coincidence, not relevance.
        if not triggered and r.prefix != "proj" and len(set(tokens(r.get("Condition") + " " + r.get("Action"))) & q) < 2:
            continue
        strong = triggered or s >= threshold
        (active if is_active(r, today) else inactive).append((s, strong, r))
    # Keep every triggered or strong record (bounded), then fill up to k with the best positive matches,
    # so one dominant record can never hide the rest of a small profile.
    trig = [x for x in active if x[1]][: 3 * k]
    rest = [x for x in active if not x[1]][: max(0, k - len(trig))]
    inactive = [x for x in inactive if x[1]]
    active = sorted(trig + rest, key=lambda x: -x[0])
    active = [(s, r) for s, _, r in active]
    inactive = [(s, r) for s, _, r in inactive][:k]
    chosen = [r for _, r in active]

    groups = {"stated": [], "inferred": [], "others": [], "project": [], "elsewhere": []}
    for r in chosen:
        if names_missing(r, brief):
            groups["elsewhere"].append(r)
        elif r.prefix == "proj":
            groups["project"].append(r)
        elif said_by_other(r):
            groups["others"].append(r)
        elif r.status in INFERRED:
            groups["inferred"].append(r)
        else:
            groups["stated"].append(r)

    conflicts = []
    own = [r for r in chosen if r.prefix != "proj" and not said_by_other(r) and not names_missing(r, brief)]
    for i, a in enumerate(own):
        for b in own[i + 1:]:
            if possible_conflict(a, b):
                w = winner(a, b)
                conflicts.append({"records": [a.id, b.id], "use": w.id,
                                  "why": f"{w.status}, {w.get('Updated') or w.get('Source date')}"})

    by_id = profile.by_id()
    excluded = []
    for _, r in inactive:
        if r.status == "superseded":
            newer = [x.id for x in profile.records if r.id in [s.strip() for s in re.split(r"[,;]", x.get("Supersedes"))]]
            excluded.append({"id": r.id, "why": "superseded" + (f" by {', '.join(newer)}" if newer else "")})
        else:
            excluded.append({"id": r.id, "why": f"expired {r.get('Expires')}"})
    # A matched record that replaces another should also flag what it replaced, even if that scored low.
    for r in chosen:
        for old in (s.strip() for s in re.split(r"[,;]", r.get("Supersedes")) if s.strip() and not is_empty(s)):
            if old in by_id and old not in {e["id"] for e in excluded}:
                excluded.append({"id": old, "why": f"superseded by {r.id}"})

    hits, scored = track_record(profile)
    return {
        "precedents": [{"id": r.id, "line": one_line(r, today)} for r in precedents],
        "track_record": {"correct": hits, "scored": scored},
        "brief": brief,
        "profile": str(profile.path),
        "date": today.isoformat(),
        "total_records": len(profile.records),
        "matched": len(chosen),
        "groups": {g: [{"id": r.id, "line": one_line(r, today)} for r in rs] for g, rs in groups.items()},
        "conflicts": conflicts,
        "excluded": excluded,
    }


def recall_text(profile: Profile, brief: str, k: int = 8, today: dt.date | None = None) -> str:
    d = recall_data(profile, brief, k, today)
    out = [
        "# Mini Me recall",
        f"Brief: {d['brief']}",
        f"{d['matched']} of {d['total_records']} records matched · {d['date']}",
        "Precedence: today's request > the client's or audience's stated requirements > records below.",
        "Apply each record only inside its Scope.",
        "",
    ]
    titles = {
        "stated": "Apply: stated by the user",
        "inferred": "Apply with care: inferred, say so in the reply",
        "others": "Others' constraints: only if the deliverable is inside their scope",
        "project": "Project state",
        "elsewhere": "Check scope: names a client, product or project not in the brief. Apply only if it really covers this task",
    }
    for g, title in titles.items():
        if d["groups"][g]:
            out.append(f"## {title}")
            out += [x["line"] for x in d["groups"][g]]
            out.append("")
    if d["conflicts"]:
        out.append("## Possible conflicts: same situation, different instructions")
        for c in d["conflicts"]:
            out.append(f"- {' vs '.join(c['records'])} → use **{c['use']}** ({c['why']}: latest explicit correction wins). "
                       f"Check that both describe the same decision")
        out.append("")
    if d["precedents"]:
        out.append("## Precedents: what the user decided before in similar situations")
        out += [x["line"] for x in d["precedents"]]
        tr = d["track_record"]
        if tr["scored"]:
            out.append(f"Prediction track record: {tr['correct']} of {tr['scored']} predictions right. "
                       "State a confidence that matches it.")
        out.append("")
    if d["excluded"]:
        out.append("## Do not apply")
        out += [f"- {e['id']}: {e['why']}" for e in d["excluded"]]
        out.append("")
    if not d["matched"] and not d["precedents"]:
        out.append("No records match this brief. Work from the request and make consequential assumptions visible.")
    return "\n".join(out).rstrip() + "\n"


# --------------------------------------------------------------------------- writes

def atomic_write(path: Path, text: str, expected_digest: str | None) -> None:
    if expected_digest is not None:
        current = hashlib.sha256(path.read_text(encoding="utf-8").encode()).hexdigest() if path.exists() else None
        if current != expected_digest:
            raise MiniMeError("profile changed while editing. Re-read it and apply only the intended change")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".mini-me-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def set_field(lines: list[str], r: Record, key: str, value: str) -> None:
    """Set a field in place inside the record's line span, inserting it if missing."""
    last_field = r.line - 1
    for i in range(r.line, r.end_line):
        m = FIELD_RE.match(lines[i].strip())
        if m:
            last_field = i
            if normalize_key(m.group("key")) == key:
                lines[i] = f"- {key}: {value}"
                r.fields[key] = value
                return
    lines.insert(last_field + 1, f"- {key}: {value}")
    r.fields[key] = value


def next_id(profile: Profile | None, prefix: str) -> str:
    nums = [0]
    for r in (profile.records if profile else []):
        m = ID_RE.match(r.id)
        if m and m.group("prefix") == prefix:
            nums.append(int(m.group("num")))
    return f"{prefix}-{max(nums) + 1:03d}"


def commit(path: Path, new_text: str, digest: str | None, today: dt.date) -> None:
    """Validate the would-be file first; write only if it has no errors."""
    candidate = parse_text(new_text, path)
    errors = [f for f in validate(candidate, today) if f.level == "error"]
    if errors:
        raise MiniMeError("not saved, the result would be invalid:\n" + "\n".join(str(f) for f in errors))
    atomic_write(path, new_text, digest)


def add_record(path: Path, fields: dict[str, str], today: dt.date | None = None) -> str:
    """Add a record, or merge it into the existing record for the same decision.

    Merging is how evidence compounds: a second independent source promotes 'tentative' to 'likely'.
    """
    today = today or dt.date.today()
    fields = {normalize_key(k): str(v).strip() for k, v in fields.items() if v is not None and str(v).strip()}
    raw_type = fields.pop("Type", "")
    prefix = type_prefix(raw_type)
    if prefix is None:
        raise MiniMeError(f"unknown type '{raw_type}'. Use one of {sorted(TYPES)}")
    fields.setdefault("Reason", "unknown")
    fields.setdefault("Source date", today.isoformat())
    fields.setdefault("Updated", today.isoformat())
    fields.setdefault("Supersedes", "—")
    fields.setdefault("Sensitivity", "sensitive" if prefix == "sens" else "ordinary")
    fields.setdefault("Status", "tentative")
    if prefix not in NON_RULE:
        fields.setdefault("Exceptions", "none known")
    if prefix == "dec":
        fields.setdefault("Choice", "pending")
    fields["Status"] = fields["Status"].lower()

    exists = path.exists()
    profile = parse(path) if exists else None
    text = profile.text if profile else "# Mini Me profile\n\n<!-- PRIVATE. Keep this file out of shared repositories. -->\n\n## Records\n"
    lines = text.splitlines()

    # 1. Same decision already recorded: merge sources instead of duplicating.
    if profile and prefix not in NON_RULE:
        for r in profile.records:
            if (r.prefix == prefix and is_active(r, today)
                    and norm_text(r.get("Condition")) == norm_text(fields.get("Condition", ""))
                    and norm_text(r.get("Action")) == norm_text(fields.get("Action", ""))):
                new_sources = [s.strip() for s in re.split(r"[,;]", fields.get("Sources", "")) if s.strip()]
                have = {s.lower() for s in r.sources()}
                added = [s for s in new_sources if s.lower() not in have]
                old_status = r.status
                status = max([old_status, fields["Status"]], key=lambda s: STATUS_RANK.get(s, -1))
                if status == "tentative" and len(have) + len(added) >= 2:
                    status = "likely"
                if not added and status == old_status:
                    return f"Already recorded as {r.id}. No change."
                if added:
                    set_field(lines, r, "Sources", ", ".join(r.sources() + added))
                    ev = fields.get("Evidence")
                    if ev and ev not in r.get("Evidence"):
                        set_field(lines, r, "Evidence", f"{r.get('Evidence')} | {ev}")
                if fields.get("Reason", "unknown") != "unknown" and r.get("Reason").lower() in {"", "unknown"}:
                    set_field(lines, r, "Reason", fields["Reason"])
                set_field(lines, r, "Status", status)
                set_field(lines, r, "Updated", today.isoformat())
                commit(path, "\n".join(lines) + "\n", profile.digest, today)
                msg = f"Merged into {r.id} (sources: {', '.join(r.sources())})."
                if status != old_status:
                    msg += f" Status {old_status} → {status}."
                return msg

    # 2. New record. Mark what it replaces.
    rid = next_id(profile, prefix)
    sup = fields.get("Supersedes", "—")
    if profile and not is_empty(sup):
        by_id = profile.by_id()
        for old in (s.strip() for s in re.split(r"[,;]", sup) if s.strip()):
            if old not in by_id:
                raise MiniMeError(f"supersedes unknown record '{old}'")
            # Edit from the bottom up so earlier line numbers stay valid.
        for old in sorted((by_id[s.strip()] for s in re.split(r"[,;]", sup) if s.strip()), key=lambda r: -r.line):
            set_field(lines, old, "Status", "superseded")
            set_field(lines, old, "Updated", today.isoformat())
    ordered = [k for k in FIELD_ORDER if k in fields] + [k for k in fields if k not in FIELD_ORDER]
    block = [f"### {rid} · {TYPES[prefix]}"] + [f"- {k}: {fields[k]}" for k in ordered]
    new_text = "\n".join(lines).rstrip("\n") + "\n\n" + "\n".join(block) + "\n"
    commit(path, new_text, profile.digest if profile else None, today)
    return f"Added {rid}." + (f" Marked {sup} superseded." if not is_empty(sup) else "")


def forget_record(path: Path, rid: str) -> str:
    profile = parse(path)
    targets = [r for r in profile.records if r.id == rid]
    if not targets:
        raise MiniMeError(f"no record '{rid}'")
    lines = list(profile.lines)
    cleared = []
    for r in profile.records:
        refs = [s.strip() for s in re.split(r"[,;]", r.get("Supersedes")) if s.strip()]
        if rid in refs:
            rest = [s for s in refs if s != rid]
            set_field(lines, r, "Supersedes", ", ".join(rest) or "—")
            cleared.append(r.id)
    drop: set[int] = set()
    for r in targets:
        drop.update(range(r.line - 1, r.end_line))
    kept = [ln for i, ln in enumerate(lines) if i not in drop]
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).rstrip("\n") + "\n"
    atomic_write(path, text, profile.digest)
    if any(r.id == rid for r in parse(path).records):
        raise MiniMeError("forget failed: record still present")
    msg = f"Removed {rid} from {path}."
    if cleared:
        msg += f" Cleared references in {', '.join(cleared)}."
    return msg + "\nNot reached by this tool: earlier exports, the original sources, and copies held by other agents or hosts."


# --------------------------------------------------------------------------- review

def review_text(profile: Profile, today: dt.date | None = None, stale_days: int = 180) -> str:
    """Suggest maintenance. Never applies anything: the user decides."""
    today = today or dt.date.today()
    active = [r for r in profile.records if is_active(r, today) and r.prefix != "proj"]
    items = []

    for r in active:
        if r.status == "tentative" and len(r.sources()) >= 2:
            items.append(f"Promote {r.id} to likely: {len(r.sources())} independent sources.")
    seen_pairs = set()
    for i, a in enumerate(active):
        for b in active[i + 1:]:
            if a.prefix != b.prefix or said_by_other(a) or said_by_other(b):
                continue
            same_cond = jaccard(a.get("Condition"), b.get("Condition")) >= 0.6
            act = jaccard(a.get("Action"), b.get("Action"))
            if same_cond and act >= 0.8 and {s.lower() for s in a.sources()} != {s.lower() for s in b.sources()}:
                items.append(f"Merge {a.id} + {b.id}: same decision from different sources → one record, status likely or better.")
                seen_pairs.add((a.id, b.id))
            elif possible_conflict(a, b):
                w = winner(a, b)
                loser = b if w is a else a
                items.append(f"Conflict {a.id} vs {b.id}: same situation, different instructions. Latest explicit correction is "
                             f"{w.id}. Ask the user, or mark {loser.id} superseded by {w.id}.")
    for r in profile.records:
        if r.status != "superseded" and is_expired(r, today):
            items.append(f"Retire {r.id}: expired {r.get('Expires')}. Mark it superseded or forget it.")
    for r in active:
        src = parse_date(r.get("Source date"))
        if r.status == "tentative" and len(r.sources()) < 2 and src and (today - src).days > stale_days:
            items.append(f"Check {r.id}: tentative for {(today - src).days} days on one example. Ask the user once, or forget it.")
        if r.status in {"confirmed", "likely"} and r.get("Scope").lower() in {"all", "everything", "any", "all work", "always"}:
            items.append(f"Narrow {r.id}: scope '{r.get('Scope')}' is unbounded. Name the work it applies to.")
    items += clarity_issues(profile, today)
    if not items:
        return f"Nothing to review in {len(profile.records)} records."
    return f"# Mini Me review: {len(items)} suggestion(s), nothing applied\n\n" + "\n".join(f"{i}. {t}" for i, t in enumerate(items, 1))


VAGUE = {"better", "good", "nice", "properly", "proper", "appropriate", "appropriately", "etc", "stuff",
         "things", "improve", "optimal", "best", "correctly", "nicely", "well"}
TRIGGER_WORDS = ("when", "if", "for", "before", "after", "whenever", "while", "once")


def clarity_issues(profile: Profile, today: dt.date) -> list[str]:
    """Rules another agent could misapply: vague, unbounded, too long, or missing the why."""
    out: list[str] = []
    ask_why = []
    for r in profile.records:
        if not is_active(r, today):
            continue
        if r.prefix == "dec":
            src = parse_date(r.get("Updated")) or parse_date(r.get("Source date"))
            if is_pending(r) and src and (today - src).days > 14:
                out.append(f"Close {r.id}: still open after {(today - src).days} days. Record the user's actual choice with `choose {r.id}`.")
            continue
        if r.prefix in NON_RULE or said_by_other(r):
            continue
        cond, act = r.get("Condition"), r.get("Action")
        if cond and not cond.lower().startswith(TRIGGER_WORDS):
            out.append(f"Clarify {r.id}: start the condition with 'When …' so it is clear when the rule applies.")
        vague = sorted({w for w in re.findall(r"[a-z]+", act.lower()) if w in VAGUE})
        if vague:
            out.append(f"Make {r.id} concrete: '{', '.join(vague)}' is vague. Say exactly what to do.")
        if len(act.split()) > 30:
            out.append(f"Split {r.id}: {len(act.split())} words in one action. One rule, one action.")
        if r.status in {"confirmed", "likely"} and r.get("Reason").lower() in {"", "unknown"}:
            ask_why.append(r)
    ask_why.sort(key=lambda r: (-STATUS_RANK.get(r.status, 0), r.date()))
    for r in ask_why[:3]:
        out.append(f"Ask why for {r.id}: '{r.get('Action')}' has no reason. The reason tells the agent where else it applies.")
    if len(ask_why) > 3:
        out.append(f"…and {len(ask_why) - 3} more rules without a reason. Ask about the ones you use most.")
    hits, scored = track_record(profile)
    if scored >= 3 and hits / scored < 0.5:
        out.append(f"Predictions were right {hits} of {scored} times. Treat 'which would I choose?' answers as low confidence, "
                   "and record the reason each time the user chooses differently.")
    return out


def choose_record(path: Path, rid: str, choice: str, reason: str | None = None, evidence: str | None = None,
                  sources: str | None = None, today: dt.date | None = None) -> str:
    """Record the user's actual choice on a decision, keeping the earlier prediction for the track record."""
    today = today or dt.date.today()
    if not choice or choice.strip().lower() in PENDING:
        raise MiniMeError("give the choice the user actually made")
    profile = parse(path)
    r = profile.by_id().get(rid)
    if r is None or r.prefix != "dec":
        raise MiniMeError(f"no decision record '{rid}'")
    lines = list(profile.lines)
    set_field(lines, r, "Choice", choice.strip())
    if reason:
        set_field(lines, r, "Reason", reason.strip())
    if evidence:
        set_field(lines, r, "Evidence", f"{r.get('Evidence')} | {evidence.strip()}" if r.get("Evidence") else evidence.strip())
    if sources:
        have = r.sources()
        add = [s.strip() for s in re.split(r"[,;]", sources) if s.strip() and s.strip().lower() not in {h.lower() for h in have}]
        if add:
            set_field(lines, r, "Sources", ", ".join(have + add))
    set_field(lines, r, "Status", "confirmed")
    set_field(lines, r, "Updated", today.isoformat())
    commit(path, "\n".join(lines) + "\n", profile.digest, today)
    msg = f"Recorded the choice on {rid}: {choice.strip()}."
    pred = r.get("Predicted")
    if not is_empty(pred):
        right = norm_text(pred) == norm_text(choice)
        msg += f" Mini Me had predicted {pred}: {'right' if right else 'wrong'}."
        if not right and not reason:
            msg += " Ask the user why: the reason is what fixes the next prediction."
    hits, scored = track_record(parse(path))
    if scored:
        msg += f" Track record: {hits} of {scored} predictions right."
    return msg


CONFIDENCE = {
    "confirmed": "Confirmed: the user said this explicitly.",
    "likely": "Likely: supported by {n} independent sources, but not stated outright.",
    "tentative": "Tentative: inferred from one example. Ask before relying on it outside the same task.",
    "superseded": "Superseded: replaced by a newer record. Not applied.",
}


def explain_text(profile: Profile, rid: str, today: dt.date | None = None) -> str:
    """One record in plain language: what it makes the agent do, why, how sure, and where it came from."""
    today = today or dt.date.today()
    by_id = profile.by_id()
    r = by_id.get(rid)
    if r is None:
        raise MiniMeError(f"no record '{rid}'")
    out = [f"## {r.id} · {TYPES.get(r.prefix, r.type_label)}"]
    if r.prefix == "dec":
        out.append(f"**Question:** {r.get('Question')}")
        out.append(f"**Options:** {r.get('Options')}")
        if is_pending(r):
            out.append(f"**Your choice:** not recorded yet. Mini Me predicted **{r.get('Predicted')}**.")
        else:
            out.append(f"**You chose:** {r.get('Choice')}")
            out.append(f"**Why:** {r.get('Reason') or 'not recorded'}")
            hit = prediction_hit(r)
            if hit is not None:
                out.append(f"**Prediction:** Mini Me predicted {r.get('Predicted')}, which was {'right' if hit else 'wrong'}.")
    elif r.prefix == "proj":
        out.append(f"**Project:** {r.get('Project')}")
        if not is_empty(r.get("Constraints")):
            out.append(f"**Client requirements:** {r.get('Constraints')}")
        out.append(f"**Latest version:** {r.get('Latest version')}")
        out.append(f"**Last decision:** {r.get('Last decision')}")
        out.append(f"**Next step:** {r.get('Next step')}")
    else:
        act = r.get("Action")
        out.append(f"**{r.get('Condition').rstrip('.')},** Mini Me will: {act[:1].lower() + act[1:]}.")
        out.append(f"**Only for:** {r.get('Scope')}.")
        if not is_empty(r.get("Exceptions")) and r.get("Exceptions").lower() != "none known":
            out.append(f"**Except:** {r.get('Exceptions')}.")
        if not is_empty(r.get("Expires")):
            out.append(f"**Expires:** {r.get('Expires')}" + (" (already expired, not applied)." if is_expired(r, today) else "."))
        reason = r.get("Reason")
        if reason.lower() in {"", "unknown"}:
            out.append("**Why:** not known yet. Telling Mini Me why lets it apply this rule in the right new situations.")
        else:
            out.append(f"**Why:** {reason}.")
        if said_by_other(r):
            out.append(f"**Whose rule:** {r.get('Said by')}. It is their instruction, not your own preference.")
        if r.prefix == "sens":
            out.append(f"**Kept for:** {r.get('Purpose')} (sensitive, stored because you asked).")
    if is_pending(r):
        hits, scored = track_record(profile)
        record = f" Past predictions: {hits} of {scored} right." if scored else ""
        out.append(f"**How sure:** a prediction only, until the user decides.{record}")
    else:
        out.append(f"**How sure:** {CONFIDENCE.get(r.status, r.status).format(n=len(r.sources()))}")
    out.append(f"**Evidence:** {r.get('Evidence')} (source: {r.get('Sources')}, {r.get('Source date')}).")
    replaced = [s.strip() for s in re.split(r"[,;]", r.get("Supersedes")) if s.strip() and not is_empty(s)]
    for old in replaced:
        o = by_id.get(old)
        if o:
            out.append(f"**Replaced:** {old} ({o.get('Action') or o.get('Choice')}) on {r.get('Source date')}.")
    newer = [x for x in profile.records if rid in [s.strip() for s in re.split(r"[,;]", x.get("Supersedes"))]]
    for x in newer:
        out.append(f"**Replaced by:** {x.id} ({x.get('Action') or x.get('Choice')}) on {x.get('Source date')}.")
    return "\n".join(out) + "\n"


def history_events(profile: Profile, today: dt.date) -> list[tuple[dt.date, str, str]]:
    events = []
    by_id = profile.by_id()
    for r in profile.records:
        first = parse_date(r.get("Source date")) or dt.date.min
        last = parse_date(r.get("Updated")) or first
        if r.prefix == "dec":
            if is_pending(r):
                events.append((last, r.id, f"Asked: {r.get('Question')} Mini Me predicted {r.get('Predicted')}. Your choice is still open."))
            else:
                hit = prediction_hit(r)
                tail = "" if hit is None else f" (Mini Me predicted {r.get('Predicted')}: {'right' if hit else 'wrong'})"
                events.append((last, r.id, f"Decided: {r.get('Question')} → {r.get('Choice')}. Why: {r.get('Reason') or 'not recorded'}{tail}"))
            continue
        if r.prefix == "proj":
            events.append((last, r.id, f"Project {r.get('Project')}: {r.get('Last decision')}. Next: {r.get('Next step')}"))
            continue
        what = f"{r.get('Condition')} → {r.get('Action')}"
        olds = [s.strip() for s in re.split(r"[,;]", r.get("Supersedes")) if s.strip() and not is_empty(s)]
        if olds:
            events.append((first, r.id, f"Corrected {', '.join(olds)}: {what}"))
        elif r.prefix == "exc":
            events.append((first, r.id, f"One-off ({r.get('Expires')}): {what}"))
        else:
            label = "Noted" if said_by_other(r) else "Learned"
            who = f" (said by {r.get('Said by')})" if said_by_other(r) else ""
            events.append((first, r.id, f"{label}, {r.status}{who}: {what}"))
        if r.status in {"likely", "confirmed"} and last > first and not olds:
            events.append((last, r.id, f"Strengthened to {r.status}: {len(r.sources())} source(s)"))
    return events


def history_text(profile: Profile, project: str | None = None, since: str | None = None, limit: int = 30,
                 today: dt.date | None = None) -> str:
    """Timeline, newest first: what you decided, what was learned, what was corrected."""
    today = today or dt.date.today()
    events = history_events(profile, today)
    if project:
        keep = {r.id for r in profile.records if project.lower() in " ".join(r.fields.values()).lower()}
        events = [e for e in events if e[1] in keep]
    if since:
        d = parse_date(since)
        if d is None:
            raise MiniMeError("--since must be YYYY-MM-DD")
        events = [e for e in events if e[0] >= d]
    events.sort(key=lambda e: (e[0], e[1]), reverse=True)
    if not events:
        return "No history yet."
    out = ["# Mini Me history (newest first)", ""]
    out += [f"- {d.isoformat()} · **{rid}** · {text}" for d, rid, text in events[:limit]]
    if len(events) > limit:
        out.append(f"- … {len(events) - limit} older events (use --limit)")
    return "\n".join(out) + "\n"


def stats_text(profile: Profile, today: dt.date | None = None) -> str:
    today = today or dt.date.today()
    active = [r for r in profile.records if is_active(r, today)]
    rules = [r for r in active if r.prefix not in NON_RULE]
    by_status = {s: sum(1 for r in rules if r.status == s) for s in ("confirmed", "likely", "tentative")}
    with_reason = sum(1 for r in rules if r.get("Reason").lower() not in {"", "unknown"})
    decs = [r for r in profile.records if r.prefix == "dec"]
    open_decs = sum(1 for r in decs if is_pending(r))
    hits, scored = track_record(profile)
    out = [
        "# Mini Me stats",
        "",
        f"- Active rules: {len(rules)} ({by_status['confirmed']} confirmed, {by_status['likely']} likely, {by_status['tentative']} tentative)",
        f"- Rules with a known reason: {with_reason} of {len(rules)}",
        f"- Decisions recorded: {len(decs)} ({open_decs} still open)",
        f"- Prediction track record: " + (f"{hits} of {scored} right" if scored else "no scored predictions yet"),
        f"- Inactive (superseded or expired): {len(profile.records) - len(active)}",
    ]
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------- read-only views

def select(profile: Profile, today: dt.date, rtype: str | None = None, project: str | None = None,
           query: str | None = None, include_inactive: bool = False) -> list[Record]:
    out = []
    want = (type_prefix(rtype) or rtype) if rtype else None
    for r in profile.records:
        if not include_inactive and not is_active(r, today):
            continue
        if want and r.prefix != want:
            continue
        blob = " ".join(r.fields.values()).lower()
        if project and project.lower() not in blob:
            continue
        if query and query.lower() not in (blob + " " + r.id.lower()):
            continue
        out.append(r)
    return out


def show_text(profile: Profile, today: dt.date | None = None, **filters) -> str:
    today = today or dt.date.today()
    records = select(profile, today, **filters)
    if not records:
        return "No matching active records."
    decisions = [r for r in records if r.prefix == "dec"]
    records = [r for r in records if r.prefix != "dec"]
    groups = (
        ("Stated by you", [r for r in records if r.status not in INFERRED and not said_by_other(r)]),
        ("Inferred: correct me if wrong", [r for r in records if r.status in INFERRED and not said_by_other(r)]),
        ("Your decisions", decisions),
        ("Said by others: applied only within their scope", [r for r in records if said_by_other(r)]),
    )
    out = []
    for title, group in groups:
        if group:
            out.append(f"## {title}\n")
            out += [render(r) + "\n" for r in group]
    return "\n".join(out)


def export_text(profile: Profile, today: dt.date | None = None, include_sources: bool = False,
                include_sensitive: bool = False, **filters) -> tuple[str, int]:
    today = today or dt.date.today()
    records = select(profile, today, **filters)
    if not include_sensitive:
        records = [r for r in records if r.get("Sensitivity").lower() != "sensitive"]
    hide = set() if include_sources else PRIVATE_FIELDS
    out = [
        "# Mini Me working preferences (export)",
        "",
        f"Snapshot taken {today.isoformat()}. It does not update itself: re-export to refresh.",
        "Status: confirmed = stated by the user; likely = 2+ independent sources; tentative = one example.",
        "Apply each record only within its Scope. A 'Said by' record is someone else's instruction, not the user's preference.",
        "",
    ]
    out += [render(r, hide) + "\n" for r in records]
    return "\n".join(out), len(records)


# --------------------------------------------------------------------------- CLI

TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "profile.template.md"


def load(args) -> Profile:
    path = resolve_path(args.profile)
    if not path.exists():
        raise MiniMeError(f"no profile at {path}. Run `mini_me.py init` to create one")
    return parse(path)


def cmd_init(args) -> int:
    path = resolve_path(args.profile)
    if path.exists() and not args.force:
        raise MiniMeError(f"{path} already exists. Pass --force to overwrite")
    text = TEMPLATE.read_text(encoding="utf-8") if args.example else (
        "# Mini Me profile\n\n<!-- PRIVATE. Keep this file out of shared repositories. "
        "Format: references/profile-format.md -->\n\n## Records\n")
    atomic_write(path, text, None)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    print(f"Created {path} (private, mode 600).")
    return 0


def cmd_validate(args) -> int:
    text, ok = validate_text(load(args))
    print(text)
    return 0 if ok else 1


def cmd_recall(args) -> int:
    brief = " ".join(args.brief) if args.brief else sys.stdin.read()
    if not brief.strip():
        raise MiniMeError("give a brief: recall \"what the task is\"")
    profile = load(args)
    if args.json:
        print(json.dumps(recall_data(profile, brief.strip(), args.k), indent=2))
    else:
        print(recall_text(profile, brief.strip(), args.k), end="")
    return 0


def cmd_add(args) -> int:
    fields: dict[str, str] = {}
    if args.json:
        raw = sys.stdin.read() if args.json == "-" else Path(args.json).read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise MiniMeError("--json must hold one JSON object of field: value")
        fields.update({k: str(v) for k, v in data.items()})
    for flag, key in ADD_FLAGS:
        val = getattr(args, flag)
        if val is not None:
            fields[key] = val
    if args.type:
        fields["Type"] = args.type
    print(add_record(resolve_path(args.profile), fields))
    return 0


def cmd_review(args) -> int:
    print(review_text(load(args), stale_days=args.stale_days))
    return 0


def cmd_show(args) -> int:
    print(show_text(load(args), rtype=args.type, project=args.project, query=args.query,
                    include_inactive=args.include_inactive))
    return 0


def cmd_export(args) -> int:
    text, n = export_text(load(args), include_sources=args.include_sources, include_sensitive=args.include_sensitive,
                          rtype=args.type, project=args.project, query=args.query, include_inactive=args.include_inactive)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"Exported {n} records to {args.output}")
    else:
        print(text)
    return 0


def cmd_forget(args) -> int:
    path = resolve_path(args.profile)
    profile = load(args)
    if args.dry_run:
        if not any(r.id == args.id for r in profile.records):
            raise MiniMeError(f"no record '{args.id}'")
        print(f"Would remove {args.id}.")
        return 0
    print(forget_record(path, args.id))
    return 0


def cmd_explain(args) -> int:
    print(explain_text(load(args), args.id), end="")
    return 0


def cmd_history(args) -> int:
    print(history_text(load(args), project=args.project, since=args.since, limit=args.limit), end="")
    return 0


def cmd_stats(args) -> int:
    print(stats_text(load(args)), end="")
    return 0


def cmd_choose(args) -> int:
    load(args)
    print(choose_record(resolve_path(args.profile), args.id, args.choice, args.reason, args.evidence, args.sources))
    return 0


def cmd_next_id(args) -> int:
    prefix = type_prefix(args.prefix) or args.prefix
    if prefix not in TYPES:
        raise MiniMeError(f"unknown prefix '{args.prefix}'. Use one of {sorted(TYPES)}")
    path = resolve_path(args.profile)
    print(next_id(parse(path) if path.exists() else None, prefix))
    return 0


ADD_FLAGS = [
    ("condition", "Condition"), ("action", "Action"), ("scope", "Scope"), ("exceptions", "Exceptions"),
    ("evidence", "Evidence"), ("sources", "Sources"), ("reason", "Reason"), ("status", "Status"),
    ("source_date", "Source date"), ("said_by", "Said by"), ("expires", "Expires"), ("purpose", "Purpose"),
    ("supersedes", "Supersedes"), ("project", "Project"), ("constraints", "Constraints"),
    ("latest_version", "Latest version"), ("last_decision", "Last decision"), ("completed", "Completed"),
    ("next_step", "Next step"), ("sensitivity", "Sensitivity"),
    ("question", "Question"), ("options", "Options"), ("choice", "Choice"), ("predicted", "Predicted"),
]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mini_me", description=__doc__.splitlines()[0])
    p.add_argument("--profile", help="profile path (default: $MINI_ME_PROFILE or ~/.mini-me/profile.md)")
    p.add_argument("--version", action="version", version=f"mini_me {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    ip = sub.add_parser("init", help="create a private profile")
    ip.add_argument("--example", action="store_true", help="start from the example template")
    ip.add_argument("--force", action="store_true")

    sub.add_parser("validate", help="check the profile; exit 1 on errors")

    rp = sub.add_parser("recall", help="the records relevant to a task brief, compact")
    rp.add_argument("brief", nargs="*", help="task brief (or pipe it on stdin)")
    rp.add_argument("-k", type=int, default=8, help="max active records (default 8)")
    rp.add_argument("--json", action="store_true")

    ap = sub.add_parser("add", help="add a record, or merge it into the same decision")
    ap.add_argument("--type", help="goal, pref, rule, method, exc, sens, proj, dec")
    ap.add_argument("--json", help="JSON object of fields, from a file or '-' for stdin")
    for flag, key in ADD_FLAGS:
        ap.add_argument("--" + flag.replace("_", "-"), dest=flag, help=key)

    rv = sub.add_parser("review", help="suggest promotions, merges, conflicts, retirements")
    rv.add_argument("--stale-days", type=int, default=180)

    for name in ("show", "export"):
        sp = sub.add_parser(name)
        sp.add_argument("--type", help="record type or prefix, e.g. rule, pref")
        sp.add_argument("--project", help="substring match on any field")
        sp.add_argument("--query", help="substring match on any field or ID")
        sp.add_argument("--include-inactive", action="store_true", help="include superseded and expired records")
        if name == "export":
            sp.add_argument("--include-sources", action="store_true", help="include Evidence and Sources")
            sp.add_argument("--include-sensitive", action="store_true", help="include sensitive records")
            sp.add_argument("-o", "--output", help="write to file instead of stdout")

    xp = sub.add_parser("explain", help="one record in plain language: what it does, why, how sure, its history")
    xp.add_argument("id")

    hp = sub.add_parser("history", help="timeline of decisions, lessons and corrections, newest first")
    hp.add_argument("--project", help="substring match on any field")
    hp.add_argument("--since", help="YYYY-MM-DD")
    hp.add_argument("--limit", type=int, default=30)

    sub.add_parser("stats", help="rules by confidence, reasons known, decisions, prediction track record")

    cp = sub.add_parser("choose", help="record the user's actual choice on a decision (dec-)")
    cp.add_argument("id")
    cp.add_argument("--choice", required=True)
    cp.add_argument("--reason")
    cp.add_argument("--evidence")
    cp.add_argument("--sources")

    fp = sub.add_parser("forget", help="remove a record and references to it")
    fp.add_argument("id")
    fp.add_argument("--dry-run", action="store_true")

    np_ = sub.add_parser("next-id", help="print the next free ID for a prefix")
    np_.add_argument("prefix")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handler = {
        "init": cmd_init, "validate": cmd_validate, "recall": cmd_recall, "add": cmd_add, "review": cmd_review,
        "show": cmd_show, "export": cmd_export, "forget": cmd_forget, "next-id": cmd_next_id,
        "explain": cmd_explain, "history": cmd_history, "stats": cmd_stats, "choose": cmd_choose,
    }[args.cmd]
    try:
        return handler(args)
    except MiniMeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2 if "no profile at" in str(exc) else 1


if __name__ == "__main__":
    sys.exit(main())

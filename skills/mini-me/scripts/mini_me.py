#!/usr/bin/env python3
"""Mini Me profile tool: validate, show, export, forget, next-id.

Stdlib only. The profile is a private Markdown file (see references/profile-format.md).
Path resolution: --profile, then $MINI_ME_PROFILE, then ~/.mini-me/profile.md.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import os
import re
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

TYPES = {
    "goal": "Goal",
    "pref": "Preference",
    "rule": "Decision rule",
    "method": "Problem-solving method",
    "exc": "Exception",
    "sens": "Sensitive constraint",
    "proj": "Project state",
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
}
STATUSES = {"confirmed", "likely", "tentative", "superseded"}
INFERRED = {"likely", "tentative"}
SENSITIVITY = {"ordinary", "sensitive"}
COMMON_REQUIRED = ["Evidence", "Sources", "Reason", "Status", "Source date", "Updated", "Sensitivity"]
RULE_REQUIRED = ["Condition", "Action", "Scope"]
EXTRA_REQUIRED = {
    "exc": ["Expires"],
    "sens": ["Purpose"],
    "proj": ["Project", "Latest version", "Last decision", "Next step"],
}
PRIVATE_FIELDS = {"Evidence", "Sources"}
EMPTY = {"", "—", "-", "none", "n/a"}

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


@dataclass
class Record:
    id: str
    type_label: str
    line: int
    fields: dict[str, str] = field(default_factory=dict)
    end_line: int = 0  # exclusive, 0-based index into lines

    @property
    def prefix(self) -> str:
        m = ID_RE.match(self.id)
        return m.group("prefix") if m else ""

    @property
    def status(self) -> str:
        return self.fields.get("Status", "").strip().lower()

    def get(self, key: str) -> str:
        return self.fields.get(key, "").strip()

    def sources(self) -> set[str]:
        raw = self.get("Sources")
        return {s.strip().lower() for s in re.split(r"[,;]", raw) if s.strip().lower() not in EMPTY}


@dataclass
class Profile:
    path: Path
    text: str
    lines: list[str]
    records: list[Record]
    start_index: dict[str, int]  # record id -> 0-based heading line index

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.text.encode()).hexdigest()


def resolve_path(arg: str | None) -> Path:
    if arg:
        return Path(arg).expanduser()
    env = os.environ.get("MINI_ME_PROFILE")
    if env:
        return Path(env).expanduser()
    return Path("~/.mini-me/profile.md").expanduser()


def parse(path: Path) -> Profile:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    records: list[Record] = []
    start_index: dict[str, int] = {}
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
            start_index.setdefault(current.id, i)
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
    return Profile(path=path, text=text, lines=lines, records=records, start_index=start_index)


def normalize_key(key: str) -> str:
    key = " ".join(key.split())
    return key[:1].upper() + key[1:].lower()


def type_prefix(label: str) -> str | None:
    return TYPE_ALIASES.get(label.strip().lower())


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
        if prefix != "proj":
            required += RULE_REQUIRED
        required += EXTRA_REQUIRED.get(prefix, [])
        for key in required:
            if key not in r.fields or (is_empty(r.fields[key]) and key not in {"Reason"}):
                findings.append(Finding("error", r.line, f"{r.id}: missing required field '{key}'"))

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

        exp = parse_date(r.get("Expires"))
        if exp and exp < today and status != "superseded":
            findings.append(Finding("warning", r.line, f"{r.id}: expired on {exp}. Stop applying it, then mark it superseded or forget it"))

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
        if r.status == "superseded" or r.prefix == "proj":
            continue
        key = (frozenset(r.sources()), norm_text(r.get("Condition")), norm_text(r.get("Action")))
        if not key[0]:
            continue
        if key in seen:
            findings.append(Finding("error", r.line, f"{r.id}: duplicates {seen[key].id} (same sources, condition and action). Merge into one record"))
        else:
            seen[key] = r
    return sorted(findings, key=lambda f: (f.line, f.level))


def norm_text(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


SELF = {"", "user", "the user", "me", "self", "—", "-"}


def said_by_other(r: Record) -> bool:
    return r.get("Said by").lower() not in SELF


def is_active(r: Record, today: dt.date) -> bool:
    if r.status == "superseded":
        return False
    exp = parse_date(r.get("Expires"))
    return not (exp and exp < today)


def select(profile: Profile, args, today: dt.date) -> list[Record]:
    out = []
    for r in profile.records:
        if not getattr(args, "include_inactive", False) and not is_active(r, today):
            continue
        if args.type and r.prefix != (type_prefix(args.type) or args.type):
            continue
        blob = " ".join(r.fields.values()).lower()
        if args.project and args.project.lower() not in blob:
            continue
        if args.query and args.query.lower() not in (blob + " " + r.id.lower()):
            continue
        out.append(r)
    return out


def render(r: Record, hide: set[str]) -> str:
    lines = [f"### {r.id} · {TYPES.get(r.prefix, r.type_label)}"]
    for k, v in r.fields.items():
        if k not in hide:
            lines.append(f"- {k}: {v}")
    return "\n".join(lines)


def cmd_validate(args) -> int:
    profile = parse(resolve_path(args.profile))
    findings = validate(profile)
    for f in findings:
        print(f)
    errors = sum(f.level == "error" for f in findings)
    warnings = len(findings) - errors
    print(f"{len(profile.records)} records, {errors} errors, {warnings} warnings: {profile.path}")
    return 1 if errors else 0


def cmd_show(args) -> int:
    today = dt.date.today()
    profile = parse(resolve_path(args.profile))
    records = select(profile, args, today)
    if not records:
        print("No matching active records.")
        return 0
    others = [r for r in records if said_by_other(r)]
    stated = [r for r in records if r.status not in INFERRED and not said_by_other(r)]
    inferred = [r for r in records if r.status in INFERRED and not said_by_other(r)]
    groups = (
        ("Stated by you", stated),
        ("Inferred: correct me if wrong", inferred),
        ("Said by others: applied only within their scope", others),
    )
    for title, group in groups:
        if not group:
            continue
        print(f"## {title}\n")
        for r in group:
            print(render(r, set()) + "\n")
    return 0


def cmd_export(args) -> int:
    today = dt.date.today()
    profile = parse(resolve_path(args.profile))
    records = select(profile, args, today)
    if not args.include_sensitive:
        records = [r for r in records if r.get("Sensitivity").lower() != "sensitive"]
    hide = set() if args.include_sources else PRIVATE_FIELDS
    out = [
        "# Mini Me working preferences (export)",
        "",
        f"Snapshot taken {today.isoformat()}. It does not update itself: re-export to refresh.",
        "Status: confirmed = stated by the user; likely = 2+ independent sources; tentative = one example.",
        "Apply each record only within its Scope.",
        "",
    ]
    out += [render(r, hide) + "\n" for r in records]
    text = "\n".join(out)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"Exported {len(records)} records to {args.output}")
    else:
        print(text)
    return 0


def atomic_write(path: Path, text: str, expected_digest: str) -> None:
    current = hashlib.sha256(path.read_text(encoding="utf-8").encode()).hexdigest()
    if current != expected_digest:
        raise RuntimeError("profile changed while editing. Re-read it and apply only the intended change")
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".mini-me-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def cmd_forget(args) -> int:
    path = resolve_path(args.profile)
    profile = parse(path)
    targets = [r for r in profile.records if r.id == args.id]
    if not targets:
        print(f"No record '{args.id}'.", file=sys.stderr)
        return 1
    drop: set[int] = set()
    for r in targets:
        drop.update(range(r.line - 1, r.end_line))
    lines = list(profile.lines)
    cleared = []
    for r in profile.records:
        sup = r.get("Supersedes")
        if args.id in [s.strip() for s in re.split(r"[,;]", sup)]:
            for i in range(r.line - 1, r.end_line):
                if FIELD_RE.match(lines[i].strip()) and normalize_key(FIELD_RE.match(lines[i].strip()).group("key")) == "Supersedes":
                    rest = [s.strip() for s in re.split(r"[,;]", sup) if s.strip() and s.strip() != args.id]
                    lines[i] = re.sub(r"(:\s*).*$", lambda m: m.group(1) + (", ".join(rest) or "—"), lines[i])
                    cleared.append(r.id)
    kept = [ln for i, ln in enumerate(lines) if i not in drop]
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).rstrip("\n") + "\n"
    if args.dry_run:
        print(f"Would remove {args.id}" + (f" and clear references in {', '.join(cleared)}" if cleared else ""))
        return 0
    atomic_write(path, text, profile.digest)
    after = parse(path)
    if any(r.id == args.id for r in after.records):
        print("Forget failed: record still present.", file=sys.stderr)
        return 1
    print(f"Removed {args.id} from {path}." + (f" Cleared references in {', '.join(cleared)}." if cleared else ""))
    print("Not reached by this tool: earlier exports, the original sources, and copies held by other agents or hosts.")
    return 0


def cmd_next_id(args) -> int:
    prefix = type_prefix(args.prefix) or args.prefix
    if prefix not in TYPES:
        print(f"Unknown prefix '{args.prefix}'. Use one of {sorted(TYPES)}", file=sys.stderr)
        return 1
    path = resolve_path(args.profile)
    nums = [0]
    if path.exists():
        for r in parse(path).records:
            m = ID_RE.match(r.id)
            if m and m.group("prefix") == prefix:
                nums.append(int(m.group("num")))
    print(f"{prefix}-{max(nums) + 1:03d}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="mini_me", description=__doc__.splitlines()[0])
    p.add_argument("--profile", help="profile path (default: $MINI_ME_PROFILE or ~/.mini-me/profile.md)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("validate", help="check the profile; exit 1 on errors")

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

    fp = sub.add_parser("forget", help="remove a record and references to it")
    fp.add_argument("id")
    fp.add_argument("--dry-run", action="store_true")

    np_ = sub.add_parser("next-id", help="print the next free ID for a prefix")
    np_.add_argument("prefix")

    args = p.parse_args(argv)
    path = resolve_path(args.profile)
    if args.cmd != "next-id" and not path.exists():
        print(f"No profile at {path}. Copy templates/profile.template.md there to start.", file=sys.stderr)
        return 2
    handler = {
        "validate": cmd_validate,
        "show": cmd_show,
        "export": cmd_export,
        "forget": cmd_forget,
        "next-id": cmd_next_id,
    }[args.cmd]
    try:
        return handler(args)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

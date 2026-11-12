#!/usr/bin/env python3
"""Build README visuals: banner.html (static) is already here; this writes terminal.html from REAL recall output.

Run from the repo root:  python3 docs/assets/src/build.py && node docs/assets/src/render.js
"""
from __future__ import annotations

import datetime as dt
import html
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "skills" / "mini-me" / "scripts"))
import mini_me  # noqa: E402

PROFILE = ROOT / "eval" / "scenarios" / "s4-large-profile" / "profile.md"
BRIEF = "Draft the Halden Shipping proposal: new client, fixed scope, procurement will review it"
TODAY = dt.date(2026, 11, 12)
GROUPS = [("stated", "Apply: stated by you", "#7CF0B4"), ("inferred", "Apply with care: inferred", "#FFC46B"),
          ("others", "Others' rules: only inside their scope", "#9DB4FF"), ("project", "Project state", "#9DB4FF"),
          ("elsewhere", "Check scope: names another client or project", "#C9D3FA")]


def short(rec: mini_me.Record) -> str:
    """'When … → action', the part of a recall line a reader needs."""
    if rec.prefix == "proj":
        return f"{rec.get('Project')} (not this client)"
    act = rec.get("Action")
    if len(act) > 58:
        act = act[:56].rstrip() + "…"
    return f"{rec.get('Condition')} → {act}"


def main() -> int:
    profile = mini_me.parse(PROFILE)
    d = mini_me.recall_data(profile, BRIEF, today=TODAY)
    by_id = profile.by_id()
    rows = [
        f'<div class="cmd"><span class="ps">$</span> mini_me recall <span class="str">"{html.escape(BRIEF)}"</span></div>',
        f'<div class="dim">{d["matched"]} of {d["total_records"]} records matched</div>',
    ]
    for key, title, color in GROUPS:
        items = [x["id"] for x in d["groups"][key]]  # every record recall returned: no curation
        if not items:
            continue
        rows.append(f'<div class="h" style="color:{color}">{title}</div>')
        for rid in items:
            r = by_id[rid]
            rows.append(f'<div class="ln"><span class="id">{rid}</span> <span class="st {r.status}">{r.status}</span> '
                        f'{html.escape(short(r))}</div>')
    for c in d["conflicts"]:
        rows.append('<div class="h" style="color:#9DB4FF">Conflict resolved</div>')
        rows.append(f'<div class="ln">{" vs ".join(c["records"])} → use <span class="id">{c["use"]}</span> '
                    f'<span class="dim">(latest explicit correction)</span></div>')
    if d["excluded"]:
        rows.append('<div class="h" style="color:#FF8A66">Do not apply</div>')
        for e in d["excluded"]:
            rows.append(f'<div class="ln x"><span class="id">{e["id"]}</span> {html.escape(e["why"])}</div>')
    body = "\n".join(rows)
    page = (Path(__file__).parent / "terminal.template.html").read_text().replace("{{BODY}}", body)
    (Path(__file__).parent / "terminal.html").write_text(page)
    print("wrote terminal.html from real recall output:", d["matched"], "matched")
    return 0


if __name__ == "__main__":
    sys.exit(main())

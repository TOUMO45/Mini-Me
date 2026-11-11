#!/usr/bin/env python3
"""Scale benchmark: what an agent must load per task, whole profile (v1) vs recall (v2), as the profile grows.

At every size the same 6 relevant records and 2 traps are hidden among distractors. The check is that recall
still returns all 6, excludes both traps, and resolves the case-study conflict.
Tokens are estimated as characters / 4. Run: python3 eval/bench_scale.py
"""
from __future__ import annotations

import datetime as dt
import random
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "skills" / "mini-me" / "scripts"))
sys.path.insert(0, str(ROOT / "scenarios" / "s4-large-profile"))
import generate  # noqa: E402
import mini_me  # noqa: E402

BRIEF = ("draft the proposal for Halden Shipping, a new client. Scope is fixed and well-defined: a 6-week "
         "route-planning audit. Their procurement team will review it before signing.")
RELEVANT = {"rule-011", "rule-014", "pref-004", "pref-021", "pref-009", "pref-017"}
TRAPS = {"rule-003", "exc-002"}
TODAY = dt.date(2026, 11, 11)


def run(sizes=(51, 250, 1000, 4000)) -> list[dict]:
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        for n in sizes:
            generate.R = random.Random(4)
            text = generate.build(n)
            path = Path(tmp) / f"p{n}.md"
            path.write_text(text, encoding="utf-8")
            t0 = time.perf_counter()
            profile = mini_me.parse(path)
            out = mini_me.recall_text(profile, BRIEF, today=TODAY)
            ms = (time.perf_counter() - t0) * 1000
            d = mini_me.recall_data(profile, BRIEF, today=TODAY)
            got = {x["id"] for g in d["groups"].values() for x in g}
            excluded = {e["id"] for e in d["excluded"]}
            conflict_ok = any(set(c["records"]) == {"pref-009", "pref-021"} and c["use"] == "pref-021"
                              for c in d["conflicts"])
            rows.append({
                "records": len(profile.records),
                "full_tokens": len(text) // 4,
                "recall_tokens": len(out) // 4,
                "relevant_found": len(RELEVANT & got),
                "traps_excluded": len(TRAPS & excluded) if not (TRAPS & got) else 0,
                "conflict_ok": conflict_ok,
                "ms": round(ms, 1),
            })
    return rows


def main() -> int:
    rows = run()
    print("| Records | Whole profile (v1) | recall (v2) | Reduction | Relevant found | Traps excluded | Conflict resolved | recall time |")
    print("|---|---|---|---|---|---|---|---|")
    ok = True
    for r in rows:
        ok &= r["relevant_found"] == len(RELEVANT) and r["traps_excluded"] == len(TRAPS) and r["conflict_ok"]
        print(f"| {r['records']} | ~{r['full_tokens']:,} tokens | ~{r['recall_tokens']:,} tokens | "
              f"{r['full_tokens'] / max(r['recall_tokens'], 1):.0f}× | {r['relevant_found']}/{len(RELEVANT)} | "
              f"{r['traps_excluded']}/{len(TRAPS)} | {'yes' if r['conflict_ok'] else 'NO'} | {r['ms']} ms |")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

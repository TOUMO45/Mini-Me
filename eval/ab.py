#!/usr/bin/env python3
"""Blind A/B test: does the Mini Me profile reduce edits to acceptance?

  prepare  Shuffle the with-profile and without-profile outputs into A/B. The key is stored apart from them.
  record   Store the user's verdict: which output they accept, and what each would need to become.
  report   Per arm: preference wins, first-pass acceptance, word edits to acceptance, out-of-scope rules.

Only observed results are reported. Nothing is extrapolated.
"""
from __future__ import annotations

import argparse
import difflib
import json
import random
import re
import shutil
import sys
from pathlib import Path

ARMS = ("with", "without")


def words(text: str) -> list[str]:
    return re.findall(r"\S+", text)


def word_edits(shown: str, final: str) -> int:
    """Word-level edits needed to turn the shown output into the accepted text."""
    sm = difflib.SequenceMatcher(a=words(shown), b=words(final), autojunk=False)
    return sum(max(i2 - i1, j2 - j1) for op, i1, i2, j1, j2 in sm.get_opcodes() if op != "equal")


def task_dir(root: Path, task: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_.\-]+", task):
        raise SystemExit(f"invalid task id '{task}'")
    return root / task


def cmd_prepare(args) -> int:
    root = Path(args.dir)
    d = task_dir(root, args.task)
    if d.exists() and not args.force:
        raise SystemExit(f"{d} exists. Pass --force to overwrite")
    d.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)
    order = list(ARMS)
    rng.shuffle(order)
    key = {"A": order[0], "B": order[1]}
    sources = {"with": Path(args.with_profile), "without": Path(args.without_profile)}
    for label, arm in key.items():
        shutil.copyfile(sources[arm], d / f"{label}.md")
    keys_dir = root / ".keys"
    keys_dir.mkdir(exist_ok=True)
    (keys_dir / f"{args.task}.json").write_text(json.dumps(key), encoding="utf-8")
    print(f"Show the user {d / 'A.md'} and {d / 'B.md'}. The key is in {keys_dir}/: keep it hidden until `report`.")
    return 0


def cmd_record(args) -> int:
    root = Path(args.dir)
    d = task_dir(root, args.task)
    key = json.loads((root / ".keys" / f"{args.task}.json").read_text(encoding="utf-8"))
    finals = {"A": args.final_a, "B": args.final_b}
    result = {"task": args.task, "choice": args.choice}
    for label in ("A", "B"):
        arm = key[label]
        shown = (d / f"{label}.md").read_text(encoding="utf-8")
        entry = {"label": label}
        if finals[label]:
            entry["edits"] = word_edits(shown, Path(finals[label]).read_text(encoding="utf-8"))
        elif args.choice == label and args.accepted_as_is:
            entry["edits"] = 0
        result[arm] = entry
    result["out_of_scope"] = {"with": args.out_of_scope_with}
    with (root / "results.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(result) + "\n")
    print(f"Recorded {args.task}.")
    return 0


def load_results(root: Path) -> list[dict]:
    path = root / "results.jsonl"
    if not path.exists():
        return []
    latest: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            latest[r["task"]] = r  # a re-recorded task replaces the earlier verdict
    return list(latest.values())


def summarize(results: list[dict]) -> dict:
    out = {"tasks": len(results), "arms": {}}
    for arm in ARMS:
        edits = [r[arm]["edits"] for r in results if "edits" in r.get(arm, {})]
        wins = 0
        for r in results:
            if r["choice"] in ("A", "B") and r.get(arm, {}).get("label") == r["choice"]:
                wins += 1
        out["arms"][arm] = {
            "chosen": wins,
            "measured": len(edits),
            "first_pass_accepted": sum(1 for e in edits if e == 0),
            "mean_edits": round(sum(edits) / len(edits), 1) if edits else None,
        }
    out["neither"] = sum(1 for r in results if r["choice"] == "neither")
    oos = [r["out_of_scope"].get("with") for r in results if r["out_of_scope"].get("with") is not None]
    out["out_of_scope_rules_with_profile"] = sum(oos) if oos else None
    return out


def cmd_report(args) -> int:
    root = Path(args.dir)
    results = load_results(root)
    if not results:
        print("No results recorded yet.")
        return 0
    s = summarize(results)
    if args.json:
        print(json.dumps(s, indent=2))
        return 0
    print(f"Tasks: {s['tasks']} (neither accepted: {s['neither']})")
    print(f"{'arm':<10}{'chosen':>8}{'measured':>10}{'first-pass':>12}{'mean edits':>12}")
    for arm in ARMS:
        a = s["arms"][arm]
        mean = "-" if a["mean_edits"] is None else a["mean_edits"]
        print(f"{arm:<10}{a['chosen']:>8}{a['measured']:>10}{a['first_pass_accepted']:>12}{mean:>12}")
    if s["out_of_scope_rules_with_profile"] is not None:
        print(f"Rules applied outside their scope (with profile): {s['out_of_scope_rules_with_profile']}")
    if s["tasks"] < 5:
        print(f"Note: {s['tasks']} task(s) is too few to claim an effect. Report these counts, not a conclusion.")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ab", description=__doc__.splitlines()[0])
    p.add_argument("--dir", default="eval/runs", help="run directory (default eval/runs)")
    sub = p.add_subparsers(dest="cmd", required=True)

    pp = sub.add_parser("prepare")
    pp.add_argument("task")
    pp.add_argument("--with", dest="with_profile", required=True, help="output produced WITH the profile")
    pp.add_argument("--without", dest="without_profile", required=True, help="output produced WITHOUT the profile")
    pp.add_argument("--seed", type=int, default=None)
    pp.add_argument("--force", action="store_true")

    rp = sub.add_parser("record")
    rp.add_argument("task")
    rp.add_argument("--choice", required=True, choices=["A", "B", "neither"])
    rp.add_argument("--final-a", help="text the user would accept, starting from A")
    rp.add_argument("--final-b", help="text the user would accept, starting from B")
    rp.add_argument("--accepted-as-is", action="store_true", help="the chosen output needed no edits")
    rp.add_argument("--out-of-scope-with", type=int, default=None,
                    help="number of rules the with-profile output applied outside their scope")

    rep = sub.add_parser("report")
    rep.add_argument("--json", action="store_true")

    args = p.parse_args(argv)
    return {"prepare": cmd_prepare, "record": cmd_record, "report": cmd_report}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())

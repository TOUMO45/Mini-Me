# Mini Me: learn how I work

An agent skill that learns **what you chose, why, when it applies, and what justifies an exception**, then uses that to finish new work the way you would. Every inference can be traced to a source and corrected.

**Success metric:** fewer edits before you accept the result, on a task the agent has never seen.

```
skills/mini-me/
  SKILL.md                      the skill (shareable, no personal data)
  references/profile-format.md  memory record format
  templates/profile.template.md starting profile
  scripts/mini_me.py            validate / show / export / forget / next-id
eval/
  scenarios/                    test fixtures (S1–S3)
  rubrics.md                    pass/fail criteria, written before the runs
  results/                      graded baseline and with-skill runs
  ab.py                         blind A/B harness for your own held-out tasks
.claude/skills/mini-me -> ../../skills/mini-me   (Claude Code picks it up in this repo)
```

## Install

**Claude Code, in this repo:** nothing to do. `.claude/skills/mini-me` is already linked.

**Claude Code, everywhere:**

```bash
mkdir -p ~/.claude/skills && cp -r skills/mini-me ~/.claude/skills/
```

**A chat assistant with custom instructions:** paste the body of `skills/mini-me/SKILL.md` from the `# Mini Me` title down.

## Start your private profile

Records live **outside** this repo. `.gitignore` blocks `profile.md` as a safety net.

```bash
mkdir -p ~/.mini-me && cp skills/mini-me/templates/profile.template.md ~/.mini-me/profile.md
```

```bash
python3 skills/mini-me/scripts/mini_me.py validate
```

To keep the profile somewhere else, set `MINI_ME_PROFILE=/path/to/profile.md`, or pass `--profile`.

| Command | What it does |
|---|---|
| `validate` | Rejects stored credentials (without echoing them), duplicate or malformed IDs, `likely` records with fewer than 2 independent sources, broken `Supersedes` chains, the same source and decision recorded twice, and sensitive records without a stated purpose. Warns on expired exceptions |
| `show [--type] [--project] [--query]` | "What have you learned about me?" Groups records into stated by you, inferred, and said by others |
| `export [--include-sources] [--include-sensitive]` | A dated snapshot for another agent. Evidence and sensitive records are left out by default |
| `forget <ID>` | Removes the record and clears references to it. Refuses if the file changed underneath. Says what it can't reach |
| `next-id <prefix>` | The next stable ID |

## First prompt to try

> Mini Me, compare my draft with the version I accepted. Identify the working rules you can support and show the evidence for each. Apply those rules to the new task I attached. I'll tell you which conclusions apply generally and which were specific to the first task.

## How the skill was tested

The skill was written test-first. Fresh agents ran the same scenarios **without** the skill (baseline), then **with** it. Each output was graded against the rubrics in `eval/rubrics.md`, which were written before any run. Details: `eval/results/`.

| Scenario | Baseline | With skill |
|---|---|---|
| S1: draft vs accepted, new client | 7/9 | 8/9, then 9/9 after the revision |
| S2: imported chat (manager's rules, embedded injection, password, one-off) | 9/10 | 10/10 |
| S3: corrected rule + scope across clients (held out) | not run | see `eval/results/` |

The baseline is already strong. The skill fixes specific failures: an unexplained deletion turned into "never offer discounts", a manager's leadership-only rule applied to a client proposal, one-off inferences presented at the same confidence as explicit rules, and rationale placed before the deliverable. Each scenario ran once (n = 1), so these show behavior, not rates.

## Measure it on your own work

Hold back tasks that were never used to build your profile. For each one, produce an output with the profile and one without it, then:

```bash
python3 eval/ab.py prepare task-01 --with out-with.md --without out-without.md
```

Read `eval/runs/task-01/A.md` and `B.md` without opening `eval/runs/.keys/`, then record your verdict:

```bash
python3 eval/ab.py record task-01 --choice A --final-a accepted.md --final-b accepted.md --out-of-scope-with 0
```

```bash
python3 eval/ab.py report
```

The report shows only observed counts: wins, first-pass acceptance, word edits to acceptance, and rules applied outside their scope. With fewer than 5 tasks it says the sample is too small to claim an effect.

## Tests

```bash
python3 -m unittest discover -s skills/mini-me/scripts
```

```bash
python3 -m unittest discover -s eval
```

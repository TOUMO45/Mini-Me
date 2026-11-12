# Mini Me

**A portable memory for how you work, for any AI agent.** Mini Me learns what you chose, why, when it applies, and what justifies an exception. Then it finishes new work the way you would. Every inference is traceable to evidence and open to correction.

**Success metric:** fewer edits before you accept the result, on tasks the agent has never seen.

[![test](https://github.com/TOUMO45/Mini-Me/actions/workflows/test.yml/badge.svg)](https://github.com/TOUMO45/Mini-Me/actions/workflows/test.yml)

## Why it's different

| | Typical "AI memory" | Mini Me |
|---|---|---|
| What's stored | Facts and summaries | **Decision rules**: condition → action, scope, reason, evidence |
| Confidence | Everything looks equally true | `confirmed` (you said it) · `likely` (2+ independent sources) · `tentative` (one example) |
| One-off instructions | Leak into later work | `exc-` records with an expiry, never applied outside their scope |
| Your manager's or client's rules | Mixed into "your" preferences | Attributed (`Said by`) and limited to the scope they stated |
| Past decisions | Lost in old chats | **Decision history**: what you chose, between what, and why. Used as precedents for the next choice |
| "Which would I choose?" | A confident guess | A prediction **with its track record** ("right 1 of 3 times so far"), logged and checked against what you actually chose |
| Per-task cost | Grows with history | **~570 tokens**, flat from 61 to 4,000 records |
| Trust | Opaque | A plain Markdown file you own. It refuses to store credentials, and it can explain or forget any rule |
| Lock-in | One vendor | Claude Code skill, MCP server, AGENTS.md, CLI, or pasted instructions |

## How it works

```
 today's brief ──► recall ──► only the 8 records that matter ──► deliverable
                     ▲         (apply / inferred / others' / conflicts resolved / do-not-apply)
                     │
 your edits & corrections ──► add ──► merge, promote, supersede, validate ──► private profile.md
```

Each task runs the same loop: **Brief → Recall → Decide → Deliver → Learn**. Learning is built to need few examples:
- **Harvest the diff.** Every edit you make becomes one record.
- **Ask for one reason.** Ask why for the single most consequential edit. The reason is what transfers to new situations.
- **Compound.** A second independent example promotes a guess to `likely`. `review` suggests merges and resolves conflicts.
- **Decide from precedent.** Past decisions come back as precedents, with the reason behind each. Predictions are logged, then scored against your real choice.
- **Stay readable.** `explain <ID>` turns any rule into a plain sentence with its reason, confidence and history. `review` flags vague rules and rules with no reason.

## Quick start

```bash
python3 skills/mini-me/scripts/mini_me.py init
```

```bash
python3 skills/mini-me/scripts/mini_me.py add --type rule --condition "When writing a client proposal with fixed scope" --action "Lead with the fixed-fee option" --scope "Client proposals" --evidence '"Fixed scope, fixed fee first."' --sources chat-2026-10-01 --status confirmed
```

```bash
python3 skills/mini-me/scripts/mini_me.py recall "Draft a proposal for a new client, fixed-scope audit"
```

The profile lives at `~/.mini-me/profile.md`. Override it with `$MINI_ME_PROFILE` or `--profile`. Python 3.11+ (tested on 3.11, 3.12, 3.13), standard library only.

## Use it with your agent

| Agent | Setup |
|---|---|
| **Claude Code** | Works in this repo (`.claude/skills/mini-me`). Everywhere: `cp -r skills/mini-me ~/.claude/skills/` |
| **Claude Desktop, Cursor, any MCP client** | Add `skills/mini-me/scripts/mcp_server.py` as an MCP server. It provides 7 tools |
| **Codex and other AGENTS.md readers** | `AGENTS.md` points them to the skill and `recall` |
| **ChatGPT, Gemini, chat UIs** | Paste the SKILL.md body as instructions. Paste a `recall` or `export` block per task |
| **Your own agent (API)** | Put the SKILL.md body in the system prompt and inject `recall` output per task |

Copy-paste configs: [`skills/mini-me/references/integration.md`](skills/mini-me/references/integration.md).

## Commands

| Command | Purpose |
|---|---|
| `init` | Create a private profile (mode 600) |
| `recall "<brief>"` | The relevant records only, grouped and with conflicts resolved. `--json` available |
| `add …` | Record, merge, promote, or supersede. Validated before writing. Credentials refused |
| `add --type dec …` · `choose dec-N` | Log a prediction for a decision, then record what you actually chose |
| `explain <ID>` | "Why did you do that?": the rule as a plain sentence, with reason, confidence, evidence and history |
| `history` | "What did I decide before?": decisions, lessons and corrections, newest first |
| `stats` | How well Mini Me knows you: rules by confidence, reasons known, prediction track record |
| `review` | Suggestions for promotions, merges, conflicts, expired exceptions, stale guesses, open decisions, and unclear rules. Applies nothing |
| `show` | "What have you learned about me?": stated, inferred, said by others |
| `export` | A dated snapshot for another agent. Evidence and sensitive records are left out by default |
| `forget <ID>` | Delete a record and its references. It says what it can't reach |
| `validate` · `next-id` | Check the file · get the next stable ID |

## Evidence

The skill was built test-first. Fresh agents ran each scenario without the skill, then with it, graded against rubrics written in advance ([`eval/rubrics.md`](eval/rubrics.md)).

| Scenario | No skill | v1 | v2 |
|---|---|---|---|
| S1: your draft vs accepted version, new client | 7/9 | 9/9 | 9/9 |
| S2: imported chat with a manager's rules, injection, password | 9/10 | 10/10 | 10/10 |
| S3: corrected rule, cross-client scope (held out) | — | 6/6 | 6/6 |
| S4: 61-record profile with 5 traps | — | 8/8 | 8/8 |
| S5: "Which would I choose?" from decision history | — | 7/8 (v2.1: couldn't log the prediction) | **8/8** (v2.2) |

`python3 eval/bench_scale.py`:

| Records | Whole profile | `recall` | Relevant found | Traps excluded |
|---|---|---|---|---|
| 61 | ~6,100 tokens | ~570 | 6/6 | 2/2 |
| 1,010 | ~101,000 | ~570 | 6/6 | 2/2 |
| 4,010 | ~404,000 | ~610 | 6/6 | 2/2 |

What this does **not** show: each scenario ran once (n = 1), and the fixtures and benchmark distractors are synthetic. Whether Mini Me reduces *your* edits is measured on your own held-out tasks with the blind A/B harness:

```bash
python3 eval/ab.py prepare task-01 --with out-with.md --without out-without.md
```

```bash
python3 eval/ab.py record task-01 --choice A --final-a accepted.md --final-b accepted.md
```

```bash
python3 eval/ab.py report
```

Details: [`eval/results/`](eval/results/).

## Repository

```
skills/mini-me/
  SKILL.md                    operating loop (what agents load)
  references/spec.md          full specification
  references/profile-format.md
  references/integration.md   setup for every agent type
  scripts/mini_me.py          engine + CLI
  scripts/mcp_server.py       MCP server
  templates/profile.template.md
eval/                         scenarios, rubrics, results, A/B harness, scale benchmark
AGENTS.md  CHANGELOG.md  .github/workflows/test.yml
```

## License

[MIT](LICENSE) © 2026 Kamari Fatima Zuhra. Free to use, modify, and share, including commercially.

## Privacy

Your profile never belongs in this repository. `.gitignore` blocks `profile.md`, and `init` creates the file readable only by you. The engine refuses anything shaped like a password, token, or key, and reports it without echoing the value. Sensitive personal facts are stored only when you say what to keep and why.

## Tests

```bash
python3 -m unittest discover -s skills/mini-me/scripts
```

```bash
python3 -m unittest discover -s eval
```

```bash
python3 eval/bench_scale.py
```

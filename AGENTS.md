# AGENTS.md

Instructions for AI coding agents working in this repository (Codex, Claude Code, Cursor, and others).

## What this repo is

Mini Me: an agent skill plus a stdlib-only Python engine that learns a user's working rules and recalls the relevant ones for each new task.

- `skills/mini-me/SKILL.md`: the skill. Keep it an operating summary. Details go in `skills/mini-me/references/`.
- `skills/mini-me/scripts/mini_me.py`: profile engine (CLI and library). `mcp_server.py`: the same operations over MCP.
- `eval/`: scenarios, pre-registered rubrics, graded results, the A/B harness, and the scale benchmark.

## Using Mini Me as an agent

If the user wants work done their way, follow `skills/mini-me/SKILL.md`. Start each task with:

```bash
python3 skills/mini-me/scripts/mini_me.py recall "<task brief>"
```

## Rules for changing this repo

- **Python standard library only.** No dependencies: the engine must run anywhere an agent has `python3`.
- **Never commit a real profile.** `.gitignore` blocks `profile.md` outside `eval/scenarios/`. Fixtures use invented people and clients.
- **Test before claiming.** Run both suites and the benchmark. Each must pass:

```bash
python3 -m unittest discover -s skills/mini-me/scripts
```

```bash
python3 -m unittest discover -s eval
```

```bash
python3 eval/bench_scale.py
```

- **Behavior changes to SKILL.md need evidence.** Re-run the affected scenarios in `eval/scenarios/` with a fresh agent, grade them against `eval/rubrics.md`, and record the result in `eval/results/`. Add a rubric row *before* the run when you add a scenario.
- **Report observed results only.** Each scenario run is n = 1. Don't present it as a rate.

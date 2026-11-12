# Changelog

## 2.2.1 — 2026-11-12

### Fixed
- **Recall precision.** A single shared word ("client", "review") no longer pulls in unrelated rules. An untriggered rule now needs two distinct brief words in its condition or action, and a trigger needs two matching words when the condition has two or more. On the Halden brief: 7 records instead of 12, with all 6 relevant rules and both traps still handled at every benchmark size (regression test added).
- The per-task cost is now measured at **~610 tokens** (it was ~570 before recall started showing the "check scope" group). The reel, infographic, posts and README now say "~600".

### Added
- A professional README: hero banner (also usable as the GitHub social preview), badges, an animated reel preview linked to the full video, the infographic, a real `recall` terminal screenshot, and a flowchart. All visuals rebuild from `docs/assets/src/`.

## 2.2.0 — 2026-11-12

**Remembers your decisions, not only your rules.**

### Added
- **Decision records (`dec-`)**: question, options, your choice, your reason, and Mini Me's prediction, kept separately. `add --type dec … --predicted …` logs a prediction. `choose dec-N --choice … --reason …` records what you actually chose and scores the prediction.
- **Precedents in `recall`**: past decisions similar to today's question, with the reason behind each, plus the **prediction track record**. They never use up the rule budget.
- **`explain <ID>`**: one record in plain language: what it makes the agent do, why, how sure, the evidence, and what it replaced or was replaced by.
- **`history`**: a timeline of decisions, lessons and corrections, newest first, filterable by project and date.
- **`stats`**: rules by confidence, how many have a known reason, open decisions, and prediction accuracy.
- **Clarity checks in `review`**: conditions that don't say when a rule applies, vague actions ("better", "properly"), overlong actions, important rules with no reason, decisions left open for more than 14 days, and a low prediction track record.
- MCP tools `mini_me_choose`, `mini_me_explain`, `mini_me_history`, `mini_me_stats`.
- SKILL.md: a "Which would I choose?" protocol and a "Write rules anyone can apply" standard. Scenario S5 and its rubric.

### Changed
- **License: MIT**, © 2026 Kamari Fatima Zuhra. This replaces the noncommercial + Pro dual license from 2.1.0.

## 2.1.0 — 2026-11-11

### Licensing
- Dual license: free under the **PolyForm Noncommercial License 1.0.0** (official text, verified against SPDX), or under the **Mini Me Pro License 1.0** for work and client use.
- `LICENSING.md`: a plain-language guide covering who needs Pro and what Pro includes.
- SPDX headers in the scripts, a `license` field in SKILL.md, and a license notice from `init`.
- `tools/package_skill.py` ships all three license files, writes the Pro purchase URL (`--pro-url`), and refuses to build if the PolyForm text was altered, the root and skill licenses differ, or a header is missing.

## 2.0.0 — 2026-11-11

**Recall instead of rereading.** The agent loads the ~8 records that matter for today's task, not the whole profile. Per-task memory cost stays at ~570 tokens from 61 to 4,000 records (`eval/bench_scale.py`).

### Added
- `recall "<brief>"`: retrieval ranked by BM25 plus a trigger-condition match. Groups results into: apply, apply with care (inferred), others' constraints, project state, check scope (names a different client), possible conflicts resolved by the latest explicit correction, and do not apply (superseded or expired). `--json` for programs.
- `add`: structured writes. Assigns IDs, merges a repeat of the same decision, promotes `tentative` → `likely` on a second independent source, upgrades to `confirmed` on an explicit statement, and marks superseded records. It validates before writing, so an invalid record or a credential leaves the file untouched.
- `review`: suggests promotions, merges, conflicts, retirements of expired exceptions, stale single-example guesses, and unbounded scopes. Applies nothing.
- `init`: creates a private profile with mode 600.
- `scripts/mcp_server.py`: stdlib MCP server (stdio JSON-RPC) exposing recall, add, show, review, export, forget, and validate to Claude Desktop, Cursor, and any MCP client.
- `references/integration.md` (setup for every agent type), `AGENTS.md`, a CI workflow, the scale benchmark, and scenario S4 (61 records, 5 traps).
- SKILL.md: a five-step loop (Brief → Recall → Decide → Deliver → Learn), a "learn more from less" section (diff harvest, one-reason question, generalize through reasons, compounding, cold start), and red flags. The full specification moved, intact, to `references/spec.md`.

### Fixed during v2 testing
- Recall dropped records when one record dominated the score.
- Recall listed another client's rule under "Apply".
- Recall missed a rule over wording ("directions" vs "options").

## 1.0.0 — 2026-11-11

Initial skill, private Markdown profile format, `validate`/`show`/`export`/`forget`/`next-id`, scenarios S1–S3 with pre-registered rubrics, and the blind A/B harness.

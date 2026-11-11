# Changelog

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

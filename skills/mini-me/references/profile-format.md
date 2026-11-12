# Mini Me profile format

The profile is a private Markdown file. It holds records only, not these skill instructions.

**Location** (first match wins): the path the user names → `$MINI_ME_PROFILE` → `~/.mini-me/profile.md`.
Never commit it to a shared repository. Start from `templates/profile.template.md`.

Prefer `mini_me.py add` to hand-editing. It assigns the ID, merges duplicates, promotes evidence, and validates before writing. If you edit by hand, run `validate` afterwards.

## Record shape

One `###` heading per record, then one `- Field: value` bullet per field.

```markdown
### rule-003 · Decision rule
- Condition: When a client proposal's scope is expected to change a lot
- Action: Lead with the time-and-materials option
- Scope: Client proposals
- Exceptions: none known
- Evidence: "Hallam's scope is going to move a lot and fixed fee would burn us."
- Sources: chat-2026-09-14-hallam
- Reason: Scope volatility makes fixed fee unprofitable
- Status: confirmed
- Source date: 2026-09-14
- Updated: 2026-09-14
- Supersedes: —
- Sensitivity: ordinary
```

## Types and ID prefixes

| Type (heading) | Prefix | Extra required fields |
|---|---|---|
| Goal | `goal-` | Condition, Action, Scope |
| Preference | `pref-` | Condition, Action, Scope |
| Decision rule | `rule-` | Condition, Action, Scope |
| Problem-solving method | `method-` | Condition, Action, Scope |
| Exception | `exc-` | Condition, Action, Scope, Expires |
| Sensitive constraint | `sens-` | Condition, Action, Scope, Purpose |
| Project state | `proj-` | Project, Latest version, Last decision, Next step |
| Decision | `dec-` | Question, Options, Choice (or `pending` with `Predicted`) |

Every record needs: Evidence, Sources, Reason, Status, Source date, Updated, Sensitivity.

Optional on any record: `Said by` (default: the user. Name the person when a manager, client, or colleague said it), `Exceptions`, `Completed`, `Expires`, `Purpose`.

Optional on `proj-` records: `Constraints`, for a client's or audience's stated requirements (brief, tone, accessibility level). These describe the client, not the user, so they stay with the project.

## Field rules

- **ID**: stable. Never renumber. Get the next free one with `python3 scripts/mini_me.py next-id <prefix>`.
- **Condition / Action**: a conditional another agent can apply. "When …, do …".
- **Sources**: comma-separated source IDs (a chat, a file, a date). Several summaries of one conversation share **one** source ID.
- **Reason**: the user's stated reason, or `unknown`. Never invent one.
- **Status**:
  - `confirmed`: the user stated it explicitly within this scope. A one-time instruction is `confirmed` with an `Expires` value.
  - `likely`: two or more independent sources support the same inference. The validator enforces this.
  - `tentative`: inferred from a single example.
  - `superseded`: replaced. The newer record names it in `Supersedes`.
- **Expires**: a date (`2026-12-31`) or a scope end (`end of Acme project`, `this task only`).
- **Sensitivity**: `ordinary` or `sensitive`. `sens-` records must be `sensitive`, `confirmed`, and carry the user's stated `Purpose`.
- **Never store** passwords, access keys, tokens, or private keys. The validator rejects common shapes of them.

## Decision

A choice the user made between options. These are the precedents recall uses for "which would I choose?". Log a prediction before the user decides (`Choice: pending`, status `tentative`), then record the real choice with `mini_me.py choose`. The prediction stays in `Predicted`, so the track record can score it.

```markdown
### dec-003 · Decision
- Question: Accept a 3-week rush job from Acme Logistics at a 30% higher rate?
- Options: Accept (+30% rate, 3 weeks, whole team); Decline
- Choice: Decline
- Predicted: Accept
- Evidence: "Decline. Rush jobs wrecked the team in Q2, the premium isn't worth it."
- Sources: chat-2026-10-06
- Reason: Rush jobs burned out the team in Q2; the rate premium did not compensate
- Status: confirmed
- Source date: 2026-10-06
- Updated: 2026-10-06
- Supersedes: —
- Sensitivity: ordinary
```

A pending decision can't be `confirmed`, and it must have a `Predicted` value.

## Project state

```markdown
### proj-001 · Project state
- Project: Borealis cold-chain dashboard
- Constraints: Formal tone in all written communication (Borealis kickoff)
- Latest version: drafts/borealis-week3-v2.md (accepted 2026-11-11)
- Last decision: Vendor B sensors, chosen 2026-11-14
- Completed: Week-3 update sent
- Next step: Draft week-4 update after VPN contact is named
- Evidence: User: "Sent. Go with B."
- Sources: chat-2026-11-14
- Reason: unknown
- Status: confirmed
- Source date: 2026-11-14
- Updated: 2026-11-14
- Supersedes: —
- Sensitivity: ordinary
```

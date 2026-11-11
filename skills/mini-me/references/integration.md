# Using Mini Me with any agent

The behavior lives in `SKILL.md`. The memory lives in one private Markdown file. Every integration below is a different way to give an agent those two things.

| Agent | Instructions | Memory access |
|---|---|---|
| Claude Code | Skill directory (auto-loaded) | CLI via shell, or MCP |
| Claude Desktop, Cursor, Windsurf, any MCP client | MCP server `instructions` + tool descriptions | MCP tools |
| Codex CLI, Jules, Aider, other `AGENTS.md` readers | `AGENTS.md` pointing at `SKILL.md` | CLI via shell |
| ChatGPT, Gemini, Claude.ai projects (no shell) | Paste the `SKILL.md` body into custom instructions | Paste a `recall` block or an `export` snapshot |
| Your own agent (API) | `SKILL.md` body in the system prompt | Call `recall` and inject the result |

## Claude Code

```bash
mkdir -p ~/.claude/skills && cp -r skills/mini-me ~/.claude/skills/
```

```bash
python3 ~/.claude/skills/mini-me/scripts/mini_me.py init
```

Inside this repository nothing is needed: `.claude/skills/mini-me` is already linked.

## MCP clients

Add this to the client's MCP configuration (`claude_desktop_config.json`, `.cursor/mcp.json`, and so on). Use absolute paths.

```json
{
  "mcpServers": {
    "mini-me": {
      "command": "python3",
      "args": ["/ABS/PATH/skills/mini-me/scripts/mcp_server.py"],
      "env": { "MINI_ME_PROFILE": "/ABS/PATH/.mini-me/profile.md" }
    }
  }
}
```

Claude Code can register it from the shell:

```bash
claude mcp add mini-me -e MINI_ME_PROFILE="$HOME/.mini-me/profile.md" -- python3 "$PWD/skills/mini-me/scripts/mcp_server.py"
```

Tools: `mini_me_recall`, `mini_me_add`, `mini_me_show`, `mini_me_review`, `mini_me_export`, `mini_me_forget`, `mini_me_validate`. The server tells the agent at initialization to call `mini_me_recall` before work the user wants done their way. `mini_me_forget` is marked destructive, so clients that confirm destructive tools will ask the user first.

## AGENTS.md readers (Codex and others)

The repository root `AGENTS.md` already points agents to the skill. To use Mini Me in another repository, add:

```markdown
## Working the user's way
Before producing work for the user, follow /ABS/PATH/skills/mini-me/SKILL.md.
Recall: python3 /ABS/PATH/skills/mini-me/scripts/mini_me.py recall "<task brief>"
```

## Chat assistants without a shell

1. Paste the body of `SKILL.md`, from `# Mini Me` down, into custom instructions or project instructions.
2. Before a task, run `recall "<brief>"` locally and paste its output into the chat. For a project, paste an `export` snapshot as a project file.
3. When the assistant gives you records to keep, save them with `add` or paste them into the profile, then run `validate`.

An export is a snapshot dated when it was made. Re-export after the profile changes.

## Your own agent (API)

Put the skill body in the system prompt and inject only the relevant memory for each task:

```python
import subprocess

def mini_me_context(brief: str) -> str:
    return subprocess.run(
        ["python3", "skills/mini-me/scripts/mini_me.py", "recall", brief],
        capture_output=True, text=True, check=True,
    ).stdout

system_prompt = SKILL_BODY + "\n\n" + mini_me_context(task_brief)
```

Record corrections with `mini_me.py add … ` or `--json -` from your agent loop, and check the exit code. A non-zero exit means nothing was written.

## Session-only mode

Without a store, follow the same loop from the conversation. When the user asks to keep a lesson, give a copyable record in `profile-format.md` form and say what to bring into the next session.

## Sharing across agents

All agents can share one profile file. Writes are atomic, and every write checks that the file hasn't changed since it was read: a conflicting concurrent write fails instead of overwriting. Agents on other machines need a synced file (a private Git repository, or a synced folder) with write access only for agents the user trusts.

# Install Mini Me

Requires Python 3.11+ (standard library only, nothing to `pip install`).

## 1. Put the skill where your agent reads skills

**Claude Code (all projects):** unzip so this folder becomes `~/.claude/skills/mini-me/`.

```bash
unzip mini-me-v2.0.0.zip -d ~/.claude/skills/
```

**Claude.ai / Claude apps:** upload the zip as a custom skill (Settings → Capabilities → Skills), if your plan supports custom skills.

**Other agents:** see `references/integration.md` (MCP clients, Codex/AGENTS.md, chat assistants, your own API agent).

## 2. Create your private profile

```bash
python3 ~/.claude/skills/mini-me/scripts/mini_me.py init
```

This creates `~/.mini-me/profile.md`, readable only by you. To keep it elsewhere, set `MINI_ME_PROFILE`.

## 3. Optional: connect it as MCP tools (Claude Desktop, Cursor, any MCP client)

```json
{
  "mcpServers": {
    "mini-me": {
      "command": "python3",
      "args": ["/ABSOLUTE/PATH/mini-me/scripts/mcp_server.py"],
      "env": { "MINI_ME_PROFILE": "/ABSOLUTE/PATH/.mini-me/profile.md" }
    }
  }
}
```

## 4. First prompt to try

> Mini Me, compare my draft with the version I accepted. Identify the working rules you can support and show the evidence for each. Then apply them to this new task: …

## Check it works

```bash
python3 ~/.claude/skills/mini-me/scripts/mini_me.py recall "draft a client proposal"
```

With a new profile this prints "No records match this brief". That's expected until it has learned something.

# repro-mcp

> [!NOTE]
> **Should I use `repro-mcp` or `repro-git-hook`?**
> 
> If you are looking for an infallible, automated audit trail that doesn't rely on the AI remembering to log its own decisions, we strongly recommend using the sister project: **[repro-git-hook](https://github.com/ABindoff/repro-git-hook)**. 
>
> **When to use `repro-mcp`:**
> `repro-mcp` relies on "In-band" logging (the AI must actively call the MCP logging tools). While AI agents sometimes forget to do this when tackling complex coding problems, **`repro-mcp` has one major advantage: it does not require Git.** This makes it the perfect tool for auditing non-code workflows like document creation, legal drafting, or policy writing where a git repository isn't being used.
>
> **When to use `repro-git-hook`:**
> If you are working in a Git-tracked coding environment, `repro-git-hook` provides an infallible audit trail by operating "Out-of-band" — it passively hooks into your `git commit` lifecycle to run reproducibility linting, detect secrets, and extract native IDE transcripts automatically.
> **To install `repro-git-hook` instantly:**
> Add the following to your project's `.git/hooks/pre-commit` (requires [uv](https://docs.astral.sh/uv/)):
> ```bash
> #!/bin/bash
> uvx --from git+https://github.com/ABindoff/repro-git-hook repro-hook pre-commit
> ```

An MCP server that brings reproducibility logging to AI-assisted scientific computing.

Git records *what* changed. `repro-mcp` records *why* — logging prompts, responses, methodological decisions, and environment snapshots to human-readable markdown files that live alongside your code.

Built for researchers working under privacy or funding constraints who run models locally and need an audit trail that holds up to peer review.

---

## Why this exists

AI coding assistants are increasingly used in scientific workflows, but the interaction between a researcher and an AI — the prompts, the reasoning, the alternatives considered — disappears when the session ends. This matters because:

- A methods section can't cite a conversation
- A future collaborator can't reproduce your reasoning, only your code
- Environment drift silently breaks analyses months later

`repro-mcp` captures all of this locally. No cloud dependency. No data leaves the machine.

---

## How it works

`repro-mcp` is a [Model Context Protocol](https://modelcontextprotocol.io) server. Any MCP-compatible AI client (Claude Code, Cline, Cursor, Continue) can connect to it. It exposes tools the AI can call to:

- Open a session and snapshot the environment
- Log each prompt/response exchange
- Record significant decisions and the alternatives that were rejected
- Check code against reproducibility rules before it runs
- Close the session with a git diff summary

All output goes to `.repro/` in your project directory — plain markdown, git-friendly, human-readable.

---

## Installation

Requires Python 3.11+. The recommended way is via [`uv`](https://docs.astral.sh/uv/):

```bash
# No install step — uvx runs it in an isolated environment
uvx repro-mcp
```

Or with pip:

```bash
pip install repro-mcp
```

Or from source:

```bash
git clone https://github.com/ABindoff/repro-mcp.git
cd repro-mcp
pip install -e .
```

---

## Configuration

### Claude Code

Add it manually to `.mcp.json` in your project root (recommended — checked into git alongside your code):

```json
{
  "mcpServers": {
    "repro-mcp": {
      "command": "uvx",
      "args": ["repro-mcp"]
    }
  }
}
```

Or register globally via the Claude Code CLI:

```bash
claude mcp add repro-mcp --scope user -- uvx repro-mcp
```

Verify it's running with `claude mcp list`.

#### Auto-start via hooks (recommended)

Calling `session_start` manually triggers a permission prompt. The better approach is a `UserPromptSubmit` hook that auto-starts a session on your first message — no prompts, no manual steps.

Add this to `~/.claude/settings.json` (global, applies to all projects):

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "repro start",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

The `repro` command is installed alongside `repro-mcp`. It auto-detects the project name from your current directory and uses `"Claude Code session"` as the default goal. You can override either:

```bash
repro start my-project "Fit Cox model to patient cohort"
```

The hook is idempotent — if a session is already active it exits silently, so firing on every message is safe.

#### Ending a session

Close the active session from the terminal when you're done:

```bash
repro end success       # or: abandoned, inconclusive
repro end success --notes "Switched to Efron method"
```

Or call `session_end` via the MCP tool if you've allowlisted repro-mcp tools (add `"mcp__repro-mcp__*"` to the `permissions.allow` array in `~/.claude/settings.local.json`).

#### Allowlisting MCP tools (optional)

If you want to call repro-mcp tools directly (e.g. `log_decision`, `log_exchange`) without permission prompts, add this to `~/.claude/settings.local.json`:

```json
{
  "permissions": {
    "allow": ["mcp__repro-mcp__*"]
  }
}
```

### Cline (VS Code extension)

Open Cline settings → MCP Servers → add:

```json
{
  "repro-mcp": {
    "command": "python",
    "args": ["-m", "repro_mcp.server"],
    "cwd": "${workspaceFolder}"
  }
}
```

### Cline SDK / CLI

Use the `afterModel` hook to log every turn automatically:

```python
from cline import AgentPlugin

repro_plugin: AgentPlugin = {
    "hooks": {
        "afterModel": async ({ snapshot, assistantMessage }) => {
            await mcpClient.callTool("log_exchange", {
                "session_id": your_session_id,
                "prompt": snapshot.lastUserMessage,
                "response": assistantMessage.content,
            })
        }
    }
}
```

---

## Tools

| Tool | Description |
|---|---|
| `session_start` | Open a session, snapshot the environment, create the log file |
| `session_end` | Close the session, write git diff summary, update the index |
| `log_exchange` | Log a prompt/response pair with optional tags |
| `log_decision` | Log a methodological decision with rationale and alternatives |
| `snapshot_environment` | Capture a mid-session environment snapshot |
| `check_rules` | Check code against reproducibility rules before running |

---

## Log format

Each session produces `.repro/logs/YYYY-MM-DDTHHMMSS.md`:

```markdown
# Session: 2026-05-14T143022
**Project:** survival-analysis
**Goal:** Fit Cox model to patient cohort, compare AIC across covariates
**Branch:** feature/cox-model
**Git hash:** a3f9c12d8e41

### Environment snapshot `2026-05-14T14:30:22+00:00`
- **Python:** 3.11.4
- **Platform:** Linux 6.5.0 (x86_64)
- **Git:** `a3f9c12d8e41` (feature/cox-model)

**Packages:**
```
lifelines==0.29.0
numpy==1.26.4
pandas==2.2.1
```

---

## Exchange — 14:30:45
**Prompt:** How should I handle tied survival times in the Cox model?
**Response:** The three standard methods are Breslow, Efron, and Exact...
**Tags:** `model-fit`

---

## Decision — 14:47:12
**Decision:** Use Efron method for tie handling
**Rationale:** More accurate than Breslow when tie rate exceeds ~5%; our cohort has ~12% tied events
**Alternatives considered:** Breslow (rejected — bias at this tie rate); Exact (rejected — O(n!) complexity at n=14k)

---

## Session close — 15:45:00
**Outcome:** success

**Git diff summary:**
```
3 files changed, 142 insertions(+), 7 deletions(-)
```
```

An index of all sessions is maintained at `.repro/index.md`.

---

## Rules

`repro-mcp` ships with five built-in rules. Configure them by copying `repro_defaults/rules.yaml` to `.repro/rules.yaml` in your project.

| Rule | Severity | What it checks |
|---|---|---|
| `random-seed` | error | Any RNG call must have a seed set in scope |
| `env-pinned` | warn | `requirements.txt` / `environment.yml` must pin versions |
| `no-hardcoded-paths` | error | No absolute paths outside of config files |
| `no-inplace-data-mutation` | warn | Raw data directories should not be written to |
| `gpu-nondeterminism` | info | CUDA ops detected without determinism flags |

To disable a rule:

```yaml
# .repro/rules.yaml
rules:
  gpu-nondeterminism:
    enabled: false
```

---

## Project layout

```
your-project/
└── .repro/
    ├── index.md              # table of all sessions
    ├── rules.yaml            # rule configuration (optional)
    └── logs/
        ├── 2026-05-14T143022.md
        └── 2026-05-14T160011.md
```

Add `.repro/logs/` to `.gitignore` if you want to keep logs local, or commit them to give collaborators the full audit trail.

---

## Roadmap

- [x] Publish to PyPI
- [ ] Cline upstream PR: `PostAssistantTurn` hook for automatic `log_exchange` calls in the VS Code extension
- [ ] `data-provenance` rule: flag data loading that doesn't reference a hash or versioned source
- [ ] Export session log as a structured methods-section draft

---

## Contributing

Issues and PRs welcome. The Cline integration gap (automatic per-turn logging in the VS Code extension) is the most impactful open problem — see the [Cline repo](https://github.com/cline/cline) if you want to help.

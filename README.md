# laya-service

A self-hosted "hot and ready" decision service for LLMs that orchestrate
projects and tasks. It runs [Laya](https://github.com/NandhaKishorM/laya) — a
fast, non-autoregressive decision model — behind a small HTTP API, and exposes
it to agents through an MCP server.

Laya answers bounded questions. It does not generate text. Your orchestration
code owns thresholds and side effects; Laya just returns `choice`, `score`, or
`noul` answers with calibrated probabilities and confidence.

## What this is

Two processes:

1. **A service** that loads the Laya model once at startup and answers requests
   over HTTP. One process, one resident model, no cold loads per request.
2. **An MCP server** that agents plug into. It turns `laya_choice`,
   `laya_score`, and `laya_noul` tool calls into HTTP requests to that service.

```
agent  ──(stdio MCP)──>  mcp_server  ──(HTTP)──>  laya-service  ──>  Laya model
```

This mirrors how the open-source ecosystem wires up
[TypeSafe Jev](https://typesafe.ai): the model exposes a typed-decision surface,
and an MCP server (or an agent skill) is the thin layer that puts it in front of
an LLM.

## Install

```bash
cd laya-service
uv venv .venv
source .venv/bin/activate
uv pip install -e ".[full]"        # service + MCP + Laya model
```

For a wiring-only smoke test with no model:

```bash
uv pip install -e ".[server,dev]"
```

## Run the service

```bash
laya-service
# or, explicitly:
uvicorn laya_service.server:app --host 127.0.0.1 --port 8000
```

Check it is warm:

```bash
curl http://127.0.0.1:8000/healthz
```

### Settings (environment variables)

| Variable | Default | Meaning |
| --- | --- | --- |
| `LAYA_DEVICE` | auto | `cuda`, `mps`, or `cpu`. Auto picks cuda > mps > cpu. |
| `LAYA_PRELOAD` | `1` | Load the model at startup so requests never pay a cold load. |
| `LAYA_PRELOAD_MODELS` | all three | Comma list, e.g. `english`, to keep fewer checkpoints resident. |
| `LAYA_AUTO_TASK_DETECTION` | `0` | Opt in to typed-decisions workflow detection. |
| `LAYA_MOCK` | `0` | `1` runs a deterministic stub instead of the model. |
| `LAYA_HOST` / `LAYA_PORT` | `127.0.0.1` / `8000` | HTTP bind. |

The model is not installed on first boot until you `uv pip install -e ".[full]"`.
The `laya` README claims `torch 2.14` / `transformers 5.x`, but its actual
`pyproject.toml` uses `torch>=2.0`, `transformers>=4.48`, `safetensors>=0.4`,
`huggingface_hub>=0.20`, and `numpy>=1.20`.

## Run as a background service

`laya-mcp` (the MCP server) is per-session and can stay that way — it is
stateless and cheap. The **service** process is the one that holds the resident
model, so keep it alive if you want it truly hot-and-ready without a terminal.

### launchd (macOS)

```bash
laya-service --install-daemon    # writes ~/Library/LaunchAgents/com.laya.service.plist and loads it
laya-service --uninstall-daemon  # unloads and removes it
```

The agent runs at login with `KeepAlive` (auto-restart on crash), logs to
`~/Library/Logs/laya-service/`, and inherits `LAYA_DEVICE`, `LAYA_PRELOAD_MODELS`,
and `HF_TOKEN` from the environment at install time.

### Docker

```bash
docker compose up -d --build    # CPU torch image, starts on :8000, restarts on failure
```

Checkpoints persist in the `laya-hf-cache` volume, so restarts do not redownload.

## Call the API

`POST /v1/systemone` takes `{ state, questions }` and returns typed answers.

```bash
curl -s http://127.0.0.1:8000/v1/systemone \
  -H 'content-type: application/json' \
  -d '{
    "state": "We have 4 rooms to clean but only 2 cleaners on shift.",
    "questions": {
      "escalate": {
        "type": "noul",
        "instructions": "Does the situation need a human manager?"
      },
      "priority": {
        "type": "score",
        "instructions": "How urgent is the situation?",
        "criteria": ["routine", "soon", "now"]
      },
      "handler": {
        "type": "choice",
        "instructions": "Who should own this next step?",
        "criteria": {"ops": "cleaning operations", "support": "guest support", "none": "no one yet"}
      }
    }
  }'
```

Response shape (Laya's own `system_one` result plus a `routing` key):

```json
{
  "model": "laya-rl-agent",
  "answers": {
    "escalate": {"type": "noul", "noul": 0.87, "confidence": 0.87, "action": {"act_probability": 0.99}},
    "priority": {"type": "score", "score": 1.2, "legend": {"0": "routine", "1": "soon", "2": "now"},
                 "probabilities": {"0": 0.2, "1": 0.4, "2": 0.4}, "confidence": 0.71, "action": {"act_probability": 0.98}},
    "handler": {"type": "choice", "choice": "ops", "probabilities": {"ops": 0.7, "support": 0.2, "none": 0.1},
                "confidence": 0.62, "action": {"act_probability": 0.97}}
  },
  "usage": {"input_tokens": 96, "output_tokens": 0},
  "routing": {"model": "english", "reason": "English Latin text", "repo": "convaiinnovations/laya"}
}
```

A choice question also accepts an `options` list of plain strings. A score
question also accepts `rubric` or `levels` as the list of levels.

## Connect to your assistants

One service, one MCP entry. Each assistant only needs to know how to launch the
`laya-mcp` stdio server, which forwards tool calls to the running service.

### One command (recommended)

Run it from inside the venv. `laya-install-mcp` writes or merges the right config
for each client and never removes other servers:

```bash
laya-install-mcp                                  # all clients
laya-install-mcp --clients claude,opencode,codex  # pick some
laya-install-mcp --dry-run                        # preview first
```

| Assistant     | Config file (global/user scope)                    | Project scope equivalent |
| ---           | ---                                                | --- |
| Claude Code   | `~/.claude.json` via `claude mcp add --scope user` | `.mcp.json`              |
| opencode      | `~/.config/opencode/opencode.json`                 | `opencode.json`          |
| Codex         | `~/.codex/config.toml`                             | `.codex/config.toml`     |
| Cursor        | `~/.cursor/mcp.json`                               | `.cursor/mcp.json`       |
| Antigravity   | `~/.gemini/config/mcp_config.json`                 | `.agents/mcp_config.json`|

Why not a third-party "install to everything" CLI? None today covers all five —
Antigravity in particular is new. The shared *pattern* these tools converge on is
one stdio entry (`command` + `args` + `env`); the installer writes that same shape
into each client's own file.

### By hand, per assistant

The stdio entry is the same everywhere:

```json
{
  "command": "/absolute/path/to/laya-service/.venv/bin/python",
  "args": ["-m", "laya_service.mcp_server"],
  "env": { "LAYA_BASE_URL": "http://127.0.0.1:8000" }
}
```

`LAYA_BASE_URL` is the only variable the MCP client needs; it points at the
running service (default `http://127.0.0.1:8000`).

**Claude Code**

```bash
claude mcp add --env LAYA_BASE_URL=http://127.0.0.1:8000 \
  --transport stdio laya -- \
  /path/to/laya-service/.venv/bin/python -m laya_service.mcp_server
```

**opencode** — `~/.config/opencode/opencode.json`

```json
{
  "mcp": {
    "laya": {
      "type": "local",
      "command": ["/path/to/laya-service/.venv/bin/python", "-m", "laya_service.mcp_server"],
      "environment": { "LAYA_BASE_URL": "http://127.0.0.1:8000" },
      "enabled": true
    }
  }
}
```

**Codex** — `~/.codex/config.toml`

```toml
[mcp_servers.laya]
command = "/path/to/laya-service/.venv/bin/python"
args = ["-m", "laya_service.mcp_server"]

[mcp_servers.laya.env]
LAYA_BASE_URL = "http://127.0.0.1:8000"
```

**Cursor** — `~/.cursor/mcp.json` (Settings > MCP in the UI)

```json
{
  "mcpServers": {
    "laya": {
      "command": "/path/to/laya-service/.venv/bin/python",
      "args": ["-m", "laya_service.mcp_server"],
      "env": { "LAYA_BASE_URL": "http://127.0.0.1:8000" }
    }
  }
}
```

**Antigravity** — `~/.gemini/config/mcp_config.json` (note: remote transports
use `serverUrl`, not `url`)

```json
{
  "mcpServers": {
    "laya": {
      "command": "/path/to/laya-service/.venv/bin/python",
      "args": ["-m", "laya_service.mcp_server"],
      "env": { "LAYA_BASE_URL": "http://127.0.0.1:8000" }
    }
  }
}
```

Tools the agent gets:

- `laya_choice(state, instructions, options[, descriptions])` — pick one option.
- `laya_score(state, instructions, levels)` — score on an ordered rubric.
- `laya_noul(state, instructions)` — yes/no with a calibrated P(true).
- `laya_system_one(state, questions)` — raw batch of typed questions.
- `laya_guard(prompt)` — input guardrails (jailbreak, injection, sensitive data, harm, topic).
- `laya_moderate(post)` — content moderation (toxic, harassment, threat, spam, severity).
- `laya_triage(message)` — support triage (intent, urgency, frustration, refund, churn).
- `laya_triage_email(body)` — email triage (category, spam, phishing, urgency, reply).
- `laya_route(request)` — model routing (difficulty, domain, needs tools, sensitive).

The five preset tools wrap Laya's own tuned workflows (`laya/presets.py`), so
agents use the wording the checkpoint is calibrated for instead of hand-rolling
weaker questions.

To run the MCP server as a shared network endpoint instead of stdio:

```bash
laya-mcp --transport sse --base-url http://127.0.0.1:8000
```

No MCP at all? `skills/laya-decisions/SKILL.md` also documents a plain `curl`
fallback against `/v1/systemone`, so the service is usable from any tool that
can run a shell command.

## Design rule

The model only answers bounded questions. Your orchestration code reads the
`choice` / `score` / `noul` value plus its `probability` / `confidence`, then
decides what to do. Never let the model act — let it decide, then you branch.

## Agent skill

Ship `skills/laya-decisions/SKILL.md` to teach agents the decision contract:
what each tool returns, when to use `choice` vs `score` vs `noul` (vs a preset
tool), and the rule that the agent's own code owns thresholds and side effects.
The file is the same everywhere; only its location differs per assistant:

| Assistant     | Skill directory |
| ---           | --- |
| Claude Code   | `~/.claude/skills/laya-decisions/` (or `.claude/skills/`) |
| opencode      | `.opencode/skill/laya-decisions/` |
| Codex         | `~/.codex/skills/laya-decisions/` (or `.codex/skills/`) |
| Cursor        | `.cursor/skills/laya-decisions/` |
| Antigravity   | Agent Skills in Settings, or `.agents/skills/` |

### Install via the skills CLI

The maintained cross-assistant installer is Vercel's
[`skills` CLI](https://skills.sh) (`package` `skills`). It reads a GitHub
repo's `skills/` directory and configures the skill for every supported
agent, including Claude Code, opencode, Codex, Cursor, and Antigravity:

```bash
npx skills add <owner>/laya-service          # installs skills/laya-decisions/SKILL.md
```

This repo is already in the expected layout (one `SKILL.md` under
`skills/<name>/`). To be installable this way, push it to a public GitHub repo.
Add a badge once live:

```
[![skills.sh](https://skills.sh/b/<owner>/laya-service)](https://skills.sh/<owner>/laya-service)
```

### Install via skillz (PyPI MCP server)

[`skillz`](https://pypi.org/project/skillz) (Intellectronica, MIT) is an MCP
server that turns a directory of Claude-style `SKILL.md` files into MCP tools
for any MCP client — handy for agents without native skill support, like Copilot
or older Cursor setups. It expects a flat `skills/<name>/SKILL.md` layout, which
this repo already matches:

```bash
# point skillz at this repo's skills/ directory; skills appear as MCP tools
uvx skillz@latest /path/to/laya-service/skills
```

Skills live under `~/.skillz` by default. `skillz` is experimental and can run
bundled scripts, so treat skills as untrusted code.

Note: npm has no `skill add` command, and the npm package `skilz` (one "l") is
an empty placeholder. The real paths are the `skills` CLI/`skills.sh`, the PyPI
`skillz` MCP server, and the per-assistant skill directories above.

A shorter alternative is one line in the agent's own rules file
(`AGENTS.md` / rules):

> Use `laya_noul`, `laya_choice`, and `laya_score` for fast bounded decisions.
> Read the returned probability plus confidence, then apply your own threshold.
> Never let Laya take an action — you branch on its answer.

## Prior art

Same idea, already in the wild: [receptron/laya](https://github.com/receptron/laya)
(ONNX Runtime client for the Laya weights), the various
[Jev MCP servers](https://github.com/jkudish/jev-mcp), and
[jaredpalmer/kev](https://github.com/jaredpalmer/kev) (local Jev-style models).
This project is the Laya flavoured version: same typed-decision contract, one
self-hosted service, one MCP surface.
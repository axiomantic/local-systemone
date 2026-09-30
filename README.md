# local-systemone

A lightweight, universal self-hosted **System 1 decision daemon** and MCP server for AI agents, multi-agent swarms ([Rhizo](https://github.com/axiomantic/rhizo), [Garden](https://github.com/axiomantic/garden)), and orchestration loops.

Unlike generative LLMs that predict tokens autoregressively, a **System 1 model** evaluates input state text against typed question schemas (`choice`, `score`, `noul`) in a single forward pass, returning calibrated probabilities and confidence in milliseconds without parsing hallucinations.

---

## Supported Backends

`local-systemone` supports multiple pluggable backends exposing the standard Jev-compatible `POST /v1/systemone` endpoint:

| Engine | Flag / Environment | Description | Typical Latency |
| :--- | :--- | :--- | :--- |
| **`laya`** *(Default)* | `--engine laya`<br>`SYSTEMONE_ENGINE=laya` | Native **ModernBERT-large (421M)** & mmBERT-base (322M). Runs locally on Apple Silicon Metal (MPS), CUDA, or CPU with proper scoring calibration (RLCD). | **~25–45 ms** |
| **`ollama`** | `--engine ollama`<br>`OLLAMA_URL=http://127.0.0.1:11434` | Connects to a local Ollama instance running any model (e.g. `llama3.2`, `qwen2.5-coder`). | **~150–400 ms** |
| **`openai` / `llamacpp`** | `--engine openai`<br>`OPENAI_BASE_URL=http://127.0.0.1:8080/v1` | Connects to local `llama-server` (GGUF), vLLM, or LM Studio. | **~100–300 ms** |
| **`proxy` / `jev`** | `--engine proxy`<br>`UPSTREAM_URL=https://api.typesafe.ai` | Local caching proxy forwarding to cloud TypeSafe Jev API. | **~20–50 ms** (+ net) |
| **`mock`** | `--engine mock`<br>`SYSTEMONE_ENGINE=mock` | Deterministic stub for CI, unit testing, and offline test environments. | **<1 ms** |

---

## Installation

Install directly from GitHub via `pip` or `uv`:

```bash
# Core service + Laya neural engine + MCP tools:
pip install "git+https://github.com/axiomantic/local-systemone.git#egg=local-systemone[full]"

# Or using uv:
uv pip install "git+https://github.com/axiomantic/local-systemone.git#egg=local-systemone[full]"

# Or wiring only (Ollama/Proxy/OpenAI backends, zero torch dependency):
pip install "git+https://github.com/axiomantic/local-systemone.git#egg=local-systemone[server]"

# Or from a local clone:
git clone https://github.com/axiomantic/local-systemone.git
cd local-systemone
pip install -e ".[full]"
```

---

## Running the Service

### Foreground

```bash
# Default (Laya engine on Apple Silicon / CUDA / CPU, port 8100):
local-systemone

# Or run with a specific engine:
local-systemone --engine ollama
local-systemone --engine openai --port 8100
```

Verify reachability:
```bash
curl http://127.0.0.1:8100/healthz
# {"status":"ok","engine":"laya","mock":false,"loaded_models":["multilingual","typed-decisions","english"],"device":"mps"}
```

---

## Running as a Background Daemon

`local-systemone` includes built-in daemon management for macOS and Linux.

### macOS (`launchd`)

Install as a background LaunchAgent (runs automatically at login, restarts on failure, logs to `~/Library/Logs/local-systemone/`):

```bash
# Auto-install and load:
local-systemone --install-daemon

# Check status:
local-systemone --status-daemon

# Uninstall and unload:
local-systemone --uninstall-daemon
```

*Static template available at [`daemons/launchd/com.axiomantic.local-systemone.plist`](daemons/launchd/com.axiomantic.local-systemone.plist).*

### Linux (`systemd`)

Install as a systemd user service (managed by `systemctl --user`, logs to `journalctl`):

```bash
# Auto-install and enable user service:
local-systemone --install-daemon

# Check status:
systemctl --user status local-systemone.service

# Live logs:
journalctl --user -u local-systemone.service -f

# Uninstall:
local-systemone --uninstall-daemon
```

> [!TIP]
> **Headless Linux Servers**: Run `loginctl enable-linger $USER` to ensure the user service continues running after SSH logout.

*Static templates available at [`daemons/systemd/local-systemone-user.service`](daemons/systemd/local-systemone-user.service) and [`daemons/systemd/local-systemone.service`](daemons/systemd/local-systemone.service).*

---

## Integration with Rhizo

In your project with [Rhizo](https://github.com/axiomantic/rhizo):

1. Set your service URL in `.env.local` (or `rhizo-routes.yaml`):
```bash
# .env.local
RHIZO_SERVICE_URL="http://127.0.0.1:8100"
```

2. Validate service connectivity:
```bash
rhizo route lint --check-service
```

3. Route directives:
```bash
rhizo route "Fix memory leak in websocket reconnection handler"
rhizo enqueue --route "Fix memory leak in websocket reconnection handler"
```

---

## API Contract

`POST /v1/systemone`

```json
{
  "state": "Support ticket: Cannot access billing portal after password reset",
  "questions": {
    "domain": {
      "type": "choice",
      "instructions": "Which team handles this?",
      "criteria": {
        "auth": "login, MFA, password reset",
        "billing": "invoices, payment methods, receipts",
        "infrastructure": "network, server downtime"
      }
    },
    "urgency": {
      "type": "score",
      "instructions": "How urgent is this ticket?",
      "criteria": ["low priority", "standard triage", "blocking outage"]
    },
    "escalate": {
      "type": "noul",
      "instructions": "Does this require supervisor escalation?"
    }
  }
}
```

Response:
```json
{
  "model": "laya",
  "answers": {
    "domain": {
      "type": "choice",
      "choice": "auth",
      "probabilities": {
        "auth": 0.9412,
        "billing": 0.0514,
        "infrastructure": 0.0074
      },
      "confidence": 0.932
    },
    "urgency": {
      "type": "score",
      "score": 0.88,
      "confidence": 0.82
    },
    "escalate": {
      "type": "noul",
      "noul": 0.12,
      "confidence": 0.88
    }
  }
}
```

---

## MCP Server

Plug into Claude Desktop, Antigravity, OpenCode, or Cursor:

```bash
systemone-install-mcp
```

Or manually configure in `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "systemone": {
      "command": "systemone-mcp"
    }
  }
}
```

---

## License

MIT © [Axiomantic](https://axiomantic.org)
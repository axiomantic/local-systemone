"""Minimal MCP server exposing typed-decision tools over the HTTP service.

The MCP server is a thin client to the Laya service (`LAYA_BASE_URL`), so the
model stays resident in the single uvicorn process instead of being reloaded
inside every agent subprocess. It runs over stdio by default, which is what an
agent's MCP config spawns:

    .../python -m laya_service.mcp_server

Set `LAYA_BASE_URL` to point somewhere other than http://127.0.0.1:8000, or pass
`--base-url` / `--transport sse` for a shared network endpoint.
"""
from __future__ import annotations

import argparse
import os
from typing import Any, Dict, List, Optional

import httpx
from mcp.server.fastmcp import FastMCP

from .presets import PRESETS

BASE_URL = os.environ.get("LAYA_BASE_URL", "http://127.0.0.1:8000").rstrip("/")

mcp = FastMCP("laya")


def _system_one(payload: Dict[str, Any]) -> Dict[str, Any]:
    resp = httpx.post(f"{BASE_URL}/v1/systemone", json=payload, timeout=60.0)
    resp.raise_for_status()
    return resp.json()


def _strip_action(answer: Dict[str, Any]) -> Dict[str, Any]:
    out = {k: v for k, v in answer.items() if k != "action"}
    return out


@mcp.tool()
def laya_choice(
    state: str,
    instructions: str,
    options: List[str],
    descriptions: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Ask Laya to pick one of several options. Returns the top choice, per-option probabilities, and confidence."""
    criteria = {
        o: (descriptions[i] if descriptions and i < len(descriptions) else None)
        for i, o in enumerate(options)
    }
    res = _system_one(
        {
            "state": state,
            "questions": {"q": {"type": "choice", "instructions": instructions, "criteria": criteria}},
        }
    )
    return _strip_action(res["answers"]["q"])


@mcp.tool()
def laya_score(
    state: str,
    instructions: str,
    levels: List[str],
) -> Dict[str, Any]:
    """Ask Laya to score `state` on an ordered rubric. Returns an expected level index and the level distribution."""
    res = _system_one(
        {
            "state": state,
            "questions": {"q": {"type": "score", "instructions": instructions, "criteria": levels}},
        }
    )
    return _strip_action(res["answers"]["q"])


@mcp.tool()
def laya_noul(state: str, instructions: str) -> Dict[str, Any]:
    """Ask Laya a yes/no question. Returns a calibrated P(true) in [0, 1] plus confidence."""
    res = _system_one(
        {
            "state": state,
            "questions": {"q": {"type": "noul", "instructions": instructions}},
        }
    )
    return _strip_action(res["answers"]["q"])


@mcp.tool()
def laya_system_one(state: Any, questions: Dict[str, Any]) -> Dict[str, Any]:
    """Run an arbitrary batch of Laya typed questions against `state` in one forward pass."""
    return _system_one({"state": state, "questions": questions})


def _run_preset(field: str, questions: Dict[str, Any], value: str) -> Dict[str, Any]:
    res = _system_one({"state": {field: value}, "questions": questions})
    return {qid: _strip_action(a) for qid, a in res["answers"].items()}


@mcp.tool()
def laya_guard(prompt: str) -> Dict[str, Any]:
    """Run Laya's input-guardrail preset on a prompt: jailbreak, prompt injection, sensitive data, harm severity, topic."""
    field, questions = PRESETS["guard"]()
    return _run_preset(field, questions, prompt)


@mcp.tool()
def laya_moderate(post: str) -> Dict[str, Any]:
    """Run Laya's content-moderation preset on a post: toxic, harassment, threat, spam, severity."""
    field, questions = PRESETS["moderate"]()
    return _run_preset(field, questions, post)


@mcp.tool()
def laya_triage(message: str) -> Dict[str, Any]:
    """Run Laya's support-triage preset on a message: intent, urgency, frustration, refund requested, churn risk."""
    field, questions = PRESETS["triage"]()
    return _run_preset(field, questions, message)


@mcp.tool()
def laya_route(request: str) -> Dict[str, Any]:
    """Run Laya's model-routing preset on a request: difficulty, domain, needs tools, sensitive."""
    field, questions = PRESETS["route"]()
    return _run_preset(field, questions, request)


@mcp.tool()
def laya_triage_email(body: str) -> Dict[str, Any]:
    """Run Laya's email-triage preset on an email body: category, spam, phishing, urgency, needs reply."""
    field, questions = PRESETS["email"]()
    return _run_preset(field, questions, body)


def main() -> None:
    global BASE_URL
    parser = argparse.ArgumentParser(prog="laya-mcp")
    parser.add_argument("--base-url", default=BASE_URL, help="Laya service base URL")
    parser.add_argument(
        "--transport", default="stdio", choices=["stdio", "sse"], help="MCP transport"
    )
    args = parser.parse_args()
    BASE_URL = args.base_url.rstrip("/")
    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
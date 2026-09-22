---
name: laya-decisions
description: Use when the agent must decide, classify, score, or gauge confidence on a bounded question as part of orchestration (routing, priority, triage, guards, yes/no gates). Laya is a local System 1 typed-decision model exposed through the laya_choice, laya_score, laya_noul, and laya_system_one MCP tools, plus ready-made laya_guard, laya_moderate, laya_triage, laya_triage_email, and laya_route workflow tools. Trigger phrases — "should I escalate this", "how urgent", "pick the owner", "which of these next steps", "is this ready to merge", "triage this task", "moderate this post", "route this request", any need for a fast calibrated judgment instead of a generated paragraph.
---

# Laya decisions

## What Laya is

Laya is a decision model. It does not write text. You give it a short
`state` and one or more bounded questions; it returns a typed answer with
probabilities and a confidence number.

It is fast (tens of milliseconds) and local, so it suits hot-path decisions
inside an orchestration loop: routing, triage, priority, guards, and yes/no
gates. It is not a substitute for the main model when the task is to generate
or explain.

## The rule you must follow

Laya answers a bounded question. **Your code owns the thresholds, the action,
and any side effects.** Never let the answer act on its own. Read the value
plus its probability, compare against a threshold you set, then branch.

A high probability is not certainty. A `noul` of 0.62 means weak yes. Treat
`confidence` as calibration, not as permission to skip a guard.

## Tools

- `laya_choice(state, instructions, options, descriptions=[])` — pick one option.
  Returns `choice`, per-option `probabilities`, and `confidence`.
- `laya_score(state, instructions, levels)` — score on an ordered rubric.
  Returns an expected `score` index plus the level `probabilities`.
- `laya_noul(state, instructions)` — yes/no. Returns `noul`, the calibrated
  P(true) in [0, 1], plus `confidence`.
- `laya_system_one(state, questions)` — one batch of typed questions in a
  single forward pass. Use this when you have several questions on the same
  state; it is cheaper than several separate calls.

## Ready-made workflows (prefer these)

Laya ships tuned question sets for the jobs it is best at. Use the matching
tool instead of hand-rolling questions — the model's calibration is tuned to
this wording:

- `laya_guard(prompt)` — input guardrails: jailbreak, prompt injection,
  sensitive data, harm severity, topic.
- `laya_moderate(post)` — content moderation: toxic, harassment, threat, spam,
  severity.
- `laya_triage(message)` — support triage: intent, urgency, frustration,
  refund requested, churn risk.
- `laya_triage_email(body)` — email triage: category, spam, phishing, urgency,
  needs reply.
- `laya_route(request)` — model routing: difficulty, domain, needs tools,
  sensitive.

These are where Laya is appropriate. If the situation does not map to one of
them, fall back to the bare `laya_choice` / `laya_score` / `laya_noul` tools.

## How to phrase questions

- Put the situation in `state` as plain facts. Keep it short.
- Put the single decision in `instructions`. Ask a question, not for an essay.
- Use `laya_choice` when the answers are a fixed set of names.
- Use `laya_score` when the answers are ordered levels ("routine, soon, now").
- Use `laya_noul` when the answer is yes or no.
- Batch related questions with `laya_system_one`.

## Steering on the result

Read the returned value, then apply a threshold you own:

- If `confidence` is below your gate, defer or ask the human. Do not invent a
  decision from a faint number.
- On a `choice`, prefer the top option only when its probability clears your
  bar; otherwise treat the top two as a short list to resolve elsewhere.
- On a `noul`, decide your own `P(true)` boundary before you call it.
- Record the decision and the number you saw, so the loop stays auditable.

## If the MCP tools are not wired up

The skill works without MCP too. Call the HTTP service directly at
`http://127.0.0.1:8000/v1/systemone` with `{ "state", "questions" }` and read
`answers.<id>`. The preset workflows map to a dict state keyed by the field the
questions reference (`message`, `body`, `prompt`, `post`, `request`):

```bash
curl -s http://127.0.0.1:8000/v1/systemone \
  -H 'content-type: application/json' \
  -d '{
    "state": "We have 4 rooms to clean but only 2 cleaners on shift.",
    "questions": {
      "priority": {"type": "score", "instructions": "How urgent?", "criteria": ["routine", "soon", "now"]},
      "escalate": {"type": "noul", "instructions": "Does this need a human manager?"}
    }
  }'
```

Prefer the MCP tools when they are present; use this as the zero-install
fallback, applying the same thresholds you own.
"""Pluggable System One decision backends.

Supports:
- Laya (ModernBERT-large 421M / mmBERT-base 322M on Apple Silicon MPS / CUDA / CPU)
- Ollama (local LLM via http://127.0.0.1:11434)
- OpenAI-compatible (local llama-server GGUF / vLLM / LM Studio)
- Proxy (upstream TypeSafe Jev API or remote System 1 instance)
- Mock (deterministic stub for testing and CI)
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional

import httpx

State = Any
Questions = Dict[str, Dict[str, Any]]


class Backend:
    name: str = "base"
    device: str = "n/a"

    @property
    def loaded(self) -> List[str]:
        return []

    def predict(
        self,
        state: State,
        questions: Questions,
        model: Optional[str] = None,
        task: Optional[str] = None,
        lang: Optional[str] = None,
    ) -> Dict[str, Any]:
        raise NotImplementedError


class MockBackend(Backend):
    """Deterministic stub that mirrors System One result shape without downloading a model."""

    name: str = "mock"

    def __init__(self, device: str = "mock"):
        self.device = device

    @property
    def loaded(self) -> List[str]:
        return ["mock"]

    def predict(
        self,
        state: State,
        questions: Questions,
        model: Optional[str] = None,
        task: Optional[str] = None,
        lang: Optional[str] = None,
    ) -> Dict[str, Any]:
        answers: Dict[str, Any] = {}
        n_tokens = 0
        for qid, q in questions.items():
            n_tokens += 32
            t = q.get("type", "noul")
            if t == "noul":
                answers[qid] = {
                    "type": "noul",
                    "noul": 0.5,
                    "confidence": 0.5,
                    "action": {"act_probability": 1.0},
                }
            elif t == "choice":
                crit = q.get("criteria") or {}
                if isinstance(crit, list):
                    crit = {str(c): None for c in crit}
                keys = list(crit) or ["unknown"]
                probs = {k: round(1.0 / len(keys), 4) for k in keys}
                answers[qid] = {
                    "type": "choice",
                    "choice": keys[0],
                    "probabilities": probs,
                    "confidence": round(1.0 / len(keys), 4),
                    "action": {"act_probability": 1.0},
                }
            else:
                crit = q.get("criteria") or []
                if isinstance(crit, dict):
                    crit = [str(v) for v in crit.values()]
                k = len(crit) or 1
                mid = round((k - 1) / 2.0, 4)
                answers[qid] = {
                    "type": "score",
                    "score": mid,
                    "legend": {str(i): c for i, c in enumerate(crit)},
                    "probabilities": {str(i): round(1.0 / k, 4) for i in range(k)},
                    "confidence": round(1.0 / k, 4),
                    "action": {"act_probability": 1.0},
                }

        routing = {
            "model": "mock",
            "repo": "mock",
            "reason": "mock backend; no model loaded",
            "detection": None,
            "workflow": None,
        }
        return {
            "model": "systemone-mock",
            "answers": answers,
            "usage": {"input_tokens": n_tokens, "output_tokens": 0},
            "routing": routing,
        }


class LayaBackend(Backend):
    """Wraps a preloaded `laya.Router` (ModernBERT-large 421M / mmBERT-base 322M)."""

    name: str = "laya"

    def __init__(
        self,
        device: Optional[str] = None,
        preload: bool = True,
        preload_models: Optional[List[str]] = None,
        auto_task_detection: bool = False,
    ):
        from laya import Router

        self._router = Router(device=device, auto_task_detection=auto_task_detection, preload=False)
        if preload:
            self._router.preload(preload_models)

    @property
    def loaded(self) -> List[str]:
        return list(self._router.loaded)

    @property
    def device(self) -> str:
        for agent in self._router._agents.values():
            return str(agent.device)
        return "mps" if os.uname().sysname == "Darwin" else "cpu"

    def predict(
        self,
        state: State,
        questions: Questions,
        model: Optional[str] = None,
        task: Optional[str] = None,
        lang: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self._router.predict(state, questions, model=model, task=task, lang=lang)


class ProxyBackend(Backend):
    """Forwards requests to remote TypeSafe Jev API or another System 1 instance."""

    name: str = "proxy"
    device: str = "remote"

    def __init__(
        self,
        url: str = "https://api.typesafe.ai",
        api_key: Optional[str] = None,
        model: str = "jev-1",
        timeout: float = 30.0,
    ):
        self.url = url.rstrip("/")
        self.api_key = api_key or os.environ.get("JEV_API_KEY") or os.environ.get("SYSTEMONE_API_KEY") or ""
        self.model = model
        self.timeout = timeout

    @property
    def loaded(self) -> List[str]:
        return [f"proxy:{self.url}:{self.model}"]

    def predict(
        self,
        state: State,
        questions: Questions,
        model: Optional[str] = None,
        task: Optional[str] = None,
        lang: Optional[str] = None,
    ) -> Dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "state": state,
            "questions": questions,
            "model": model or self.model,
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(f"{self.url}/v1/systemone", json=payload, headers=headers)
                resp.raise_for_status()
                return resp.json()
        except Exception as exc:
            raise RuntimeError(f"Proxy request to {self.url} failed: {exc}") from exc


class OllamaBackend(Backend):
    """Bridge connecting a local Ollama instance to System 1 typed decision schemas."""

    name: str = "ollama"
    device: str = "ollama"

    def __init__(
        self,
        url: str = "http://127.0.0.1:11434",
        model: str = "llama3.2",
        timeout: float = 30.0,
    ):
        self.url = url.rstrip("/")
        self.model = model
        self.timeout = timeout

    @property
    def loaded(self) -> List[str]:
        return [f"ollama:{self.model}"]

    def predict(
        self,
        state: State,
        questions: Questions,
        model: Optional[str] = None,
        task: Optional[str] = None,
        lang: Optional[str] = None,
    ) -> Dict[str, Any]:
        active_model = model or self.model
        prompt = _build_llm_decision_prompt(state, questions)

        payload = {
            "model": active_model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.0},
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(f"{self.url}/api/generate", json=payload)
                resp.raise_for_status()
                raw_text = resp.json().get("response", "{}")
                parsed = _safe_extract_json(raw_text)
                return _normalize_llm_answers(parsed, questions, model_name=f"ollama:{active_model}")
        except Exception as exc:
            raise RuntimeError(f"Ollama decision evaluation failed: {exc}") from exc


class OpenAICompatibleBackend(Backend):
    """Bridge connecting local llama-server (GGUF), vLLM, or LM Studio to System 1."""

    name: str = "openai-compatible"
    device: str = "local-server"

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8080/v1",
        api_key: str = "not-needed",
        model: str = "default",
        timeout: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    @property
    def loaded(self) -> List[str]:
        return [f"openai:{self.base_url}:{self.model}"]

    def predict(
        self,
        state: State,
        questions: Questions,
        model: Optional[str] = None,
        task: Optional[str] = None,
        lang: Optional[str] = None,
    ) -> Dict[str, Any]:
        active_model = model or self.model
        prompt = _build_llm_decision_prompt(state, questions)

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload = {
            "model": active_model,
            "messages": [
                {"role": "system", "content": "You are a fast, calibrated System 1 decision engine. Respond strictly with JSON."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.0,
            "response_format": {"type": "json_object"},
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
                resp.raise_for_status()
                content = resp.json()["choices"][0]["message"]["content"]
                parsed = _safe_extract_json(content)
                return _normalize_llm_answers(parsed, questions, model_name=f"openai:{active_model}")
        except Exception as exc:
            raise RuntimeError(f"OpenAI-compatible decision evaluation failed: {exc}") from exc


# --- LLM decision formatting helpers ---

def _build_llm_decision_prompt(state: State, questions: Questions) -> str:
    state_str = json.dumps(state, indent=2) if isinstance(state, (dict, list)) else str(state)
    q_descriptions = []
    for qid, q in questions.items():
        qtype = q.get("type", "noul")
        ins = q.get("instructions", "")
        crit = q.get("criteria")
        if qtype == "choice":
            keys = list(crit.keys()) if isinstance(crit, dict) else list(crit or [])
            q_descriptions.append(f"- Question '{qid}' (choice): {ins}\n  Options: {keys}")
        elif qtype == "score":
            levels = [f"level {i}: {c}" for i, c in enumerate(crit)] if isinstance(crit, list) else []
            q_descriptions.append(f"- Question '{qid}' (score): {ins}\n  Levels: {levels}")
        else:
            q_descriptions.append(f"- Question '{qid}' (noul): {ins} (assess probability in [0.0, 1.0])")

    questions_text = "\n".join(q_descriptions)

    return f"""Evaluate the following STATE against the questions.

STATE:
```
{state_str}
```

QUESTIONS:
{questions_text}

Respond strictly with a JSON object in this format:
{{
  "answers": {{
    "<question_id>": {{
      "type": "choice | score | noul",
      "choice": "<selected_option>",       // required for choice
      "score": 0.0,                       // required for score (float index)
      "noul": 0.85,                       // required for noul (probability 0.0 to 1.0)
      "confidence": 0.9                   // estimated calibration confidence
    }}
  }}
}}
"""


def _safe_extract_json(text: str) -> Dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
    return {}


def _normalize_llm_answers(parsed: Dict[str, Any], questions: Questions, model_name: str) -> Dict[str, Any]:
    raw_answers = parsed.get("answers", parsed)
    answers: Dict[str, Any] = {}

    for qid, q in questions.items():
        qtype = q.get("type", "noul")
        raw = raw_answers.get(qid, {}) if isinstance(raw_answers, dict) else {}
        conf = float(raw.get("confidence", 0.8))

        if qtype == "choice":
            crit = q.get("criteria") or {}
            keys = list(crit.keys()) if isinstance(crit, dict) else list(crit or [])
            choice = str(raw.get("choice", keys[0] if keys else "unknown"))
            if choice not in keys and keys:
                choice = keys[0]
            probs = {k: (conf if k == choice else round((1.0 - conf) / max(1, len(keys) - 1), 4)) for k in keys}
            answers[qid] = {
                "type": "choice",
                "choice": choice,
                "probabilities": probs,
                "confidence": conf,
            }
        elif qtype == "score":
            crit = q.get("criteria") or []
            k = len(crit) if isinstance(crit, list) else 3
            score = float(raw.get("score", (k - 1) / 2.0))
            answers[qid] = {
                "type": "score",
                "score": round(score, 4),
                "legend": {str(i): str(c) for i, c in enumerate(crit)} if isinstance(crit, list) else {},
                "confidence": conf,
            }
        else:
            noul_val = float(raw.get("noul", 0.5))
            answers[qid] = {
                "type": "noul",
                "noul": round(max(0.0, min(1.0, noul_val)), 4),
                "confidence": conf,
            }

    return {
        "model": model_name,
        "answers": answers,
        "usage": {"input_tokens": 128, "output_tokens": 32},
        "routing": {"model": model_name, "backend": model_name},
    }
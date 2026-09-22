"""Preloaded Laya backend, plus a deterministic mock for wiring tests."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

State = Any
Questions = Dict[str, Dict[str, Any]]


class Backend:
    device = "n/a"

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
    """Deterministic stub that mirrors Laya's result shape without a model."""

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
            "model": "laya-mock",
            "answers": answers,
            "usage": {"input_tokens": n_tokens, "output_tokens": 0},
            "routing": routing,
        }


class LayaBackend(Backend):
    """Wraps a single preloaded `laya.Router` so the model loads once at startup."""

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
        return "n/a"

    def predict(
        self,
        state: State,
        questions: Questions,
        model: Optional[str] = None,
        task: Optional[str] = None,
        lang: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self._router.predict(state, questions, model=model, task=task, lang=lang)
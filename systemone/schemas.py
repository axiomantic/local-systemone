"""Request/response models and normalisation for the System One endpoint.

The canonical question schema is Laya's native one:

    choice: {"type": "choice", "instructions": "...", "criteria": {"optA": "desc", ...}}
    score:  {"type": "score",  "instructions": "...", "criteria": ["lvl0", "lvl1", ...]}
    noul:   {"type": "noul",   "instructions": "..."}

For convenience the endpoint also accepts Jev-style `options` (list) on a
choice question and `rubric`/`levels` (list) on a score question, which are
translated into Laya's `criteria` shape on the way in.
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict


class Question(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: Literal["choice", "score", "noul"]
    instructions: str
    criteria: Any = None
    options: Any = None
    rubric: Any = None
    levels: Any = None


class SystemOneRequest(BaseModel):
    state: Union[str, Dict[str, Any], List[Any]]
    questions: Dict[str, Question]
    model: Optional[str] = None
    task: Optional[str] = None
    lang: Optional[str] = None


class SystemOneResponse(BaseModel):
    model: str
    answers: Dict[str, Any]
    usage: Dict[str, int]
    routing: Optional[Dict[str, Any]] = None


class HealthResponse(BaseModel):
    status: str
    engine: str = "laya"
    mock: bool
    loaded_models: List[str]
    device: str


def to_laya_question(q: Question) -> Dict[str, Any]:
    """Translate a request question into Laya's native `{type, instructions, criteria}` dict."""
    t = q.type
    instructions = q.instructions

    if t == "choice":
        crit = q.criteria if q.criteria is not None else q.options
        if crit is None:
            raise ValueError("choice question requires 'criteria' (dict) or 'options' (list)")
        if isinstance(crit, list):
            crit = {str(c): None for c in crit}
        if not isinstance(crit, dict):
            raise ValueError("choice criteria must be a dict or list")
        return {"type": "choice", "instructions": instructions, "criteria": crit}

    if t == "score":
        crit = q.criteria
        if crit is None:
            crit = q.rubric if q.rubric is not None else q.levels
        if isinstance(crit, dict):
            crit = [str(v) for v in crit.values()]
        if crit is None:
            crit = []
        if not isinstance(crit, list):
            raise ValueError("score criteria must be a list of levels")
        return {"type": "score", "instructions": instructions, "criteria": [str(c) for c in crit]}

    body: Dict[str, Any] = {"type": "noul", "instructions": instructions}
    if q.criteria:
        body["criteria"] = q.criteria
    return body


def normalize_questions(questions: Dict[str, Question]) -> Dict[str, Dict[str, Any]]:
    return {qid: to_laya_question(q) for qid, q in questions.items()}
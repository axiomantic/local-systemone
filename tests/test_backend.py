from __future__ import annotations

import json
from systemone.backend import (
    MockBackend,
    OllamaBackend,
    OpenAICompatibleBackend,
    ProxyBackend,
    _build_llm_decision_prompt,
    _normalize_llm_answers,
    _safe_extract_json,
)
from systemone.server import build_backend


def test_build_backend_engines():
    assert isinstance(build_backend("mock"), MockBackend)
    assert isinstance(build_backend("stub"), MockBackend)

    ollama = build_backend("ollama")
    assert isinstance(ollama, OllamaBackend)
    assert ollama.name == "ollama"

    openai = build_backend("openai")
    assert isinstance(openai, OpenAICompatibleBackend)
    assert openai.name == "openai-compatible"

    proxy = build_backend("proxy")
    assert isinstance(proxy, ProxyBackend)
    assert proxy.name == "proxy"


def test_llm_prompt_building():
    state = "Error: Database connection timeout on migration"
    questions = {
        "domain": {
            "type": "choice",
            "instructions": "Which domain?",
            "criteria": {"database": "DB stuff", "frontend": "UI stuff"},
        },
        "urgency": {
            "type": "score",
            "instructions": "Urgency?",
            "criteria": ["low", "high"],
        },
        "needs_fix": {
            "type": "noul",
            "instructions": "Needs immediate fix?",
        },
    }

    prompt = _build_llm_decision_prompt(state, questions)
    assert "Database connection timeout" in prompt
    assert "Question 'domain' (choice)" in prompt
    assert "Question 'urgency' (score)" in prompt
    assert "Question 'needs_fix' (noul)" in prompt


def test_normalize_llm_answers():
    questions = {
        "domain": {
            "type": "choice",
            "instructions": "Which domain?",
            "criteria": {"database": "DB stuff", "frontend": "UI stuff"},
        },
        "urgency": {
            "type": "score",
            "instructions": "Urgency?",
            "criteria": ["low", "high"],
        },
        "needs_fix": {
            "type": "noul",
            "instructions": "Needs immediate fix?",
        },
    }

    raw_json = {
        "answers": {
            "domain": {"choice": "database", "confidence": 0.95},
            "urgency": {"score": 1.0, "confidence": 0.9},
            "needs_fix": {"noul": 0.85, "confidence": 0.85},
        }
    }

    result = _normalize_llm_answers(raw_json, questions, "test-model")
    assert result["model"] == "test-model"
    assert result["answers"]["domain"]["choice"] == "database"
    assert result["answers"]["domain"]["confidence"] == 0.95
    assert result["answers"]["domain"]["probabilities"]["database"] == 0.95
    assert result["answers"]["urgency"]["score"] == 1.0
    assert result["answers"]["needs_fix"]["noul"] == 0.85

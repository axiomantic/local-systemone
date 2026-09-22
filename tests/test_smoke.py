from fastapi.testclient import TestClient

from laya_service.backend import MockBackend
from laya_service.server import create_app


def _client():
    app = create_app(backend=MockBackend())
    return TestClient(app)


def test_healthz_reports_mock():
    c = _client()
    r = c.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["mock"] is True
    assert body["loaded_models"] == ["mock"]


def test_choice_with_options_list():
    c = _client()
    r = c.post(
        "/v1/systemone",
        json={
            "state": "Pick a team",
            "questions": {"handler": {"type": "choice", "instructions": "Who owns this?", "options": ["ops", "support"]}},
        },
    )
    assert r.status_code == 200, r.text
    ans = r.json()["answers"]["handler"]
    assert ans["type"] == "choice"
    assert ans["choice"] in {"ops", "support"}
    assert set(ans["probabilities"]) == {"ops", "support"}


def test_score_with_rubric():
    c = _client()
    r = c.post(
        "/v1/systemone",
        json={
            "state": "urgent",
            "questions": {"sev": {"type": "score", "instructions": "How urgent?", "rubric": ["low", "mid", "high"]}},
        },
    )
    assert r.status_code == 200, r.text
    ans = r.json()["answers"]["sev"]
    assert ans["type"] == "score"
    assert ans["score"] == 1.0
    assert set(ans["legend"].values()) == {"low", "mid", "high"}


def test_noul():
    c = _client()
    r = c.post(
        "/v1/systemone",
        json={"state": "x", "questions": {"ok": {"type": "noul", "instructions": "fine?"}}},
    )
    assert r.status_code == 200, r.text
    ans = r.json()["answers"]["ok"]
    assert ans["type"] == "noul"
    assert 0.0 <= ans["noul"] <= 1.0


def test_missing_choice_criteria_is_400():
    c = _client()
    r = c.post(
        "/v1/systemone",
        json={"state": "x", "questions": {"bad": {"type": "choice", "instructions": "?"}}},
    )
    assert r.status_code == 400
"""Laya System One service: a self-hosted, Jev-compatible decision backend."""

from .backend import Backend, LayaBackend, MockBackend
from .schemas import (
    HealthResponse,
    Question,
    SystemOneRequest,
    SystemOneResponse,
    normalize_questions,
    to_laya_question,
)

__version__ = "0.1.0"

__all__ = [
    "Backend",
    "LayaBackend",
    "MockBackend",
    "Question",
    "SystemOneRequest",
    "SystemOneResponse",
    "HealthResponse",
    "normalize_questions",
    "to_laya_question",
    "__version__",
]
"""FastAPI service exposing a Jev-compatible System One endpoint.

Backed by pluggable decision engines:
- Laya (ModernBERT-large 421M / mmBERT-base 322M)
- Ollama (local LLM via http://127.0.0.1:11434)
- OpenAI-compatible (local llama-server GGUF / vLLM / LM Studio)
- Proxy (upstream TypeSafe Jev API or remote System 1 instance)
- Mock (deterministic stub for testing and CI)
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from .backend import (
    Backend,
    LayaBackend,
    MockBackend,
    OllamaBackend,
    OpenAICompatibleBackend,
    ProxyBackend,
)
from .schemas import HealthResponse, SystemOneRequest, SystemOneResponse, normalize_questions

__all__ = ["app", "main", "build_backend", "create_app"]


def build_backend(engine: Optional[str] = None) -> Backend:
    engine = engine or os.environ.get("SYSTEMONE_ENGINE") or os.environ.get("LAYA_ENGINE") or "auto"
    engine = engine.strip().lower()

    if os.environ.get("LAYA_MOCK", "").strip().lower() in ("1", "true", "yes") or engine in ("mock", "stub"):
        return MockBackend()

    if engine == "ollama":
        return OllamaBackend(
            url=os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434"),
            model=os.environ.get("OLLAMA_MODEL", "llama3.2"),
        )

    if engine in ("openai", "openai-compatible", "llamacpp", "vllm", "lmstudio"):
        return OpenAICompatibleBackend(
            base_url=os.environ.get("OPENAI_BASE_URL", "http://127.0.0.1:8080/v1"),
            api_key=os.environ.get("OPENAI_API_KEY", "not-needed"),
            model=os.environ.get("OPENAI_MODEL", "default"),
        )

    if engine in ("proxy", "jev"):
        return ProxyBackend(
            url=os.environ.get("UPSTREAM_URL", "https://api.typesafe.ai"),
            api_key=os.environ.get("UPSTREAM_API_KEY") or os.environ.get("JEV_API_KEY") or "",
            model=os.environ.get("UPSTREAM_MODEL", "jev-1"),
        )

    if engine in ("laya", "auto"):
        try:
            device = os.environ.get("LAYA_DEVICE") or None
            preload = os.environ.get("SYSTEMONE_PRELOAD", os.environ.get("LAYA_PRELOAD", "1")).strip().lower() not in ("0", "false", "no")
            auto_task_detection = os.environ.get("LAYA_AUTO_TASK_DETECTION", "").strip().lower() in ("1", "true", "yes")
            raw_models = os.environ.get("LAYA_PRELOAD_MODELS", "english")
            preload_models = [m for m in raw_models.split(",") if m.strip()] or ["english"]
            return LayaBackend(
                device=device,
                preload=preload,
                preload_models=preload_models,
                auto_task_detection=auto_task_detection,
            )
        except (ImportError, Exception) as exc:
            if engine == "auto":
                return MockBackend()
            raise RuntimeError(f"Failed to initialize Laya backend: {exc}") from exc

    raise ValueError(f"Unknown engine: '{engine}'. Supported: laya, ollama, openai, proxy, mock")


def create_app(backend: Optional[Backend] = None, engine: Optional[str] = None) -> FastAPI:
    if backend is not None:
        app = FastAPI(title="Local System One", version="0.2.1")
        app.state.backend = backend
    else:
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            app.state.backend = build_backend(engine=engine)
            yield

        app = FastAPI(title="Local System One", version="0.2.1", lifespan=lifespan)

    def _backend(request: Request) -> Backend:
        return request.app.state.backend

    @app.get("/healthz", response_model=HealthResponse)
    def healthz(request: Request) -> HealthResponse:
        b = _backend(request)
        warming = not isinstance(b, MockBackend) and not b.loaded
        return HealthResponse(
            status="warming-up" if warming else "ok",
            engine=getattr(b, "name", "unknown"),
            mock=isinstance(b, MockBackend),
            loaded_models=b.loaded,
            device=b.device,
        )

    @app.post("/v1/systemone", response_model=SystemOneResponse)
    def system_one(req: SystemOneRequest, request: Request) -> Dict[str, Any]:
        try:
            questions = normalize_questions(req.questions)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        try:
            return _backend(request).predict(
                req.state, questions, model=req.model, task=req.task, lang=req.lang
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @app.post("/v1/predict", response_model=SystemOneResponse)
    def predict(req: SystemOneRequest, request: Request) -> Dict[str, Any]:
        return system_one(req, request)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    return app


app = create_app()


def main() -> None:
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(
        prog="local-systemone",
        description="Run the Local System One decision service (foreground) or manage its background daemon.",
    )
    parser.add_argument("--host", default=os.environ.get("SYSTEMONE_HOST", os.environ.get("LAYA_HOST", "127.0.0.1")))
    parser.add_argument("--port", type=int, default=int(os.environ.get("SYSTEMONE_PORT", os.environ.get("LAYA_PORT", "8100"))))
    parser.add_argument("--engine", choices=["laya", "ollama", "openai", "proxy", "mock", "auto"],
                        default=os.environ.get("SYSTEMONE_ENGINE", "auto"),
                        help="decision engine backend (laya, ollama, openai, proxy, mock)")
    parser.add_argument("--install-daemon", action="store_true",
                        help="install a background daemon (launchd on macOS, systemd on Linux)")
    parser.add_argument("--uninstall-daemon", action="store_true",
                        help="unload and remove the background daemon")
    parser.add_argument("--status-daemon", action="store_true",
                        help="check if the background daemon is running")
    args = parser.parse_args()

    if args.install_daemon:
        from .daemon import install_daemon
        install_daemon(host=args.host, port=args.port, engine=args.engine if args.engine != "auto" else None)
        return
    if args.uninstall_daemon:
        from .daemon import uninstall_daemon
        uninstall_daemon()
        return
    if args.status_daemon:
        from .daemon import status_daemon
        status_daemon()
        return

    custom_app = create_app(engine=args.engine)
    uvicorn.run(custom_app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
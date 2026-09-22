"""FastAPI service exposing a Jev-compatible System One endpoint backed by Laya.

Run with `laya-service` (or `uvicorn laya_service.server:app`). The Laya model
is loaded once at startup (see `laya_service.backend.LayaBackend`), so every
request after warm-up is answered from a resident checkpoint.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request

from .backend import Backend, LayaBackend, MockBackend
from .schemas import HealthResponse, SystemOneRequest, SystemOneResponse, normalize_questions

__all__ = ["app", "main", "build_backend", "create_app"]


def build_backend() -> Backend:
    if os.environ.get("LAYA_MOCK", "").strip().lower() in ("1", "true", "yes"):
        return MockBackend()
    device = os.environ.get("LAYA_DEVICE") or None
    preload = os.environ.get("LAYA_PRELOAD", "1").strip().lower() not in ("0", "false", "no")
    auto_task_detection = os.environ.get("LAYA_AUTO_TASK_DETECTION", "").strip().lower() in ("1", "true", "yes")
    raw_models = os.environ.get("LAYA_PRELOAD_MODELS", "")
    preload_models = [m for m in raw_models.split(",") if m.strip()] or None
    return LayaBackend(
        device=device,
        preload=preload,
        preload_models=preload_models,
        auto_task_detection=auto_task_detection,
    )


def create_app(backend: Optional[Backend] = None) -> FastAPI:
    if backend is not None:
        app = FastAPI(title="Laya System One", version="0.1.0")
        app.state.backend = backend
    else:
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            app.state.backend = build_backend()
            yield

        app = FastAPI(title="Laya System One", version="0.1.0", lifespan=lifespan)

    def _backend(request: Request) -> Backend:
        return request.app.state.backend

    @app.get("/healthz", response_model=HealthResponse)
    def healthz(request: Request) -> HealthResponse:
        b = _backend(request)
        warming = not isinstance(b, MockBackend) and not b.loaded
        return HealthResponse(
            status="warming-up" if warming else "ok",
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

    @app.post("/v1/predict", response_model=SystemOneResponse)
    def predict(req: SystemOneRequest, request: Request) -> Dict[str, Any]:
        return system_one(req, request)

    from fastapi.middleware.cors import CORSMiddleware

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
        prog="laya-service",
        description="Run the Laya decision service (foreground) or manage its launchd agent.",
    )
    parser.add_argument("--host", default=os.environ.get("LAYA_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("LAYA_PORT", "8000")))
    parser.add_argument("--install-daemon", action="store_true",
                        help="install a launchd LaunchAgent that keeps the service running")
    parser.add_argument("--uninstall-daemon", action="store_true",
                        help="unload and remove the launchd LaunchAgent")
    args = parser.parse_args()

    if args.install_daemon:
        from .daemon import install_daemon
        install_daemon(host=args.host, port=args.port)
        return
    if args.uninstall_daemon:
        from .daemon import uninstall_daemon
        uninstall_daemon()
        return

    uvicorn.run("laya_service.server:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
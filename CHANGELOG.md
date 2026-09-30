# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.1] - 2026-09-30

### Fixed
- **Laya 0.3.7+ Compatibility**:
  - Relaxed `usage` schema dictionary typing in `SystemOneResponse` from `Dict[str, int]` to `Dict[str, Any]`. In Laya 0.3.7+ (`0.3.22`), `predict()` includes list/boolean fields (e.g. `truncated_questions: []`, `truncated: False`) which previously triggered FastAPI `ResponseValidationError` returning HTTP 500.
  - Pinned `laya==0.3.22` in `pyproject.toml` optional dependencies for reproducible installs across platforms.

## [0.2.0] - 2026-09-30

### Added
- **Multi-Engine Pluggable Architecture**:
  - Implemented unified backend interface supporting `laya` (ModernBERT/mmBERT), `ollama`, `openai` (local GGUF llama-server), `proxy` (TypeSafe Jev API), and `mock`.
  - Added CLI flag `--engine <type>` with automatic engine detection based on local environment and model availability.
- **Cross-Platform Background Daemon Manager**:
  - **macOS**: Automatic `launchd` LaunchAgent generation and registration (`com.axiomantic.local-systemone` in `~/Library/LaunchAgents/`).
  - **Linux**: Automatic `systemd` user service unit generation and registration (`local-systemone.service` in `~/.config/systemd/user/`) with `loginctl enable-linger` support.
  - Added CLI management flags: `--install-daemon`, `--uninstall-daemon`, and `--status`.
- **Stand-Alone Service Templates**:
  - Added declarative service configurations in `daemons/launchd/com.axiomantic.local-systemone.plist`, `daemons/systemd/local-systemone.service`, and `daemons/systemd/local-systemone-user.service`.
- **Fast Startup & Model Preload Optimization**:
  - Optimized model preloading (`LAYA_PRELOAD_MODELS="english"` by default) to eliminate 40-second multi-checkpoint initialization pauses, reducing cold startup time to ~2 seconds.
- **Complete Test Suite**:
  - Added unit, daemon, and smoke tests verifying schema compliance (`choice`, `score`, `noul`), health checks, and daemon configuration rendering.

### Changed
- **Dedicated Port Default**:
  - Changed default service port from `8000` to `8100` across server, daemon templates, and tests to prevent collisions with web development servers.
- **Project Rebranding & Package Generalization**:
  - Renamed package to `local-systemone` with dual entrypoint scripts (`local-systemone`, `systemone`).
  - Maintained complete backward compatibility with `laya-service` CLI commands and Python module imports (`laya_service`).

## [0.1.0] - 2026-09-22

### Added
- Initial release of Laya ModernBERT local decision service.
- HTTP server with `/v1/systemone` and `/healthz` endpoints.
- Integration with `convaiinnovations/laya`.

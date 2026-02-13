# Repository Guidelines

## Project Structure & Module Organization
Core entry points are `cli.py`, `startup.py`, and `pentest.py`. Main runtime modules:
- `actions/`: planning, execution, shell/tool actions.
- `roles/`: Collector/Scanner/Exploiter role logic.
- `server/`: FastAPI backend (`server/api`, `server/chat`).
- `web/`: Streamlit UI.
- `rag/`: embedding, retriever, KB services/parsers.
- `db/`: SQLAlchemy models and repositories.
- `config/`: YAML-backed settings loaders.
- `prompts/`, `experiment/`, `utils/`, `images/`: prompts, experiments, shared utilities, assets.

Runtime/config files at repo root: `basic_config.yaml`, `db_config.yaml`, `kb_config.yaml`, `model_config.yaml`.

## Build, Test, and Development Commands
- Use `uv` as the default package and environment manager for all local development.
- `uv sync`: create/update the virtual environment from `pyproject.toml` and `uv.lock`.
- `uv run python cli.py init`: initialize directories, create DB tables, generate config templates.
- `uv run python cli.py start --api`: start FastAPI service (default `:7861`).
- `uv run python cli.py start -w`: start Streamlit WebUI (default `:8501`).
- `uv run python cli.py vulnbot -m 5`: run VulnBot workflow with max interactions.

## Coding Style & Naming Conventions
- Language: Python 3.11, 4-space indentation, UTF-8 source.
- Follow PEP 8 naming: `snake_case` for functions/files, `PascalCase` for classes, `UPPER_CASE` for constants.
- Keep modules focused by domain (new DB code in `db/`, API routes in `server/api/`, role logic in `roles/`).
- Prefer explicit typing and concise docstrings for non-obvious behavior.

## Testing Guidelines
No dedicated `tests/` suite is currently included. Use smoke/integration checks:
- `python cli.py init` must succeed.
- API/WebUI must boot without tracebacks.
- Optional DB check: confirm tables (`sessions`, `plans`, `tasks`, etc.) exist.

If adding tests, use `pytest` with files named `test_*.py` under a new `tests/` directory.

## Commit & Pull Request Guidelines
Recent history favors short, imperative commits (e.g., `Fix bug in WritePlan`, `Add pyproject and uv lock`).
- Commit format: `<Verb> <scope/what changed>` (example: `Fix planner None response handling`).
- Keep commits focused and atomic; avoid mixing refactor + behavior change.
- PRs should include: purpose, key changes, config impacts, run steps, and logs/screenshots for API/UI changes.

## Security & Configuration Tips
- Never commit real credentials in `*_config.yaml`.
- Verify MySQL/LLM/Kali settings before running `vulnbot`.
- Keep `enable_rag` off unless Milvus and KB settings are fully configured.

# Repository Guidelines

## Project Structure & Module Organization

- `personalCab/frontend/`: cabinet UI (`index.html`, `app.js`, `styles.css`), landing page, `front_assets/`, and Python HTTP server.
- `personalCab/prom/prom_lab/ai_agents_lab/`: dialogue workflow. Keep orchestration in `agents/`, application services in `services/`, persistence in `repositories/`, typed models in `schemas/`, and tools in `agent_tools/`.
- Tests live in `personalCab/frontend/tests/` and the workflow package’s `tests/`.
- `DataAndArcBuild/architecture/`, `ABOUT.md`, and `REQUIREMENTS.md` describe the intended system. Modules 2–5 are currently unconfigured.
- Root `src/` and `assets/` contain local reference material and are Git-ignored; do not place new tracked application code there.

## Build, Test, and Development Commands

Run from the repository root. Existing setup uses this shared Python environment:

```sh
PY=/Users/retro0/projects/PyVenv/venv_core/bin/python
$PY -m pip install -r personalCab/prom/prom_lab/ai_agents_lab/requirements.txt
$PY -m personalCab.frontend.server
$PY -m pytest personalCab/frontend/tests personalCab/prom/prom_lab/ai_agents_lab/tests -q
```

These install pinned dependencies, serve the cabinet at `http://127.0.0.1:5173/`, and run both test suites. Start Ollama with `gpt-oss:20b` available for live chat. The frontend uses plain HTML/CSS/JavaScript without a build step; chat requires the Python server.

## Coding Style & Naming Conventions

Use four-space Python indentation, `snake_case` functions/modules, `PascalCase` classes, and uppercase constants. Preserve type annotations and Pydantic models at boundaries. Follow nearby JavaScript formatting and existing CSS naming. No formatter or linter configuration is currently checked in; avoid unrelated reformatting.

## Testing Guidelines

Use pytest with `test_*.py` files and `test_*` functions. Use temporary SQLite databases and deterministic extractor fixtures; automated tests should not require Ollama. HTTP tests need local port access. Cover persistence, revisions, idempotency, profile isolation, and failure paths when changing those behaviors. No numeric coverage threshold is configured. Verify UI changes in the browser and include a live-model check when changing extraction.

## Commit & Pull Request Guidelines

History contains short, informal subjects such as `first commit`; no formal convention is established. Write concise, action-oriented subjects. PRs should explain behavior changes, include validation commands/results, link relevant issues or specifications, and attach screenshots for UI changes.

## Configuration & Data Boundaries

Use `OLLAMA_BASE_URL` to override the local model endpoint and `--database` for an alternate SQLite path. Keep databases and secrets untracked. Preserve server-controlled identities and consent checks, and keep unknown client facts explicit. The local DEMO does not issue real credit decisions.

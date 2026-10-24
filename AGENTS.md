# Repository Guidelines

## Project Structure & Current Scope

- `personalCab/frontend/`: plain HTML/CSS/JavaScript cabinet, landing page, `front_assets/`, and same-origin Python HTTP server. No JS build step.
- `knowledge/`: structured requirement reference; `personalCab/prom/rag/`: offline FAISS lexical retrieval and LangGraph subgraph. Keep citations/source hashes and read-only reference routing; source text must never grant consent or mutate applicant facts. Contract term requirements use `credit_applications.requested_term_months`.
- `personalCab/prom/prom_lab/ai_agents_lab/`: M1 orchestration in `agents/`, M2–M5 services in `services/`, persistence in `repositories/`, typed boundaries in `schemas/`, tools in `agent_tools/`.
- `DataAndArcBuild/architecture/`: module specifications. `DataAndArcBuild/AURELIUS_CREDIT_PROCESS_SUMMARY.md` is the decision/status journal. `docs/POSTGRES_INTEGRATION.md` records the integration contract and unresolved mappings.
- M1–M5 are connected in local DEMO. M4 loads real registered synthetic CatBoost on explicit operator-reviewed inputs. M5 persists manual review, offers and acknowledged simulation only. A snapshot is not a ready feature vector or credit decision. See `docs/DEMO_MODULES_1_5.md`.
- `scoring/bd/schema.sql`, `business_scoring.backup`, `seeds/`: business schema and synthetic examples. `scoring/bd/migrations/`: additive application migrations. `scoring/models/`: offline synthetic ML experiments, not a production scoring service.
- Root `src/` and `assets/` are ignored reference material; do not put tracked application code there.

## Build, Test, and Development Commands

Run from the repository root. Docker deployment:

```sh
docker compose up --build -d
```

A fresh PostgreSQL volume restores the checked-in backup once (30 synthetic companies, R01–R03, 99 field requirements). The init service applies workflow/checkpoint migrations before the app starts at `http://127.0.0.1:5173/`. Existing volumes are preserved; do not delete volumes to apply migrations. PostgreSQL is published on loopback port 5433. Docker demo defaults are documented in `.env.example`; replace its public demo password for deployment. Start Ollama separately with `gpt-oss:20b`.

For host-side Python, use the shared environment:

```sh
PY=/Users/retro0/projects/PyVenv/venv_core/bin/python
$PY -m pip install -r personalCab/prom/prom_lab/ai_agents_lab/requirements.txt
$PY -m personalCab.prom.prom_lab.ai_agents_lab.database --init-workflow
$PY -m personalCab.frontend.server --company-id 40
$PY -m pytest personalCab/frontend/tests personalCab/prom/prom_lab/ai_agents_lab/tests -q
```

Configure PostgreSQL through `PG_HOST`, `PG_PORT`, `PG_DATABASE`, `PG_USER`, `PG_PASSWORD`, libpq equivalents/pgpass, or `AURELIUS_DATABASE_URL`. Host Python does not automatically load `.env`; Compose does. `OLLAMA_BASE_URL` overrides Ollama. Explicit `--database PATH` selects legacy SQLite for compatibility/tests only; the default runtime is PostgreSQL with no silent fallback.

## Coding Style & Naming

Use four-space Python indentation, `snake_case` functions/modules, `PascalCase` classes, uppercase constants, type annotations and Pydantic boundary validation. Follow nearby JS/CSS formatting. Avoid unrelated reformatting; no checked-in formatter/linter configuration exists.

## Testing

Tests live in frontend `tests/` and workflow `tests/`, use pytest `test_*.py`. Legacy tests use temporary SQLite and deterministic extraction; no Ollama dependency. PostgreSQL tests run only when `AURELIUS_TEST_DATABASE_URL` explicitly points to a dedicated seeded test DB. They add test records; never point them at production. HTTP/PG tests require local network access. Cover revisions, receipt idempotency, immutable snapshots, consent, cross-company isolation, locks and failure recovery. Verify UI changes in browser; a live-model check is needed when extraction changes.

## Data and Architecture Boundaries

- PostgreSQL is authoritative for cases, web sessions, receipts, audit, LangGraph checkpoints and business records. `aurelius_workflow` separates app state from `public`. SQLite import is explicit, transactional and non-destructive; old graph checkpoints are not imported.
- Keep all 16 catalog directions. Only `term→R01`, `rcl→R02`, `overdraft→R03` support business DB snapshots. Others must expose `database_supported=false`; never silently reroute them into R01.
- Server/CLI assigns actor, borrower and `company_id`; chat/LLM cannot bind identities or grant consent. `AURELIUS_DEMO_EVIDENCE_CONSENT=true` is an explicit trusted startup grant for synthetic DEMO data; false by default. Consent UI persists grants/revocations; selectable companies come only from an operator allowlist. Real production authentication remains future work.
- M3 records source rows, cutoff, provenance, missing fields and snapshot IDs. Time-unavailable evidence stays unknown. Do not derive unapproved ratios, industry encodings, legal form from company name, interest-rate units or month/day conversion.
- Actual CatBoost interfaces have 16 baseline/23 dynamic inputs. The documented 53 + 12×8 target is future work. Missing mappings block readiness. No probability or lending decision may be invented from seeded scores. Actual M4 inference requires reviewed feature_inputs tied to case/revision/evidence/product; preserve baseline/dynamic semantics. Manual reviewer commands live only in operator.py; borrower APIs never approve their own inputs or cases.
- Validate extracted fields independently through Pydantic and verbatim current-message evidence; preserve valid siblings through one repair. Persist unresolved clarifications and expose DataResolutionPlan. Do not replace a known value with an invalid attempted update.
- `lookup_business_profile` is a minimal, consent-guarded read before full request completion: only verified legal_form with company/borrower/cutoff provenance. No historical loan amount/term prefill. Missing/unavailable/conflicting profile data leads to a customer question; configuration/ML formula gaps go to ENGINEERING.
- Product terms without approval/version validity remain UNKNOWN. Keep contract term, tranche term and drawdown window separate. `LEGAL_ENTITY` does not imply OOO; a published minimum rate is not the contractual `annual_rate`.
- Preserve user-edited architecture. Surface material conflicts and ask which source wins before implementing disputed financial logic.
- Keep credentials and runtime DBs untracked. Treat repo backup/seeds as synthetic reference data; never restore over an existing database automatically.

## Commits & Pull Requests

Use concise action-oriented subjects; no formal historical convention exists. Explain behavior changes, validation/results, relevant specifications and UI screenshots when applicable. The local DEMO does not issue real credit decisions.

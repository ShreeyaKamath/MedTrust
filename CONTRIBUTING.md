# Contributing to MedTrust

Phase 1 covers repository foundation and research design only. Implement later-phase functionality only when that phase is explicitly authorized.

## Workflow

Use feature branches and reviewed pull requests. Do not push directly to `main` during normal development. Example branch names:

- `feat/backend-foundation`
- `feat/clinical-data-model`
- `feat/rag-pipeline`
- `feat/openclaw-agents`
- `feat/provenance-memory`
- `feat/trust-engine`
- `feat/uncertainty-engine`
- `feat/mcp-security`
- `feat/frontend`

Use commit prefixes `feat:`, `fix:`, `test:`, `docs:`, `refactor:`, `perf:`, `chore:`, and `research:`. Describe the concrete change and why it is needed.

## Research and safety rules

- No real patient data, secrets, credentials, or API keys in Git, issues, logs, or shared outputs.
- Use synthetic, permitted public de-identified, or properly de-identified data only; verify licensing and redistribution permission.
- Do not make autonomous medical claims, claim clinical efficacy, or suggest regulatory approval.
- Recommendations require clinician review and never authorize actions.
- Never expose or store private chain-of-thought; use structured findings and evidence references.
- Functional changes should include meaningful tests; research-design changes should include documentation.
- Preserve existing functionality and document compatibility impacts.
- Generated results must not be fabricated. Distinguish proposed experiments from completed runs; preserve reproducible configurations and report failures.

## Development checks

Python 3.12 is the target. Optional tooling is declared in the `dev` dependency group; installing the future application stack is outside Phase 1. For later Python changes, use `ruff check .` and `pytest` when meaningful tests exist. There are no application tests in Phase 1; an empty pytest suite is not a passing application test result.

For documentation/configuration changes, validate TOML and available YAML tooling, local links, Git ignore behavior, and the absence of secrets and generated artifacts. Record exact commands, results, changed files, and unresolved limitations in the review. `.gitignore` is a convenience, not a security boundary; inspect content before staging.

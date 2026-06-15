# Implementation Plan: DevContainer CI Validation

## Summary of the change
Add a GitHub Actions workflow that validates `.devcontainer/devcontainer.json`, asserts VS Code telemetry remains disabled by default, and builds `.devcontainer/Dockerfile` whenever DevContainer inputs change.

## Files to modify
- `.github/workflows/devcontainer-validation.yml` — new workflow.
- `IDEAS.json`, `TASKS.md`, `PLAN.md`, `TEST_REPORT.json`, `CLOSE_SUMMARY.md` — cycle artifacts.

## Step-by-step implementation instructions
1. Create a feature branch from `main`.
2. Add a path-scoped GitHub Actions workflow for `.devcontainer/**` changes.
3. Use pinned `actions/checkout` to match repository supply-chain policy.
4. Validate `devcontainer.json` with `python -m json.tool`.
5. Add a Python guard that fails if `customizations.vscode.settings.telemetry.telemetryLevel` is not `off`.
6. Build the DevContainer Dockerfile with `docker build -f .devcontainer/Dockerfile .devcontainer`.
7. Run local validation commands and open a PR.

## Test cases to verify
- `python -m json.tool .devcontainer/devcontainer.json` exits 0.
- The telemetry guard reads the config and verifies `telemetry.telemetryLevel == "off"`.
- Workflow YAML parses successfully as YAML.
- If Docker is available locally, `.devcontainer/Dockerfile` builds successfully.

## Rollback procedure
Delete `.github/workflows/devcontainer-validation.yml` and revert the cycle artifact updates.

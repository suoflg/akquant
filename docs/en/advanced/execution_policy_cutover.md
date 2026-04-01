# Execution Policy Cutover Checklist

This checklist is for the final cutover from legacy `execution_mode` / `timer_execution_policy` to `fill_policy`.

## Scope

- Keep API name unchanged (`run_backtest` / `run_warm_start`)
- Keep `symbols` as the only symbol argument
- Move execution semantics to `fill_policy` as primary path
- Use `legacy_execution_policy_compat` as staged gate

## Phase A: Warning Cleanup

- Run all tests and ensure no regression:

```bash
uv run ruff check .
uv run mypy .
uv run pytest -q
```

- Search codebase for legacy invocation patterns:

```bash
rg 'execution_mode='
rg 'timer_execution_policy='
```

- Update internal callsites to `fill_policy` everywhere
- Remove remaining `execution_mode` / `timer_execution_policy` callsites

## Phase B: Staging/Canary Validation

- Verify runbook scenarios:
  - backtest with `fill_policy` works
  - warm start with `fill_policy` works
  - legacy calls fail with explicit migration error
- Generate and review golden baseline report:

```bash
uv run python scripts/golden_baseline_report.py
```

## Phase C: Production Legacy Retirement

- Monitor logs for:
  - migration errors from remaining legacy callers
  - sudden strategy behavior drift
- Keep rollback path ready:
  - fast rollback: set env back to `true`
  - release rollback: revert deployment version

## Rollback Points

- **R1: Runtime rollback**
  - Change only env value:
  - `AKQ_LEGACY_EXECUTION_POLICY_COMPAT=true`
- **R2: Release rollback**
  - Roll back to previous release artifact
- **R3: Callsite rollback**
  - Temporarily pass `legacy_execution_policy_compat=True` at specific problematic callsites

## Exit Criteria

- No production callers rely on legacy execution semantics
- No warnings/errors related to legacy execution policy for one full observation window
- Golden baseline report accepted by strategy owners

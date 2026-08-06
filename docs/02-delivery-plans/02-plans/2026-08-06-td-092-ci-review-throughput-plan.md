# TD-092 CI 反馈周期与复审收敛治理 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将高风险 PR 的中间反馈从每次 full Backend 改为 Draft risk-targeted，且把最终 Ready HEAD、main 和 nightly 的完整回归门禁保留下来，同时冻结可并行、按根因返修的复审流程。

**Architecture:** 继续使用现有 `detect-change-scopes` 和 `select_backend_tests.py`，增加 PR Draft 状态与“可迭代高风险”分类。Draft 高风险使用固定 Agent/migration risk suite，Ready 高风险回到 full；始终 full 的路径继续 fail closed。复审规则写入现有治理事实源和 PR review packet，不引入业务代码依赖。

**Tech Stack:** GitHub Actions, Bash, Python stdlib, pytest, Markdown engineering gates.

---

### Task 1: Register TD-092 and freeze the contract

**Files:**
- Modify: `docs/03-engineering-governance/technical-debt.md`
- Modify: `docs/03-engineering-governance/current-work.md`
- Create: `docs/02-delivery-plans/01-specs/2026-08-06-td-092-ci-review-throughput.md`
- Create: `docs/02-delivery-plans/02-plans/2026-08-06-td-092-ci-review-throughput-plan.md`

- [ ] Add TD-092 to the technical-debt index and detail section with the PR #530 timing evidence, completion criteria, and no-business-logic boundary.
- [ ] Move TD-092 into `current-work.md` as the sole active task and record branch, CI/review scope, and the fact that R1-S4-C is paused.
- [ ] Run `scripts/check-engineering-docs` and `git diff --check` before implementation.
- [ ] Commit the task registration and contract as `docs(governance): register TD-092 CI review throughput`.

### Task 2: Add failing selector tests for Draft risk-targeted behavior

**Files:**
- Modify: `scripts/ci/select_backend_tests.py`
- Modify: `tests/engineering/test_backend_test_selection.py`

- [ ] Add tests asserting a Draft migration change returns `risk-targeted` and includes migration/Agent risk tests.
- [ ] Add tests asserting the same migration change with `draft=False` returns `full`.
- [ ] Add tests asserting Draft `app/composition` and Agent context changes return `risk-targeted`, while Ready returns `full`.
- [ ] Add tests asserting CI/selector/shared/identity/unknown changes remain `full` even in Draft.
- [ ] Add tests asserting direct Agent test changes remain targeted and do not silently become full.
- [ ] Run `cd packages/server-python && uv run pytest ../../tests/engineering/test_backend_test_selection.py -q`; the new tests must fail before the implementation changes.

### Task 3: Implement the risk-tiered selector

**Files:**
- Modify: `scripts/ci/select_backend_tests.py`
- Modify: `tests/engineering/test_backend_test_selection.py`

- [ ] Add an explicit `draft` input and a `risk-targeted` selection mode.
- [ ] Keep all existing always-full paths fail-closed.
- [ ] Define a stable Agent core risk suite and append transport, erasure, or migration/schema/roundtrip tests by changed path; always include health/database smoke tests and directly changed test files.
- [ ] Ensure the selector evaluates all changed paths before deciding; one always-full path must dominate any targeted selection.
- [ ] Keep selected paths deterministic, sorted, deduplicated, and non-empty.
- [ ] Add CLI support for `--draft` and include selection reason in JSON/GitHub output.
- [ ] Run the selector engineering tests and verify all new tests pass.

### Task 4: Connect Draft/Ready state to GitHub Actions

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `.github/actions/change-scopes/action.yml` only if event metadata requires it
- Modify: `tests/engineering/test_backend_test_selection.py` or add `tests/engineering/test_ci_policy.py`

- [ ] Extend `pull_request` activity types to include `ready_for_review` and `converted_to_draft` while preserving `opened`, `synchronize`, and `reopened`.
- [ ] Pass `github.event.pull_request.draft` to the selector for PR events.
- [ ] Run both `targeted` and `risk-targeted` through the targeted pytest step.
- [ ] Use non-required `Backend iteration` for Draft and preserve required `Backend` for Ready/main; keep `Frontend` and `Engineering docs` stable.
- [ ] Keep main push, schedule, workflow dispatch, unknown paths, and CI/selector changes full.
- [ ] Add a concise `$GITHUB_STEP_SUMMARY` selection report with mode, reason, and test scope.
- [ ] Do not use Draft risk-targeted output as a Ready/high-risk merge result; the different Draft/Ready check names must force the latest Ready high-risk HEAD to execute the full step.
- [ ] Run YAML/static checks and the selector tests locally.

### Task 5: Freeze PR shape and review packet rules

**Files:**
- Modify: `docs/03-engineering-governance/01-rules/quality-gates.md`
- Modify: `docs/03-engineering-governance/01-rules/review-scorecard.md`
- Modify: `docs/03-engineering-governance/workflow.md`
- Modify: `docs/03-engineering-governance/task-modes.md`
- Add or modify: `.github/pull_request_template.md` if the repository has or adopts a PR template

- [ ] Add the Draft/Ready review lifecycle and state the exact final-full rule.
- [ ] Add review-packet fields: invariants, state table, source/type matrix, lock order, failure/retry/idempotency matrix, test mapping, non-goals, and current HEAD SHA.
- [ ] Require first review to cover three parallel lenses and consolidate findings by root-cause family.
- [ ] Require horizontal audit across selector/writer/heal/verify/equivalent paths for each P1/P2 finding.
- [ ] Add escalation after two consecutive rounds with new P1 findings: stop patching, split or redesign.
- [ ] Add the one-major-risk-domain-per-implementation-PR rule and prohibit new source-size exceptions over 1000 lines in feature PRs.
- [ ] Preserve existing review score and follow-up recording requirements.

### Task 6: Validate the workflow and record measured results

**Files:**
- Modify: `docs/03-engineering-governance/technical-debt.md`
- Modify: `docs/03-engineering-governance/current-work.md`
- Modify: `docs/03-engineering-governance/work-log.md` only at closeout

- [ ] Run selector/unit tests, Ruff, mypy baseline, docs gate, and diff-check.
- [ ] Create a temporary Draft probe containing an Agent high-risk path and verify the CI summary reports `risk-targeted` and the Backend wall time is at most 3 minutes.
- [ ] Convert the probe to Ready and verify the exact latest HEAD reports `full`; add a code commit while Ready and verify full is triggered again.
- [ ] Verify main push, manual/schedule, unknown path, and selector/CI changes remain full.
- [ ] Record actual timing and test counts; do not claim a target based on estimates.
- [ ] Update TD-092 completion evidence and workbench state only after the PR is merged.
- [ ] Run the full Backend once on the final HEAD and keep R1-S4-C paused until TD-092 is fully closed.

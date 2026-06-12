# DOC-059 新建 `check_task_completion_pr_consistency` 兜底脚本 — Spec

> Spec 入口：DOC-059 任务卡事实源 [`docs/03-engineering-governance/technical-debt.md#doc-059`](../../03-engineering-governance/technical-debt.md#doc-059)（L150 / L2045-L2089）。
> Plan：[`2026-06-12-doc-059-task-pr-consistency-fallback-plan.md`](../02-plans/2026-06-12-doc-059-task-pr-consistency-fallback-plan.md)。
> 工作日分支：`docs/doc-059-pr-consistency-fallback`。

## 背景

DOC-059 由 TD-048 漂移回退（[`work-log.md#2026-06-11-td-048-事实源漂移回退`](../../03-engineering-governance/work-log.md#2026-06-11-td-048-事实源漂移回退)）入账，违反"任务卡声明完成 vs `gh pr list --state merged` 是否真存在 PR"语义一致性。原计划走 `gh pr list --state merged --search <ID>`（任务卡 L2071），但 DOC-060（PR #206）+ DOC-063（PR #209）已将该路径演化为 git plumbing fast path（`git rev-parse mergeCommit^{commit}` < 5ms/次，零网络）。

本 spec 收口时**调整实现路径**：

- DOC-060 已覆盖"任务卡写明 PR 编号 + mergeCommit 字段"的校验（`check_task_card_stale_completion`）。
- DOC-059 本轮的独有价值 = "任务卡 🟢 完成但既没写 `| 交付 PR |` 字段、也没写 `| Merge Commit |` 字段"的兜底扫描（DOC-060 在 `task_card_claims.py` L225-227 显式 skip 这种卡"等 DOC-059 报"）。
- 实现用 `git log --oneline --all --grep <ID>` 兜底（< 1s/次，本地零网络；沙箱/CI 同样可用）。
- 不再使用 `gh pr list --search` 路径（DOC-063 已证明 gh 路径性能 6000x 落后于 git plumbing）。

## 目标

建立 `check_task_completion_pr_consistency_fallback`（_common.py 通用函数）+ `task_pr_consistency.py`（新 check 模块），扫三份事实源（`docs/03-engineering-governance/technical-debt.md` / `work-log.md` / `current-work.md`）中所有 `状态：🟢 完成` 任务卡，提取任务 ID，对每个 ID 跑 `git log --oneline --all --grep <ID>`，0 命中且任务卡里既无 `| 交付 PR |` 也无 `| Merge Commit |` 字段时报 1 个 `task-pr-consistency-fallback` issue。

## 验收标准（AC）

| AC | 描述 | 验证 |
|----|------|------|
| **AC-1** | 临时 `technical-debt.md` 含 1 个 `状态：🟢 完成` 任务卡（无 `\| 交付 PR \|` 也无 `\| Merge Commit \|` 字段），mock `_common._git_log_grep` 返回 `("UNAVAILABLE", ...)` → 跑 `python3 scripts/check-engineering-docs` 退出码 1，stderr 含 `task-pr-consistency-fallback-unavailable` + 含任务 ID。 | `test_fails_when_completed_debt_card_uses_git_log_fallback_unavailable` |
| **AC-2** | 临时 `technical-debt.md` 含 1 个 `状态：🟢 完成` 任务卡（无 PR 字段），mock `_common._git_log_grep` 返回 `("OK", 1)` → 跑 `python3 scripts/check-engineering-docs` 退出码 0（0 active issue）。 | `test_passes_when_completed_debt_card_has_pr_in_git_log` |
| **AC-3** | 临时 `technical-debt.md` 含 1 个 `状态：🟡 进行中` 任务卡，mock `_common._git_log_grep` 返回 `("UNAVAILABLE", ...)` → 跑 `python3 scripts/check-engineering-docs` 退出码 0（不扫非完成状态）。 | `test_skips_non_completed_task_cards` |
| **AC-4** | 在 `scripts/engineering/checks/task_card_claims.py` L225-227 处解除"DOC-059 负责'PR 不存在'；本 check 跳过，等 DOC-059 报"循环占位；改成不再 skip，由 DOC-060 报 `task-card-stale-completion-unavailable` + DOC-059 同时报 `task-pr-consistency-fallback` 互补报警。 | `rg -n "等 DOC-059 报\|DOC-059 负责.*PR 不存在" scripts/engineering/checks/task_card_claims.py` 0 命中 |
| **AC-5** | `python3 scripts/check-engineering-docs` 在当前 main 上退出码 0（基线 + DOC-059 新增 0 active issue）。 | 沙箱复跑 |
| **AC-6** | `python3 -m pytest tests/engineering/ -v` → 25 passed（22 旧 + 3 新）零回归。 | 沙箱复跑 |
| **AC-7** | `git diff --check` clean。 | 沙箱复跑 |
| **AC-8** | `rg -n "check_task_completion_pr_consistency_fallback\|task_pr_consistency" scripts/engineering/` 命中 ≥ 3 处（`_common.py` + `task_pr_consistency.py` + `__init__.py`）。 | 沙箱复跑 |

## 边界

- **不**实现 `gh pr list --search` 路径（DOC-060/063 路径已覆盖；性能 +6000x）。
- **不**新增 `KNOWN_ISSUES` 白名单（63 个 🟢 完成任务卡中预期 0 命中 false positive；如有遗漏由独立 PR 收口）。
- **不**缓存 git log 结果（首版简单实现；如性能不足由独立 PR 加 LRU cache）。
- **不**改 DOC-060 行为（DCO-060 在 `task_card_claims.py` L225-227 解除 skip 后的预期行为变化：当前 main 上 0 个卡满足此条件，所以 0 active issue；但语义更准确）。

## 风险

- **63 个 🟢 任务卡触发新 issue**：预期 0 命中 false positive；如有 CI 报"63 条 active issue"，由独立 DOC-xxx 收口。**不在本债范围内**。
- **git log 性能**：63 次串行 git log 在沙箱 < 5s，CI 上 < 2s。性能预算可接受。

## 跨事实源同步（PR-B 收口时执行）

- `docs/03-engineering-governance/technical-debt.md` L150 翻 🟢 完成 + L2089 任务卡补 PR 链接 + 交付记录补实施要点。
- `docs/03-engineering-governance/work-log.md` 追加 2026-06-12 DOC-059 索引行（含"本 DOC-059 是任务卡 L2071 重新定义后的工程脚本债"备注，避免与 2026-06-11 老 DOC-059 同号混淆）。
- `docs/03-engineering-governance/current-work.md` DOC-059 任务卡从"当前进行中"移到"最近完成"顶部。

## 不在范围内

- 重构现有 8 个 check（DCO-060 收口时已重构过）。
- 改 `gh` 路径（DOC-063 已重构成 git plumbing）。
- Backlog / Iteration / Milestone 集成（DOC-059 仅扫 3 份工程治理事实源）。

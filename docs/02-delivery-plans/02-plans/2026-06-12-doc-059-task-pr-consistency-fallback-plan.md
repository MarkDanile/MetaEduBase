# DOC-059 收口实施计划

> Plan 入口：DOC-059（PR-A 业务脚本 + PR-B docs-only 跨事实源收口，共 2 PR）。
> 验收口径见 [`2026-06-12-doc-059-task-pr-consistency-fallback.md`](../01-specs/2026-06-12-doc-059-task-pr-consistency-fallback.md)。
> 任务卡事实源：[`docs/03-engineering-governance/technical-debt.md#doc-059`](../../03-engineering-governance/technical-debt.md#doc-059)（L150 / L2045-L2089）。

## 切片划分

按 `task-modes.md#技术债修复` 切片节奏，本债分 **2 个 PR 收口**（与 DOC-060 收口时 PR-1 业务代码 + PR-2 docs-only 跨事实源的 2-PR 节奏一致）：

| 切片 | 内容 | 依赖 | 预计顺序 |
|------|------|------|----------|
| **PR-A 业务脚本** | `_common.check_task_completion_pr_consistency_fallback`（git log 兜底） + `task_pr_consistency.py` 新 check + 主入口注册 + 删 `task_card_claims.py` 中"DOC-059 负责'PR 不存在'；本 check 跳过，等 DOC-059 报"循环占位（DOC-060 改成不再 skip，让 DOC-060 报 `task-card-stale-completion-unavailable`、DOC-059 同时报 `task-pr-consistency-fallback`） + 3 个 pytest（inproc run_checker_inproc 走 mock 隔离） + `KNOWN_ISSUES` 加历史 14 个 task 白名单（与 DOC-060 收口时同款，让门禁不退回历史债） | 无 | 1 |
| **PR-B docs-only 跨事实源收口** | `docs/03-engineering-governance/technical-debt.md` L150 翻 🟢 完成 + L2089 任务卡补 PR-A 链接 + merge commit + 交付记录补 `check_task_completion_pr_consistency_fallback` 实施要点 + `docs/03-engineering-governance/work-log.md` 追加 DOC-059 索引行（同时保留 work-log 现有的 2026-06-11 DOC-059 "点名任务入口解析门禁"同号行，加 1 段"本 DOC-059 是 2026-06-12 重命名后的工程脚本债"备注避免后人混淆）+ `docs/03-engineering-governance/current-work.md` 把 DOC-059 任务卡从"当前进行中"移到"最近完成"区顶部 + 分支删除 | PR-A 合 main | 2 |

---

## PR-A 业务脚本

### Task A.1 — `_common.py` 新增 `check_task_completion_pr_consistency_fallback`

**位置**：`scripts/engineering/checks/_common.py`（与 `check_merge_commit_in_git_history` 同模块）

**签名**：
```python
def check_task_completion_pr_consistency_fallback(
    technical_debt_path: Path,
    work_log_path: Path,
    current_work_path: Path,
    *,
    repo_root: Path,
) -> list[Issue]:
    """DOC-059: git log 兜底路径。

    任务卡 L2071 原计划走 `gh pr list --state merged --search <ID>`（49+ 次串行
    gh，DOC-063 已重构成 git plumbing fast path）。DOC-059 收口时调整实现为
    git log 兜底（DOC-060 已用 `check_merge_commit_in_git_history` 覆盖『任务卡
    写明 PR 编号 + mergeCommit』维度；本函数专扫『任务卡 🟢 完成但任务卡里既
    没写 PR 编号、也没写 Merge Commit 字段』的兜底维度）。

    算法：
    1. 扫 3 份文档的 🟢 完成 任务卡（technical-debt / work-log / current-work）
    2. 提取所有任务 ID（正则 `\b(?:TD|DOC|REQ)-\d{3}(?:-\d+)?\b`）
    3. 对每个 ID 跑 `git log --oneline --all --grep <ID>` （timeout 5s/次）
    4. 命中 0 行（== merge commit 或工作 commit 在 git history 都不存在）报 1 个
       `task-pr-consistency-fallback` issue：
       - path = 文档路径
       - line_no = 🟢 完成 行号（或任务卡起始行）
       - message = "任务卡片声明完成但 git history 无 <ID> 关键字命中（兜底：PR 编号 / Merge Commit 字段也未提供）"
       - suggestion = "在任务卡『交付 PR』段下补 `| 交付 PR |` 字段，或在 KNOWN_ISSUES 跳过本任务；DOC-060 也会同时报 `task-card-stale-completion-unavailable`"

    沙箱降级：`git` 不可用 / 超时时 issue 改 code =
    `task-pr-consistency-fallback-unavailable` + message 写"未运行: git
    log 受环境限制"，按 `quality-gates.md#验证表述规范` 的 `未运行` 分支。

    性能预算：63 个 🟢 完成 任务卡 × 5s timeout 上限 = 上界 315s，但 git log
    --grep 在本地仓库 < 1s/次，实际 < 5s；CI 上（Linux）更快。如果有性能问题，
    后续可加 LRU cache（按 ID 缓存 git log 结果），但首版不引入。
    """
```

**复用现有 helpers**：`_common` 已有 `TASK_ID_RE`（注意：DOC-059 的 regex 与 `_common.TASK_ID_RE` 略有差异——`_common.TASK_ID_RE` 用 `(?:REQ|TD|DOC|BUG|APP)-\d{3}` 不带子任务后缀；DOC-059 任务卡 L2071 写的是 `(?:TD|DOC|REQ)-\d{3}(?:-\d+)?` 含子任务后缀但 BUG/APP 不在扫描范围）。本函数用 DOC-059 任务卡指定的正则（在函数内 `re.compile` 局部常量），不复用 `_common.TASK_ID_RE`（避免影响现有 check）。

**DONE_STATUS_RE 复用**：DOC-060 已在 `task_card_claims.py` 写 `DONE_STATUS_RE = re.compile(r"状态[:：]\s*🟢\s*完成")`。DOC-059 复用它（从 `task_card_claims` 模块 re-export），避免重复定义。

### Task A.2 — 新建 `task_pr_consistency.py`

**位置**：`scripts/engineering/checks/task_pr_consistency.py`（新文件，参考 `task_card_claims.py` 头部 docstring 风格）

**导出**：
```python
def check(root: Path) -> list[Issue]:
    """DOC-059 入口：扫 3 份文档的 🟢 完成 任务卡，git log 兜底校验。

    调用 `_common.check_task_completion_pr_consistency_fallback` 拆 3 份文档
    路径后批量调用。返回合并的 issue 列表。
    """
```

**不在本 check 里做**：正则匹配（收敛到 `_common` 函数）、PR 字段提取（DOC-060 已覆盖）、merge commit 校验（DOC-060 已覆盖）。DOC-059 只补"任务卡完成但 PR 字段缺失"这个 DOC-060 skip 留下的口子。

### Task A.3 — `__init__.py` 注册新 check

**位置**：`scripts/engineering/checks/__init__.py`

**变更**：
1. 新增 import：`from .task_pr_consistency import check as check_task_pr_consistency`
2. 在 `KNOWN_CHECKS` 元组末尾追加 `check_task_pr_consistency`
3. 注释：`# DOC-059: 兜底扫『任务卡 🟢 完成但未写 PR 编号 / Merge Commit』，git log 路径`

### Task A.4 — 修 `task_card_claims.py` 解除循环占位

**位置**：`scripts/engineering/checks/task_card_claims.py` L225-227

**变更**：
```python
# OLD
if pr_number is None:
    # DOC-059 负责"PR 不存在"；本 check 跳过，等 DOC-059 报。
    continue
# NEW
if pr_number is None:
    # 任务卡未写 `| 交付 PR |` 字段：DOC-060 报
    # `task-card-stale-completion-unavailable`（让人类补字段或显式
    # KNOWN_ISSUES 跳过），DOC-059 同时报 `task-pr-consistency-fallback`。
    # 不再 skip，由两层门禁独立报警。
    sub_issues = check_task_card_claim_vs_code(
        task_id=task_id,
        claim_kind="pr_state",
        declared_value="MERGED",
        pr_number=None,
        merge_commit=None,
        repo_root=root,
    )
    ...
    continue
```

**预期行为变化**：当前 main 上 0 个 🟢 任务卡缺 PR 字段（DOC-060 收口后 14 个历史 task 都进了 KNOWN_ISSUES 白名单），所以**改后新增 0 条 active issue**。但语义上更准确：DOC-060 + DOC-059 互补、不再 skip。

### Task A.5 — 3 个 pytest

**位置**：`tests/engineering/test_check_engineering_docs.py`（紧跟现有 `test_fails_when_residual_count_claim_diverges_from_ripgrep` 后）

**test 1：`test_fails_when_completed_debt_card_uses_git_log_fallback_unavailable`**（DOC-059 主路径）

- 临时 `tmp_path` 写 1 份 technical-debt.md，含 1 个 `状态：🟢 完成` 任务卡（**无** `| 交付 PR |` 字段 + **无** `| Merge Commit |` 字段 + **不**在 KNOWN_ISSUES 白名单）
- mock `_common.is_known` 返回 False（绕白名单）
- mock `_common._git_log_grep`（新私有 helper）返回 `("UNAVAILABLE", "未运行: git log 受环境限制")`（或更准确：mock 整个 `check_task_completion_pr_consistency_fallback` 的 subprocess 入口）
- `run_checker_inproc` 走 pytest 进程内
- 断言：退码 1 + stderr 含 `task-pr-consistency-fallback-unavailable` + 含任务 ID
- 这是沙箱环境的真实场景（沙箱 git log 可用，但测试要锁"未运行降级"路径）

**test 2：`test_passes_when_completed_debt_card_has_pr_in_git_log`**（命中 git log 正常通过）

- 临时 `tmp_path` 写 1 份 technical-debt.md，含 1 个 🟢 完成 任务卡（**无** PR/Merge Commit 字段）
- mock `_common._git_log_grep` 返回 `("OK", 1)`（表示 1 个 commit 命中）
- `run_checker_inproc`
- 断言：退码 0（0 active issue）

**test 3：`test_skips_non_completed_task_cards`**（不扫 🟡 / 🟣 / 🔵 等）

- 临时 `tmp_path` 写 1 份 technical-debt.md，含 1 个 `状态：🟡 进行中` 任务卡
- mock `_common._git_log_grep` 返回 `("UNAVAILABLE", ...)`（如跑过就会报）
- `run_checker_inproc`
- 断言：退码 0（不应该触发 git log；只扫 🟢 完成）

**mock 策略**：参考 DOC-060 现有 mock 模式（`patch.object(_common, "is_known", return_value=False)` + `patch.object(_common, "check_merge_commit_in_git_history", return_value=...)`），DOC-059 的 mock 用 `patch.object(_common, "_git_log_grep", return_value=...)`（私有 helper 命名待定；可改 `check_git_log_grep` 公开）。

### Task A.6 — `KNOWN_ISSUES` 历史白名单

**位置**：`scripts/engineering/checks/_common.py` L67-142 段（DOC-060 14 个 task 白名单已就位）

**变更**：DOC-059 引入新 code `task-pr-consistency-fallback` / `task-pr-consistency-fallback-unavailable`。本轮不预加白名单（63 个 🟢 完成 任务卡中预期大部分都能 git log 命中；如出现 false positive 再由独立 PR 收口）。

**例外**：DOC-059 任务卡 L2088 的历史债 "TD-048 漂移回退的 3 PR"（`#196` / `#197` / `#198`）—— 这 3 个 PR 已合 main，git log 能搜到 `TD-048` 关键字。不需白名单。

### Task A.7 — 验证

```bash
# 本地沙箱
python3 scripts/check-engineering-docs
# 期望：退出码 0 或 1（按当前 KNOWN_ISSUES 状态），DOC-059 新增 0 active issue

python3 -m pytest tests/engineering/ -v
# 期望：22 + 3 = 25 passed

git diff --check
# 期望：clean
```

### Task A.8 — 提交 + PR

- 分支：`docs/doc-059-pr-consistency-fallback`
- 提交：`feat(engineering): DOC-059 — task completion PR consistency fallback (git log)`
- PR 描述：Summary（2-3 行）/ Scope（5 个文件）/ Validation（3 个 pytest + `scripts/check-engineering-docs` + `git diff --check`）/ Risks（63 个 🟢 卡可能触发新 issue，需独立 PR 收口）/ Docs（PR-B 待提）
- squash merge 合 main

---

## PR-B docs-only 跨事实源收口

### Task B.1 — 翻 DOC-059 状态

**位置**：`docs/03-engineering-governance/technical-debt.md` L150

**变更**：
- `| DOC-059 | 新建 ... | ⚫ 待办 | P2 | ... |` → `| DOC-059 | 新建 ... | 🟢 完成 | P2 | ... |`
- 状态描述段（CSV 字段 `事实源` 后的描述）末尾追加 `|[PR #<PR-A>](https://github.com/MarkDanile/MetaEduBase/pull/<PR-A>) (merge \`<sha>\`)|`

### Task B.2 — 补任务卡交付记录

**位置**：`docs/03-engineering-governance/technical-debt.md` L2086-2088

**变更**（参考 DOC-060 收口 L2089 的格式）：
```markdown
- 2026-06-12 收口（接手工具：Claude Code），2 PR：
  - PR-A 业务脚本（[PR #<N>](https://github.com/MarkDanile/MetaEduBase/pull/<N>) / merge \`<sha>\` / 分支 \`docs/doc-059-pr-consistency-fallback\`）：在 `scripts/engineering/checks/_common.py` 加 `check_task_completion_pr_consistency_fallback`（git log 兜底路径，DOC-059 任务卡 L2071 原计划 `gh pr list` 路径已被 DOC-060/063 改用 git plumbing 取代，本债改走 git log --grep <ID> 兜底）+ 新建 `scripts/engineering/checks/task_pr_consistency.py` 注册 `check_task_pr_consistency` + `__init__.py` 主入口注册新 check + 修 `task_card_claims.py` L225-227 解除"等 DOC-059 报"循环占位（DOC-060 改成同时报 `task-card-stale-completion-unavailable`）+ 3 个 pytest（`_git_log_grep` mock 隔离；inproc `run_checker_inproc` 走 pytest 进程内）。`scripts/check-engineering-docs` 退出码 0（DOC-059 新增 0 active issue）；`git diff --check` clean；`pytest tests/engineering/` 25 passed 零回归（22 旧 + 3 新）。
  - PR-B docs-only 跨事实源收口（本 PR）。
```

### Task B.3 — work-log 索引行

**位置**：`docs/03-engineering-governance/work-log.md` L18 之上插入

**变更**：
```markdown
| 2026-06-12 | DOC-059 新建 `check_task_completion_pr_consistency` 兜底脚本扫『任务卡完成 → PR 真实存在』语义一致性（与 2026-06-11 归档的"DOC-059 点名任务入口解析门禁"是同名不同事；本 DOC-059 是任务卡 L2071 重新定义后的工程脚本债） | 工程脚本 / 质量门禁 / 任务卡完成 → PR 一致性 / git log 兜底 |  |  | `docs/03-engineering-governance/technical-debt.md#doc-059`（L150 翻 🟢 完成 + L2089 任务卡补 PR-A/B 链接）/ `docs/03-engineering-governance/current-work.md`（DOC-059 任务卡移到"最近完成"顶部）/ 分支 `docs/doc-059-pr-consistency-fallback`（待删） |
```

**注意**：work-log L27 已存在 `2026-06-11 | DOC-059 点名任务入口解析门禁 ...` 的同名行（与 L205 序号 23 重复），需在 L27 那行末尾加 1 段 `（注：此 DOC-059 是 2026-06-11 老债，与 2026-06-12 新 DOC-059 同号不同事）` 备注，避免后人搜 DOC-059 出来 2 条都以为是同一事。

### Task B.4 — current-work 移最近完成

**位置**：`docs/03-engineering-governance/current-work.md` L17-19

**变更**：
- 任务卡字段从 `🟡 进行中` / `🟣 待验证` / `🔵 就绪` → `🟢 完成`（pre-PR-B 阶段用 `🟡 进行中` 占位，PR-B 收口时再翻）
- 摘要 ≤ 220 字符（按 `CURRENT_WORK_RECENT_SUMMARY_LIMIT`）
- 行格式：`| 2026-06-12 | DOC-059 ... | 🟢 完成 | 2 PR 收口（PR-A 业务脚本 + PR-B docs-only）：git log 兜底扫任务卡完成 → PR 真实存在；DOC-060 改同时报 stale-completion-unavailable；25 pytest 零回归。 | [DOC-059](../../03-engineering-governance/technical-debt.md#doc-059) / PR #<PR-A>（merge \`<sha>\`）/ PR #<PR-B>（merge \`<sha>\`） |`

### Task B.5 — 验证

```bash
python3 scripts/check-engineering-docs
python3 -m pytest tests/engineering/ -v
git diff --check
```

### Task B.6 — 提交 + PR

- 分支：`docs/doc-059-pr-consistency-fallback-cross-source-closure`
- 提交：`docs(governance): DOC-059 — post-merge cross-source closure (work-log / debt / workbench)`
- PR 描述：Summary / Scope（3 文件）/ Validation / Risks / Docs
- squash merge 合 main
- 合并后删远端分支

---

## 验证方式（端到端）

按 task 卡 L2078-L2084 + L2089 同款验证口径：

- 运行 `python3 scripts/check-engineering-docs` 退出码 0（本机沙箱复跑；DOC-059 新增 0 active issue）
- 运行 `python3 -m pytest tests/engineering/ -v` → 25 passed（22 旧 + 3 新）零回归
- 运行 `git diff --check` clean
- 运行 `rg -n "check_task_completion_pr_consistency_fallback|task_pr_consistency" scripts/engineering/` 命中 ≥ 3 处（`_common.py` + `task_pr_consistency.py` + `__init__.py`）
- 临时写 1 个含 `状态：🟢 完成` 但**无** `| 交付 PR |` 也**无** `| Merge Commit |` 字段、且 ID 不在 KNOWN_ISSUES 的假任务卡（mock `git log --grep` 返回 0 命中），跑 `python3 scripts/check-engineering-docs` → 退出码 1 + stderr 含 `task-pr-consistency-fallback`；删假任务卡后恢复 0
- 运行 `gh pr view <PR-A> --json state` state = MERGED
- 运行 `gh pr view <PR-B> --json state` state = MERGED
- 运行 `git log --oneline origin/main` 包含 PR-A + PR-B 的 merge commit
- 确认 `docs/03-engineering-governance/current-work.md` L37 `🟢 完成` 区有 DOC-059 行（PR-B 落地后）
- 确认 `docs/03-engineering-governance/work-log.md` 索引行有 2026-06-12 DOC-059 新行（PR-B 落地后）

---

## 风险

- **63 个 🟢 任务卡触发新 issue**：DOC-059 兜底路径只扫"无 PR 字段"卡，预期 0 命中（DCO-060 收口后 14 个历史 task 补了 PR 字段），但如有遗漏，63 个卡会触发 63 条 issue。**缓解**：本轮先合 DOC-059；如果 CI/PR 上报"63 条 active issue"，由独立 DOC-xxx 收口。**不在本债范围内**。
- **git log 性能**：63 次串行 git log 在沙箱 < 5s，CI 上 < 2s。如有性能问题，后续可加 LRU cache（按 ID 缓存结果），但首版不引入。
- **DOC-060 行为变化**：本债 PR-A 会让 DOC-060 不再 skip "无 PR 字段"卡。当前 main 上 0 个卡满足此条件，但如有未来任务卡漏写 PR 字段，DCO-060 + DCO-059 会同时报警。**这是预期行为**，不是回归。
- **work-log 同号备注**：work-log L27 已有 2026-06-11 DOC-059 老债；本轮 B.3 会加备注避免后人混淆，但 work-log 仍保留 2 条 DOC-059 索引行（合任务卡 "DCO-xxx 不强制编号"原则）。

---

## 关键文件清单

| 文件 | 角色 | 变更 |
|------|------|------|
| `scripts/engineering/checks/_common.py` | 共享 | 加 `check_task_completion_pr_consistency_fallback` + `_git_log_grep` 私有 helper |
| `scripts/engineering/checks/task_pr_consistency.py` | 新建 | 导出 `check` 函数 |
| `scripts/engineering/checks/__init__.py` | 共享 | import + 注册 `check_task_pr_consistency` |
| `scripts/engineering/checks/task_card_claims.py` | 共享 | L225-227 改"不再 skip，由两层门禁独立报警" |
| `tests/engineering/test_check_engineering_docs.py` | 测试 | +3 个 pytest |
| `docs/03-engineering-governance/technical-debt.md` | 事实源 | L150 翻 🟢 + L2089 补 PR 链接 + 描述补实施要点（PR-B） |
| `docs/03-engineering-governance/work-log.md` | 事实源 | +1 行 2026-06-12 DOC-059 索引行 + L27 加同名备注（PR-B） |
| `docs/03-engineering-governance/current-work.md` | 事实源 | DOC-059 任务卡移到"最近完成"顶部（PR-B） |
| `docs/02-delivery-plans/01-specs/2026-06-12-doc-059-task-pr-consistency-fallback.md` | 新建 | 验收口径（spec） |
| `docs/02-delivery-plans/02-plans/2026-06-12-doc-059-task-pr-consistency-fallback-plan.md` | 新建 | 本文件（plan） |

---

## 复盘

DOC-059 收口的核心教训是**任务卡描述与现状冲突时要及时调整**：

- 任务卡 L2071 写于 2026-06-11 的 `gh pr list` 路径，已被 DOC-060 + DOC-063 演化为 git plumbing 路径（性能 +6000x，零网络）。本债强行按 L2071 写会与现状冲突。
- DOC-059 真正剩下的独有价值 = "任务卡 🟢 完成但 PR 字段缺失"的兜底扫描（DOC-060 显式 skip 这种卡）。**调整实现路径不改债的价值**，比硬照搬任务卡描述更合理。
- 经验：P2 债 1-2 周内被覆盖时，调整实现路径 + 标注"任务卡 L2071 路径已被 X 替代"是合理收口方式；不应浪费在重写已弃用的 gh 路径上。

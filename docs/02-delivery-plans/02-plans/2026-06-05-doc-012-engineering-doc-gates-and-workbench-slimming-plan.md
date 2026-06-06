# DOC-012 工程文档自动门禁与工作台瘦身 — Plan

## 任务入口

- Spec: `docs/02-delivery-plans/01-specs/2026-06-05-doc-012-engineering-doc-gates-and-workbench-slimming.md`
- 任务卡片: `docs/03-engineering-governance/current-work.md` 的 DOC-012 候选行
- 类型: 文档 / 工程规范 / 工具链
- 当前执行模式: plan-do

## 实施顺序

### 1. 建立最小工程文档门禁

- [x] 确认仓库现有脚本目录约定；主实现放到 `scripts/engineering/check_engineering_docs.py`，`scripts/check-engineering-docs` 保留兼容入口。
- [x] 选择简单可维护的实现方式，优先使用 Python 标准库或 shell + `rg`，不引入新依赖。
- [x] 输出格式包含文件、行号、问题和建议动作。

### 2. 检查 current-work 区域约束

- [x] 解析 `docs/03-engineering-governance/current-work.md` 的三个区域。
- [x] 校验“下一批候选任务”只保留 1 到 3 个未完成候选。
- [x] 校验候选区不得出现 `🟢 完成`。
- [x] 校验“最近完成”最多 5 行。

### 3. 检查已完成 plan 的活动式未完成项

- [x] 找出已完成任务对应的 plan 范围。
- [x] 校验已完成 plan 不残留活动式 `- [ ]`。
- [x] 允许明确 out of scope 或绑定后续任务编号的未完成项，避免误报历史说明。

### 4. 检查 Markdown 相对链接

- [x] 扫描 `docs/03-engineering-governance/*.md`、`docs/02-delivery-plans/01-specs/*.md`、`docs/02-delivery-plans/02-plans/*.md` 的 Markdown 链接。
- [x] 对本仓库内相对路径做存在性校验。
- [x] 忽略外部 URL、锚点-only 链接和明确历史兼容链接。

### 5. 检查 work-log 追加式索引风险

- [x] 在脚本中检查当前 diff 中 `docs/03-engineering-governance/work-log.md` 的删除行。
- [x] 如果删除或替换任务索引行，要求提交说明或任务文档中有明确原因。
- [x] 失败信息提示“默认新增索引，不要覆盖旧行”。

### 6. 检查验证声明证据格式

- [x] 扫描 `docs/03-engineering-governance/*.md`、`docs/02-delivery-plans/01-specs/*.md`、`docs/02-delivery-plans/02-plans/*.md` 中的强通过声明。
- [x] 对“全量 pytest passed / tests passed / ruff passed”等声明要求附近存在命令、结果、环境或 CI/PR checks 证据。
- [x] 如果验证无法复核，要求写成“未通过 / 未运行 / 当前环境不可运行 + 原因”。

### 7. 瘦身 current-work 入口

- [x] 新增或更新 `docs/03-engineering-governance/01-rules/workbench.md`，承载状态流、保留策略和任务卡片模板。
- [x] 将 `current-work.md` 保留为短入口：使用规则摘要、当前进行中、下一批候选任务、最近完成。
- [x] 确保 `AGENTS.md` / `CLAUDE.md` 的入口指向仍准确。

### 8. 接入完成门禁

- [x] 在 `docs/03-engineering-governance/01-rules/quality-gates.md#完成门禁` 中引用工程文档门禁命令。
- [x] 在 `docs/03-engineering-governance/01-rules/git-workflow.md#快速交付通道` 的文档-only 验证中引用该命令。
- [x] 在 `docs/03-engineering-governance/01-rules/docs.md` 中记录 `scripts/engineering/*` 与 `scripts/*` 的目录边界。
- [x] 避免重复展开脚本内部检查细节。

### 9. 验证

- [x] 运行工程文档门禁命令，确认退出码 0。
- [x] 临时制造一个候选区完成行或断链，确认命令退出非 0 并输出可操作提示；随后还原。
- [x] `git diff --check` 退出码 0。
- [x] `rg -n "check-engineering-docs|工程文档门禁" docs/03-engineering-governance AGENTS.md CLAUDE.md` 命中新入口。

## 验证记录

- `packages/server-python/.venv/bin/python -m pytest tests/engineering/test_check_engineering_docs.py -q`：8 passed，覆盖主实现与兼容 wrapper。
- `packages/server-python/.venv/bin/python scripts/engineering/check_engineering_docs.py`：退出码 0，输出 `engineering docs checks passed (1 known issue(s) allowlisted)`。
- `packages/server-python/.venv/bin/python scripts/check-engineering-docs`：退出码 0，输出与主实现一致；allowlist 指向已登记的 TD-023。
- `git diff --check`：退出码 0。
- `rg -n "check-engineering-docs|工程文档门禁|workbench.md" docs/03-engineering-governance AGENTS.md CLAUDE.md`：命中新门禁入口和 workbench 规则索引。
- 负向临时验证：在临时目录制造 `🟢 完成` 候选行和断链，脚本退出码 1，并输出具体文件、行号和建议动作。
- 首次运行真实门禁发现 TD-004 历史 plan 的两个断链，已修正为可跳转相对链接。

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| 脚本误报历史文档 | 第一版聚焦当前事实源和 docs 工程文档；必要时加白名单并写清原因 |
| 门禁过重拖慢提交 | 文档门禁只做文本解析和文件存在性检查，不跑业务测试 |
| current-work 瘦身后 agent 找不到模板 | 模板迁入 `rules/workbench.md`，入口文档保留链接 |
| 规则再次膨胀 | 入口只引用命令和规则文档，不复制脚本检查细节 |

## 提交前最终回查

- `current-work.md` 候选区仍只保留 1 到 3 个未完成候选。
- DOC-012 的 spec/plan/current-work 状态一致。
- 新增命令的失败输出足够具体。
- 文档-only PR 范围不混入业务代码。

# 跨 AI 开发工作流

本文件统一 Codex、Claude Code、Trae、superpower 和其他插件的协作入口。工具可以不同，事实源和交付闭环必须一致。

## 核心原则

- 仓库文档是事实源，插件是执行工具。
- 当前状态统一维护在 `docs/03-engineering-governance/current-work.md`。
- 修改工作台或任务状态前，先读 `01-rules/workbench.md`。
- 会修改仓库文件时，先按 `01-rules/git-workflow.md#开发前分支门禁` 确认不在 `main`。
- 任务模式、开工条件和完成标准见 `task-modes.md`。
- 最终回复不是事实源；PR 是默认交付事实源。
- 插件输出不是唯一事实源；spec/plan 必须迁移或镜像到 `docs/02-delivery-plans/01-specs/*` / `02-plans/*`。
- 复核、测试、PR review 或验收发现的问题必须修复或入账，不停留在聊天记录。

## 开发前检查

1. 读 `current-work.md`；点名任务不在工作台时，按 `task-modes.md#任务入口解析门禁` 定位事实源。
2. 会修改文件时运行 `git status --short --branch`；在 `main` 时先建任务分支。
3. 按任务卡片渐进式读取 spec、plan、技术债、Requirement、Milestone、架构或专项规则。
4. 需要更新工作台时，读 `01-rules/workbench.md` 并把任务移入“当前进行中”。
5. 明确本轮范围、完成标准、验证方式和当前分支。

很小的即时修复或纯问答可以不新增任务卡；跨文件修改、计划接力、状态交接或后续继续开发必须登记。

## 计划来源优先级

1. 用户当前对话明确指定的计划或文档。
2. `current-work.md` 任务卡片链接的 Plan。
3. `docs/02-delivery-plans/02-plans/*`。
4. `docs/02-delivery-plans/01-specs/*`。
5. `docs/01-product-planning/*`。
6. `docs/90-compat-legacy/superpowers/*`。
7. `ARCHITECTURE.md` 长期约束。

文档冲突时，不静默选择；先指出冲突并请用户确认。

## 开发中规则

- 只实现任务卡片和计划要求的内容。
- 不做无关重构、资产清理或历史问题顺手修复。
- 发现新债务，先入账；除非阻塞当前任务，否则不扩范围。
- 计划与代码事实冲突时，先更新 plan / 任务卡或向用户确认。
- 后续遗留按 `task-modes.md#follow-up-分流` 建稳定编号。

## 任务池索引与插入规则

- `04-backlog.md`：产品 / 需求 / BUG / APP / DOC 索引，不写长 PRD；新增条目追加到对应主表，长内容进 Requirement / spec / plan。
- `technical-debt.md`：技术债总账；任务编号稳定，新增条目追加到总览和详情；长交付细节进 PR / work-log。
- 主表新增编号必须放在同前缀最后；不要把新编号插入历史编号中间。
- 多电脑或并行窗口临时登记用 `DRAFT-YYYYMMDD-HHMM-XXXX`；进入主表前归并为 `REQ` / `BUG` / `TD` / `DOC` / `APP` 正式编号，DRAFT 只留在来源字段。
- `work-log.md`、`review-score-log.md`：长期日志，最新在上。
- `current-work.md`：当前工作台，不是完整 backlog；只保留当前、候选和最近完成窗口。
- `workflow.md`：流程规则，不记录任务流水。

AI 查找任务时优先 `rg "REQ-xxx|TD-xxx|BUG-xxx|DOC-xxx"` 精确定位，只读命中小段；不要为了插入一行通读或重排整份长文档。

## 并行开发模式

仅用户明确触发时启用。协调者先输出并行可行性评估：任务、agent、分支、worktree / clone、允许范围、禁止范围、共享契约、冲突点、合并顺序、集成负责人。

并行期间，各 agent 少改全局事实源；过程状态写各自 plan / PR。完成后由集成者统一验证、回填工作台、Backlog、milestone、work-log、评分和 follow-up。

## 开发后收尾

1. 运行与范围匹配的验证；环境阻塞时记录命令、失败摘要、影响范围。
2. 更新工作台状态、进展、下一步和验证结果。
3. 执行 `01-rules/quality-gates.md#完成门禁`。
4. 技术债、需求、BUG、DOC 等任务同步对应总账。
5. 需要长期追踪的完成项写入 `work-log.md`。
6. 用户要求提交时，按 `01-rules/git-workflow.md#快速交付通道` 推进到指定阶段。
7. 完整 Git 闭环后，清除交付占位；PR 未 merge 不得写 `🟢 完成`。

## 插件使用规则

- superpower、compound-engineering-plugin 等生成的 spec/plan 必须登记到任务卡片的 `插件输出`。
- 进入开发前，把规范副本迁移或镜像到 `docs/02-delivery-plans/01-specs/*` / `02-plans/*`。
- 插件内部状态不能替代 `current-work.md`。
- `.claude/rules/*`、`.trae/rules/*` 和其他 IDE 私有规则只做跳转入口，不维护正文副本。

## Superpower 兼容规则

superpower 可继续读写 `docs/90-compat-legacy/superpowers/*`，但开工必须先读 `current-work.md`；新 spec/plan 必须迁入或镜像到交付层；若插件生成旧顶层目录，视为路径门禁失败，迁移后再提交。

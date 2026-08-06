# Quality Gates — 质量门禁规范

质量门禁按改动范围选择。目标是留下可复现证据，而不是写“看起来通过”。

## 基本原则

- 先跑最小相关验证，再按风险扩展。
- 本地 commit / push 只做秒级静态反馈；分钟级 pytest 进入 CI，不重复堆叠在每个阶段。
- 退出码为 0 才能写“通过”；非 0 且属历史问题时，写“未通过；失败项属于 TD-xxx；本任务未新增”。
- 文档-only 也要检查链接、编号、状态、引用路径。
- 未解决问题必须绑定已有任务或新增任务，不停留在聊天记录。

## 执行分层

| 阶段 | 默认职责 |
|------|----------|
| pre-commit | 只检查 staged 文件：Ruff / ESLint / 文档门禁 / lock 一致性；不跑 pytest 或全量 typecheck |
| pre-push | 按 `origin/main` 到 `HEAD` 的净变更执行相关模块静态门禁；不跑 pytest |
| PR CI | 三个 required check 始终出现；无关 job 快速 no-op，相关后端运行 targeted 或完整 hermetic 回归 |
| 定时 / 手动 CI | 全 scope + 后端完整 hermetic 回归；真实外部服务验收不进入自动 CI |

路径分类事实源为 `scripts/ci/detect-change-scopes`；未知路径必须 fail-safe 全跑。Codex、Claude Code 和人工终端共同使用仓库 hooks，不维护 Agent 私有门禁。

后端 scope 内的进一步测试选择必须基于稳定模块所有权和风险分级；不得按文件数量任意分片，也不得仅因改动行数少而跳过共享、鉴权、租户、迁移或测试基础设施的完整回归。专项治理见 TD-083。

### Draft / Ready 复审门禁

- Draft PR 是返修迭代状态，不得合并，并只产生非 required 的 `Backend iteration` check。普通叶子 Context 运行 targeted；可迭代高风险路径运行 risk-targeted；CI、selector、shared、identity/security、全局 fixture、依赖锁和未知路径仍 full fail-safe。
- PR 转为 Ready 后才产生 required `Backend` check；高风险 PR 的当前最新 HEAD 必须运行完整 hermetic Backend。Ready 状态下的每次代码推送都会重新触发 `Backend` full；需要继续返修时先转回 Draft，避免把中间提交误当最终验收。
- `main` push、schedule、workflow_dispatch 始终运行 full；risk-targeted 只能提供中间反馈，不能作为高风险 PR 的合并证据。
- PR 交接必须记录 selector mode、reason、pytest scope 和当前 HEAD；复审方必须以该 HEAD 重新同步，过期 HEAD 的 finding 不进入返修批次。

## 完成门禁

提交、PR、合并或声明完成前执行本节：

1. 范围：`git diff --name-status` 或 PR Scope 只包含本任务；无关资产、生成物、缓存、人工清理不得混入。
2. 验证：写真实命令 / 手动场景、退出结果、文件范围、环境；不得用主观判断替代输出。
3. 状态：`current-work.md`、Backlog、Requirement、Iteration、Milestone、TD、spec/plan、work-log 不互相矛盾。
4. 完成：PR 未 `MERGED` 前不得写 `🟢 完成`；硬条件见 `git-workflow.md#翻完成前硬条件` 和 `workbench.md#状态同步规则`。
5. 计数：写“全部收口”“N 个 AC / 用例 / 文件 / 任务”时，回到源文件或命令输出逐条核对。
6. 占位：完成态不得残留 `未运行`、`待提交`、`以最终回复为准`、`TBD`、`TD-???` 等活动占位。
7. 工作台：`下一批候选任务` 只保留 1 到 3 个未完成候选；`最近完成` 超过 20 行时一次性裁剪到最新 12 行。
8. 插件输出：spec/plan 事实源必须指向 `docs/02-delivery-plans/01-specs/*` / `02-plans/*`。
9. 收口方式：工作台状态变更、工程治理事实源变更必须走 PR；禁止 `git push origin main` 直推。
10. 门禁失败：先修被拦截对象；禁止在当前任务内修改门禁脚本、`KNOWN_ISSUES`、忽略列表、阈值或 CI 配置来绕过失败。
11. AI / RAG 效果型任务：完成态必须写最高验证层级；代码接入、mock、dry-run、真实 PG、真实 LLM / 用户验收不得互相冒充。

文档、规则、spec、plan、任务状态或交接信息变化时，额外运行：

```bash
scripts/check-engineering-docs
```

## 脚本门禁候选清单

本节只记录可脚本化方向；标为“已实现”的项必须能被 `scripts/check-engineering-docs` 或其子 check 反查。

| 候选门禁 | 当前状态 | 触发价值 |
|----------|----------|----------|
| `current-work.md` 最近完成最多 20 行，超过后只保留最新 12 行 | 已实现 | 防止工作台无限扩张 |
| `current-work.md` 下一批候选最多 3 行，且不允许 `🟢 完成` | 已实现 | 防止候选区变历史索引 |
| `current-work.md` 当前进行中无活跃任务时只保留单句，不得追加完成摘要段落 | 已实现 | 防止当前进行中区被完成摘要段落污染 |
| 已完成任务不得残留 `未运行`、`待提交`、`以最终回复为准` 等占位 | 已实现 / 持续补强 | 防止完成态漂移 |
| Backlog、Requirement、current-work、work-log、score log、technical-debt 中任务 ID 唯一且状态不冲突 | 候选 / 部分实现 / [DOC-077](../../01-product-planning/04-backlog.md) | 降低跨事实源漂移，阻止同一 ID 映射到不同任务语义 |
| 禁止把 `REQ-xxx-FOLLOWUP` / `TD-xxx-FOLLOWUP` 作为长期任务编号 | 已实现 | 保持稳定检索 |
| `DRAFT-*` 临时编号不得作为正式任务池主键 | 已实现 | 支持多电脑登记但不污染长期编号 |
| `Done` 任务在 Backlog / current-work / work-log 之间有最小索引闭环 | 已实现 | 防止关闭后事实源缺失 |
| Backlog / technical-debt 主表最新编号必须位于同前缀最后 | 已实现 | 防止新任务插入历史编号中间 |
| spec / plan 中 `TBD` / `TD-???` / `未回填` 扫描 | 候选 | 防止完成态残留占位 |
| 旧 docs 路径残留检查 | 已实现 | 防止目录迁移回退 |
| Markdown 相对链接存在性检查 | 已实现 | 防止断链 |
| AGENTS.md / CLAUDE.md 与 IDE 兼容入口同步检查 | 已实现 | 防止入口漂移 |
| 源码文件超过 1000 行硬限制检查 | 已实现 | 防止超大文件无登记回归 |
| PR 描述必须包含 Summary / Scope / Validation / Risks / Docs | 候选 | 让 PR 成为交付事实源 |
| 声明“零业务逻辑变更”时检查行为变化信号 | 候选 | 防止重构 / lint PR 隐含行为变化 |
| 非门禁治理任务修改门禁脚本或 `KNOWN_ISSUES` | 已实现 / [DOC-073](../../01-product-planning/04-backlog.md) | 防止“改裁判”绕过当前失败 |
| AI / RAG 效果型任务完成态分层声明 | 候选 / [DOC-074](../../01-product-planning/04-backlog.md) | 防止代码接入被误写成真实效果验收 |

## 验证矩阵

| 改动范围 | 必跑验证 | 视情况追加 |
|----------|----------|------------|
| 后端 Python | 相关 pytest；涉及 lint 风险时 ruff / make lint | 数据库迁移、手动 API |
| 前端 Vue/TS | `pnpm --filter @metaedu/web lint` + `typecheck` | build、浏览器验收 |
| API / DTO / Schema | 后端相关测试 + 前端 typecheck | shared typecheck、契约测试 |
| 数据库迁移 | Alembic upgrade + 相关 repository/API 测试 | downgrade / 回滚 |
| 文档-only | `scripts/check-engineering-docs` + `git diff --check` | 人工读关键段 |
| AI 协作规则 | `scripts/check-engineering-docs` + 入口同步检查 | 跨工具 dry run |

## 专项检查

- 行为变化声明：出现“零业务逻辑变更”“仅 lint”“无行为变化”时，检查函数签名、默认值、条件、异常、SQL、prompt、路由注册、配置和用户文案；有信号就改写为风险声明并补验证。
- 覆盖矩阵：影响多个等价入口、对象类型、状态流或端点时，用最小矩阵锁定覆盖；回归测试要覆盖正确行为，不只覆盖暴露 bug 的路径。
- 前端请求生命周期：涉及 composable、Vue Query、轮询、loading/error、mutation 刷新时，检查请求参数、enabled/lazy-load、轮询、刷新、UI 状态、DTO adapter。
- AI / RAG 效果型验收：区分代码接入、mock / fixture、dry-run / 真实 PG、真实 LLM / 用户验收；只允许按已跑到的最高层级翻状态。
- 复核发现入账：当前任务内能修则修；不阻塞但有证据则入 `REQ` / `BUG` / `TD` / `DOC`；近期接力才加入候选区。

## 验证表述规范

- `通过`：命令退出码 0，或手动验收全部满足。
- `未通过`：命令退出码非 0，或验收失败。
- `未运行`：没有执行，并写清原因。
- `历史失败`：命令未通过，但失败项不是本任务引入，并绑定任务编号。

收尾记录模板：`已运行：命令 + 结果`；`未运行：原因`；`当前失败：摘要 / 阻塞条件`。

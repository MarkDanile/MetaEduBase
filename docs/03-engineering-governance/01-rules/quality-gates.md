# Quality Gates — 质量门禁规范

质量门禁按改动范围选择。目标是让每次 AI 或人工开发结束时，都能留下可复现的验证结果。

## 基本原则

- 优先运行与改动范围最相关的最小验证，再按风险扩展。
- 如果验证无法运行，记录具体原因，不要只写“未测试”。
- 文档-only 改动也需要检查链接、编号、状态和引用路径。
- 当前工作状态必须同步到 `docs/03-engineering-governance/current-work.md`。
- 验证结论必须以真实命令输出或明确验收场景为依据。退出码为 0 才能写“通过”。
- 如果命令退出码非 0，但失败项属于历史问题，必须写成“命令未通过；失败项属于 TD-xxx；本任务未新增”，不得写成“通过”。
- 复核、测试失败或验证矩阵发现的未解决问题，必须绑定到已有任务或新增任务；不能只写“后续处理”。

## 完成门禁

本节是提交、PR、合并前或声明任务完成前的唯一通用收尾检查。其他流程文档只引用本节，不重复展开长清单。

1. 范围：`git diff --name-status` 或 PR Scope 只包含本任务；无关资产、生成物、缓存或人工清理不得混入。
2. 验证：验证结论来自真实命令输出或明确验收场景；退出码非 0 不得写“通过”。
3. 状态：`current-work.md`、对应总账、Backlog、Requirement、Iteration、Milestone、plan/spec 的状态、验证结果和未完成项不互相矛盾；关闭 `REQ-xxx` 时必须把产品规划层和工程工作台作为同一组事实源回查。
4. 计数：摘要中写“全部收口”“N 个 AC / 用例 / 文件 / 任务”时，必须回到 Requirement、Plan 或测试输出逐条核对；不得凭记忆或二手摘要填写。
5. 文档：已完成任务不得残留活动式 `- [ ]`、`未运行`、`待提交`、`以最终回复为准` 等过期占位；保留未完成项时必须绑定后续任务编号或标明 out of scope。
6. 工作台：`当前进行中` 只保留活跃任务；`下一批候选任务` 只保留 1 到 3 个未完成候选；`最近完成` 最多 5 行。
7. 入账：复核、测试或验收发现但未修复的问题，必须进入对应事实源；需要近期接力时再加入“下一批候选任务”。
8. 插件输出：如使用 superpower、compound-engineering-plugin 或其他插件，任务卡片的 `Spec` / `Plan` 必须指向 `docs/02-delivery-plans/01-specs/*` / `docs/02-delivery-plans/02-plans/*`；原始插件路径只能写入 `插件输出`。

文档、规则、spec、plan、任务状态或交接信息发生变化时，额外运行：

```bash
scripts/check-engineering-docs
```

该命令是稳定兼容入口；主实现位于 `scripts/engineering/check_engineering_docs.py`，工程文档门禁逻辑优先收敛到该目录。

## 脚本门禁候选清单

本节只记录可脚本化方向，不代表全部都已实现。新增脚本前先评估误伤率、维护成本和是否能用稳定文本模式判断；无法稳定判断的项保留为人工完成门禁。

| 候选门禁 | 当前状态 | 触发价值 |
|----------|----------|----------|
| `current-work.md` 最近完成最多 5 行 | 已实现 | 防止工作台无限扩张 |
| `current-work.md` 下一批候选最多 3 行，且不允许 `🟢 完成` | 已实现 | 防止候选区变成历史索引 |
| 已完成任务不得残留 `未运行`、`待提交`、`以最终回复为准` 等占位 | 已实现 / 持续补强 | 防止状态声明与实际交付不一致 |
| Backlog、current-work、work-log、technical-debt 中任务 ID 唯一且状态不冲突 | 候选 / 部分实现 | 降低跨事实源状态漂移 |
| 禁止把 `REQ-xxx-FOLLOWUP` / `TD-xxx-FOLLOWUP` 作为长期任务编号 | 已实现 | 保持稳定编号和可检索历史 |
| `Done` 任务在 Backlog / current-work / work-log 之间有最小索引闭环 | 已实现 | 防止任务关闭后事实源缺失 |
| 旧 docs 路径残留检查 | 已实现 | 防止目录迁移后链接回退 |
| Markdown 相对链接存在性检查 | 已实现 | 防止文档迁移或重命名后断链 |
| AGENTS.md / CLAUDE.md 与 IDE 兼容入口同步检查 | 已实现 | 防止入口规则漂移或 IDE 私有规则复制正文 |
| PR 描述必须包含 Summary / Scope / Validation / Risks / Docs | 候选 / 可放 CI | 让 PR 成为默认交付事实源 |
| spec / requirement 中编号、AC 数量、摘要计数一致 | 候选 | 防止“全部收口”“N 个 AC”与源文件不一致 |
| 声明“零业务逻辑变更”时检查行为变化关键词和 diff 信号 | 候选 | 防止重构或 lint PR 隐含行为变化 |

专项门禁按任务触发：行为变化声明、覆盖矩阵、前端请求生命周期等价矩阵、API / DTO 契约、数据完整性和 Git 合并流程仍以本文件和对应专项规则为准。

## 行为变化声明检查

当计划、PR 描述、任务卡片或最终回复中出现“零业务逻辑变更”“仅格式化”“仅 lint 修复”“无行为变化”等声明时，提交前必须额外检查行为变化信号。

至少检查以下类别：

- 函数签名、API 参数、默认值、配置项、环境变量、Schema 或 DTO 是否变化。
- 条件判断、循环边界、排序、过滤、分页、去重、事务边界或异步任务调度是否变化。
- 异常处理是否变化，包括扩大或缩小捕获范围、使用 `suppress`、改变错误返回、改变 retry 或 fallback。
- 校验规则是否变化，例如新增 `strict=True`、assertion、类型收窄、空值处理或长度限制。
- SQL / ORM 查询、级联删除、join 条件、flush / commit 时机是否变化。
- 字符串内容是否变化，尤其是 prompt、错误消息、用户可见文案、解析模板或正则表达式。
- import 副作用、注册表、Celery task 注册、路由注册或模块加载顺序是否变化。

如果出现任何信号，不得笼统声明“零业务逻辑变更”。应改写为“以 lint/重构为主，但包含以下可观察行为风险”，并补充对应验证；如果判断没有外部可观察变化，也必须说明判断依据。

## 验证矩阵

| 改动范围 | 必跑验证 | 视情况追加 |
|----------|----------|------------|
| 后端 Python | 相关 pytest 或 `make test`；涉及 lint 风险时运行 `make lint` | 数据库迁移、手动 API 验证 |
| 前端 Vue/TS | `pnpm --filter @metaedu/web lint` + `pnpm --filter @metaedu/web typecheck` | `pnpm --filter @metaedu/web build`、浏览器手动验证 |
| API / DTO / Schema | 后端相关测试 + 前端 typecheck；涉及 shared 时运行 `pnpm --filter @metaedu/shared typecheck` | 契约测试或手动接口验证；契约规则见 `docs/03-engineering-governance/01-rules/contracts.md` |
| 数据库迁移 | Alembic upgrade 路径 + 相关 repository/API 测试 | downgrade 路径 |
| 文档-only | `scripts/check-engineering-docs` + `git diff --check` | 人工阅读关键段落 |
| AI 协作规则 | `scripts/check-engineering-docs`；检查 AGENTS.md、CLAUDE.md、current-work/workflow 索引一致 | 跨工具入口 dry run |

## 覆盖矩阵

当一次改动影响多个等价入口、对象类型、状态流或 API 端点时，提交前必须用最小矩阵检查测试覆盖。矩阵可以写在任务卡片、plan、PR 描述或最终回复中。

示例：

```md
| 对象 | Delete | Reinitialize |
|------|--------|--------------|
| File | 已覆盖 | 已覆盖 |
| Dataset | 已覆盖 | 已覆盖 |
```

如果矩阵中某格不适合自动化测试，必须记录手动验收方式或明确原因。回归测试的目标是锁定正确行为，不只验证本次暴露 bug 的路径。

### 前端请求生命周期等价矩阵

前端重构如果涉及 composable、Vue Query、请求 service、轮询、loading / error 状态或 mutation 后刷新，提交前必须额外检查行为等价矩阵。矩阵至少包含以下行：

| 检查项 | 旧行为 | 新行为 | 验证 |
|--------|--------|--------|------|
| 请求参数 | query/body/formData 字段、默认值 | 是否完全一致 | mock、DevTools 或测试 |
| lazy-load / enabled | 页面进入、tab 展开、选中项变化时何时请求 | 是否完全一致 | mock、DevTools 或测试 |
| 轮询条件 | start、pause、stop、unmount 清理 | 是否完全一致 | fake timer、mock 或手动验收 |
| mutation 刷新 | invalidation、refetch、选中项更新 | 是否完全一致 | mock、DevTools 或测试 |
| UI 状态 | loading、disabled、toast、错误文案、重试入口 | 是否完全一致 | 组件测试或手动验收 |
| DTO / adapter | 后端真实响应形态和页面展示类型 | 是否显式转换 | typecheck + 代码检查 |

lint、typecheck 和 build 只证明基础静态质量，不证明上述行为等价。若存在已知缺口，必须绑定到任务编号；不得在 PR 或任务卡片中写“行为不变”。

## 复核发现入账

当 code review、PR review、Codex / Claude Code 交叉复核、测试失败分析或人工验收发现问题时，按以下顺序处理：

1. 如果问题属于当前任务完成标准，优先在当前任务内修复并补充验证。
2. 如果问题不阻塞当前交付，但存在明确证据，新增或更新对应事实源任务，例如 `TD-xxx`、bug 任务或后续 plan。
3. 如果问题需要近期接力，加入 `docs/03-engineering-governance/current-work.md` 的“下一批候选任务”；否则只保留在对应总账。
4. 最终回复中提到的未解决问题，必须能在仓库事实源中找到对应编号或记录。

新增任务必须包含证据、完成标准和验证方式；缺少任一项时，只能记录为待澄清，不得标记为 `🔵 就绪`。

加入“下一批候选任务”前必须检查该区域仍然只是近期接力池：只允许 1 到 3 个未完成候选，不允许 `🟢 完成` 行。已完成任务应进入“最近完成”或归档到对应事实源；“最近完成”超过 5 行时，最旧条目必须移入 `docs/03-engineering-governance/work-log.md` 或对应总账。

## 验证表述规范

- `通过`：只能用于命令退出码为 0，或手动验收全部满足。
- `未通过`：命令退出码非 0，或验收场景失败。
- `未运行`：没有执行该验证，并写清原因。
- `历史失败`：命令未通过，但失败项已确认不是本任务引入，并绑定到已有或新增 `TD-xxx`。
- `本任务未新增问题`：只能作为补充说明，不能替代命令是否通过的客观结果。

记录验证结果时，优先写“命令 + 退出结果 + 失败摘要”。测试类验证还必须写清文件 / 用例范围、是否依赖数据库或外部服务、执行环境标识（本地、CI、特定 AI IDE 沙箱等）。不要把“我改的代码干净”写成“整个命令通过”。

## 已知门禁状态

- `pnpm --filter @metaedu/web typecheck` 当前可作为前端基础门禁。
- `pnpm --filter @metaedu/web lint` 当前可运行，且当前无已知 warning。后续新增 warning 应在当前任务内修复，或登记为新的技术债并说明原因。
- 后端完整 pytest 依赖 `metaedu_test` 测试库；新环境运行 `./dev.sh init-test-db` 或 `cd packages/server-python && make init-test-db` 显式初始化，可通过 `TEST_DATABASE_URL` 覆盖默认连接串。

## 收尾记录模板

```md
验证状态：
- 已运行：命令 + 结果
- 未运行：原因
- 当前失败：失败摘要 / 阻塞条件
```

收尾记录完成后，执行本文件的“完成门禁”。

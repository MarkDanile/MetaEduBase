# Quality Gates — 质量门禁规范

质量门禁按改动范围选择。目标是让每次 AI 或人工开发结束时，都能留下可复现的验证结果。

## 基本原则

- 优先运行与改动范围最相关的最小验证，再按风险扩展。
- 如果验证无法运行，记录具体原因，不要只写“未测试”。
- 文档-only 改动也需要检查链接、编号、状态和引用路径。
- 当前工作状态必须同步到 `docs/engineering/current-work.md`。
- 验证结论必须以真实命令输出或明确验收场景为依据。退出码为 0 才能写“通过”。
- 如果命令退出码非 0，但失败项属于历史问题，必须写成“命令未通过；失败项属于 TD-xxx；本任务未新增”，不得写成“通过”。

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
| API / DTO / Schema | 后端相关测试 + 前端 typecheck；涉及 shared 时运行 `pnpm --filter @metaedu/shared typecheck` | 契约测试或手动接口验证；契约规则见 `docs/engineering/rules/contracts.md` |
| 数据库迁移 | Alembic upgrade 路径 + 相关 repository/API 测试 | downgrade 路径 |
| 文档-only | `rg` 检查路径/编号/旧引用，人工阅读关键段落 | 无 |
| AI 协作规则 | 检查 AGENTS.md、CLAUDE.md、current-work/workflow 索引一致 | 跨工具入口 dry run |

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

## 验证表述规范

- `通过`：只能用于命令退出码为 0，或手动验收全部满足。
- `未通过`：命令退出码非 0，或验收场景失败。
- `未运行`：没有执行该验证，并写清原因。
- `历史失败`：命令未通过，但失败项已确认不是本任务引入，并绑定到已有或新增 `TD-xxx`。
- `本任务未新增问题`：只能作为补充说明，不能替代命令是否通过的客观结果。

记录验证结果时，优先写“命令 + 退出结果 + 失败摘要”。不要把“我改的代码干净”写成“整个命令通过”。

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

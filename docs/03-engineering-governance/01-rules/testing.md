# Testing — 测试策略

本文件记录长期测试策略。具体门禁命令见 `quality-gates.md`；本地初始化见 `local-development.md`。

## 测试目标

- 锁定核心业务行为，避免回归。
- 保护多租户、异步任务、数据清理、契约变更等高风险边界。
- 让 AI 或人工接手时能快速验证改动没有明显破坏已有行为。

不维护固定测试数量；数量以实际命令输出为准。

## 测试分层

| 层级 | 位置 | 重点 |
|------|------|------|
| 共享逻辑 | `packages/server-python/tests/shared` | provider fallback、测试库初始化、seed 安全、任务生命周期 helper |
| 上下文测试 | `packages/server-python/tests/contexts/*` | API 成功 / 失败、权限、删除、重试、重新初始化 |
| 契约与回归 | 相关 context 或 shared | API / DTO / schema、多入口状态流、清理和重建 |
| 前端测试 | `packages/web/src/**/__tests__` | 关键交互、组件契约、可回归 UI 行为 |

## 环境原则

- 后端集成测试使用独立测试库，不复用开发库。
- 测试库 schema 由稳定初始化入口准备。
- 测试 seed 只服务测试环境。
- 连接隔离优先，避免连接池或事件循环污染隐藏问题。

## 稳定入口

```bash
cd packages/server-python && make test
cd packages/server-python && make lint
cd packages/server-python && .venv/bin/pytest path/to/test_file.py -v
pnpm --filter @metaedu/web lint
pnpm --filter @metaedu/web typecheck
pnpm --filter @metaedu/web build
```

PR 后端当前默认运行 `pytest -m "not slow"`；`slow` 用例仍由每日定时或手动 CI 全量执行。后续按 TD-083 建立稳定的上下文级影响分析后，叶子上下文改动可运行相关测试与全局 smoke，高风险共享改动仍运行完整回归。slow 失败必须修复或入账，不得因其不阻塞普通 PR 而长期忽略。

## Mock 边界

普通自动化测试默认禁止访问外部网络，只放行 `TEST_DATABASE_URL` 指向的测试
PostgreSQL。遗漏 mock 时必须立即失败并指出连接目标，不得依赖连接失败、重试或
timeout 结束测试。

必须 mock：

- 外部 LLM / embedding 服务。
- Celery broker 投递。
- Redis、第三方 HTTP / MCP 和其他网络依赖。

使用 `AsyncMock`、`httpx.MockTransport` 或在生产代码实际查找符号处 patch。
重试、连接失败和 timeout 分支必须 mock 对应异常或时间源，不得用真实网络失败、
长时间 `sleep` 或完整 timeout 倒计时来驱动断言。
真实外部调用只允许出现在手工 opt-in 验收中，并显式标记
`external_network`；该 marker 不是普通单元/集成测试的绕过入口。

尽量真实集成：

- 数据库读写。
- Repository / ORM 查询。
- 多租户上下文传播。
- 删除、重试、重新初始化等生命周期逻辑。

## 覆盖重点

优先补测试或覆盖矩阵：

- 多租户隔离。
- 数据完整性 / 级联清理。
- 异步任务状态流。
- API / DTO / shared schema。
- LLM provider / fallback。
- 删除、重试、重新初始化。
- 复杂前端交互和请求生命周期。

## 常见断言约束

- 唯一字段避免跨测试冲突。
- 未认证断言可兼容实际 `401/403`，但权限语义要清楚。
- 搜索断言优先验证结果集合和行为，不依赖偶然排序。
- 状态流断言优先看状态迁移、派生数据和副作用，不只看 HTTP 200。
- 回归测试锁定正确行为，不只覆盖暴露 bug 的那条路径。

## 环境阻塞

测试因数据库、依赖或环境不可运行时：

1. 先跑最相关的最小验证。
2. 在 `current-work.md` 记录命令、失败摘要、影响范围。
3. 不能写“通过”。
4. 影响交付判断时，登记技术债或 follow-up。

## 何时更新本文件

新增或切换测试框架、测试分层、测试数据库策略、mock 边界或正式门禁时更新。新增若干用例或测试数量变化通常不更新。

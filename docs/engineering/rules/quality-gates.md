# Quality Gates — 质量门禁规范

质量门禁按改动范围选择。目标是让每次 AI 或人工开发结束时，都能留下可复现的验证结果。

## 基本原则

- 优先运行与改动范围最相关的最小验证，再按风险扩展。
- 如果验证无法运行，记录具体原因，不要只写“未测试”。
- 文档-only 改动也需要检查链接、编号、状态和引用路径。
- 当前工作状态必须同步到 `docs/engineering/current-work.md`。

## 验证矩阵

| 改动范围 | 必跑验证 | 视情况追加 |
|----------|----------|------------|
| 后端 Python | 相关 pytest 或 `make test`；涉及 lint 风险时运行 `make lint` | 数据库迁移、手动 API 验证 |
| 前端 Vue/TS | `pnpm --filter @metaedu/web lint` + `pnpm --filter @metaedu/web typecheck` | `pnpm --filter @metaedu/web build`、浏览器手动验证 |
| API / DTO / Schema | 后端相关测试 + 前端 typecheck；涉及 shared 时运行 `pnpm --filter @metaedu/shared typecheck` | 契约测试或手动接口验证；契约规则见 `docs/engineering/rules/contracts.md` |
| 数据库迁移 | Alembic upgrade 路径 + 相关 repository/API 测试 | downgrade 路径 |
| 文档-only | `rg` 检查路径/编号/旧引用，人工阅读关键段落 | 无 |
| AI 协作规则 | 检查 AGENTS.md、CLAUDE.md、current-work/workflow 索引一致 | 跨工具入口 dry run |

## 已知门禁状态

- `pnpm --filter @metaedu/web typecheck` 当前可作为前端基础门禁。
- `pnpm --filter @metaedu/web lint` 当前可运行，且当前无已知 warning。后续新增 warning 应在当前任务内修复，或登记为新的技术债并说明原因。
- 后端完整 pytest 依赖 `localhost:5432/metaedu_test`；测试环境可复现问题见 `TD-004`。

## 收尾记录模板

```md
验证状态：
- 已运行：命令 + 结果
- 未运行：原因
- 当前失败：失败摘要 / 阻塞条件
```

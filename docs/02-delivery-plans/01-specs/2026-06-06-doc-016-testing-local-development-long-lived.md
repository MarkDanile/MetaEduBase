# DOC-016 Testing / Local Development 长期化重构 — Spec

## 背景

在完成 `README.md` 和 `ARCHITECTURE.md` 的长期化整理后，测试规范与本地开发文档仍然保留了不少短期事实：

1. `testing.md` 混合了测试策略、当前测试数量和部分实现细节。
2. `local-development.md` 以命令堆栈为主，但缺少“主入口 / 场景 / 恢复方式”的清晰结构。
3. AI 或新同事虽然能找到文档，但不够容易快速判断“应该从哪个稳定入口开始”。

本次整理目标是让这两份规则文档也遵循长期性原则：保留稳定入口和策略，减少短期事实堆积。

## 目标

1. `docs/03-engineering-governance/01-rules/testing.md` 成为长期稳定的测试策略文档。
2. `docs/03-engineering-governance/01-rules/local-development.md` 成为长期稳定的本地开发入口文档。
3. 强化“稳定命令入口”与“场景化使用”的表达，而不是简单罗列命令。
4. 同步更新必要的索引描述，保持 AI 渐进式披露一致。

## 非目标

1. 不修改 `dev.sh`、`Makefile`、pytest fixture 或测试脚本行为。
2. 不引入新的测试框架、前端测试基建或本地环境工具。
3. 不扩写为完整运维手册或排障百科。

## 长期性原则

### testing.md 应保留的内容

- 测试分层与验证策略
- 测试环境与隔离原则
- mock 边界与真实依赖边界
- 测试组织方式与常见断言约定
- 稳定的测试入口命令

### testing.md 不应承载的内容

- 固定测试数量
- 偶发性的覆盖率数字或一次性统计
- 过度贴近某个 fixture 内部实现的长段细节

### local-development.md 应保留的内容

- 本地开发主入口
- 常见开发场景和对应稳定命令
- 开发库 / 测试库初始化边界
- 环境阻塞时的记录方式

### local-development.md 不应承载的内容

- 过度展开的内部脚本实现说明
- 与当前命令无关的一次性排障细节
- 与 Git、质量门禁、架构边界重复的内容

## 完成标准

1. `testing.md` 改为长期稳定的测试策略文档。
2. `local-development.md` 改为长期稳定的本地开发入口文档。
3. 移除 `testing.md` 中固定测试数量等短期事实。
4. 必要索引描述同步更新，如 `AGENTS.md` / `CLAUDE.md` / `docs.md`。
5. `scripts/check-engineering-docs` 通过。
6. `git diff --check` 通过。

## 验证

- 人工阅读：确认两份文档都以“策略 / 入口 / 稳定命令”为主，而不是短期事实堆栈。
- `scripts/check-engineering-docs`
- `git diff --check`

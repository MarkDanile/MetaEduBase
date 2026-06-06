# DOC-017 Contracts / Task Modes 长期化重构 — Spec

## 背景

在完成顶层入口文档、测试策略和本地开发入口的长期化整理后，`contracts.md` 与 `task-modes.md` 仍存在两个问题：

1. `contracts.md` 同时承载现状描述、实现路径和流程规则，结构还可以更稳定。
2. `task-modes.md` 已经形成完整流程，但内容偏长、重复较多，不够利于 AI 和人工快速扫描。

本次整理目标不是削弱约束，而是把两份规则压到“更稳定、更易扫、更适合跨 IDE 接手”的形态。

## 目标

1. `docs/engineering/rules/contracts.md` 成为长期稳定的契约治理文档。
2. `docs/engineering/task-modes.md` 成为长期稳定的任务模式入口文档。
3. 保留已有稳定锚点和常用章节，避免打断现有引用。
4. 同步更新必要索引描述，保持渐进式披露一致。

## 非目标

1. 不修改契约实现代码、shared schema 或 DTO 本身。
2. 不改变当前任务流程的核心约束，只做结构收敛和重复压缩。
3. 不重写 `workflow.md` 或 `quality-gates.md` 的主流程。

## 长期性原则

### contracts.md 应保留的内容

- 契约所有权
- 何时提升到 shared
- 兼容 / 破坏性变更边界
- 前后端各自的约束
- 契约变更的最小同步与验证步骤

### contracts.md 不应承载的内容

- 一次性现状盘点
- 某个具体任务的临时治理细节
- 高度依赖当前文件布局的冗长叙述

### task-modes.md 应保留的内容

- 任务分类模型
- 通用开工与收尾检查
- 默认模式路由
- 各任务模式的必读、执行原则和完成标准

### task-modes.md 不应承载的内容

- 与 `workflow.md`、`quality-gates.md` 大段重复的流程描述
- 每个模式都重复写一遍同样的入口规则
- 过多解释性文字，导致扫描成本过高

## 完成标准

1. `contracts.md` 被重构为长期稳定的契约治理文档。
2. `task-modes.md` 被重构为更短、更稳的任务模式入口文档。
3. 现有被引用的稳定章节名保留，至少包括：
   - `默认模式路由`
   - `通用收尾回查`
   - `技术债修复`
   - `Bug 修复`
   - `新需求开发`
   - `重构`
   - `Spike / 调研`
   - `基础设施 / 依赖 / 工具链`
   - `数据迁移 / 发布`
4. 必要索引描述同步更新，如 `AGENTS.md`、`CLAUDE.md`、`docs.md`。
5. `scripts/check-engineering-docs` 通过。
6. `git diff --check` 通过。

## 验证

- 人工阅读：确认两份文档都比原来更利于快速扫描，且未丢失关键约束。
- `scripts/check-engineering-docs`
- `git diff --check`

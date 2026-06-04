# Docs — 文档规范

## 文档结构

| 文档 | 位置 | 说明 |
|------|------|------|
| AGENTS.md / CLAUDE.md | 根目录 | AI IDE 入口与渐进式披露索引 |
| current-work.md | docs/engineering/current-work.md | 当前开发任务入口与交接状态 |
| work-log.md | docs/engineering/work-log.md | 已完成任务的一行式历史索引 |
| workflow.md | docs/engineering/workflow.md | 跨 AI IDE / 插件开发流程 |
| task-modes.md | docs/engineering/task-modes.md | 常见任务模式、类型与领域检查表 |
| ARCHITECTURE.md | 根目录 | 系统架构详述（API/Schema/流程） |
| README.md | 根目录 | 快速开始、环境要求、部署总览 |
| docs/specs/* | 目录 | 插件无关的功能需求、产品设计、验收标准 |
| docs/plans/* | 目录 | 插件无关的实施计划、任务拆分、验收步骤 |
| docs/superpowers/* | 目录 | 历史 superpower 文档或兼容输出，不作为新任务默认目录 |
| docs/engineering/rules/* | 目录 | 跨 AI IDE / 插件共享的专项规范事实源 |

## 代码注释规范

### Python
```python
# 模块级说明
"""Knowledge node domain entity and related value objects."""

# 类/函数说明（仅当 WHY 非显而易见时添加）
class KnowledgeNode(AggregateRoot):
    """Knowledge node aggregate root.

    WHY: 需要物化路径支持层级查询，path 字段由 service 层计算写入。
    """
```

**原则**：
- 只写 **WHY**，不写 **WHAT**（好命名已说明）
- 不添加无意义的 docstring
- 复杂业务逻辑用代码内注释说明决策

### TypeScript / Vue
```typescript
// 仅在非显而易见时添加注释
// WHY: 租户上下文需要异步传递，无法通过 props 直接传递
```

## 文档更新规则

| 文件变更 | 必须同步更新 |
|----------|--------------|
| `router.py` | ARCHITECTURE.md API 端点表 |
| `models.py` | ARCHITECTURE.md 数据库 Schema |
| `config.py` / `.env` | ARCHITECTURE.md 配置项速查 + README.md 环境变量 |
| `main.css` | `docs/engineering/rules/coding-style.md` 设计 Token |
| API 请求/响应 DTO、前端 service 类型、shared schema | `docs/engineering/rules/contracts.md`，必要时更新 ARCHITECTURE.md API 端点表 |
| 新增页面 | ARCHITECTURE.md 页面清单 |
| 新增业务上下文 | ARCHITECTURE.md + README.md 项目结构 |
| 删除逻辑变更 | `docs/engineering/rules/data-integrity.md` 级联删除要求 |
| 质量门禁或验证策略变更 | `docs/engineering/rules/quality-gates.md`，必要时同步 README.md 验证说明 |
| 本地启动、依赖安装或运行命令变更 | `docs/engineering/rules/local-development.md` + README.md 快速开始 |
| AI 协作流程变更 | `docs/engineering/workflow.md` + AGENTS.md + CLAUDE.md |
| 任务模式、开工条件或验收流程变更 | `docs/engineering/task-modes.md` + `docs/engineering/workflow.md` |
| Spec / Plan 目录约定变更 | `docs/engineering/workflow.md` + `docs/specs/README.md` + `docs/plans/README.md` |
| 行为变化声明或验证表述规则变更 | `docs/engineering/rules/quality-gates.md` + `docs/engineering/task-modes.md` |
| Git 提交、PR 范围或合并流程变更 | `docs/engineering/rules/git-workflow.md` + `docs/engineering/workflow.md` |
| 纯前端 UI 变更（无 API/Schema 影响） | 无需更新 |

## 规则归属

| 内容类型 | 放置位置 |
|----------|----------|
| 当前开发状态、下一步、交接备注 | `docs/engineering/current-work.md` |
| 已完成任务历史索引 | `docs/engineering/work-log.md` |
| 跨 AI IDE / 插件流程 | `docs/engineering/workflow.md` |
| 任务类型、领域、开工条件和验收模式 | `docs/engineering/task-modes.md` |
| 技术债任务与定期复盘 | `docs/engineering/technical-debt.md` |
| 长期架构、阶段路线、系统边界 | `ARCHITECTURE.md` |
| 本地启动、依赖、迁移和常用运行命令 | `docs/engineering/rules/local-development.md` |
| 编码、测试、安全、数据完整性等长期规则 | `docs/engineering/rules/*` |
| API / DTO / shared schema 契约治理 | `docs/engineering/rules/contracts.md` |
| 功能需求、产品设计、验收标准 | `docs/specs/*` |
| 功能实施步骤、任务拆分 | `docs/plans/*` |
| 历史 superpower 文档或兼容输出 | `docs/superpowers/*` |

如果新内容不明显属于某个规则，先放到 `docs/engineering/current-work.md` 的任务卡片备注或新建对应 spec/plan；不要塞进 `ARCHITECTURE.md` 或入口文件。

## README.md 结构

```
# Project Name
> 简短描述

## 快速开始
## 环境要求
## 目录结构
## 部署
```

## 注释禁止项

- ❌ 解释显而易见的代码（`i += 1  # i 加 1`）
- ❌ 解释已有好命名的函数（`# 获取用户  →  函数名已说明`）
- ❌ 留下 TODO 而不描述为什么需要做
- ❌ 使用中文拼音命名

## 工作模式

| 任务类型 | 模式 | 说明 |
|----------|------|------|
| Bug fix, 小功能, UI 调整 | **Plan-Do** | 提出方案 → 确认 → 实施 |
| >3 文件, Schema 变更, 新端点 | **Spec / Plan** | `docs/specs/*` 需求 → `docs/plans/*` 计划 → 实施 |

任何工作模式都必须在 `docs/engineering/current-work.md` 中登记或更新当前状态。

# Docs — 文档规范

## 文档结构

| 文档 | 位置 | 说明 |
|------|------|------|
| AGENTS.md / CLAUDE.md | 根目录 | AI IDE 入口与渐进式披露索引 |
| current-work.md | docs/03-engineering-governance/current-work.md | 当前开发任务入口与交接状态 |
| work-log.md | docs/03-engineering-governance/work-log.md | 已完成任务的一行式历史索引 |
| workflow.md | docs/03-engineering-governance/workflow.md | 跨 AI IDE / 插件开发流程 |
| task-modes.md | docs/03-engineering-governance/task-modes.md | 任务模式入口、默认模式路由与各模式完成标准 |
| workbench.md | docs/03-engineering-governance/01-rules/workbench.md | 当前工作台状态流、保留策略和任务卡片模板 |
| ARCHITECTURE.md | 根目录 | 长期架构地图：系统边界、上下文划分、关键流转、质量属性 |
| README.md | 根目录 | 项目入口：能力概览、仓库导航、最小启动路径 |
| docs/01-product-planning/* | 目录 | 产品规划、路线图、迭代、需求池和可塑形需求 |
| docs/02-delivery-plans/01-specs/* | 目录 | 插件无关的功能需求、产品设计、验收标准 |
| docs/02-delivery-plans/02-plans/* | 目录 | 插件无关的实施计划、任务拆分、验收步骤 |
| docs/03-engineering-governance/03-retrospectives/* | 目录 | 复盘、根因分析和纠正动作索引 |
| docs/90-compat-legacy/superpowers/* | 目录 | 历史 superpower 文档或兼容输出，不作为新任务默认目录 |
| docs/03-engineering-governance/01-rules/* | 目录 | 跨 AI IDE / 插件共享的专项规范事实源 |

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
| `router.py` / API 请求响应语义 | `docs/03-engineering-governance/01-rules/contracts.md`；只有系统边界或关键流程变化时才更新 `ARCHITECTURE.md` |
| `models.py` / migration / 数据所有权 | `docs/03-engineering-governance/01-rules/contracts.md`、`docs/03-engineering-governance/01-rules/data-integrity.md`；只有上下文边界变化时才更新 `ARCHITECTURE.md` |
| `config.py` / `.env` / 运行命令 | `docs/03-engineering-governance/01-rules/local-development.md`；只有最短启动路径变化时才更新 `README.md` |
| `main.css` | `docs/03-engineering-governance/01-rules/coding-style.md` 设计 Token |
| API 请求/响应 DTO、前端 service 类型、shared schema | `docs/03-engineering-governance/01-rules/contracts.md`；只有共享契约策略或系统级流转变化时才更新 `ARCHITECTURE.md` |
| 新增页面 | 通常无需更新顶层文档；只有影响仓库导航或系统结构时才更新 `README.md` / `ARCHITECTURE.md` |
| 新增业务上下文 | ARCHITECTURE.md + README.md 项目结构 |
| 删除逻辑变更 | `docs/03-engineering-governance/01-rules/data-integrity.md` 级联删除要求 |
| 质量门禁或验证策略变更 | `docs/03-engineering-governance/01-rules/quality-gates.md`；通常不更新顶层文档 |
| 工程工具脚本或门禁实现变更 | `scripts/engineering/*` + `docs/03-engineering-governance/01-rules/quality-gates.md`；如需稳定命令入口，可保留根级 `scripts/check-*` wrapper |
| 本地启动、依赖安装或运行命令变更 | `docs/03-engineering-governance/01-rules/local-development.md`；只有最短启动路径变化时再同步 `README.md` |
| AI 协作流程变更 | `docs/03-engineering-governance/workflow.md` + AGENTS.md + CLAUDE.md |
| 任务模式、开工条件或验收流程变更 | `docs/03-engineering-governance/task-modes.md` + `docs/03-engineering-governance/workflow.md` |
| Spec / Plan 目录约定变更 | `docs/03-engineering-governance/workflow.md` + `docs/02-delivery-plans/01-specs/README.md` + `docs/02-delivery-plans/02-plans/README.md` |
| 产品路线图、需求池或迭代规则变更 | `docs/01-product-planning/README.md` + `docs/01-product-planning/01-roadmap.md` 或 `docs/01-product-planning/04-backlog.md`；必要时同步 `docs/03-engineering-governance/workflow.md` |
| 插件输出路径或跨 IDE 交付规则变更 | `docs/03-engineering-governance/workflow.md` + `docs/02-delivery-plans/README.md` + AGENTS.md + CLAUDE.md |
| 复盘、根因分析或纠正动作规则变更 | `docs/03-engineering-governance/03-retrospectives/README.md` + 对应 `REQ` / `BUG` / `TD` / `DOC` / `OPS` 事实源 |
| 行为变化声明或验证表述规则变更 | `docs/03-engineering-governance/01-rules/quality-gates.md` + `docs/03-engineering-governance/task-modes.md` |
| Git 提交、PR 范围或合并流程变更 | `docs/03-engineering-governance/01-rules/git-workflow.md` + `docs/03-engineering-governance/workflow.md` |
| 纯前端 UI 变更（无 API/Schema 影响） | 无需更新 |

## 规则归属

| 内容类型 | 放置位置 |
|----------|----------|
| 当前开发状态、下一步、交接备注 | `docs/03-engineering-governance/current-work.md` |
| 已完成任务历史索引 | `docs/03-engineering-governance/work-log.md` |
| 跨 AI IDE / 插件流程 | `docs/03-engineering-governance/workflow.md` |
| 任务类型、领域、开工条件和验收模式 | `docs/03-engineering-governance/task-modes.md` |
| 当前工作台状态流、保留策略和任务卡片模板 | `docs/03-engineering-governance/01-rules/workbench.md` |
| 技术债任务与定期复盘 | `docs/03-engineering-governance/technical-debt.md` |
| 产品路线图、里程碑、迭代和需求池 | `docs/01-product-planning/*` |
| 复盘、根因分析和纠正动作追踪 | `docs/03-engineering-governance/03-retrospectives/*` |
| 长期架构、系统边界、关键流转、质量属性、演进方向 | `ARCHITECTURE.md` |
| 项目入口、能力概览、仓库导航、最小启动路径 | `README.md` |
| 本地开发入口、数据库初始化与常见开发命令 | `docs/03-engineering-governance/01-rules/local-development.md` |
| 编码、测试、安全、数据完整性等长期规则 | `docs/03-engineering-governance/01-rules/*` |
| 工程文档门禁、仓库治理检查等内部工具实现 | `scripts/engineering/*`；根级 `scripts/check-*` 只保留稳定兼容命令入口 |
| API / DTO / shared schema 契约治理 | `docs/03-engineering-governance/01-rules/contracts.md` |
| 已进入交付的功能需求、产品设计、验收标准 | `docs/02-delivery-plans/01-specs/*` |
| 功能实施步骤、任务拆分 | `docs/02-delivery-plans/02-plans/*` |
| 历史 superpower 文档或兼容输出 | `docs/90-compat-legacy/superpowers/*` |

如果新内容不明显属于某个规则，先判断它处于哪一层：产品规划进入 `docs/01-product-planning/*`，交付需求进入 `docs/02-delivery-plans/01-specs/*`，实施步骤进入 `docs/02-delivery-plans/02-plans/*`，当前状态进入 `docs/03-engineering-governance/current-work.md`。不要塞进 `ARCHITECTURE.md` 或入口文件。

## 顶层文档原则

- 顶层文档优先记录稳定内容，不追逐高频变化事实。
- API 清单、数据库字段、固定测试数量、一次性迁移命令不要堆进 `README.md` 或 `ARCHITECTURE.md`。
- 如果某段内容更新频率高于“系统边界变化”，它大概率不属于 `ARCHITECTURE.md`。
- 如果某段内容只是帮助启动或找入口，而不是解释系统边界，它更可能属于 `README.md`。

## README.md 推荐结构

```
# Project Name
> 项目定位

## 核心能力
## 系统快照
## 仓库导航
## 快速开始
## 开发与协作入口
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
| 未塑形的新需求、里程碑拆解 | **Product Planning** | `docs/01-product-planning/04-backlog.md` → `docs/01-product-planning/05-requirements/*` → spec/plan |
| >3 文件, Schema 变更, 新端点 | **Spec / Plan** | `docs/02-delivery-plans/01-specs/*` 需求 → `docs/02-delivery-plans/02-plans/*` 计划 → 实施 |

任何工作模式都必须在 `docs/03-engineering-governance/current-work.md` 中登记或更新当前状态。

插件生成的 spec / plan 只能作为草稿来源。任务卡片的 `Spec` / `Plan` 字段必须指向交付层规范副本，原始插件文件只写入 `插件输出`。

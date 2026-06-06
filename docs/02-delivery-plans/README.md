# Delivery Plans — 交付层入口

本目录承载已经准备交付的需求、设计、验收标准和实施计划。它位于产品规划之后、当前执行工作台之前。

## 目录

| 目录 | 说明 |
|------|------|
| [01-specs](01-specs/README.md) | 交付级需求、产品设计和验收标准 |
| [02-plans](02-plans/README.md) | 实施计划、任务拆分、验证步骤和交付记录 |

## 使用规则

- 只有已明确范围和验收标准的工作才进入本层。
- 本层是高质量交付体系的核心事实源；复杂开发以这里的 spec / plan 作为开发、验收和交接依据。
- 使用 superpower、compound-engineering-plugin 或其他插件生成的 spec / plan，进入开发前必须迁移或镜像到本层。
- 不能假设插件会自动识别本仓库的新目录；生成前应明确指定 `docs/02-delivery-plans/01-specs/*` 和 `docs/02-delivery-plans/02-plans/*`，生成后必须检查规范副本已落在本层。
- 未塑形需求继续留在 [产品规划层](../01-product-planning/README.md)。
- 当前执行状态和任务交接记录进入 [工程治理层](../03-engineering-governance/README.md)。

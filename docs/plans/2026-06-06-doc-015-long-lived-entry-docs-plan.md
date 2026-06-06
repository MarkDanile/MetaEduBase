# DOC-015 README / ARCHITECTURE 长期化重构 — Plan

## 对应 Spec

- `docs/specs/2026-06-06-doc-015-long-lived-entry-docs.md`

## 实施步骤

1. 盘点现有 `README.md`、`ARCHITECTURE.md`、`docs/engineering/rules/docs.md`、`docs/engineering/rules/architecture.md` 的职责混叠点。
2. 重写 `README.md`，只保留项目入口、能力概览、仓库导航、最小快速开始和协作入口。
3. 重写 `ARCHITECTURE.md`，只保留系统边界、子系统、上下文、关键流程、质量属性和事实源导航。
4. 调整 `docs/engineering/rules/docs.md`，把顶层文档定义成稳定入口，去掉“接口表 / Schema 清单必须维护在 ARCHITECTURE.md”的要求。
5. 调整 `docs/engineering/rules/architecture.md`，把它收敛成架构实现约束与定位指南。
6. 运行文档门禁与 diff 检查，回填当前工作台和工作日志。

## 风险与控制

- 风险：删除顶层 inventory 后，后来者短期不适应。
  - 控制：在 `README.md` 和 `ARCHITECTURE.md` 中显式加入“去哪里找细节”的导航。
- 风险：规则文档仍要求把易变实现细节塞回顶层文档。
  - 控制：同步修正规则文档边界。
- 风险：整理过度，导致快速上手信息不足。
  - 控制：README 仍保留最小启动路径与常用入口，不把全部命令挪走。

## 验证计划

1. `scripts/check-engineering-docs`
2. `git diff --check`
3. 人工回查：
   - `README.md` 是否仍像入口文档。
   - `ARCHITECTURE.md` 是否仍像架构地图。
   - 规则是否不再要求维护顶层 API / Schema inventory。

# 工程工作日志索引

本文件记录已完成任务的一行式历史索引，避免 `current-work.md` 无限扩张。详细事实仍以对应技术债总账、spec、plan、PR 或架构文档为准。

## 记录规则

- 每个已完成且需要长期追踪的任务保留一行。
- `current-work.md` 中移出的完成任务，应在这里有索引。
- 本文件只记录检索信息，不承载详细复盘、设计或验证输出。
- 任务详情优先链接到对应事实源：`technical-debt.md`、`docs/specs/*`、`docs/plans/*` 或 PR。
- PR 是默认交付事实源；本表的 PR 和 merge commit 都是可选追踪字段，只有已有历史、审计需要或任务总账明确要求时记录，缺省可留空并通过 GitHub PR 查询。
- `current-work.md` 的“最近完成”只保留短摘要；本文件保留长期检索索引，避免入口文档无限扩张。

## 索引

| 日期 | 任务 | 类型 | PR 可选 | Merge Commit 可选 | 归档位置 |
|------|------|------|----|-------------------|----------|
| 2026-06-05 | TD-021 收口已完成计划文件和候选区状态同步漏洞 | 技术债 / 文档 / 工程流程 |  |  | `docs/engineering/technical-debt.md#td-021-收口已完成计划文件和候选区状态同步漏洞` |
| 2026-06-05 | DOC-009 生成 TD-005/006/007 follow-up 与规则补强 | 文档 / 工程规范 |  |  | `docs/engineering/technical-debt.md#td-015-修复-td-007-databaseview-vue-query-迁移后的行为回归` |
| 2026-06-05 | TD-005 拆分大型后端任务流水线文件（抽任务生命周期 helper） | 技术债 / 重构 | [#34](https://github.com/MarkDanile/MetaEduBase/pull/34) | `e5197a5` | `docs/engineering/technical-debt.md#td-005-拆分大型后端任务流水线文件` |
| 2026-06-05 | TD-006 集中 LLM provider 和模型 fallback 策略 | 技术债 / 重构 | [#35](https://github.com/MarkDanile/MetaEduBase/pull/35) | `042e4a9` | `docs/engineering/technical-debt.md#td-006-集中-llm-provider-和模型-fallback-策略` |
| 2026-06-05 | TD-007 减少前端请求状态处理重复（DatabaseView 迁到 Vue Query） | 技术债 / 重构 | [#36](https://github.com/MarkDanile/MetaEduBase/pull/36) | `350acd2` | `docs/engineering/technical-debt.md#td-007-减少前端请求状态处理重复` |
| 2026-06-05 | TD-015 修复 TD-007 DatabaseView Vue Query 迁移后的行为回归 | 技术债 / 修复 / follow-up | [#38](https://github.com/MarkDanile/MetaEduBase/pull/38) | `f38fbbc` | `docs/engineering/technical-debt.md#td-015-修复-td-007-databaseview-vue-query-迁移后的行为回归` |
| 2026-06-05 | TD-016 收敛 knowledge ai_router 的 LLM provider 选择重复逻辑 | 技术债 / 重构 / follow-up | [#39](https://github.com/MarkDanile/MetaEduBase/pull/39) | `4e6cf42` | `docs/engineering/technical-debt.md#td-016-收敛-knowledge-ai_router-的-llm-provider-选择重复逻辑` |
| 2026-06-05 | TD-017 将 Vue Query 请求生命周期治理推广到 FileDetailView | 技术债 / 重构 / follow-up | [#40](https://github.com/MarkDanile/MetaEduBase/pull/40) | `5af2793` | `docs/engineering/technical-debt.md#td-017-将-vue-query-请求生命周期治理推广到-filedetailview` |
| 2026-06-05 | TD-018 FileDetailView 剩余手写 load 迁到 Vue Query | 技术债 / 重构 / follow-up | [#41](https://github.com/MarkDanile/MetaEduBase/pull/41) | `8ad15e6` | `docs/engineering/technical-debt.md#td-018-filedetailview-剩余手写-load-迁到-vue-query` |
| 2026-06-05 | TD-019 修复 Vue Query 轮询自引用导致的页面初始化运行时错误 | 技术债 / 修复 / follow-up | [#42](https://github.com/MarkDanile/MetaEduBase/pull/42) | `387d8f8` | `docs/engineering/technical-debt.md#td-019-修复-vue-query-轮询自引用导致的页面初始化运行时错误` |
| 2026-06-05 | DOC-008 将合并后 backfill 改为条件触发 | 文档 / 工程规范 |  |  | `docs/engineering/rules/git-workflow.md` |
| 2026-06-05 | DOC-007 压缩 current-work 最近完成区并强化渐进式披露 | 文档 / 工程规范 | [#30](https://github.com/MarkDanile/MetaEduBase/pull/30) | `3b36023` | `docs/engineering/current-work.md` |
| 2026-06-05 | DOC-006 修复 current-work 重复完成区标题 | 文档 / 工程规范 | [#29](https://github.com/MarkDanile/MetaEduBase/pull/29) | `7d0f427` | `docs/engineering/current-work.md` |
| 2026-06-05 | TD-014 加强测试数据库 legacy stamp 的列级形态校验 | 技术债 / follow-up | [#28](https://github.com/MarkDanile/MetaEduBase/pull/28) | `af7d246` | `docs/engineering/technical-debt.md#td-014-加强测试数据库-legacy-stamp-的列级形态校验` |
| 2026-06-05 | TD-013 收口 TD-004 测试数据库初始化安全与文档占位 | 技术债 / follow-up | [#27](https://github.com/MarkDanile/MetaEduBase/pull/27) | `8f25b20` | `docs/engineering/technical-debt.md#td-013-收口-td-004-测试数据库初始化安全与文档占位` |
| 2026-06-04 | DOC-005 补强复核入账与候选任务选择策略 | 文档 / 工程规范 | [#25](https://github.com/MarkDanile/MetaEduBase/pull/25) | `7a4241c` | `docs/engineering/current-work.md` |
| 2026-06-04 | TD-004 让后端测试数据库环境可复现 | 技术债 / 基础设施 | [#23](https://github.com/MarkDanile/MetaEduBase/pull/23) | `b8b34a6` | `docs/engineering/technical-debt.md#td-004-让后端测试数据库环境可复现` |
| 2026-06-04 | DOC-003 补强跨插件计划、行为声明和 PR 范围边界规则 | 文档 / 工程规范 | [#20](https://github.com/MarkDanile/MetaEduBase/pull/20) | `3b883ea` | `docs/engineering/current-work.md` |
| 2026-06-04 | DOC-002 强化跨 AI 提交前回查与验证声明规范 | 文档 / 工程规范 | [#16](https://github.com/MarkDanile/MetaEduBase/pull/16) | `f438307` | `docs/engineering/current-work.md` |
| 2026-06-04 | TD-012 治理后端全量 ruff 质量门禁 | 技术债 | [#17](https://github.com/MarkDanile/MetaEduBase/pull/17) | `a4dcb2a` | `docs/engineering/technical-debt.md#td-012-治理后端全量-ruff-质量门禁` |
| 2026-06-04 | TD-002-FOLLOWUP 收口 TD-002 流程与测试遗留 | 技术债 / 修复 / 文档 | [#13](https://github.com/MarkDanile/MetaEduBase/pull/13) | `ea34271` | `docs/engineering/current-work.md` |
| 2026-06-04 | TD-002 收敛文件清理的级联删除逻辑 | 技术债 | [#12](https://github.com/MarkDanile/MetaEduBase/pull/12) | `2eb59e8` | `docs/engineering/technical-debt.md#td-002-收敛文件清理的级联删除逻辑` |
| 2026-06-04 | TD-001 拆分应用启动时的数据库迁移与默认种子数据 | 技术债 / 基础设施 |  | `291dbbc` | `docs/engineering/technical-debt.md#td-001-拆分应用启动时的数据库迁移与默认种子数据` |
| 2026-06-04 | TD-011 治理前端 lint warning | 技术债 / 基础设施 |  | `090242a` | `docs/engineering/technical-debt.md#td-011-治理前端-lint-warning` |
| 2026-06-04 | TD-003 让前端 lint 质量门禁可运行 | 技术债 / 基础设施 |  | `090242a` | `docs/engineering/technical-debt.md#td-003-让前端-lint-质量门禁可运行` |
| 2026-06-04 | DOC-001 统一并优化跨 AI 工程规则 | 文档 / 工程规范 |  | `c0bac8a` | `docs/engineering/workflow.md` |

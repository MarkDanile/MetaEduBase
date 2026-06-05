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
| 2026-06-06 | TD-029 收口 TD-009 的 shared schema 门禁与 FileDetailView 类型错误 | 技术债 / 修复 / follow-up |  |  | `docs/engineering/technical-debt.md#td-029-收口-td-009-的-shared-schema-门禁与-filedetailview-类型错误` |
| 2026-06-06 | TD-009 减少前后端契约漂移（结构化抽取容器契约） | 技术债 / 重构 |  |  | `docs/engineering/technical-debt.md#td-009-减少前后端契约漂移` |
| 2026-06-05 | TD-027 补 `ui-input` / `ui-btn-*` / `ui-tag-*` / `ui-dialog` 共享类（设计系统扩展） | 技术债 / 设计系统 | [#59](https://github.com/MarkDanile/MetaEduBase/pull/59) |  | `docs/engineering/technical-debt.md#td-027-补-ui-input-ui-btn-ui-tag-ui-dialog-共享类设计系统扩展` |
| 2026-06-05 | TD-026 共享组件 `liquid-card` 残留验证 | 技术债 / 文档 / follow-up | [#58](https://github.com/MarkDanile/MetaEduBase/pull/58) |  | `docs/engineering/technical-debt.md#td-026-共享组件-liquid-card-残留验证` |
| 2026-06-05 | DOC-014 刷新 README / ARCHITECTURE 项目入口文档 | 文档 / 架构 / 交接 |  |  | `README.md` / `ARCHITECTURE.md` |
| 2026-06-05 | DOC-013 工程文档门禁增强与 UI 迁移事实源收口 | 文档 / 工程规范 / 工具链 |  |  | `scripts/engineering/check_engineering_docs.py` |
| 2026-06-05 | TD-023 收口 TD-020 文档一致性、断链与归档索引 | 文档 / 工程流程 / 跨 AI 交接 / follow-up |  |  | `docs/engineering/technical-debt.md#td-023-收口-td-020-文档一致性-断链与归档索引` |
| 2026-06-05 | DOC-012 工程文档自动门禁与工作台瘦身 | 文档 / 工程规范 / 工具链 |  |  | `docs/plans/2026-06-05-doc-012-engineering-doc-gates-and-workbench-slimming-plan.md` |
| 2026-06-05 | TD-020 统一 LLM provider resolver 与 factory 优先级事实源 | 技术债 / 重构 | [#46](https://github.com/MarkDanile/MetaEduBase/pull/46) | `2c15868` | `docs/engineering/technical-debt.md#td-020-统一-llm-provider-resolver-与-factory-优先级事实源` |
| 2026-06-05 | DOC-011 技术债总账结构化展示优化 | 文档 / 工程规范 |  |  | `docs/engineering/technical-debt.md` |
| 2026-06-05 | DOC-010 收敛完成门禁并瘦身重复流程规则 | 文档 / 工程规范 |  |  | `docs/engineering/rules/quality-gates.md#完成门禁` |
| 2026-06-05 | TD-021 收口已完成计划文件和候选区状态同步漏洞 | 技术债 / 文档 / 工程流程 |  |  | `docs/engineering/technical-debt.md#td-021-收口已完成计划文件和候选区状态同步漏洞` |
| 2026-06-05 | TD-022 收口早期已完成计划文件的活动式未勾选项 | 技术债 / 文档 / 工程流程 / follow-up | [#44](https://github.com/MarkDanile/MetaEduBase/pull/44) | `f33c19c` | `docs/engineering/technical-debt.md#td-022-收口早期已完成计划文件的活动式未勾选项` |
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

## 段落归档

当一段工作由多个连续 PR / 任务组成、并构成一个相对独立的工程主题时，在此用一节记录总览，避免单行索引表把段落切碎。详细事实仍以对应 PR、merge commit、`technical-debt.md` 任务卡、`coding-style.md` 迁移说明为准。

### 2026-06-05 设计系统迁移：`liquid-*` → `ui-*`

一段连贯的 5 任务工作，把前端样式体系从「以 `liquid-*` 类为中心」迁移到「`ui-*` 优先 / `liquid-*` 兼容」。完成「calm workspace / token 化 / 不带装饰动效」的统一目标。

**任务链与 PR**：

| # | 任务 | 切片 | PR | Merge Commit | 关键事实 |
|---|------|------|-----|--------------|----------|
| 1 | TD-008 明确从 `liquid-*` 类到语义 UI 层的迁移路径 | 共享骨架 | [#53](https://github.com/MarkDanile/MetaEduBase/pull/53) | `1f32e4a` | 5 个 `ui-*` 容器层共享类（`ui-page-shell` / `ui-page-section` / `ui-panel` / `ui-toolbar` / `ui-interactive-row`）+ 3 个共享骨架组件迁移（`LayoutView` / `PageHeader` / `EmptyState`）；建立迁移规范（`coding-style.md#迁移说明-td-008`） |
| 2 | TD-025 业务页面 `liquid-card` 容器统一迁移到 `ui-panel` | 业务视图（3 切片） | [#54](https://github.com/MarkDanile/MetaEduBase/pull/54) + [#55](https://github.com/MarkDanile/MetaEduBase/pull/55) + [#56](https://github.com/MarkDanile/MetaEduBase/pull/56) | `558884e` + `90763d1` + `26d4654` | 7 业务页面 20 处 `liquid-card` → `ui-panel`；`liquid` 主题下 `ui-panel` 加玻璃感覆盖（`main.css` 行 1154） |
| 3 | TD-026 共享组件 `liquid-card` 残留验证 | 零代码收口 | [#58](https://github.com/MarkDanile/MetaEduBase/pull/58) | `7735046` | 严格 `rg "liquid-card"` 验证 4 个共享组件 0 命中；任务卡残留量 22 处为 TD-008 快照误计 |
| 4 | TD-027 补 `ui-input` / `ui-btn-*` / `ui-tag-*` / `ui-dialog` 共享类 | 设计系统扩展 | [#59](https://github.com/MarkDanile/MetaEduBase/pull/59) | `040f7ad` | 12 个 `ui-*` 原子层共享类（`ui-input` / `ui-btn` 4 类 / `ui-tag` 5 类 / `ui-dialog` 2 类）+ 2 个新 token（`--overlay-bg` / `--btn-ripple`，4 主题分别给值） |
| 5 | TD-028 业务视图与共享组件的 `liquid-*-atomic` 存量替换 | 机械批量替换 | [#61](https://github.com/MarkDanile/MetaEduBase/pull/61) | `349c743` | 12 文件 119 处 `liquid-input` / `liquid-btn*` / `liquid-tag*` / `liquid-dialog*` → `ui-*` + 5 处 `\`liquid-tag-${color}\`` 模板字符串迁移 |

**段落级 PR（状态回填）**：[#57](https://github.com/MarkDanile/MetaEduBase/pull/57) (TD-008/TD-025 状态回填) + [#60](https://github.com/MarkDanile/MetaEduBase/pull/60) (TD-027 状态回填) + [#62](https://github.com/MarkDanile/MetaEduBase/pull/62) (TD-028 状态回填)。

**最终成果**：
- `ui-*` 容器层（5）+ 原子层（12）= **17 个共享类**，全部 token 化复用现有 `--color-*` / `--radius-*` / `--shadow-*` / `--duration-*` / `--ease-*` / `--surface-*` token
- 业务视图与共享组件 100% 切到 `ui-*`（容器 + 原子）
- 4 主题（liquid / ink / navy / notion）视觉不发生可观察退化（除 `liquid-card:hover` 上浮取消、`wet-line` 装饰条移除、`animate-slide-up` 入场动画移除、`liquid-card-scan` 装饰保留等已声明的有意行为变化外）
- `liquid-*` 类全部保留为兼容别名（`main.css` 中），无破坏性删除
- `LoginView` 品牌背景 / `liquid-card` / `liquid-card-scan` 装饰动效按 TD-008 规则保持兼容

**过程中的关键决策**（按"先想后写 + 用户确认"原则）：
- TD-008 范围：ui-panel 玻璃感覆盖在 liquid 主题下加；其他 3 主题维持白底细边框
- TD-025 切片 1：保留 `liquid-card-scan` 装饰动效；保留 `animate-slide-up` + `stagger-N`
- TD-025 切片 3：保留 `HomeView` `liquid-card-scan` 装饰；`coding-style.md` 显式登记 6 类例外（`liquid-btn-primary` / `liquid-btn-ghost` / `liquid-input` / `liquid-tag-*` / `liquid-card-scan` / `stagger-N` & `animate-slide-up`）
- TD-026 路径选择：用户从三选项中选"实测收口"（任务卡残留量与实际不符规律已在 TD-025 切片 2/3 出现 3 次）；设计系统扩展拆为 TD-027（补类）+ TD-028（替换）
- TD-027 自动模式 build 拒批硬编码 rgba → 用户选"确实抽 2 个新 token" → 补 `--overlay-bg` / `--btn-ripple` 4 主题分别给值
- TD-027 用户选择 ui-btn-primary 保留装饰（点按泠漪）+ 动效节奏与 liquid-* 一致 + 5 个 ui-tag 变体
- TD-028 一次完成 119 处（杠杆最大）；LoginView 也迁（仅 input/btn，品牌背景仍例外）；零差异

**复盘 / 经验**：
1. **任务卡残留量与实际不符的规律在 TD-025 切片 2/3 + TD-026 反复出现**（4 次：TemplateModal 8→0、TemplateEditorView 6→0、FieldEditor 12→0、KGDetailPanel 4→0、ConfirmDialog 5→0、KGGraph 1→0）。任务卡编写时把页面里所有 `liquid-*` 类（`liquid-btn-*` / `liquid-input` / `liquid-tag-*` / `liquid-dialog*` / `liquid-card`）都误计入 `liquid-card` 残留。后续技术债应明确"以 `rg` 实测为准，不使用任务卡原残留量"作为新债编写约定。
2. **从长到短的 sed 替换顺序是机械替换的安全保证**（`liquid-btn-primary` → `liquid-btn` 基类 → `liquid-tag-blue/green/amber/purple` → `liquid-tag` 基类 → `liquid-input` → `liquid-dialog-overlay` → `liquid-dialog`），保证子串不被父串吞掉。
3. **token 化与命名一致性是设计系统扩展的前提**。TD-027 在 PR #59 第一次提交时，`ui-dialog-overlay` 与 `ui-btn-primary::after` 仍使用硬编码 `rgba(0, 0, 0, 0.2)` 与 `rgba(255, 255, 255, 0.25)`（从 `liquid-*` 1:1 复制），自动模式 build 分类器拒批后必须补 `--overlay-bg` / `--btn-ripple` 2 个新 token（4 主题分别给值）。事后看，TD-008 应在建 `ui-panel` 玻璃覆盖时同步补 2 个 token，但当时是"`ui-panel` 单独覆盖"未扩到 4 类。**建议把 `--overlay-bg` / `--btn-ripple` 路径在 `coding-style.md` 写明"任何 `ui-*` 新类必须在 main.css 中以 token 形式引用颜色，不允许硬编码 rgba"**——但本工作已通过 TD-027 满足此约束。
4. **状态回填 PR 是 docs-only 的"小 PR"模式**。3 个状态回填 PR（#57、#60、#62）每次 2-3 个文件 + 1 个原子提交，专门把 `current-work.md` 候选区清理 + 最近完成区追加 + `technical-debt.md` 总览表状态修正，保持 `quality-gates.md#完成门禁#3`（状态不自相矛盾）。这种 PR 没有代码变更但对跨 AI 交接极重要。
5. **`liquid-*` 作为兼容别名长期保留是设计系统迁移的正确策略**。5 个任务全部完成，但 `main.css` 中 `liquid-*` 类未删除（也不应该删）；新增 `ui-*` 体系与 `liquid-*` 1:1 镜像，纯属"新约定优先"+"历史兼容保留"的并存模式。后续 AI IDE 接手时只需遵循 `coding-style.md#迁移说明-td-008` 即可。

**未来接力**：
- TD-009 减少前后端契约漂移（P2，API / 类型）：选高价值契约族（模板字段或任务状态），建共享 schema 检查。

**主要文档事实源**：
- 迁移规范：[docs/engineering/rules/coding-style.md#迁移说明-td-008](rules/coding-style.md)
- 任务清单：[docs/engineering/rules/coding-style.md#业务页面迁移清单-td-025](rules/coding-style.md) + [docs/engineering/rules/coding-style.md#共享组件迁移清单-td-026](rules/coding-style.md)
- 任务总账：5 个 TD 任务卡（[TD-008](technical-debt.md) / [TD-025](technical-debt.md) / [TD-026](technical-debt.md) / [TD-027](technical-debt.md) / [TD-028](technical-debt.md)）

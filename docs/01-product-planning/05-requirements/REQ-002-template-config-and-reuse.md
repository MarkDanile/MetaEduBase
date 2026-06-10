# REQ-002: 模板化结构抽取能力的配置与复用体验

Status: 🔵 Ready
Priority: P2
Milestone: P1 / P2
External:
Parent:

## 背景

资源库目前已经具备结构化数据抽取的主链路：上传文档 → 解析 → 模板匹配（REQ-004）→ 结构化抽取（REQ-005）→ 知识图谱抽取 → RAG 问答（REQ-006）。模板作为这条链路的"配置中心"，决定了不同 doc_type 的字段定义与 AI 抽取指令，是整个抽取链路能否被业务复用与扩展的关键。

但模板的"配置与复用体验"仍存在与"功能可用"之间的差距：

- **后台 CRUD 已具备**：领域实体 / 仓储 / 服务 / API 路由 / DTO / ORM 模型都已落地，单元测试覆盖基础路径。
- **前端编辑器已具备**：模板列表页、编辑页、AI 辅助面板、嵌套字段编辑器（FieldEditor + FieldCard + FieldItem）、结构化抽取渲染器（ExtractedDataRenderer + TableRenderer）均已实现，支持 object / table / array 多层嵌套与字段增删。
- **AI 辅助配置已具备**：后端 `init_by_ai` 端点接入 LLM 分析样例文档并返回字段定义；前端 `TemplateAiPanel` 支持文档类型输入 + 样例文档上传 + `ai_context` 补充说明 + 覆盖确认；`ai_context` DTO / entity / repository 字段已就位并随表单保存。
- **模板 doc_type 冲突检查已具备**：`check-doc-type` 端点能在新建/编辑前返回某 doc_type 是否已被现有模板占用，避免多模板争抢同一 doc_type。

REQ-002 不需要再做一轮"模板功能从无到有"，而是要在已有能力上把"配置效率、复用机制、可观测性、可维护性"四件事补齐，让模板真正承担起"业务规则沉淀 + 跨文档复用"的职责。

## 期望用户与场景

| 角色 | 场景 | 期望 |
|------|------|------|
| 课程负责人 / 教学秘书 | 第一次面对一个新 doc_type（例如"实训手册"） | 5 分钟内通过 AI 辅助配置出可用的字段骨架，再人工微调后保存 |
| 模板维护者 | 调整既有模板（例如"教案"模板新增"信息化手段"字段） | 保留已有字段顺序、嵌套结构与历史抽取结果，仅追加/修改 |
| 普通教师 | 上传新文档 | 系统按 doc_type 自动选模板，无需在 UI 选择；模板缺失时给出明确提示而不是"黑盒失败" |
| 运维 / 教学督导 | 排查某文档抽取结果异常 | 能从"文档 → doc_type → 模板 → 字段定义 → 抽取结果"反查，看到该文档到底命中了哪个模板、哪个字段被截断或缺失 |
| 数据治理 / 跨学期复用者 | 把上学期 A 学校的教案模板拷贝到 B 学校 | 通过"复制模板"动作一键复用，再按需调整 doc_type / 字段 |

## 范围

### 包含

REQ-002 的核心目标是把模板的**配置效率 + 复用机制 + 可观测性 + 可维护性**四件事补齐。具体覆盖：

1. **配置效率（编辑器能力补齐）**
   - 字段顺序调整：支持拖拽排序（root / object 子字段 / array 项模板三层都可拖）。
   - 字段引用与复制：在 object / array 子树上支持"复制子树"，减少重复字段定义。
   - 字段删除可逆：删除字段时提示影响范围（已有抽取结果里的该字段会被裁剪），并支持 1 步撤销（站内 toast 撤销 / 软删除均可）。
   - 大模板浏览：在 30+ 字段的模板里支持"折叠/展开全部子树"和"按 label / key 搜索字段"。

2. **复用机制**
   - **同租户复制模板**：从已存在模板"另存为新模板"，保留 fields 嵌套结构与 ai_context，仅允许覆盖 name + doc_types + source_file_id（Q1 决议：仅同租户；跨租户在 P2 起另议，依赖权限与审计约束设计）。
   - **模板版本快照**：每次 update 追加 version 记录，全量保留 + 分页查看，不做超限清理（Q2 决议：全量保留 + 分页；存储成本由模板上下文负责，不引入外部归档）。
   - **模板导入 / 导出**：导出 JSON 模板定义（含嵌套 fields + ai_context + schema_version），跨实例粘贴 JSON 即可重建模板；导入时校验 schema_version，不匹配则提示用户手动确认。

3. **可观测性**
   - **抽取结果溯源**：在 `structured_data["template"]` 内扩展字段为 `{id, version, layer, ...data}`（Q3 决议：扩 template 字段），让"该文档究竟用了哪个模板哪个版本、命中哪一层"成为可查事实；旧 contract 测试需要随子任务同步对齐。
   - **模板使用率**：在 TemplateListView 展示"该模板关联的文档数、最近一次抽取时间、平均字段填充率"，让"哪些模板被冷落"可见。
   - **模板与 doc_type 命中统计**：在 Backend 增加 `GET /api/v1/templates/usage-stats` 端点，按模板聚合 doc_type 覆盖文档数。
   - **字段填充率定义**（Q4 决议：可配置）：默认统计窗口近 30 天，默认口径只看叶子字段（text/textarea/number），UI 允许在"窗口（7d/30d/90d/全部）× 口径（叶子/全量）"两轴切换。

4. **可维护性**
   - **模板与 doc_type 一致性**：单一 doc_type 仍只允许一个活跃模板占用（沿用 `check-doc-type`），但允许"标记 deprecated" 老模板，避免被新文档误命中。
   - **schema 演进策略**（Q6 决议：text/textarea/number 内可改，其余需 schema_version 递增 + 二次确认）：
     - 叶子类型互转（text ⇄ textarea ⇄ number）允许直接保存，schema_version 不递增。
     - object ⇄ table ⇄ array 互转、删除容器字段、删除叶子字段、修改叶子字段 key：必须 `schema_version += 1` 且 UI 二次确认（影响范围提示：现有抽取结果里的该字段会被裁剪/失配）。
     - 新增字段（任意类型）允许，schema_version 不递增。
   - **模板字段命名规范**：校验 `key` 必须是 `^[a-z][a-z0-9_]*$`，禁止与已有字段 key 重复（同一层），避免抽取后端解析失败。

5. **配置效率（编辑器能力补齐）**
   - **拖拽排序**（Q5 决议：root + object 子字段 + array 项模板三层）：root 层 / object children / array items 都允许拖拽；不需要持久化到 ai_context，仅影响 fields 数组顺序。
   - **字段引用与复制**：在 object / array 子树上支持"复制子树"，减少重复字段定义。
   - **字段删除可逆**：删除字段时提示影响范围（已有抽取结果里的该字段会被裁剪），并支持 1 步撤销（站内 toast 撤销 / 软删除均可）。
   - **大模板浏览**：在 30+ 字段的模板里支持"折叠/展开全部子树"和"按 label / key 搜索字段"。

### 不包含

REQ-002 明确不包含以下事项，避免范围蔓延：

- 不重做模板 CRUD / AI 初始化 / 模板匹配 / 嵌套结构抽取（这些由 REQ-004 / REQ-005 / REQ-006 + 当前 backend 实现覆盖）。
- 不引入新的存储引擎或 schema 迁移方向（如 ES / 向量库），保持 PostgreSQL JSONB。
- 不做模板的多语言标签（label 多语种）方案，P2 阶段保持单语种 label。
- 不做模板的权限分级（谁能改 / 谁能用）；现有登录 + 租户隔离即满足 P1 / P2 需求。
- 不做模板的"模板市场"或对外发布，跨租户复制限制在"由用户在 UI 显式发起"。
- 不把模板与 RAG 召回 / KG 抽取耦合；REQ-002 只动模板上下文，不动 knowledge / rag 上下文。
- 不在 P1 做跨租户复制（Q1 决议：P1 仅同租户；跨租户在 P2 起再评估权限与审计约束）。

## 验收（建议拆为多个 REQ 子任务 / 单独 PR）

REQ-002 的塑形期已完成澄清（见「决策记录」段），可拆分为 4 个子任务进入开发。每个子任务验收必须满足以下边界：

| 边界 | 要求 |
|------|------|
| 决议一致性 | 子任务实现不得偏离「决策记录」段决议；如需偏离，必须先回到本 requirement 修订决议并走独立 follow-up |
| 验收口径 | 子任务必须给出 N 条验收点（参考 REQ-005 的 AC-1 ~ AC-11 写法），不能只写"完成模板配置" |
| 行为变化声明 | 若涉及业务代码改动，每个子任务必须明确写出"行为不变 / 行为变化点列表" |
| 复用边界 | 子任务不得把 RAG / KG / 文档解析上下文的功能"顺手"加进来；越界改动按 follow-up 登记 |
| 测试要求 | 涉及编辑器交互的子任务（REQ-002-1）必须至少 1 条 e2e 或可视化回归（puppeteer / playwright / 手测截图任选其一）；涉及 contract 扩展的子任务（REQ-002-3）必须回归 REQ-005 / REQ-006 相关断言 |
| 文档同步 | 子任务完成后必须同步 TemplateListView / TemplateEditorView / TemplateAiPanel / ExtractedDataRenderer 的内嵌说明与 docstring |
| 依赖顺序 | REQ-002-3 必须先于 REQ-002-1 / REQ-002-2 / REQ-002-4 进入开发（`structured_data["template"]` 字段扩展是后续 contract 基线） |

## 决策记录（2026-06-10 塑形澄清）

| # | 问题 | 决议 | 影响范围 |
|---|------|------|----------|
| Q1 | 复用范围：跨租户 / 跨学期"复制模板"在 P1 / P2 哪个阶段必备？ | **P1 仅同租户复制**；跨租户在 P2 起再评估权限与审计约束。 | 复用机制子任务；不需要新建权限分级 / 审计表。 |
| Q2 | 版本快照：保留多少条历史？超限清理策略？ | **全量保留 + 分页**，不做超限清理。 | 模板版本表全量增长；UI 需提供分页；存储由 PostgreSQL JSONB 承担。 |
| Q3 | 抽取结果回写：template_id / template_version 补写到哪里？ | **扩 `structured_data["template"]` 字段**：结构变为 `{id, version, layer, ...data}`。 | 涉及 REQ-005 contract 测试与 REQ-006 e2e 断言同步对齐；document 上下文需要新增字段写入逻辑。 |
| Q4 | 字段填充率指标定义与统计窗口？ | **可配置**：默认近 30 天 + 叶子字段非空率；UI 允许在"窗口（7d/30d/90d/全部）× 口径（叶子/全量）"两轴切换。 | 模板使用率子任务需提供后端聚合端点 + 前端切换控件。 |
| Q5 | 拖拽排序允许哪些层？是否持久化到 ai_context？ | **root + object 子字段 + array 项模板三层**均可拖；**不持久化到 ai_context**，仅影响 fields 数组顺序。 | 配置效率子任务；vuedraggable 已在依赖里，需集成到 FieldItem 树。 |
| Q6 | schema 演进约束？ | **text/textarea/number 内可改（schema_version 不递增）**；其余破坏性变更（容器互转、删字段、改叶子 key）必须 `schema_version += 1` + UI 二次确认。 | 可维护性子任务；template entity / DTO 新增 `schema_version` 字段；前端 editor 增加"破坏性变更"二次确认弹窗。 |

这些决议是 REQ-002 子任务拆分的边界条件。任何子任务在实现时若与上述决议冲突，必须先回到本 requirement 修订决议（新建 REQ-xxx follow-up 或直接修订本文件），不得"实现顺手"改变决议。

## 下一步

REQ-002 已完成塑形（Shaping → Ready 过渡），下一步按以下顺序推进：

1. **子任务拆分**（立即可做）：
   - 把"配置效率 / 复用机制 / 可观测性 / 可维护性"四块拆为独立子任务。**建议子任务编号**（具体由用户在 backlog 创建时确认）：
     - **REQ-002-1 配置效率**：拖拽排序（Q5）+ 字段引用与复制 + 字段删除可逆 + 大模板浏览。
     - **REQ-002-2 复用机制**：同租户复制模板（Q1）+ 模板版本快照（Q2）+ JSON 导入导出。
     - **REQ-002-3 可观测性**：抽取结果溯源字段扩展（Q3）+ 模板使用率展示 + 字段填充率可配置（Q4）+ `usage-stats` 端点。
     - **REQ-002-4 可维护性**：schema_version 字段 + 容器互转 / 删字段二次确认（Q6）+ deprecated 标记 + 字段命名规范校验。
   - 每子任务先建 spec（在 `docs/02-delivery-plans/01-specs/`）+ plan（在 `docs/02-delivery-plans/02-plans/`），再进入开发。
   - 涉及跨 backend + frontend + 数据迁移的子任务（REQ-002-2 / REQ-002-3 / REQ-002-4）按 `superpower` 模式跑；纯前端编辑器补齐（REQ-002-1）可按 `plan-do` 模式。

2. **依赖与边界**：
   - **REQ-002-3（可观测性）必须先于** REQ-002-1 / REQ-002-2 / REQ-002-4 进入开发：因为 `structured_data["template"]` 字段扩展（Q3）会影响后续子任务的 contract 测试基线。
   - 与 REQ-006（P1 演示验收）保持独立：REQ-002 子任务不得为了"演示好看"而扩大范围。
   - 与 `check-engineering-docs` / 质量门禁脚本保持同步：每个子任务的"行为变化声明"必须能通过门禁扫描。
   - 与 memory 中 `next-phase-roadmap.md` 提到的"结构化抽取模板页面"对齐：REQ-002-1 / REQ-002-2 优先满足"模板页面"路线图。

3. **里程碑归属**：
   - REQ-002-1 / REQ-002-3 → P2 阶段（与 milestone 02-growth-phase 对齐）。
   - REQ-002-2 / REQ-002-4 → P2 / P3 视迭代容量决定。

## 历史事实源

- 模板抽取链路 Spec：`docs/90-compat-legacy/superpowers/specs/2026-05-15-document-pipeline-design.md`
- 模板抽取链路 Plan：`docs/90-compat-legacy/superpowers/plans/2026-05-15-document-pipeline-backend.md`
- 模板结构抽取 Spec：`docs/90-compat-legacy/superpowers/specs/2026-05-27-structured-template-design.md`
- 模板结构抽取 Plan：`docs/90-compat-legacy/superpowers/plans/2026-05-27-structured-template-plan.md`
- 模板 ai_context Spec：`docs/90-compat-legacy/superpowers/specs/2026-06-28-template-ai-context-design.md`
- 模板 ai_context Plan：`docs/90-compat-legacy/superpowers/plans/2026-06-28-template-ai-context-implementation.md`
- 模板匹配可解释化 Spec：`docs/02-delivery-plans/01-specs/2026-W23-req-004-template-match-explainability.md`
- 结构化抽取嵌套稳定性 Spec：`docs/02-delivery-plans/01-specs/2026-W23-req-005-structured-extraction-regression.md`
- 模板上下文代码（已实现）：
  - Backend：`packages/server-python/app/contexts/template/`（domain / application / infrastructure / interfaces）
  - Frontend：`packages/web/src/views/admin/` 下 TemplateListView / TemplateEditorView / TemplateModal / TemplateAiPanel / TemplateFormFields / FieldCard / FieldItem + `packages/web/src/components/FieldEditor.vue` + `packages/web/src/components/TableRenderer.vue`
- 当前模板后端测试：`packages/server-python/tests/contexts/template/test_template.py`

## 备注

- 当前模板核心 CRUD + AI 初始化 + 嵌套字段编辑器 + doc_type 冲突检查已落地。REQ-002 不再"重复造轮子"，只补"配置体验 / 复用 / 可观测性 / 可维护性"。
- vuedraggable 已在 `packages/web/package.json` 安装但 UI 未启用，是子任务"配置效率"的天然起点。
- 任何涉及"模板存储 schema 变更"或"跨上下文（document / knowledge / rag）协作"的子任务，必须先建 spec 再进入开发，避免把塑形阶段当成实现阶段。
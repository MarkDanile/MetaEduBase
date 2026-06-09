# REQ-002: 模板化结构抽取能力的配置与复用体验

Status: 🟣 Shaping
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
   - **跨租户 / 跨学期复制模板**：从已存在模板"另存为新模板"，保留 fields 嵌套结构与 ai_context，仅允许覆盖 name + doc_types + source_file_id。
   - **模板版本快照**：在模板上保存"历史版本"（每次 update 写一条 version 记录），允许列表中查看最近 N 个版本并"回滚到该版本"。
   - **模板导入 / 导出**：导出 JSON 模板定义（含嵌套 fields + ai_context），跨实例粘贴 JSON 即可重建模板。

3. **可观测性**
   - **抽取结果溯源**：在 `structured_data["template"]` 旁补充 `template_id` / `template_version` / `match_layer`，让"该文档究竟用了哪个模板哪个版本"成为可查事实。
   - **模板使用率**：在 TemplateListView 展示"该模板关联的文档数、最近一次抽取时间、平均字段填充率"，让"哪些模板被冷落"可见。
   - **模板与 doc_type 命中统计**：在 Backend 增加 `GET /api/v1/templates/usage-stats` 端点，按模板聚合 doc_type 覆盖文档数。

4. **可维护性**
   - **模板与 doc_type 一致性**：单一 doc_type 仍只允许一个活跃模板占用（沿用 `check-doc-type`），但允许"标记 deprecated" 老模板，避免被新文档误命中。
   - **schema 演进策略**：模板字段类型 / 嵌套结构 / columns 定义的破坏性变更必须经过 schema 版本字段校验，避免旧抽取结果字段错位。
   - **模板字段命名规范**：校验 `key` 必须是 `^[a-z][a-z0-9_]*$`，禁止与已有字段 key 重复（同一层），避免抽取后端解析失败。

### 不包含

REQ-002 明确不包含以下事项，避免范围蔓延：

- 不重做模板 CRUD / AI 初始化 / 模板匹配 / 嵌套结构抽取（这些由 REQ-004 / REQ-005 / REQ-006 + 当前 backend 实现覆盖）。
- 不引入新的存储引擎或 schema 迁移方向（如 ES / 向量库），保持 PostgreSQL JSONB。
- 不做模板的多语言标签（label 多语种）方案，P2 阶段保持单语种 label。
- 不做模板的权限分级（谁能改 / 谁能用）；现有登录 + 租户隔离即满足 P1 / P2 需求。
- 不做模板的"模板市场"或对外发布，跨租户复制限制在"由用户在 UI 显式发起"。
- 不把模板与 RAG 召回 / KG 抽取耦合；REQ-002 只动模板上下文，不动 knowledge / rag 上下文。

## 验收（建议拆为多个 REQ 子任务 / 单独 PR）

REQ-002 是塑形阶段的 Shaping 条目，验收标准随子任务展开。在塑形阶段必须明确的边界：

| 边界 | 要求 |
|------|------|
| 验收口径 | 子任务必须给出 N 条验收点（参考 REQ-005 的 AC-1 ~ AC-11 写法），不能只写"完成模板配置" |
| 行为变化声明 | 若涉及业务代码改动，每个子任务必须明确写出"行为不变 / 行为变化点列表" |
| 复用边界 | 子任务不得把 RAG / KG / 文档解析上下文的功能"顺手"加进来；越界改动按 follow-up 登记 |
| 测试要求 | 涉及编辑器交互的子任务必须至少 1 条 e2e 或可视化回归（puppeteer / playwright / 手测截图任选其一） |
| 文档同步 | 子任务完成后必须同步 TemplateListView / TemplateEditorView / TemplateAiPanel 的内嵌说明与 docstring |

## 待回答问题（塑形期必须澄清）

1. **复用范围**：跨租户 / 跨学期"复制模板"是 P1 必备还是 P2 必备？若 P1 必备，需要哪些权限与审计约束？
2. **模板版本快照**：保留全部历史版本还是只保留最近 N 条？超限后的清理策略？
3. **抽取结果回写**：`template_id` / `template_version` 是补写到现有 `structured_data["template"]` 旁还是另起一个字段（如 `template_meta`）？需要 REQ-006 / 文档上下文协作配合，避免旧字段被新结构覆盖。
4. **字段填充率**：以什么指标定义"字段填充率"（非空字段数 / 总字段数？叶子字段 vs 容器字段？）？统计窗口（近 7 天 / 30 天 / 全部）？
5. **拖拽排序**：仅 root 层还是包含 object 子字段 / array 项模板？拖拽后的状态是否需要持久化到 ai_context 或独立字段？
6. **schema 演进**：字段类型变化（text → table）是否允许？破坏性变更（删字段）是否需要两步确认？

## 下一步

REQ-002 当前处于塑形阶段，下一步按以下顺序推进：

1. **塑形收口（当前 PR 范围内）**
   - 沉淀本 requirement 文件为后续 spec / plan 的入口。
   - 把 backlog `下一步` 从"从历史 superpower计划中提炼需求边界"改为"完成塑形并拆分为子任务列表"。
   - 在 current-work `下一批候选任务` 维持 Shaping 不变；候选状态未变。

2. **子任务拆分（Shaping → Ready 过渡时）**
   - 把"配置效率 / 复用机制 / 可观测性 / 可维护性"四块拆为独立子任务（建议编号 REQ-002-1 ~ REQ-002-4 或独立新 ID，由用户/团队约定）。
   - 每子任务先建 spec（在 `docs/02-delivery-plans/01-specs/`）+ plan（在 `docs/02-delivery-plans/02-plans/`），再进入开发。
   - 涉及跨 backend + frontend + 数据迁移的子任务按 `superpower` 模式跑；纯前端编辑器补齐可按 `plan-do` 模式。

3. **明确依赖与边界**
   - 与 REQ-006（P1 演示验收）保持独立：REQ-002 子任务不得为了"演示好看"而扩大范围。
   - 与 `check-engineering-docs` / 质量门禁脚本保持同步：每个子任务的"行为变化声明"必须能通过门禁扫描。
   - 与 memory 中 `next-phase-roadmap.md` 提到的"结构化抽取模板页面"对齐：REQ-002 的子任务优先满足"模板页面"路线图。

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
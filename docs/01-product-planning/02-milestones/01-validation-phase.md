# P1: 阶段一 — 验证期

Status: 🟡 Doing
Current: Yes
External:

## Goal

在 **PostgreSQL 单引擎 + 最少基础设施依赖** 前提下，验证两条核心产品链路：

1. RAG 问答链路：用户提问 -> 多源召回 -> 融合排序 -> LLM 回答。
2. 文档抽取链路：文档上传 -> 模板匹配 -> 结构化抽取 / 知识图谱抽取。

阶段一的核心判断不是“功能数量最多”，而是证明平台的知识资产处理闭环可用，并且在不扩张基础设施的情况下具备最小质量能力。

## Retrieval Architecture

阶段一的“3 通道召回”是 **PostgreSQL 单引擎验证版**，不是最终行业形态的“向量库 + 图数据库 + Elasticsearch”三件套。当前目标是在最少基础设施下验证 RAG 链路、抽象接口和降级能力。

| 通道 | 当前实现 | 查询对象 | 目标 | 非目标 |
|------|----------|----------|------|--------|
| Vector | `PgVectorRecallChannel` | `knowledge_nodes.embedding` + pgvector `<=>` | 验证语义召回能进入问答上下文 | 不引入 Milvus / Qdrant |
| Keyword | `PgKeywordRecallChannel` | `knowledge_nodes.title` / `description` + `ILIKE` | 用最简单全文兜底补充语义召回 | 不引入 Elasticsearch，不做中文分词 |
| Metadata | `PgMetadataRecallChannel` | `RuleBasedNER` 输出的 `domain` / `level` 过滤 | 用职教领域枚举和层级信息提高召回相关性 | 不做图遍历，不查询 `knowledge_edges` |

编排方式：

- `ai_chat` 先执行 `RuleBasedNER.extract`，得到领域和层级。
- 三个 PostgreSQL 通道通过 `asyncio.gather` 并行执行。
- 单通道失败由 `_run_channel` 捕获并降级为空结果，避免单通道故障拖垮整体问答。
- `FrequencyFusion` 按“出现通道数优先，其次最佳分数”融合排序。
- `sources` 从融合结果生成，返回 `id` / `title` / `domain` / `level` / `score` / `channel`。

阶段一的关键交付不是召回质量达到最终形态，而是：RAG 链路可演示、`RecallChannel` / `ResultFusion` 抽象已落地、后续能按阶段替换为更强通道。

## Tracks

### 轨道 A：产品能力

| 里程碑项 | 状态 | 说明 |
|---|---|---|
| 基础架构搭建 | 🟢 Done | FastAPI + Vue3 + PostgreSQL + pgvector |
| Identity 认证上下文 | 🟢 Done | JWT + 多租户 ContextVar |
| Knowledge 知识图谱上下文 | 🟢 Done | CRUD + 知识树 + ltree 物化路径 |
| Resource / Document 文档上下文 | 🟢 Done | 文件上传/下载 + MinIO 本地存储 |
| AI Chat 基础对话 | 🟢 Done | 规则 NER + 3 通道召回 + 频次融合 + Provider resolver |
| 数据要素模板管理 | 🟢 Done | 模板 CRUD + AI 辅助配置 |
| 文档结构化抽取 | 🟢 Done | 模板匹配 + JSON 结构化结果 |
| 文档知识图谱抽取 | 🟢 Done | 文件级 KG 抽取与展示 |
| `ui-*` 语义化 UI 体系 | 🟢 Done | workspace 语义层 + 4 主题；`liquid-*` 保留兼容别名和少量品牌/装饰例外 |
| MCP Server | 🟢 Done | 知识库查询工具 |
| 前端 Markdown 渲染 | 🟢 Done | marked + highlight.js 代码高亮 |

### 轨道 B：检索 / 抽取质量

本轨道采用“实现事实 / 验证证据”分栏口径：代码存在只能证明已实现，必须有测试或端到端验收证据后，才可关闭阶段一质量项。

状态用于快速阅读；验收事实仍以“验证结论”为准，不用颜色替代证据。

| 里程碑项 | 状态 | 实现事实 | 验证结论 | 说明 |
|---|---|---|---|---|
| NER 实体识别（枚举规则） | 🟢 Done | 已实现 | 已通过 `tests/contexts/ai/test_rule_based_ner.py` 7 用例（AC-1/AC-2） | `RuleBasedNER` 已落地；测试覆盖域别名 / 关键词 / 全角 / 大小写 / 未知 query / dataclass / 协议；未覆盖空字符串 query。 |
| 多源并行召回（3 通道） | 🟡 待集成验收 | 已实现 | 已通过 `test_recall_channels_contract.py` 9 用例（AC-6）+ `test_recall_channels_behavior.py` 9 用例（AC-1 行为级）；端到端 PG 集成待 REQ-006 | PostgreSQL 内 vector / keyword / metadata 三通道已落地；不是图谱召回或 ES 全文检索。契约层（形参 / `name` / 返回类型 / 空实现）已锁定；行为层覆盖各通道 tenant / topk / embedding / keywords / NER 信号缺失时的回退。 |
| 结果融合（频次排序） | 🟢 Done | 已实现 | 已通过 `tests/contexts/ai/test_frequency_fusion.py` 5 用例（AC-3/AC-4/AC-5） | `FrequencyFusion` 已落地；测试覆盖通道频次优先、最佳分数排序、空输入和单通道降级。 |
| 溯源上下文组装增强 | 🟡 待补边界 | 已实现 | 已通过 `tests/contexts/ai/test_ai_chat_rag_e2e.py` 3 用例（AC-7 单通道失败降级 / AC-8 sources 字段集 / AC-9 跨通道去重）；未覆盖空召回回退与 LLM 失败兜底文案 | `ai_chat` 返回 `sources`，含 channel / node_id / title / score；e2e 用例覆盖单通道异常降级、sources 字段集、跨通道去重；空召回（`fused = []`）与 `_call_llm` 异常兜底文案尚无对应测试。 |
| 模板匹配可解释化 | 🟡 待集成验收 | 已实现 | 已通过 `tests/contexts/document/test_extract_template_selection.py` 16 项用例（9 旧分支回归 + 4 caplog 参数化 L1/L2/L3/none 日志可观测 + 1 L3 confidence 解析失败 0.0 < 阈值 + 1 L3 空响应 `AI returned empty response` + 1 生产代码漂移保护）：L1 精确 / L2 文件名 / L3 AI 命中 / L3 低于阈值 / L3 单行默认 0.5 / L3 命中未配置 / L3 LLM 异常 / 空 doc_type 文件名 / L1 优先级高于 L2 L3。3 层匹配已抽到 `app/contexts/document/application/template_selector.py`，4 个分支各输出统一 `template.select layer=...` 日志；端到端 PG 集成待 REQ-006。REQ-008（[PR #79](https://github.com/MarkDanile/MetaEduBase/pull/79)）收口 ruff 5 项清零 + L3 解析失败 / 空响应覆盖 + caplog 断言 + 漂移保护。 | 选择器纯函数可单测；3 层优先级与阈值 0.7 不变。 |
| 结构化抽取嵌套结构稳定性 | 🟢 Done | 已实现 | 已通过 `tests/contexts/document/test_extract_template_prompts.py` 11 项用例（AC-1~AC-8）：`build_fields_desc` 覆盖 object 单层 / 2 层嵌套 / array 含 items / array 空 items 降级到 bare type / table 列顺序 / object+array+table+text 混合；`try_parse` 覆盖 markdown fence 含 object+array+table 三层嵌套 / `<think>` 标签剥离后再解析 / 坏 JSON 降级 / 未闭合 fence 降级；`_merge_template_structured_data` 锁定浅拷贝契约（外层新 dict、内嵌 list/dict 同引用）。`array + items=[]` 走 bare-type 分支是当前既定行为，已被回归锁定。端到端 PG + 真实 LLM 演示待 REQ-006。 | object / array / table 嵌套抽取链路可纯函数回归，无需 LLM / DB；0 业务代码改动。 |

### 轨道 C：基础设施

| 里程碑项 | 状态 | 说明 |
|---|---|---|
| PostgreSQL 单引擎 | 🟢 Done | 业务数据 + 向量 + 图谱关系共库 |
| Celery + Redis | 🟢 Done | 文档 / 数据集异步任务 |
| MinIO 单节点 | 🟢 Done | 对象存储，本地 fallback |
| LLM Provider 工厂 + fallback | 🟢 Done | `factory.py` + `provider_resolver.py` 已集中 provider 选择；统一代理和计量留到阶段二 |
| Protocol 接口定义 | 🟢 Done | `NERPipeline` / `RecallChannel` / `ResultFusion` Protocol 已落地 |
| 测试回归 | 🟡 Doing | 完整运行依赖 `metaedu_test` 初始化；质量门禁持续维护 |

## Completion Criteria

- RAG 问答链路可完成：用户输入问题 -> NER 识别领域 / 级别 -> 3 通道并行召回 -> 融合排序 -> LLM 带来源标注回答。
- 阶段一 3 通道限定为 PostgreSQL 内 vector / keyword / metadata；图谱关系召回、ES 全文检索和独立向量库属于后续阶段。
- 文档抽取链路可完成：上传文档 -> 命中模板 -> 输出结构化结果 / 知识图谱结果。
- 回归测试和质量门禁可复现运行。
- 无新增基础设施依赖，仍以 PostgreSQL / Redis / MinIO 为主。
- P1 关闭前，轨道 B 的“待验证 / 待收口”项必须通过测试或演示验收，并把结果回填到本文件、迭代文件和 Backlog。

## Open Items

| ID | 状态 | 说明 | 归属 |
|----|------|------|------|
| REQ-001 | ⚪ Idea | 知识资产处理链路的产品化验收视图 | `docs/01-product-planning/04-backlog.md` |
| REQ-002 | ⚪ Idea | 模板化结构抽取能力的配置与复用体验 | `docs/01-product-planning/04-backlog.md` |
| REQ-003 | 🟢 Done | P1 RAG 质量链路验收与回归测试（已由 PR #74 关闭，验收缺口由 REQ-007 承接） | `docs/01-product-planning/04-backlog.md` |
| REQ-004 | 🟢 Done | 模板匹配可解释化收口（主要代码和测试由 PR #77 关闭；验收证据与质量门禁缺口由 REQ-008 承接） | `docs/01-product-planning/04-backlog.md` |
| REQ-005 | 🟢 Done | 结构化抽取嵌套结构稳定性验收（`tests/contexts/document/test_extract_template_prompts.py` 11 项用例，object / array / table 嵌套回归；0 业务代码改动） | `docs/01-product-planning/04-backlog.md` |
| REQ-006 | 🟣 Shaping | P1 知识资产处理链路最终演示验收（spec / plan 骨架已建；Stage 1 待实施：端到端脚本 + UI 手册；`metaedu_test` 已恢复） | `docs/01-product-planning/04-backlog.md` |
| REQ-007 | 🟢 Done | REQ-003 复盘缺口的 RAG 质量链路收口（5 AC 全部由 [PR #75](https://github.com/MarkDanile/MetaEduBase/pull/75) 关闭：行为级测试 + e2e 死代码清理 + 状态同步 + 过度验证声明修正 + 验证声明真实） | `docs/01-product-planning/04-backlog.md` |
| REQ-008 | 🟢 Done | 收口 REQ-004 验收证据与质量门禁缺口（5 项 ruff 清零 + 4 分支 caplog 断言 + L3 解析失败 / 空响应覆盖 + 漂移保护；[PR #79](https://github.com/MarkDanile/MetaEduBase/pull/79)） | `docs/01-product-planning/04-backlog.md` |

## Evidence

- 历史规划：`git show bf6429c:ARCHITECTURE.md`
- 文档处理管道：`docs/90-compat-legacy/superpowers/specs/2026-05-15-document-pipeline-design.md`
- 模板结构抽取：`docs/90-compat-legacy/superpowers/specs/2026-05-27-structured-template-design.md`
- 工程交付记录：`docs/03-engineering-governance/work-log.md`
- 2026-06-07 复核命令：`.venv/bin/python -m pytest tests/contexts/ai/test_ai_chat.py tests/contexts/knowledge/test_knowledge.py tests/contexts/document/test_structured_data_contract.py tests/contexts/template/test_template.py -q`
- 2026-06-07 复核结果：`7 passed, 27 errors`；错误原因为本机 PostgreSQL `localhost:5432` 连接失败，不能证明 P1 集成验收通过。

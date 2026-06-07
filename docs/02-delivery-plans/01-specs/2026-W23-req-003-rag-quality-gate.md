# REQ-003 P1 RAG 质量链路验收与回归测试 — Spec

> Spec 入口：REQ-003（Backlog `Candidate` → 进入 `Ready` / `Planned` 的依据）。本文件是验收口径与边界的事实源；实施拆分见 `docs/02-delivery-plans/02-plans/2026-W23-req-003-rag-quality-gate-plan.md`。

## 目标

为 P1 验证期 RAG 质量链路四要素（NER、3 通道召回、频次融合、sources 结构）建立可复现运行的回归测试；让轨道 B 中"已实现 / 待验证"项可以凭证据关闭。

## 范围

包含：

- `RuleBasedNER.extract` 的纯函数 / 异步函数回归测试（域别名、层级关键字、归一化、未知输入）。
- `FrequencyFusion.fuse` 的纯函数回归测试（去重、频次优先、最佳分数兜底、渠道合并、空输入、`top_k` 截断）。
- `ai_chat` 端到端回归测试，断言 `sources` 的结构（`id` / `title` / `domain` / `level` / `score` / `channel`）和融合后的行为（重复节点频次提升、单通道失败降级、LLM stub）。
- 把 3 个 `PgXxxRecallChannel` 的 SQL 路径锁在接口级契约（mock `AsyncSession.execute` 走 fake rows），不直接连 PostgreSQL。
- 把验收结果回填到 `docs/01-product-planning/02-milestones/01-validation-phase.md` 轨道 B 与 `docs/01-product-planning/04-backlog.md` REQ-003 状态。

不包含：

- 端到端真 PostgreSQL 集成测试（独立任务：先修本机 `metaedu_test` 连通性 / `make init-test-db`，不在本 REQ 范围内）。
- 新增向量库、图数据库、ES、对象存储等基础设施（阶段二才考虑）。
- NER / 融合算法的功能升级（只锁行为，不重写）。
- 性能基准与 RRF / rerank（阶段二才做）。
- 真实 LLM provider 校验（用现有 `httpx.AsyncClient` mock 模式）。

## 验收标准

| ID | 验收点 | 通过条件 | 失败条件 |
|----|--------|----------|----------|
| AC-1 | NER 域与层级识别 | 至少 6 条用例覆盖别名 / 中文括号 / 大小写 / 关键词优先级 / 未知 query | 任何用例不通过 |
| AC-2 | NER 协议形状 | `RuleBasedNER` 满足 `NERPipeline` 协议（`runtime_checkable`） | 不通过 |
| AC-3 | 融合去重与频次 | 同 `node_id` 跨通道出现合并；按"频次降序 → 最佳分数降序"排序 | 排序或合并不符 |
| AC-4 | 融合 `top_k` 截断 | `top_k=2` 时只输出 2 条；空输入返回 `[]` | 截断不符 |
| AC-5 | 融合 `channel` 拼接 | 合并后 `channel` 含全部来源通道名（去重），顺序与频次一致 | 缺通道或重复 |
| AC-6 | Recall 通道接口契约 | 3 通道同 `RecallChannel` 协议形态；`name` 分别为 `vector`/`keyword`/`metadata` | 缺协议或命名错 |
| AC-7 | 单通道失败降级 | 注入通道抛异常时，`ai_chat` 仍返回 200 且 `sources` 至少包含其他通道命中 | 整体 500 或 sources 空 |
| AC-8 | `sources` 字段结构 | 端到端 mock LLM 时，`sources` 列表每个元素具备 `id/title/domain/level/score/channel`，无多余字段 | 字段缺失或多余 |
| AC-9 | 端到端融合行为 | 多通道同 `node_id` 在 `sources` 里只出现一次，`channel` 含多通道名 | 重复或单通道 |
| AC-10 | 命令可复现 | `cd packages/server-python && .venv/bin/python -m pytest tests/contexts/ai tests/contexts/knowledge -q` 退出码 0 | 退出码非 0 |
| AC-11 | 文档回填 | `01-validation-phase.md` 轨道 B 四项由"待验证"翻为具体验证结论（指向测试文件/命令）；Backlog REQ-003 状态推到 `Done` 或明确 `Blocked` 原因 | 未回填 |

## 接口与依赖

测试目标模块（不可改）：

- `app/contexts/knowledge/application/ner_service.py:RuleBasedNER`
- `app/contexts/knowledge/application/recall_service.py:PgVectorRecallChannel / PgKeywordRecallChannel / PgMetadataRecallChannel`
- `app/contexts/knowledge/application/fusion_service.py:FrequencyFusion`
- `app/contexts/knowledge/interfaces/api/ai_router.py:ai_chat` + 内部 `_recall_to_source`

测试工具沿用现有风格（`tests/conftest.py`）：

- 纯函数 / 协议测试用 `pytest` 直接调对象，不连 DB。
- 通道 / 端到端用 `unittest.mock.AsyncMock` 模拟 `AsyncSession.execute` 返回 `mappings().all()`，避免本机 PG 依赖。
- 沿用 `tests/contexts/ai/test_ai_chat.py` 已有的 `httpx.AsyncClient` mock 模式打 LLM。

## 文件计划

新增：

- `packages/server-python/tests/contexts/ai/test_rule_based_ner.py`（AC-1、AC-2）
- `packages/server-python/tests/contexts/ai/test_frequency_fusion.py`（AC-3、AC-4、AC-5）
- `packages/server-python/tests/contexts/ai/test_recall_channels_contract.py`（AC-6）
- `packages/server-python/tests/contexts/ai/test_ai_chat_rag_e2e.py`（AC-7、AC-8、AC-9）

修改：

- `docs/01-product-planning/02-milestones/01-validation-phase.md`（AC-11）
- `docs/01-product-planning/04-backlog.md`（AC-11）

不动：

- `app/contexts/knowledge/**` 任何业务代码（不混入行为变更）。

## 风险与边界

- `FrequencyFusion` 现有实现里 `existing.channel` 写回 list 后又用 `","` 拼回字符串，**存在被构造出重复渠道的边角行为**（取决于 `set` 顺序）。spec 验收写"含全部来源通道名（去重）"——如果首次跑发现实际未去重，spec 验收要相应放宽到"含全部来源（允许重复）"并入账技术债，不得改业务代码绕过。
- `RuleBasedNER._normalize` 的全角符号替换里 `"（" → "("`、`"）" → ")"`，可能与 SQL `ILIKE` 路径交互但**与 NER 单元测试无关**。记入观察项，不在本 REQ 处理。
- 当前 `conftest.py` 依赖 `metaedu_test` 存在；本 spec 测试不主动触发该 fixture（直接构造对象 / mock session），避免被 DB 阻塞。

## 不在范围 / 后续任务

| ID | 说明 | 归属 |
|----|------|------|
| REQ-006 | 端到端 PG 集成验收（要求 `metaedu_test` 可达） | 单独 task |
| TD-??? | 如 AC-5 触发的 `FrequencyFusion.channel` 重复/去重行为 | 触发现入账 |
| REQ-004 | 模板匹配可解释化 | 单独 task |
| REQ-005 | 结构化抽取嵌套结构稳定性 | 单独 task |

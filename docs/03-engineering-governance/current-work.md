# 当前开发工作台

本文件是所有 AI IDE、插件和人工协作的当前任务入口。开始任何开发任务前，先阅读本文件，再按任务卡片中的链接渐进式读取相关 spec、plan、技术债或架构约束。

不同任务类型的开工条件、必读文档和完成标准见 `docs/03-engineering-governance/task-modes.md`。

## 使用规则

- 本文件只保留当前任务、近期候选和少量最近完成任务；任何修改本文件或任务状态前，必须先读 `docs/03-engineering-governance/01-rules/workbench.md`。
- 开发前确认本次任务卡片，并按卡片链接渐进式读取 spec、plan、技术债或架构约束。
- 涉及跨文件开发、计划接力、状态交接或后续继续开发时，必须登记或更新任务卡片。
- 代码、验证或 Git 阶段变化后，必须同步任务状态、当前进展、下一步和验证结果。
- 提交、PR、合并或声明完成前，运行 `scripts/check-engineering-docs` 并执行 `docs/03-engineering-governance/01-rules/quality-gates.md#完成门禁`；门禁主实现位于 `scripts/engineering/check_engineering_docs.py`。

## 当前进行中

当前无活跃任务。REQ-039 P2 graph_edge 禁用全量真 LLM 验收解除阻塞（TD-071 接力）已 🟢 完成（验证报告含 AC-4 wall-clock 超时 follow-up：实测 17.8min 全 suite，REQ-028 v3 子集按比例 6.6min 达标）。TD-071 实施 PR #384 open 待 merge。后续候选见下方。

## 下一批候选任务

| 任务 | 状态 | 优先级 | 领域 | 下一步 | 事实源 |
|------|------|--------|------|--------|--------|
| AC-4 wall-clock 超时 follow-up | 🔵 候选 | P3 | P2 / RAG / Verification | 本次实测全 suite 17.8min 超 AC-4 ≤10min 目标。REQ-028 v3 子集按比例 6.6min 达标。如需严格满足 AC-4，下次 brief 命令需显式限制 REQ-028 子集（仅传 `--req028-samples` 不传 `--weak-recall-samples`，或加 `--limit`） | [REQ-039 验收报告 §6 follow-up #1](../02-delivery-plans/01-specs/2026-06-21-req-039-p2-graph-edge-disable-llm-verify-unblock-report.md#6-follow-up) |
| Q7_kg_occupation_to_skill graph_edge 退化排查 | 🔵 候选 | P3 | P2 / RAG / Fusion | baseline 0.4 → graph_edge 0（substring/semantic 口径），1/27 样例。graph_edge 通道在某些 fusion 排序下改变 packed chunk 选择导致命中下降。规模小不构成系统性；如需修复需复查 fusion 排序与 graph_edge 通道交互 | [REQ-039 验收报告 §6 follow-up #2](../02-delivery-plans/01-specs/2026-06-21-req-039-p2-graph-edge-disable-llm-verify-unblock-report.md#6-follow-up) |
| 离线批量 keypoint embedding 预计算 | 🔵 候选 | P3 | RAG / Embedding / TD | REQ-037 登记 follow-up。TD-071 batch helper 已铺路：runner.py 改 `embedding_callable=get_embeddings_with_timeout_batch` 可进一步省 HTTP 数（预计全量 ~5min） | [REQ-037 验收报告 §6](../02-delivery-plans/01-specs/2026-06-21-req-037-graph-edge-disable-real-llm-verify-report.md#6-follow-up) |

## 最近完成

最近完成区默认最多保留 20 行（按 `docs/03-engineering-governance/01-rules/workbench.md#保留策略` 强约束）。超过 20 行时，必须一次性批量归档，只保留最新 12 行；第 13 行及以后全部移出。不得每次只移动 1 行。本表只承担"近期完成窗口"的角色，详细验证、行为变化、PR 描述和复盘见 `docs/03-engineering-governance/work-log.md`、对应技术债总账、plan 或 PR。

按"最近优先"（最新任务在最上）排序：

| 日期 | 任务 | 状态 | 摘要 | 事实源 |
|------|------|------|------|--------|
| 2026-06-22 | REQ-039 P2 graph_edge 禁用全量真 LLM 验收解除阻塞（TD-071 接力） | 🟢 完成 | 全量 `--allow-llm --concurrency 4` 实测 17.8min（27 样例 × 6 scenario = 162 run）；`_EMB_STATS` hit=2177/miss=475/timeout=0/error=0 健康。mismatch=37（70% LLM 噪声字段，确定性字段正负抵消）。REQ-036 禁用决策真实 LLM 维度无系统性回归 | [REQ-039](../01-product-planning/05-requirements/REQ-039-p2-graph-edge-disable-llm-verify-unblock.md) / [验收报告](../02-delivery-plans/01-specs/2026-06-21-req-039-p2-graph-edge-disable-llm-verify-unblock-report.md) / [PR #384](https://github.com/MarkDanile/MetaEduBase/pull/384) |
| 2026-06-21 | REQ-002 模板化结构抽取配置与复用体验 closeout | 🟢 Done | 4 子任务全收口：REQ-002-3 溯源（PR #153）+ REQ-002-1 配置效率（PR #158）+ TD-041 嵌套拖拽（PR #161）+ REQ-002-2 复用机制（PR #159）+ TD-042 PG 集成测试（PR #159/#122）+ REQ-002-4 可维护性（PR #170）。requirement Status 🔵 Ready → 🟢 Done，docs-only 内务登记 | [Requirement](../01-product-planning/05-requirements/REQ-002-template-config-and-reuse.md) |
| 2026-06-21 | W25 迭代 2026-W25 P2 RAG 质量增强 收口 | 🟢 Done | Scope 24 项全交付（修复 BUG-007 漂移）。覆盖 REQ-013/014/015 + REQ-016/017/018 + REQ-024→037 + TD-068/069/070 + DOC-074。graph_edge 治理全闭环 | [迭代文件](../01-product-planning/03-iterations/2026-W25-p2-rag-quality-enhancement.md) / [work-log 索引](work-log.md) |
| 2026-06-21 | REQ-037 P2 graph_edge 禁用真 LLM 全量验收（REQ-036 follow-up） | 🟢 完成 | 全量真 LLM run 受 embedding provider 累积吞吐阻塞；dry-run 实证 10/10 样例 baseline = graph_edge@0.5 零覆盖度差异。全量真 LLM 登记 REQ-038 follow-up | [REQ-037](../01-product-planning/05-requirements/REQ-037-p2-graph-edge-disable-real-llm-verify.md) / [验收报告](../02-delivery-plans/01-specs/2026-06-21-req-037-graph-edge-disable-real-llm-verify-report.md) |
| 2026-06-21 | TD-070 vector 召回 query embedding 无超时兜底 | 🟢 完成 | `get_embedding_with_timeout(text, timeout=60.0)` helper + 3 recall 调用点改造。慢 provider 从阻塞 90s 改为 60s fail-fast 降级 keyword。+3 单测 89 passed 无回归，解锁 REQ-037 | [TD-070](technical-debt.md#td-070) / [Spec](../02-delivery-plans/01-specs/2026-06-21-td-070-vector-recall-timeout.md) |
| 2026-06-21 | DOC-074 AI / RAG 需求完成态分层与真实验收口径收紧 | 🟢 完成 | PR #376 squash merge `96689b7`：定义效果型任务最高验证层级，明确代码接入、mock、dry-run / 真实 PG、真实 LLM / 用户验收不得互相冒充；评分卡同步扣分口径 | [Backlog](../01-product-planning/04-backlog.md) / [PR #376](https://github.com/MarkDanile/MetaEduBase/pull/376) |
| 2026-06-20 | REQ-036 P2 graph_edge 通道禁用实现（REQ-035 follow-up） | 🟢 完成 | `GRAPH_EDGE_RECALL_ENABLED` env 门控默认 off；`PgEdgeRecallChannel` 代码保留可重新启用。单测 37 passed 无回归。dry-run 实证 4/10 样例 packed 仅 1-2 chunk 微调。真 LLM 全量验收因 embedding provider 慢阻登记 REQ-037。REQ-018 基线降级 | [REQ-036](../01-product-planning/05-requirements/REQ-036-p2-graph-edge-channel-disable-impl.md) / [实现报告](../02-delivery-plans/01-specs/2026-06-20-req-036-graph-edge-channel-disable-impl-report.md) |
| 2026-06-20 | REQ-035 P2 graph_edge 通道去留决策（REQ-034 follow-up） | 🟢 完成 | 成本/收益对照 + 禁用/上调可行性 + 决策。**决策：禁用 graph_edge 通道**。生产默认 0.5 下召回纯无效；即使 boosting 增益有限。禁用机制已存在（`edge_retriever=None`）。登记 REQ-036 实现候选 | [REQ-035](../01-product-planning/05-requirements/REQ-035-p2-graph-edge-channel-decision.md) / [决策报告](../02-delivery-plans/01-specs/2026-06-20-req-035-graph-edge-channel-decision-report.md) |
| 2026-06-20 | REQ-034 P2 graph_edge RRF 权重/策略调整评估（REQ-033 follow-up） | 🟢 完成 | 5 点 weight sweep + 策略可行性 + REQ-018/025 影响面。**关键发现**：生产默认 0.5 下 graph_edge 召回 8 chunks/样例但 0 进 fusion/packed（惰性死权重）；REQ-033 Metric A=5/10 实测于 w=1.2 boosting，高估生产贡献。下调权重无效；保留 0.5，登记 REQ-035 决策候选 | [REQ-034](../01-product-planning/05-requirements/REQ-034-p2-graph-edge-rrf-weight-strategy-evaluation.md) / [评估报告](../02-delivery-plans/01-specs/2026-06-20-req-034-graph-edge-rrf-weight-strategy-evaluation-report.md) |
| 2026-06-20 | REQ-033 P2 链路真 vector 价值评估 | 🟢 完成 | retrieval 层价值评估：指标 A（edge 关联补足率）=5/10、指标 B（跨 section 扩展）=1/10、跨文档 grounding=0/10。判定**价值有限**。AC-5 根因归档为指标错配（keypoint 覆盖 vs graph_edge 关联补足目标不一致），REQ-030 翻完成。登记 REQ-034 候选 | [REQ-033](../01-product-planning/05-requirements/REQ-033-p2-chain-real-vector-value-evaluation.md) / [评估报告](../02-delivery-plans/01-specs/2026-06-20-req-033-p2-chain-value-evaluation-report.md) |
| 2026-06-20 | REQ-032 P2 semantic_emb 阈值校准与 continuous 口径 | 🟢 完成 | `--semantic-emb-threshold` CLI + continuous 字段。threshold 0.35 后 AC-4 达标 4/10；AC-5 三口径各 1/10，根因定位为 P2 链路无正向贡献（非阈值），登记 REQ-033 | [REQ-032](../01-product-planning/05-requirements/REQ-032-p2-semantic-emb-threshold-calibration.md) / [Report](../02-delivery-plans/01-specs/2026-06-20-req-030-new-quality-metric-report.md) |
| 2026-06-20 | REQ-031 P2 semantic embedding 覆盖率稳定性（REQ-030 接力） | 🟢 完成 | 进程内 embedding 缓存（hit=1581/miss=259）+ asyncio.wait_for 60s 硬超时 + 降级。timeout=0/error=0 消除 batch 挂起；semantic_emb 从全 0 变为 8/10 非零。REQ-030 AC-4/5 阈值校准留 follow-up | [REQ-031](../01-product-planning/05-requirements/REQ-031-p2-semantic-embedding-coverage-stabilization.md) / [Report](../02-delivery-plans/01-specs/2026-06-20-req-030-new-quality-metric-report.md) |
| 2026-06-20 | REQ-030 P2 RAG 自动质量评估新口径（semantic embedding + LLM-as-judge） | 🟢 完成 | 四口径 + continuous + retrieval 层指标 A/B 评估口径充分。AC-4 达标 4/10；AC-5 三口径各 1/10 不达标，REQ-033 归档为指标错配（非链路缺陷）。经 REQ-031/032/033 三轮接力收口 | [REQ-030](../01-product-planning/05-requirements/REQ-030-p2-rag-new-quality-metric.md) / [Report](../02-delivery-plans/01-specs/2026-06-20-req-030-new-quality-metric-report.md) / [REQ-033 评估报告](../02-delivery-plans/01-specs/2026-06-20-req-033-p2-chain-value-evaluation-report.md) |

# P4: 阶段四 — 规模化与多模态

Status: ⚪ Future
Current: No
External:

## Goal

在 P3 企业 Agent 平台和真实应用证明价值后，进入按瓶颈触发的升级模式。P4 关注容量、延迟、可用性、多模态和高可用，但每次只升级一个指标最明确的子系统，不为架构完整性一次性引入多套基础设施。

## Entry Criteria

- P3 Control Plane、Workspace、Runtime、Tool Gateway、Approval，以及 APP-005/009/012/030/016 园区近期主线的分阶段业务验收达到完成标准。
- 现有 PostgreSQL/Redis/MinIO/外部模型链路出现可复现的容量、性能、成本、可用性或多模态业务瓶颈。
- 每个升级项有基线、目标、迁移/回滚方案和真实负载验证，不按技术偏好进入开发。

## Retrieval Architecture

P4 才评估多引擎 RAG：独立向量库、图数据库、全文搜索集群和多模态索引分别承担不同职责，再由现有 Tool Gateway 和 Retrieval 抽象聚合结果。

| 通道 / 引擎 | 候选实现 | 解决的问题 | 触发前提 |
|-------------|----------|------------|----------|
| 向量检索 | Milvus / Qdrant | 百万级向量容量、索引内存、低延迟语义召回 | pgvector 容量或 p99 延迟成为瓶颈 |
| 知识图谱检索 | Neo4j | 多跳关系、图算法、复杂知识路径推理 | PostgreSQL 递归查询或关系边规模成为瓶颈 |
| 全文检索 | Elasticsearch | 中文分词、同义词、拼音、复杂过滤和高亮 | PostgreSQL `tsvector` 无法满足质量或性能 |
| 多模态召回 | 视觉 / 音频 embedding + 多模态索引 | 文本、语音、图像统一检索 | 有真实教育/园区多模态应用和授权数据 |
| 融合与重排 | RRF + Reranker + Circuit Breaker | 跨引擎排序、容错和通道熔断 | 多引擎并行后出现稳定质量/可用性需求 |

GraphRAG 在本阶段仍是可选 Retrieval Tool，不替代 Agent Control Plane、Runtime、Approval 或 Memory。

## Tracks

### 轨道 A：容量与检索引擎

| 升级项 | 说明 |
|--------|------|
| Milvus / Qdrant | 独立向量数据库与水平扩展 |
| Neo4j | 知识图谱引擎、图算法和多跳查询 |
| Elasticsearch | 中文全文搜索、复杂过滤和高亮 |
| Reranker | 只有离线评测证明收益覆盖延时/成本时引入 |

### 轨道 B：多模态与模型基础设施

| 升级项 | 说明 |
|--------|------|
| 视觉/音频理解 | 图像、扫描件、语音和视频的结构化理解与检索 |
| 自部署推理 | vLLM/Embedding/Reranker 私有化部署，按成本、数据和 SLA 触发 |
| 专用模型 | 领域 NER、分类或抽取模型，需真实数据集和持续评测 |

### 轨道 C：高可用与运维

| 升级项 | 说明 |
|--------|------|
| Object Storage | MinIO 集群或 S3/OSS，按容量和可用性迁移 |
| Queue | Redis broker 到 RabbitMQ，按队列可靠性和吞吐触发 |
| Observability | Prometheus/Grafana/Trace，与 Agent Run 指标统一 |
| Runtime Cells | 高风险/高负载租户独立 Cell，支持弹性、配额和故障域隔离 |
| Circuit Breaker | Runtime、模型、检索和外部 Tool 的熔断/降级 |

## Trigger Signals

| 组件 | 容量阈值 | 性能 / 质量阈值 | 切换信号 |
|------|----------|-----------------|----------|
| pgvector | 100 万+ 向量 | p99 检索 > 500ms | 评估 Milvus / Qdrant |
| ltree + JSONB | 10 万+ 边 / 3 跳以上查询 | 递归 CTE > 1s | 评估 Neo4j |
| PostgreSQL tsvector | 50 万+ 文档 | 关键词搜索 > 300ms 或质量不足 | 评估 Elasticsearch |
| Celery + Redis | 队列持续堆积 / 任务可靠性不足 | 队列深度持续 > 100 | 评估 RabbitMQ |
| Embedding/LLM API | 限频或数据边界不满足 | QPS、成本或 SLA 不达标 | 评估自部署模型 |
| MinIO 单节点 | 存储 > 500GB | 可用性目标 >= 99.9% | 评估 MinIO 集群 / S3 |
| Shared Runtime Worker | 高风险租户或资源争用 | P95 排队/运行时间持续超标 | 评估 per-tenant Runtime Cell |

阈值是评估触发器，不是自动迁移命令。进入实现前必须用生产或等价负载重新校准。

## Completion Criteria

- 被触发的子系统达到独立 spec 定义的容量、P95/P99、可用性、成本和恢复目标。
- 每次迁移保留回滚路径、双读/影子验证或等价一致性证明，不同时替换多个事实源。
- 多模态能力必须完成至少一个真实授权教育或园区场景，不以模型 Demo 代替业务验收。
- Agent Control Plane、Tool Gateway、tenant policy、Approval 和 Artifact 契约不因底层引擎替换而改变所有权。

## Open Items

| ID | 状态 | 说明 | 归属 |
|----|------|------|------|
| P4-VECTOR | ⚪ Future | Milvus / Qdrant 独立向量库 | 待触发指标成立 |
| P4-GRAPH | ⚪ Future | Neo4j 知识图谱引擎 | 待触发指标成立 |
| P4-SEARCH | ⚪ Future | Elasticsearch 全文搜索集群 | 待触发指标成立 |
| P4-MULTIMODAL | ⚪ Future | 教育/园区多模态理解与检索 | 待真实应用和数据授权成立 |
| P4-OBS | ⚪ Future | 全链路可观测、HA 和 Runtime Cell | 待 P3 运行指标形成基线 |

## Evidence

- P3 里程碑：[03-agent-platform-phase.md](03-agent-platform-phase.md)
- 历史 P3 规模化规划兼容入口：[03-scale-phase.md](03-scale-phase.md)
- 技术债和治理进展：`docs/03-engineering-governance/technical-debt.md`
- 工程工作日志：`docs/03-engineering-governance/work-log.md`

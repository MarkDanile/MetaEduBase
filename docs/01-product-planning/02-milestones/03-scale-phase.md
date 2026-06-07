# P3: 阶段三 — 规模化

Status: Future
Current: No
External:

## Goal

进入按瓶颈触发的升级模式，按子系统容量、延迟、可用性和质量阈值逐项演化，而不是一次性整体替换。阶段三关注多引擎、多模态、可观测性和高可用，但每次只升级一个瓶颈最明确的子系统。

## Retrieval Architecture

阶段三才进入接近行业常见形态的多引擎 RAG：独立向量库、图数据库、全文搜索集群分别承担不同召回职责，再由统一编排和融合层聚合结果。

| 通道 / 引擎 | 阶段三候选实现 | 解决的问题 | 触发前提 |
|-------------|----------------|------------|----------|
| 向量检索 | Milvus / Qdrant | 百万级向量容量、索引内存、低延迟语义召回 | pgvector 容量或 p99 延迟成为瓶颈 |
| 知识图谱检索 | Neo4j | 多跳关系、图算法、复杂知识路径推理 | PostgreSQL 递归查询或关系边规模成为瓶颈 |
| 全文检索 | Elasticsearch | 中文分词、同义词、拼音、复杂过滤和高亮 | PostgreSQL `tsvector` 无法满足召回质量或性能 |
| 多模态召回 | 视觉 / 音频 embedding + 多模态索引 | 文本、语音、图像统一检索 | 阶段二文本链路稳定且有真实多模态需求 |
| 融合与重排 | RRF + Reranker + Circuit Breaker | 跨引擎结果排序、容错、通道熔断 | 多引擎并行后需要稳定质量和可用性 |

阶段三不是“为了架构完整而替换”，而是根据触发指标逐项升级。每次只替换一个瓶颈明确的子系统，并保留阶段一 / 二建立的召回通道和融合抽象。

## Tracks

### 轨道 A：产品能力扩展

| 升级项 | 说明 |
|---|---|
| LLaVA 视觉理解 | 图像 / 视频 -> 多模态 Embedding |
| 多模态端到端检索 | 文本 + 语音 + 图像统一召回与生成 |
| 专用 NER 模型 | 微调职教领域实体识别，覆盖率 95%+ |
| RRF + Reranker | 动态权重 + 可选二次排序 |

### 轨道 B：数据与检索引擎升级

| 升级项 | 说明 |
|---|---|
| Milvus / Qdrant | 独立向量数据库，水平扩展 |
| Neo4j | 知识图谱引擎，支持图算法 |
| Elasticsearch | 全文搜索集群，中文分词 + 同义词 + 拼音 |

### 轨道 C：基础设施与运维能力

| 升级项 | 说明 |
|---|---|
| vLLM 自部署 | 私有化 LLM 推理集群 |
| S3 / OSS 云存储 | 替代 MinIO |
| Prometheus + Grafana | 全链路监控 |
| Circuit Breaker | 召回通道熔断器 |

## Trigger Signals

| 组件 | 容量阈值 | 性能 / 质量阈值 | 切换信号 |
|---|---|---|---|
| pgvector | 100 万+ 向量 | p99 检索 > 500ms | 评估迁移 Milvus / Qdrant |
| ltree + JSONB | 10 万+ 边 / 3 跳以上查询 | 递归 CTE > 1s | 评估迁移 Neo4j |
| ILIKE / tsvector | 50 万+ 文档 | 关键词搜索 > 300ms | 评估迁移 Elasticsearch |
| Celery + Redis | 队列堆积 / 任务丢失 | 队列深度持续 > 100 | 评估迁移 RabbitMQ |
| Embedding API | API 限频 | QPS 不足 | 评估自部署 Embedding 模型 |
| MinIO 单节点 | 存储 > 500GB | 可用性要求 99.9% | 评估 MinIO 集群 / S3 |
| 规则 NER | 覆盖率不足 | 规则命中率 < 70% | 评估 LLM 混合 NER 或专用模型 |
| 频次融合 | 排序质量不足 | 用户对结果满意度低 | 评估 RRF / Reranker |
| PostgreSQL 并行召回 | 通道数增加 / 跨引擎 | 单一引擎成为瓶颈 | 评估多引擎编排 |

## Completion Criteria

- 百万级向量检索 p99 达到阶段目标，旧规划参考值为 <= 200ms。
- 系统可用性达到阶段目标，旧规划参考值为 >= 99.9%。
- 多模态（文本 + 语音 + 图像）端到端检索能力成熟。

## Open Items

| ID | 状态 | 说明 | 归属 |
|----|------|------|------|
| DOC-024 | Idea | 工程协作规则模板化，等本项目规则经过更多实践后进入 Shaping | `docs/01-product-planning/04-backlog.md` |
| P3-VECTOR | Future | Milvus / Qdrant 独立向量库 | 待触发指标成立 |
| P3-GRAPH | Future | Neo4j 知识图谱引擎 | 待触发指标成立 |
| P3-SEARCH | Future | Elasticsearch 全文搜索集群 | 待触发指标成立 |
| P3-OBS | Future | Prometheus + Grafana 全链路监控 | 待触发指标成立 |

## Evidence

- 历史规划：`git show bf6429c:ARCHITECTURE.md`
- 技术债和治理进展：`docs/03-engineering-governance/technical-debt.md`
- 工程工作日志：`docs/03-engineering-governance/work-log.md`

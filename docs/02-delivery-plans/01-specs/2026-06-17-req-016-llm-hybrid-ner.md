# REQ-016 Spec: P2 LLM 混合 NER / Query Understanding

> Status: 🟣 Shaping
> Created: 2026-06-17
> Source: P2-NER Open Item

## 1. Problem Statement

当前 `RuleBasedNER` + `BUG-010` deterministic normalizer 已能处理确定性关键词匹配（专业/课程/知识点领域词、电子信息/智能制造等 domain 别名）。但用户真实问法是自然语言：

- "我想了解这个专业大二上学期有哪些核心课程？"（嵌套意图 + 时间约束）
- "Python 函数的参数要怎么理解最好"（术语意图，未命中 domain/level 关键词）
- "这门课的教学做得好不好？"（需要情感/质量维度过滤）

这类 query 的 `domains` / `levels` 均为空，`raw_entities` 也不足以引导召回。需要在规则 NER 之上加一层 **LLM Query Understanding**，将自然问法解析成检索友好的结构化意图，并只在必要时调用 LLM（避免延迟和成本失控）。

## 2. Goals

1. 建立稳定、可 trace 的 LLM Query Understanding schema
2. 实现低置信 / 规则未命中触发 LLM 的策略
3. LLM 输出的检索术语扩展（expanded terms）可被召回链路消费
4. 完整 trace 进入 AI Chat diagnostics
5. 保留 BUG-010 deterministic normalizer 行为，零回归

## 3. Non-Goals

- 不训练专用 NER 模型
- 不替代 chunk / graph / keyword 召回本身
- 不引入 Elasticsearch / Neo4j / reranker
- 不在规则命中场景调用 LLM（成本 + 延迟控制）

## 4. Architecture

### 4.1 层次结构

```
User Query
    │
    ▼
┌─────────────────────────┐
│   RuleBasedNER.extract  │  ← 确定性规则匹配，零成本
└────────┬────────────────┘
         │ NERResult
         ▼
┌─────────────────────────┐
│  QueryUnderstandingEngine │  ← 新增：判断是否需要 LLM
│  (HybridQueryUnderstandingService) │
└────────┬────────────────┘
         │ confidence < threshold
         ▼
┌─────────────────────────┐
│  LLM Query Understanding │  ← 可选，HTTP 调用
│  (via _call_llm)        │
└────────┬────────────────┘
         │ QueryUnderstandingResult
         ▼
┌─────────────────────────┐
│  Retrieval Pipeline     │  ← 消费 expanded_terms / filters
└─────────────────────────┘
```

### 4.2 核心数据模型

#### 新增 `QueryUnderstandingResult`

```python
class QueryUnderstandingResult(BaseModel):
    """REQ-016 — LLM Query Understanding 输出结构."""

    method: Literal["rule", "llm"]           # 使用的方法
    confidence: float                         # 0.0–1.0，LLM 时有效
    normalized_query: str                     # 规范化后的核心 query
    core_terms: list[str]                    # 核心检索词（来自规则或 LLM）
    expanded_terms: list[str]                 # 扩展检索词（近义词/相关词，LLM 时有）
    entities: list[str]                      # 识别的实体
    filters: dict[str, Any]                   # 过滤条件 {field: value}
    raw_llm_output: str | None = None         # LLM 原始输出（用于 trace）
    llm_model: str | None = None              # LLM 模型名（用于 trace）
```

#### 修改后的 `NERResult`（不变）

现有 `NERResult` 保持不变（domains / levels / raw_entities），由规则 NER 填充。

#### `HybridQueryUnderstandingResult` 组合结果

```python
class HybridQueryUnderstandingResult(BaseModel):
    """规则 NER + LLM QU 的组合结果."""
    ner: NERResult                             # 规则 NER 结果
    query_understanding: QueryUnderstandingResult | None = None  # LLM QU（未触发时 None）
    trigger_reason: str | None = None          # 为什么触发/未触发 LLM
```

### 4.3 触发策略

| 条件 | 行为 |
|------|------|
| `NERResult` 非空（命中 domain 或 level） | 不触发 LLM，直接用规则结果 |
| `NERResult` 为空 **且** query 长度 > 15 字符 | 触发 LLM Query Understanding |
| `NERResult` 为空 **且** query 长度 ≤ 15 字符 | 不触发，返回 method="rule" + confidence=0.0 |
| LLM 调用失败 | 降级为 method="rule" + confidence=0.0，记录 error trace |

**置信度阈值：`confidence < 0.5` 时视为低置信，LLM QU 结果的 expanded_terms 会进入检索。**

### 4.4 LLM Prompt Schema

System prompt 要求 LLM 输出 JSON，字段对应 `QueryUnderstandingResult`。

## 5. File Layout

```
packages/server-python/app/contexts/knowledge/application/
├── ner_service.py                          # 修改：RuleBasedNER
├── hybrid_ner_service.py                    # 新增：HybridQueryUnderstandingService
└── query_understanding.py                  # 新增：QueryUnderstandingResult 模型

packages/server-python/app/contexts/knowledge/application/ai_chat_service.py
                                              # 修改：注入 HybridQueryUnderstandingService
                                              # 修改：diagnostics 包含 query_understanding
packages/server-python/tests/contexts/ai/
├── test_hybrid_ner_service.py               # 新增：LLM QU 回归测试
└── test_rule_based_ner.py                   # 不改（已有）
```

## 6. Acceptance Criteria

| ID | 内容 | 验证方式 |
|----|------|----------|
| AC-1 | `QueryUnderstandingResult` schema 稳定，字段完整 | Pydantic model validation test |
| AC-2 | 规则命中 query（"电子信息专业课程"）不触发 LLM，method="rule" | Unit test |
| AC-3 | 规则未命中 + query > 15 字符触发 LLM，method="llm"，expanded_terms 非空 | Mock LLM test |
| AC-4 | LLM 调用失败时降级 method="rule"，不抛异常 | Mock failure test |
| AC-5 | 召回链路能消费 `expanded_terms` | Integration / e2e |
| AC-6 | diagnostics 输出包含 query_understanding（method / confidence / expanded_terms / trigger_reason） | Unit test |
| AC-7 | BUG-010 deterministic normalizer 行为不变 | 现有回归测试通过 |
| AC-8 | 至少 3 类真实问法有回归测试：Python 教程 / 课程能力 / 资源库 | Test cases |

## 7. Diagnostics Trace

`AIChatDiagnostics` 新增字段：

```python
class AIChatDiagnostics(BaseModel):
    # … existing fields …
    query_understanding: dict | None = None  # 新增
```

输出示例（JSON）：
```json
{
  "query_understanding": {
    "method": "llm",
    "confidence": 0.82,
    "normalized_query": "python 函数参数",
    "core_terms": ["python", "函数参数"],
    "expanded_terms": ["函数参数", "parameter", "参数传递", "默认值参数"],
    "entities": ["Python"],
    "filters": {},
    "trigger_reason": "rule_miss_and_long_query"
  }
}
```

## 8. Relationship to Existing Code

| 组件 | 关系 |
|------|------|
| `RuleBasedNER` | 不修改行为，作为前置规则层 |
| `NERPipeline` Protocol | 扩展实现类 `HybridQueryUnderstandingService` 仍满足 Protocol |
| `AIChatService` | 注入新的 `HybridQueryUnderstandingService`，仍接收 `NERResult` 供 retrievers 使用 |
| `CompositeChunkRetriever` | `expanded_terms` 通过 `ner_result` 间接传给 retrievers（retrievers 已有 `ner_result` 参数） |
| REQ-017 RRF diagnostics | `query_understanding` 在 fusion diagnostics 之前填充，互不干扰 |

## 9. Slice 划分建议

| Slice | 内容 | 依赖 |
|-------|------|------|
| Slice 1 | `QueryUnderstandingResult` schema + `hybrid_ner_service.py` 骨架 + 触发策略 + Mock LLM tests | — |
| Slice 2 | 接入 `AIChatService`，diagnostics 扩展，真实 LLM call（dev DB 验证） | Slice 1 |
| Slice 3 | `expanded_terms` 流经 retrievers（若 retrievers 已支持 `ner_result` 的 terms 扩展则跳过） | Slice 2 |
| Slice 4 | 真实样例回归测试 + 真实 PG 验证报告 | Slice 3 |

"""REQ-016 — LLM Query Understanding schemas and prompt templates.

QueryUnderstandingResult: LLM Query Understanding 输出结构.
HybridQueryUnderstandingResult: 规则 NER + LLM QU 组合结果.
QUERY_UNDERSTANDING_PROMPT: LLM system prompt 模板.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.shared.domain.ner_pipeline import NERResult


class QueryUnderstandingResult(BaseModel):
    """REQ-016 — LLM Query Understanding 输出结构."""

    method: Literal["rule", "llm"] = "rule"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    normalized_query: str = ""
    core_terms: list[str] = Field(default_factory=list)
    expanded_terms: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)
    raw_llm_output: str | None = None
    llm_model: str | None = None

    model_config = {"extra": "forbid"}


class HybridQueryUnderstandingResult(NERResult):
    """规则 NER + LLM QU 的组合结果，继承 NERResult 以满足 NERPipeline Protocol.

    继承字段: domains / levels / raw_entities 来自规则 NER.
    扩展字段: query_understanding(LLM QU 结果) / trigger_reason(触发原因).
    便捷属性: method / confidence / normalized_query 代理到 query_understanding.
    """

    query_understanding: QueryUnderstandingResult | None = None
    trigger_reason: str | None = None

    model_config = {"extra": "forbid"}

    @property
    def method(self) -> str:
        """代理到 query_understanding.method，fallback 为 'rule'."""
        if self.query_understanding is not None:
            return self.query_understanding.method
        return "rule"

    @property
    def confidence(self) -> float:
        """代理到 query_understanding.confidence."""
        if self.query_understanding is not None:
            return self.query_understanding.confidence
        return 0.0

    @property
    def normalized_query(self) -> str:
        """代理到 query_understanding.normalized_query."""
        if self.query_understanding is not None:
            return self.query_understanding.normalized_query
        return ""


QUERY_UNDERSTANDING_PROMPT = """\
你是一个教育知识库的查询理解助手。你的任务是将用户的自然语言问题解析成结构化的检索意图。

## 任务
给定用户的查询，输出一个 JSON 对象，包含以下字段：

- "normalized_query": 规范化后的核心查询（去除停用词、语气词）
- "core_terms": 核心检索词列表（来自原始查询的专业术语、领域词）
- "expanded_terms": 扩展检索词列表（同义词、近义词、相关概念，用于提升召回）
- "entities": 识别出的实体（课程名、专业名、技术栈等）
- "filters": 过滤条件字典，如 {"level": "professional", "domain": "electronics_info"}
- "confidence": 置信度 0.0-1.0（表示你对解析结果的自信程度）
- "reason": 一句话解释你如何理解这个查询

## 要求
- 只返回 JSON，不要有其他文字。
- expanded_terms 应该包含至少 2-3 个同义词或相关概念，帮助召回更多相关内容。
- 如果查询非常简单直接，expanded_terms 可以与 core_terms 相同或接近。
- 中文回答，JSON 字段名用英文。

## 示例
输入：Python 函数的参数要怎么理解最好
输出：{"normalized_query": "Python 函数参数", "core_terms": ["Python", "函数参数"],
      "expanded_terms": ["parameter", "参数传递"], "entities": ["Python"],
      "filters": {}, "confidence": 0.85, "reason": "编程语言学习类"}

输入：电子信息专业大二课程有哪些
输出：{"normalized_query": "电子信息专业课程", "core_terms": ["电子信息", "课程"],
      "expanded_terms": ["电子信息工程", "专业课"], "entities": ["电子信息专业"],
      "filters": {"level": "course", "domain": "electronics_info"},
      "confidence": 0.92, "reason": "专业课程检索"}

输入：土木建筑的知识点
输出：{"normalized_query": "土木建筑知识点", "core_terms": ["土木建筑", "知识点"],
      "expanded_terms": ["土木工程", "建筑学"], "entities": ["土木建筑"],
      "filters": {"domain": "civil_engineering"}, "confidence": 0.88,
      "reason": "专业领域知识点检索"}
"""

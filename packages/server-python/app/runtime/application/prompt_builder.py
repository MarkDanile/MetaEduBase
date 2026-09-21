"""TD-085 Slice B — Prompt 构造（含 Context Packing 消费侧编排）。

从 ``knowledge.application.ai_chat_service`` 拆出的 prompt 构造职责
（spec ADR-085-2）：

- ``build_prompt_context``：把 PackedContext 的 blocks 渲染为「参考证据」
  prompt 段（[1] / [2] 编号与 evidence[] citation 序列一致）。
- ``build_user_content``：拼装最终 user message（有证据段 / 无证据段两态）。

边界约束：

- runtime 不 import knowledge 模块。这里通过窄 Protocol
  （``PromptPackedLike`` 等）结构化消费 packed 对象，保持
  knowledge/application → runtime/application 单向依赖。
- runtime 不携带业务 prompt 文案：``SYSTEM_PROMPT`` 等业务措辞保留在
  knowledge 侧（``AIChatService.SYSTEM_PROMPT``），本模块只负责结构拼装。

行为保持：函数体从 ``ai_chat_service._build_prompt_context`` /
``_evidence_source_label`` 逐字迁移，输出字符串 byte-identical。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class PromptEvidenceLike(Protocol):
    """build_prompt_context 需要的最小 evidence 结构面。

    只读 property 成员（协变）：``EvidenceItem.source_type`` 是
    ``SourceType`` Literal，属性不变量下不等于 ``str``，property
    形式让 ``SourceType <: str`` 成立。
    """

    @property
    def source_type(self) -> str: ...

    @property
    def title(self) -> str: ...


class PromptBlockLike(Protocol):
    """build_prompt_context 需要的最小 packed block 结构面。"""

    @property
    def evidence_index(self) -> int: ...

    @property
    def source_type(self) -> str: ...

    @property
    def title(self) -> str: ...

    @property
    def content(self) -> str: ...

    @property
    def channels(self) -> list[str]: ...

    @property
    def expansion_type(self) -> str: ...


class PromptPackedLike(Protocol):
    """PackedContext 的最小消费面（Sequence 保持协变，兼容 list 实参）。"""

    @property
    def blocks(self) -> Sequence[PromptBlockLike]: ...

    @property
    def evidence(self) -> Sequence[PromptEvidenceLike]: ...


def _evidence_source_label(ev: PromptEvidenceLike | None) -> str:
    if ev is None:
        return "unknown"
    if ev.source_type == "chunk":
        return "chunk"
    if ev.source_type == "knowledge_node":
        return "knowledge_node"
    if ev.source_type == "knowledge_edge":
        return "knowledge_edge"
    if ev.source_type == "structured_field":
        return "structured_field"
    return ev.source_type


def build_prompt_context(packed: PromptPackedLike) -> str:
    """Build 「参考证据」 prompt segment with [1] / [2] numbering.

    Uses packed.blocks[] for content (neighbor-expanded / section-expanded).
    Citation numbering follows block.evidence_index to stay consistent with
    the evidence[] citation sequence the caller sees in sources.
    """
    if not packed.blocks:
        return ""
    ctx = "\n\n参考证据：\n"
    for block in packed.blocks:
        evidence_idx = block.evidence_index
        # Look up the original evidence for stable source label
        ev = (
            packed.evidence[evidence_idx - 1]
            if evidence_idx <= len(packed.evidence)
            else None
        )
        source_label = _evidence_source_label(ev) if ev else block.source_type
        title_part = block.title or (ev.title if ev else block.evidence_index)
        channels = ",".join(block.channels) if block.channels else "—"
        expansion_tag = (
            f" [{block.expansion_type}]" if block.expansion_type != "hit" else ""
        )
        ctx += (
            f"[{evidence_idx}] 来源: {source_label}{expansion_tag} | "
            f"标题: {title_part} | 命中: {channels}\n{block.content}\n"
        )
    return ctx


def build_user_content(context_text: str, message: str) -> str:
    """拼装最终 user message：有参考证据段时前置，否则仅问题本体。"""
    if context_text:
        return f"{context_text}\n\n学生问题：{message}"
    return f"学生问题：{message}"

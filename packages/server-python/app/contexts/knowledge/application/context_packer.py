"""`ContextPacker` — REQ-013 RAG Context Packing.

Responsibilities:
- Take fused `EvidenceItem[]` and expand each hit into a richer context
  by fetching neighboring chunks and/or same-section chunks.
- Guard against TOC / directory chunks dominating the prompt.
- Produce a `PackedContext` whose `blocks[]` feed the LLM prompt,
  while `evidence[]` (the original `EvidenceItem[]`) remains the citation
  sequence exposed to the caller / UI.

Packing order (budget-governed):
  1. Hit chunk itself.
  2. Neighbor expansion  (chunk_index ± 1, same file_id).
  3. Section expansion   (same section_path, within budget).
  4. Graph source expansion (knowledge_node → fetch source chunk + neighbors).

TOC guard:
  - A chunk is TOC-like if its title or content matches `IS_TOC_LIKE_PATTERNS`.
  - TOC-like blocks are kept in the evidence list but ranked below
    non-TOC blocks when building the prompt.

Budget:
  - `max_chars` (default 4 000) caps total packed content.
  - `max_blocks` (default 8) caps number of PackedContextBlocks.
  - `max_chars_per_block` (default 800) prevents a single block from
    consuming the entire budget.

Usage:
    packer = ContextPacker(session, tenant_id)
    packed = await packer.pack(fused_evidence, options)
    prompt_blocks = packed.blocks   # feed LLM prompt
    sources       = packed.evidence # citation sequence (unchanged)
"""

from __future__ import annotations

import re
import uuid

import structlog
from pydantic import BaseModel, Field

from app.contexts.knowledge.domain.evidence import EvidenceItem

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# TOC-like detection patterns
# ---------------------------------------------------------------------------

_IS_TOC_TITLE_PATTERNS = [
    re.compile(r"^目[录录]", re.IGNORECASE),
    re.compile(r"^Table\s+of\s+Contents$", re.IGNORECASE),
    re.compile(r"^目录\s*\(Table\s+of\s+Contents\)$", re.IGNORECASE),
    re.compile(r"^第\s*\d+\s*章.*页码$"),  # "第 1 章 … 页码"
    re.compile(r"^章节\s*索引$", re.IGNORECASE),
    re.compile(r"^Content$"),                # standalone "Content"
]

_IS_TOC_CONTENT_PATTERNS = [
    re.compile(r"^第\s*\d+\s*[章节]\s+\S+.*?\s+\d+\s*$"),  # "第 1 章 标题 … 12"
    re.compile(r"^\S+\s+\d+$", re.MULTILINE),              # "标题名 12" on most lines
    re.compile(r"^(Chapter|第).*?(\d+[-–]\d+|\d+)$", re.IGNORECASE | re.MULTILINE),
]


def is_toc_like_chunk(title: str, content: str) -> bool:
    """Return True when `title` or `content` strongly resemble a TOC / directory."""
    for pat in _IS_TOC_TITLE_PATTERNS:
        if pat.match(title.strip()):
            return True
    # Very short content that is mostly line-number / page-number patterns
    lines = content.strip().splitlines()
    page_num_pat = re.compile(r"^\S.*?\s+\d+\s*$")
    if 3 <= len(lines) <= 60 and all(
        page_num_pat.match(ln) or ln.strip() == ""
        for ln in lines
        if ln.strip()
    ):
        return True
    return any(pat.search(content) for pat in _IS_TOC_CONTENT_PATTERNS)


# ---------------------------------------------------------------------------
# Options
# ---------------------------------------------------------------------------

class ContextPackingOptions(BaseModel):
    """Tunable parameters for context packing."""

    max_chars: int = Field(default=4000, ge=100, le=20000)
    max_blocks: int = Field(default=8, ge=1, le=50)
    max_chars_per_block: int = Field(default=800, ge=50, le=4000)
    neighbor_window: int = Field(default=1, ge=0, le=3)
    include_toc_blocks: bool = Field(
        default=True,
        description="Whether to include TOC-like blocks at all; False = drop them completely",
    )
    toc_guard: bool = Field(
        default=True,
        description="Whether to deprioritize TOC blocks to prompt tail (still kept in evidence)",
    )


# ---------------------------------------------------------------------------
# Packed context model
# ---------------------------------------------------------------------------

class PackedContextBlock(BaseModel):
    """A single block of content assembled for the LLM prompt.

    One block may represent:
    - The hit chunk itself
    - A neighbor chunk
    - A same-section continuation chunk
    """

    evidence_index: int = Field(description="1-based index into EvidenceItem[]")
    file_id: uuid.UUID | None = None
    chunk_ids: list[uuid.UUID] = Field(
        default_factory=list,
        description="All chunk IDs included in this block (for traceability)",
    )
    source_type: str = "chunk"
    title: str = ""
    section_title: str | None = None
    section_path: str | None = None
    content: str = ""
    channels: list[str] = Field(default_factory=list)
    score: float | None = None
    is_toc_like: bool = False
    expansion_type: str = Field(
        default="hit",
        description="hit | neighbor | section | graph_source",
    )

    model_config = {"extra": "forbid"}


class PackedContextDiagnostics(BaseModel):
    """Debug / trace information about the packing process."""

    channel_top_k: dict[str, int] = Field(default_factory=dict)
    fused_count: int = 0
    graph_hydrated_count: int = 0
    total_blocks_before_trim: int = 0
    total_chars_before_trim: int = 0
    toc_blocks_count: int = 0
    sections_fallback_triggered: bool = False
    graph_chunks_fetched: int = 0


class PackedContext(BaseModel):
    """Output of `ContextPacker.pack()`."""

    blocks: list[PackedContextBlock] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    diagnostics: PackedContextDiagnostics = Field(default_factory=PackedContextDiagnostics)

    model_config = {"extra": "forbid"}


# ---------------------------------------------------------------------------
# ContextPacker
# ---------------------------------------------------------------------------

class ChunkRepositoryInterface:
    """Abstract interface for chunk storage — implemented by ChunkRepository."""

    async def get_chunks_by_file_and_indices(
        self,
        file_id: uuid.UUID,
        indices: list[int],
        tenant_id: uuid.UUID,
    ) -> dict[int, dict]:
        ...

    async def get_chunk_by_id(
        self,
        chunk_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> dict | None:
        """Fetch a single chunk row by its primary key id."""
        ...

    async def get_chunks_by_file_and_section(
        self,
        file_id: uuid.UUID,
        section_path: str,
        tenant_id: uuid.UUID,
        *,
        limit: int = 12,
    ) -> list[dict]:
        """Fetch chunks in one section for parent-section expansion."""
        ...


class ContextPacker:
    """Expand fused evidence into a richer context."""

    def __init__(
        self,
        chunk_repo: ChunkRepositoryInterface,
        tenant_id: uuid.UUID,
        options: ContextPackingOptions | None = None,
    ) -> None:
        self._chunk_repo = chunk_repo
        self._tenant_id = tenant_id
        self._opts = options or ContextPackingOptions()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def pack(
        self,
        evidence: list[EvidenceItem],
        *,
        channel_top_k: dict[str, int] | None = None,
    ) -> PackedContext:
        """Main entry point.

        Args:
            evidence: fused + graph-hydrated EvidenceItem[] from AIChatService.
            channel_top_k: optional {channel_name: count} for diagnostics.

        Returns:
            PackedContext with `blocks[]` for the LLM prompt and `evidence[]`
            (identical to input, preserved for citation sequence).
        """
        diag = PackedContextDiagnostics(
            fused_count=len(evidence),
            channel_top_k=channel_top_k or {},
        )

        # Separate TOC vs non-TOC for the TOC guard
        toc_indices: set[int] = set()
        for idx, ev in enumerate(evidence, 1):
            title = getattr(ev, "title", "") or ""
            content = getattr(ev, "content", "") or ""
            if is_toc_like_chunk(title, content):
                toc_indices.add(idx)

        diag.toc_blocks_count = len(toc_indices)

        # ------------------------------------------------------------------
        # Phase 1: process all chunk-type evidence (hit + neighbor expansion)
        # ------------------------------------------------------------------
        file_chunks: dict[uuid.UUID, dict[int, dict]] = {}
        blocks: list[PackedContextBlock] = []
        seen_chunk_keys: set[tuple[uuid.UUID, uuid.UUID]] = set()

        for idx, ev in enumerate(evidence, 1):
            if ev.source_type != "chunk":
                continue
            fid = ev.file_id
            if fid is None:
                continue

            cid = ev.chunk_id
            if cid is not None:
                key = (fid, cid)
                if key in seen_chunk_keys:
                    continue
                seen_chunk_keys.add(key)

            chunk_idx = ev.metadata.get("chunk_index")
            if chunk_idx is None:
                continue

            # Neighbor indices to fetch
            neighbors = list(range(
                max(0, chunk_idx - self._opts.neighbor_window),
                chunk_idx + self._opts.neighbor_window + 1,
            ))
            missing = [n for n in neighbors if n not in file_chunks.get(fid, {})]
            if missing:
                if fid not in file_chunks:
                    file_chunks[fid] = {}
                rows = await self._chunk_repo.get_chunks_by_file_and_indices(
                    fid, missing, self._tenant_id,
                )
                file_chunks[fid].update(rows)
            hit_row = file_chunks.get(fid, {}).get(chunk_idx)
            hit_cid = hit_row.get("id") if hit_row else cid
            if hit_cid:
                seen_chunk_keys.add((fid, hit_cid))

            # Hit block
            blocks.append(self._make_block(
                idx, fid, [hit_cid] if hit_cid else [],
                "chunk",
                title=(
                    hit_row.get("section_title")
                    if hit_row and hit_row.get("section_title")
                    else ev.title or ""
                ),
                section_title=(
                    hit_row.get("section_title")
                    if hit_row
                    else ev.metadata.get("section_title")
                ),
                section_path=(
                    hit_row.get("section_path")
                    if hit_row
                    else ev.metadata.get("section_path")
                ),
                content=(
                    hit_row.get("content", "")
                    if hit_row
                    else ev.content
                ),
                channels=ev.channels,
                score=ev.score,
                is_toc_like=(idx in toc_indices),
                expansion_type="hit",
            ))

            # Neighbor blocks
            for n_idx in neighbors:
                if n_idx == chunk_idx:
                    continue
                row = file_chunks.get(fid, {}).get(n_idx)
                if not row:
                    continue
                n_cid = row.get("id")
                if n_cid:
                    seen_chunk_keys.add((fid, n_cid))
                blocks.append(self._make_block(
                    idx, fid, [n_cid] if n_cid else [],
                    "chunk",
                    title=row.get("section_title") or row.get("content", "")[:60],
                    section_title=row.get("section_title"),
                    section_path=row.get("section_path"),
                    content=row.get("content", ""),
                    channels=ev.channels,
                    score=ev.score,
                    is_toc_like=is_toc_like_chunk(
                        row.get("section_title") or "",
                        row.get("content", ""),
                    ),
                    expansion_type="neighbor",
                ))

        # ------------------------------------------------------------------
        # Phase 2: graph evidence → fetch source chunk + expand
        # Slice 3 AC: graph evidence with source_chunk_id is fetched and
        # its neighbors are included in packed context.
        # ------------------------------------------------------------------
        graph_fetch_count = 0
        for idx, ev in enumerate(evidence, 1):
            if ev.source_type != "knowledge_node":
                continue
            source_cid = ev.source_chunk_id or ev.chunk_id
            if source_cid is None:
                continue

            fid = ev.file_id
            if fid is None:
                continue

            # Look up the source chunk row from prior fetches (by id not index)
            source_row = self._find_chunk_by_id(source_cid, file_chunks)

            if source_row is None:
                # Fetch the source chunk directly by id
                source_row = await self._chunk_repo.get_chunk_by_id(
                    source_cid, self._tenant_id,
                )
                if source_row:
                    f_chunks = file_chunks.setdefault(fid, {})
                    f_chunks[source_row["chunk_index"]] = source_row

            if source_row is None:
                continue

            graph_fetch_count += 1
            chunk_idx = source_row["chunk_index"]

            # Fetch neighbors of the source chunk
            neighbors = list(range(
                max(0, chunk_idx - self._opts.neighbor_window),
                chunk_idx + self._opts.neighbor_window + 1,
            ))
            missing = [n for n in neighbors if n not in file_chunks.get(fid, {})]
            if missing:
                if fid not in file_chunks:
                    file_chunks[fid] = {}
                rows = await self._chunk_repo.get_chunks_by_file_and_indices(
                    fid, missing, self._tenant_id,
                )
                file_chunks[fid].update(rows)

            # Build graph-source block (the actual source chunk content)
            blocks.append(self._make_block(
                idx, fid, [source_cid],
                "chunk",
                title=source_row.get("section_title") or ev.title or "",
                section_title=source_row.get("section_title"),
                section_path=source_row.get("section_path"),
                content=source_row.get("content", ""),
                channels=ev.channels,
                score=ev.score,
                is_toc_like=is_toc_like_chunk(
                    source_row.get("section_title") or "",
                    source_row.get("content", ""),
                ),
                expansion_type="graph_source",
            ))

            # Neighbor blocks of the source chunk
            for n_idx in neighbors:
                if n_idx == chunk_idx:
                    continue
                row = file_chunks.get(fid, {}).get(n_idx)
                if not row:
                    continue
                n_cid = row.get("id")
                if n_cid:
                    seen_chunk_keys.add((fid, n_cid))
                blocks.append(self._make_block(
                    idx, fid, [n_cid] if n_cid else [],
                    "chunk",
                    title=row.get("section_title") or row.get("content", "")[:60],
                    section_title=row.get("section_title"),
                    section_path=row.get("section_path"),
                    content=row.get("content", ""),
                    channels=ev.channels,
                    score=ev.score,
                    is_toc_like=is_toc_like_chunk(
                        row.get("section_title") or "",
                        row.get("content", ""),
                    ),
                    expansion_type="neighbor",
                ))

        diag.graph_chunks_fetched = graph_fetch_count

        # ------------------------------------------------------------------
        # Phase 3: section expansion
        # When section_path is stable (non-empty, non-"?"), pull additional
        # chunks from the same section up to budget.
        # Fallback: if section_path is empty/missing, skip (chunk_index
        # neighbors already handled in Phase 1).
        # ------------------------------------------------------------------
        sections_to_expand: dict[tuple[uuid.UUID, str], int] = {}
        for idx, ev in enumerate(evidence, 1):
            fid = ev.file_id
            if fid is None:
                continue
            sp = ev.metadata.get("section_path") or ""
            if sp and sp not in ("?", "null", "undefined"):
                sections_to_expand.setdefault((fid, sp), idx)
        for fid, f_chunks in file_chunks.items():
            for row in f_chunks.values():
                sp = row.get("section_path") or ""
                if sp and sp not in ("?", "null", "undefined"):
                    sections_to_expand.setdefault((fid, sp), 1)

        for (fid, section_path), evidence_index in sections_to_expand.items():
            rows = await self._chunk_repo.get_chunks_by_file_and_section(
                fid,
                section_path,
                self._tenant_id,
                limit=self._opts.max_blocks * 2,
            )
            if fid not in file_chunks:
                file_chunks[fid] = {}
            for row in rows:
                file_chunks[fid][row["chunk_index"]] = row

            # Add section expansion blocks for chunks we don't already have
            for row in sorted(
                file_chunks.get(fid, {}).values(),
                key=lambda item: item.get("chunk_index", 0),
            ):
                sp = row.get("section_path") or ""
                if sp != section_path:
                    continue
                n_cid = row.get("id")
                key = (fid, n_cid) if n_cid else None
                # Only add if not already in blocks (avoid duplicate with neighbor phase)
                already_seen = key is None or key in seen_chunk_keys
                if already_seen:
                    continue
                if n_cid:
                    seen_chunk_keys.add(key)  # type: ignore[arg-type]
                blocks.append(self._make_block(
                    evidence_index=evidence_index,
                    file_id=fid,
                    chunk_ids=[n_cid] if n_cid else [],
                    source_type="chunk",
                    title=row.get("section_title") or row.get("content", "")[:60],
                    section_title=row.get("section_title"),
                    section_path=row.get("section_path"),
                    content=row.get("content", ""),
                    channels=[],
                    score=None,
                    is_toc_like=is_toc_like_chunk(
                        row.get("section_title") or "",
                        row.get("content", ""),
                    ),
                    expansion_type="section",
                ))

        diag.sections_fallback_triggered = False  # always succeeds now (no-op fallback)

        # Budget enforcement
        diag.total_blocks_before_trim = len(blocks)
        diag.total_chars_before_trim = sum(len(b.content) for b in blocks)

        blocks = self._apply_budget(blocks, toc_indices)

        return PackedContext(
            blocks=blocks,
            evidence=evidence,
            diagnostics=diag,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _make_block(
        self,
        evidence_index: int,
        file_id: uuid.UUID | None,
        chunk_ids: list[uuid.UUID],
        source_type: str,
        title: str,
        section_title: str | None,
        section_path: str | None,
        content: str,
        channels: list[str],
        score: float | None,
        is_toc_like: bool,
        expansion_type: str,
    ) -> PackedContextBlock:
        return PackedContextBlock(
            evidence_index=evidence_index,
            file_id=file_id,
            chunk_ids=chunk_ids,
            source_type=source_type,
            title=title,
            section_title=section_title,
            section_path=section_path,
            content=content,
            channels=channels,
            score=score,
            is_toc_like=is_toc_like,
            expansion_type=expansion_type,
        )

    @staticmethod
    def _find_chunk_by_id(
        chunk_id: uuid.UUID,
        file_chunks: dict[uuid.UUID, dict[int, dict]],
    ) -> dict | None:
        """Search already-fetched chunk rows by primary key id."""
        for f_chunks in file_chunks.values():
            for row in f_chunks.values():
                if row.get("id") == chunk_id:
                    return row
        return None

    def _apply_budget(
        self,
        blocks: list[PackedContextBlock],
        toc_indices: set[int],
    ) -> list[PackedContextBlock]:
        """Trim blocks to fit max_chars / max_blocks budget.

        TOC guard: TOC-like blocks are sorted after non-TOC blocks.
        Within each group, higher score wins.
        """
        # Separate TOC and non-TOC
        toc: list[PackedContextBlock] = []
        non_toc: list[PackedContextBlock] = []
        for b in blocks:
            if b.is_toc_like and self._opts.toc_guard:
                toc.append(b)
            else:
                non_toc.append(b)

        # Sort each group by score descending
        toc.sort(key=lambda b: b.score or 0.0, reverse=True)
        non_toc.sort(key=lambda b: b.score or 0.0, reverse=True)

        # Interleave: non-TOC first, TOC fills remaining budget
        ordered = non_toc + toc

        # Apply block count cap
        ordered = ordered[: self._opts.max_blocks]

        # Apply char budget
        chosen: list[PackedContextBlock] = []
        char_count = 0
        for b in ordered:
            if len(b.content) <= self._opts.max_chars_per_block:
                # Block fits within per-block cap — check total budget
                if char_count + len(b.content) <= self._opts.max_chars:
                    chosen.append(b)
                    char_count += len(b.content)
                elif len(chosen) < self._opts.max_blocks:
                    # Truncate to fit remaining budget
                    truncated = b.model_copy(deep=True)
                    truncated.content = b.content[: self._opts.max_chars - char_count]
                    chosen.append(truncated)
                    char_count = self._opts.max_chars
                    break
            elif len(chosen) < self._opts.max_blocks:
                # Block exceeds per-block cap — truncate to cap
                truncated = b.model_copy(deep=True)
                cap = min(len(b.content), self._opts.max_chars_per_block)
                if char_count + cap <= self._opts.max_chars:
                    truncated.content = b.content[:cap]
                    chosen.append(truncated)
                    char_count += cap
                    if char_count >= self._opts.max_chars:
                        break
        return chosen


# ---------------------------------------------------------------------------
# Stub for Slice 3+ (graph → chunk expansion)
# ---------------------------------------------------------------------------


async def expand_graph_evidence(
    evidence: list[EvidenceItem],
    chunk_repo: ChunkRepositoryInterface,
    tenant_id: uuid.UUID,
    options: ContextPackingOptions,
) -> list[EvidenceItem]:
    """Backward-compatible wrapper for graph source expansion.

    New code should call `ContextPacker.pack()` directly. This helper keeps the
    old extension point importable while delegating the actual graph-to-chunk
    expansion to the packer implementation.
    """
    packer = ContextPacker(chunk_repo, tenant_id, options)
    packed = await packer.pack(evidence)
    return packed.evidence

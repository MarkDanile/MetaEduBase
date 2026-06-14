"""Recursive semantic document chunking — industry best practice approach.

Strategy (inspired by LangChain RecursiveCharacterTextSplitter + Semantic Chunking):
1. Split on paragraph boundaries first (\n\n)
2. For each paragraph, split on sentence-ending punctuation (。！？)
3. Merge sentences into chunks with token-aware sizing
4. If a sentence itself exceeds chunk size, split recursively on clause markers
5. Never end a chunk mid-sentence if it can be avoided

Chunk Size Strategy (TD-051):
- TARGET_CHUNK_CHARS = 500: 500 Chinese characters ≈ 300-500 tokens, aligning with
  RAG best practice of 300-600 token chunks. The 350-499 cluster observed in
  production data (822 of 1551 chunks) is expected — sentences rarely align
  exactly with the target, and we never split mid-sentence.
- CHUNK_HEADROOM = 80: When fewer than 80 chars remain in a chunk, start a new
  chunk rather than risk an underfilled final chunk.
- MIN_CHUNK_CHARS = 80: Chunks smaller than this are merged into the previous
  chunk to avoid noise from tiny fragments.
- MIN_SENTENCES_KEPT = 1: At least one complete sentence is kept together.
  Currently fixed; future versions may use higher values for richer context.
- Neighbor expansion / parent-child chunk: Deferred to a P2 follow-up task.
  The current chunker is single-pass and does not include neighbor packing.

TD-051 AC-4: These parameters are explicitly documented; chunk size is not
changed by this fix — the primary issue was metadata loss, not sizing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.shared.parsing.pdf_parser import ParsedDocument


@dataclass
class Chunk:
    content: str
    section_title: str = ""
    section_path: str = ""
    char_start: int = 0
    char_end: int = 0
    index: int = 0


# Target chunk size in characters (≈300-500 tokens for Chinese)
TARGET_CHUNK_CHARS = 500
# When remaining space in chunk < this, start a new chunk even if current fits
CHUNK_HEADROOM = 80
# Minimum chunk size in characters — smaller chunks are merged with previous
MIN_CHUNK_CHARS = 80
# Minimum sentences to keep together
MIN_SENTENCES_KEPT = 1
# Clause markers — last resort split points (keep these together within sentences)
CLAUSE_MARKERS = '，、；'


def chunk_by_structure(
    parsed: ParsedDocument,
    target_chars: int = TARGET_CHUNK_CHARS,
    section_offset: int = 0,
) -> list[Chunk]:
    """Split document into semantically coherent chunks.

    Never splits mid-sentence when avoidable. Uses recursive splitting:
    paragraphs → sentences → clauses → characters.

    section_offset: absolute character offset of section.content[0] within the
    original full_text. Each section should be processed with its correct
    position so char_start/char_end are globally correct.
    """
    chunks: list[Chunk] = []
    chunk_index = 0
    # TD-054 round 2 fix: 重命名 char_offset → local_offset, 语义改为
    # "已累积的 chunk 实际长度"（绝对偏移 = section_offset + 局部偏移）。
    # 旧 char_offset 在合并分支也 + sent_len + 1, 且 _enforce_size_limit
    # 拆分后未校准, 导致 offset_overlaps 恶化 52.61% → 82.14%。
    local_offset = section_offset

    for section in parsed.sections:
        text = section.content.strip()
        if not text:
            continue

        # Step 1: split into paragraphs (on blank lines)
        paragraphs = _split_paragraphs(text)

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            # Step 2: split paragraph into sentences
            sentences = _split_into_sentences(para)

            # Step 3: accumulate sentences into chunks
            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence:
                    continue

                sent_len = len(sentence)

                if not chunks:
                    # First chunk ever
                    chunks.append(
                        Chunk(
                            content=sentence,
                            section_title=section.title,
                            section_path=section.path,
                            char_start=local_offset,
                            char_end=local_offset + sent_len,
                            index=chunk_index,
                        )
                    )
                    # TD-054 fix: 仅在新建 chunk 时累加真实 chunk 长度,
                    # 去掉 phantom +1 (sentence 间分隔符不固定)
                    local_offset += sent_len
                    chunk_index += 1
                else:
                    last = chunks[-1]
                    last_len = last.char_end - last.char_start

                    if last_len + sent_len + 1 <= target_chars:
                        # Fits in last chunk — merge
                        last.content += "\n" + sentence
                        last.char_end = last.char_start + len(last.content)
                    else:
                        # Doesn't fit — start new chunk
                        # But first: if last chunk is very small AND this sentence
                        # is long, merge them to avoid tiny chunks
                        if last_len < 100 and sent_len > target_chars * 0.8:
                            last.content += "\n" + sentence
                            last.char_end = last.char_start + len(last.content)
                        else:
                            # TD-054 round 2 fix: merge branches (L126 / L133)
                            # update last.char_end but do NOT advance
                            # local_offset. Before creating a new chunk we
                            # must sync local_offset to last.char_end so the
                            # new chunk's char_start is correct (>= last
                            # chunk's actual end). Previously local_offset
                            # stayed at the stale value from when `last` was
                            # first created, causing overlaps when merge
                            # branches fired.
                            local_offset = last.char_end
                            chunks.append(
                                Chunk(
                                    content=sentence,
                                    section_title=section.title,
                                    section_path=section.path,
                                    char_start=local_offset,
                                    char_end=local_offset + sent_len,
                                    index=chunk_index,
                                )
                            )
                            # TD-054 fix: 新建 chunk 时累加真实长度
                            local_offset += sent_len
                            chunk_index += 1

    # Step 4: enforce chunk size hard limit by recursively splitting oversized chunks
    chunks = _enforce_size_limit(chunks, target_chars)

    # Step 5: merge very small chunks with neighbors
    chunks = _merge_small_chunks(chunks, min_size=MIN_CHUNK_CHARS)

    # Step 6: re-index
    for i, c in enumerate(chunks):
        c.index = i

    return chunks


def _split_paragraphs(text: str) -> list[str]:
    """Split text on paragraph boundaries (blank lines)."""
    parts = re.split(r'\n\s*\n', text)
    return [p.strip() for p in parts if p.strip()]


# Sentence-ending punctuation (strongest semantic boundary)
_SENTENCE_END = re.compile(r'[。！？\?!]')
# Clause separators (weaker, within sentences)
_CLAUSE_SEP = re.compile(r'[，、；]')


def _split_into_sentences(text: str) -> list[str]:
    """Split text into sentences, preferring sentence-end boundaries.

    Returns sentences as they appear in text order. Never splits at clause markers
    unless a sentence exceeds the target size.
    """
    sentences: list[str] = []
    current = ""

    i = 0
    n = len(text)

    while i < n:
        ch = text[i]

        # Check for sentence end
        if ch in '。！？?!':
            current += ch
            sentences.append(current)
            current = ""
            i += 1
            continue

        # Check for clause separator (but don't split here, just mark)
        # We'll only split at clause separators if forced by size
        current += ch
        i += 1

    if current.strip():
        sentences.append(current)

    return sentences


def _enforce_size_limit(chunks: list[Chunk], max_chars: int) -> list[Chunk]:
    """Recursively split any chunk that exceeds max_chars at clause/sentence boundaries.

    TD-051: preserves char_start/char_end by passing the absolute offset of the
    original chunk content so that sub-chunks get correct absolute positions.
    """
    result: list[Chunk] = []

    for chunk in chunks:
        if len(chunk.content) <= max_chars:
            result.append(chunk)
            continue

        # Split this oversized chunk — get (text, char_start_in_original) pairs
        sub_chunks = _split_oversized_chunk(chunk.content, max_chars)
        for sub_text, sub_offset in sub_chunks:
            new_chunk = Chunk(
                content=sub_text,
                section_title=chunk.section_title,
                section_path=chunk.section_path,
                char_start=chunk.char_start + sub_offset,
                char_end=chunk.char_start + sub_offset + len(sub_text),
                index=chunk.index,  # will be re-indexed later
            )
            result.append(new_chunk)

    return result


def _split_oversized_chunk(text: str, max_chars: int) -> list[tuple[str, int]]:
    """Split oversized text at clause boundaries first, then sentence boundaries.

    Never splits mid-sentence if avoidable.
    Returns list of (text_piece, char_start_in_original) tuples.
    """
    # First try: split on sentence end
    sentences = _split_into_sentences(text)
    result: list[tuple[str, int]] = []
    current = ""
    current_start = 0
    # Track character position within text as we accumulate sentences
    pos = 0

    for sent in sentences:
        sent_len = len(sent)
        if not current:
            current = sent
            current_start = pos
            pos += sent_len
        elif len(current) + sent_len + 1 <= max_chars:
            current = (current + "\n" + sent).strip()
            # TD-054 round 2 fix: pos is total of individual sentence lengths,
            # but `current` is the merged group. After a merge, advance pos
            # to current_start + len(current) so the next sentence's
            # char_start (via `current_start = pos`) is correct.
            pos = current_start + len(current)
        else:
            result.append((current, current_start))
            if sent_len > max_chars:
                clause_parts = _split_by_clauses(sent, max_chars)
                # TD-054 fix: each clause part gets a distinct
                # char_start, computed by accumulating prior part
                # lengths from the sentence's start position.
                # Previously this branch assigned `pos` to every part,
                # causing multiple sub-pieces to share the same
                # char_start and triggering the offset_overlaps
                # regression in the TD-051 quality report.
                clause_cursor = pos
                for part in clause_parts[:-1]:
                    result.append((part, clause_cursor))
                    clause_cursor += len(part)
                current = clause_parts[-1]
                current_start = clause_cursor
                pos = clause_cursor + len(clause_parts[-1])
            else:
                current = sent
                current_start = pos
                pos += sent_len

    if current.strip():
        result.append((current, current_start))

    # If we still have an oversized chunk, force split by character
    cleaned: list[tuple[str, int]] = []
    for piece, piece_start in result:
        if len(piece) <= max_chars:
            cleaned.append((piece, piece_start))
        else:
            sub = _split_by_characters(piece, max_chars)
            # TD-054 fix: `_split_by_characters` returns substrings
            # with NO separator between them — so accumulate prior
            # lengths WITHOUT the +1 phantom separator. Previously
            # the +1 caused sub-iteration start positions to drift
            # and create overlap.
            sub_cursor = piece_start
            for part in sub:
                cleaned.append((part, sub_cursor))
                sub_cursor += len(part)

    return cleaned


def _split_by_clauses(text: str, max_chars: int) -> list[str]:
    """Split text on clause separators (，、；) without breaking mid-sentence."""
    parts = _CLAUSE_SEP.split(text)
    result: list[str] = []
    current = ""

    for part in parts:
        part = part.strip()
        if not part:
            continue

        if not current:
            current = part
        elif len(current) + len(part) + 1 <= max_chars:
            current += "，" + part
        else:
            result.append(current)
            current = part

    if current.strip():
        result.append(current)

    return result


def _split_by_characters(text: str, max_chars: int) -> list[str]:
    """Last resort: split by character count, preserving complete clause units."""
    # Split at clause separators first
    clauses = _CLAUSE_SEP.split(text)
    result: list[str] = []
    current = ""

    for clause in clauses:
        clause = clause.strip()
        if not clause:
            continue

        if not current:
            current = clause
        elif len(current) + len(clause) + 1 <= max_chars:
            current += "，" + clause
        else:
            if current:
                result.append(current)
            if len(clause) > max_chars:
                for i in range(0, len(clause), max_chars - CHUNK_HEADROOM):
                    result.append(clause[i:i + max_chars - CHUNK_HEADROOM])
                current = ""
            else:
                current = clause

    if current.strip():
        result.append(current)

    return result


def _merge_small_chunks(chunks: list[Chunk], min_size: int) -> list[Chunk]:
    """Merge very small chunks (< min_size chars) with the previous chunk."""
    if not chunks:
        return chunks

    result = [chunks[0]]

    for chunk in chunks[1:]:
        curr_len = len(chunk.content)

        if curr_len < min_size:
            # Too small to be standalone — merge into previous chunk
            last = result[-1]
            merged_content = last.content + "\n" + chunk.content
            last.content = merged_content
            last.section_title = chunk.section_title
            last.char_end = last.char_start + len(merged_content)
        else:
            result.append(chunk)

    return result

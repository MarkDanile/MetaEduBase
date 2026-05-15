"""Recursive semantic document chunking — industry best practice approach.

Strategy (inspired by LangChain RecursiveCharacterTextSplitter + Semantic Chunking):
1. Split on paragraph boundaries first (\n\n)
2. For each paragraph, split on sentence-ending punctuation (。！？)
3. Merge sentences into chunks with token-aware sizing
4. If a sentence itself exceeds chunk size, split recursively on clause markers
5. Never end a chunk mid-sentence if it can be avoided
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
# Minimum sentences to keep together
MIN_SENTENCES_KEPT = 1
# Clause markers — last resort split points (keep these together within sentences)
CLAUSE_MARKERS = '，、；'


def chunk_by_structure(
    parsed: ParsedDocument,
    target_chars: int = TARGET_CHUNK_CHARS,
) -> list[Chunk]:
    """Split document into semantically coherent chunks.

    Never splits mid-sentence when avoidable. Uses recursive splitting:
    paragraphs → sentences → clauses → characters.
    """
    chunks: list[Chunk] = []
    chunk_index = 0
    char_offset = 0

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
                            char_start=char_offset,
                            char_end=char_offset + sent_len,
                            index=chunk_index,
                        )
                    )
                    char_offset += sent_len + 1
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
                            chunks.append(
                                Chunk(
                                    content=sentence,
                                    section_title=section.title,
                                    section_path=section.path,
                                    char_start=char_offset,
                                    char_end=char_offset + sent_len,
                                    index=chunk_index,
                                )
                            )
                            char_offset += sent_len + 1
                            chunk_index += 1

    # Step 4: enforce chunk size hard limit by recursively splitting oversized chunks
    chunks = _enforce_size_limit(chunks, target_chars)

    # Step 5: merge very small chunks with neighbors
    chunks = _merge_small_chunks(chunks, min_size=80)

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
    """Recursively split any chunk that exceeds max_chars at clause/sentence boundaries."""
    result: list[Chunk] = []

    for chunk in chunks:
        if len(chunk.content) <= max_chars:
            result.append(chunk)
            continue

        # Split this oversized chunk
        sub_chunks = _split_oversized_chunk(chunk.content, max_chars)
        for sc in sub_chunks:
            new_chunk = Chunk(
                content=sc,
                section_title=chunk.section_title,
                section_path=chunk.section_path,
                index=chunk.index,  # will be re-indexed later
            )
            result.append(new_chunk)

    return result


def _split_oversized_chunk(text: str, max_chars: int) -> list[str]:
    """Split oversized text at clause boundaries first, then sentence boundaries.

    Never splits mid-sentence if avoidable.
    """
    # First try: split on sentence end
    sentences = _split_into_sentences(text)
    result: list[str] = []
    current = ""

    for sent in sentences:
        if len(current) + len(sent) + 1 <= max_chars:
            current = (current + "\n" + sent).strip()
        else:
            if current:
                result.append(current)
            # If single sentence exceeds max_chars, split on clauses
            if len(sent) > max_chars:
                clause_parts = _split_by_clauses(sent, max_chars)
                result.extend(clause_parts[:-1])
                current = clause_parts[-1]
            else:
                current = sent

    if current.strip():
        result.append(current)

    # If we still have an oversized chunk, force split by character
    cleaned: list[str] = []
    for piece in result:
        if len(piece) <= max_chars:
            cleaned.append(piece)
        else:
            # Force split — this is a last resort
            sub = _split_by_characters(piece, max_chars)
            cleaned.extend(sub)

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
            # Current clause doesn't fit — flush and start new
            if current:
                result.append(current)
            # If single clause exceeds max_chars, force split by characters
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

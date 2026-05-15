"""Structure-aware document chunking."""

from __future__ import annotations

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


MAX_CHUNK_CHARS = 512
OVERLAP_CHARS = 64


def chunk_by_structure(parsed: ParsedDocument, max_chars: int = MAX_CHUNK_CHARS, overlap: int = OVERLAP_CHARS) -> list[Chunk]:
    """Split a parsed document into chunks, respecting section boundaries."""
    chunks: list[Chunk] = []
    char_offset = 0
    chunk_index = 0

    for section in parsed.sections:
        text = section.content.strip()
        if not text:
            continue

        if len(text) <= max_chars:
            chunks.append(Chunk(
                content=text,
                section_title=section.title,
                section_path=section.path,
                char_start=char_offset,
                char_end=char_offset + len(text),
                index=chunk_index,
            ))
            char_offset += len(text) + 1
            chunk_index += 1
        else:
            paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
            sub_chunks = _split_paragraphs(paragraphs, max_chars, overlap)
            for sc in sub_chunks:
                chunks.append(Chunk(
                    content=sc,
                    section_title=section.title,
                    section_path=section.path,
                    char_start=char_offset,
                    char_end=char_offset + len(sc),
                    index=chunk_index,
                ))
                char_offset += len(sc) + 1
                chunk_index += 1

    if not chunks and parsed.full_text.strip():
        for sc in _split_paragraphs([parsed.full_text], max_chars, overlap):
            chunks.append(Chunk(
                content=sc,
                section_title="",
                section_path="",
                char_start=char_offset,
                char_end=char_offset + len(sc),
                index=chunk_index,
            ))
            char_offset += len(sc) + 1
            chunk_index += 1

    return chunks


def _split_paragraphs(paragraphs: list[str], max_chars: int, overlap: int) -> list[str]:
    """Join paragraphs into chunks of max_chars, with overlap."""
    chunks: list[str] = []
    current_parts: list[str] = []
    current_len = 0

    for para in paragraphs:
        if current_len + len(para) + 1 > max_chars and current_parts:
            chunks.append("\n".join(current_parts))
            tail = "\n".join(current_parts)
            overlap_text = tail[-overlap:] if overlap < len(tail) else tail
            current_parts = [overlap_text]
            current_len = len(overlap_text)

        current_parts.append(para)
        current_len += len(para) + 1

    if current_parts:
        chunks.append("\n".join(current_parts))

    return chunks

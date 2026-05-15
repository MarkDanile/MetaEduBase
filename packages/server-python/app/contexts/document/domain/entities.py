"""Document context domain entities and enums."""

from __future__ import annotations

from enum import StrEnum


class FileStatus(StrEnum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class DocumentTaskType(StrEnum):
    PARSE = "parse"
    CHUNK = "chunk"
    EMBED = "embed"
    INDEX_TSV = "index_tsv"
    EXTRACT_TEMPLATE = "extract_template"
    EXTRACT_KG = "extract_kg"


TASK_TYPE_LABELS: dict[str, str] = {
    "parse": "文档解析",
    "chunk": "结构切片",
    "embed": "向量化",
    "index_tsv": "全文索引",
    "extract_template": "模板抽取",
    "extract_kg": "知识图谱",
}

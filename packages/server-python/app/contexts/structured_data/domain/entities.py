"""Structured data context domain entities and enums."""

from __future__ import annotations

from enum import StrEnum


class SourceType(StrEnum):
    FILE = "file"
    DATASET = "dataset"


class DatasetStatus(StrEnum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"


class KgStatus(StrEnum):
    PENDING = "pending"
    BUILDING = "building"
    DONE = "done"
    FAILED = "failed"


DS_TASK_TYPE_LABELS: dict[str, str] = {
    "ds_parse": "数据集解析",
    "ds_embed": "数据向量化",
    "ds_extract_kg": "知识图谱构建",
}

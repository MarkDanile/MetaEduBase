"""Shared dataclasses and path constants for the REQ-024 P2 real validation script.

Split out of the original monolithic `validate_req024_p2_real_validation.py`
(TD-032 slice 8). Holds the dataclasses (Question / Keypoint / Scenario /
ScenarioRun) and the repo path constants + sys.path bootstrap so that `app.*`
imports resolve from `packages/server-python`.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SERVER_PYTHON = REPO_ROOT / "packages" / "server-python"
if str(SERVER_PYTHON) not in sys.path:
    sys.path.insert(0, str(SERVER_PYTHON))

DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000001"
DEFAULT_REQ016_SAMPLES = (
    REPO_ROOT / "tests" / "fixtures" / "rag_validation_samples" / "validate_real_pg_rag_req016.example.json"
)
DEFAULT_REQ018_SAMPLES = (
    REPO_ROOT / "tests" / "fixtures" / "rag_validation_samples" / "validate_real_pg_rag_req018.example.json"
)
DEFAULT_REQ026_SAMPLES = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "rag_validation_samples"
    / "validate_real_pg_rag_req026_weak_recall.example.json"
)
DEFAULT_REQ028_SAMPLES = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "rag_validation_samples"
    / "validate_real_pg_rag_req028_weak_recall_v3.example.json"
)
DEFAULT_OUT = (
    REPO_ROOT
    / "docs"
    / "02-delivery-plans"
    / "01-specs"
    / "2026-06-18-req-024-p2-real-validation-report.md"
)
DEFAULT_REQ026_OUT = (
    REPO_ROOT
    / "docs"
    / "02-delivery-plans"
    / "01-specs"
    / "2026-06-18-req-026-rag-effect-comparison-validation-report.md"
)


@dataclass
class Question:
    group: str
    question_id: str
    text: str
    expected: dict[str, Any]
    expected_keypoints: list["Keypoint"]


@dataclass
class Keypoint:
    term: str
    synonyms: list[str] = field(default_factory=list)
    weight: float = 1.0


@dataclass
class Scenario:
    name: str
    use_hybrid_ner: bool
    use_graph_edge: bool
    rrf_weights: dict[str, float]


@dataclass
class ScenarioRun:
    question_group: str
    question_id: str
    question_text: str
    scenario: str
    query_understanding: dict[str, Any] | None
    retrieval_counts: dict[str, int]
    fusion_topn: list[dict[str, Any]]
    packed_blocks: list[dict[str, Any]]
    prompt_preview: str
    final_answer_preview: str
    document_sources_count: int
    graph_edge_retrieval_count: int
    graph_edge_fusion_count: int
    graph_edge_packed_count: int
    vector_fallback_count: int
    graph_edge_chunk_ids: list[str]
    fusion_chunk_ids: list[str]
    document_sources_titles: list[str]
    keypoint_total: int
    keypoint_hit_count: int
    keypoint_coverage_pct: float
    keypoint_hit_list: list[str]
    # REQ-028: three-metric coverage fields
    keypoint_coverage_pct_substring: float = 0.0
    keypoint_coverage_pct_semantic: float = 0.0
    keypoint_weight_pct_semantic: float = 0.0
    keypoint_llm_judge_pct: float | None = None
    # REQ-030: semantic embedding coverage
    keypoint_semantic_embedding_pct: float = 0.0
    keypoint_semantic_embedding_weight_pct: float = 0.0
    keypoint_semantic_embedding_hit_terms: list[str] = field(default_factory=list)
    # REQ-032: continuous weighted coverage (no threshold binarization)
    keypoint_semantic_embedding_continuous_pct: float = 0.0
    keypoint_hit_list_substring: list[str] = field(default_factory=list)
    keypoint_hit_list_semantic: list[str] = field(default_factory=list)

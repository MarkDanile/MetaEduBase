from __future__ import annotations

from unittest.mock import MagicMock

from app.contexts.knowledge.application.context_packer import ContextPacker
from app.contexts.knowledge.application.evidence_fusion import RRFFusion
from app.contexts.knowledge.interfaces.api.ai_router import _build_evidence_service


def test_default_evidence_service_uses_rrf_and_context_packer() -> None:
    service = _build_evidence_service(
        MagicMock(),
        "11111111-1111-1111-1111-111111111111",
    )

    assert isinstance(service.evidence_fusion, RRFFusion)
    assert isinstance(service._context_packer, ContextPacker)

from typing import get_type_hints

from app.contexts.ai_app.application.service import AiAppService
from app.contexts.ai_app.infrastructure.models import AiApplicationModel


def test_list_published_public_return_annotation_resolves() -> None:
    hints = get_type_hints(AiAppService.list_published_public)

    assert hints["return"] == list[AiApplicationModel]

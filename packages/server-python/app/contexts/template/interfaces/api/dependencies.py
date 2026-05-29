from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.template.application.service import TemplateService
from app.contexts.template.infrastructure.repository import TemplateRepositoryImpl
from app.shared.infrastructure.database import get_session


def get_template_service(
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> TemplateService:
    return TemplateService(TemplateRepositoryImpl(session))

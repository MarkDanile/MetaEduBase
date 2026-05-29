from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.template.application.service import TemplateService
from app.contexts.template.infrastructure.repository import TemplateRepositoryImpl
from app.shared.infrastructure.database import async_session


async def get_template_session() -> AsyncSession:
    async with async_session() as session:
        yield session

def get_template_service(
    session: AsyncSession = Depends(get_template_session),
) -> TemplateService:
    return TemplateService(TemplateRepositoryImpl(session))

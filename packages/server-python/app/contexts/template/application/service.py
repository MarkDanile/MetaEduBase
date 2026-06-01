import json
import logging
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.contexts.template.application.dto import FieldDTO, TemplateCreate, TemplateUpdate
from app.contexts.template.domain.entity import Field, TableColumn, Template
from app.contexts.template.domain.repository import TemplateRepository

logger = logging.getLogger(__name__)


def _dto_to_entity(dto: FieldDTO) -> Field:
    return Field(
        key=dto.key,
        label=dto.label,
        type=dto.type,
        description=dto.description,
        children=[_dto_to_entity(c) for c in dto.children],
        columns=[TableColumn(**c.model_dump()) for c in dto.columns],
        items=[_dto_to_entity(i) for i in dto.items],
    )

def _entity_to_dto(entity: Template) -> dict:
    return {
        "id": str(entity.id),
        "tenant_id": str(entity.tenant_id),
        "name": entity.name,
        "doc_types": entity.doc_types,
        "fields": [f.to_dict() for f in entity.fields],
        "ai_prompt": entity.ai_prompt,
        "ai_context": entity.ai_context,
        "source_file_id": str(entity.source_file_id) if entity.source_file_id else None,
        "created_at": entity.created_at.isoformat(),
        "updated_at": entity.updated_at.isoformat(),
    }

class TemplateService:
    def __init__(self, repo: TemplateRepository):
        self.repo = repo

    async def list(self, tenant_id: UUID) -> list[dict]:
        templates = await self.repo.list(tenant_id)
        return [_entity_to_dto(t) for t in templates]

    async def get(self, template_id: UUID, tenant_id: UUID) -> dict | None:
        template = await self.repo.get(template_id, tenant_id)
        return _entity_to_dto(template) if template else None

    async def create(self, dto: TemplateCreate, tenant_id: UUID) -> dict:
        template = Template(
            id=uuid4(),
            tenant_id=tenant_id,
            name=dto.name,
            doc_types=dto.doc_types,
            fields=[_dto_to_entity(f) for f in dto.fields],
            ai_prompt=dto.ai_prompt,
            ai_context=dto.ai_context,
            source_file_id=UUID(dto.source_file_id) if dto.source_file_id else None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        await self.repo.create(template)
        return _entity_to_dto(template)

    async def update(self, template_id: UUID, dto: TemplateUpdate, tenant_id: UUID) -> dict | None:
        existing = await self.repo.get(template_id, tenant_id)
        if not existing:
            return None
        if dto.name is not None:
            existing.name = dto.name
        if dto.doc_types is not None:
            existing.doc_types = dto.doc_types
        if dto.fields is not None:
            existing.fields = [_dto_to_entity(f) for f in dto.fields]
        if dto.ai_prompt is not None:
            existing.ai_prompt = dto.ai_prompt
        if dto.ai_context is not None:
            existing.ai_context = dto.ai_context
        if dto.source_file_id is not None:
            existing.source_file_id = UUID(dto.source_file_id)
        existing.updated_at = datetime.now(UTC)
        await self.repo.update(existing)
        return _entity_to_dto(existing)

    async def delete(self, template_id: UUID, tenant_id: UUID) -> None:
        await self.repo.delete(template_id, tenant_id)

    async def init_by_ai(
        self, doc_type: str, source_file_id: UUID | None, tenant_id: UUID, ai_context: str | None = None
    ) -> list[dict]:
        """Use LLM to generate field definitions from doc type and optional sample document."""
        # Build context: doc type description + optional file content
        context_parts = [f"文档类型：{doc_type}"]

        if source_file_id:
            from app.contexts.document.infrastructure.file_repository import FileRepository
            from app.shared.infrastructure.database import async_session_factory

            async with async_session_factory() as session:
                file_repo = FileRepository(session)
                file = await file_repo.get(source_file_id)
                if file and file.content:
                    content_snippet = file.content[:6000]
                    context_parts.append(f"\n样例文档内容（前6000字）：\n{content_snippet}")

        user_prompt = (
            "你是一个结构化数据提取专家。你的任务是根据给定的文档类型和样例文档内容，"
            "分析并生成最合适的字段定义列表。\n\n"
            "字段类型说明：\n"
            "- text: 单行文本（用于简短的字符串，如姓名、标题）\n"
            "- textarea: 多行文本（用于长文本段落）\n"
            "- number: 数字（用于数值）\n"
            "- object: 对象组（用于一组相关的字段，可嵌套子字段）\n"
            "- table: 表格（用于结构化的行列数据，需定义列）\n"
            "- array: 数组（用于同类型对象的列表，需定义数组成员模板）\n\n"
            + "\n".join(context_parts) +
            "\n\n请分析以上内容，输出该文档最适合的结构化字段定义。"
            "返回格式为 JSON 数组，每个元素包含：\n"
            "- key: 字段英文键名（使用 snake_case，如 course_name）\n"
            "- label: 字段中文标签（如 课程名称）\n"
            "- type: 字段类型（text/textarea/number/object/table/array）\n"
            "- description: 字段说明（可选）\n"
            "对于 object 类型，需要包含 children 数组（子字段）。\n"
            "对于 table 类型，需要包含 columns 数组（每列有 key、label、type）。\n"
            "对于 array 类型，需要包含 items 数组（数组成员模板，一个 object）。\n\n"
            "只返回 JSON 数组，不要其他文字说明。"
            "确保 JSON 格式正确，可以被 json.loads() 解析。"
        )

        system_prompt = (
            "你是一个专业的教育领域数据提取助手，擅长分析教案、课程标准、试卷等职教文档的结构，"
            "并生成准确的结构化字段定义。你的输出严格是 JSON 数组格式。"
        )
        if ai_context:
            system_prompt += "\n\n补充上下文：" + ai_context

        # Call LLM
        content = await _call_llm(system_prompt, user_prompt)

        # Parse response
        try:
            fields_data = json.loads(content)
            if not isinstance(fields_data, list):
                fields_data = []
        except json.JSONDecodeError:
            logger.warning(f"LLM response is not valid JSON: {content[:200]}")
            fields_data = []

        return fields_data


async def _call_llm(system_prompt: str, user_prompt: str) -> str:
    from app.shared.llm.chat import chat
    try:
        return await chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
            max_tokens=3000,
            timeout=60.0,
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"LLM call failed: {e}")
        return json.dumps(_fallback_fields())


def _fallback_fields() -> list[dict]:
    """Fallback field definitions when LLM is unavailable."""
    return [
        {"key": "title", "label": "标题", "type": "text"},
        {"key": "content", "label": "内容", "type": "textarea"},
    ]

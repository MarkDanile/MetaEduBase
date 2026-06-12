from __future__ import annotations

import copy
import json
import logging
import re
import time
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.contexts.template.application.dto import (
    CloneTemplateRequest,
    FieldDTO,
    ImportTemplateRequest,
    TemplateCreate,
    TemplateUpdate,
)
from app.contexts.template.domain.entity import Field, TableColumn, Template
from app.contexts.template.domain.repository import TemplateRepository
from app.contexts.template.domain.template_version import TemplateVersion
from app.contexts.template.infrastructure.template_version_repository import (
    TemplateVersionRepositoryImpl,
)
from app.shared.llm.chat_with_fallback import chat_with_model_fallback
from app.shared.llm.protocol import ProviderUnavailable

logger = logging.getLogger(__name__)


# REQ-002-4: reserved meta keys (REQ-002-3 contract). Field.key must NOT
# collide with these or downstream `structured_data["template"]` merge
# would shadow extracted field data.
_RESERVED_META_KEYS = frozenset(
    {"id", "version", "layer", "matched_type", "confidence", "reason"}
)
_FIELD_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_CONTAINER_TYPES = frozenset({"object", "table", "array"})
_LEAF_TYPES = frozenset({"text", "textarea", "number"})


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
        # REQ-002-4
        "schema_version": entity.schema_version,
        "is_deprecated": entity.is_deprecated,
        "deprecated_at": entity.deprecated_at.isoformat() if entity.deprecated_at else None,
        "deprecated_reason": entity.deprecated_reason,
    }


def _detect_destructive_changes(
    old_fields: list[dict], new_fields: list[dict]
) -> bool:
    """REQ-002-4 AC-5/6/7: Detect changes that must bump ``schema_version``.

    Returns True if ANY of:
      * any field is deleted (path in old but not in new)
      * any container type changes (object ⇄ table ⇄ array), including
        container ⇄ leaf
      * any leaf field's key is renamed (path differs at any level)

    Position-only reordering (REQ-002-1 drag) is intentionally ignored —
    flattening by path is order-insensitive.
    """

    def _flatten(fields: list[dict], prefix: str = "") -> dict[str, str]:
        out: dict[str, str] = {}
        for f in fields:
            key = f.get("key", "")
            path = f"{prefix}.{key}" if prefix else key
            out[path] = f.get("type", "text")
            children = f.get("children") or []
            if children:
                out.update(_flatten(children, path + ".children"))
            items = f.get("items") or []
            if items:
                out.update(_flatten(items, path + ".items"))
        return out

    old_map = _flatten(old_fields)
    new_map = _flatten(new_fields)

    # 1. Deletion: path in old but missing in new
    if set(old_map) - set(new_map):
        return True

    # 2. Type change: any path with a different type
    for path, old_type in old_map.items():
        new_type = new_map.get(path)
        if new_type is None:
            continue  # already covered as deletion
        if old_type == new_type:
            continue
        # Any type change involving a container is destructive.
        if old_type in _CONTAINER_TYPES or new_type in _CONTAINER_TYPES:
            return True
        # Leaf ⇄ leaf (text/textarea/number) is non-destructive.

    return False


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
        # REQ-002-4: validate field naming before persisting
        self._validate_fields([f.model_dump() for f in dto.fields])
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
            # REQ-002-4 defaults
            schema_version=1,
            is_deprecated=False,
            deprecated_at=None,
            deprecated_reason=None,
        )
        await self.repo.create(template)
        return _entity_to_dto(template)

    async def update(self, template_id: UUID, dto: TemplateUpdate, tenant_id: UUID) -> dict | None:
        existing = await self.repo.get(template_id, tenant_id)
        if not existing:
            return None
        # REQ-002-4: detect destructive field changes BEFORE applying
        # (snapshot is taken from the persisted entity, ignoring position
        # changes from drag-reorder, per AC-4 / spec risk #7).
        if dto.fields is not None:
            old_fields_raw = [f.to_dict() for f in existing.fields]
            new_fields_raw = [f.model_dump() for f in dto.fields]
            is_destructive = _detect_destructive_changes(old_fields_raw, new_fields_raw)
            if is_destructive or dto.force_schema_bump:
                existing.schema_version = (existing.schema_version or 1) + 1
        if dto.name is not None:
            existing.name = dto.name
        if dto.doc_types is not None:
            existing.doc_types = dto.doc_types
        if dto.fields is not None:
            # REQ-002-4: validate field naming + reserved keys (AC-12/13/14)
            self._validate_fields([f.model_dump() for f in dto.fields])
            existing.fields = [_dto_to_entity(f) for f in dto.fields]
        if dto.ai_prompt is not None:
            existing.ai_prompt = dto.ai_prompt
        if dto.ai_context is not None:
            existing.ai_context = dto.ai_context
        if dto.source_file_id is not None:
            existing.source_file_id = UUID(dto.source_file_id)
        existing.updated_at = datetime.now(UTC)
        await self.repo.update(existing)
        # REQ-002-2 AC-3: write version snapshot in same transaction
        # REQ-002-4: snapshot stores the (possibly bumped) schema_version
        await self._write_version_snapshot(existing)
        return _entity_to_dto(existing)

    async def delete(self, template_id: UUID, tenant_id: UUID) -> None:
        await self.repo.delete(template_id, tenant_id)

    # REQ-002-4: deprecation + deconstruction detection
    async def deprecate(self, template_id: UUID, reason: str, tenant_id: UUID) -> dict | None:
        existing = await self.repo.get(template_id, tenant_id)
        if not existing:
            return None
        existing.is_deprecated = True
        existing.deprecated_at = datetime.now(UTC)
        existing.deprecated_reason = reason
        existing.updated_at = datetime.now(UTC)
        await self.repo.update(existing)
        # AC-9: deprecate also writes a version snapshot (REQ-002-2
        # consistency) but does NOT bump schema_version (per spec risk #6
        # — deprecation is a lifecycle event, not a field-shape change).
        await self._write_version_snapshot(existing)
        return _entity_to_dto(existing)

    async def undeprecate(self, template_id: UUID, tenant_id: UUID) -> dict | None:
        existing = await self.repo.get(template_id, tenant_id)
        if not existing:
            return None
        existing.is_deprecated = False
        existing.deprecated_at = None
        existing.deprecated_reason = None
        existing.updated_at = datetime.now(UTC)
        await self.repo.update(existing)
        await self._write_version_snapshot(existing)
        return _entity_to_dto(existing)

    async def list_with_filter(
        self, tenant_id: UUID, include_deprecated: bool = False
    ) -> list[dict]:
        """List templates with optional include_deprecated (AC: list_templates query)."""
        templates = await self.repo.list(tenant_id)
        result = [_entity_to_dto(t) for t in templates]
        if not include_deprecated:
            result = [t for t in result if not t["is_deprecated"]]
        return result

    # REQ-002-2: clone / version / export / import

    @property
    def _session(self) -> AsyncSession:
        """Access the underlying DB session from the repo for version writes."""
        return self.repo.session  # type: ignore[attr-defined]

    async def _write_version_snapshot(self, template: Template) -> None:
        """Write a version snapshot for the template (same transaction)."""
        version_repo = TemplateVersionRepositoryImpl()
        max_ver = await version_repo.max_version_number(self._session, template.id)
        next_version_number = max_ver + 1
        snapshot = TemplateVersion(
            id=uuid4(),
            template_id=template.id,
            tenant_id=template.tenant_id,
            version_number=next_version_number,
            name=template.name,
            doc_types=template.doc_types,
            fields=[f.to_dict() for f in template.fields],
            ai_prompt=template.ai_prompt,
            ai_context=template.ai_context,
            # REQ-002-4: snapshot stores the current schema_version
            schema_version=template.schema_version or 1,
            snapshot_at=datetime.now(UTC),
        )
        await version_repo.create(self._session, snapshot)

    async def clone(
        self, template_id: UUID, dto: CloneTemplateRequest, tenant_id: UUID
    ) -> dict | None:
        """AC-1: Deep copy a template within the same tenant."""
        original = await self.repo.get(template_id, tenant_id)
        if not original:
            return None
        # REQ-002-4: validate cloned fields (in case original accumulated
        # bad keys via older code paths or external import).
        cloned_fields = copy.deepcopy([f.to_dict() for f in original.fields])
        self._validate_fields(cloned_fields)
        cloned = Template(
            id=uuid4(),
            tenant_id=tenant_id,
            name=dto.name,
            doc_types=dto.doc_types,
            fields=[Field.from_dict(f) for f in cloned_fields],
            ai_prompt=original.ai_prompt,
            ai_context=original.ai_context,
            source_file_id=UUID(dto.source_file_id) if dto.source_file_id else None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            # REQ-002-4: clone starts fresh — schema_version resets to 1
            schema_version=1,
            is_deprecated=False,
            deprecated_at=None,
            deprecated_reason=None,
        )
        await self.repo.create(cloned)
        return _entity_to_dto(cloned)

    async def list_versions(
        self, template_id: UUID, tenant_id: UUID, limit: int, offset: int
    ) -> list[dict]:
        """AC-4: List version snapshots (paginated, desc)."""
        version_repo = TemplateVersionRepositoryImpl()
        versions = await version_repo.list(self._session, template_id, tenant_id, limit, offset)
        return [
            {
                "version_number": v.version_number,
                "name": v.name,
                "snapshot_at": v.snapshot_at.isoformat(),
                "schema_version": v.schema_version,
                "doc_types": v.doc_types,
            }
            for v in versions
        ]

    async def get_version(
        self, template_id: UUID, tenant_id: UUID, version_number: int
    ) -> dict | None:
        """AC-4: Get a single version snapshot detail."""
        version_repo = TemplateVersionRepositoryImpl()
        v = await version_repo.get(self._session, template_id, tenant_id, version_number)
        if not v:
            return None
        return {
            "version_number": v.version_number,
            "name": v.name,
            "doc_types": v.doc_types,
            "fields": v.fields,
            "ai_prompt": v.ai_prompt,
            "ai_context": v.ai_context,
            "schema_version": v.schema_version,
            "snapshot_at": v.snapshot_at.isoformat(),
        }

    async def rollback(
        self, template_id: UUID, version_number: int, tenant_id: UUID
    ) -> dict | None:
        """AC-5: Restore template from a version snapshot (writes new version)."""
        version = await self.get_version(template_id, tenant_id, version_number)
        if not version:
            return None
        update_dto = TemplateUpdate(
            name=version["name"],
            doc_types=version["doc_types"],
            fields=version["fields"],
            ai_prompt=version["ai_prompt"],
            ai_context=version["ai_context"],
        )
        return await self.update(template_id, update_dto, tenant_id)

    async def export_template(self, template_id: UUID, tenant_id: UUID) -> dict | None:
        """AC-6/AC-7: Export template as metaedu-template-v1 format."""
        template = await self.repo.get(template_id, tenant_id)
        if not template:
            return None
        return {
            "format": "metaedu-template-v1",
            "template": {
                "name": template.name,
                "doc_types": template.doc_types,
                "fields": [f.to_dict() for f in template.fields],
                "ai_prompt": template.ai_prompt,
                "ai_context": template.ai_context,
            },
            "schema_version": 1,
            "exported_at": datetime.now(UTC).isoformat(),
        }

    async def import_template(self, dto: ImportTemplateRequest, tenant_id: UUID) -> dict:
        """AC-8/AC-9/AC-10: Import template from JSON payload."""
        # AC-8: schema_version compatibility check
        current_schema = 1
        payload_schema = dto.template.get("schema_version", current_schema)
        if payload_schema < current_schema:
            raise ValueError(
                f"Cannot import template with older schema "
                f"(payload={payload_schema}, current={current_schema})"
            )

        # AC-9 / AC-10: field key regex + sibling uniqueness + REQ-002-4
        # reserved-key + recursive validation. _validate_fields already
        # walks children/items, so a single call covers the whole tree.
        self._validate_fields(dto.template.get("fields", []))

        name = dto.name_override or dto.template["name"]
        template = Template(
            id=uuid4(),
            tenant_id=tenant_id,
            name=name,
            doc_types=dto.template.get("doc_types", []),
            fields=[Field.from_dict(f) for f in dto.template.get("fields", [])],
            ai_prompt=dto.template.get("ai_prompt"),
            ai_context=dto.template.get("ai_context"),
            source_file_id=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            # REQ-002-4
            schema_version=1,
            is_deprecated=False,
            deprecated_at=None,
            deprecated_reason=None,
        )
        await self.repo.create(template)
        return _entity_to_dto(template)

    def _validate_fields(self, fields: list, parent_key: str = "") -> None:
        """AC-9 / AC-10 / REQ-002-4 AC-12~AC-14: Recursively validate key
        naming, sibling uniqueness, and reserved-meta-key collision.

        Raises ``ValueError`` on the first violation; router maps to 422.
        """
        seen: set[str] = set()
        for f in fields:
            key = f.get("key", "")
            # REQ-002-4 AC-14: reserved meta key collision must be rejected
            if key in _RESERVED_META_KEYS:
                raise ValueError(
                    f"field key {key!r} is reserved (REQ-002-3 meta key — "
                    f"conflicts with structured_data['template'] merge)"
                )
            # AC-9: snake_case pattern
            if not _FIELD_KEY_RE.match(key):
                raise ValueError(
                    f"field key must match ^[a-z][a-z0-9_]*$ (got {key!r})"
                )
            # AC-10: sibling uniqueness
            if key in seen:
                raise ValueError(
                    f"sibling field keys must be unique (duplicate {key!r})"
                )
            seen.add(key)
            # Recurse into children / items (REQ-002-4 risk #5)
            if f.get("children"):
                self._validate_fields(f["children"], key)
            if f.get("items"):
                self._validate_fields(f["items"], key)

    async def init_by_ai(
        self,
        doc_type: str,
        source_file_id: UUID | None,
        tenant_id: UUID,
        ai_context: str | None = None,
    ) -> list[dict]:
        """Use LLM to generate field definitions from doc type and optional sample document."""
        total_start = time.perf_counter()
        sample_fetch_ms = 0.0
        prompt_build_ms = 0.0
        llm_call_ms = 0.0
        json_parse_ms = 0.0

        # Build context: doc type description + optional file content
        prompt_start = time.perf_counter()
        context_parts = [f"文档类型：{doc_type}"]

        if source_file_id:
            fetch_start = time.perf_counter()
            from app.contexts.document.infrastructure.file_repository import FileRepository
            from app.shared.infrastructure.database import async_session_factory

            async with async_session_factory() as session:
                file_repo = FileRepository(session)
                file = await file_repo.get(source_file_id)
                if file and file.content:
                    content_snippet = file.content[:6000]
                    context_parts.append(f"\n样例文档内容（前6000字）：\n{content_snippet}")
            sample_fetch_ms = (time.perf_counter() - fetch_start) * 1000

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
        prompt_build_ms = (time.perf_counter() - prompt_start) * 1000

        llm_start = time.perf_counter()
        try:
            content = await chat_with_model_fallback(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                fast_provider="deepseek",
                fast_model="deepseek-v4-flash",
                fallback_provider="deepseek",
                fallback_model=settings.deepseek_model,
                temperature=0.7,
                max_tokens=3000,
                timeout=60.0,
            )
        except ProviderUnavailable as e:
            logger.warning(f"LLM call failed after flash→pro fallback: {e}")
            content = json.dumps(_fallback_fields())
        llm_call_ms = (time.perf_counter() - llm_start) * 1000

        parse_start = time.perf_counter()
        try:
            fields_data = json.loads(content)
            if not isinstance(fields_data, list):
                fields_data = []
        except json.JSONDecodeError:
            logger.warning(f"LLM response is not valid JSON: {content[:200]}")
            fields_data = []
        json_parse_ms = (time.perf_counter() - parse_start) * 1000

        total_ms = (time.perf_counter() - total_start) * 1000
        logger.warning(
            "template.init_by_ai timing "
            "doc_type=%r source_file=%s ai_context=%s fields=%d "
            "total=%.1fms fetch=%.1fms prompt=%.1fms llm=%.1fms parse=%.1fms",
            doc_type,
            bool(source_file_id),
            bool(ai_context),
            len(fields_data),
            total_ms,
            sample_fetch_ms,
            prompt_build_ms,
            llm_call_ms,
            json_parse_ms,
        )

        return fields_data


def _fallback_fields() -> list[dict]:
    """Fallback field definitions when LLM is unavailable."""
    return [
        {"key": "title", "label": "标题", "type": "text"},
        {"key": "content", "label": "内容", "type": "textarea"},
    ]

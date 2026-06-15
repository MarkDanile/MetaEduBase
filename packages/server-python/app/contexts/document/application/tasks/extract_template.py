"""`extract_template` Celery task — pipeline step 5 of 6 (教案/教学设计)."""

from __future__ import annotations

import json
import logging
import uuid

from celery import shared_task
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.template.infrastructure.repository import TemplateRepositoryImpl
from app.shared.llm.chat import chat
from app.shared.tasks.lifecycle import (
    _create_task,
    _run_in_session,
    _update_task_status,
)

from .extract_template_prompts import (
    _merge_template_structured_data,
    build_few_shot_examples,
    build_fields_desc,
    try_parse,
)

logger = logging.getLogger("app.contexts.document.application.tasks")


async def _update_files_doc_type(
    session: AsyncSession,
    file_id: uuid.UUID,
    template_obj: object | None,
    matched_type: str,
    layer: str,
) -> None:
    """BUG-005 fix: 回写 files.doc_type + files.template_id.

    在 L1/L2/L3 命中模板时同步回写 files 表的 doc_type + template_id 字段，
    保证 ResourceLibrary doc_type 筛选、跨文件模板统计、evidence_coverage
    `file_metadata` 指标可用。L3(低置信度, template_obj=None) / layer=none
    时跳过——保持 NULL。

    在调用方 UPDATE structured_data 同一事务内调用，确保一致。
    """
    if template_obj is None or layer not in ("L1", "L2", "L3"):
        return
    template_uuid = getattr(template_obj, "id", None)
    if template_uuid is None:
        return
    await session.execute(
        text(
            "UPDATE metaedu.files "
            "SET doc_type = :dt, template_id = :tid "
            "WHERE id = :fid"
        ),
        {
            "dt": matched_type,
            "tid": template_uuid,
            "fid": file_id,
        },
    )


@shared_task(name="extract_template")
def extract_template(file_id_str: str, tenant_id_str: str, pipeline_version: str = ""):
    import asyncio

    file_id = uuid.UUID(file_id_str)
    tenant_id = uuid.UUID(tenant_id_str)

    async def _do(session: AsyncSession):
        task_id = await _create_task(
            session, tenant_id, file_id=file_id, task_type="extract_template"
        )
        await _update_task_status(session, task_id, "running", 0)
        await session.commit()

        try:
            # Note: extract_template skips stale check — it's idempotent and runs at
            # the end of the pipeline. The stale check (comparing updated_at) is
            # unreliable here because upstream tasks (index_tsvector) may have
            # already updated updated_at to mark the pipeline as done.

            # Get chunks content, doc_type, and filename
            result = await session.execute(
                text(
                    "SELECT dc.content, f.doc_type, f.filename "
                    "FROM metaedu.document_chunks dc "
                    "JOIN metaedu.files f ON f.id = dc.file_id "
                    "WHERE dc.file_id = :fid AND dc.tenant_id = :tid "
                    "ORDER BY dc.chunk_index LIMIT 10"
                ),
                {"fid": file_id, "tid": tenant_id},
            )
            rows = result.mappings().all()
            chunks_text = "\n".join(row["content"] for row in rows)
            doc_type = rows[0]["doc_type"] if rows else None
            filename = rows[0]["filename"] if rows else ""

            # 匹配优先级：L1 精确 doc_type → L2 文件名 → L3 AI 置信度
            # 抽到 template_selector.select_template 以便单测与可观测日志
            from app.contexts.document.application.template_selector import (
                select_template,
            )

            all_templates = await TemplateRepositoryImpl(session).list(tenant_id)
            selection = await select_template(
                chunks_text=chunks_text,
                doc_type=doc_type,
                filename=filename or "",
                templates=all_templates,
                ai_chat=lambda prompt: chat(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.0,
                    timeout=30.0,
                ),
            )
            template_obj = selection.template

            if selection.layer == "L1":
                logger.info(
                    "template.select layer=L1 doc_type=%r filename=%r → template=%s id=%s",
                    doc_type, filename, template_obj.name, template_obj.id,
                )
            elif selection.layer == "L2":
                logger.info(
                    "template.select layer=L2 matched_doc_type=%r filename=%r → template=%s id=%s",
                    selection.matched_type, filename, template_obj.name, template_obj.id,
                )
            elif selection.layer == "L3" and template_obj is not None:
                msg = (
                    "template.select layer=L3 matched_doc_type=%r "
                    "confidence=%.2f → template=%s id=%s"
                )
                logger.info(
                    msg,
                    selection.matched_type, selection.confidence,
                    template_obj.name, template_obj.id,
                )
            elif selection.layer == "L3" and selection.confidence is not None:
                msg = (
                    "template.select layer=L3 confidence=%.2f < threshold "
                    "doc_type=%r — using generic"
                )
                logger.info(
                    msg,
                    selection.confidence, selection.matched_type,
                )
            elif selection.layer == "none" and selection.matched_type:
                logger.warning(
                    "template.select layer=none reason=%r doc_type=%r confidence=%.2f",
                    selection.reason, selection.matched_type, selection.confidence or 0.0,
                )
            else:
                logger.warning(
                    "template.select layer=none reason=%r doc_type=%r filename=%r",
                    selection.reason, doc_type, filename,
                )

            # Build prompt: use template.ai_prompt > template.fields > default
            if template_obj and template_obj.ai_prompt:
                prompt_template = template_obj.ai_prompt
            elif template_obj and template_obj.fields:

                fields_dicts = [
                    f.to_dict() if hasattr(f, "to_dict") else f
                    for f in template_obj.fields
                ]
                fields_desc = build_fields_desc(fields_dicts)
                # TD-067: inject few-shot JSON examples for complex schema
                # fields (array[object] / table / object[children]).
                # The LLM already handles simple text/array-of-strings;
                # these examples anchor the harder shapes and prevent
                # silent fallback to "-".
                few_shot = build_few_shot_examples(fields_dicts)
                few_shot_block = f"\n\n{few_shot}" if few_shot else ""
                prompt_template = (
                    f"请严格根据以下字段定义，从文档内容中提取JSON格式的结构化信息：\n"
                    f"字段结构说明：{fields_desc}\n"
                    f"要求：\n"
                    f"1. JSON的key必须与上述字段key完全一致\n"
                    "2. object型字段（如basic_info、teaching_objectives）的"
                    "value必须是嵌套的JSON对象，包含对应的子字段\n"
                    "3. array型字段（如teaching_process）的value必须是JSON数组，"
                    "每个成员是包含子字段的object\n"
                    f"4. table型字段的value必须是JSON数组，每行是一个object\n"
                    f"5. 文档中没有的内容填写\"-\"，只返回JSON不要任何解释\n"
                    f"{few_shot_block}\n\n"
                    f"文档内容：\n{chunks_text[:10000]}"
                )
            else:
                prompt_template = (
                    "请对以下文档内容提取结构化摘要，将所有字段翻译为中文，只返回JSON不要任何解释：\n"
                    "字段：title(中文标题), summary(100字内中文摘要), "
                    "sections[中文章节列表], key_points[中文关键要点], "
                    "keywords[中文关键词最多5个]\n\n"
                    f"内容：\n{chunks_text[:6000]}"
                )

            prompt = prompt_template

            # Use auto-selected provider (deepseek -> minimax -> siliconflow -> dashscope)
            template_data: dict = {}
            try:
                content = await chat(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    timeout=60.0,
                )
                template_data = try_parse(content)
            except Exception as e:
                logger.warning(f"extract_template LLM call failed: {e}")

            if not template_data:
                logger.warning(
                    "extract_template: LLM returned no template data for file=%s (chunks=%d)",
                    file_id, len(rows),
                )

            # Save to file structured_data
            result = await session.execute(
                text("SELECT structured_data FROM metaedu.files WHERE id = :fid"),
                {"fid": file_id},
            )
            existing = result.mappings().first()
            existing_raw = (
                existing["structured_data"]
                if existing and existing["structured_data"]
                else "{}"
            )
            # REQ-002-3: 当命中模板（L1/L2/L3）时构造溯源 meta；layer == "none" 不传
            meta: dict[str, object] | None = None
            if (
                template_obj is not None
                and selection.layer in ("L1", "L2", "L3")
            ):
                meta = {
                    "id": str(template_obj.id),
                    "version": getattr(template_obj, "schema_version", None),
                    "layer": selection.layer,
                    "matched_type": selection.matched_type,
                    "confidence": selection.confidence,
                    "reason": selection.reason,
                }

            existing_data = _merge_template_structured_data(existing_raw, template_data, meta)

            await session.execute(
                text(
                    "UPDATE metaedu.files "
                    "SET structured_data = CAST(:data AS JSONB) "
                    "WHERE id = :fid"
                ),
                {
                    "data": json.dumps(existing_data),
                    "fid": file_id,
                },
            )

            # BUG-005 fix: 回写 files.doc_type + files.template_id
            # (与上方 UPDATE structured_data 同一事务)。
            # L1 / L2 / L3 命中时回写；L3(低置信度, template_obj=None)
            # 或 layer=none 时跳过。
            await _update_files_doc_type(
                session, file_id, template_obj, selection.matched_type, selection.layer
            )

            await _update_task_status(session, task_id, "success", 100)

            # Chain to KG extraction
            from .extract_knowledge_graph import extract_knowledge_graph

            extract_knowledge_graph.delay(file_id_str, tenant_id_str, pipeline_version)

            # TD-061 fix: return the extracted-field count so the
            # outer `asyncio.run(_run_in_session(_do))` call (L231)
            # can propagate the int back to the caller. Same
            # pattern as TD-055/056/057/058/059/060.
            return len(template_data)

        except Exception as e:
            await _update_task_status(session, task_id, "failed", 0, str(e))
            await session.commit()
            raise

    # TD-061 fix: capture asyncio.run's return value.
    return asyncio.run(_run_in_session(_do))

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

import bcrypt
from sqlalchemy import text

from app.config import settings
from app.shared.infrastructure.database import async_session_factory, engine

DEFAULT_TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
DEFAULT_ADMIN_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")


async def seed_default_data() -> None:
    if not settings.allow_default_seed:
        raise RuntimeError("默认开发 seed 需要显式设置 ALLOW_DEFAULT_SEED=true")

    async with async_session_factory() as session:
        result = await session.execute(
            text("SELECT id FROM metaedu.tenants WHERE id = :id"),
            {"id": DEFAULT_TENANT_ID},
        )
        if result.scalar_one_or_none():
            return

        now = datetime.now(UTC).replace(tzinfo=None)
        await session.execute(
            text(
                """
                INSERT INTO metaedu.tenants
                    (id, name, school_name, isolation, is_active, created_at, updated_at)
                VALUES
                    (:id, :name, :school_name, :isolation, true, :now, :now)
                """
            ),
            {
                "id": DEFAULT_TENANT_ID,
                "name": "default",
                "school_name": "默认学校",
                "isolation": "shared",
                "now": now,
            },
        )

        password_hash = bcrypt.hashpw(b"admin123", bcrypt.gensalt()).decode()
        await session.execute(
            text(
                """
                INSERT INTO metaedu.users
                    (
                        id,
                        tenant_id,
                        username,
                        email,
                        password_hash,
                        role,
                        clearance_level,
                        is_active,
                        created_at,
                        updated_at
                    )
                VALUES
                    (
                        :id,
                        :tenant_id,
                        :username,
                        :email,
                        :password_hash,
                        :role,
                        5,
                        true,
                        :now,
                        :now
                    )
                """
            ),
            {
                "id": DEFAULT_ADMIN_ID,
                "tenant_id": DEFAULT_TENANT_ID,
                "username": "admin",
                "email": "admin@metaedu.local",
                "password_hash": password_hash,
                "role": "super_admin",
                "now": now,
            },
        )

        await session.commit()
        print("✅ 种子数据已插入: 默认租户 + admin 用户")

        await seed_ai_applications(session, now)


async def seed_ai_applications(session: Any, now: Any) -> None:
    """Seed APP-001 ~ APP-005 内置应用数据"""
    apps = [
        {
            "id": str(uuid.uuid4()),
            "code": "APP-001",
            "name": "课程能力图谱智能体工具",
            "description": "自动构建、动态管理与智能应用课程能力图谱，支撑个性化学习路径规划和资源推荐。",  # noqa: E501
            "category": "learning",
            "icon": "🗺️",
            "status": "Published",
            "visibility": "internal",
            "entry_type": "internal_route",
            "route_path": "/apps/course-capability-map",
            "config_schema": {"course_id": None, "auto_refresh": False, "max_nodes": 500},
            "required_capabilities": ["RAG", "KG", "document_parsing"],
            "owner": "system",
            "version": "1.0.0",
            "sort_order": 1,
            "tenant_id": str(DEFAULT_TENANT_ID),
            "now": now,
        },
        {
            "id": str(uuid.uuid4()),
            "code": "APP-002",
            "name": "智能预习规划与导学智能体",
            "description": "基于课程能力图谱与学生学情，智能规划预习任务、推送预习资源、诊断预习效果。",  # noqa: E501
            "category": "learning",
            "icon": "📚",
            "status": "Draft",
            "visibility": "internal",
            "entry_type": "internal_route",
            "route_path": "/apps/preview-guide",
            "config_schema": {"prerequisite_depth": 2, "generate_quiz": True},
            "required_capabilities": ["RAG", "KG", "student_profile"],
            "owner": "system",
            "version": "1.0.0",
            "sort_order": 2,
            "tenant_id": str(DEFAULT_TENANT_ID),
            "now": now,
        },
        {
            "id": str(uuid.uuid4()),
            "code": "APP-003",
            "name": "个性化学习资源推荐智能体",
            "description": "基于学生画像与学习情境实现精准资源匹配与智能推送，提升学习资源利用效率。",  # noqa: E501
            "category": "learning",
            "icon": "🎯",
            "status": "Draft",
            "visibility": "internal",
            "entry_type": "internal_route",
            "route_path": "/apps/resource-recommendation",
            "config_schema": {"max_recommendations": 10, "enable_collaborative_filtering": False},
            "required_capabilities": ["RAG", "student_profile", "resource_library"],
            "owner": "system",
            "version": "1.0.0",
            "sort_order": 3,
            "tenant_id": str(DEFAULT_TENANT_ID),
            "now": now,
        },
        {
            "id": str(uuid.uuid4()),
            "code": "APP-004",
            "name": "智能复习规划与巩固智能体",
            "description": "基于遗忘曲线与学习记录，智能规划复习任务、推送巩固内容，实现高效巩固。",
            "category": "learning",
            "icon": "🧠",
            "status": "Draft",
            "visibility": "internal",
            "entry_type": "internal_route",
            "route_path": "/apps/review-planner",
            "config_schema": {"max_review_items": 20, "forgetting_curve_enabled": True},
            "required_capabilities": ["RAG", "learning_records", "quiz"],
            "owner": "system",
            "version": "1.0.0",
            "sort_order": 4,
            "tenant_id": str(DEFAULT_TENANT_ID),
            "now": now,
        },
        {
            "id": str(uuid.uuid4()),
            "code": "APP-005",
            "name": "企业 360 背调工作台",
            "description": "面向园区招商的企业 360 背调：锚定企业主体，整合外部（企查查）+ 内部客户 + 内部问数三类数据，生成企业画像报告与可回溯证据账本。",  # noqa: E501
            "category": "operations",
            "icon": "🔍",
            "status": "Published",
            "visibility": "internal",
            "entry_type": "internal_route",
            "route_path": "/apps/enterprise-360-dd",
            "config_schema": {},
            "required_capabilities": ["MCP", "skill_registry", "structured_query"],
            "owner": "system",
            "version": "1.0.0",
            "sort_order": 5,
            "tenant_id": str(DEFAULT_TENANT_ID),
            "now": now,
        },
    ]
    for app in apps:
        await session.execute(
            text(
                """
                INSERT INTO metaedu.ai_applications
                    (id, code, name, description, category, icon, status, visibility,
                     entry_type, route_path, config_schema, required_capabilities,
                     owner, version, sort_order, tenant_id, created_at, updated_at)
                VALUES
                    (:id, :code, :name, :description, :category, :icon, :status,
                     :visibility, :entry_type, :route_path,
                     (:config_schema)::jsonb, (:required_capabilities)::jsonb,
                     :owner, :version, :sort_order, :tenant_id, :now, :now)
                ON CONFLICT (code) DO NOTHING
                """
            ),
            app,
        )
    await session.commit()
    print("✅ 种子数据已插入: APP-001 ~ APP-005 内置应用")


async def seed_development_database() -> None:
    try:
        await seed_default_data()
    finally:
        await engine.dispose()


def main() -> None:
    asyncio.run(seed_development_database())


if __name__ == "__main__":
    main()

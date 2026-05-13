from __future__ import annotations

import re

from app.shared.domain.ner_pipeline import NERResult  # noqa: I001

_DOMAIN_ALIASES: dict[str, str] = {
    "电子信息": "electronics_info",
    "电子与信息": "electronics_info",
    "电子与信息技术": "electronics_info",
    "智能制造": "smart_manufacturing",
    "智能制造业": "smart_manufacturing",
    "财经商贸": "finance_commerce",
    "财经": "finance_commerce",
    "商贸": "finance_commerce",
    "医药健康": "medical_health",
    "医药": "medical_health",
    "健康": "medical_health",
    "教育与体育": "education_sports",
    "教育体育": "education_sports",
    "教育": "education_sports",
    "体育": "education_sports",
    "土木建筑": "civil_engineering",
    "建筑": "civil_engineering",
    "土木": "civil_engineering",
    "交通运输": "transportation",
    "交通": "transportation",
    "农林牧渔": "agriculture",
    "农业": "agriculture",
    "农林": "agriculture",
    "文化艺术": "art_design",
    "艺术": "art_design",
    "设计": "art_design",
    "艺术设计": "art_design",
    "公共管理": "public_service",
    "公共管理与服务": "public_service",
    "公共事务": "public_service",
}

_LEVEL_KEYWORDS: dict[str, str] = {
    "专业": "professional",
    "专业类": "professional",
    "课程": "course",
    "科目": "course",
    "章节": "chapter",
    "节": "chapter",
    "知识点": "knowledge_point",
    "知识": "knowledge_point",
    "技能点": "skill_point",
    "技能": "skill_point",
    "操作步骤": "operation_step",
    "步骤": "operation_step",
    "实操": "operation_step",
}


def _normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"\s+", "", text)
    subs = [
        ("（", "("), ("）", ")"),
        ("，", ","), ("。", "."),
        ("？", "?"), ("！", "!"),
        ("、", ","),
    ]
    for cn, en in subs:
        text = text.replace(cn, en)
    return text


class RuleBasedNER:
    def __init__(
        self,
        domain_aliases: dict[str, str] | None = None,
        level_keywords: dict[str, str] | None = None,
    ):
        self.domain_aliases = domain_aliases or _DOMAIN_ALIASES
        self.level_keywords = level_keywords or _LEVEL_KEYWORDS

    async def extract(self, query: str) -> NERResult:
        normalized = _normalize(query)
        domains: list[str] = []
        matched_entities: list[str] = []

        for alias, domain_key in self.domain_aliases.items():
            if _normalize(alias) in normalized and domain_key not in domains:
                domains.append(domain_key)
                matched_entities.append(alias)

        levels: list[str] = []
        for keyword, level_key in self.level_keywords.items():
            if _normalize(keyword) in normalized and level_key not in levels:
                levels.append(level_key)
                matched_entities.append(keyword)

        return NERResult(domains=domains, levels=levels, raw_entities=matched_entities)

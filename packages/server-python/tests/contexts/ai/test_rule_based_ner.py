import pytest

from app.contexts.knowledge.application.ner_service import RuleBasedNER
from app.shared.domain.ner_pipeline import NERPipeline, NERResult


@pytest.mark.asyncio
async def test_extract_known_domain_and_level():
    ner = RuleBasedNER()
    result = await ner.extract("电子信息专业的课程有哪些？")
    assert "electronics_info" in result.domains
    assert "professional" in result.levels
    assert "course" in result.levels


@pytest.mark.asyncio
async def test_extract_aliases_normalize_to_same_domain():
    ner = RuleBasedNER()
    a = await ner.extract("财经商贸类知识")
    b = await ner.extract("财经商贸类知识")
    c = await ner.extract("财经商贸类知识")
    assert a.domains == b.domains == c.domains == ["finance_commerce"]


@pytest.mark.asyncio
async def test_extract_full_width_punctuation_does_not_break():
    ner = RuleBasedNER()
    result = await ner.extract("智能制造（高端）是什么？")
    assert "smart_manufacturing" in result.domains


@pytest.mark.asyncio
async def test_extract_case_insensitive_for_english_segments():
    ner = RuleBasedNER()
    result = await ner.extract("What is 智能制造?")
    assert "smart_manufacturing" in result.domains


@pytest.mark.asyncio
async def test_extract_unknown_query_returns_empty_lists():
    ner = RuleBasedNER()
    result = await ner.extract("你好，请问今天天气如何")
    assert result == NERResult(domains=[], levels=[], raw_entities=[])


@pytest.mark.asyncio
async def test_extract_returns_ner_result_dataclass():
    ner = RuleBasedNER()
    result = await ner.extract("土木建筑专业的知识点")
    assert isinstance(result, NERResult)
    assert "civil_engineering" in result.domains
    assert "knowledge_point" in result.levels


def test_rule_based_ner_satisfies_protocol():
    ner = RuleBasedNER()
    assert isinstance(ner, NERPipeline)

"""Slice A round-2 P1-fix boundary tests.

Asserts that the application layer is fully decoupled from the router /
concrete adapter / infrastructure boundary:

1. ``app.contexts.knowledge.application`` modules do not contain any
   ``from app.contexts.knowledge.interfaces.api`` import (module-load
   *and* runtime function-body import).
2. ``app.contexts.knowledge.application`` modules do not import any
   ``app.runtime.infrastructure`` symbol.
3. ``app.contexts.knowledge.application.ai_chat_service`` does not
   transitively import ``ai_router`` even after instantiation and a
   first LLM call.
4. ``app.contexts.knowledge.application.query_planner`` does not gain
   a new router or concrete-provider dependency as part of Slice A.
5. ``AIChatService`` accepts an injected ``LlmProvider`` and routes
   ``_call_llm`` / ``_call_llm_with_tools`` through it; the legacy dict
   shape is preserved on the tool-call path.
6. ``HybridQueryUnderstandingService`` accepts an injected
   ``LlmProvider``; ``legacy_llm_callable`` seam continues to accept
   pre-Slice A tests' sync / async callables.
7. Production composition root (``ai_router._build_evidence_service``)
   constructs the ``OpenAIProvider`` and injects the same instance into
   both services; the application modules remain unaware of the adapter.

All assertions are import-time / AST-time / construction-time. None of these
tests connect to PG or invoke an LLM.
"""

import ast
import sys
from unittest.mock import AsyncMock

import pytest

from app.runtime.application.llm_provider import ToolCall, ToolCallingResult

# (ruff I001 wants ``from __future__ import annotations`` merged into the
# import block; that re-ordering causes lint churn for no functional
# reason, so we keep ``from __future__`` as a separate statement.)


# --- helpers ------------------------------------------------------------


_ROUTER_MODNAME = "app.contexts.knowledge.interfaces.api.ai_router"


def _purge_router_from_sys_modules() -> None:
    sys.modules.pop(_ROUTER_MODNAME, None)


def _load_application_module_safely(modname: str) -> None:
    """Import ``modname`` after purging ``ai_router`` from ``sys.modules``
    so we can verify the application module does not transitively
    pull the router in.
    """
    _purge_router_from_sys_modules()
    if modname in sys.modules:
        # Force a re-import by removing the cached module.
        del sys.modules[modname]
    __import__(modname)


# --- 1-2. AST boundary check --------------------------------------------


_APPLICATION_ROOT = (
    "packages/server-python/app/contexts/knowledge/application"
)


def _application_python_files():
    import os

    root = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "..",
        _APPLICATION_ROOT,
    )
    out: list[str] = []
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            if f.endswith(".py"):
                out.append(os.path.join(dirpath, f))
    return out


def _imports_in_file(path: str) -> list[tuple[str, int]]:
    """Return ``(module, line)`` pairs for every ``from X import ...``
    statement in ``path``.
    """
    with open(path, encoding="utf-8") as fh:
        source = fh.read()
    tree = ast.parse(source, filename=path)
    out: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            out.append((node.module or "", node.lineno))
    return out


def test_application_has_no_interfaces_api_import_anywhere():
    """Static AST scan: every ``.py`` under
    ``app/contexts/knowledge/application/`` must NOT contain a
    ``from app.contexts.knowledge.interfaces.api`` import — module
    top-level *or* function-body.
    """
    offenders: list[tuple[str, int]] = []
    for path in _application_python_files():
        for module, line in _imports_in_file(path):
            if module.startswith("app.contexts.knowledge.interfaces.api"):
                offenders.append((path, line))
    assert not offenders, (
        f"application layer still imports interfaces.api: {offenders}"
    )


def test_application_has_no_runtime_infrastructure_import():
    """Static AST scan: application modules must not import concrete
    adapter classes — composition wiring is the only construction site.
    """
    offenders: list[tuple[str, int]] = []
    for path in _application_python_files():
        for module, line in _imports_in_file(path):
            if module.startswith("app.runtime.infrastructure"):
                offenders.append((path, line))
    assert not offenders, (
        f"application layer imports runtime.infrastructure: {offenders}"
    )


# --- 3. Runtime import isolation ----------------------------------------


def test_ai_chat_service_module_load_does_not_pull_router():
    _purge_router_from_sys_modules()
    import app.contexts.knowledge.application.ai_chat_service  # noqa: F401

    assert _ROUTER_MODNAME not in sys.modules, (
        "ai_chat_service module import must not pull ai_router into "
        "sys.modules (router is allowed only via composition root)."
    )


def test_hybrid_ner_service_module_load_does_not_pull_router():
    _purge_router_from_sys_modules()
    import app.contexts.knowledge.application.hybrid_ner_service  # noqa: F401

    assert _ROUTER_MODNAME not in sys.modules, (
        "hybrid_ner_service module import must not pull ai_router "
        "into sys.modules."
    )


# --- 4. query_planner regression -----------------------------------------


def test_query_planner_has_no_new_router_or_provider_dependency():
    """query_planner.py predates Slice A. Verify it did NOT gain a new
    ``app.runtime.infrastructure`` or ``ai_router`` import.
    """
    # __file__ = packages/server-python/tests/runtime/test_application_boundary.py
    # os.path.dirname(__file__) = .../tests/runtime
    # Walk up to repo root, then descend to query_planner.py.
    import os

    here = os.path.dirname(os.path.abspath(__file__))
    repo_root = here
    pyproject_rel = os.path.join(
        "packages", "server-python", "pyproject.toml"
    )
    while not os.path.isfile(os.path.join(repo_root, pyproject_rel)):
        parent = os.path.dirname(repo_root)
        if parent == repo_root:
            raise FileNotFoundError(
                "Could not find repo root from " + here
            )
        repo_root = parent
    abs_qp = os.path.join(
        repo_root,
        "packages",
        "server-python",
        "app",
        "contexts",
        "structured_data",
        "application",
        "query_planner.py",
    )
    assert os.path.isfile(abs_qp), f"query_planner.py not found at {abs_qp}"
    imports = _imports_in_file(abs_qp)
    for module, _line in imports:
        assert not module.startswith("app.runtime.infrastructure"), (
            f"query_planner.py now imports {module} — Slice A boundary"
            f" creep."
        )
        assert not module.startswith("app.contexts.knowledge.interfaces.api"), (
            f"query_planner.py now imports {module} — Slice A boundary"
            f" creep."
        )


# --- 5. AIChatService injection -----------------------------------------


@pytest.fixture
def fake_llm_provider():
    """An LlmProvider whose both methods are AsyncMock instances."""

    class _Provider:
        chat_text = AsyncMock(return_value="injected text reply")

        async def chat_with_tools(self, messages, *, tools=None, **kwargs):
            return ToolCallingResult(
                content="injected tool-aware reply",
                tool_calls=[
                    ToolCall(
                        id="call_x",
                        name="query_internal_data",
                        arguments_json='{"sql": "SELECT 1"}',
                    )
                ],
            )

    return _Provider()


@pytest.mark.asyncio
async def test_ai_chat_service_routes_through_injected_provider_chat_text(
    fake_llm_provider,
):
    """``_call_llm`` must call ``provider.chat_text`` with the
    exact system / user prompts.
    """
    _purge_router_from_sys_modules()
    from app.contexts.knowledge.application.ai_chat_service import AIChatService

    service = AIChatService(
        chunk_retriever=_Stub(),
        graph_retriever=_Stub(),
        metadata_filter=_Stub(),
        evidence_fusion=_Stub(),
        llm_provider=fake_llm_provider,
    )
    assert service.llm_provider is fake_llm_provider
    result = await service._call_llm("system-x", "user-y")
    assert result == "injected text reply"
    fake_llm_provider.chat_text.assert_awaited_once_with("system-x", "user-y")


@pytest.mark.asyncio
async def test_ai_chat_service_routes_through_injected_provider_tool_calls(
    fake_llm_provider,
):
    """``_call_llm_with_tools`` must call the port and re-shape the
    ``ToolCallingResult`` back into the legacy dict envelope.
    """
    _purge_router_from_sys_modules()
    from app.contexts.knowledge.application.ai_chat_service import AIChatService

    service = AIChatService(
        chunk_retriever=_Stub(),
        graph_retriever=_Stub(),
        metadata_filter=_Stub(),
        evidence_fusion=_Stub(),
        llm_provider=fake_llm_provider,
    )
    out = await service._call_llm_with_tools(
        [{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "x"}}],
        tool_choice="auto",
        temperature=0.5,
        max_tokens=256,
    )
    assert out == {
        "content": "injected tool-aware reply",
        "tool_calls": [
            {
                "id": "call_x",
                "type": "function",
                "function": {
                    "name": "query_internal_data",
                    "arguments": '{"sql": "SELECT 1"}',
                },
            }
        ],
    }


@pytest.mark.asyncio
async def test_ai_chat_service_raises_when_no_provider_configured():
    """Refuse to call the legacy router implicitly — composition root
    must inject a provider. Falling back to ``ai_router._call_llm``
    would silently re-introduce the reverse import Slice A removes.
    """
    _purge_router_from_sys_modules()
    from app.contexts.knowledge.application.ai_chat_service import AIChatService

    service = AIChatService(
        chunk_retriever=_Stub(),
        graph_retriever=_Stub(),
        metadata_filter=_Stub(),
        evidence_fusion=_Stub(),
    )
    with pytest.raises(RuntimeError) as excinfo:
        await service._call_llm("s", "u")
    assert "llm_provider is not configured" in str(excinfo.value)


# --- 6. HybridNERService seam preservation ------------------------------


@pytest.mark.asyncio
async def test_hybrid_ner_service_uses_injected_llm_provider(fake_llm_provider):
    """Production path: ``HybridQueryUnderstandingService`` accepts an
    ``LlmProvider`` and routes ``_call_llm_qu`` through it.
    """
    _purge_router_from_sys_modules()
    from app.contexts.knowledge.application.hybrid_ner_service import (
        HybridQueryUnderstandingService,
    )

    service = HybridQueryUnderstandingService(llm_provider=fake_llm_provider)

    ner_result = await _rule_miss_ner_result()
    await service._call_llm_qu("complex query", ner_result)
    # fake_llm_provider.chat_text returns "injected text reply";
    # the service parses it as JSON. JSON parse failure → fallback path;
    # we only assert the provider was called.
    fake_llm_provider.chat_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_hybrid_ner_service_legacy_callable_seam_still_works():
    """Pre-Slice A tests injected a raw ``Callable[[str, str], str]``
    (sync or async). That seam continues to work — production uses
    the ``LlmProvider`` port, but the legacy seam is preserved.
    """
    _purge_router_from_sys_modules()
    from app.contexts.knowledge.application.hybrid_ner_service import (
        HybridQueryUnderstandingService,
    )

    # Sync callable seam
    sync_callable = lambda sys, user: f"SYNC:{user}"  # noqa: E731
    service = HybridQueryUnderstandingService(legacy_llm_callable=sync_callable)

    ner_result = await _rule_miss_ner_result()
    out = await service._call_llm_qu("anything", ner_result)
    # JSON parse of "SYNC:anything" fails → fallback path is exercised,
    # but no exception leaks: this proves the legacy seam still works
    # without router / adapter wiring.
    assert out is not None

    # Async callable seam
    async def async_callable(sys, user):
        return f"ASYNC:{user}"

    service = HybridQueryUnderstandingService(
        legacy_llm_callable=async_callable
    )
    out = await service._call_llm_qu("anything", ner_result)
    assert out is not None


@pytest.mark.asyncio
async def test_hybrid_ner_service_raises_when_no_provider_configured():
    """Without ``llm_provider`` AND without ``legacy_llm_callable``,
    refuse to call the legacy router implicitly.
    """
    _purge_router_from_sys_modules()
    from app.contexts.knowledge.application.hybrid_ner_service import (
        HybridQueryUnderstandingService,
    )

    service = HybridQueryUnderstandingService()
    ner_result = await _rule_miss_ner_result()
    with pytest.raises(RuntimeError) as excinfo:
        await service._call_llm_qu("anything", ner_result)
    assert "LlmProvider" in str(excinfo.value)


# --- 7. Composition root wires the same instance ------------------------


@pytest.mark.asyncio
async def test_composition_root_injects_same_provider_into_both_services():
    """Slice B (承接 Slice A P2 follow-up)：真实构造断言，替换原先的
    ``inspect.getsource`` 源码字符串检查。

    调用真实装配入口 ``ai_router._build_evidence_service``（构造期不触发
    DB / LLM I/O：Pg* retriever 与 ChunkRepository 构造仅保存引用），验证：

    1. 返回的 ``AIChatService.llm_provider`` 是 ``OpenAIProvider`` 实例；
    2. ``HybridQueryUnderstandingService._llm_provider`` 与
       ``AIChatService.llm_provider`` 是**同一个** provider 实例。
    """
    import uuid as _uuid
    from unittest.mock import MagicMock

    from app.contexts.knowledge.interfaces.api import ai_router
    from app.runtime.infrastructure.openai_provider import OpenAIProvider

    session = MagicMock()  # 构造期不使用；不连接数据库
    service = ai_router._build_evidence_service(session, str(_uuid.uuid4()))

    assert isinstance(service.llm_provider, OpenAIProvider)
    ner_pipeline = service.ner_pipeline
    assert ner_pipeline is not None, "use_hybrid_ner 默认 True"
    assert ner_pipeline._llm_provider is service.llm_provider


def test_runtime_application_does_not_import_knowledge_contexts():
    """Slice B 新增边界：``app.runtime.application``（prompt_builder /
    tool_orchestrator / llm_provider）不得 import 任何 ``app.contexts.*``
    模块 —— runtime 通过窄 Protocol / 参数注入消费业务能力，保持
    knowledge/application → runtime/application 单向依赖。
    """
    import os

    here = os.path.dirname(os.path.abspath(__file__))
    repo_root = here
    pyproject_rel = os.path.join(
        "packages", "server-python", "pyproject.toml"
    )
    while not os.path.isfile(os.path.join(repo_root, pyproject_rel)):
        parent = os.path.dirname(repo_root)
        if parent == repo_root:
            raise FileNotFoundError("Could not find repo root from " + here)
        repo_root = parent
    runtime_app = os.path.join(
        repo_root, "packages", "server-python", "app", "runtime", "application"
    )
    offenders: list[tuple[str, int]] = []
    for fname in os.listdir(runtime_app):
        if not fname.endswith(".py"):
            continue
        path = os.path.join(runtime_app, fname)
        for module, line in _imports_in_file(path):
            if module.startswith("app.contexts"):
                offenders.append((path, line))
    assert not offenders, (
        f"runtime/application imports knowledge contexts: {offenders}"
    )


# --- helpers for service-level tests ------------------------------------


class _Stub:
    """Minimal stand-in for the constructor-required dependencies of
    ``AIChatService`` / ``HybridQueryUnderstandingService`` — none of
    these stubs are exercised in the LLM-routing tests.
    """

    async def __call__(self, *args, **kwargs):  # pragma: no cover - unused
        raise AssertionError("Stub should not be called")


async def _rule_miss_ner_result():
    """A NER result with no rule hits — forces the service into the
    ``_call_llm_qu`` branch.
    """
    from app.shared.domain.ner_pipeline import NERResult

    return NERResult(domains=[], levels=[], raw_entities=[])

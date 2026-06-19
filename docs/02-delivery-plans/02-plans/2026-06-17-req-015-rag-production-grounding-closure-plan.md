# REQ-015 RAG 生产链路 grounding 与真实验收收口 — Plan

Requirement: `docs/01-product-planning/05-requirements/REQ-015-rag-production-grounding-closure.md`
Spec: `docs/02-delivery-plans/01-specs/2026-06-17-req-015-rag-production-grounding-closure.md`
Status: 🟢 Done

## Tasks

| Step | 内容 | 验收 |
|------|------|------|
| 1 | 登记 REQ-015 到 Backlog、P2 Milestone、W25 Iteration、current-work | ✅ 五个事实源指向同一任务，不重复造任务源 |
| 2 | 生产 AI Chat 按请求注入 `ContextPacker` | ✅ 默认 endpoint 不再走无 packer fallback |
| 3 | 默认融合切换 `RRFFusion`，支持 weighted RRF | ✅ 单测覆盖 channel weights |
| 4 | `AIChatService` 返回 diagnostics | ✅ 测试断言 retrieval_topn / fusion_topn / packed_blocks / prompt_preview |
| 5 | `ContextPacker` 按 section_path 拉取同章节 chunk | ✅ 单测证明 section block 来自 repository 查询 |
| 6 | 修正 `validate_real_pg_rag.py` 真库验收契约 | ✅ 脚本与接口字段、鉴权 token、当前 schema、BUG-006/007 复测入口对齐，py_compile 通过 |
| 7 | 补“Python 基本数据类型”行为回归 | ✅ 断言 prompt / diagnostics 中有正文内容；hit block 优先使用 `document_chunks.content` 完整正文，不只测 response shape |
| 8 | 跑验证并同步状态 | ✅ 真 PG 样例、授权 DeepSeek ask、PR #314 merge 和跨事实源同步已完成 |

## Validation Results — 2026-06-17

| Command | Result | Notes |
|---------|--------|-------|
| `packages/server-python/.venv/bin/python -m pytest packages/server-python/tests/contexts/ai/test_ai_chat_router_req015.py packages/server-python/tests/contexts/knowledge/test_evidence_fusion.py packages/server-python/tests/contexts/knowledge/test_context_packer.py packages/server-python/tests/contexts/knowledge/test_ai_chat_service.py -q` | 40 passed | 覆盖 builder 注入、weighted RRF、section expansion、hit block 完整 chunk、diagnostics、Python packed context 回归 |
| `packages/server-python/.venv/bin/python -m py_compile scripts/validate_real_pg_rag.py` | exit 0 | 验收脚本语法通过 |
| `packages/server-python/.venv/bin/python -m ruff check ... scripts/validate_real_pg_rag.py` | exit 0 | 触达后端、测试与验收脚本 ruff 通过 |
| `pnpm --filter @metaedu/web typecheck` | exit 0 | 前端新增 diagnostics 类型兼容 |
| `packages/server-python/.venv/bin/python scripts/validate_real_pg_rag.py report --samples tests/fixtures/rag_validation_samples/validate_real_pg_rag_samples.example.json --out /private/tmp/req015-rag-validation-dry-run-report.md` | exit 0 | 缺环境时生成占位报告并输出 warning |
| `scripts/check-engineering-docs` | exit 0 | engineering docs checks passed |
| `git diff --check` | exit 0 | whitespace clean |
| `packages/server-python/.venv/bin/python -m pytest packages/server-python/tests/contexts/ai/test_ai_chat.py -q` | 5 passed | 允许连接本机 PG 后通过；验证 evidence endpoint 认证与 mock service 兼容 |
| `packages/server-python/.venv/bin/python -m pytest packages/server-python/tests/contexts/knowledge/test_context_packer.py packages/server-python/tests/contexts/knowledge/test_ai_chat_service.py packages/server-python/tests/contexts/knowledge/retrievers/test_pg_chunk_keyword_retriever.py packages/server-python/tests/contexts/knowledge/retrievers/test_pg_chunk_vector_retriever_embedding_fallback.py packages/server-python/tests/contexts/knowledge/test_evidence_fusion.py -q` | 50 passed | BUG-009 聚焦回归：顺序检索、RRF rank 分数保留、lexical supplement 排序、ContextPacker neighbor TOC 识别 |
| `gh pr view 314 --json state,mergeCommit,url` | `MERGED`, merge `4d78667` | BUG-009 / REQ-015 收口 PR 已合并 |

真 PG 样例和完整外部 ask 已执行：完整 ask 在用户明确授权后发送 dev DB 检索切片和 prompt context 给 `DeepSeek / deepseek-v4-pro`，HTTP 200，回答包含基本数据类型列表与引用。

## Validation Plan

- `packages/server-python/.venv/bin/python -m pytest packages/server-python/tests/contexts/knowledge/test_evidence_fusion.py packages/server-python/tests/contexts/knowledge/test_context_packer.py packages/server-python/tests/contexts/knowledge/test_ai_chat_service.py packages/server-python/tests/contexts/ai/test_ai_chat.py -q`
- `scripts/check-engineering-docs`
- `git diff --check`

真 PG 验收需要 dev DB、后端服务、`AI_CHAT_AUTH_TOKEN` 和 LLM key；本 PR 只保证脚本契约可运行，真实执行结果如环境不可用必须记录阻塞。

## Risks

- diagnostics 可能包含 prompt 片段，后续如暴露到生产 UI 需做权限 / 脱敏评估。
- RRF 默认排序可能改变 evidence 顺序；本任务通过测试锁定基础行为，但真实质量仍需样例报告继续观察。
- section metadata 质量仍可能不稳定；packer 必须保留 neighbor fallback。

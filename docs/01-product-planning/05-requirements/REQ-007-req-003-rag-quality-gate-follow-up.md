# REQ-007: 收口 REQ-003 RAG 质量链路验收缺口

Status: Done
Priority: P1
Milestone: P1
Parent: REQ-003
External:

## Problem

REQ-003 已为 P1 RAG 质量链路新增 24 个测试用例，但复核发现部分验收声明强于实际覆盖范围，且 P1 里程碑 / 迭代状态没有完全同步。

本任务只收口 REQ-003 原验收范围内的缺口，不处理已独立入账的 `TD-030` Protocol 签名漂移，也不替代 REQ-006 的真实 PostgreSQL 端到端验收。

## Evidence

- `docs/02-delivery-plans/01-specs/2026-W23-req-003-rag-quality-gate.md` 要求 3 个 `PgXxxRecallChannel` 用 mock `AsyncSession.execute` + fake rows 锁 SQL 路径。
- `packages/server-python/tests/contexts/ai/test_recall_channels_contract.py` 当前只验证 `name`、coroutine 和签名参数，没有验证 fake rows 到 `RecallResult` 的行为。
- `docs/01-product-planning/02-milestones/01-validation-phase.md` 的验证结论存在过度描述：NER 未显式覆盖空字符串；`ai_chat` e2e 未覆盖空召回回退和 LLM 失败兜底文案。
- `docs/01-product-planning/02-milestones/01-validation-phase.md` 和 `docs/01-product-planning/03-iterations/2026-W23-p1-final-gap-closure.md` 仍把 `REQ-003` 标为 `Candidate`，与 Backlog / current-work 的 `Done` 不一致。
- `packages/server-python/tests/contexts/ai/test_ai_chat_rag_e2e.py` 保留未使用 imports / helpers，显示原计划里的 fake row 路径没有落地。

## Scope

- 补 3 个 recall channel 的行为级 mock session 测试：
  - `PgVectorRecallChannel`：mock embedding + fake rows，断言 SQL execute 被调用、参数含 tenant / vector / limit，输出 `RecallResult` 字段正确。
  - `PgKeywordRecallChannel`：fake rows 断言 keyword 参数、score 递减、channel 为 `keyword`。
  - `PgMetadataRecallChannel`：fake rows 断言 domain / level 参数、score 递减、channel 为 `metadata`。
- 修正 P1 milestone、iteration、Backlog、current-work 中对 REQ-003 / REQ-007 的状态和说明。
- 修正过度验证声明：要么补测试，要么把描述改为实际覆盖范围。
- 清理 `test_ai_chat_rag_e2e.py` 中未使用的 import、helper 或无效变量。

## Out of Scope

- 不修改 RAG 业务代码，除非测试揭示真实 bug 且用户确认并入本任务。
- 不处理真实 PostgreSQL 端到端验收；该工作由 REQ-006 承接。
- 不处理 `RecallChannel` Protocol 与具体类签名漂移；该工作由 `TD-030` 承接。

## Acceptance

- AC-1: 3 个 recall channel 均有 fake rows 行为级测试，覆盖 row mapping、score/channel、关键参数和空输入 / 无条件早退路径。
- AC-2: `docs/01-product-planning/02-milestones/01-validation-phase.md` 中 REQ-003 / REQ-007 状态不再与 Backlog、iteration、current-work 冲突。
- AC-3: P1 轨道 B 的验证结论只描述实际测试覆盖；如写"覆盖空召回 / LLM 失败"，必须有对应测试。
- AC-4: REQ-003 相关测试文件无明显未使用 import、未使用 helper 或无效变量。
- AC-5: 验证命令结果被如实记录；当前环境无法连 PostgreSQL 时，不得把 DB 依赖测试写成通过。

## Validation

- `cd packages/server-python && .venv/bin/python -m pytest tests/contexts/ai/test_rule_based_ner.py tests/contexts/ai/test_frequency_fusion.py tests/contexts/ai/test_recall_channels_contract.py tests/contexts/ai/test_ai_chat_rag_e2e.py -q`
- `scripts/check-engineering-docs`
- `git diff --check`

## Delivery Links

- Parent Spec: `docs/02-delivery-plans/01-specs/2026-W23-req-003-rag-quality-gate.md`
- Parent Plan: `docs/02-delivery-plans/02-plans/2026-W23-req-003-rag-quality-gate-plan.md`
- Backlog: `docs/01-product-planning/04-backlog.md`

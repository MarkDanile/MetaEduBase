# 2026-07-15: 近期完成任务 Code Review

Trigger:
- 用户要求按流程对近期完成任务做 Code Review，并与 `review-score-log.md` 对比找出未评审项。

Scope:
- 评分总账最后登记日为 2026-06-18；本轮以 `work-log.md`、`current-work.md` 和已合并 PR 为事实源，覆盖此后所有有业务代码、门禁脚本或复杂验收行为的完成项。
- 按交付主题聚合微 PR，避免对同一条接力链重复评分。
- REQ-052 spec shaping、产业园区应用规划、REQ-055 Idea 登记等 docs-only 规划项不作为 Code Review 对象；REQ-002 closeout 与 W25 closeout 只汇总已评审子任务，也不重复评分。

## 未评审集合

| 批次 | 任务 / PR | 本轮处理 |
|------|-----------|----------|
| AI Chat 用户缺陷 | BUG-016 timeout #388（alias: 历史 BUG-011）/ BUG-012 source link #391 | 完整评分 |
| Embedding 数据修复 | TD-068 / TD-069 #366 | 完整评分 |
| P2 graph_edge 决策 | REQ-028、REQ-030~039、TD-032 slice 8，PR #367~#380 / #384 | 聚合评分 |
| RAG 验收性能 | TD-070~074、REQ-040、AC-4 reports，PR #379 / #386 / #400 / #402 / #404 / #407 / #409 / #411 | 聚合评分 |
| 治理门禁 | DOC-074 / DOC-075 / DOC-076，PR #376 / #394 / #397 | 聚合评分 |
| DB 可靠性 | 两个不同任务都使用历史 BUG-013：#406（保留 BUG-013） / #418（重命名为 BUG-014） | 聚合评分 + 编号治理 |
| 智能问数 | REQ-052 #417 | 完整评分，重新打开 |
| 数据库 Catalog | REQ-054 #421 / #422 / #424 | 完整评分，有条件关闭 |

## Findings

### P0: REQ-052 实际查询忽略用户过滤条件

- `ImportedDatasetAdapter.query()` 当前只按 `tenant_id`、`dataset_id` 和 `limit` 查询 `DatasetRowModel`。
- `JsonbQueryBuilder` 已有过滤、时间范围和 limit 实现，但生产代码没有任何调用；引用只出现在独立单测。
- 结果是“某企业过去三年欠费”等问题可能对整张数据集聚合，返回看似合理但业务上错误的数字。

处理：登记 `REQ-056`，REQ-052 从 Done 重新进入 Doing。

### P0: AI Chat tool calling 只在注入 mock 时成立

- `_build_evidence_service()` 没有传入 `query_service`。
- `/ai/chat/evidence` 调 `service.chat()` 时没有传入认证用户的 `user_id` 和 `role`。
- `AIChatService.chat()` 在 `query_service is None` 时只返回 `query_service not available`，测试则通过 `_make_service(query_service=AsyncMock())` 绕过了生产接线。

处理：`REQ-056` 必须增加 production wiring regression test 和真实 AI Chat 验收。

### P0: 多 Catalog 下 AI Chat 仍是单键路由

- REST 问数 API 已按 `(catalog_id, entity_type)` 双键查语义模型。
- AI Chat tool 路径仍调用已弃用的 `get_active_by_entity_type()`；同 tenant 多 Catalog 同 entity_type 时选择不确定。

处理：并入 `REQ-056`，AI Chat 工具参数或会话上下文必须携带 catalog_id。

### P1: REQ-054 的 DirectDB / MCP Adapter 不可从主链路到达

- `DirectDBAdapter` / `MCPAdapter` 有独立实现和单测。
- `default_adapter_factory()` 仍只支持 imported_dataset；现有 router 测试明确断言 direct_db 返回 400。
- 因此“3 种数据源统一接入 / AC-1~10 全覆盖”的交付描述过满。

处理：登记 `REQ-057`，统一 adapter registry 和能力分层声明。

### P1: REQ-054 entity_type 契约跨事实源漂移

- PR #422 已把上传策略改为自由输入 + 动态发现，代码中的 `validate_entity_type()` 变为 no-op。
- Requirement、Spec、Plan、work-log 仍声明白名单校验和 AC-1 / AC-4 完成。

处理：`REQ-057` 统一动态发现契约，并补两 Catalog 同 entity_type 验收。

### P1: TD-069 backfill 默认分页会跳行

- 脚本用 `WHERE embedding IS NULL ORDER BY ... LIMIT ... OFFSET ...` 取一批后，把该批更新为非 NULL，再递增 OFFSET。
- 下一轮结果集已经缩短，继续 OFFSET 会跳过尚未处理的行；代码没有对应单测。
- PR #366 有 599/599 真 DB 结果，说明当时数据最终已被填满，但不能证明脚本的一次性、幂等实现正确。

处理：登记 `TD-075`，改为 keyset 或不递增 OFFSET 的稳定批处理，并补大于 batch_size 的测试。

### P1: BUG 编号已发生两次碰撞

- 历史 `BUG-011` 同时指“模板 AI 生成 500”（#342，保留 BUG-011）和“AI Chat timeout”（#388，已重命名为 BUG-016）。
- 历史 `BUG-013` 同时指“pgvector cast”（#406，保留 BUG-013）和“DB unavailable 503”（#418，已重命名为 BUG-014）。
- 当前任务 ID 门禁检查 DRAFT / FOLLOWUP / Backlog Done 索引，但不检查 Requirement 文件标题与 work-log 的同 ID 异义。

处理：登记 `DOC-077`，按创建时间保留先占用编号，后创建项重新编号并保留 alias；新增跨事实源唯一性门禁。

### P2: 审计失败降级语义与事务行为不一致

- `QueryService._audit()` 捕获并吞掉 audit flush 异常，随后 `ask()` 继续 `session.commit()`。
- SQLAlchemy flush 失败后 session 通常已进入 failed transaction，后续 commit 仍会失败；“用户响应不受影响”声明不成立。
- 国资场景也不应默认返回无法落审计的敏感结果。

处理：纳入 `REQ-056`，默认采用 fail-closed 并测试事务状态。

## 评分

| 批次 | 范围 /15 | 实现 /20 | 验证 /20 | 流程 /15 | 风险 /15 | 交接 /10 | 改进 /5 | 总分 | 结论 |
|------|----------|----------|----------|----------|----------|----------|---------|------|------|
| BUG-016 timeout + BUG-012 link | 14 | 18 | 18 | 6 | 12 | 9 | 4 | 81 | 功能修复有效；历史 BUG-011 编号碰撞已治理（alias BUG-016）。 |
| TD-068 / TD-069 embedding schema + backfill | 13 | 14 | 13 | 10 | 12 | 8 | 4 | 74 | 真 PG 结果成立，但 backfill 分页实现和 PR 占位需修。 |
| REQ-028 / REQ-030~039 graph_edge 评估决策链 | 14 | 17 | 18 | 12 | 13 | 8 | 4 | 86 | 多口径评估最终支持默认禁用，证据链较完整。 |
| TD-070~074 / REQ-040 / AC-4 性能收口链 | 14 | 18 | 19 | 13 | 13 | 8 | 4 | 89 | 从 50~60min 阻塞推进到真实 10:02，缓存和路由测试充分。 |
| DOC-074~076 治理门禁链 | 14 | 18 | 18 | 12 | 14 | 8 | 4 | 88 | 规则分层和工作台形状门禁有效；任务 ID 唯一性仍有盲区。 |
| BUG-013 cast + BUG-014 DB unavailable | 14 | 17 | 15 | 7 | 12 | 8 | 4 | 77 | 两个修复本身有效；历史编号碰撞已治理，状态/TBD 和空测试拉低可追踪性。 |
| REQ-052 智能问数 | 9 | 10 | 11 | 6 | 9 | 8 | 5 | 58 | 不合格；核心查询与 AI Chat 生产链未闭环，不能维持 Done。 |
| REQ-054 Catalog + #422 / #424 | 11 | 14 | 14 | 8 | 11 | 9 | 5 | 72 | Catalog 骨架可用但有条件关闭；adapter 可达性和契约漂移必须接力。 |

## Follow-up Cards

### REQ-056: 智能问数真实执行闭环与 AI Chat 生产接线

- 状态：🔵 Ready，P0。
- 事实源：`docs/01-product-planning/05-requirements/REQ-056-intelligent-data-query-production-closure.md`。
- 近期优先级最高，先于 REQ-046 使用内部问数能力。

### REQ-057: Catalog 数据源 Adapter 路由与 entity_type 契约收口

- 状态：🟣 Shaping，P1。
- 事实源：`docs/01-product-planning/05-requirements/REQ-057-catalog-adapter-and-entity-contract-closure.md`。
- 不进入当前 3 条候选窗口，先完成契约塑形。

### TD-075: knowledge_nodes embedding backfill 稳定分页

- 状态：⚫ 待办，P1。
- 修复 mutable predicate + OFFSET 跳行，并补大于 batch_size 的回归测试。

### DOC-077: 跨事实源任务编号唯一性与历史碰撞收口

- 状态：🔵 Ready，P0。
- 按创建时间保留历史 BUG-011 / BUG-013 的首次占用（template-init / business-tests），后创建项分配新编号（BUG-016 / BUG-014）；所有旧链接保留 alias 说明。
- 扩展 `scripts/check-engineering-docs`：Requirement 文件名 / H1、Backlog、current-work、work-log、score log 同 ID 不得映射到不同标题。
- 验证必须包含两个不同文件复用同一 BUG ID 的 RED 用例和规范归并后的 GREEN。

## 规则判断

本轮不扩写长规则。现有规则已经明确“任务 ID 稳定”和“效果型任务按最高验证层级关闭”，问题在于两个低成本检查尚未形成闭环：

- 跨 Requirement / 日志的同 ID 异义没有脚本门禁，由 DOC-077 实现。
- REQ-052 说明“AC-7 待真实 e2e”却仍标 Done，说明效果分层规则存在执行偏差；先用 REQ-056 和评分扣分纠正，不继续增加文本规则。

## 本轮验证

- `pnpm --filter @metaedu/web test -- chatError.spec.ts openFileUrl.spec.ts`：11 passed。
- `pytest tests/scripts/rag_validation -q`：50 passed。
- `pytest test_ai_chat_tool_calling.py test_bug013_db_unavailable_handler.py -q`：8 passed；其中 BUG-014（原 BUG-013）的“非 DB 错误仍 500”测试函数仅 `pass`，作为验证扣分记录。
- `pytest tests/engineering -q`：38 passed。
- `scripts/check-engineering-docs`：退出码 0，但未发现重复 BUG ID，印证 DOC-077 门禁缺口。
- 真实 structured_data dev DB e2e：未运行，当前本机 5432 未监听；不得据此关闭 REQ-052 AC-7。

## Git Closeout

- PR：[PR #425](https://github.com/MarkDanile/MetaEduBase/pull/425)，2026-07-15 squash merge。
- Merge commit：`96056855`。
- 仓库未上报 CI checks；合并前本地 `scripts/check-engineering-docs`、38 个 engineering tests 和 `git diff --check` 均通过。

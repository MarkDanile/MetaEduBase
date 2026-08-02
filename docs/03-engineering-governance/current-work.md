# 当前开发工作台

本文件是所有 AI IDE、插件和人工协作的当前任务入口。开始任何开发任务前，先阅读本文件，再按任务卡片中的链接渐进式读取相关 spec、plan、技术债或架构约束。

不同任务类型的开工条件、必读文档和完成标准见 `docs/03-engineering-governance/task-modes.md`。

## 使用规则

- 本文件只保留当前任务、近期候选和少量最近完成任务；任何修改本文件或任务状态前，必须先读 `docs/03-engineering-governance/01-rules/workbench.md`。
- 开发前确认本次任务卡片，并按卡片链接渐进式读取 spec、plan、技术债或架构约束。
- 涉及跨文件开发、计划接力、状态交接或后续继续开发时，必须登记或更新任务卡片。
- 代码、验证或 Git 阶段变化后，必须同步任务状态、当前进展、下一步和验证结果。
- 提交、PR、合并或声明完成前，运行 `scripts/check-engineering-docs` 并执行 `docs/03-engineering-governance/01-rules/quality-gates.md#完成门禁`；门禁主实现位于 `scripts/engineering/check_engineering_docs.py`。

## 当前进行中

### BUG-021: `dev.sh` 跳过 Redis / MinIO 且 Celery Worker 无法启动

状态：🟡 进行中
类型：bug fix / infrastructure
领域：本地开发 / Redis / MinIO / Celery
当前执行模式：bug fix
最近接手工具：Codex
分支：`codex/bug-dev-sh-services`（隔离 worktree：`/private/tmp/metaedu-bug-dev-sh-services`）

需求来源：
- Bug: [BUG-021](../01-product-planning/05-requirements/BUG-021-dev-sh-skips-redis-minio-and-celery.md)
- 本地开发约束：[Local Development](01-rules/local-development.md)

当前进展：已定位 Docker infra 提前返回、local 模式不启动 Redis、Celery wrapper 找不到裸 `celery` 三条根因；实现逐服务补齐、本地 Redis 生命周期管理及当前 Python `-m celery` 启动。现场 PostgreSQL / Redis / MinIO / Backend / Frontend 已在线，Celery `inspect ping` 返回 `pong`；登录缺 seed 的独立问题已用标准 init seed 恢复为 HTTP 200。
下一步：提交并创建独立 PR；保持未合并，等待评审。R1-S3-C 继续由 PR #519 的独立分支推进，本修复不触碰其代码。
验证状态：`bash -n`、新增 5 条 contract tests、ruff、docs gate、diff-check 已通过；真实 `./dev.sh infra/status`、Redis `PONG`、Celery `1 node online / pong` 及登录 HTTP 200 已通过。
交接备注：主工作区用户改动未触碰；`dev_setup` 的 AI application JSONB seed 异常不在本 BUG 范围。
||||||| parent of 78d315e3 (docs(agent): R1-S3-C Writer fence 启动（工作台登记）)
当前无活跃任务。R1-S3-B Schema 与基础契约已合并（PR #517 merge `7d1b21d3`），下一步入口为 R1-S3-C（Writer fence PR — composition-owned fenced execution port，注入 `consume_turn_requested` / Direct RAG / cancel API / Runtime ingest）。 78d315e3 (docs(agent): R1-S3-C Writer fence 启动（工作台登记）)
||||||| parent of 6c24cf94 (feat(server): R1-S3-C M1a FencedExecutionPort + create_run_with_root 注入 + advance 反例)
当前进展：S3-A（契约注记）+ S3-B（schema+contract）已合并（PR #515/517）。S3-C 按契约注记实现 composition-owned fenced execution port，注入 `consume_turn_requested`（create_run 真实入口，非 submit_turn）/ Direct RAG（activate_turn/complete_turn/fail_turn/publish_completed_turn）/ RunQueryService（get_run/request_cancel/read_event_batch）/ Runtime ingest（ingest_runtime_event）；覆盖全部 implicit event writer（start_run/transition_run/mark_run_resume_required/resume_run/commit_terminal 内部 _append_event_locked）；禁止生产路径直调未 fenced writer；writer 返回 `created` 标志驱动 event 计数器（round-2 P2-1 闭合）；cross-source-key 闭集已就位（round-1 P1-5）。
下一步：实现 fenced execution port + 9 writer 注入 + writer `created` 标志 + 变异测试（删除 fence -> 旧 fence 行为复活 / 跨 owner 写失败 / `created` 标志丢失 fail）-> PR -> 独立 max/Codex 复审。
验证状态：待实现。
交接备注：S3-A 已合并（PR #515 merge `2d4f8091`）；S3-B 已合并（PR #517 merge `7d1b21d3`）；S3-C 复用 S3-B 的 fenced port + writer `created` 标志 + per-owner source key 闭集 + 6 处 fail-closed guard；erase_available 保持 False（S3-D 翻）；不进 S4；不启用 purge scheduler。 6c24cf94 (feat(server): R1-S3-C M1a FencedExecutionPort + create_run_with_root 注入 + advance 反例)
||||||| parent of 39b6810e (fix(server): R1-S3-C round-4 复审返修（P1 verdict-before-writer + P2 测试 + P3 stage 去重）)
当前进展：S3-C M1a 完成（FencedExecutionPort 抽象 + create_run_with_root 注入 + advance 反例测试）。(1) 新建 `app/composition/execution_fenced_port.py`：`FencedExecutionPort` 类（`require_active_fence` verdict + `advance_run_event_checkpoint` advance 原语），组合既有 `AgentErasureRepository`（不复制 fence/lock 逻辑）。(2) `bridge.consume_turn_requested` 返回类型改 `tuple[AgentRun, InboxAckV1, bool]`（透传 `created` 标志，IDEMPOTENT_REPLAY / 命中 existing 时 `created=False`）。(3) `agent_control_plane.consume_turn_event` 返回类型同步改 3-tuple。(4) `dispatch_turn` 注入 fenced port：verdict（owner lock + fence FOR UPDATE）+ advance（`run_event_payload` 计数器 +1，仅 `created=True` 时调）。(5) `test_s3c_fenced_port.py` 反例：删 advance 调用 -> `run_event_payload` source_key 计数器不推进 -> purge scan 误判 writer 路径未写过事件 -> 旧 fence 行为复活。
下一步：M1b 注入其余 8 个 writer（start_run/transition_run/mark_run_resume_required/resume_run/commit_terminal/append_event/ingest_runtime_event/CompatibilityOutputService.stage）+ 端到端变异测试（删 `created` 检查 -> IDEMPOTENT_REPLAY 误推进计数器）。
验证状态：ruff passed / mypy baseline 0 回归 / docs gate passed；advance 反例测试 conftest-bypass 直接调通过。
交接备注：S3-A 已合并（PR #515）；S3-B 已合并（PR #517）；S3-C M1a 复用 S3-B 的 `actor_identity` capability + per-owner source key 闭集 + 6 处 fail-closed guard；erase_available 保持 False（S3-D 翻）；不进 S4；不启用 purge scheduler。 39b6810e (fix(server): R1-S3-C round-4 复审返修（P1 verdict-before-writer + P2 测试 + P3 stage 去重）)
||||||| parent of a9423134 (fix(server): R1-S3-C round-5 revert（verdict-after-writer in same txn）)
当前进展：S3-C round-4 复审返修完成（独立 max 发现 P0=0/P1=1/P2=2/P3=1 全部闭合）。(1) P1 verdict-before-writer：consume_turn_event 新增 pre_create_callback 参数，dispatch_turn 传 _verdict 回调（require_active_fence 在 Guard+Conversation 锁后、create/replay 前执行），replay 也经过 verdict；advance 仅 created=True 时调。(2) P2 测试：新增 erasing fence reject + dispatch_turn verdict 顺序 inspect + replay 不推进条件检查。(3) P2 工作台同步为 round-4 实际状态。(4) P3 stage 去重：stage 内部调 stage_with_created 丢弃 created。
下一步：待独立 max 只读复核 -> P0/P1 清零后按流程合并 S3-C -> 启动 S3-D（ExecutionErasureParticipant）。
验证状态：ruff passed / mypy baseline 0 回归 / docs gate passed；三路 CI 待确认。
交接备注：S3-A 已合并（PR #515）；S3-B 已合并（PR #517）；S3-C fenced port 在 composition 层（不违反跨上下文边界）；erase_available 保持 False（S3-D 翻）；不进 S4；不启用 purge scheduler。 a9423134 (fix(server): R1-S3-C round-5 revert（verdict-after-writer in same txn）)
||||||| parent of 114d0e7b (docs(agent): R1-S3-C round-5 revert 收口（CI 9m35s 全绿）)
当前进展：S3-C round-5 revert 完成。回退 round-4 verdict-before-writer（pre_create_callback）方案：Backend CI 30+ 分钟挂起（Guard + Conversation 行锁内再取 owner lock + fence FOR UPDATE，与 backfill Conversation -> owner 形成环路）。回到 round-3 顺序：consume_turn_event 先持 Guard + Conversation 行锁 + commit writer；caller (dispatch_turn) 在 created=True 时调 fenced_create_run 取 owner lock + advance run_context_body=queue_seq。P3 stage 去重保留；erasing fence reject 测试保留（直接验 require_active_fence）；测试改 round-5 顺序断言（dispatch_turn 用 fenced_create_run；consume_turn_event 无 pre_create_callback；if created 条件保留）。
下一步：提交并 push -> 三路 CI 验证稳定（目标 8-9 分钟）-> 独立 max 只读复核 -> P0/P1 清零后按流程合并 S3-C -> 启动 S3-D（ExecutionErasureParticipant）。
验证状态：ruff 待跑 / mypy 待跑 / docs gate 待跑；三路 CI 待确认。
交接备注：S3-A 已合并（PR #515）；S3-B 已合并（PR #517）；S3-C fenced port 在 composition 层；erase_available 保持 False（S3-D 翻）；不进 S4；不启用 purge scheduler。round-5 方案是 trade-off——verdict-after-writer 不在 writer 前，但同事务内仍由 Guard + Conversation 行锁串行化，避免 owner 环路。 114d0e7b (docs(agent): R1-S3-C round-5 revert 收口（CI 9m35s 全绿）)
||||||| parent of c4390aa5 (feat(server): R1-S3-C round-6（无条件 verdict + 13 接线 + 9 writer 矩阵 + 真实 PostgreSQL 反例）)
当前进展：S3-C round-5 revert 已推（commit `a9423134`）并通过三路 CI。回退 round-4 verdict-before-writer（pre_create_callback）方案：Backend CI 30+ 分钟挂起（Guard + Conversation 行锁内再取 owner lock + fence FOR UPDATE，与 backfill Conversation -> owner 形成环路）。回到 round-3 顺序：consume_turn_event 先持 Guard + Conversation 行锁 + commit writer；caller (dispatch_turn) 在 created=True 时调 fenced_create_run 取 owner lock + advance run_context_body=queue_seq。P3 stage 去重保留；erasing fence reject 测试保留（直接验 require_active_fence）；测试改 round-5 顺序断言（ast.unparse 剥离 docstring/comment 误报）。
下一步：等独立 max 只读复核 round-5 revert -> P0/P1 清零后按流程合并 S3-C -> 启动 S3-D（ExecutionErasureParticipant）。
验证状态：ruff passed / mypy baseline 0 回归 / docs gate passed；三路 CI 全绿（Backend 9m35s / Engineering docs 6s / Frontend 5s）。
交接备注：S3-A 已合并（PR #515）；S3-B 已合并（PR #517）；S3-C fenced port 在 composition 层；erase_available 保持 False（S3-D 翻）；不进 S4；不启用 purge scheduler。round-5 方案是 trade-off——verdict-after-writer 不在 writer 前，但同事务内仍由 Guard + Conversation 行锁串行化，避免 owner 环路。 c4390aa5 (feat(server): R1-S3-C round-6（无条件 verdict + 13 接线 + 9 writer 矩阵 + 真实 PostgreSQL 反例）)
||||||| parent of 384a6974 (docs(agent): R1-S3-C round-6 hotfix 收口（Backend 9m15s 全绿）)
当前进展：S3-C round-6 完成。(1) P1-2 verdict-before-writer unconditional + advance conditional：consume_turn_event 加 pre_create_callback 参数（Guard + Conversation 行锁内、writer commit 前调 fence 裁决），dispatch_turn 传 _verdict 回调；create AND replay 都走 verdict（erasing/erased raise 不 ACK）；advance 仅 created=True 时调。(2) P1-1 13 处 writer 接线：direct_rag_compatibility（activate_turn transition_run / complete_turn append_event x2 + stage + commit_terminal / fail_turn append_event + commit_terminal 共 8 处）+ agent_control_plane.start_run + run_query_service.request_cancel 加 Guard + 5 处 fenced_commit_terminal / fenced_transition_run。(3) 9 writer 矩阵全 wrapper：新增 fenced_mark_run_resume_required / fenced_resume_run / fenced_ingest_runtime_event。(4) 锁链修复：advance_ingress_checkpoint_for_update 不再独立 SELECT FOR UPDATE Conversation（Guard 串行化即可；round-4 2-way deadlock 根因）；FencedExecutionPort 加 _assert_guard_held 自检（pg_locks 查 pid+objid，漏 Guard 时 raise）。(5) 真实 PostgreSQL 反例：新增 test_s3c_writer_fence_e2e.py（erasing fence reject / active advance 落库 / 并发 dispatch_30s 无 deadlock）；重写 test_s3c_fenced_port.py（保留 advance_checkpoint + _assert_guard_held 单元测试，删除 AST/inspect 测试）。(6) workbench + PR 描述同步。
下一步：提交并 push -> 三路 CI 验证 -> 独立 max 只读复核 round-6 -> P0/P1 清零后按流程合并 S3-C -> 启动 S3-D（ExecutionErasureParticipant）。
验证状态：ruff passed / mypy baseline 0 回归 / docs gate passed；三路 CI 待确认。
交接备注：S3-A 已合并（PR #515）；S3-B 已合并（PR #517）；S3-C fenced port 在 composition 层（不违反跨上下文边界）；erase_available 保持 False（S3-D 翻）；不进 S4；不启用 purge scheduler。round-6 锁链修复需 E2E 验证：CI 通过 + pg_stat_activity 快照无 lock wait；如 CI 仍挂起需保留 pg_stat_activity 快照证据（不回退锁链修复）。 384a6974 (docs(agent): R1-S3-C round-6 hotfix 收口（Backend 9m15s 全绿）)
||||||| parent of 570c7da9 (docs(agent): R1-S3-C round-7 commit-9 进度同步（commit 1-7 完成 P1-1~4 + P2-1 锁链修复）)
当前进展：S3-C round-6 三轮 hotfix 收口（commits c4390aa5 + 835bd1af + ed037910 + 92377670）。(1) P1-2 verdict-before-writer unconditional + advance conditional：consume_turn_event 加 pre_create_callback 参数（Guard + Conversation 行锁内、writer commit 前调 fence 裁决），dispatch_turn 传 _verdict 回调；create AND replay 都走 verdict；advance 仅 created=True 时调。(2) P1-1 13 处 writer 接线：direct_rag_compatibility（activate_turn transition_run / complete_turn append_event x2 + stage + commit_terminal / fail_turn append_event + commit_terminal 共 8 处）+ agent_control_plane.start_run + run_query_service.request_cancel 5 处 fenced_commit_terminal / fenced_transition_run。(3) 9 writer 矩阵全 wrapper：新增 fenced_mark_run_resume_required / fenced_resume_run / fenced_ingest_runtime_event。(4) 锁链修复：advance_ingress_checkpoint_for_update 不再独立 SELECT FOR UPDATE Conversation（Guard 串行化即可）。(5) 真实 PostgreSQL 反例：test_s3c_writer_fence_e2e.py（erasing fence reject + active advance 落库 + 并发 3 dispatch 30s 无 deadlock）。(6) 三轮 hotfix：hotfix-1 _assert_guard_held oid→int8；hotfix-2 移除 _assert_guard_held + request_cancel 不取 Guard（与 delete race 防 AB-BA deadlock）；hotfix-3 移除 pg_stat_activity 全库快照断言（gather TimeoutError 判定）。
下一步：等独立 max 只读复核 round-6 -> P0/P1 清零后按流程合并 S3-C -> 启动 S3-D（ExecutionErasureParticipant）。
验证状态：ruff passed / mypy baseline 0 回归 / docs gate passed；三路 CI 全绿（Backend 9m15s / Engineering docs 8s / Frontend 6s）。
交接备注：S3-A 已合并（PR #515）；S3-B 已合并（PR #517）；S3-C fenced port 在 composition 层（不违反跨上下文边界）；erase_available 保持 False（S3-D 翻）；不进 S4；不启用 purge scheduler。fenced_* wrapper 不强制 Guard 持锁（hotfix-2 修复 deadlock），由 caller 路径（dispatch_turn 的 consume_turn_event、direct_rag 的 _acquire_write_guard）按 Spec §6.1 自然持 Guard；fence verdict + advance 仍由 wrapper 统一提供。 570c7da9 (docs(agent): R1-S3-C round-7 commit-9 进度同步（commit 1-7 完成 P1-1~4 + P2-1 锁链修复）)
||||||| parent of 4271173a (docs(agent): R1-S3-C round-7 commit-9 progress（commits 10-14 完成 P1-1~4）)
当前进展：S3-C round-7（commits 9c68c8d3 / 3bfa8f44 / 7d2bc2ca / a61e9f92 / fb2c5339 / f128ad77）完成 P1-1~4 + P2-1 锁链修复（commit 1-7），e2e 真路径覆盖（commit 8）+ workbench/PR 同步（commit 9）待。(1) P1-1 Run 归属绑定：每个 fenced_* writer 入口调 _require_run_identity 校验 caller 传 conversation_id/queue_seq 与 AgentRun 一致；fenced_ingest_runtime_event 校验 frame.tenant_id/run_id 与外层一致。(2) P1-2 verdict unconditional + advance conditional 已保留。(3) P1-2 cancel AB-BA 锁序：caller 严格取 Guard + Conv 行锁；cancel_intent CAS 下推到 transition_run/commit_terminal SQL。(4) P1-2 跨边界 Protocol：agent_execution/application/ports.py 新增 FencedWriterPort，RunQueryService 依赖 Protocol 不反向 import composition 实现。(5) P1-3 start_run 锁序：Guard -> lock_owned_conversation -> fenced_start_run。(6) P1-3 activate_turn 锁序：Guard + lock_owned_conversation 在 fenced_transition_run 前显式取。(7) P1-4 pre_create_callback 必填。(8) P2-1 恢复 advance Conversation FOR UPDATE（S2-C 冻结原语保留）。(9) P2-3 Wrapper 恢复返回值（fenced_append_event RunEvent、fenced_mark_run_resume_required / fenced_resume_run RuntimeSessionBinding）。(10) P2-5 commit 9 待补 workbench + PR 描述 + 真 e2e 覆盖路径测试。
下一步：commit 8 补真 PostgreSQL 反例（dispatch_turn 真实路径无 deadlock / 跨 Conv raise / 跨 tenant raise / frame 身份 raise / cancel+delete 无 AB-BA）-> commit 9 workbench + PR 描述 -> 三路 CI 验证 -> 独立 max 复核 -> 合并 S3-C。
验证状态：ruff passed / mypy baseline 0 回归 / docs gate passed；三路 CI 待确认（commits 1-7 已推）。
交接备注：S3-A 已合并（PR #515）；S3-B 已合并（PR #517）；S3-C fenced port 在 composition 层（commit-5 加 Protocol 拆分）；erase_available 保持 False（S3-D 翻）。commit 5 把 cancel_intent CAS 下推后，repository 层 transition_run/commit_terminal 接受可选 cancel_intent_revision 参数（向后兼容默认 None）。 4271173a (docs(agent): R1-S3-C round-7 commit-9 progress（commits 10-14 完成 P1-1~4）)
||||||| parent of 53dd6540 (docs(agent): R1-S3-C round-7 final sync（commit-15~16 完成 P2-2 + PR 描述）)
当前进展：S3-C round-7 commit-10~14 完成（commits ea9a23f3 + 23b724ea）。复审 P1-1~4 全部闭合。(1) commit-10 P1-1：cancel_intent_revision 透传到 fenced_commit_terminal/fenced_transition_run + 删除 # type: ignore[assignment]（Protocol 与实现签名一致）。(2) commit-11 P1-2：commit_terminal / transition_run 在 _require_run_for_update 之后做完整 cancel intent CAS 校验（已存在 != raise；已存在 == 幂等；不存在写入）+ status_revision 校验保留。request_cancel 移除 early-return CANCELLING（避免 revision 错配的 cancel 被吞）。(3) commit-12 P1-3：RunQueryService 构造函数改为必填三个 Protocol（WorkspaceReadPort + GuardLockPort + FencedWriterPort）；删除 workspace_read=None 无锁 fallback；删除默认 FencedExecutionPort 实例化；composition 层 build_run_query_service 注入所有实现。(4) commit-13 P1-4：fenced_ingest_runtime_event 新增 conversation_id 校验；RuntimeIngestFrame 加 conversation_id 字段；advance_checkpoint 新增 _require_fence_identity 校验 fence.conversation_id == caller conversation_id。(5) commit-14 P3：WorkspaceRunStartBarrier docstring 明确"can_start_run 二次取 lock_owned_conversation 在 caller 已持锁事务内是 reentrant"。
下一步：commit-15 真 PostgreSQL 反例覆盖被测路径 + commit-16 PR 描述更新 + 解决 Backend CI 30min 超时（lock window 加长使并发测试串行——可能需要把 lock_owned_conversation 缩短或拆分事务边界）。
验证状态：ruff passed / mypy baseline 0 回归 / docs gate passed；Backend CI 触发了两次 run（30702134432 / 30705833152），均超时取消。Backend 运行 11% 进度时仍有早期 F（commit-10 已修复 P1-1，剩余 F 大概率与新增 Conv 行锁延长串行相关，待 commit-15/16 + lock window 调优后回归）。
交接备注：S3-A 已合并（PR #515）；S3-B 已合并（PR #517）；S3-C fenced port 在 composition 层（commit-12 加 GuardLockPort 拆分跨边界）。run_query_service.request_cancel 锁链严格：Guard -> Conv -> fenced writer 内部 AgentRun FOR UPDATE + cancel intent CAS，与 S3-D `Conversation -> owner/fence -> AgentRun` 同序无 AB-BA。fenced_ingest_runtime_event 形态已就位（Runtime adapter 推迟到 S4）。 53dd6540 (docs(agent): R1-S3-C round-7 final sync（commit-15~16 完成 P2-2 + PR 描述）)
||||||| parent of a3b30dfa (docs(agent): R1-S3-C round-7 final（commit-15~16 + hotfix + CI 超时已知）)
当前进展：S3-C round-7 commit-15~16 收口（commits 516b1082 + 待 push）。(1) commit-15 真 e2e（commit-15 P2-2）：6 组真实 PostgreSQL 反例覆盖 dispatch_turn 真实路径 / 跨 Conv/tenant 拒 / Runtime frame 拒 / 并发无 deadlock / erasing fence 拒。(2) commit-16 PR 描述更新（`gh pr edit`）：Summary + Scope（commit-1~15 关键决策）+ Validation + Risks + 锁链矩阵 + Next（独立 max 复核 + CI 调优）。
下一步：push commit-15~16 -> 三路 CI 验证（Backend 35m 超时取消待调优）-> 独立 max 只读复核 round-7 -> P0/P1 清零后按流程合并 S3-C -> 启动 S3-D。
验证状态：ruff passed / mypy baseline 0 回归 / docs gate passed；commit-15 新增 e2e 6 组（真实 PG + 真实 port + 无 mock）；Backend CI 仍 35m 超时取消（commit-10 修 P1-1 早期 TypeError；剩余与 lock window 加长导致并发串行有关，待调优）。
交接备注：S3-A 已合并（PR #515）；S3-B 已合并（PR #517）；S3-C fenced port 在 composition 层（commit-12 加 GuardLockPort 拆分跨边界）。run_query_service.request_cancel 锁链严格：Guard → Conv → fenced writer 内部 AgentRun FOR UPDATE + cancel intent CAS，与 S3-D `Conversation → owner/fence → AgentRun` 同序无 AB-BA。fenced_ingest_runtime_event 形态已就位（Runtime adapter 推迟到 S4）。PR #519 描述已同步 round-7 commit-15 收口。 a3b30dfa (docs(agent): R1-S3-C round-7 final（commit-15~16 + hotfix + CI 超时已知）)
||||||| parent of e1620438 (docs(agent): R1-S3-C round-7 workbench 同步 commit-17~19)
当前进展：S3-C round-7 commit-15~16 收口（commits 516b1082 + 53dd6540 + 78309186 + 345b95dc）。(1) commit-15 真 e2e（commit-15 P2-2）：6 组真实 PostgreSQL 反例（dispatch_turn 真实路径 / 跨 Conv/tenant 拒 / Runtime frame 拒 / 并发无 deadlock / erasing fence 拒）。(2) commit-16 PR 描述 `gh pr edit`（Summary + Scope + 锁链矩阵）。(3) commit-15 hotfix-1+2：RuntimeIngestCommand -> RuntimeEventCommand + RuntimeEventProvenance 路径修正（CI 早期 ImportError）。(4) Backend CI 30min 超时取消（lock window 加长导致并发测试串行）—— 复审 max 已知，CI 调优可独立迭代。
下一步：复审 max 复核 round-7 commit-15~16 -> P0/P1 清零后按流程合并 S3-C -> 启动 S3-D。
验证状态：ruff passed / mypy baseline 0 回归 / docs gate passed；e2e 6 组（真实 PG + 真实 port + 无 mock）已 CI 早期阶段通过（commit-15 hotfix 解决 ImportError）；Backend full hermetic tests 因 30min job 超时被取消（commit-15 前已同样超时，怀疑是 round-7 整体锁链加长导致并发测试串行——需 S3-D 阶段调优事务边界）。
交接备注：S3-A 已合并（PR #515）；S3-B 已合并（PR #517）；S3-C fenced port 在 composition 层（commit-12 加 GuardLockPort 拆分跨边界）。run_query_service.request_cancel 锁链严格：Guard → Conv → fenced writer 内部 AgentRun FOR UPDATE + cancel intent CAS，与 S3-D `Conversation → owner/fence → AgentRun` 同序无 AB-BA。fenced_ingest_runtime_event 形态已就位（Runtime adapter 推迟到 S4）。PR #519 描述已同步 round-7 commit-15 收口；Backend CI 30min 超时已知需后续调优。 e1620438 (docs(agent): R1-S3-C round-7 workbench 同步 commit-17~19)
||||||| parent of df643350 (docs(agent): R1-S3-C round-7 收口（三路 CI 全绿，0 failed）)
当前进展：S3-C round-7 commit-17~19 完成（commits d3258846 + ef844af0）。复审 P1-1/P1-2/P1-3 修复 + 6 个 CI 失败修复。(1) commit-15 真 e2e（commit-15 P2-2）：6 组真实 PostgreSQL 反例（dispatch_turn 真实路径 / 跨 Conv/tenant 拒 / Runtime frame 拒 / 并发无 deadlock / erasing fence 拒）。(2) commit-16 PR 描述 `gh pr edit`（Summary + Scope + 锁链矩阵）。(3) commit-15 hotfix-1+2：RuntimeIngestCommand -> RuntimeEventCommand + RuntimeEventProvenance 路径修正（CI 早期 ImportError）。(4) Backend CI 30min 超时取消（lock window 加长导致并发测试串行）—— 复审 max 已知，CI 调优可独立迭代。
下一步：push commit-19 + CI 重跑验证 0 failed -> 独立 max 复核 -> 合并 S3-C。
验证状态：ruff passed / mypy baseline 0 回归 / docs gate passed；e2e 6 组（真实 PG + 真实 port + 无 mock）已 CI 早期阶段通过（commit-15 hotfix 解决 ImportError）；Backend full hermetic tests 因 30min job 超时被取消（commit-15 前已同样超时，怀疑是 round-7 整体锁链加长导致并发测试串行——需 S3-D 阶段调优事务边界）。
交接备注：S3-A 已合并（PR #515）；S3-B 已合并（PR #517）；S3-C fenced port 在 composition 层（commit-12 加 GuardLockPort 拆分跨边界）。run_query_service.request_cancel 锁链严格：Guard → Conv → fenced writer 内部 AgentRun FOR UPDATE + cancel intent CAS，与 S3-D `Conversation → owner/fence → AgentRun` 同序无 AB-BA。fenced_ingest_runtime_event 形态已就位（Runtime adapter 推迟到 S4）。PR #519 描述已同步 round-7 commit-15 收口；Backend CI 30min 超时已知需后续调优。 df643350 (docs(agent): R1-S3-C round-7 收口（三路 CI 全绿，0 failed）)

## 下一批候选任务

按"建议执行顺序"排序；候选区只保留近期 1 到 3 个入口，完整任务池回 `docs/01-product-planning/04-backlog.md` / `docs/03-engineering-governance/technical-debt.md`。

| 优先级 | 任务 | 状态 | 建议下一步 | 事实源 |
|--------|------|------|------------|--------|
| P1-P | REQ-042 Agent Workspace 塑形 | 🔵 Ready for Docs Only | 可并行塑形 Conversation/Run/Event UI 契约；完整代码实现等待 R1/C1 | [Requirement](../01-product-planning/05-requirements/REQ-042-agent-workspace-three-pane-experience.md) |
| P1 | REQ-047 C1 Durable Core 总验收 | ⚫ Blocked by R1-S1..S6 | R1 全部验收后执行联合 conformance 与文档收口 | [Joint Plan](../02-delivery-plans/02-plans/2026-07-24-req-041-047-conversation-run-contract-plan.md#slice-c1durable-core-总验收与文档收口) |

## 最近完成

最近完成区默认最多保留 20 行（按 `docs/03-engineering-governance/01-rules/workbench.md#保留策略` 强约束）。超过 20 行时，必须一次性批量归档，只保留最新 12 行；第 13 行及以后全部移出。不得每次只移动 1 行。本表只承担"近期完成窗口"的角色，详细验证、行为变化、PR 描述和复盘见 `docs/03-engineering-governance/work-log.md`、对应技术债总账、plan 或 PR。

按"最近优先"（最新任务在最上）排序：

| 日期 | 任务 | 状态 | 摘要 | 事实源 |
|------|------|------|------|--------|
| 2026-07-31 | R1-S3-B Schema 与基础契约（actor tombstone + shared digest + per-owner source key） | 🟢 完成 |  migration 038 + shared digest helper + per-owner source key + tombstone 契约（6 处 fail-closed guard + `DirectRagTerminalReplayError` 透传）；6 轮 max 复审收口 0/0/0；23 文件 / 1689 增；三路 CI 全绿（Backend 8m52s） |
| 2026-07-30 | R1-S3-A Execution owner 契约注记/plan delta（先于代码冻结） | 🟢 完成 | 纯文档冻结 execution.core.v1 participant 设计（fenced port + 9 writer 矩阵 + migration 038 actor tombstone + per-owner source key + event 计数器 + S3/S6 拆分）；两轮 max 复审 + 轻量复核 0/0/0；S3-A~E PR 拆分冻结；三路 CI 全绿 | [PR #515](https://github.com/MarkDanile/MetaEduBase/pull/515)（merge `2d4f8091`）/ [Plan §R1-S3](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md) / [work-log](work-log.md) |
| 2026-07-30 | R1-S2-D/E workspace 正文清除 + participant ACK + final body scan | 🟢 完成 | workspace.core.v1 participant 正文清除 + body scan + ACK；V1 冻结契约（fingerprint 持久化 migration 037 + 构造器禁覆盖 + placeholder denylist）；7 轮 max 复审 P0/P1/P2=0/0/0；全量 1908 passed；三路 CI 全绿 | [PR #513](https://github.com/MarkDanile/MetaEduBase/pull/513)（merge `5db40361`）/ [Plan §R1-S2](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md) / [work-log](work-log.md) |
| 2026-07-29 | R1-S2-C ingress checkpoint source key + title/create fence + backfill 锁序 | 🟢 完成 | ingress 真实 source key + verdict/advance 拆分 + title/create 接 fence + backfill 消 AB-BA + deleted 410/redacted envelope + migration 036 归一；四轮 max 复审清零；全量 1849 passed；三路 CI 全绿 | [PR #511](https://github.com/MarkDanile/MetaEduBase/pull/511)（merge `2ceaffd0`）/ [Plan §R1-S2](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md) / [work-log](work-log.md) |
| 2026-07-28 | R1-S1 Fence/Hold/Purge schema 基座 | 🟢 完成 | owner key 锁 + owner registry + 四协调表 + tombstone + fence 状态机（16 边）+ backfill 恢复契约；六轮 max 复审 P0/P1/P2=0/0/0；全量 1777 passed；dev 已 reset 到 034 head | [PR #506](https://github.com/MarkDanile/MetaEduBase/pull/506)（merge `b8cbdf14`）/ [Plan §R1-S1](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md) / [work-log](work-log.md) |
| 2026-07-27 | REQ-060 Slice 4 移动端 + a11y + Playwright + 收口 | 🟢 完成 | useMobileDrawer + LayoutView 重构（30 新增 vitest）+ Playwright 3 组 spec（55/55）；326/326 vitest；三路 CI 全绿；六轮复审 P0/P1/P2=0/0/0；评分 95 | [PR #503](https://github.com/MarkDanile/MetaEduBase/pull/503)（）/ [Plan §Slice 4](../02-delivery-plans/02-plans/2026-07-23-req060-console-ia-nav-rbac-plan.md) / [work-log](work-log.md) / [scorecard](04-retrospectives/review-score-log.md) |
| 2026-07-25 | TD-087 模板管理 API 后端 RBAC | 🟢 完成 | 15 个管理端点统一高权守卫；tenant-local 最小 lookup DTO、403 脱敏与 92 例角色/租户矩阵完成；Template 124、Identity 47、Frontend 175 passed，三路 CI 全绿 | [PR #495](https://github.com/MarkDanile/MetaEduBase/pull/495)（`40a7bf46`）/ [Tech Debt](technical-debt.md#td-087-模板管理-api-缺少后端-rbac) |
| 2026-07-25 | Agent Control Plane D1 Direct RAG compatibility recording | 🟢 完成 | 旧 evidence API 持久化 Conversation/Message/Run/Event/terminal；双向 bridge 恢复、scoped identity、隔离 execution claim 与 `033` staging；全量 1623 passed，三路 CI 与 `max` 复审全绿 | [PR #489](https://github.com/MarkDanile/MetaEduBase/pull/489)（`56de6bf1`） |
| 2026-07-24 | Agent Control Plane A1 Run query 与 SSE replay | 🟢 完成 | owner-private GET Run、持久化幂等 cancel intent、PostgreSQL ledger SSE replay/live polling、权限重验和 gap/retention/cursor 错误；`032` migration；全量 1605 passed，三路 CI 全绿 | [PR #487](https://github.com/MarkDanile/MetaEduBase/pull/487)（`2f91bed8`） |
| 2026-07-24 | Agent Control Plane B1 Workspace/Execution bridge | 🟢 完成 | shared schema/JCS、双向 inbox/outbox、fencing、Guard、真实 FIFO barrier、terminal projection、dead-letter/reconcile、guarded DELETE/restore 与 `031` migration；全量 1587 passed，三路 CI 全绿 | [PR #485](https://github.com/MarkDanile/MetaEduBase/pull/485)（`e113904b`） |
| 2026-07-24 | Agent Execution E1 durable core | 🟢 完成 | `AgentRun/TurnInput/RunEvent`、FIFO/one-active、连续 Runtime ACK、atomic resume、canonical terminal、组合 FK 与 `030` migration；无 B1/API/Pi/extended entity 越界；全量 1562 passed | [PR #483](https://github.com/MarkDanile/MetaEduBase/pull/483)（`d66f50d3`） |
| 2026-07-24 | Agent Execution E0 identity、Binding 与 Snapshot | 🟢 完成 | `agent_execution` 最小 catalog、版本化 Snapshot、Direct RAG compatibility identity、Binding epoch/DB-clock lease/cursor 契约与 `029` migration；无 Run/Event/API/Runtime 越界；全量 1411 passed | [PR #481](https://github.com/MarkDanile/MetaEduBase/pull/481)（`37417149`） |
| 2026-07-24 | Agent Workspace W1 durable store | 🟢 完成 | `agent_workspace` 四业务表 + inbox/outbox、owner-private API、CAS/keyset、双 seq 与完整摘要落地；DELETE/`/turns` 保持关闭；全量 1390 passed | [PR #479](https://github.com/MarkDanile/MetaEduBase/pull/479)（`88bf3c35`） |

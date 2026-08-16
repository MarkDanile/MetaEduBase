# REQ-041/047 R1 Retention、Purge 与恢复分 Slice 实施计划

> Status: Proposed
> Date: 2026-07-27
> Spec: [R1 专项契约](../01-specs/2026-07-27-req-041-047-r1-retention-purge-recovery.md)
> Parent Plan: [Conversation/Run Durable Core Plan](2026-07-24-req-041-047-conversation-run-contract-plan.md)

## 1. 交付目标

在不开放新 Agent Workspace submit-turn、不实现 Runtime 和 extended entities 的前提下，完成 Conversation 30 天恢复、owner-scoped erasure fence、durable purge saga、legal hold、Run/Event 90/365 天 retention、迟到写抑制与真实 PostgreSQL 故障恢复。

执行顺序固定为：

```text
R1-S0 契约冻结
  -> R1-S1 Fence/Hold/Purge schema 基座
  -> R1-S2 Workspace owner
  -> R1-S3 Execution owner
  -> R1-S4 Transport/External/Late-write
  -> R1-S5 Scheduler/Operations/Legal-hold API
  -> R1-S6 Fault + Retention 验收
  -> C1 Durable Core 总验收与文档收口
```

REQ-042 可在 R1 实施期间并行进行文档塑形，但完整 Workspace 代码实现不早于 C1。TD-085、REQ-043 依次位于 C1 和 REQ-042 之后。

## 2. AI Delivery Profile

- Complexity: 极高
- Risk: 多租户数据删除、法律 hold、分布式状态、并发锁序、迟到写、外置对象、审计保留
- Lead: Codex + GPT-5.6 Sol `xhigh`；普通 repository/DTO/test slice 可降为 `high`
- Delegable: 纯 DTO、只读 query、测试 fixture、运维展示和文档同步可在契约冻结后交给 GLM-5.2 `high/max`
- Not Delegable: owner registry、迁移/回填、锁 key、fence 状态机、hold/purge CAS、ACK 完成条件和 external unknown 语义
- Independent Review: 第二 Harness + 不共享实现上下文的模型 `max`，只读输出 P0/P1/P2 反例清单
- Human Gate: 架构负责人冻结 owner/边界；数据或安全负责人签字 legal hold、retention、日志和生产发布
- Validation: 真实 PostgreSQL 故障/并发套件 + hermetic backend 全量 + migration 往返 + docs gate；mock 不能替代锁序、外置对象或 Runtime 产品验收

实现模型和第二评审模型不得同时修改同一迁移、状态机或公共契约。每个 PR 记录实际 model id、effort、返工、CI 尝试和评审缺陷。

## 3. Slice 计划

### R1-S0：专项契约与任务事实源

**复杂度/执行**：高，GPT-5.6 Sol `xhigh`；只做文档。

交付：

- [ ] 用户确认 Spec §12 五项实施门禁。
- [ ] 冻结 fixed owner keys、owned payload/audit envelope、hold authority、writer fence、unknown owner 和 external object 语义。
- [x] 修正 Backlog、P3 Milestone、W30 Iteration、REQ-041/047 和 current-work 中过期的 `D1 Next`、R1/C1 命名及顺序。
- [x] 建立本 Plan，后续实现 PR 不再直接扩写联合 Plan 的单段 R1。

退出条件：文档门禁与链接检查通过；不得声明 R1 implementation In Progress 或 C1 Ready。

### R1-S1：Fence、Hold 与 Purge schema 基座

**复杂度/执行**：极高，Sol `xhigh` 主实现，独立 `max` 审查迁移与并发契约。

建议代码边界：

```text
packages/server-python/app/composition/agent_erasure.py
packages/server-python/app/contexts/agent_workspace/{domain,application,infrastructure}/...
packages/server-python/alembic/versions/<next>_agent_erasure_foundation.py
packages/server-python/tests/contexts/agent_workspace/...
packages/server-python/tests/composition/...
```

交付：

- [x] 实现唯一版本化 `conversation_owner_key()`；复用现有 Conversation guard，不允许 Adapter 自行 hash。
- [x] 增加 ErasureFence、PurgeOperation、PurgeOwnerCheckpoint、ConversationLegalHold 与 Conversation `hold_revision`，同时扩展 Message/Run/CompatibilityOutput/transport 的显式 tombstone 表达；禁止用空正文占位。
- [x] 建立 code-defined owner registry、canonical snapshot/digest 和 capability negotiation；未知/版本变化 fail closed。
- [x] migration 只做 expand；另提供可恢复、分批、tenant 限流的 backfill 命令补既有 Conversation baseline fences。upgrade/downgrade 与重复 backfill 幂等。
- [x] 只实现状态/port/repository，不启动 scheduler、不清正文。

明确不做：Workspace/Execution erase、外部 Runtime 调用、API 菜单或 UI。

验证：schema check、tenant composite keys、CAS 表驱动、hash golden vectors、migration 往返、并发创建 fence 唯一性。

R1-S1 实施记录（`034_agent_erasure_foundation`）：

- 锁 key 唯一实现位于 `app/composition/agent_erasure_locks.py`，canonical bytes 带 `metaedu.agent.owner.v1\x00` 版本前缀 + SHA-256 前 8 字节 big-endian signed，与既有 `conversation_guard_key`（无前缀）不同输出域；跨进程 golden-vector 测试覆盖。
- owner registry 位于 `app/composition/agent_erasure_registry.py`，6 个固定 `.v1` owner；snapshot 按 owner_key 字典序，digest 经 `canonical_digest`；unknown/版本变化/缺 capability 均 fail closed；`runtime.private.v1` 与 `external.payload.v1` 的 eraser 在 S1 不可用（无已安装 adapter）。
- 四张 coordination 表 ORM 落在 `agent_workspace/infrastructure/models.py`（Conversation/lifecycle owner），经 `AgentErasureRepository`（`erasure_repository.py`）使用；不建跨 bounded-context FK/cascade，`agent_execution` 不 import 这些 ORM。
- tombstone expand-only：Message 增 `body_state`（redacted 仅当 content_state=redacted）+ actor tombstone（redacted 可清 `author_id`、保留不可逆 `actor_identity_digest`；present user_input 仍强制 `author_id` 非空）；AgentRun `output_publish_state=suppressed` 新增“清 ref/media_type/classification/message_id 保留 digest/size”tombstone 分支，同时保留 B1 “保留 envelope 审计”分支（两者并存，禁止部分清除）；CompatibilityOutput 增 `payload_state`（present 仍强制正文非空）；两侧 outbox 新增 `suppressed` 状态（清正文保留 digest），正常 `cancelled` 语义不变。
- backfill 命令位于 `app/composition/agent_erasure_backfill.py`，按 Conversation 独立短事务、`INSERT ... ON CONFLICT DO NOTHING` 幂等、分批 + tenant 限流；可执行入口 `python -m app.composition.agent_erasure_backfill --tenant-id ... [--after-id 游标]`。
- 测试隔离：`tests/composition/conftest.py` 增加 autouse `_clean_agent_tables`（复用 `tests/shared/agent_control_plane.py` 的 `AGENT_CONTROL_PLANE_CLEAN_SQL`，每个测试前后 truncate agent 控制面表），与 agent_workspace/execution/control_plane conftest 的 autouse clean 约定一致；否则 `db_session`（yield 后 commit）写入的 tombstone 行（如 redacted CompatibilityOutput 的 `response_envelope IS NULL`）会让 `agent_workspace` 的迁移往返测试在 downgrade 恢复 NOT NULL 时失败。

R1-S1 复审修订（2026-07-28，PR #506 复审 P1/P2）：

- backfill 增加 keyset 游标：`backfill_baseline_fences(..., after_id=...)` 输入游标，报告带回 `next_after_id` 与 `completed`；bounded 调用须串联 `next_after_id` 才能持续推进（修复“反复处理同一批头部”缺陷）。`report.ok` 仅表示无失败、不等于已扫完；新增 `completed` 表示已扫描完全部。附可执行 CLI 入口。
- fence transition fail closed 版本守卫：`transition_fence_state` 现在用 `require_owner_version` 校验 fence 行的 `owner_version` 与已安装 registry 一致，版本变化即拒绝推进（修复“旧 owner version 仍可 active->erasing”）。
- registry 全部 owner `erase_available=False`：S1 不实现任何 eraser（S2-S4 才由真实 participant 注册），`require_capability(..., "erase")` 一律 fail closed（修复“未实现的 eraser 被声明为可用”）。
- PurgeOperation 持久化排序 owner 列表 `registry_snapshot`（JSONB array，不只 digest）；PurgeOwnerCheckpoint 记录 `owner_version` + `capability_digest`，代码升级后可重建某次 ACK 对应的 owner capability。
- legal hold 修复多 active hold：`has_active_legal_hold` 改 `EXISTS` 语义（同一 Conversation 允许多个 active hold，不再抛 `MultipleResultsFound`）。
- snapshot JSON object/大小上限：`ingress_checkpoint`（object ≤16KB）、`retention_policy_snapshot`（object ≤16KB）、`registry_snapshot`（array ≤64KB）加 CHECK。
- Message actor tombstone（评审 P1.6）：schema 提供 actor 清除能力（redacted 可清 `author_id` 保留 `actor_identity_digest`）。**实际清除正文/actor 的 writer 属 S2，不在 S1**；S1 只交付 schema 表达，正常未擦除写路径约束不弱化。
- CAS transition 范围澄清：S1 交付 fence CAS transition（含版本守卫）；PurgeOperation / PurgeOwnerCheckpoint / LegalHold 的 CAS transition 归 S5（scheduler/operations/hold API），S1 未交付，前文“全部完成”表述据此修正。
- 验证：36 erasure 专项（locks 7 + registry 9 + schema/CAS/并发/tombstone/backfill 19 + migration 往返 1）+ 235 workspace/execution/control-plane 回归全绿；ruff 0 错误；mypy baseline 0 回归。migration `034` 在原 revision 上原地修订（PR 未合并），test DB 重建至 head 通过 upgrade/downgrade/upgrade 往返。

R1-S1 复审修订第二轮（2026-07-28，PR #506 复审第二轮 P1/P2）：

- purge registry snapshot 与 digest 绑定：`create_purge_operation` 不再接受调用方传入的 `registry_digest`，改为从将持久化的 `registry_snapshot()` 同源地计算 digest；新增可选 `expected_registry_digest` 乐观并发校验（不一致即 `OwnerRegistryChangedError` fail closed）。`create_owner_checkpoint` 改从该 operation 持久化的 `registry_snapshot` 取 `owner_version/capability_digest`（不再重读当前 registry），owner 不在 snapshot 中即 `UnknownOwnerError`。
- Conversation actor tombstone（Spec §7.1）：`agent_conversations` 新增 `actor_state`（present/redacted）与 `creator_identity_digest`，`created_by` 放宽为 nullable；`ck_agent_conv_actor` 约束 present 强制 `created_by` 非空、redacted 允许 `created_by=NULL` 但保留 64-hex digest。**实际清除 writer 归 S2**。domain `Conversation.created_by` 保持 `UUID`（创建命令必有 actor）；`_to_conversation` 遇 `created_by IS NULL`（越权 tombstone 行）fail closed。
- backfill 参数 fail closed：`batch_size >= 1`、`max_conversations is None or >= 1`，非法即 `ValueError`（修复 `batch_size=0` 虚假 `completed=True`）。`BackfillReport` 删除全量 `processed_conversations` 列表（内存随会话数线性增长）；失败明细改 `failures`（含稳定 `reason_code` + `error_type`，仅失败条目、内存有界），`failed_conversations` 保留为兼容视图。
- CLI 退出码契约：`0`=全部完成、`1`=有失败、`2`=未完成须以 `next_after_id` 续跑（修复 bounded 未完成仍 exit 0）。新增 CLI 专项测试。
- 验证：45 erasure 专项（含新增反例）+ 235 workspace/execution/control-plane 回归全绿；ruff 0；mypy baseline 0 回归（修复 `created_by` 放宽引入的 domain 类型回归）；migration `034` 原地再修订，upgrade/downgrade/upgrade 往返通过。
- 注意：本地 dev DB 为旧版同 revision `034`，其 schema 与当前文件不一致，普通 downgrade 会失败（新版 downgrade 会删除旧 schema 没有的约束）；须在 `034` 最终稳定后对 dev 做显式 schema reset 或专门修复脚本，不能假设普通 downgrade 可用。

R1-S1 复审修订第三轮（2026-07-28，PR #506 复审第三轮 P1/P2）：

- registry 真正 fail closed（修复第二轮未闭环）：`create_purge_operation` 改为对**同一份** `registry_snapshot()` 经 `snapshot_digest()` 计算 digest（不再 `registry_snapshot()`/`registry_digest()` 分离调用）。`create_owner_checkpoint` 新增两道 fail-closed 校验——(a) 持久化 `registry_snapshot` 的 digest 必须等于持久化 `registry_digest`（snapshot 被篡改即拒）；(b) operation 的 digest 必须仍匹配当前已安装 registry（registry 升级即拒，不基于过期能力视图建 checkpoint，Spec §4.2 / R1-AC2）。新增 registry helper `snapshot_digest(snapshot)` 对任意 snapshot 计算 canonical digest。
- `hold_revision_snapshot` 下界：repository 参数校验 `< 0` 即 `ValueError`，ORM 与 migration 的 `ck_agent_purge_revisions` 同步加 `hold_revision_snapshot >= 0`（修复真实 PostgreSQL 可持久化 `-1`）。
- backfill failures 真正内存有界：`BackfillReport` 增 `failure_count`（总失败数）+ `failures` 样本封顶 `_MAX_FAILURE_SAMPLES=16`（超出只计数不再 append，系统性失败不再 O(N)）。
- backfill completed 误报修复：达到 `max_conversations` 提前退出时，仍对游标后做一次 `EXISTS` 探测；仅剩 1 行且 `max=1` 时正确返回 `completed=True`（不再误报未完成 / CLI exit 2）。
- 文档同步（评审 P2.5）：本 plan 与 current-work 不再提前宣称问题已关闭，改为按真实修复结论记录。
- 验证：51 erasure 专项（含新增 6 个反例）+ 235 workspace/execution/control-plane 回归全绿；ruff 0；mypy baseline 0 回归；migration `034` 原地再修订，upgrade/downgrade/upgrade 往返通过。

R1-S1 复审修订第四轮（2026-07-28，PR #506 独立 `max` 对抗式复审 F1-F10，P0=0/P1=1/P2=9）：

- F1（P1）fence fencing token 单调守卫：`transition_fence_state` 新增 `purge_revision < model.purge_revision or hold_revision < model.hold_revision` 即 `ValueError` fail closed（等值合法，重试复用同 token）。修复「CAS 可把 token 回退到更小值、重新放行持有旧 revision 的暂停 writer」（R1-AC3）。反例：active→erasing(token 5/3) 后再 erasing→active(token 1/0) 原可成功，现拒。
- F2 registry drift 校验 (b) 补变异杀手测试：新增 `test_owner_checkpoint_fails_closed_on_stale_but_consistent_registry`——把 snapshot 改成 v999 视图**同时**把 `registry_digest` UPDATE 为该篡改 snapshot 的 digest（内部自洽、躲过校验 a），但与当前 registry 不符，仅校验 (b) 能拦截。原 `..._on_registry_drift` 测试只改 digest、被校验 (a) 先行拦截，删掉 (b) 仍绿，无锁定能力。
- F3 failures 上界补变异杀手：新增 `test_backfill_failures_capped_above_sample_limit`（失败数 `cap+5` 真实超上限，断言 `len(failures)==cap` 且 `failure_count==total`）。原测试只造 5 个失败（<16），删封顶逻辑仍绿。
- F5 tombstone「清一半必须拒」负向分支补测试：新增 msg redacted 缺 `actor_identity_digest`、Conversation redacted 缺 `creator_identity_digest`、两侧 outbox `suppressed` 保留正文三组反例（真实 PG CHECK 拒），原测试只锁「redacted+digest 可写 / present 缺 actor 拒」一半。
- F4 CLI 打印失败总数：`failed=` 改打 `report.failure_count`（原打有界样本数 `len(failed_conversations)`，系统性失败时误导三个数量级）。
- F10b 删死代码 `count_conversations`（无调用方）。F10c `create_purge_operation` 应用层补 `purge_revision < 1` 即 `ValueError`（与 `hold_revision_snapshot` 校验深度一致，不再漏到 DB IntegrityError）。
- F8 `completed` docstring 降级为「游标探测时点之后没有更多可处理行」的 point-in-time 语义（随机 UUID 主键下 keyset 无法覆盖并发插入，补偿归 S2 首写建 fence + S6 巡检 + 幂等重跑），不作为完备性证明。
- F10a TD-032 登记行数 1007 → 1486。
- 验证：59 erasure 专项（51 + 8 新增反例）+ 235 workspace/execution/control-plane 回归全绿；全部新增测试经变异验证（M1-M5 分别移除单调守卫/registry 校验 (b)/failures 封顶/CLI 修复/purge_revision 校验，对应测试均变红）；ruff 0；mypy baseline 0 回归。本轮**不改 migration 034**（无 schema 变更，纯代码守卫 + 测试）。

**入账为后续 Slice 前置 / 已知缺口（本轮不修）**：

- F7 fence 索引入账 TD-089（经复核更正）：复审称「PK==UK 同列 + PK 前缀 ix = 两棵冗余 btree」。复核（离线 mock 执行 034 `upgrade()`、离线 `--sql`、test_db_setup 与裸 `alembic upgrade head` 双路径真实建库）证实库中无该 UK；round5 复审以纯 PostgreSQL 回滚事务复现进一步更正归因——**PostgreSQL 自身**对「PK 与 UK 同列」去重（只建 PK）。故 `uq_agent_erasure_fence_owner` 是从不生效的**死声明**（非冗余 btree）；`ix_agent_erasure_fence_conversation` 是唯一实际冗余 btree。清理（删死声明 + 冗余 ix）时机决定迁移方式：**#506 合并前处理可原地修订 `034`；合并后处理必须新增 migration**。
- F6 legal-hold primitive 与 Spec §5.3 的语义差距，显式登记为 **R1-S5 前置**：(a) `reason_code` 受控枚举；(b) `create_legal_hold` 推进 `agent_conversations.hold_revision` 且 domain `Conversation` 暴露该字段（S1 为 write-never/read-never）；(c) `has_active_legal_hold` 计入 `expires_at` expiry；(d) `create_purge_operation` 校验 active hold（hold 阻止 purge）。S1 均无在网调用方，「primitive 已交付」不等于「语义已闭环」。
- F9（复核更正，原指控不成立）：复审称「本地 `metaedu_test` 缺 `uq_agent_erasure_fence_owner` = 同 revision schema 漂移」。复核证实**非漂移**：离线 `--sql` 确含该 UK，但 PostgreSQL 对「PK 与 UK 同列」真实执行去重，全新 `alembic upgrade head`（CI 同路径）同样不建。现网/CI 库与 migration 一致，非「同 revision 旧 schema」。本地 test 库已重置至 head（59 专项全绿）；dev 库「同 revision schema reset」流程仍照旧适用。教训：评审关于「schema 漂移」的反例需先以离线 SQL + 真实建库双向证实，不能仅凭「库里缺某约束」推断漂移。

R1-S1 复审修订第五轮（2026-07-28，PR #506 复审第五轮 P0=0/P1=1/P2=3）：

- P1 fence 状态机显式转移表：新增 `_FENCE_ALLOWED_TRANSITIONS`（允许 active→erasing、erasing→erased/blocked、blocked→erasing），`transition_fence_state` 对非法边（erasing/erased→active、active→erased、erased→任意、blocked→active/erased）fail closed；合法推进（→erasing/erased/blocked）要求 `purge_revision >= 1`（purge fencing token）。修复「erasing→active 重新开放 writer」「active→erased 绕过 erasing fencing」（Spec §5.1/§6.2，R1-AC3）。新增完整 `4×4` 表驱动测试 `test_fence_state_transition_table_4x4`，经变异验证（M6 删转移表校验即变红）。
- P2.2 修复 TD-085 标题被吞：登记 TD-089 时误删 `### TD-085` 标题（索引与正文断开），已恢复。
- P2.3 更正 TD-089 归因 + 迁移方式：同列 PK/UK 去重归因为 **PostgreSQL 自身**（纯 PG 回滚事务复现证实，非 SQLAlchemy）；并明确「#506 合并前处理可原地修订 `034`，合并后处理必须新增 migration」。
- P2.4 backfill 失败恢复契约：`BackfillReport.conversations_scanned` 改名 `conversations_succeeded`（只计成功行，语义准确）；模块 docstring 与 `next_after_id` 注释明确「失败行游标仍推进、`--after-id` 续跑不重试失败行、失败后唯一可靠恢复是从 tenant 起点幂等重跑到 exit 0」；CLI exit 1 增打「rerun from tenant start」指令。新增 `test_backfill_report_exposes_succeeded_not_scanned` + `test_cli_exit1_prints_full_rerun_recovery`。
- 验证：62 erasure 专项（59 + 3 新增反例）+ 235 workspace/execution/control-plane 回归全绿；ruff 0；mypy baseline 0 回归；本轮**不改 migration 034**（纯代码守卫 + 测试 + 文档）。

R1-S1 复审修订第六轮（2026-07-28，PR #506 复审第六轮 P0=0/P1=0/P2=2 + 1 P3 文案，证据/输入约束小收口）：

- P2.1 补齐 fence 状态机 4×4 边覆盖：原测试实际 15/16，漏 `blocked→blocked` 自迁移；且 `purge_revision=0` 下界只测了 `erasing→erased/blocked`，漏 `active→erasing`、`blocked→erasing`。补齐后 4×4 全部 16 条边 + 三条非 active 源边的 token 下界均有断言（生产转移表无需改动）。
- P2.2 非 erased 边携带 ACK fail closed：`transition_fence_state` 新增 `new_state is not ERASED and ack_digest is not None → ValueError`（ACK 只属于 erased；非 erased 携带 ACK 会被静默丢弃，掩盖调用方把「提交 ACK」与「状态推进」混用）。补三条合法非 erased 边（active→erasing、erasing→blocked、blocked→erasing）携带 ACK 均拒的表驱动断言；经变异验证（M7 删守卫即变红）。
- P3 文案更正：fence 注释「restore 路径重挂新 fence」不准确——owner 一旦离开 active，普通 restore 即不允许，不存在「删除并重建 fence 回到 active」的路径。
- 验证：62 erasure 专项 + 235 回归全绿；ruff 0；mypy baseline 0 回归；本轮**不改 migration 034**。

### R1-S2：Workspace owner 与恢复截止

**复杂度/执行**：极高，Sol `xhigh`；repository/test 切片可由 GLM-5.2 `high` 实现，主模型审查。

交付：

- [ ] `workspace.core.v1` participant 清 Conversation title、物理删除 MessagePart 正文行、清原 actor id 与 ConversationUserState，保留 Message envelope、digest 和不可逆 actor audit digest。
- [ ] Conversation create、submit-turn、auto title、rename、assistant projection、retry/abandon 的正文路径接 writer fence。
- [ ] restore 强制 `now < purge_after`、无 started owner ACK、revision/hold/purge CAS；purged/expired 使用稳定错误码。
- [ ] list/get/search/history 对 deleted/purged fail closed，purge 后 UUID 已知也不泄露正文。
- [ ] final workspace body scan 是完成门禁，不把受影响行数当 ACK。

明确不做：Execution 清除、transport cancellation、Scheduler API。

验证：30 天冻结时钟、restore/delete/purge race、writer fence-check 后暂停、跨 tenant/actor、正文扫描和重复 participant ACK。

#### S2-C 契约注记 / plan delta（2026-07-29，先于代码冻结）

本轮冻结 S2-C 的设计决策与不变量，作为后续实现与独立 `max`/Codex 复审的事实源。不改 migration 034/035、不进 S2-D/E/S3、不启用 purge scheduler、不混入 TD-090 P3。

**1. ingress_checkpoint / ingress_digest 的 canonical source key（Spec §5.1/§6.2，本 Slice 的核心设计）**

`workspace.core.v1` 在 fence 内持有两类受管正文 ingress：`conversation_title`（title 能力）与 `message_part_body`（正文能力）。checkpoint 是**有界 canonical JSON**，只记录 source key 的 epoch/连续水位与 digest，**不保存正文、prompt、自由文本或原始 payload**：

```text
ingress_checkpoint = {
  "schema_version": 1,
  "sources": {
    "body_messages":  {"watermark": <last written message seq>, "epoch": <conversation purge_revision>},
    "title":          {"watermark": <last title-write conversation revision>, "epoch": <conversation purge_revision>},
  }
}
ingress_digest = canonical_digest(ingress_checkpoint)   # JCS SHA-256（shared canonical_digest）
```

- **canonical source key = 受管能力类别**（`body_messages` / `title`），对应 registry 里 `workspace.core.v1` 的 `message_part_body` / `conversation_title` 能力。不引入第三份正文事实源。
- **watermark = 连续水位**（§6.2「连续水位」）：
  - `body_messages` → workspace **message `seq`**。`seq` 是 per-Conversation 连续序号（`ck_agent_msg_seq_positive` / `uq_agent_msg_seq`），在 Conversation 行锁下分配，是该 Conversation 正文的天然连续水位。记录「已写入正文的最后一个 seq」。
  - `title` → Conversation **`revision`**（title 写经 revision CAS 后的值），是 title 这一 owner 类别的单调 token。
- **epoch = Conversation `purge_revision`**：单调 fencing token；purge/restore 推进它即翻转 epoch，旧 epoch 的迟到写在新 epoch 下不得复活正文。
- **digest 规则**：`ingress_digest = canonical_digest(ingress_checkpoint)`（JCS + SHA-256，复用 `shared/schemas/canonical_json.canonical_digest`，与 `_empty_ingress_digest()` 同一函数路径）。
- **明确不伪造**：watermark/epoch 一律取真实 source 序号/token，**不得用 `last_body_write_at`（可观察时间戳）或 fence 自身 `revision`（CAS 计数器）冒充 ingress checkpoint**。`last_body_write_at` 保留为可观察字段，不参与 checkpoint。
- **原子性（§6.2 第 5 步）**：checkpoint 与正文写、receipt 在**同一数据库事务** commit。实现上将 `require_body_write_fence_for_update` 的「建 fence + 校验 + 推进 token/revision」与「写正文」解耦为两步：先裁决 fence（不写 checkpoint），再在同一事务、拿到分配的 `seq`/CAS 后 `revision` 后写入 checkpoint，随正文一起 flush。独立 preflight read 不构成授权。

**2. fence 推进原语拆分（支撑第 1 步原子性）**

`require_body_write_fence_for_update` 当前把「裁决」与「推进 last_body_write_at/revision」耦合。S2-C 拆为：
- 裁决阶段：owner lock → fence FOR UPDATE（缺失按 registry 建 `active`）→ 校验 owner_version/state/fencing token（与现有一致，fail closed → `LateBodyWriteRejectedError`）。
- 推进阶段：仅裁决放行后，由 writer 传入本写的 `watermark`（body=seq / title=revision）与 `epoch`（conversation.purge_revision），在同一事务更新 `ingress_checkpoint`/`ingress_digest`/`last_body_write_at`/fence `revision` CAS。
- title writer（rename/auto-title）与 body writer 复用同一推进原语，仅 source key/watermark 取值不同。

**3. Conversation create 的 fence 接线（item 2 边界）**

新 Conversation 须为 `workspace.core.v1` 建立 baseline `active` fence（缺失不得解释为安全）。create 用 `INSERT ... ON CONFLICT DO NOTHING RETURNING` + `creation_digest` 幂等：仅**真实新建分支**（`RETURNING` 非空）在同事务内经 `create_fence_under_owner_lock` 建 fence（该入口自带 Conversation 行锁 + owner lock，防 AB-BA）；幂等重放分支（行已存在）按既有契约返回、不重建 fence。title 初始为 `title_source=none` 的 tombstone，不算 title 正文写，不在 create 时推进 title ingress。

**4. list/get/search/history fail-closed（item 1）**

- `get_conversation`（`include_deleted=False`）、`list_conversations`（按 `state` 精确过滤）、`list_messages`（先 `_get_owned_row(include_deleted=False)`，缺失即 `ConversationNotFoundError`）现状已 fail-closed：已知 UUID 对 deleted/purged 返回稳定 gone/not-found。
- 本 Slice **补负向契约测试**：已知 UUID 对 deleted/purged 的 get/search/history 不泄露 title、正文、actor 或可恢复元数据（purged title 已清为 tombstone，actor 经不可逆 audit digest）。`_to_conversation` 已对 deleted/purged 投影 tombstone title/不可逆 actor digest，不泄露真实 title/UUID。
- 不改读路径的现有 fail-closed 谓词，只补回归证据。

**5. 受控 backfill 命令（item 4）**

S1 已交付 `app/composition/agent_erasure_backfill.py`（bounded cursor、分批、tenant 限流参数、幂等 ON CONFLICT、exit 0/1/2、next_after_id、失败行语义、`report.ok`≠完备）。S2-C **补齐锁序缺口**：现 `_backfill_conversation` 裸 `INSERT ... ON CONFLICT`，未持 Conversation 行锁/owner advisory lock——与正文 writer 形成 AB-BA 死锁风险，且绕过 `_create_fence` 的「非 baseline 行 fail closed」。改造为**逐 Conversation 经 `AgentErasureRepository.create_fence_under_owner_lock`**（自带 Conversation 行锁→owner lock→fence FOR UPDATE），保留既有幂等/分批/游标/退出码契约不变；`create_fence_under_owner_lock` 对非 baseline（version 漂移/非 active）行 fail closed，计入 `failure_count`。多 owner 逐 owner 建 fence（workspace.core.v1 等）。

**6. reserve fence-before-replay（item 6）**

`reserve_user_turn` 已在幂等 replay 查找（`client_message_id` 命中返回）**之前**调 `require_body_write_fence_for_update`——fence 校验先于幂等命中。补契约测试锁定该顺序：fence 非 active（purge 进行中）时，即使 `client_message_id` 已存在也 fail closed（`LateBodyWriteRejectedError`），不得因幂等命中而复活清除路径上的正文。

**7. 补测试与 race（item 5/7/8）**

- `late_body_write_rejected` API 409 E2E： fence 非 active 时经 API 提交 turn 返回 409（`LateBodyWriteRejectedError` → 409，而非 500）。
- concurrent double-restore race：两个并发 restore 仅一个成功，另一个 CAS conflict fail closed（不双推进 purge_revision）。
- hold 生效中的 restore：登记到 hold slice（S5），本 Slice 只在 S2-C 注记边界、不实现（hold lifecycle 归 S5）。
- 不变量复核（item 8）：惰性建 fence 与 backfill 同走 `create_fence_under_owner_lock`/`_create_fence` 幂等路径、无 PK 冲突；purge/restore/writer 锁序统一 Conversation row→owner lock→fence，无 AB-BA；suppressed tombstone 路径（`project_suppressed_output`）不接正文 fence、不读写正文；跨 tenant/跨 actor/未知 owner/stale token 全部 fail closed。

**验证**：S2-C 专项（fence ingress 推进原子性、title writer fence、create 建 fence、read fail-closed、backfill 锁序、reserve fence-before-replay、409 e2e、double-restore race）+ workspace/execution/control-plane 回归全绿；新增测试经变异验证；ruff 0；mypy baseline 0 回归；docs gate + git diff --check 通过。本轮**不改 migration 034/035**。

#### S2-C 复审修订（2026-07-29，独立 `max` round 1/2 返修落点）

冻结注记后两轮独立复审发现的偏差及落地修订，**优先于上面 §3/§4 的对应旧陈述**：

- **§3 初始 title 旧陈述作废**（round 1 P1-4）：原写「create 时 title 恒为 tombstone、不推进 title ingress」。实际 `create_conversation` 支持初始 title；修订为——真实新建分支若 `conversation.title is not None`，在同一事务按 `title` source key 推进 title ingress（watermark=Conversation `revision`、epoch=`purge_revision`），与 set_title 同一推进原语。初始 title 视为真实 title 正文写，必须进 checkpoint。
- **§4 deleted 读边界修订**（round 2 P1-3）：原写「`_to_conversation` 已对 deleted 投影 tombstone」。实际此前 `_to_conversation` 对 deleted 仍返回原始 `title`/`created_by`。修订为——`_to_conversation` 对 `state=deleted` 投影 **redacted recovery envelope**：`title=None`、`title_source=none`、`created_by=None`、`archived_by=None`、`deleted_by=None`，仅保留恢复所需字段（`id`/`state`/`revision`/`purge_after`/`deleted_at`）；active/archived 行为不变。DELETE 响应、get `include_deleted=True` 均经此 redaction，不泄露真实 title/actor。
- **§4 list/search fail-closed 增强**（round 1 P1-3）：`list_conversations`/`search` 对 `state=deleted` 不再精确过滤返回，而是 fail-closed 抛 `DeletedConversationListingError` → HTTP 410 `deleted_conversation_listing`，避免经 deleted 列表泄露 title 与正文匹配关系。
- **migration 036 数据矩阵**（round 2 P1-1/P1-2）：upgrade 精确匹配 legacy pair（`ingress_checkpoint={} AND ingress_digest=LEGACY`，不依赖 revision），未知 digest 与非空 checkpoint 不动；downgrade 同时还原 legacy checkpoint 与 legacy digest 两列，不留失配。数据中间态由专门 036 数据矩阵测试锁定（rev1/rev>1 legacy 归一、未知 digest 不被覆盖、非空 checkpoint 不动、downgrade 两列正确）。

#### S2-D/E 契约注记 / plan delta（2026-07-29，先于代码冻结）

本轮冻结 S2-D/E（workspace.core.v1 正文清除 + participant ACK + final body scan）的设计决策与不变量，作为后续实现与独立 `max`/Codex 复审的事实源。不改已合并 migration 034/035/036、不进 S3（Execution owner）/S4/S5、**不启用 purge scheduler 对生产自动执行**（`conversation_purge_scheduler` 启用在 Spec §10 属独立 deploy 阶段，本 Slice 只交付可被 scheduler/受控命令调用的清除与 ACK 原语）、不混入 TD-090 P3。

**范围切分**：S2-D = `workspace.core.v1` participant 正文清除原语 + final body scan（Spec §7.1 的执行器）；S2-E = participant ACK + purge operation/owner checkpoint 推进 + 完成门禁（Spec §5.2 的 saga 闭合）。两者共用同一锁序与 fencing token，故契约注记合并冻结、分两个 commit 实现。

**1. 清除触发与锁序（Spec §6.1，与 writer/backfill 同序，防 AB-BA）**

purge 对单 Conversation 的清除**必须**沿用固定锁序：`Conversation row FOR UPDATE -> owner advisory lock(workspace.core.v1) -> ErasureFence row FOR UPDATE -> owner aggregate rows（Conversation -> Message -> MessagePart -> ConversationUserState）`。清除执行器经 `ensure_fence_under_owner_lock`/`transition_fence_state` 取锁，**不得**绕开 Conversation 行锁直接锁 fence 或 Message（否则与 writer 的 Conversation->owner->fence 构成反向等待）。fence 缺失时在 owner lock 下创建（Spec §5.1「不能把缺行解释为安全」）。

**2. workspace.core.v1 participant 清除动作（Spec §7.1，同事务、可重入）**

单 Conversation、单 purge_revision 内，participant 在同一事务完成以下清除并推进 fence `active -> erasing`（首次）：

- **Conversation title**：置 `title=NULL`、`title_source=none`（tombstone），保留 id/state/revision/purge_after/purged_at 等 envelope。**不**物理删除 Conversation 行（restore/审计 envelope 保留）。
- **actor 不可逆匿名化**：`Conversation.created_by`/`Message.author_id` 置 NULL，另存 tenant-scoped 不可逆 `creator_identity_digest`/`actor_identity_digest`（HMAC-SHA256(tenant-scoped key, actor UUID)，64-hex，**不含可还原明文**）。沿用 S1 已建的 `actor_state='redacted'` + digest CHECK 约束（`ck_agent_conv_actor`/`ck_agent_msg_actor_digest`），不用真实 UUID 冒充匿名。
- **Message 正文**：**物理删除** `agent_message_parts` 正文行（V1 不保留 Part envelope，避免空正文违反 part-type 约束），并把所属 `agent_messages` 转 redacted tombstone（`body_state='redacted'`、`content_state='redacted'`、`redacted_at`、`redacted_reason` 用受控 code），保留 Message id/seq/kind/`content_digest`/必要 opaque id。**不得**改写 seq 或删除 Message envelope。
- **ConversationUserState**：物理删除 `agent_conversation_user_state`（pin/read 非审计必需 envelope，Spec §7.1）。
- **redacted_reason 受控化**：一律走 shared `suppression_reason_code` 白名单 code，自由文本（可能含正文/prompt/secret）**绝不**入库（与 S2-A/B tombstone 一致）。

可重入（Spec §8「重复 claim/ACK 丢失后从 checkpoint 恢复」）：对已 redacted Message、已删 Part/UserState、已匿名 actor 再次执行清除是幂等 no-op，不报错、不二次计数。重试复用同 purge_revision 与 owner checkpoint，不新建 revision。

**3. final workspace body scan（完成门禁，Spec §5.2/§7.1）**

清除后、ACK 前必须做 workspace 正文扫描：该 Conversation 下 `body_state='present'` 的 Message、`agent_message_parts` 残留行、`agent_conversation_user_state` 残留行、`actor_state='present'` 的 Conversation/Message 必须为 **0**。扫描结果（每类计数 + canonical digest）记入 owner `checkpoint_digest`。**扫描非零 -> 不得 ACK**，fence 保持/回 `blocked` 并记稳定 reason code（如 `workspace_body_scan_nonzero`），不把「已执行 DELETE 的受影响行数」当完成（Spec §4.2「没有查到正文不是隐式 ACK」）。

**4. participant ACK 与 fencing（Spec §5.1/§5.2）**

- 仅当 body scan 为零，participant 才提交 ACK：`transition_fence_state(erasing -> erased, ack_digest=canonical_digest(清除摘要))`，`ack_digest` 仅允许落在 erased 边（S1 状态机已强制）。ACK 摘要 = 排序后的 `{owner_key, owner_version, purge_revision, 各类清除计数, body_scan_digest}` 的 canonical digest，**不含正文/actor 明文**。
- 推进 fencing token：`purge_revision` 单调不减（重试复用同 token），`hold_revision` 对当前 Conversation `hold_revision`。active legal hold 阻止 fence `active -> erasing`（Spec §5.3），purge operation 记 `blocked`，**不**清除任何正文。
- purge operation/owner checkpoint 同步：`agent_conversation_purge_owners` 该 owner `pending/erasing -> acked`（带 `ack_digest`），operation 在**所有 snapshot owner acked 且 registry digest 匹配且最终 body scan 为零**后才写 `purge_state=completed`/`purged_at`（Spec §5.2）。本 Slice 只接 `workspace.core.v1` 单 owner；多 owner（execution/transport）的 operation 完成判定属 S3/S4，本 Slice 不伪造 completed。

**5. 明确不做（边界）**

- 不启用/不实现 `conversation_purge_scheduler` 对到期 Conversation 的自动 claim 循环（Spec §8/§10，独立 deploy + S3 worker claim 顺序一并交付）；本 Slice 的清除执行器以**受控入口/服务方法**形态供 scheduler 或运维命令调用。
- 不清除 Execution/Runtime/transport owner 正文（S3/S4）。
- 不改 legal hold lifecycle（S5）；仅消费 `hold_revision` 做 purge CAS 与 active-hold 阻止。
- 不实现 external object erase（无生产 adapter，Spec §7.3 对未知 scheme fail closed `external_owner_unavailable`）。

**6. 竞态与不变量复核（复审重点）**

- 清除与并发正文 writer：清除在 owner lock 内推进 fence `active -> erasing` 后，writer 经 `require_body_write_fence_for_update` 裁决即被拒（`LateBodyWriteRejectedError`），清除期间不得有新正文复活（与 S2-A writer-win/purge-win race 互补）。
- 清除与 restore：fence 已离开 `active` 后 restore fail closed（S2-B 已锁）；清除开始后 restore 不得复活正文。
- 迟到写：fence `erasing/erased` 下旧事件只能写无正文 tombstone/receipt，不重建正文（Spec §6.2）。
- 跨 tenant/跨 actor/未知 owner/stale fencing token/版本漂移 全部 fail closed。

**验证**：S2-D/E 专项（title/Message/Part/UserState/actor 清除断言、tombstone envelope 保留、body scan 零/非零门禁、ACK digest 契约、active hold 阻止、清除中 writer 被拒、可重入幂等、跨 tenant/actor fail closed）+ workspace/control-plane 回归全绿；新增测试经变异验证（删除某清除动作 -> body scan 非零 / ACK 被拒）；ruff 0；mypy baseline 0 回归；docs gate + git diff --check 通过。本轮**不改 migration 034/035/036**、不启用 purge scheduler。

#### S2-D/E 复审修订（2026-07-29，独立 `max` round 1 返修落点）

首轮实现后独立 `max` 复审 P0/P1/P2=0/5/2，5 个 P1 阻塞项已按 Sol `xhigh` 返修，**优先于上面注记的对应旧陈述**：

- **P1-1 purge 前置无条件强制**（Spec §3）：原实现未校验会话状态/恢复窗口，active/未到期会话可被直接擦除。修订为--执行器在锁 Conversation 行后强制 `state=deleted AND now >= purge_after AND purged_at IS NULL`，任一不满足 `ConversationNotPurgeableError` fail closed，不依赖 scheduler 只 claim 到期行。反例：active 会话、未到期（`now < purge_after`）、已 purged 三类均 fail closed。
- **P1-2 actor digest 改 HMAC**：原实现用普通 `SHA-256(tenant||actor)`，不满足冻结契约的 HMAC。修订为--`HMAC(HMAC(secret, tenant_id), actor_id)`（SHA-256），tenant-scoped 派生 key、密钥隔离（`settings.jwt_secret` 回退，可注入测试值）。反例：digest != 普通 SHA-256、不同 tenant/secret 产生不同 digest。
- **P1-3 archived_by/deleted_by 清除**：原实现只清 `created_by`，遗漏 `archived_by`/`deleted_by` 两个直接主体标识。修订为--`_anonymize_conversation_actors` 一并 NULL 这两列（V1 无独立 digest 列，删除/归档审计在事件账本非会话行）。反例：清除后两列为 NULL。
- **P1-4 ACK 绑定具体 operation/checkpoint fencing**：原 ACK 用 `(conversation, purge_revision)` 子查询批量 UPDATE、无 CAS、无 registry drift 校验。修订为--`erase_conversation_body` 接 `purge_operation_id`，ACK 时加载具体 operation FOR UPDATE（校验 `purge_revision` 一致 + `registry_digest` 仍匹配已安装 registry，drift -> `OwnerRegistryChangedError`）+ 具体 owner checkpoint FOR UPDATE CAS（`pending/erasing/blocked -> acked`，落 `ack_digest` + `checkpoint_digest`，后者为 scan digest 与前者分离）。反例：purge_revision 不符/registry drift/non-existent operation 均 fail closed。
- **P1-5 blocked 可靠提交 + 重试**：原实现 scan 非零时抛 `WorkspaceBodyScanNonZeroError`，异常致事务回滚、blocked 状态丢失；重试时 fence 已 erasing 致 CAS 冲突。修订为--blocked 改为**正常返回** `WorkspaceErasureOutcome(blocked=True, block_reason=...)`，调用方 commit 后 operation/checkpoint/fence 的 blocked 状态持久化；fence 状态机用 `erasing->blocked`（scan 非零）+ `blocked->erasing`（重试入口），清除幂等（已 redacted/已删除 no-op），重试 scan 归零即 `erasing->erased` ACK。`_record_blocked`/`_ack_owner_checkpoint` 用 state 谓词 CAS（不 clobber completed/cancelled）。active legal hold 也改为 blocked 正常返回（reason=`legal_hold_active`，retryable）。反例：blocked 状态 commit 后持久化、blocked->重试->ACK 全路径。
- **P2（自审）**：`checkpoint_digest` 与 `ack_digest` 分离（scan digest vs 清除摘要 digest）；`conversation.purge_state` 投影与 operation/owner 行同事务保持一致（erasing->`running`、blocked->`blocked`，单 owner 不伪造 `completed`）。

#### S2-D/E round-2 复审修订（2026-07-29，独立 `max` round 2 返修落点）

round-1 返修后独立 `max` 复审 P0/P1/P2/P3=0/5/4/1，5 个 P1 阻塞项已按 Sol `xhigh` 返修，**优先于上面 round-1 注记的对应旧陈述**：

- **P1-1 capability gate 放行**：原 registry 对所有 owner `erase_available=False`，workspace.core.v1 eraser 只能绕过能力门调用。修订为--`workspace.core.v1` 翻 `erase_available=True`，执行器入口经 `require_capability(workspace.core.v1, "erase")` 放行；其余 owner 仍 `False`（待 S3/S4）。`capability_digest` 因此含 `erase_available` 字段。
- **P1-2 actor HMAC secret 隔离**：原实现回退 `settings.jwt_secret`，违反密钥用途隔离（JWT 轮换会改变审计身份摘要）。修订为--新增独立 `settings.actor_erasure_secret`（空值 dev 占位、生产 fail-fast、版本固定），`HMAC(HMAC(actor_erasure_secret, tenant_id), actor_id)`。
- **P1-3 operation/checkpoint 完整 fencing**：原 ACK 仅校验 `purge_revision` + registry drift，`purge_operation_id` 可缺省，未校验 conversation_id/lease_epoch/hold_revision_snapshot/checkpoint owner_version/capability_digest。修订为--`purge_operation_id` 必填；`_load_verified_operation` 校验 conversation_id（跨 Conversation 误 ACK 防护）+ purge_revision + lease_epoch（stale lease）+ registry_digest + hold_revision_snapshot（hold 漂移）；`_load_verified_checkpoint` 校验 owner_version + capability_digest CAS。反例表驱动：跨 conversation / purge_revision / lease_epoch / hold_revision / owner_version / capability_digest 六类不符均 fail closed。
- **P1-4 operation 投影 + erased fence 恢复**：原实现 operation 状态未投影（首成功可能留 scheduled、blocked 重试可能留 blocked），erased fence 重放在 `purged_at` 前置之后被拒、且不修复 pending checkpoint。修订为--erasing 开始 `_mark_operation_running`（scheduled->running）；erased fence 幂等重放**先于** purge 前置（`purged_at` 不阻断），`_repair_checkpoint_if_pending` 用 fence.ack_digest 补 ACK pending checkpoint + operation scheduled->running（ACK 丢失恢复）。反例：erased fence + pending checkpoint + purged_at 重放修复到 acked。
- **P1-5 final scan + 幂等清除完整性**：原 scan 未计入 `archived_by`/`deleted_by`，`_redact_messages` 只选 `body_state=present`（已 redacted 但仍带 author_id 的 assistant/system Message 永久残留、blocked 无法自愈）。修订为--scan 含 archived_by/deleted_by；`_redact_messages` 选择 `or_(body_state=present, author_id IS NOT NULL)`，清除所有 author_id 残留；`_anonymize_conversation_actors` 清 created_by + archived_by + deleted_by。反例：scan 计 archived_by/deleted_by；已 redacted 带 author_id 的 assistant_output 经 erase 清除 author_id -> scan 归零 ACK。
- **P2-1 scan tenant 谓词**：scan_body 的 Conversation 查询补 `tenant_id` 谓词（不用裸 get(PK)），跨 tenant 不误报 actor 残留。
- **P2-2 blocked 路径 scan digest**：`_record_blocked` 也写 `checkpoint.checkpoint_digest = scan.digest()`（非零 scan 证据，不只 success ACK 路径）。
- **P2-3 PostgreSQL 时钟**：purge 截止在 Conversation 锁后取 `clock_timestamp()`（非进程时钟），`now=None` 走 `_database_now()`。
- **P2-4 reason code**：legal hold 用 Spec §9.2 `purge_blocked_by_legal_hold`（非 `legal_hold_active`）。
- **P3**：round-1 注记 line 的前置表达式 typo 修正为 `now >= purge_after AND purged_at IS NULL`；PR 描述更新为 32 测试 / 1881 回归 / HMAC actor digest。

**验证**：S2-D/E round-2 专项 32 测试（含 6 场景表驱动 fencing 反例 + erased fence pending checkpoint 恢复 + scan archived_by/deleted_by + 已 redacted author_id 残留清除 + DB 时钟 + tenant 谓词 + 生产 fail-fast）经 18 项变异验证全部 killed；ruff 0；mypy 0 回归；全量 `pytest -m 'not external_network'` 1881 passed；docs gate + git diff --check 通过。本轮**不改 migration 034/035/036**、不启用 purge scheduler。待独立 `max` 只读复核。

#### S2-D/E round-3 复审修订（2026-07-29，独立 `max` round 3 返修落点）

round-2 返修后独立 `max` 复审 P0/P1/P2=0/4/2，6 项已按 Sol `xhigh` 返修，**优先于 round-2 注记的对应旧陈述**：

- **P1-1 blocked 重试状态一致**：round-2 `_mark_operation_running` 只 scheduled->running，blocked 重试后 operation 卡 blocked + failure_code 残留，与 checkpoint=acked / conversation.purge_state=running 不一致。修订为--`_mark_operation_running` 推进 scheduled/blocked->running 并清 failure_code + bump revision（`_mark_operation_running` 是 failure_code 唯一清除点，ACK 不再防御性清--可测）。反例：重试 ACK 后 operation=running + failure_code=None，与 checkpoint/purge_state 一致。
- **P1-2 operation revision replay fencing**：round-2 ACK 无 operation revision CAS，跨事务 stale operation 可重放。修订为--`erase_conversation_body` 接 `expected_operation_revision` 必填；`_load_verified_operation` 支持 revision CAS（首次加载裁决，后续 mark_running/ack/record_blocked 复用锁内稳定 revision）；状态变化（scheduled/blocked->running、->blocked、repair scheduled->running）bump revision。反例：调用方观测 revision 过期（被并发 bump）-> "operation revision mismatch" fail closed。
- **P1-3 erased repair 安全**：round-2 erased fence 重放不校验 scan 与 operation 状态，可在非零 scan 或终态 operation 上补 ACK。修订为--erased 重放先校验 `scan.total == 0`（非零 = 正文泄漏矛盾，fence 已终态不可 blocked，fail closed）；`_repair_checkpoint_if_pending` 校验 operation 处可修复状态（scheduled/running/blocked），cancelled/failed/completed 终态 fail closed。反例：erased + 非零 scan -> ValueError；erased + cancelled operation -> ValueError。
- **P1-4 actor secret 强度 + 版本契约**：round-2 只校验非空，无强度阈值与版本机制。修订为--新增 `settings.actor_erasure_secret_version`（混入 HMAC key 派生 `HMAC(HMAC("{v}:{secret}", tenant), actor)`，轮换 = 新 secret + bump version）；`validate_production_actor_erasure_secret`（lifespan 启动期）+ 构造期双重校验：production secret >= 32 字符 + version >= 1，否则 fail-fast。反例：空/弱 secret -> RuntimeError；不同 version -> 不同 digest。
- **P1-5 公开 now 参数绕过 DB 时钟**：round-2 `erase_conversation_body` 暴露 `now` 参数，调用方可传进程时钟绕过 `clock_timestamp()`。修订为--移除 `now` 参数，purge 截止始终用 `_database_now()`（Conversation 锁后采样）。反例：传 `now=` -> TypeError（参数不存在）；DB 时钟始终被调用。
- **P2 owner_version 去硬编码**：round-2 `_record_blocked` / `_repair_checkpoint_if_pending` 硬编码 `fence_owner_version=1`。修订为--两处改用 `fence.owner_version`（与 `_ack_owner_checkpoint` 一致，未来 owner version bump 不会误判 mismatch）。反例：fence + checkpoint owner_version=2 同步时 blocked 路径仍匹配（硬编码 1 会误 raise）。

**验证**：S2-D/E round-3 专项 40 测试（含 7 场景表驱动 fencing 反例 +operation revision CAS+ + erased 非零 scan fail closed + erased 终态 operation fail closed + blocked 重试状态一致 + secret 强度/版本/启动校验 + now 不被接受 + owner_version 去硬编码）经 8 项 round-3 变异全 killed；ruff 0；mypy 0 回归；docs gate + git diff --check 通过。本轮**不改 migration 034/035/036**、不启用 purge scheduler。待独立 `max` 只读复核。

#### S2-D/E round-4 复审修订（2026-07-29，独立 `max` round 4 返修落点）

round-3 返修后独立 `max` 复审 P0/P1/P2=0/5/0，5 项已按 Sol `xhigh` 返修，**优先于 round-3 注记的对应旧陈述**：

- **P1-1 legal-hold 路径绕过 operation revision CAS**：round-3 `_record_blocked` 无 `expected_revision`，legal-hold 路径调用时不裁决 revision；stale caller（revision 过期）+ 活跃 hold 仍能把 operation/checkpoint 置 blocked。修订为--`_record_blocked` 新增 `expected_revision: int | None = None` 透传 `_load_verified_operation`；legal-hold 路径传 `expected_revision=expected_operation_revision`。反例：stale revision + 活跃 hold -> "operation revision mismatch" fail closed，零状态变更（operation 留 scheduled、checkpoint 留 pending）。
- **P1-2 legal-hold blocked 投影不一致 + reason change 不 bump**：round-3 legal-hold 分支置 operation/checkpoint=blocked 但不投影 `Conversation.purge_state=blocked`（仍 scheduled），违反 Spec §5.2 同事务一致；且 `_record_blocked` 对已 blocked operation 的 reason 变化不更新 `failure_code`、不 bump revision。修订为--legal-hold 路径同事务置 `conversation.purge_state = BLOCKED`；`_record_blocked` 已 blocked 且 `failure_code != reason` 时更新 failure_code + bump revision（checkpoint 同理设 cp_changed）。反例：legal-hold 后 purge_state=blocked 与 operation/checkpoint 一致；scan_nonzero -> legal_hold reason 变化 revision 递增。
- **P1-3 erased repair 接受/留下矛盾事实**：round-3 `_repair_checkpoint_if_pending` 对 ACKed checkpoint 不验证 `ack_digest`/`checkpoint_digest` 与 fence/scan 一致；对 blocked operation 只清 `failure_code` 不推进 running，Conversation 投影不修复。可得到 `fence=erased / checkpoint=acked / operation=blocked / failure_code=NULL`。修订为--ACKed checkpoint 必须验证 `ack_digest == fence.ack_digest` 且 `checkpoint_digest == scan.digest()`，矛盾 fail closed；blocked operation 推进到 running（不只清 failure_code）+ bump revision；erased 重放同事务修复 `conversation.purge_state = RUNNING`（三方一致）。反例：篡改 ack_digest -> "contradictory ACK fact"；blocked operation + purge_state=blocked -> 修复到 running + purge_state=running。
- **P1-4 actor digest key version 未持久化**：round-3 `config.py` 声明 secret+version 轮换，但表只存 64-hex digest 无 version 列，actor UUID 清除后无法重算或判断历史 digest 版本。修订为--**V1 冻结契约**：生产环境 `actor_erasure_secret_version` 冻结为 1，**禁止轮换** secret/version，直至 migration 落地持久化 digest version；`validate_production_actor_erasure_secret` + 构造期双重校验 production `version != 1` -> RuntimeError；非生产允许 version>=1 供测试。反例：production version=2 -> "必须为 1" RuntimeError；version=0 -> 同样 fail。
- **P1-5 agent-type Message author digest 不可逆丢失**：round-3 `_redact_messages` 只对 `author_type=="user"` 计算 digest 但清除**所有** `author_id`，违反 plan:255 `Message.author_id -> actor_identity_digest` 契约（assistant_output/system_notice 的 author_id 也应转 digest）。修订为--对所有 `author_id is not None` 的消息计算 `actor_identity_digest`（不再限定 author_type），然后清 author_id。反例：agent author 消息 redact 后 `actor_identity_digest` 为 64-hex HMAC（非 None），与 user author 一致。

**验证**：S2-D/E round-4 专项 46 测试（+7 round-4：legal-hold stale revision fail closed / legal-hold purge_state=blocked 投影 / record_blocked reason change bump / erased ACKed digest mismatch fail closed / erased blocked->running + 三方一致 / V1 版本冻结 / agent author digest 全类型）经 8 项 round-4 变异全 killed（含唯一锚点修正）；ruff 0；mypy 0；agent_control_plane + composition + identity jwt 228 passed；全量 `pytest -m 'not external_network'` 1895 passed / 0 failed；docs gate + git diff --check 通过。本轮**不改 migration 034/035/036**、不启用 purge scheduler。待独立 `max` 只读复核。

#### S2-D/E round-5 复审修订（2026-07-29，独立 `max` round 5 返修落点）

round-4 返修后独立 `max` 复审 P0/P1/P2=0/2/1，3 项已按 Sol `xhigh` 返修，**优先于 round-4 注记的对应旧陈述**：

- **P1-1 ACKed checkpoint 绕过 operation 状态修复**：round-4 `_repair_checkpoint_if_pending` 在 ACKed checkpoint digest 验证后早 return，跳过 operation 修复块。`checkpoint=acked + operation=blocked/scheduled` 矛盾组合漏过--Conversation 被改 running 但 operation 留旧状态。现有 round-4 测试把 checkpoint 回退为 pending 避开了此分支。修订为--ACKed digest 验证后不早 return，fall through 到统一 operation 修复块（`checkpoint_already_acked` 标记跳过 checkpoint 重写，但 operation 修复始终执行）。反例：ACKed+blocked -> operation 修复 running；ACKed+scheduled -> operation 修复 running + 补 started_at。
- **P1-2 冻结 version 未冻结实际 secret**：round-4 只校验 secret 长度 + version=1，生产把 secret A 换 B（version 仍 1）启动/构造都通过，历史 digest 孤儿化。"禁止轮换" 只是文案。修订为--(1) 新增 migration 037 `system_key_fingerprints` 表 + `_actor_erasure_key_fingerprint`（HMAC-SHA256(secret, 域分隔符) 64-hex，非可逆）+ `validate_production_actor_erasure_key_fingerprint`（lifespan 启动期 upsert 持久化 fingerprint，首次锁定 / 不一致 fail closed，检测 secret 静默替换）；(2) 构造器生产环境禁覆盖 `audit_secret`/`audit_secret_version`（必须来自 settings，防调用方注入不同 key）。反例：secret A->B 同 version=1 -> fingerprint 不一致 RuntimeError；构造器传 audit_secret -> "does not accept override" RuntimeError。
- **P2 模块文案与 V1 冻结契约冲突**：round-4 docstring/error 仍写"新 secret + bump version，审计可追溯"/"独立轮换"。修订为--统一改为"migration 落地前不可轮换"（docstring + `_actor_audit_digest` 注记 + error message）。

**验证**：S2-D/E round-5 专项 52 测试（+6 round-5：ACKed+blocked operation 修复 / ACKed+scheduled operation 修复 / fingerprint lock-in+match / fingerprint mismatch fail closed / 构造器禁覆盖 / 非生产跳过）经 6 项 round-5 变异全 killed；ruff 0；mypy 0；migration roundtrip + schema 56 passed；agent_control_plane + composition + identity jwt 234 passed；全量 `pytest -m 'not external_network'` 回归通过；docs gate + git diff --check 通过。本轮**新增 migration 037**（不改 034/035/036）、不启用 purge scheduler。待独立 `max` 只读复核。

#### S2-D/E round-6 复审修订（2026-07-29，独立 `max` round 6 返修落点）

round-5 返修后独立 `max` 复审 P0/P1/P2=0/1/3，4 项已按 Sol `xhigh` 返修，**优先于 round-5 注记的对应旧陈述**：

- **P1 生产部署未接入新密钥契约**：round-5 新增 `ACTOR_ERASURE_SECRET` + `ENVIRONMENT=production` 启动校验，但 `deploy/docker-compose.yml` 未传递两者，`deploy/.env.production` / `.env.example` 也未声明，应用沿用 `development` 默认跳过校验 + 用 dev 占位密钥生成 digest。修订为--Compose backend 注入 `ENVIRONMENT`（默认 production）+ `ACTOR_ERASURE_SECRET`（必填）；`.env.production` 声明两者；`.env.example` 补 `ACTOR_ERASURE_SECRET` 模板；`security.md` secret 表 + 生产节登记。
- **P2 校验失败前提交调用方事务**：round-5 `validate_production_actor_erasure_key_fingerprint` 在 fingerprint 比对前 `session.commit()`，函数接受任意 `AsyncSession`，mismatch 抛错前已提交调用方已有写入。修订为--函数不自行 commit，由 lifespan 用 `async with async_session_factory.begin()` 持有事务（成功自动提交、失败自动回滚）。多 worker 并发首启由 PG 行锁串行化（第二个 upsert 阻塞到首个提交后走 on_conflict re-read）。
- **P2 错误信息暴露 verifier + 非常量时间比较**：round-5 mismatch 异常含 `existing`/`fingerprint` 值（固定消息 HMAC 是密钥 verifier，可离线验证猜测），且用 `!=` 非常量时间。修订为--`hmac.compare_digest()` 常量时间比较；异常文本只保留通用 mismatch 信息（不泄露 fingerprint 值）。
- **P2 037 与多 worker 契约缺专属回归**：round-5 只在 `test_alembic_migrations.py` 断言 head 版本，无 037 表/PK/CHECK + 真实 downgrade->upgrade；fingerprint 测试只用单共享 session，无并发首启覆盖。修订为--新增 `test_037_system_key_fingerprints_downgrade_upgrade_round_trip`（表 + pk + check 约束 + 真实降升级）；新增并发首启测试（两独立 session/事务：同 secret 都成功仅一行 / 不同 secret 恰一方成功一方 mismatch fail）；新增 mismatch error redaction 测试（异常不含 fingerprint 值）。

**验证**：S2-D/E round-6 专项 55 测试（+3 round-6：并发同 secret / 并发不同 secret / mismatch redaction）+ 037 迁移往返 1 项；2 项 round-6 变异 killed（redaction + no-commit），compare_digest 变异 SURVIVED 是预期（timing-only 不可功能测试）；ruff 0；mypy 0；agent_control_plane + composition + identity jwt 238 passed；全量回归通过；docs gate + git diff --check 通过。本轮**新增 migration 037**（不改 034/035/036）、不启用 purge scheduler。待独立 `max` 只读复核。

#### S2-D/E round-7 复审修订（2026-07-29，独立 `max` round 7 返修落点）

round-6 返修后独立 `max` 复审 P0/P1/P2=0/1/1，2 项已按 Sol `xhigh` 返修，**优先于 round-6 注记的对应旧陈述**：

- **P1 生产模板公开 placeholder 通过校验**：round-6 `.env.production` 模板值 `CHANGE_ME_random_jwt_secret_at_least_32_chars` / `CHANGE_ME_random_actor_erasure_secret_at_least_32_chars` 均 >=32 字符，当前校验接受--直接用模板启动会以公开 JWT 密钥运行，并把公开 actor key fingerprint 锁入 037（V1 冻结期不可轮换）。修订为--(1) `.env.production` 模板值留空（Compose `${VAR:?}` 必填检查阻止未配置启动）；(2) 启动期 + 构造期校验新增仓库已知 placeholder denylist（`_KNOWN_JWT_PLACEHOLDERS` / `_KNOWN_ACTOR_ERASURE_PLACEHOLDERS`，含 config 默认值 + deploy 模板值），公开值 fail-fast。反例：`dev-only-*` / `CHANGE_ME_*` -> RuntimeError；随机高熵值 -> 通过。
- **P2 并发测试共享全局 settings**：round-6 并发协程直接覆盖 `settings.actor_erasure_secret`，不能稳定模拟两 worker 独立配置，调度变化时两任务可能读同一 secret；直接赋值也绕过 `monkeypatch` 恢复污染后续测试。修订为--每个协程传独立 `SimpleNamespace` cfg（不修改全局 settings）；`system_key_fingerprints` 加入 autouse TRUNCATE 清理防跨测试泄漏。反例：两独立 cfg 不同 secret -> 恰一方成功一方 mismatch fail。

**验证**：S2-D/E round-7 专项 58 测试（+3 round-7：actor placeholder 拒绝 / JWT placeholder 拒绝 / ctor placeholder 拒绝；并发测试改独立 cfg）；3 项 round-7 变异全 killed（startup/ctor/JWT placeholder 拒绝）；ruff 0；mypy 0（jose stubs 历史忽略）；agent_control_plane + composition + identity 281 passed；全量回归通过；docs gate + git diff --check 通过。本轮不改 migration 034/035/036/037、不启用 purge scheduler。待独立 `max` 只读复核。





### R1-S3：Execution owner、RunEvent payload 与 compatibility output

**复杂度/执行**：极高，Sol `xhigh`；独立 `max` 审查 terminal/projection 反例。

交付：

- [ ] `execution.core.v1` participant 覆盖 Binding、Run、TurnInput、RunEvent 和 CompatibilityOutput 的 conversation-owned 正文。
- [ ] terminal/output/context snapshot/event ingest/compatibility settle 等 writer 接 owner fence。
- [ ] purge ACK 前 suppress 未投影 output、清 terminal/context refs、清 compatibility reply/envelope，并使用显式 payload/tombstone state 保留 digest；不得伪造 output ref 或空 JSON。
- [ ] RunEvent payload tombstone 不改变 seq；外置 ref 交给 `external.payload.v1`，未 ACK 前 execution 不 ACK。
- [ ] 365 天 audit prune 不删除 catalog AgentDefinitionVersion/RuntimeProfile；非终态、unresolved action、`outcome_unknown` fail closed。

明确不做：完整 Approval/Tool/Artifact/Evidence 模型、Pi session destroy。

验证：terminal/projection/delete/purge race、compatibility replay 在 purge 后不返回正文、event seq 连续、catalog 引用不被误删、365 天边界。

#### S3 契约注记 / plan delta（2026-07-29，先于代码冻结；round-1 复审修订 2026-07-30）

本轮冻结 S3（execution.core.v1 participant + 执行 writer fence + RunEvent/compatibility tombstone + dispatch_output deterministic 分类）的设计决策与不变量，作为后续实现与独立 `max`/Codex 复审的事实源。不进 S4（transport/external payload/Runtime fake）、不启用 purge scheduler、不实现 Pi/Runtime session destroy。

> **round-1 复审修订（2026-07-30，P0=0/P1=5/P2=1）**：初始注记有 6 处安全语义未闭合，已按复审返修并直接改正下文（不保留旧陈述）：
> 1. writer fence 覆盖不全（漏 implicit event writer + cancel API 旁路）-> §2 改为 composition-owned fenced port + 完整 writer 命令矩阵。
> 2. actor identity 不能 TD 延后 -> §1/§4/§5 改为 migration 038 + purge 匿名化（Spec §7.1「等直接主体标识」覆盖 execution 表）。
> 3. terminal_reason 非正文无依据 -> §1/§4 改为 purge 裁剪为受控 code，保留 digest。
> 4. RunEvent scan 漏残留 `payload_ref` -> §5 改为无条件 `payload_inline IS NOT NULL OR payload_ref IS NOT NULL`。
> 5. checkpoint source ownership + event 水位未闭合 -> §3 改为 per-owner source key 闭集映射 + per-Conversation event 计数器（非 queue_seq）。
> 6. 30 天 purge 与 365 天 prune 不应共用 participant -> §9 拆分为 S3 Conversation-scoped body eraser + S6 Run-scoped prune worker。

> **round-2 复审修订（2026-07-30，P0=0/P1=4/P2=3）**：round-1 方向已确认，但新暴露 7 处实现缺口，已直接改正下文：
> 1. S3-B 不能提前翻 `erase_available=True`（eraser 未安装）-> §1/§PR 拆分：S3-B 增 `actor_identity` capability 但保持 `erase_available=False`，S3-D 与 participant/scan/ACK 同 commit 翻 `True`。
> 2. create_run 真实入口是 `dispatch_turn -> consume_turn_event -> consume_turn_requested -> create_run`（bridge.py:70），`submit_turn` 只写 workspace outbox -> §2 改正生产入口。
> 3. `terminal_code` 并非受控（`TerminalResult.code` 是任意 1-100 字符文本，run.py:131）-> §1/§4/§5 purge 同时裁剪 code，scan 验证 code+reason。
> 4. migration 038 缺应用层 tombstone 契约 -> §Schema 增 domain/mapper/start/direct-RAG/API 对 `created_by=None` 的处理契约。
> 5. event 计数器需持久化 + baseline 决策 + `created` 标志 -> §3 闭合。
> 6. 不复用 workspace 私有 `_actor_audit_digest` -> §4 提取 composition/shared 公开版本化 helper。
> 7. migration 038 downgrade 仅在无 redacted 行时可逆 -> §Schema 增 anonymization 后 fail-closed/forward-fix 边界。

**1. execution.core.v1 participant 覆盖范围（Spec §4.1/§7.1/§7.2）**

- registry **新增 `actor_identity` capability**（覆盖 execution 表的直接主体标识，与 workspace.core.v1 同名 capability）。**`erase_available` 时序**（round-2 P1-1）：S3-B 增 capability 但**保持 `erase_available=False`**（eraser 未安装，`require_capability("execution.core.v1", "erase")` 仍 fail closed）；S3-D 与 participant + scan + ACK 测试**同 commit 翻 `erase_available=True`**。`capability_digest` 因此分两次变化（S3-B 增 capability、S3-D 翻 erase_available）。其余 owner（workspace.transport/execution.transport/external.payload/runtime.private）保持 `erase_available=False`。
- participant 清除的 Conversation-owned 执行正文（对应 registry capabilities）：
  - `run_output_body`：completed Run 的 terminal output -> `output_publish_state=suppressed` + `terminal_output_ref/media_type/classification/message_id` = NULL，保留 `terminal_output_digest/terminal_output_size`。S1 `ck_agent_run_terminal_output` 已含 suppressed tombstone 分支（schema 不变）。
  - `run_context_body`：Run `context_snapshot_ref/digest/classification` -> NULL（保留 Run status/时间/catalog refs envelope）。
  - `compatibility_output`：`CompatibilityOutput.reply_text/response_envelope` -> NULL + `payload_state=redacted`，保留 `output_digest/response_digest`。S1 `ck_agent_compat_output_payload` 已支持。
  - `run_event_payload`：`RunEvent.payload_inline` -> NULL + `payload_state=redacted`，保留 `seq/event_type/visibility/classification/payload_digest/payload_size/provenance`。**seq 不变**（seq 是不可变身份，tombstone 不改 seq，Spec §7.2/§8）。S1 `ck_agent_run_event_payload` 已支持。**external payload**（`payload_state=external`）：execution.core.v1 **不**清 `payload_ref`（归 external.payload.v1），blocked（§5）。
  - `actor_identity`（round-1 P1-2 + round-2 P2-2）：`AgentRun.created_by` / `TurnInput.created_by` -> NULL + tenant-scoped 不可逆 HMAC digest（由 composition/shared 公开版本化 helper 派生，`actor_erasure_secret` + V1 冻结契约；workspace 与 execution participant 共用同一 helper，不复用 workspace 私有 `_actor_audit_digest`）。Spec §7.1「Conversation.created_by、Message.author_id **等**直接主体标识在 purge 时清除」覆盖 execution 表，**不**延后至 TD。
- **不拥有的正文**（边界，不清除）：`RuntimeSessionBinding.runtime_session_ref`（runtime.private.v1）、execution outbox `payload_inline/payload_ref`（execution.transport.v1，S4）、external object（external.payload.v1，S4）、catalog refs（`AgentDefinitionVersion`/`RuntimeProfile` 是 tenant catalog，Spec §4.1 明确不随 Conversation purge，FK 保留至 365 天 audit prune）。
- **terminal_reason + terminal_code 裁剪**（round-1 P1-3 + round-2 P1-3）：`TerminalResult.reason`（任意 1-500 字符，`run.py:134`）**与 `TerminalResult.code`（任意 1-100 字符，`run.py:131`）都是任意文本**，无枚举/白名单约束，长度限制 ≠ 脱敏；正文可被放进 code 逃过 purge。purge 将 `terminal_reason` 与 `terminal_code` 都裁剪为受控 redaction code（`agent_suppression_reasons` 白名单归一，未知 code 归一到 fallback），保留 `terminal_result_digest`（64-hex digest 非正文）。`ck_agent_run_terminal_envelope` 要求 terminal_code/terminal_reason 非空，受控 code 满足约束，无需 migration 放宽。冻结 versioned terminal code 白名单或稳定归一规则（S3-D 落地），purge 对历史未知 code 同样裁剪。
- **正文型 JSONB snapshot 边界**：`runtime_capability_snapshot`/`run_config_snapshot`/`budget_snapshot`/`usage_summary` 是 `extra="forbid"` 结构字段 + 数字指标，不是 Conversation-owned 正文；execution.core.v1 不清除，body scan 验证无正文泄漏（若发现泄漏登记 TD）。

**2. 执行 writer fence 接线（Spec §6.2，composition-owned fenced port + 完整 writer 矩阵；round-1 P1-1）**

初始注记只列 4 writer + 2 composition 文件，但 `start_run`/`transition_run`/`mark_run_resume_required`/`resume_run`/`commit_terminal` 都内部追加 RunEvent（`_append_event_locked`），cancel API（`RunQueryService.request_cancel`）直接调 `RunCoordinator.commit_terminal`，Runtime ingest 也有独立入口。只改两个文件无法保证所有生产入口过 fence。

- **fence 接线形态**：建立 **composition-owned fenced execution port**（单一受控入口），所有生产路径经此 port 调执行 writer；port 在 Guard + Conversation 行锁内做 fence 裁决 + checkpoint 推进，再调 `RunCoordinator`/`AgentExecutionRepository`。`agent_execution` application/infrastructure 保持纯执行逻辑（不 import erasure repository，Spec §5 跨上下文边界）。**禁止生产路径直接调用未 fenced 的 `RunCoordinator` writer**（`RunQueryService.request_cancel` 等现有直调点改为经 fenced port）。
- **完整 writer 命令矩阵**（按 capability + 是否 implicit event writer）：

| writer（RunCoordinator/repository 方法） | 写入的 execution.core.v1 正文 | source key | event writer 类型 |
|---|---|---|---|
| `create_run_with_root` | Run `context_snapshot_ref` + root TurnInput | `run_context_body` | - |
| `start_run` | RUN_STARTED event payload | `run_event_payload` | implicit |
| `transition_run` | PHASE_CHANGED/RUN_RESUME_REQUIRED event | `run_event_payload` | implicit |
| `mark_run_resume_required` | RUN_RESUME_REQUIRED event | `run_event_payload` | implicit |
| `resume_run` | PHASE_CHANGED event | `run_event_payload` | implicit |
| `commit_terminal` | terminal output + `terminal_reason` + terminal event + usage | `run_output_body` + `run_event_payload` | implicit |
| `append_event` | RunEvent payload | `run_event_payload` | explicit |
| `ingest_runtime_event` | RunEvent payload | `run_event_payload` | explicit（idempotent replay 不推进） |
| `CompatibilityOutputService.stage` | `reply_text`/`response_envelope` | `compatibility_output` | - |

- **生产入口覆盖**（round-2 P1-2 改正）：`submit_turn`（agent_control_plane:124）**只写 workspace outbox**（workspace.core.v1 fence，S2 已覆盖），不创建 Run；Run 由 `dispatch_turn`（:510）-> `consume_turn_event`（:146）-> `AgentExecutionBridgeService.consume_turn_requested`（bridge.py:54，调 `create_run` @ bridge.py:70）创建。故 create_run 的 execution fence 入口是 **bridge dispatch 路径的 `consume_turn_requested`**，不是 `submit_turn`。完整入口矩阵：create_run = `consume_turn_requested`（经 dispatch_turn/Direct RAG activate_turn）；commit_terminal/cancel = `RunQueryService.request_cancel` + Direct RAG complete/fail_turn + Runtime terminal；event = Direct RAG append_event + Runtime ingest；compatibility_output = `CompatibilityOutputService.stage`（Direct RAG complete_turn）。全部经 fenced port，无旁路。
- **erased/erasing fence 下的迟到写**：fence 非 active 时裁决即拒（`LateBodyWriteRejectedError`），迟到 event 只能落无正文 tombstone/receipt（Spec §6.2 第 4 步）。幂等 replay（`ingest_runtime_event` IDEMPOTENT_REPLAY / `stage` 命中 existing / `commit_terminal` terminal digest 命中）**不**推进 checkpoint（verdict 与 checkpoint 推进解耦，与 S2-C P2-6 同理）。

**3. ingress checkpoint source key 与水位（Spec §5.1/§6.2，round-1 P1-5 闭合）**

- **per-owner source key 闭集映射**（替代全局 `INGRESS_SOURCE_KEYS`）：`advance_ingress_checkpoint_for_update` 校验 `source_key` 必须在 `owner_key -> allowed source keys` 映射中。workspace.core.v1 -> `{body_messages, title}`；execution.core.v1 -> `{run_context_body, run_output_body, compatibility_output, run_event_payload}`。跨 owner 写 source key fail closed（防 workspace owner 写 execution source key）。
- **水位**：
  - `run_context_body` / `run_output_body` / `compatibility_output`：watermark = Run `queue_seq`（per-Conversation 连续序号，`uq_agent_run_queue_seq`）。这三类是 per-Run 单值正文（每 Run 至多一个 context snapshot / terminal output / compatibility output），queue_seq 是其 per-Conversation 连续水位。
  - `run_event_payload`：watermark = **per-Conversation 单调递增 event 计数器**（int），**不**用 queue_seq。原因：同一 Run 的所有 event 共享 queue_seq，queue_seq 不能表达 event ingress 进度。计数器仅在**真实新 event 插入**时 +1（`_append_event_locked` 实际插入），`ingest_runtime_event` IDEMPOTENT_REPLAY 不推进。有界（一个 int）、单调（只增）、幂等 replay 不推进。fenced port 据 writer 返回的**明确 `created` 标志**（禁止二次探测）裁决是否推进计数器。**round-2 P2-1 闭合**：(a) 计数器**持久化于 execution.core.v1 fence 的 `ingress_checkpoint`**（不是内存），在已锁 fence 行上按真实插入结果 `+1`；(b) **baseline = 0（部署后水位）**，不回填既有 event 实际计数（计数器仅用于 S3 部署后的迟到写检测，既有 event 由 purge scan 无条件覆盖，scan 是完备性事实源）；(c) `CompatibilityOutputService.stage` 等 writer 返回明确 `created: bool` 标志（复用既有 `created` 或新增），fenced port 仅在 `created=True` 时推进计数器，禁止「写后再查」二次探测。
- **epoch = Conversation `purge_revision`**（与 workspace 同）。
- **不伪造**：watermark/epoch/计数取真实 source 序号/token，不用可观察时间戳冒充。
- **原子性**：checkpoint 推进与正文写、receipt 同事务 commit；verdict 不推进 checkpoint。

**4. purge 清除动作（Spec §7.2，同事务、可重入、锁序与 writer 一致）**

purge 对单 Conversation 的 execution 清除沿用固定锁序：`Conversation row FOR UPDATE -> owner advisory lock(execution.core.v1) -> ErasureFence row FOR UPDATE -> owner aggregate rows`（AgentRun -> RunEvent -> CompatibilityOutput；Run 在 Conversation 行锁后取，与 workspace Message 的相对顺序按既有规则）。fence 缺失时在 owner lock 下建（Spec §5.1）。

清除动作（幂等，已 tombstone/no-op）：
- **terminal output suppress**：completed Run `output_publish_state` pending/published/dead_letter -> suppressed + 清 `terminal_output_ref/media_type/classification/message_id`（保留 digest/size）。对应 execution outbox publish 事件取消/suppress 归 execution.transport.v1（S4），S3 只做 `output_publish_state=suppressed` 投影 + dispatch deterministic 分类（§8），不清 transport owner payload。
- **terminal_reason + terminal_code 裁剪**（round-1 P1-3 + round-2 P1-3）：`terminal_reason` 与 `terminal_code` 都 -> 受控 redaction code（`agent_suppression_reasons` 白名单归一，未知 code 归一 fallback），保留 `terminal_result_digest`。
- **context snapshot 清除**：`context_snapshot_ref/digest/classification` -> NULL。
- **compatibility output 清除**：`reply_text/response_envelope` -> NULL + `payload_state=redacted`。
- **RunEvent payload tombstone**：`payload_inline` -> NULL + `payload_state=redacted`（seq 不变）。**external payload**：不清 `payload_ref`（归 external.payload.v1），blocked（§5）。
- **actor 匿名化**（round-1 P1-2 + round-2 P2-2）：`AgentRun.created_by` / `TurnInput.created_by` -> NULL + HMAC `actor_identity_digest`。**不复用 workspace 私有 `_actor_audit_digest`**；提取为 **composition/shared 公开版本化 helper**（`actor_erasure_secret` + `actor_erasure_secret_version` 派生，V1 冻结契约），workspace 与 execution 两 participant 共用，避免跨 context 私有依赖或双实现漂移。幂等：已 redacted + digest 已存 no-op。
- **redacted_reason 受控化**：一律走 `agent_suppression_reasons` 白名单 code，自由文本不落库（与 S2-D 一致）。
- **catalog refs 保留**：`agent_definition_version_id`/`runtime_profile_id` FK 不动（Spec §4.1）。

**5. final execution body scan（完成门禁，Spec §5.2/§7.2）**

ACK 前扫描该 Conversation 下 execution.core.v1 受管正文，**任一非零 -> 不得 ACK**。扫描谓词**无条件**覆盖 inline 与 external ref（不按 payload_state 分类跳过）：

- RunEvent with `payload_inline IS NOT NULL OR payload_ref IS NOT NULL`（**round-1 P1-4**：旧 scan 只计 `payload_state=inline`，漏 redacted 但仍带 ref 的行；CHECK 允许 `redacted/expired/archived` 带 ref。改为无条件统计任何非空 payload）。external ref 非零 -> execution 不能 ACK（external.payload.v1 S4 未安装），blocked（reason=`purge_owner_unavailable`）。
- completed Run with `output_publish_state != suppressed` 且 `terminal_output_ref IS NOT NULL`（un-suppressed terminal output）。
- Run with `context_snapshot_ref IS NOT NULL`（un-cleared context）。
- Run with `terminal_reason` 或 `terminal_code` 非受控 redaction code（un-redacted terminal reason/code，round-1 P1-3 + round-2 P1-3；scan 同时验证 code 与 reason 都在白名单）。
- CompatibilityOutput with `payload_state = present`（un-redacted）。
- Run with `created_by IS NOT NULL` 或 TurnInput with `created_by IS NOT NULL`（un-anonymized actor，round-1 P1-2）。

扫描结果（每类计数 + canonical digest）记入 owner `checkpoint_digest`。**扫描非零 -> 不得 ACK**，fence erasing->blocked + operation/checkpoint 记 blocked + scan digest（与 S2-D P1-5/P2-2 同模式，正常返回不抛异常）。external payload 非零 -> blocked（reason=`purge_owner_unavailable`）。

**6. participant ACK 与 fencing（Spec §5.1/§5.2，复用 S2-D/E 完整 fencing）**

`ExecutionErasureParticipant.erase_execution_body` 复用 `WorkspaceErasureParticipant` 的 operation/checkpoint fencing 模式（S2-D/E round-2/3/4/5）：
- `purge_operation_id` + `expected_operation_revision` 必填；`_load_verified_operation` 校验 conversation_id / purge_revision / lease_epoch / registry_digest / hold_revision_snapshot / operation revision CAS。
- `_load_verified_checkpoint` 校验 owner_version（取自 fence，不硬编码）/ capability_digest CAS。
- `_mark_operation_running` / `_record_blocked` / `_ack_owner_checkpoint` / `_repair_checkpoint_if_pending` 与 workspace 同语义（blocked 正常返回、reason change bump revision、erased fence 幂等重放修复 pending checkpoint + 三方一致、ACKed+blocked operation 修复 fall-through）。
- **多 owner operation 完成判定**：S3 只接 `execution.core.v1` 单 owner ACK；operation `completed` 判定需所有 snapshot owner acked（workspace.core.v1 + execution.core.v1 + 后续 transport/external/runtime，Spec §5.2）。S3 **不伪造 completed**；operation 完成判定归 S5 scheduler。S3 participant ACK 只推进 execution.core.v1 checkpoint -> acked。
- **ACK digest**：排序 `{owner_key, owner_version, purge_revision, 各类清除计数, body_scan_digest}` 的 canonical digest，不含正文/actor 明文（与 S2-D 同）。
- **锁序与 workspace participant 可组合**：execution.core.v1 与 workspace.core.v1 各自独立 fence 行 + owner advisory lock（不同 owner_key）；两 participant 都遵循 Conversation row -> owner lock -> fence -> aggregate rows，同一 Conversation 行锁串行，无 AB-BA。多 owner purge 的 coordinator 调用顺序（按 owner_key 字典序 `execution.core.v1` < `workspace.core.v1`）与跨 owner 聚合行锁序归 S5。

**7. RuntimeSessionBinding 处理（Spec §7.2，runtime.private.v1 边界）**

- `RuntimeSessionBinding.runtime_session_ref` 归 `runtime.private.v1`（S4 fake / 后续真实 Runtime eraser）。execution.core.v1 **不**清 `runtime_session_ref`、**不**关 binding（status -> closed/invalid）。
- execution.core.v1 ACK 前置：若 Conversation 有 binding 且 `runtime_session_ref IS NOT NULL`，execution.core.v1 blocked（reason=`purge_owner_unavailable`，runtime eraser 未安装）。runtime.private.v1 ACK 后 execution.core.v1 清本地 ref + 关 binding（S4 接力）。
- compatibility Run（`runtime_kind=compatibility`，无 binding）：execution.core.v1 可直接 ACK（无 runtime ref 阻塞）。当前 Direct RAG compatibility 路径全走 compatibility Run，S3 可完整闭环。

**8. dispatch_output LateBodyWriteRejectedError 分类（Spec §6.2/§9.2）**

- `AgentBridgeDispatcher.dispatch_output`（execution outbox -> workspace assistant message publish）写 workspace 正文时，若 `workspace.core.v1` fence 非 active（purge 进行中）-> `LateBodyWriteRejectedError`。
- S3 将该错误分类为 **deterministic**（不可重试）：outbox publish 事件不盲重试，标记稳定 reason code（`late_body_write_rejected`，Spec §9.2），不把 purge 路径上的迟到 publish 当瞬时故障重试。原因：Conversation 已在 purge，重试永远无法写入正文（R1-AC8 不盲重试正文写）。
- **不清 transport owner**（S4）：dispatch_output 的 deterministic 分类只影响 outbox 事件重试策略与 reason code，不清 execution.transport.v1 owner 正文（outbox `payload_inline/payload_ref` 清理 + `status=suppressed` 归 S4 transport participant）。S3 的 outbox 事件在 deterministic 分类后由 S4 transport participant 在 purge 时统一 suppress。

**9. 30 天 purge 与 365 天 prune 拆分（round-1 P2-6）**

- **S3 交付 Conversation-scoped execution body eraser**（30 天 purge 调用）：清 execution.core.v1 受管正文 + actor 匿名化，ACK 推进 owner checkpoint。这是 S3 的唯一 participant 语义。
- **S6 交付 Run-scoped envelope prune worker**（365 天）：删除 Run aggregate（envelope + events），保留 catalog refs。S6 是独立 worker，**不**与 S3 共用同一 participant 语义；可复用底层原语（fence/lock/scan），但生命周期入口、retention 语义、blocked 条件各自定义。
- **S3 的 blocked 条件**（purge 前置，30 天）：state=deleted + now>=purge_after + purged_at IS NULL（PostgreSQL `clock_timestamp()` 锁后采样）；该 Conversation 全部 Run 终态（非终态 -> blocked，reason=`purge_blocked_by_unresolved_action`）。`outcome_unknown`/未解决审批目前 no-op 守卫（E1 无 Tool/Approval），future-proofing。
- **catalog refs 不删**：purge 与 prune 都不删 `AgentDefinitionVersion`/`RuntimeProfile`（tenant catalog，Spec §4.1）。

**10. 明确不做（边界）**

- 不实现 `execution.transport.v1` / `external.payload.v1` / `runtime.private.v1` eraser（S4）。
- 不启用 `conversation_purge_scheduler` 自动 claim 循环（S5）；participant 以受控入口形态供 scheduler 调用。
- 不实现 Pi/Runtime session destroy（S4）。
- 不实现 365 天 Run-scoped envelope prune worker（S6）。
- 不改 migration 034-037；S3-B 新增 migration 038（actor tombstone，§Schema）。
- 不实现完整 Approval/Tool/Artifact/Evidence 模型（plan §R1-S3 明确不做）。
- 不清 workspace.core.v1 正文（S2-D/E 已交付；S3 只清 execution.core.v1）。

**11. 竞态与不变量复核（复审重点）**

- **清除与并发执行 writer**：清除在 owner lock 内推进 fence active->erasing 后，执行 writer 经 `require_body_write_fence_for_update` 裁决即被拒（`LateBodyWriteRejectedError`），清除期间不得有新 execution 正文复活（与 S2-D writer-win/purge-win race 互补）。
- **清除与 restore**：fence 已离开 active 后 restore fail closed（S2-B 已锁）；清除开始后 restore 不得复活 execution 正文。
- **迟到 event**：fence erasing/erased 下旧 Runtime event 只能写无正文 tombstone/receipt，不重建正文（Spec §6.2）。Runtime binding 的 epoch/seq late-write 归 S4 RuntimeErasureParticipant conformance。
- **dispatch_output race**：publish 事件 dispatch 与 purge 竞争时，fence 裁决保证 publish 要么在 purge 前 commit（正文已写，purge scan 覆盖）、要么被拒（deterministic 不重试），不部分写。
- **fenced port 无旁路**：所有生产入口（`consume_turn_requested` create_run / Direct RAG / cancel API / Runtime ingest）经 fenced port，无直调 `RunCoordinator` writer 的生产路径（round-1 P1-1 + round-2 P1-2 重点；`submit_turn` 只写 workspace outbox，不是 create_run 入口）。
- **event 计数器持久化 + 幂等**：`ingest_runtime_event` IDEMPOTENT_REPLAY 不推进 run_event_payload 计数器；计数器持久化于 fence `ingress_checkpoint`，fenced port 据 writer `created` 标志在已锁 fence 行 `+1`，禁止二次探测（round-1 P1-5 + round-2 P2-1）。
- **跨 tenant/跨 actor/未知 owner/stale fencing token/版本漂移/registry drift/跨 owner source key** 全部 fail closed。
- **TurnInput 覆盖**：TurnInput `context_digest` 是 digest 非 body，`message_id` 是 workspace ref；但 `created_by` 是直接主体标识（round-1 P1-2，§4 actor 匿名化覆盖）。TurnInput 无 execution 受管正文 body，scan 不计 TurnInput body，但计其 `created_by`。
- **backfill 扩展**：S3 扩展 `agent_erasure_backfill.py` 为既有 Conversation 建 `execution.core.v1` baseline fence（与 workspace.core.v1 同 `create_fence_under_owner_lock` 路径，逐 owner）；writer 惰性首写建 fence；purge 遇缺失 fence 在 owner lock 下建（Spec §5.1 三重保障）。

**Schema 与 migration（round-1 P1-2 + round-2 P1-4/P2-3）**：

- **migration 038**（S3-B）：`agent_runs` + `agent_turn_inputs` 增 `actor_state`（present/redacted）+ `actor_identity_digest`（64-hex nullable），放宽 `created_by` 为 nullable + CHECK（present 强制 created_by 非空、redacted 允许 NULL 但保留 digest），与 S1 workspace Conversation/Message actor tombstone 同模式。expand-only。
- **downgrade 边界**（round-2 P2-3）：downgrade **仅在无 redacted 行时可逆**（还原 nullable/放宽）；已产生 redacted 行（anonymization 后）downgrade 必须 **fail closed 或 forward-fix**，**不得伪造 UUID 回填** `created_by`（匿名化不可逆，伪造会破坏审计真实性）。migration 测试需明确覆盖这两条路径。
- **应用层 tombstone 契约**（round-2 P1-4，不能只改 DB）：
  - **创建命令仍强制 UUID**：`create_run` / `create_run_with_root` 的 `CreateRunCommand.created_by` 保持必填（`AgentRun`/`TurnInput` 创建时 `actor_state=present`、`created_by` 非 NULL）。
  - **持久化 domain 显式允许 erased actor**：`AgentRun`/`TurnInput` domain 与 mapper 对 `created_by=None` + `actor_state=redacted` + `actor_identity_digest` 投影为 erased envelope（不抛 None 错误）。
  - **需要 actor 的命令遇 tombstone fail closed**：start/direct-RAG/取消等需要 `run.created_by` 的路径遇 `actor_state=redacted` -> fail closed（稳定错误码，不伪造 actor，不暴露 digest）。
  - **API 不暴露 digest**：Run/TurnInput query/projection 不返回 `actor_identity_digest`（仅内部审计）。
  - **负向测试**：purge 后 query/start/replay/cancel 对 tombstone Run 的行为（fail closed / 稳定 gone 语义，不泄露 digest、不复活 actor）。
- **registry**（S3-B）：`execution.core.v1` 增 `actor_identity` capability，**保持 `erase_available=False`**（round-2 P1-1）；S3-D 翻 `erase_available=True`。

**S3 实施 PR 拆分**（按复审建议顺序，每 PR 独立复审）：

- **S3-A**（本 PR #515）：契约注记/plan delta（含 round-1/round-2 修订）。
- **S3-B**：Schema 与基础契约 PR - migration 038（actor tombstone + 应用层 tombstone 契约 + downgrade 边界）、owner/source key 闭集映射、registry 增 `actor_identity` capability（**`erase_available` 保持 False**，round-2 P1-1）、提取 shared actor digest helper、backfill 数据矩阵。
- **S3-C**：Writer fence PR - composition-owned fenced execution port，注入 `consume_turn_requested`（create_run 真实入口，round-2 P1-2）/Direct RAG/cancel API/Runtime ingest；禁止生产路径直调未 fenced writer；覆盖全部 implicit/explicit RunEvent writer；writer 返回 `created` 标志驱动 event 计数器。
- **S3-D**：ExecutionErasureParticipant PR - terminal（output+reason+code）/context/compatibility/event/actor 清除、final scan（无条件 `payload_inline`/`payload_ref` + actor + terminal_reason + terminal_code）、external/runtime blocked、完整 operation/checkpoint CAS、幂等 repair、**翻 `erase_available=True`**（与 participant/scan/ACK 同 commit）。
- **S3-E**：Dispatch、竞态与收口 PR - deterministic late-write 分类、backfill、writer-win/purge-win、取消/terminal/runtime race、变异测试、docs closeout。

**验证**：S3 专项（terminal suppress + terminal_reason+code 裁剪 + context/compatibility/event tombstone + actor 匿名化断言、envelope/digest 保留、body scan 无条件覆盖 `payload_inline`/`payload_ref` + actor + terminal_reason+code、ACK digest 契约、external payload blocked、runtime binding blocked、compatibility Run 可 ACK、dispatch_output deterministic 分类、fenced port 无旁路（含 `consume_turn_requested` 真实 create_run 入口）、event 计数器持久化+baseline 0+`created` 标志、迟到 event tombstone、跨 tenant/actor fail closed、catalog refs 保留、非终态 Run blocked、migration 038 往返 + downgrade 边界（redacted 行 fail closed/forward-fix）+ 应用层 tombstone 契约（创建强制 UUID / domain 允许 erased / 需 actor 命令 fail closed / API 不暴露 digest / purge 后 query/start/replay 负向测试）+ shared actor digest helper 双 participant 共用）+ execution/workspace/control-plane 回归全绿；新增测试经变异验证；ruff 0；mypy baseline 0 回归；docs gate + git diff --check 通过。本轮（S3-A）纯文档；S3-B 起新增 migration 038（不改 034-037）；不启用 purge scheduler、不进 S4。

#### S3-D round-1 复审修订（2026-08-03，独立 `max` round 1 返修落点）

S3-D 首次实现（PR #522）后独立 `max` 复审 P0/P1/P2/P3 = 0/7/2/0，**暂不可合并**。以下修订**优先于上面 S3 注记的对应旧陈述**，是 S3-D 返修实现的事实源。

- **P1-1 已 suppressed 的完整 terminal envelope 漏清 + 漏扫**：`ck_agent_run_terminal_output` 的第一分支允许 `output_publish_state='suppressed'` **同时保留完整** `terminal_output_ref/media_type/classification/message_id`（B1 suppress 审计路径产生的合法状态）。首实现的清除谓词 `output_publish_state != 'suppressed'` 与 scan 谓词 `output_publish_state != 'suppressed' AND terminal_output_ref IS NOT NULL` 都跳过这类行，purge 可在正文仍在时 ACK。修订为--**清除与 scan 都不按 `output_publish_state` 跳过**：清除覆盖全部 `status='completed'` 且仍携带 terminal output 正文字段的行（`terminal_output_ref IS NOT NULL OR terminal_output_media_type IS NOT NULL OR terminal_output_classification IS NOT NULL OR terminal_message_id IS NOT NULL`），一律转 tombstone 分支（保留 digest/size）；scan 用同一无条件谓词统计。反例（真实 PostgreSQL）：`status=completed, output_publish_state=suppressed, terminal_output_ref` 非空 -> 清除后四列 NULL、scan 归零；变异（恢复 `!= 'suppressed'` 过滤）必须击杀该测试。
- **P1-2 运行时 DROP/CREATE TRIGGER 造成跨 Conversation 死锁 + 部署权限风险**：首实现在 `_clear_event_payloads` 内对 `metaedu.agent_run_events` 运行时 `DROP TRIGGER -> UPDATE -> CREATE TRIGGER`。`DROP TRIGGER` 需表级 `ACCESS EXCLUSIVE`，而同事务早前的 event scan 已持 `ACCESS SHARE`；两个并发 eraser（不同 Conversation）会互相等待锁升级形成死锁，且普通运行角色未必有该表 DDL 权限。修订为--**禁止在运行时路径执行 DDL**；**新增 migration 039**（解除本 Slice「不新增 migration」约束，见下「Schema 与 migration 增补」）把 append-only 守卫函数改为**放行受控 purge tombstone 更新**的行级判定，运行期只做普通 `UPDATE`。验证：并发两 Conversation 同时 erase 无死锁；受限运行角色（无 DDL 权限）可完成 erase；正常 writer 路径的任意其他 UPDATE/DELETE 仍被守卫拒绝。
- **P1-3 Runtime binding blocker 漏未被 Run 引用的 binding**：首实现从 `AgentRunModel` join `RuntimeSessionBindingModel` 统计，只能看见被某个 Run 的 `runtime_binding_id` 引用的 binding。`RuntimeSessionBinding` 自身直接持有 `tenant_id + conversation_id`（models.py:182），可先于 Run 创建或不被任何 Run 引用，此时活跃 `runtime_session_ref` 被漏判，execution.core.v1 会错误 ACK（违反 §7 边界）。修订为--blocker **直接查 `RuntimeSessionBinding`**：`tenant_id = ? AND conversation_id = ? AND runtime_session_ref IS NOT NULL`，不经 AgentRun join。反例：建 binding 带 `runtime_session_ref` 但不建任何 Run -> blocked（reason=`purge_owner_unavailable`）；变异（改回 join AgentRun）必须击杀。
- **P1-4 operation 既未加锁也未限制可运行状态**：首实现 `_load_verified_operation` 无 `with_for_update()`（workspace 同名方法有），且状态谓词只拒 `cancelled/completed`。并发 scheduler 更新可与 revision 裁决竞态；`failed` operation 会穿透 `_mark_operation_running`（只处理 scheduled/blocked）继续执行全部清除并 ACK checkpoint，留下 `operation=failed / checkpoint=acked / fence=erased` 的矛盾三方事实。修订为--(a) `_load_verified_operation` 加 `.with_for_update()`；(b) 与 workspace 对齐，任何清除或状态变更前强制 `operation.state in {scheduled, running, blocked}`，否则 fail closed（`failed/cancelled/completed` 均拒）。反例：`failed` operation -> 抛错且零清除零 ACK；变异（放宽状态集合或去掉 FOR UPDATE）必须击杀。
- **P1-5 blocked 路径缺 Conversation 投影与 scan 证据**：首实现 `_record_blocked(operation, checkpoint, reason_code, now)` 既不接 `Conversation` 也不接 `ExecutionBodyScan`，故所有 blocked 路径（legal hold / 非终态 Run / external payload_ref / runtime binding / final scan 非零）都未投影 `Conversation.purge_state='blocked'`，也未把 scan digest 写入 `checkpoint.checkpoint_digest`，违反 S2-D/E round-4 P1-2 已冻结的「三方一致」与 P2-2「blocked 记 scan digest」。修订为--`_record_blocked` 与 workspace 对齐：接 `conversation` + `scan`，同事务置 `conversation.purge_state = BLOCKED` + `conversation.updated_at`，并把 `checkpoint.checkpoint_digest = scan.digest()`；重试成功路径（`_mark_operation_running` / ACK）恢复 `purge_state = RUNNING`。反例：每类 blocked 路径 commit 后 operation/checkpoint/conversation 三方一致且 `checkpoint_digest` 非空；blocked -> 重试 -> ACK 后 `purge_state=running`。
- **P1-6 ACK digest 的「各类清除计数」恒为零**：首实现 `_compute_ack_digest` 从**成功后的 final scan** 取 `cleared_*` / `anonymized_*`，而 ACK 的前置条件正是 `scan.total == 0`，故这些字段恒为 0，digest 不表达任何清除事实（与 §6「ACK digest 含各类清除计数」冲突；workspace 用的是独立 `WorkspaceErasureSummary` 真实计数）。**首实现的测试还固化了这一错误语义**（`test_s3d_execution_scan_ack.py:163`），返修须同步改测试。修订为--各清除动作返回**真实影响行数**（`rowcount` 或显式计数），聚合为显式 `ExecutionErasureSummary`（terminal outputs suppressed / terminal codes redacted / context snapshots cleared / compatibility outputs redacted / event payloads redacted / run actors anonymized / turn input actors anonymized），ACK digest = 该 summary + `body_scan.digest()` 的 canonical digest。反例：清除 N>0 行后 ACK digest 与「零清除」场景 digest **不同**；变异（把某项计数改回取自 final scan）必须击杀。
- **P1-7 registry 回归未随 `erase_available=True` 更新**：GitHub 全量 CI `1988 passed / 2 failed`，两个失败均为 `tests/composition/test_agent_erasure_registry.py` 仍断言 execution.core.v1 `erase_available is False`（S3-B 时点的正确断言）。修订为--与 participant/scan/ACK 同 commit 更新 `test_only_workspace_core_eraser_available_in_s2d`（改为 workspace + execution 双 eraser 可用，其余 owner 仍 False）与 `test_execution_core_has_actor_identity_capability`，并保留「其余 owner erase fail closed」断言强度。
- **P2-1 `_mark_operation_running` 不设 `started_at`；`_record_blocked` 同 reason 重复 bump revision**：与 workspace 冻结语义不一致（workspace 首次 running 设 `started_at`；已 blocked 且 reason 未变不 bump）。修订为--两处与 workspace 对齐（`started_at is None` 时设值；`state != blocked` 或 `failure_code != reason` 才 bump）。
- **P2-2 事实源过期**：工作台仍写「验证状态：待实现」；TD-032 基线记 `execution_erasure_participant.py` 1107 行（实际 1210）；PR #522 描述仍写测试与能力开关待补。修订为--返修落地同批更新工作台、TD-032 基线行数（按返修后实际值）与 PR 描述。

**Schema 与 migration 增补（S3-D，解除本 Slice 原「不改 migration 034-038 不新增」约束）**

- 原 S3 注记 §10 与 S3-D 任务约束写「不改 migration 034-037 / 不新增」。P1-2 证明该约束与「RunEvent payload tombstone」不可兼得：`agent_run_events` 的 append-only 守卫由 migration 030 的 `trg_agent_run_event_append_only` 强制，purge 要合法更新只有两条路——运行时 DDL（已证有死锁与权限缺陷）或迁移期改守卫。**本 Slice 定向解除该约束，仅允许新增 migration 039，仍不改 034-038。**
- **migration 039**：重定义 `metaedu.guard_agent_run_event_append_only()`，从「无条件 RAISE」改为**行级白名单**：仅当更新为受控 purge tombstone 形态（`payload_inline` 由非空转 NULL、`payload_state` 转 `redacted`，且 `seq/event_type/visibility/classification/payload_digest/payload_size/provenance/payload_ref` 全部不变）时放行，其余 UPDATE 与全部 DELETE 仍 RAISE（保持 E1 append-only 语义与 §1「seq 不变」不变量）。expand-only，不改表结构。
- **downgrade**：还原 030 的无条件 RAISE 版本。已产生的 tombstone 行不受影响（守卫只作用于新写），故 downgrade 无条件可逆——与 038 的「redacted 行 fail closed」边界不同，须在 migration 测试中明确区分并断言。
- **验证**：039 upgrade/downgrade/upgrade 往返；放行矩阵（合法 tombstone 更新通过 / 改 seq 被拒 / 改 payload_digest 被拒 / 清 payload_ref 被拒 / 任意 DELETE 被拒 / 非 purge 形态 UPDATE 被拒）；受限（无 DDL 权限）运行角色可完成 erase；两 Conversation 并发 erase 无死锁。

**S3-D 返修验证**：上述 7 项 P1 + 2 项 P2 各自反例 + 变异验证（逐项还原缺陷实现均应被测试击杀）+ S3-D 专项全绿 + S3-C writer fence/E2E 回归 + S2-D/E workspace participant 回归 + agent_execution/agent_control_plane/composition 回归 + migration 039 往返与守卫矩阵 + 全量 `pytest -m 'not external_network'` 0 failed + ruff 0 + mypy baseline 0 回归 + docs gate + `git diff --check`。本轮**新增 migration 039**（不改 034-038）、不启用 purge scheduler、不进 S3-E/S4。返修后重新提交独立 `max`/Codex 只读复审。

#### S3-D round-3 Codex 复审修订（2026-08-03，独立 Codex round 3 返修落点）

round-2 复审（P0/P1/P2/P3 = 0/1/5/2）已收口；本轮为 round-3 复审（P0/P1/P2/P3 = 0/1/3/1）的落点。原 checkpoint/replay 核心防线、operation repair、真实 `FOR UPDATE` 变异测试均已被复审确认有效，本轮不改动这些语义，只修订以下工程实现与验收方式。

- **P1 `_record_blocked` 原子 fail closed（先裁决后变更）**：`_record_blocked` 必须先完成 operation/checkpoint 的**全部**状态裁决，再修改任何 ORM 实体。fail-closed 异常不得依赖调用方 `rollback` 才维持原状态——`ValueError` 不会使 SQLAlchemy 事务失效，若先改 operation（state/revision/failure_code）再校验 checkpoint 并 raise，调用方捕获异常后 `commit` 会把「operation 已 blocked + revision 已 bump、checkpoint 仍 failed」的**部分复活**落库。**反例**：真实 PostgreSQL 下调用 `_record_blocked` 抛错后**不 rollback、直接 commit**，用**新 session** 重读并断言 operation/checkpoint/Conversation 三方均未变化；对该「裁决前移」做 mutation kill（把白名单移回 operation 赋值之后应被检出）。
- **P2-2 migration 039 验收必须经真实 migration entry point**：roundtrip 测试不得直接执行迁移模块的 SQL 常量（否则交换/清空 `upgrade()`/`downgrade()` 函数体仍绿）。须用真实 Alembic `op`（经 `Operations._install_proxy()` 绑定到专用连接的 `MigrationContext`）真实执行 `039 -> 038 -> 039`，每一步断言 `alembic_version` 与 RunEvent guard 行为（downgrade 后 tombstone 被无条件 RAISE、upgrade 后重新放行）；并验证破坏/交换 `upgrade()`/`downgrade()` 后测试转红。
- **P2-3「erase 无运行时 DDL」由实际 SQL 执行轨迹证明**：静态 AST 只能作为补充（只覆盖直接作调用实参的字符串常量，变量 SQL、动态拼接及 helper 发出的 SQL 都能绕过）。须在真实 participant erase 外挂 SQLAlchemy `before_cursor_execute`，捕获实际执行的全部语句，断言不存在 `DROP/CREATE/ALTER` 等 DDL。保留双 Conversation 并发 erase 无死锁测试。
- **事实同步**：current-work 更新为 round-3 返修状态及最新 `2016 passed / 0 failed`、三路 CI 全绿基线；TD-032 participant 行数更新为实际值；修正 `agent_erasure_registry.py` 两处仍称「只有 workspace 开启」的旧注释；不提前移入「最近完成」。

**验证**：S3-D 专项 + migration 039 往返 + P1 catch+commit 反例及 mutation kill + S3-C/S2-D/E 邻近回归 + 全量 `pytest -m 'not external_network'` 0 failed + ruff + mypy baseline + docs gate + `git diff --check`；推送后等同一 HEAD 三路 CI 全绿。不扩范围、不进 S3-E/S4、不合并，返修后提交独立 Codex 轻量复核。

#### S3-E 实施落点（2026-08-04，Dispatch、竞态与收口）

S3-E 按 §553 交付 S3 收口：deterministic late-write 分类、backfill 钉住、writer-win/purge-win、迟到 event、计数器幂等、无旁路守卫、变异验证。冻结以下工程决策作为复审事实源。**不改 migration 034-039、不进 S4、不启用 purge scheduler、不重开 erase_available（S3-D 已翻 True）。**

- **§8 dispatch_output deterministic late-write 分类（本 Slice 唯一生产改动）**：`AgentBridgeDispatcher.dispatch_output` 捕获 `LateBodyWriteRejectedError`（workspace.core.v1 fence 非 active，`project_assistant_message` 抛出）时**不走** transient 的 `_record_output_failure` backoff 重试，改走新增的 `_record_output_late_write_rejected` -> `AgentExecutionBridgeService.mark_output_late_write_rejected` -> 复用 `suppress_output_projection` 落 **deterministic 终态**：outbox 事件 `status='cancelled'`（脱离 pending/claimed 可重试集）、`decision_reason='late_body_write_rejected'`（受控 code，经 `suppression_reason_code` 归一）、`decision_digest` 落库、`Run.output_publish_state='suppressed'`、清零在途 claim（`claimed_by`/`claimed_at`），**不排 `next_attempt_at`、不重试**。边界（不清 transport owner，S4）：`suppress_output_projection` 不动 outbox `payload_inline`/`payload_ref`。transient 故障（非 `LateBodyWriteRejectedError`）维持既有 backoff 重试语义不变。**反例**：erased fence 下 dispatch_output -> outbox `cancelled` + reason code + 不重回可重试集（变异：移除 deterministic 分支退回 backoff -> `cancelled` 退化为 `pending`，转红）；transient 对照组仍 `pending` 重试。
- **§11 backfill 钉住 execution fence（无生产改动）**：backfill 为注册表驱动（`for owner in owner_registry()`），execution.core.v1 自 S3-B 注册即被自动覆盖，与 workspace 同 `ensure_fence_under_owner_lock` 锁序。本 Slice **仅补钉住测试** `test_backfill_creates_execution_core_fence`（显式断言每个既有 Conversation 存在 `owner_key='execution.core.v1'` 的 active fence，与 `len(owner_registry())` 推导解耦——变异：从 backfill owner 循环剔除 execution owner -> 转红）+ 更新 `agent_erasure_backfill.py` 模块 docstring（原「R1-S1/S2-C 只补 fence」改为记录注册表驱动覆盖 execution 的事实）。
- **§6 fenced port 无旁路守卫（行为断言版，替代 round-5 被删的脆弱 AST 测试）**：静态字符串/AST 断言检出不了「接了 port 却绕过裁决」（变异 SURVIVED，已实证），改用**行为守卫** `test_s3e_fenced_port_no_bypass.py`：execution fence 翻 erasing 后，production 写正文入口 `start_run` / `consume_turn_event`（create_run 真实入口，round-2 P1-2）必须实抛 `LateBodyWriteRejectedError` 且报错来自 fence 裁决。若绕过 fence 直调 `RunCoordinator` writer，写会成功或抛下游 `RunConflictError` 而非 fence 拒绝 -> 转红（变异 KILLED）。execution 应用层保持纯执行逻辑（不 import erasure/fence），fence 裁决只在 composition 层。
- **§11 执行侧 race/幂等测试**（`test_s3e_execution_race.py`，对照 workspace `test_writer_fence.py` 同构 race）：
  - **purge-win race**（erasing/erased 参数化）：purge 按锁序（Conversation 行锁 -> owner lock -> fence CAS）持锁暂停，writer（`fenced_append_event`）在同一锁链上串行等待、不得插队；purge 提交非 active fence 后 writer fail closed（`LateBodyWriteRejectedError`），正文不复活（无新 RunEvent/AgentRun、seed terminal output 未改写）。
  - **writer-win race**：writer 过 active fence 裁决后持锁暂停，真实 `ExecutionErasureParticipant.erase_execution_body` 在 Conversation 行锁上等待不插队；writer 提交完整 completed Run 链（create->start->running->commit_terminal + context snapshot）后 purge 接管，清除 + final scan 覆盖这份迟到正文（terminal output/context/event payload/actor 归零、tombstone digest 保留、terminal_code/reason 归一受控白名单、fence erased + ACK digest 一致），`outcome.erased=True`。
  - **迟到 runtime event**（erasing/erased 参数化）：fence 非 active 下 `fenced_ingest_runtime_event` 抛 `LateBodyWriteRejectedError`、不重建正文（无新 RunEvent、seed 正文未改写）、不推进 `run_event_payload` watermark。
  - **IDEMPOTENT_REPLAY 不推进计数器**：真实 PG 同一 runtime event ingest 两次，第二次 `idempotent_replay=True` 不推进，`run_event_payload` watermark 精确 +1（不 +2），与 `execution_fenced_port.py` 的 `if not result.idempotent_replay` 一致。
- **变异验证**：本 Slice 每个改动/测试配反例——§8 移除 deterministic 分支转红；backfill 剔除 execution owner 转红；无旁路绕过 fence 转红。race 测试的不变量由 S3-D 已变异验证的 participant/scan/ACK 防线承载（本 Slice 不重开）。

**验证**：S3-E 新增测试（§8 2 + 无旁路 2 + race 6 + backfill 1）+ S3-D/S3-C/S2-D/E 邻近回归 + control-plane/composition 全量 + 全量 `pytest -m 'not external_network'` 0 failed + ruff 0 + mypy baseline 0 回归 + docs gate + `git diff --check`；推送后等同一 HEAD 三路 CI 全绿。返修后提交独立 `max`/Codex 复审。

#### S3-E round-1 复审修订（2026-08-04，独立 Codex round 1 返修落点）

S3-E 首次实现（PR #524）后独立复审 P0/P1/P2/P3 = 0/1/2/0，**暂不可合并**。以下修订**优先于上面 S3-E 落点的对应旧陈述**，是返修实现的事实源。

- **P1 专用幂等 late-write terminalize 原语（替代复用 `suppress_output_projection`）**：首实现复用人工 `suppress_output_projection`，它只接受 Run `output_publish_state ∈ {pending, dead_letter}`。但 **S3-D eraser 先把 completed Run 翻 `suppressed` 并保留 execution outbox 给 S4**；此后迟到的 `dispatch_output` 在 workspace fence 抛 `LateBodyWriteRejectedError`，而复用的原语遇 already-suppressed Run 抛 `ExecutionIntegrationConflictError`，outbox 卡 `claimed`、租约到期后继续重试——违反 deterministic 不重试契约。修订为--新增**专用幂等**原语 `terminalize_output_late_write`：接受 Run 已 `suppressed`（S3-D 先行）或 `pending/dead_letter`（publish 飞行中被 purge 拦截），仍把当前 outbox 事件置 `cancelled`、写 `decision_reason='late_body_write_rejected'` + `decision_digest`、清 claim、保持 `payload_inline`/`payload_ref` 不变（S4 边界）；Run 已 `suppressed` 时不再改 `output_publish_state`（幂等）。**反例**：构造 S3-D 终态（Run suppressed + outbox 保留 pending）后 dispatch -> `cancelled` + reason code + 不重回可重试集（变异：原语仍按 `suppress_output_projection` 拒 already-suppressed -> 转红）。**附带边界（round-2 已删除，见下）**：round-1 曾误记「S3-D erase 在 Run 回 `pending` 时违反 `ck_agent_run_terminal_output`，归 S4」——复审者用真实 participant 复现证明该假设错误（真实 eraser 原子设置 suppressed 并清字段，无 CHECK 冲突），round-2 已删除此 S4 defer，详见下节。
- **P2 terminalize 必须绑定当前 delivery claim（claim CAS）**：首实现的 deterministic 落库只按 `tenant_id/run_id` 选行，未像 `acknowledge_output`/`record_output_failure` 校验 `event_id/payload_digest/attempt_count/claimant_id`；过期 worker 可清掉后来 worker 的 claim 或覆盖同期人工裁决。修订为--专用原语复用现有 claim CAS：校验 `row.payload_digest == payload_digest`、`row.status == 'claimed'`、`row.attempt_count == expected_attempt`、`row.claimed_by == claimant_id`，不满足 fail closed（`ExecutionIntegrationConflictError`），不盲写。**反例**：attempt N 被 attempt N+1 接管后，旧 worker（attempt N）的 terminalize 被拒、不覆盖新 claim（变异：去掉 attempt/claimant CAS -> 转红）。
- **P2 PR HEAD 必须含最新工作台交接状态**：评审时本地 `current-work.md` 有未提交修改、PR HEAD 仍是旧「全量回归绿 -> 提交」状态。修订为--返修落地同批提交工作台与全部事实源，保持 PR HEAD 即最新交接状态、工作树干净。

**S3-E round-1 返修验证**：P1/P2 反例（真实 S3-D eraser 先行 + stale-claim 接管）+ 各 mutation kill + S3-E/S3-D/S3-C 邻近回归 + 全量 `pytest -m 'not external_network'` 0 failed + ruff + mypy baseline + docs gate + `git diff --check`；推送后等同一 HEAD 三路 CI 全绿。不扩范围、不进 S4、不合并，返修后提交独立 `max`/Codex 轻量复核。

#### S3-E round-2 复审修订（2026-08-04，独立 Codex round 2 返修落点）

S3-E round-1 返修后独立复审 P0/P1/P2/P3 = 0/1/2/0，**暂不可合并**。以下修订**优先于上面 round-1 落点的对应旧陈述**。

- **P1 非 `claimed` 状态不得无条件当幂等成功**：round-1 实现在校验 attempt/claimant/Run 状态前，对所有 `row.status != 'claimed'` 直接 `return`（幂等 no-op）。真实 PostgreSQL 复现：worker A claim attempt 1，worker B 接管 attempt 2 后 transient 回 `pending`，A 的 stale terminalize 静默成功，但事件仍 `pending`、`decision_reason=None`，继续进重试集——违反 deterministic 终态契约。修订为--**仅对完整匹配的既有 late-write 终态 no-op**（`status='cancelled'` AND `decision_reason='late_body_write_rejected'` AND `decision_digest` 为本事件重算值匹配 AND Run `output_publish_state='suppressed'`）；`pending/dead_letter/published/其他 cancelled` 一律 fail closed（`ExecutionIntegrationConflictError`），不静默吞掉。**反例**：`claim N -> takeover N+1 -> transient 回 pending -> stale terminalize（attempt N）` 必须 fail closed 且事件仍 `pending`（变异：恢复「非 claimed 即 return」-> 转红）。
- **P2 P1 反例必须跑真实 S3-D eraser（删除错误 S4 defer）**：round-1 测试手工清字段 + 设 `suppressed` 造状态，未调 `ExecutionErasureParticipant`；并基于「真实 eraser 在 completed+pending 下触发 `ck_agent_run_terminal_output` 冲突」的**错误假设**在 plan/工作台记了 S4 defer。复审者用真实 participant 复现 `completed + output_publish_state=pending`：`erased=True / output_publish_state=suppressed / terminal_output_ref=None`，**无 CHECK 冲突**（真实 eraser 在同一 UPDATE 原子设置 suppressed 并清字段）。修订为--P1 反例改调真实 `ExecutionErasureParticipant.erase_execution_body`（completed+pending Run -> erase -> suppressed）后再 dispatch；**删除 plan/工作台中错误的 S4 defer 陈述**。
- **P2 交接事实稳定表述（不钉漂移 SHA/时长）**：round-1 工作台写 PR HEAD `31e25994`、Backend 9m41s，实际 HEAD `509eb4e2`、9m25s；plan 又声明「全量 0 failed」与工作台记录的 clean-main 27 failures 冲突。修订为--工作台/plan 用稳定非自指表述（如「三路 CI 全绿，对应 PR #524 当前 HEAD」，不钉具体 SHA/时长），并**如实区分**「三路 CI 全绿」与「本地全量套件存在 main 预存 flake」。
- **全量 flake 登记 TD-091（独立处理，不混入 S3-E；TD-080 编号已占用）**：早前观测干净 main（无 S3-E）全量多失败（含 test_ai_chat / direct_rag / e2e / turn_bridge / writer_fence 非确定性隔离 flake），但当时未落盘逐条 node ID 日志。TD-091 已按复核要求如实登记：clean-main 基线 `f1002bea`、完整命令、失败签名集合、疑似共享 PG 污染疑点、**以及本轮在 f1002bea 独立 worktree 干净复跑为 2016 passed / 0 failed（早前 27 failed 无法复现）的如实修正**；完成标准「连续 3 次全量 hermetic 回归无重跑通过」+ 失败可复现性标定。

**S3-E round-2 返修验证**：P1 stale-takeover-pending 反例 + P1 真实 eraser 反例 + 各 mutation kill + S3-E/S3-D/S3-C 邻近回归 + 全量 `pytest -m 'not external_network'`（区分 CI 全绿与本地 main 预存 flake）+ ruff + mypy baseline + docs gate + `git diff --check`；推送后等同一 HEAD 三路 CI 全绿。不扩范围、不进 S4、不合并，返修后提交独立 `max`/Codex 轻量复核。

### R1-S4：Transport owner、external payload 与迟到写

**复杂度/执行**：极高，Sol `xhigh`；GLM-5.2 `max` 独立故障审查。

交付：

- [ ] 为 conversation-scoped workspace/execution inbox/outbox 增加结构化 owner scope 与 producer fence revision，并可靠回填既有事件。
- [ ] `workspace.transport.v1` / `execution.transport.v1` 实现 claim 外短事务、Guard 内 cancel/suppress/tombstone 和 receipt ACK。
- [ ] old/missing producer revision、ACK 丢失、claimed lease 过期和重复事件不得复活正文。
- [ ] 增加 external staging/reference lifecycle port 和 `external.payload.v1` participant；已知 DB-local ref 可实装，未知 scheme/erase unknown 必须 blocked。
- [ ] 增加 `RuntimeErasureParticipant` conformance fake，覆盖 session ref、epoch/seq late write、destroy ACK 重放；不把 fake 声称为 Pi Worker 完成。

明确不做：Pi/ACP/LangGraph Adapter；实际 Runtime spool 验收归 REQ-043。

验证：每个 inbox/outbox crash point、claim 与 purge lock inversion、历史回填不确定行、external erase timeout/outcome unknown、旧 runtime seq tombstone。

#### R1-S4-A 契约冻结（2026-08-04，先于代码冻结，纯文档，不写业务代码）

进入条件已满足：R1-S3 全部合并（S3-E PR #524 `916699db`）、main 干净、migration head=`039`、`LateBodyWriteRejectedError`/`LateOutputReadRejectedError` 已按 deterministic suppression 处理（S3-E）。本轮盘点 transport/external 边界并冻结契约，作为后续 S4-B~F 实现与独立 `max`/Codex 复审的事实源。**不改 migration 034-039、不写业务代码、不启用 purge scheduler。**

**1. transport owner 与表映射（4 张 integration 表，均已存在）**

| owner | 表 | 正文列 | receipt 列 | 当前聚合溯源列 |
|-------|----|--------|-----------|----------------|
| `workspace.transport.v1` | `agent_workspace_outbox` | `payload_inline`/`payload_ref`（≤32KB inline） | — | `aggregate_type='workspace.message'` + `aggregate_id=message_id`（**非** conversation_id） |
| `workspace.transport.v1` | `agent_workspace_inbox` | — | `payload_digest`（仅 digest，无正文） | `consumer_name` + `event_id`（无 conversation 列） |
| `execution.transport.v1` | `agent_execution_outbox` | `payload_inline`/`payload_ref` | — | `aggregate_type='execution.run'` + `aggregate_id=run_id`（**非** conversation_id） |
| `execution.transport.v1` | `agent_execution_inbox` | — | `payload_digest`（仅 digest） | `consumer_name` + `event_id`（无 conversation 列） |

registry 已冻结 owner 定义（`erase_available=False`，S4 翻 True）：`workspace.transport.v1` capabilities `workspace_outbox_payload`/`workspace_inbox_receipt`；`execution.transport.v1` capabilities `execution_outbox_payload`/`execution_inbox_receipt`；`external.payload.v1` capabilities `external_object_ref`/`staging_object`；`runtime.private.v1` capabilities `runtime_session_ref`/`runtime_spool`。

**2. 冻结决策**

- **D1 结构化 owner scope**：4 张 inbox/outbox 增 `conversation_id`（nullable，expand-only）+ `producer_purge_revision`（nullable BigInteger）。outbox 现有 `aggregate_type`+`aggregate_id` 是 message_id/run_id，**不是** conversation scope，purge 时无法稳定溯源 -> 必须新增列；inbox 当前无 conversation 溯源，同样新增。
- **D2 producer epoch 用 `Conversation.purge_revision`（不变量 2）+ 完整传播链（transport metadata，不改 V1 payload digest）**：新事件在产生同事务快照当时 `Conversation.purge_revision` 写入 `producer_purge_revision`；**不得**用 fence 行 CAS `revision` 冒充。消费/清除阶段 old/missing producer revision -> 只能 tombstone/reconcile，不得复活正文。**传播链冻结为**：`Conversation snapshot -> outbox metadata -> Claimed* envelope -> inbox metadata`。现状缺口：`ClaimedWorkspaceEvent`/`ClaimedExecutionEvent` 不携带 producer revision，V1 event schema 也无该字段，consumer 无法稳定写入 inbox。修订为--`producer_purge_revision` 作为 **transport metadata** 在 outbox 行持久化、claim 时装入 `Claimed*` envelope、consumer 消费时写入 inbox metadata；**不并入 V1 event payload**（避免静默改变 `integration_event_digest`/payload digest）。Guard 内消费/清除阶段必须 CAS 校验 `event_id` + `payload_digest` + `attempt_count` + `claimant_id` + `conversation_id` + `producer_purge_revision` 六元组，不符 fail closed。
- **D3 历史不确定行三态分类（不变量 3，替代「阻止对应 Conversation purge」的不可实现表述）**：backfill 无法可靠回填 owner scope 时按可溯源程度分三类，**均 fail closed，不静默丢弃、不猜 UUID**：
  - **已知候选 Conversation**（aggregate 可唯一映射到现存 Conversation）：阻塞**该 Conversation** 的 purge，进入具名 reconcile。
  - **scope 真正未知**（无法确定对应 Conversation）：进入 **tenant-scoped reconcile ledger**，并**阻断该 tenant 的 scheduler/canary enable**（S5 门禁读取此 ledger，存在未决项即 fail closed）。
  - **Conversation 已物理删除**：走**具名 orphan transport/external reconcile**（记录原 event/aggregate/tenant 溯源，不重建正文），**不猜 UUID**、不并入任何现存 Conversation。
- **D4 suppressed/cancelled envelope tombstone（不变量 4）**：transport 清除 = 清 `payload_inline`/`payload_ref`，**保留** `payload_digest`；禁止 `{}`、空串、伪 ref。与 S1 `ck_agent_*_outbox_payload` 的 `suppressed` 分支一致（清正文保留 digest）。**inbox receipt tombstone 表达（冻结）**：现有 `ck_agent_*_inbox_status` 仅允许 `processing/consumed/rejected`，无 tombstone 态。采用**保留现有 `status` 集合 + 新增独立 tombstone marker + digest envelope**（S4-B expand-only 新增列，如 `receipt_tombstone_state`/`receipt_tombstone_digest`），**不改** `processing/consumed/rejected` 语义、不新增 inbox status 枚举值；receipt 本就只有 digest 无正文，tombstone 标记 + 既有 `payload_digest` 即满足「保留 digest、禁空占位」。
- **D5 external ref 状态机与 ledger（覆盖所有 ref-bearing source + 清除顺序）**：**所有** `payload_ref` 承载点都是 external object 引用——`RunEvent.payload_ref`、`agent_execution_outbox.payload_ref`、**`agent_workspace_outbox.payload_ref`**（先前仅点名前两者，workspace outbox 同有 `payload_ref`，一并冻结）。新增 external ref ledger（external.payload.v1 owner）记录 ref/scheme/state，覆盖全部 ref-bearing source。**清除顺序冻结**：先登记/删除 external object 并取得 receipt，**再**清 transport DB ref——避免对象失去追踪入口（先清 DB ref 会让 external object 成为无溯源孤儿）。erase 语义：`known DB-local ref` 可实装删除并 ACK；`unknown scheme` / `erase outcome unknown` / `timeout` / `digest mismatch` 一律 **blocked（不变量 5），不得 ACK**。S3-D 已在 execution.core.v1 把现存 `payload_ref`/`runtime_session_ref` 判 `purge_owner_unavailable` blocked 移交 S4。
- **D6 transport/external 部分 ACK 不得标 completed（不变量 6）**：`workspace.transport.v1`/`execution.transport.v1`/`external.payload.v1` 各自 ACK；任一 owner 未 ACK，整个 purge operation 不得写 `purge_state=completed`。沿用 S1 operation/checkpoint 完成判定。
- **D7 Runtime fake 只证明协议（不变量 7）**：`RuntimeErasureParticipant` conformance fake 覆盖 session ref、epoch/seq late write、destroy ACK 重放；`runtime.private.v1` `erase_available` 仍 **False**，fake 不冒充 Pi/ACP/LangGraph 或真实 spool 已完成。
- **D8 claim 锁与 Guard 顺序（不变量 1，现状已合规，冻结保持）**：claim 在独立短事务（`_claim_output`/`_claim_turn` 各自 `session.begin()`，`skip_locked`），**不持 outbox row lock 等待 Guard**；消费在另一事务（`consume_output_event`/`consume_turn_event`）按 Guard -> Conversation 行锁（`lock_output_conversation`/`lock_projection_conversation`）-> owner lock -> fence 重验。S4-C/D 的 claim 外短事务 + Guard 内 cancel/suppress/tombstone 必须保持此顺序，不得引入 AB-BA。**锁链矩阵扩展（S4-B 复核 #锁序，加入 transport/external aggregate 集合 advisory lock）**：transport/external ledger 写路径（登记/推进 reconcile issue、重算行内投影）在 owner/fence 之后还须取**源行集合 advisory lock**（最内层 owner aggregate 位置，key 用独立前缀 `metaedu.agent.transport.agg.v1\x00` 与 guard/owner 分域），唯一全局顺序冻结为 `Guard -> Conversation 行锁 -> owner advisory lock -> fence 重验 -> **集合 advisory lock** -> 源 transport 行 FOR UPDATE 投影写`；任何路径不得在此链之前获取集合锁（禁止 `aggregate -> Guard` 与 `Guard -> owner/fence -> aggregate` 反向等待）；纯 backfill/运维路径不经 Guard/owner 时只取集合锁、顺序一致。集合锁为 S4-B 新增，与既有 guard/owner lock 同一 PostgreSQL 单参数 advisory namespace 但 key 输出域隔离（不同版本前缀）。

**3. 明确不做（S4-A 边界）**：不写 schema/migration（S4-B）；不改 writer/claim 代码（S4-C）；不实现 transport/external/runtime participant（S4-D/E）；不做 fault 矩阵（S4-F）；不启用 purge scheduler（S5）；不实现真实 Pi Worker、云对象存储生产 adapter、Approval/Tool/Artifact/Evidence。

**4. 后续拆分与 PR 顺序（不变量：禁止单超大 PR，S2-D/E 7 轮复审教训）**：`S4-A/B`（schema+backfill）、`S4-C/D`（writer+claim fence + transport participant）、`S4-E/F`（external+runtime fake + fault）、docs closeout，至少 4 个 PR。

**S4-A 验证**：纯文档；docs gate + `git diff --check` 通过；三路 CI 全绿。返修后提交独立 `max`/Codex 复审。

**S4-A round-1 复审修订（2026-08-04，独立复核 P0/P1/P2/P3=0/2/3/0）**：复核确认总体方向正确、属契约补全（不重做架构）。上述 D2/D3/D4/D5 已按复核意见就地修订（D2 补完整 epoch 传播链 + 六元组 CAS；D3 改三态分类替代不可实现的「阻止对应 Conversation purge」；D4 冻结 inbox tombstone 为独立 marker + digest envelope；D5 补 workspace outbox `payload_ref` 并冻结「先删 external object 取 receipt、再清 transport DB ref」顺序）。P2 工作台交接状态过期问题已同步修正（PR HEAD 与三路 CI 全绿如实回填）。修订后仅需一次轻量 diff 复核。

#### R1-S4-B Schema + Backfill 契约冻结（2026-08-04，先于代码冻结，纯文档）

按 S4-A D1-D8 冻结契约细化 schema 与 backfill。**本 delta 只写文档：不创建 migration 040、不改业务代码、不启用 scheduler；`erase_available` 在 S4-B 全程保持 `False`。** migration 034-039 已冻结，S4-B 新增 `040`（expand-only）。命名/类型沿现有约定（`agent_*` 表、`metaedu` schema、BigInteger revision、64-hex digest、`ck_/uq_/ix_/fk_` 前缀）。

**B1. migration 040 精确 schema（全部 nullable / expand-only，不收紧既有约束）**

*(a) 4 张既有 inbox/outbox 各增 3 列（全部 nullable，无默认值回填在 backfill 完成前保持 NULL）：*

| 列 | 类型 | 约束 | 说明 |
|----|------|------|------|
| `conversation_id` | `UUID` NULL | 见 (b) 部分唯一索引 + 条件 FK | 结构化 owner scope（D1） |
| `producer_purge_revision` | `BigInteger` NULL | `ck_*_producer_purge_revision`: `producer_purge_revision IS NULL OR producer_purge_revision >= 0` | 生产时 `Conversation.purge_revision` 快照（D2）；历史未知保持 NULL |
| `scope_reconcile_state` | `String(20)` NULL | `ck_*_scope_reconcile_state`: `scope_reconcile_state IS NULL OR scope_reconcile_state IN ('pending','reconciled','orphan')` | D3 三态回填结果标记；NULL=未回填/新写已带 scope |

涉及表：`agent_workspace_outbox`、`agent_workspace_inbox`、`agent_execution_outbox`、`agent_execution_inbox`。

*(b) 部分唯一索引（防 backfill/新写并发产生重复 scope 行；新写未接线前仍可能 NULL，故为部分索引，见 B7）：*

```text
uq_agent_ws_outbox_scope    ON agent_workspace_outbox  (tenant_id, conversation_id, event_type, aggregate_id) WHERE conversation_id IS NOT NULL
uq_agent_exec_outbox_scope  ON agent_execution_outbox  (tenant_id, conversation_id, event_type, aggregate_id) WHERE conversation_id IS NOT NULL
uq_agent_ws_inbox_scope     ON agent_workspace_inbox   (tenant_id, conversation_id, consumer_name, event_id)  WHERE conversation_id IS NOT NULL
uq_agent_exec_inbox_scope   ON agent_execution_inbox   (tenant_id, conversation_id, consumer_name, event_id)  WHERE conversation_id IS NOT NULL
```

*(c) 条件外键（仅在已知候选 Conversation 时约束；orphan/未知保持 NULL 不约束）：*

```text
fk_agent_ws_outbox_scope_conv   agent_workspace_outbox  (tenant_id, conversation_id) -> agent_conversations(tenant_id, id) ON DELETE RESTRICT  -- 仅当 conversation_id IS NOT NULL（PostgreSQL 复合 FK 对含 NULL 行自动放行）
fk_agent_exec_outbox_scope_conv agent_execution_outbox  (tenant_id, conversation_id) -> agent_conversations(tenant_id, id) ON DELETE RESTRICT
fk_agent_ws_inbox_scope_conv    agent_workspace_inbox   (tenant_id, conversation_id) -> agent_conversations(tenant_id, id) ON DELETE RESTRICT
fk_agent_exec_inbox_scope_conv  agent_execution_inbox   (tenant_id, conversation_id) -> agent_conversations(tenant_id, id) ON DELETE RESTRICT
```

`ON DELETE RESTRICT`：Conversation 物理删除前必须先处理 transport scope 引用（配合 D3 orphan 路径）。PostgreSQL 复合 FK 对任一列 NULL 的行不做约束检查，故 orphan/未知行（`conversation_id IS NULL`）天然放行。

*(d) `agent_transport_scope_reconcile`（D3 三态 reconcile ledger，新表）：*

| 列 | 类型 | 约束 |
|----|------|------|
| `id` | `UUID` PK default uuid4 | — |
| `tenant_id` | `UUID` NOT NULL | `fk_..._tenant` -> `tenants(id)` |
| `owner_key` | `String(40)` NOT NULL | `ck_..._owner_key`: `IN ('workspace.transport.v1','execution.transport.v1','external.payload.v1')`（封闭枚举，复核 #3；transport/external 三类 owner，新增须新 migration） |
| `source_table` | `String(40)` NOT NULL | `ck_..._source_table`: `IN ('agent_workspace_outbox','agent_workspace_inbox','agent_execution_outbox','agent_execution_inbox','agent_run_events')` |
| `source_row_id` | `UUID` NOT NULL | 源表主键 |
| `conversation_id` | `UUID` NULL | 已知候选时填；未知/已删除保持 NULL；与 `reconcile_class` 跨列绑定（下方 `ck_..._class_scope`，复核 #3） |
| `reconcile_class` | `String(20)` NOT NULL | `ck_..._class`: `IN ('conversation_scope','tenant_scope','orphan')`（D3 三态） |
| `issue_code` | `String(64)` NOT NULL | `ck_..._issue_code`: `IN ('source_message_missing','source_run_missing','source_outbox_missing','cross_tenant_mismatch','ambiguous_mapping','conversation_deleted_orphan','epoch_unresolvable')`（封闭枚举，复核 #3；scope 类 + epoch 类全集，新增须新 migration）；一行只承载一个 issue，便于多重问题并列 |
| `state` | `String(20)` NOT NULL default `'open'` | `ck_..._state`: `IN ('open','acknowledged','resolved')` |
| `revision` | `BIGINT` NOT NULL default `1` | 乐观锁版本列（复核 #1）；状态机每次迁移 `revision = revision + 1`，CAS 谓词按 `(id, revision)` |
| `resolution_digest` | `String(64)` NULL | `ck_..._resolution_digest`: `resolution_digest IS NULL OR resolution_digest ~ '^[0-9a-f]{64}$'`（B4 resolved 证据） |
| `created_at` / `resolved_at` | `DateTime(tz)` NOT NULL / NULL | — |
| — | — | `ck_..._resolution_evidence`（跨列）：`(state = 'resolved') = (resolution_digest IS NOT NULL AND resolved_at IS NOT NULL)`（resolved 必须有证据 + 时间；非 resolved 不得伪带 digest/resolved_at） |
| — | — | `ck_..._class_scope`（跨列，复核 #3 class/scope 绑定）：`(reconcile_class = 'conversation_scope') = (conversation_id IS NOT NULL)`（conversation_scope 必带 conversation_id；tenant_scope/orphan 必不带 conversation_id） |

唯一键：`uq_agent_transport_reconcile_issue (tenant_id, owner_key, source_table, source_row_id, issue_code)`——**同一源行同一 owner 的同一 issue 只一条记录**（幂等重放命中既有行），**不同 issue_code 各占一行**（scope 冲突与 `epoch_unresolvable` 等多重问题并列，不被 ON CONFLICT 吞掉，复核 #3）。索引：`ix_agent_transport_reconcile_tenant_state (tenant_id, state)`（tenant scheduler gate 查询）、`ix_agent_transport_reconcile_conv (tenant_id, conversation_id) WHERE conversation_id IS NOT NULL`（conversation purge gate 查询）。**CAS 规则（复核 #1）**：单条 issue 状态迁移（`open->acknowledged->resolved`）按 `UPDATE ... WHERE id = ? AND revision = ? SET state = ?, revision = revision + 1, ...` 乐观锁，0 行命中即并发冲突、重读重试；`revision` 由数据库自增、不回退，保证 gate 读到的 `state` 与解决证据不被并发写漂移。**作用域限定**：单条 `revision` CAS 只保护单条 issue，不保护「同一源行的 issue 集合」——投影聚合的集合级并发正确性由 B4 的**事务级 advisory lock**（或 `SERIALIZABLE` + 重试）保证（复核 #1）。

*(e) `agent_external_object_refs`（D5 external ref ledger，新表）：*

| 列 | 类型 | 约束 |
|----|------|------|
| `id` | `UUID` PK default uuid4 | — |
| `tenant_id` | `UUID` NOT NULL | `fk_..._tenant` -> `tenants(id)` |
| `conversation_id` | `UUID` NULL | 溯源；可 NULL（源行 scope 未知时） |
| `owner_key` | `String(40)` NOT NULL default `'external.payload.v1'` | — |
| `ref_scheme` | `String(40)` NOT NULL | `ck_..._ref_scheme`: `ref_scheme IN ('db_local','unknown')`（B5：S4-B 仅这两值；新 scheme 须新 migration 扩枚举） |
| `ref_value` | `String(500)` NOT NULL | external object 引用值 |
| `source_table` | `String(40)` NOT NULL | `ck_..._source_table`: `IN ('agent_run_events','agent_workspace_outbox','agent_execution_outbox')`（D5 全覆盖） |
| `source_row_id` | `UUID` NOT NULL | 源行主键 |
| `erase_state` | `String(20)` NOT NULL default `'pending'` | `ck_..._erase_state`: `IN ('pending','registered','erased','blocked','unknown')`（B5） |
| `receipt_digest` | `String(64)` NULL | `ck_..._receipt_digest`: `receipt_digest IS NULL OR receipt_digest ~ '^[0-9a-f]{64}$'`（lowercase hex，复核 #7）；erase 取得 receipt 后填（先删对象取 receipt、再清 DB ref 的证据） |
| `blocked_reason` | `String(64)` NULL | `ck_..._blocked_reason`: `blocked_reason IS NULL OR blocked_reason IN ('unknown_scheme','erase_timeout','digest_mismatch','outcome_unknown','adapter_unavailable')`（封闭枚举，复核 #3；与 `ck_..._erase_evidence` 配合：blocked/unknown 态必带其中之一） |
| `created_at` / `updated_at` | `DateTime(tz)` NOT NULL | — |
| — | — | `ck_..._erase_evidence`（跨列，复核 #4 防伪）：`(erase_state = 'erased') = (receipt_digest IS NOT NULL)`；`(erase_state IN ('blocked','unknown')) = (blocked_reason IS NOT NULL)`；`(erase_state IN ('pending','registered')) = (receipt_digest IS NULL AND blocked_reason IS NULL)`（erased 必有合法 receipt digest；blocked/unknown 必有受控 reason；pending/registered 不得伪带 receipt/reason） |

唯一键：`uq_agent_external_ref_source (tenant_id, source_table, source_row_id, ref_value)`（同一源行的同一 ref 只登记一次，幂等）。索引：`ix_agent_external_refs_conv (tenant_id, conversation_id)`、`ix_agent_external_refs_state (tenant_id, erase_state)`。

*(f) inbox tombstone marker/digest（D4，2 张 inbox 各增 2 列）：*

| 列 | 类型 | 约束 |
|----|------|------|
| `receipt_tombstone_state` | `String(16)` NULL | `ck_*_receipt_tombstone_state`: `receipt_tombstone_state IS NULL OR receipt_tombstone_state IN ('redacted')` |
| `receipt_tombstone_digest` | `String(64)` NULL | `ck_*_receipt_tombstone_digest`（lowercase hex，复核 #7）: `receipt_tombstone_digest IS NULL OR receipt_tombstone_digest ~ '^[0-9a-f]{64}$'`；`ck_*_receipt_tombstone`（跨列同生同灭）: `(receipt_tombstone_state IS NULL) = (receipt_tombstone_digest IS NULL)`（marker 与 digest 同写同清，禁单边） |

不改既有 `ck_agent_*_inbox_status`（`processing/consumed/rejected`）枚举。

**B2. 回填来源矩阵（conversation_id 溯源）**

| 目标表 | 源关联 | 映射规则 | 歧义/缺失 |
|--------|--------|----------|-----------|
| `agent_workspace_outbox` | `aggregate_id = agent_messages.id`（event_type='turn.requested.v1'，`aggregate_type='workspace.message'`） | `conversation_id = message.conversation_id`（Message 该列 NOT NULL，1:1） | message 缺失/跨 tenant -> `tenant_scope`/`orphan` reconcile |
| `agent_execution_outbox` | `aggregate_id = agent_runs.id`（event_type='assistant_message.publish_requested.v1'，`aggregate_type='execution.run'`） | `conversation_id = run.conversation_id`（Run 该列 NOT NULL，1:1） | run 缺失/跨 tenant -> reconcile |
| `agent_workspace_inbox` | `event_id = agent_execution_outbox.id`（assistant_publish 消费的源事件） | `conversation_id = 源 execution_outbox.conversation_id`（先回填 outbox 再回填 inbox，保证可 join） | 源 outbox 缺失/scope 未知 -> reconcile |
| `agent_execution_inbox` | `event_id = agent_workspace_outbox.id`（turn_requested 消费的源事件） | `conversation_id = 源 workspace_outbox.conversation_id` | 同上 |

回填顺序：先两张 outbox（直接经 Message/Run），再两张 inbox（经已回填的源 outbox）。所有 UPDATE 带 `tenant_id` 谓词 + 源行 tenant 一致性校验（跨 tenant 不映射，记 reconcile）。

**B3. 历史 `producer_purge_revision` 不可推断 -> 保持未知（NULL）**：backfill **只**回填 `conversation_id`；`producer_purge_revision` 对历史行**保持 NULL（未知）**，且**每个 `producer_purge_revision IS NULL` 的行都必须登记一条对应 `epoch_unresolvable` reconcile issue**（按行，owner 维度，命中既有行幂等不重复）——epoch 未知与 scope 缺失一样必须显式登记，不得静默通过门禁（复核 #2）。**禁止**拿当前 `Conversation.purge_revision` 伪造历史 epoch（生产时快照无法事后重建）。仅新写（S4-C 起）在产生同事务快照真实 `purge_revision`。含历史行的 Conversation 在 purge 时须由 reconcile/S4-C 消费端按「未知 epoch -> tombstone/reconcile」处理（不变量 2/3），不得当作当前 epoch。`epoch_unresolvable` 的 gate 与 resolved 条件见 B4。

**B4. 三态 reconcile ledger 语义（`agent_transport_scope_reconcile`）**

- `reconcile_class` / 触发 / gate（**gate 一律用 `state <> 'resolved'`，复核 #1：open 与 acknowledged 都保持 fail closed，只有 resolved 才解除阻塞**——运维仅 acknowledged 不得解除 gate）：
  - `conversation_scope`：scope 已知（conversation_id 已回填）、但 epoch 未决（`epoch_unresolvable`）-> **阻塞该 Conversation purge**（purge 前置查 `conversation_scope AND state <> 'resolved'` 命中即 blocked）。**A≠B 冲突（行内 scope 与来源解析值不一致）第三轮复核 #3 降级 tenant_scope**（见下），不再用 conversation_scope--唯一键无法表示 A/B 双候选、只 gate B 会漏 A 的 ledger gate。
  - `tenant_scope`：scope 真正未知（源 Message/Run/outbox 缺失或歧义，无法确定 Conversation）**或 A≠B 冲突**（行内 scope 与来源解析值不一致，第三轮 #3 降级，不 bind 单一 Conversation）-> **阻断该 tenant scheduler/canary enable**（S5 scheduler 启动前查 `tenant_scope AND state <> 'resolved'` 命中即 fail closed）。
  - `orphan`：Conversation 已物理删除（源行 conversation_id 在 `agent_conversations` 无对应）-> 具名 orphan reconcile，**不猜 UUID、不并入现存 Conversation**；不阻塞 purge（对象已删），但需运维确认到 `resolved`（带证据）才清零。
- `issue_code` 受控枚举（封闭集，新增需新版本；一行一个 issue）：**scope 类** `source_message_missing`、`source_run_missing`、`source_outbox_missing`、`cross_tenant_mismatch`、`ambiguous_mapping`、`conversation_deleted_orphan`；**epoch 类** `epoch_unresolvable`（与 scope 缺失区分，供 final verify 精确匹配，复核 #3）。
- **`epoch_unresolvable` 的 `reconcile_class` 归类 + gate + resolved（复核 #2）**：epoch 维度独立于 scope 维度；同一行可能 scope 与 epoch 各自不同状态，`epoch_unresolvable` 的 `reconcile_class` **按该行 scope 状态归类**（与 `ck_..._class_scope` 一致：conversation_scope 必带 conversation_id、tenant_scope/orphan 必不带）：
  - **scope 已知**（`conversation_id` 已回填非 NULL）-> `reconcile_class='conversation_scope'`（带 conversation_id）：purge 该 Conversation 前置查 `epoch_unresolvable AND state <> 'resolved'` 命中即 blocked（与 scope 类同 gate）。
  - **scope 未知**（scope 未决、`conversation_id IS NULL`）-> `reconcile_class='tenant_scope'`（不带 conversation_id）：与 scope 未知同源，**阻断该 tenant scheduler/canary enable**（查 `tenant_scope AND state <> 'resolved'` 命中即 fail closed）；该行同时另登记对应 scope 类 issue（如 `source_message_missing`），epoch/scope 各占一行并列。
  - **Conversation 已删除**（源行 conversation_id 在 `agent_conversations` 无对应）-> `reconcile_class='orphan'`（不带 conversation_id）：不阻塞 purge（对象已删），与 orphan 类同——需运维确认到 `resolved`（带证据）才清零；同行另登记 `conversation_deleted_orphan` scope 类 issue。

  **resolved 条件（三类通用）**：消费端/S4-D transport participant 已对未达 fence 的旧 epoch 事件做 tombstone（`payload_state='redacted'` + digest，禁伪造 epoch），取得 tombstone 证据（`resolution_digest` + `resolved_at`）后方可置 resolved；不得在未 tombstone 的情况下 resolved 放行 purge/enable。
- 状态机：`open -> acknowledged -> resolved`（单向，不回退）。**resolved 必须带证据**：`resolution_digest`（解决结果的 canonical digest）+ `resolved_at`，由 `ck_..._resolution_evidence` 强制（复核 #3）。`ck_..._class_scope` 强制 class 与 conversation_id 绑定（复核 #3）。
- **唯一事实源与一致性（复核 #8）**：`agent_transport_scope_reconcile` ledger 是 reconcile 状态与解决证据的**唯一事实源**；4 张 transport 表上的行内 `scope_reconcile_state` 只是**派生只读投影**，必须与 ledger 在**同一事务**写入（backfill/S4-C 写路径单事务同事更新行内标记 + ledger 行），不允许独立漂移。消费/purge 决策只读 ledger；行内标记仅作快速过滤索引，不作决策依据。任何「行内已 reconciled 但 ledger 无对应 resolved 行」即数据异常，verify（B7）检出即 fail closed。
- **多 issue -> 单值投影聚合规则（复核 #5）+ 事务级 advisory lock 集合锁（复核 #1/#集合锁/#源行生命周期，防集合并发漂移）**：同一源行可有多条 issue 行；行内 `scope_reconcile_state` 投影聚合规则——任一 issue `state <> 'resolved'` 时投影 `'pending'`；全部 issue `resolved` 后才投影 `'reconciled'`；`orphan` 类 issue 存在时投影 `'orphan'`（**优先级最高**，即便其他 issue 未 resolved 也标 orphan，因 Conversation 已删、scope 已无对象可回填）。**并发正确性（复核 #1）**：单条 issue 的 `(id, revision)` CAS 只保护**单条**状态机迁移，保护不了「同一源行的 issue 集合」——并发事务可插入新 issue（不改既有行 revision）导致基于过期集合的投影覆盖（lost-update/skew）。**锁对象不能依赖任何 reconcile 子行或源 transport 行的存在**：对 reconcile 子行 `FOR UPDATE` 只锁已存在行、无范围锁（空集合无行可锁），且唯一键含 `issue_code`、并发插不同 `issue_code` 无 unique 冲突；对源 transport 行 `FOR UPDATE` 则要求「源行恒存在」，但 `source_table + source_row_id` 是**多态引用、无 FK**，transport 源行若在 reconcile 未 resolved 前被删除/清理，`FOR UPDATE` 命中 0 行、集合串行化再次失效——故行级锁两条路都不成立（复核 #1/#源行生命周期）。**冻结为事务级 advisory lock 作为集合级唯一锁**：任何「读 issue 集 + 算投影 + 写投影」或「插入新 issue」都须在同一事务内先获取该源行的集合 advisory lock。key 派生**必须走带版本前缀的 canonical 实现（禁止裸 SQL `hashtextextended`）**——沿用 `agent_erasure_locks.conversation_owner_key` 同款「版本前缀 + material + SHA-256 前 8 字节 signed int64」模式，新增**独立版本前缀** `metaedu.agent.transport.agg.v1\x00`，material = 前缀 + tenant bytes + owner_key utf8 + NUL + source_table utf8 + NUL + source_row_id bytes；独立前缀确保集合锁与既有 `conversation_guard_key`（无前缀）、owner lock（`metaedu.agent.owner.v1\x00`）处于**不同输出域**——域隔离避免的是**跨域同 material 复用**导致的系统性撞锁；SHA-256 截断为 signed 64-bit 后理论碰撞仍存在，但同域内偶发碰撞仅造成保守的额外串行化、不破坏正确性（复核 #锁序）。advisory lock **无需任何数据行即可获取**，天然覆盖「源行存在 / 源行已删除 / 空集合 / 新增成员」全部场景，key 由四元组确定性派生、同事务内串行化该源行的整个「集 + 投影」临界区，事务结束自动释放（无泄漏）。**全局锁序（复核 #锁序，接入 D8，防 AB-BA）**：生产路径统一获取顺序冻结为 `Guard -> Conversation 行锁 -> owner advisory lock -> fence 重验 -> **transport/external aggregate 集合 advisory lock（最内层 owner aggregate 位置）** -> 源 transport 行 `FOR UPDATE` 投影写`——集合锁在 owner/fence 之后、最内层，**任何路径不得在 Guard/Conversation/owner/fence 之前获取集合锁**；纯 backfill/运维路径不经 Guard/owner 时同样**只**取集合锁再读集/写投影，顺序一致（不引入第二顺序）；**禁止**一条路径 `aggregate->Guard`、另一条 `Guard->owner/fence->aggregate` 的反向等待（D8 锁链矩阵同步，见 D8）。写路径（backfill / S4-C / S4-D / resolved 推进）统一流程：同事务内 (1) 生产路径先按 D8 顺序取得 `Guard -> Conversation -> owner advisory -> fence`（纯 backfill/运维路径跳过此步），再取**集合 advisory lock**（最内层）；(2) 读该源行当前完整 issue 集（ledger 是唯一事实源）；(3) 若需登记新 issue 则 `INSERT ... ON CONFLICT DO NOTHING`（唯一键仅兜底同 `issue_code` 幂等，不承担集合锁）；(4) 按完整集重算投影；(5) 若源 transport 行仍存在则 `SELECT ... FOR UPDATE` 该源行并写行内 `scope_reconcile_state`（**行内投影列的行锁，仅护投影列、不承担集合语义**；源行已删则跳过写投影——对象已删无投影对象，ledger 行仍完整承载事实源）。**源行生命周期规则（配合 orphan）**：transport 源行在该源行仍有未 resolved reconcile issue 期间**不得**被物理删除/清理（保留至少为 tombstone）；唯一允许源行缺失的路径是 orphan（Conversation 已删、scope 已无对象可回填），此时 advisory lock 仍提供集合串行化、行内投影跳过。单条 `revision` CAS 仍用于单 issue 的 `open->acknowledged->resolved` 迁移防并发漂移；**集合级正确性由 advisory lock 唯一保证**（等价的 `SERIALIZABLE` + serialization-failure 重试亦可，二者取一并冻结为实现约束；**禁止**只用单条 revision、锁 reconcile 子行、或依赖源 transport 行 `FOR UPDATE` 来保护集合）。
- 幂等：同一 `(tenant_id, owner_key, source_table, source_row_id, issue_code)` 重放命中既有行不新建（唯一键 + ON CONFLICT DO NOTHING）；**多重 issue 各占一行**，互不覆盖（复核 #3）。

**B5. external ref ledger 语义（`agent_external_object_refs`）**

- 来源唯一性：`uq_agent_external_ref_source (tenant_id, source_table, source_row_id, ref_value)`——每个 ref-bearing source 行（`agent_run_events.payload_ref`、`agent_workspace_outbox.payload_ref`、`agent_execution_outbox.payload_ref`）的每个非空 ref 恰好一条 ledger 记录。
- **`ref_scheme` 推导（复核 #6，allowlist 冻结为空，禁猜测）**：现有 `RunEvent.payload_ref` 是 opaque identifier，域层 `_validate_opaque_ref` 显式禁止含 `://`（无 scheme 前缀），无法从值可靠解析 scheme。盘点当前仓库：**没有任何 agent integration producer 生成过非空 `payload_ref`**（只有 schema 透传，无 `db_local` staging/object 生成路径），故**没有可证明的 DB-local 格式**。冻结为：**`db_local` allowlist 为空集合**；所有历史/未知 ref 一律 `ref_scheme='unknown'` 且 `erase_state='blocked'`（`blocked_reason='unknown_scheme'`），**禁止猜测 scheme**。S4-E 引入真实 DB-local staging adapter 时须先定义可证明的 ref 格式并加入 allowlist（配套新 migration 扩 `ck_..._ref_scheme` 语义/登记规则），此前 `db_local` 不可达。
- `erase_state` 状态机：`pending -> registered -> erased | blocked | unknown`。`registered`：已登记待删；`erased`：external object 已删并取得 `receipt_digest`（**先于**清 transport DB ref）；`blocked`：unknown scheme/timeout/digest mismatch（记 `blocked_reason`，不得 ACK，不变量 5）；`unknown`：erase outcome 未知（不得 ACK）。仅 `erased` 允许后续清对应 transport `payload_ref`。跨列证据约束见 B1(e) `ck_..._erase_evidence`（复核 #4）。`blocked_reason` 封闭枚举：`unknown_scheme`、`erase_timeout`、`digest_mismatch`、`outcome_unknown`、`adapter_unavailable`。
- 仅 `db_local` scheme 在 S4-E 可实装删除（当前 allowlist 为空，无历史行可达 `db_local`）；其余 scheme 一律 `blocked`/`unknown`。
- **migration 039 guard 演进（复核 #1/#4，为 S4-E 清 RunEvent.payload_ref 预留）**：现有 `guard_agent_run_event_append_only()` 白名单只放行 `payload_inline`/`payload_state` 变化，`to_jsonb(OLD)-'payload_inline'-'payload_state' = to_jsonb(NEW)-...` 强制**其余列含 `payload_ref` 全不变**——S4-E 取得 external receipt 后无法清 RunEvent.payload_ref。且既有 `ck_agent_run_event_payload` 允许 `external`（必须持 ref）**与 `redacted/expired/archived`（`payload_inline IS NULL`，可不持 ref）** 行携带 `payload_ref`——这些「非 external 但残留 ref」正是 final scan 必须处理的历史矛盾形态。冻结：**新增具名 migration `041_run_event_external_ref_tombstone`**（不在 040，与 S4-B scope 列解耦）扩展 guard 白名单，放行**持 ref 旧状态（`external` 或 `redacted/expired/archived` 带非空 `payload_ref`）-> redacted 无 ref** 的严格 tombstone 形态：`OLD.payload_ref IS NOT NULL AND NEW.payload_ref IS NULL AND NEW.payload_state='redacted' AND NEW.payload_inline IS NULL`，且 `to_jsonb` 差集在原豁免列基础上仅再豁免 `payload_ref`/`payload_state`（`OLD.payload_state` 可为 `external`/`redacted`/`expired`/`archived` 任一），**`payload_inline` 必须 OLD/NEW 均 NULL（清 ref 不同时复活 inline）、其余 envelope 列强制不变**；downgrade 还原 039 白名单。S4-B 不实现 041，仅冻结其形态供 S4-E 落地。**file/revision 映射（三面首轮 P1 后修正）**：migration **文件名保持 `041_run_event_external_ref_tombstone.py`**（plan B5 冻结名），但 **Alembic revision id 为缩短形式 `041_run_event_ref_tombstone`**（27 字符 ≤ `varchar(32)` 版本表列宽，无需加宽版本表；原始 36 字符 id 溢出列宽——文件名与 revision id 解耦，二者不必同名，alembic 以 revision id 为准）。

**B6. inbox tombstone（D4）**：purge 清 receipt 时置 `receipt_tombstone_state='redacted'` + `receipt_tombstone_digest=<64-hex digest of receipt envelope>`（marker 与 digest 同写同事务）；`status` 保持既有 `consumed`/`rejected` 等不变，不新增枚举。digest 复用 shared `canonical_digest`，禁空串/`{}`/伪值。

**B7. backfill 执行契约（可恢复 / 分批 / tenant 限流 / 幂等 / 并发安全 / 最终 verify）**

- **分批 + tenant 起点重扫（第三轮复核 #1/#3/#6）**：按 `(tenant_id, id)` keyset 分页，`batch_size>=1`，报告带 `completed`（**不**带 `next_after_id`--跨调用/跨表游标复用会跳行）；中断/失败恢复一律从 tenant 起点全量幂等重扫，已登记 issue 的行经 ``scope_reconcile_state IS NULL`` 守卫退出 actionable 扫描（不饥饿后续行），失败样本封顶。（erasure backfill `backfill_baseline_fences` 是独立 CLI，保留其 `next_after_id` 游标契约，不受影响。）
- **tenant 限流**：逐 tenant 处理 + 每批间隔（`--batch-interval-seconds`）；不锁整表。运维入口 `python -m app.composition.agent_transport_backfill`（第四轮复核 #3）：`--tenant-id` 省略则逐 tenant 全部处理；`--max-rows` 全局行数上限截断；退出码 0=完成 / 1=失败或已完成的 verify_failed / 2=截断未完成（重跑续行，幂等）。
- **幂等恢复**：所有回填 UPDATE 仅命中 `conversation_id IS NULL`（或 scope 未决）的行，重复执行/中断重跑不产生重复或覆盖已填值；reconcile 写入 ON CONFLICT DO NOTHING。
- **并发新写处理**：S4-C 完成前旧 writer 仍可能产生 `conversation_id`/`producer_purge_revision` 为 NULL 的新行 -> backfill 与部分唯一索引均以 `IS NOT NULL` 为作用域，NULL 行不参与唯一约束、不阻塞新写；**不得在本 Slice 收紧 NOT NULL 或开启 purge**（scheduler 在 S5，且需 reconcile ledger 清零前置）。
- **两阶段收敛（复核 #2，不用 UUID max 当高水位 + 不按时间豁免）**：主键是随机 UUID，`max(id)` **不是**单调插入序列——后插入行可能小于旧最大值，用 UUID max 切分 point-in-time/catch-up 会漏行（S1 backfill 已在 `BackfillReport.completed` docstring 明确记录此缺陷：point-in-time 非完备性证明）。**不引入持久化单调序列**（超 expand-only 范围，且改主键/序列代价高）。冻结为**幂等全量重扫**：
  - **S4-B point-in-time backfill**：对每表扫 ``conversation_id IS NULL AND scope_reconcile_state IS NULL`` 的存量行做回填/登记（幂等，可中断重跑）；keyset 分页仅用于单次调用内分批，**不跨调用持久化游标**（恢复从 tenant 起点重扫），**不作为完备性证明**。
  - **S4-C catch-up**：S4-C writer 全量部署、旧（不带 scope 的）capability 清零后，从 **tenant 起点**（不带游标）对所有仍 `conversation_id IS NULL` 的行做**完整幂等重扫**——幂等性保证已填行不被覆盖、已登记 reconcile 不重复（ON CONFLICT DO NOTHING），故全量重扫安全且能捕获 point-in-time 窗口内漏掉的并发新写。
  - **最终 verify 门禁（不按时间/UUID 豁免任何未登记 NULL 行，复核 #2/#3）**：每表凡 `conversation_id IS NULL` 的行**必须**在 reconcile ledger 有**对应 scope 类 issue**（`source_message_missing`/`source_run_missing`/`source_outbox_missing`/`cross_tenant_mismatch`/`ambiguous_mapping`/`conversation_deleted_orphan`）记录；存在既未填 scope 又无对应 scope 类 issue 的行即 verify 失败（fail closed）。**禁止**两种豁免：(a) `created_at > backfill 起点` 之类时间谓词；(b) 用「任意 issue」充数——单独一个 `epoch_unresolvable`（epoch 类）不能证明缺失的 scope 已登记，必须匹配到具名 scope 类 issue。时间/游标仅用于切分批次与断点续跑，不作为 verify 的完备性或豁免依据。
  - **epoch verify（复核 #2，与 scope verify 并列）**：每表凡 `producer_purge_revision IS NULL` 的行**必须**在 reconcile ledger 有对应 `epoch_unresolvable` issue 记录；存在「epoch NULL 且无 `epoch_unresolvable` 行」即 verify 失败（fail closed）。scope verify（`conversation_id IS NULL` -> scope 类 issue）与 epoch verify（`producer_purge_revision IS NULL` -> `epoch_unresolvable` issue）是**两个独立维度**，各自检查、互不豁免——一行可能 scope 已填但 epoch 未知（须 `epoch_unresolvable`），也可能两者皆 NULL（两类 issue 各一条）。

**B8. 验收矩阵（S4-B 实现时逐项验证）**：migration 040 upgrade/downgrade 往返（含既有数据 + downgrade 还原）；**downgrade fail-closed 边界（复核 #5）**：040 `downgrade()` 前必须校验——所有新增列（4 表 `conversation_id`/`producer_purge_revision`/`scope_reconcile_state`/`receipt_tombstone_*`）全为 NULL **且** `agent_transport_scope_reconcile`、`agent_external_object_refs` 两 ledger 全为空，否则 downgrade **fail closed**（拒绝降级，要求 forward-fix），不得在 backfill 后删列丢失 reconcile/external receipt/tombstone 证据；跨 tenant（A tenant 行不得映射到 B tenant Conversation）；歧义映射（A≠B 冲突 -> tenant_scope/ambiguous_mapping，不 bind 单一 Conversation；第三轮 #3）；Conversation 已删除（-> orphan reconcile，不猜 UUID）；重复执行（幂等，不产生重复 reconcile/ledger 行）；中断恢复（tenant 起点幂等重扫，已登记行经 scope_reconcile_state IS NULL 守卫退出扫描，不饥饿；第三轮 #1/#3/#6）；未知 epoch（历史行 `producer_purge_revision` 保持 NULL + 登记，不伪造）；全 ref-bearing source（`agent_run_events` + 两张 outbox 的非空 `payload_ref` 均登记 ledger，无遗漏）；backfill 期间并发新写 NULL 行不被唯一索引阻塞、不被误回填，且在 point-in-time backfill 后由 S4-C catch-up 幂等全量重扫收敛、最终经具名 scope issue verify 清零（复核 #2）；migration 041 guard 演进（S4-E 前置，本 Slice 仅冻结形态不放行）：白名单扩展后「持 ref 旧状态（`external` 或 `redacted/expired/archived` 带非空 `payload_ref`）-> redacted 无 ref」tombstone（清 `payload_ref`）被放行、其余列变化仍 RAISE（真实 PG roundtrip + 变异）。

**S4-B 边界（明确不做）**：不创建 migration 040、不改业务代码（本 delta 纯文档）；不改 writer/claim（S4-C）；不实现 transport/external/runtime participant（S4-D/E）；不做 fault 矩阵（S4-F）；不启用 scheduler（S5）；`erase_available` 保持 `False`；不收紧既有列为 NOT NULL。

**S4-B 验证（本 delta 阶段）**：纯文档；docs gate + `git diff --check` 通过；三路 CI 全绿。返修后提交独立 `max`/Codex 复审；P0/P1 清零后再实现 migration 040 + backfill。

**S4-B round-1 复审修订（2026-08-04，独立复核 P0/P1/P2/P3=0/5/4/0，docs-only）**：nullable 复合 FK 的 PostgreSQL 语义、三态 scope 分类与回填来源矩阵本身无问题。就地修订：B1(d) reconcile ledger 加 `issue_code` 维度（多重问题并列）+ `resolution_digest` + `ck_..._resolution_evidence` 状态约束（复核 #3）；B1(e) external ledger 收窄 `ref_scheme` 枚举 + `ck_..._erase_evidence` 跨列防伪（复核 #4）+ digest 改 lowercase hex（复核 #7）；B1(f) inbox tombstone digest 改 lowercase hex + 跨列同生同灭（复核 #7）；B4 补 ledger 为唯一事实源 + 行内标记为派生投影的同事务一致性契约（复核 #8）；B5 补 `ref_scheme` allowlist 推导（RunEvent opaque ref 禁 `://`，无法识别写 unknown+blocked，复核 #6）+ migration 041 guard 演进冻结（复核 #1）；B7 改两阶段收敛（point-in-time + catch-up，最终门禁不按时间豁免 NULL 行，复核 #2）；B8 补 downgrade fail-closed 边界 + 041 验收（复核 #5）。P2 工作台「三路 CI 待跑」过期表述已同步修正。修订后做一次定向复核再进 migration 040。

**S4-B 定向复审修订（2026-08-04，独立复核 P0/P1/P2/P3=0/4/3/0，docs-only）**：round-1 修订（FK 语义、ledger 唯一事实源、两阶段收敛、downgrade fail-closed、digest hex、041 冻结）均已正确落入。就地修订：B4 gate 改 `state <> 'resolved'`（open 与 acknowledged 都 fail closed，运维仅 acknowledged 不得解除 gate，复核 #1）+ `issue_code` 拆 scope 类/epoch 类并新增 `ck_..._class_scope` 绑定 class 与 conversation_id（复核 #3）+ 多 issue -> 单值投影聚合规则（orphan 优先级最高、同事务 CAS，复核 #5）；B5 `ref_scheme` allowlist 冻结为空集合（无可证明的 DB-local 格式，历史/未知 ref 一律 `unknown`+`blocked`，复核 #6）+ migration 041 guard 演进覆盖**所有持 ref 旧状态**（`external` 与 `redacted/expired/archived` 带非空 `payload_ref`）-> redacted 无 ref，`payload_inline` 两端均 NULL、其余 envelope 列强制不变（复核 #4）；B7 弃用 UUID max 高水位（随机 UUID 非单调插入序列，S1 已记录 point-in-time 非完备证明），改 **S4-B point-in-time + S4-C 自 tenant 起点完整幂等重扫**，最终 verify 要求 NULL-scope 行匹配**具名 scope 类 issue**（禁时间豁免、禁以 epoch 类/任意 issue 充数，复核 #2/#3）；B8 验收矩阵同步补并发新写经 catch-up 收敛 + 041 覆盖全持 ref 旧状态（复核 #2/#4）。P3 工作台 `reason_code`->`issue_code` 命名与 handoff 过期状态已同步。修订后做一次轻量复核再进 migration 040。

**S4-B 轻量复核修订（2026-08-04，独立复核 P0/P1/P2/P3=0/2/2/0，docs-only）**：前两轮修订均已正确落入。就地修订：B1(d) reconcile ledger 补 `revision BIGINT NOT NULL DEFAULT 1` 乐观锁列 + CAS 规则（状态迁移/投影聚合按 `(id, revision)` `UPDATE ... revision = revision+1`，0 行命中即并发冲突重读，复核 #1）+ `owner_key`/`issue_code` 封闭枚举 CHECK（复核 #3）；B1(e) `blocked_reason` 封闭枚举 CHECK（复核 #3）；B3 明确每个 `producer_purge_revision IS NULL` 行必须登记对应 `epoch_unresolvable` issue（复核 #2）；B4 补 `epoch_unresolvable` 的 gate（purge 前置查 `state <> 'resolved'` 命中即 blocked）与 resolved 条件（须先 tombstone 旧 epoch 事件取证据，复核 #2）；B7 verify 拆 scope/epoch **双维度**——scope verify 查 `conversation_id IS NULL`->scope 类 issue、epoch verify 查 `producer_purge_revision IS NULL`->`epoch_unresolvable` issue，各自独立 fail closed、互不豁免（复核 #2）。P2 工作台「下一步」过期交接状态已同步为「等待最终轻量复核；通过后合并再建实现分支」（复核 #4）。修订后做一次最终轻量复核即可进入 migration 040 + backfill 实现。

**S4-B 轻量复核修订（2026-08-04，独立复核 P0/P1/P2/P3=0/1/1/0，docs-only）**：前三轮修订均已正确落入。就地修订：B4 多 issue 投影聚合补**源行级聚合锁**——单条 `(id, revision)` CAS 只护单条状态机迁移，护不住「同一源行的 issue 集合」（并发插入新 issue 不改既有 revision，会用过期集合覆盖投影成错误的 `reconciled`），故投影聚合须同事务 `SELECT ... WHERE (tenant_id, owner_key, source_table, source_row_id) = ? FOR UPDATE` 锁定该源行全部 issue 行再重算投影，新 issue `INSERT ... ON CONFLICT DO NOTHING` 后同事务重算（复核 #1）；B1(d) CAS 规则句同步限定作用域（单条 revision 护单 issue、集合级靠 B4 源行 `FOR UPDATE` 或 `SERIALIZABLE`+重试）；B4 `epoch_unresolvable` 的 `reconcile_class` 按 scope 状态三分——scope 已知 `conversation_scope`（带 conversation_id，阻该 Conversation purge）/ scope 未知 `tenant_scope`（不带 conversation_id，阻 tenant scheduler-enable，另登记对应 scope 类 issue）/ Conversation 已删 `orphan`（不带 conversation_id，不阻 purge，另登记 `conversation_deleted_orphan`），与 `ck_..._class_scope` 一致，resolved 仍须先 tombstone 取证据（复核 #2）。修订后做一次最终轻量复核即可进入 migration 040 + backfill 实现。

**S4-B 定向复核修订（2026-08-04，独立复核 P0/P1/P2/P3=0/1/0/0，docs-only）**：前轮修订（含 `epoch_unresolvable` 三态归类）均已正确落入。就地修订：B4 投影聚合锁对象从「reconcile 子行」改为**源 transport 行**——对 reconcile 子行 `SELECT ... FOR UPDATE` 只锁已存在行、无范围锁（空集合无行可锁），且唯一键含 `issue_code`、并发插不同 `issue_code` 不发生 unique 冲突，「锁子行 + ON CONFLICT 阻塞新 issue」论证不成立；改为任何「读 issue 集 + 算投影 + 写投影」或「插入新 issue」都须同事务先对**源 transport 行** `SELECT ... FROM <source_table> WHERE (tenant_id, id) = (?, ?) FOR UPDATE`（源行恒存在，覆盖空集合与新增成员），序列化整个「集 + 投影」临界区，新 issue `INSERT ... ON CONFLICT DO NOTHING` 仅兜底同 `issue_code` 幂等、不承担集合锁；等价替代为 `SERIALIZABLE` + serialization-failure 重试或按 `(tenant_id, owner_key, source_table, source_row_id)` 派生的事务级 advisory lock，三者取一并冻结为实现约束，禁止只用单条 revision 或锁 reconcile 子行保护集合（复核 #1）。B1(d) CAS 句同步限定作用域。修订后做一次最终定向复核即可进入 migration 040 + backfill 实现。

**S4-B 定向复核修订（2026-08-04，独立复核 P0/P1/P2/P3=0/1/0/0，docs-only）**：前轮修订均已正确落入。就地修订：B4 集合级锁从「源 transport 行 `FOR UPDATE`」改为**事务级 advisory lock**——`source_table + source_row_id` 是多态引用、无 FK，「源行恒存在」只是断言：若 transport 源行在 reconcile 未 resolved 前被删除，`FOR UPDATE` 命中 0 行、集合串行化再次失效；改为任何「读 issue 集 + 算投影 + 写投影」或「插入新 issue」都须同事务先 `pg_advisory_xact_lock(hashtextextended(tenant_id|owner_key|source_table|source_row_id))`——advisory lock 无需数据行即可获取，覆盖「源行存在/已删/空集合/新增成员」全场景；源 transport 行 `FOR UPDATE` 降级为仅护行内投影列的辅助锁（源行已删则跳过写投影、ledger 仍承载事实源）；补源行生命周期规则（有未 resolved issue 期间不得物理删除，orphan 为例外）；等价替代 `SERIALIZABLE`+serialization-failure 重试，二者取一并冻结，禁止依赖源 transport 行 `FOR UPDATE` 保护集合（复核 #1）。B1(d) CAS 句同步。修订后做一次最终定向复核即可进入 migration 040 + backfill 实现。

**S4-B 定向复核修订（2026-08-04，独立复核 P0/P1/P2/P3=0/1/0/0，docs-only）**：前轮修订均已正确落入。就地修订：集合 advisory lock **接入全局锁序并隔离 key 域**——B4 key 派生从裸 SQL `hashtextextended` 改为带版本前缀 canonical（新增独立前缀 `metaedu.agent.transport.agg.v1\x00`，与 `conversation_guard_key` 无前缀、owner lock `metaedu.agent.owner.v1\x00` 分域，消除同一 PostgreSQL 单参数 advisory namespace 的 key 碰撞）；D8 锁链矩阵加入集合锁并冻结唯一全局顺序 `Guard -> Conversation 行锁 -> owner advisory lock -> fence 重验 -> 集合 advisory lock（最内层）-> 源 transport 行 FOR UPDATE 投影写`，任何路径不得在链前取集合锁（禁 `aggregate->Guard` 与 `Guard->owner/fence->aggregate` 反向 AB-BA），纯 backfill/运维路径只取集合锁、顺序一致（复核 #锁序）。B4 写路径流程同步把集合锁置于 owner/fence 之后。修订后做一次最终定向复核即可进入 migration 040 + backfill 实现。

**S4-B 最终复核修订（2026-08-04，独立复核 P0/P1/P2/P3=0/0/0/1，docs-only）**：前七轮修订均已正确落入，P0/P1/P2 全清零，复核确认集合 advisory lock 已正确接入全局锁序（`Guard -> Conversation -> owner -> fence -> aggregate advisory -> source row`）、纯 backfill 只取 aggregate lock 不反向取 Guard/owner、key 用独立版本前缀 + canonical。仅余 1 项 P3 文案准确性：B4 「从根上消除 key 碰撞」改为准确表述——域隔离避免跨域同 material 复用导致的系统性撞锁，SHA-256 截断 signed 64-bit 后理论碰撞仍存在但仅造成保守额外串行化、不破坏正确性（复核 #锁序文案）。**P0/P1 清零达成，可进入 migration 040 + backfill 实现。**

**S4-B 实现第三轮独立复核修订（2026-08-05，P0/P1/P2/P3=0/4/2/0，实现态）**：前两轮实现修订均已正确落入。就地修订：
- **#1 bounded 重跑饥饿**：NULL-scope 扫描分支加 ``scope_reconcile_state IS NULL`` 守卫，已登记 issue 的行（投影非 NULL）退出 actionable 扫描，``max_rows`` bounded 连续调用推进过永久 NULL-scope 行到后续正常行。
- **#2 A≠B 冲突检测补全**：verify 加**第五维** scope vs 来源矩阵（outbox JOIN Message/Run、inbox JOIN 源 outbox，``src.conversation_id <> t.conversation_id``），覆盖 scope-set 无 ref、不进扫描的行（#4 扫描级检测够不着），fail closed。
- **#3 A≠B 冲突 gating 降级 tenant_scope**：A≠B 冲突从 ``conversation_scope``（带解析值 B）改为 ``tenant_scope``/``ambiguous_mapping``（不带 conversation_id）--唯一键无法表示 A/B 双候选、只 gate B 会漏 A 的 ledger purge gate；tenant_scope 阻断 tenant scheduler 直到 resolved，不覆盖行内 A、external ref/epoch 同降 tenant_scope。B4/B8 同步。
- **#4 downgrade TOCTOU**：``downgrade()`` 检查前按固定顺序 ``LOCK TABLE ... ACCESS EXCLUSIVE``（4 transport + 2 ledger），关闭 EXISTS 检查与 DROP 之间的 TOCTOU 窗口（ACCESS SHARE 不挡并发 INSERT）；并发写在检查后提交的证据不再被 DROP 丢失。
- **#5 resolution_evidence CHECK 收紧**：从 ``(state='resolved') = (digest IS NOT NULL AND resolved_at IS NOT NULL)`` 改为显式 OR（resolved 两列全有 / 非 resolved 两列全空），拒绝 ``state='open'`` 单边证据（digest-only 或 resolved_at-only）。
- **#6 Plan↔impl 恢复契约同步**：B7 删 ``next_after_id``/跨调用 keyset 断点续跑，改 tenant 起点幂等重扫 + ``scope_reconcile_state IS NULL`` 守卫；B8 验收「中断恢复」与「歧义映射」同步；erasure backfill 独立 CLI 的 ``next_after_id`` 契约不受影响。
5 修复点（#1/#2/#4/#5/#6 守卫与检测）变异验证全 KILLED。全量回归 fresh 库 2079 passed / 0 failed。停在 PR #530 交第四轮独立复审，不自行合并。

**S4-B 实现第四轮独立复核修订（2026-08-05，P0/P1/P2/P3=0/3/0/1，实现态）**：第三轮修订均已正确落入。就地修订：
- **#1 mismatch 闭环**：#2 verify 第五维从「直接报错」改为「只读验证 mismatch 行有 issue」；新增 **discovery pass**（`_select_actionable_batch` mismatch 分支：EXISTS 检出来源同 tenant A≠B 或跨 tenant），`_backfill_source_row` 在集合锁下登记 `tenant_scope/ambiguous_mapping`（A≠B）或 `cross_tenant_mismatch`（跨 tenant）+ 重算投影，形成可处理 reconcile 闭环。无来源且 scope 已填的行不在 mismatch 范围（scope 仍有效、FK 保护）。
- **#2 downgrade 锁序 AB-BA**：`_lock_tables_access_exclusive` 锁序从 ledger 优先反转为 **transport 优先、ledger 后**，与 backfill「读 transport 源行 -> 写 ledger」一致，消除 migration（锁 ledger->transport）与 backfill（持 transport ACCESS SHARE -> 写 ledger ROW EXCLUSIVE）的 AB-BA 死锁。
- **#3 CLI/runner + tenant 限流**：新增 `python -m app.composition.agent_transport_backfill`（沿用 erasure backfill 模式）：`--tenant-id` 省略则逐 tenant 全部处理、`--batch-size`、`--max-rows` 全局行数上限、`--batch-interval-seconds` 每批间隔；退出码 0=完成 / 1=失败或已完成的 verify_failed / 2=截断未完成（tenant 起点幂等重跑续行，无游标）。`backfill_transport_scope` 增 `batch_interval_seconds` 参数（B7 每批间隔）。
- **#4 文案漂移**：verify 五维、report 注释、调用处注释同步；round-3 备注 2074->2079。
变异验证：#1 discovery（移除 mismatch 分支后非扫描冲突不再登记）/ #2 锁序（LOCK TABLE 移除后 TOCTOU 测试失败）均 KILLED。全量回归 fresh 库 2082 passed / 0 failed。停在 PR #530 交第五轮独立复审，不自行合并。

#### R1-S4-C Writer/Claim Scope + Epoch Fence 契约冻结（2026-08-06，先于代码冻结，纯文档）

按 S4-A D1-D8 / S4-B B1-B8 冻结 S4-C 的 writer 传播、claim envelope 与 Guard 内六元组 CAS。**本 delta 只写文档：不写业务代码、不改 migration 040、不实现 migration 041、`erase_available` 全程保持 `False`、不启用 purge scheduler（S5）、不进 S4-D/E/F。** 现状盘点基于 main `a52d8c03`（migration 040 + backfill 已合并，S4-B 第五轮复审 P0/P1 已清零）。TD-092（PR #532）已解除 S4-C 暂停并登记收敛治理：三轮内收敛、连续两轮新 P1 即拆分或重构。

> **首轮三面独立复审修订（2026-08-06，数据/状态 + 并发/锁序 + 测试/运维三面并行，round-1 返修落点，优先于下文对应旧陈述）**：三面合计 **P0=3 / P1=12 / P2=11 / P3=4**（数据/状态 P0=3 P1=4 P2=2 P3=1；并发/锁序 P0=0 P1=4 P2=3 P3=1；测试/运维 P0=0 P1=4 P2=6 P3=2）。按根因族一次返修，直接改正下文（round-1 修订），横向覆盖 writer/claim/consumer/heal/verify 及等价入口。
> **round-2 定向复核修订（2026-08-06，协调者 + 代码核对）**：R1-R6 落点逐一核对，round-1 P0/P1 均已由契约文本封闭（R1 epoch 快照同事务行锁 / R2 claim 锁定装载 + 非 NULL 成员 + 两/三源 / R3 集合锁目标 + owner_key / R4 fence/purge_state gating + turn terminalize / R5 verify 原始维度 + 扫描守卫分离 / R6 措辞）。一处落点与代码不符已修正：R2 原称「backfill 对仍 claimed 行不写 scope（scope/epoch 列不可变）」——实际 `_backfill_source_row` 的 `UPDATE ... WHERE conversation_id IS NULL` **无 status 谓词**，可回填仍 claimed 行。改为「消费事务内 FOR UPDATE 重读为准」语义（C4），与 R2 隔离设计一致；「列不可变」表述删除。
> **round-3 独立复核修订（2026-08-06，P0/P1/P2/P3=0/3/4/0）**：三面计数修正为 `3/12/11/4`（round-1 注记原写 3/9/12/4，污染 TD-092 收敛指标，已改）。三个 P1 为实现前必须冻结的事务/身份协议，round-3 已一并修正（优先于 R1/R2/R4 对应旧陈述）：**S1** turn 路径补 outbox 行 scope 校验（三源，修正 R2 数据事实）；**S2** unknown/stale 的证据提交 + outbox 终态化冻结双事务协议（修正 R4 遗漏的事务边界）；**S3** orphan 分支改为仅 catch-up/discovery 可达（consumer 先锁 Conversation 后 orphan 不可达）。P2 四项一并修（R1 workspace 锁事实、PR HEAD 稳定表述、实现 PR 冻结为两 PR 拆分）。
> **round-4 独立复核修订（2026-08-06，P0/P1/P2/P3=0/3/1/0，TD-092 连续两轮新 P1 升级）**：round-3 S2 双事务协议与现有 DB 结构冲突，已按根因批次重写为**状态表**（round-4 S2 修订，优先于 round-3 S2/R4 对应旧陈述）：**P1-a** workspace outbox 无 `decision_*`/`decided_at` 列（仅 `last_error_code`，`models.py:476`；execution outbox 有，`models.py:870-872` 决策 CHECK），且 C7 禁新增 migration → **冻结「无 migration」选择**，workspace outbox 终态用现有字段（`status='cancelled'` + 清 claim + 受控 `last_error_code`），证据由 inbox tombstone digest + ledger 承载；**P1-b** stale 与 unknown **拆开**——unknown 才登记 `epoch_unresolvable`，stale 只写 inbox tombstone deterministic evidence、**不**登记 `epoch_unresolvable`（避免制造不必要的 reconcile gate）；**P1-c** 第一事务提交后的 inbox 状态**冻结为既有 `rejected`**（`processing/consumed/rejected` 枚举，workspace `models.py:497`/execution `models.py:955`）+ 受控 `last_error_code` + tombstone marker/digest，重放识别 `rejected` + tombstone 后直接续做第二事务。
> **round-5 定向复核修订（2026-08-07，P0/P1/P2/P3=0/3/0/0，三项定向修正，不重开 C1-C9）**：**P1-1** stale 语义冲突——旧 C3 stale 条目仍写「写 inbox 前 raise」，与状态表 Tx1「正常提交不 raise」矛盾；改为 stale 统一走 round-4 S2 双事务（Tx1 正常提交 tombstone 证据、Tx2 终态化），`LateBodyWriteRejectedError` 归为 S3-E 正文写 fence 裁决、非 stale 消费终态机制。**P1-2** `epoch_unresolvable` ledger 生命周期未冻结——补最终状态（`open -> acknowledged -> resolved`）、`resolution_digest`/`resolved_at` 写入（S4-D tombstone 后以 inbox `receipt_tombstone_digest` 为证据）与重放匹配条件（open/acknowledged 续做 / resolved 且 digest 匹配幂等返回 / 终态但 digest 不符 fail closed）。**P1-3** 状态表按 workspace/execution 展开（Tx1/Tx2 各分行），execution Tx2 补 `decision_actor_id=uuid.UUID(int=0)` 系统裁决 sentinel（S3-E `terminalize_output_late_write` 同款），满足 `ck_agent_exec_outbox_decision` 全有或全无 CHECK（缺 `decision_actor_id` 违反 CHECK）。round-6 复审只需一次轻量表格核对。
> **round-6 定向复核修订（2026-08-07，P0/P1/P2/P3=0/1/1/0，两项定向修正，不重开 C1-C9）**：**P1（round-6）** ledger `resolved` 被错误当成 Tx2 已终态化——S4-D resolve 与 Tx2 outbox 更新是两个独立动作（反例：Tx1 提交 → Tx2 崩溃 → S4-D resolve → 重放时 outbox 仍 `claimed`）。改为**重放锁后检查 outbox 精确终态三分支**：(a) outbox 已 `cancelled`+清 claim（execution 另验 decision 四元）→ no-op；(b) 未终态且 claim 匹配 → 续做 Tx2；(c) 未终态且 claim 不匹配 → `*IntegrationConflictError`。ledger `resolved` 只作 tombstone evidence 校验，不作为 Tx2 完成判据。**P2** 工作台「三路 CI 全绿」与 GitHub 实际状态不一致（PR #535 因本轮取消重跑被标 CANCELLED/BLOCKED，非测试失败）；待基建恢复后以最新 HEAD 重跑 required checks 并同步工作台。
> **round-7 定向复核修订（2026-08-07，P0/P1/P2/P3=0/1/0/1，一项定向修正，不重开 C1-C9）**：**P1（round-7）**「精确终态」判据仍不够精确——任意 `cancelled`+清 claim 会被误判为本次终态（其他原因的 cancelled、错误 digest、投影漂移）。冻结**精确终态谓词**（状态表 Tx2/Tx2 后重放行，round-7）：workspace 侧须 `last_error_code == 本分支精确受控 code` **且**同事务 Message `turn_dispatch_state='abandoned'` + 匹配 `turn_dispatch_error_code`（schema 已支持 `abandoned`，`models.py:211-212`）；execution 侧须 decision 四元精确匹配（`decision_actor_id=UUID(0)` + 精确 `decision_reason` + 重算 `decision_digest` 匹配 + `decided_at` 非空）**且** Run `output_publish_state='suppressed'`（S3-E 已采用该模式，`bridge_repository.py:548+`）。续做 Tx2 只接受 `status='claimed'` 且 claim 四元匹配；`pending/dead_letter/published/其他 cancelled` 一律 fail closed。**P3** 工作台 CI 文案（HEAD `1b1ab95e` 三路 SUCCESS、PR OPEN/CLEAN）随本批同步。
> **round-8 定向复核修订（2026-08-07，P0/P1/P2/P3=0/1/0/0，一项定向修正，不重开 C1-C9）**：**P1（round-8）**「精确匹配」仍用未冻结占位值——`<本分支精确受控 code>` 与 `<重算匹配的 64-hex>` 无实际值，未登记的新 code 会被 `suppression_reason_code` 归一成 `operator_suppressed`，unknown/stale 失去可区分身份。冻结**两个具名 code**（unknown → `epoch_unknown_rejected` / stale → `epoch_stale_rejected`，加入 `SUPPRESSION_REASON_CODES` allowlist `agent_suppression_reasons.py:13`）与 **execution `decision_digest` envelope**（`snapshot_digest`，复用 `snapshots.py:149` 同一 helper；输入 = `{schema_version:1, actor_id:UUID(0), reason:<具名 code>, event_id, receipt_tombstone_digest}`，键名/版本冻结）；workspace 两个 error_code 字段（outbox `last_error_code` + Message `turn_dispatch_error_code`）用**同一具名 code**。状态表 Tx1/Tx2/Tx2 后重放行与生命周期重放段落同步。
> **round-9 定向复核修订（2026-08-07，P0/P1/P2/P3=0/0/1/1，一项拆分修正，不重开 C1-C9）**：**P2** 契约 PR 不再是纯文档——round-8 把 `agent_suppression_reasons.py` allowlist 源码改动（生产行为）提前混入，且缺直接回归测试（删除任一 allowlist 项后现有测试仍可能全绿，无法击杀回退变异）。**回退该源码改动，契约 PR 恢复纯文档**；两个具名 code 的落地**随第二实现 PR（Claim/consumer CAS + deterministic terminalization）** 并配参数化回归测试（C8 项 11：`suppression_reason_code` 不归一成 `operator_suppressed`，剔除任一 code 变红）。**P3** 工作台「只提交纯文档/docs-only」与实际 diff 不一致，随本批回填。
> **round-10 落点核对（2026-08-07，P0/P1/P2/P3=0/0/1/1，修正 round-9 回退未真正生效）**：round-9 曾 `git checkout --` 把源码恢复为 HEAD（round-8 提交 `ac742482` 仍含两 code），`git status clean` 只表示工作树匹配当前 HEAD、**不表示源码匹配 `main`**——远端 PR 实际仍含 `agent_suppression_reasons.py` 净变更 `+6`。round-10 已 `git restore --source=main` 真正回退并提交 revert，`git diff main...HEAD` 确认 PR 现仅 2 个 docs 文件、无 `.py`（纯文档恢复）。C8 项 11 与 C9 第二实现 PR 承接文案不变。
> **PR-A round-1/round-2 复审记录（2026-08-07，实现 PR #537）**：round-1 三面 P0=0/P1=10/P2=10/P3=6，按 4 根因族一次返修（① COMPLETED 写 outbox 强制非 NULL epoch + 裸测试调用方补 epoch；② `conversation_purge_revision` 自持 FOR UPDATE；③ workspace existing 分支校验 scope/epoch 一致；④ 测试判别力补齐）。round-2 定向复核 P0=0/P1=1/P2=2/P3=2，P1（execution 幂等重放测试未推进 purge_revision 无法击杀重写实现）已修复。**两项 P2 记为认知（不扩改）**：(1) `fenced_commit_terminal` 内 `conversation_purge_revision` 在 `require_active_fence`（owner/fence）之后取 Conversation 锁，若未来调用方不预持 Conversation 行锁会形成 Guard->owner->fence->Conversation 反向锁序——当前全部生产调用方均预持，同行重锁是 reentrant no-op，无死锁；建议后续实现（PR-B 接入时）将 epoch 读前置到 `require_active_fence` 之前。(2) anti-forgery 测试结构上无法击杀「fence 读取」实现（`require_body_write_fence_for_update` 单调对齐 fence 到 Conversation，fence 读取实现写出相同值）——C8 项 4「writer 禁伪造 epoch」以**代码级来源证明**（`conversation_purge_revision`/`get_conversation` 直接读 `ConversationModel.purge_revision`）+ 当前真实 PG 测试为准，不人为制造不可能的 fence 脱节状态追求 mutation kill。

> **PR-B round-1/round-2 复审与合并记录（2026-08-07，实现 PR #539，squash merge `8f184935`）**：round-1 三面首轮（数据/状态 0/0/2/2、并发/锁序 0/2/6/3、测试/运维 0/4/6/5，P1=6）按三根因族一次返修（commit `da90e3ac` + CI 修复 `e0146706`）：① **output stale 可达性**——`consume_output_event` 投影 Conversation 锁改 `allow_purge_fenced=True`（仅消费分类入口，`lock_projection_conversation` 在 `purge_state in {running, completed}` 时前置 raise `LateBodyWriteRejectedError` 使 output 侧 stale 永远落 `late_body_write_rejected` 而非具名 `epoch_stale_rejected`，违反 R4「stale 统一走双事务」；normal 才进正文 fence 裁决，`project_assistant_message` 双保险保持）；② **C1 第 4 跳落实**——`create_turn_receipt_rejected`/`create_output_receipt_rejected` 写 inbox `conversation_id` + `producer_purge_revision`（取自 claim envelope 六元 CAS 已验证源行重读值，非当前 revision；stale 写原 producer epoch、unknown 保持 NULL；幂等命中校验既有值一致，不一致 fail closed，重放不重写）——C9 要求 inbox 写在本 PR 完成，四跳链与 S4-B verify 闭环；③ **测试判别力**——ledger `owner_key` 精确断言、output takeover claim CAS 拒绝零变更、精确终态负例（其他 cancelled 不得 no-op）、推进 revision 后重放不重写；5 项 mutation kill 真实库逐一变异实证转红（错 owner_key / 跳过 output CAS / 退化精确终态谓词 / 漏写第四跳两侧）。顺带加固：`read_fence_state` TOCTOU 前提注释（owner advisory lock 排他性关闭分类-裁决窗口，前提=所有 fence 状态转移路径持同一 owner lock）、existing rejected receipt 补 `payload_digest` 一致性校验。round-2 定向复核（HEAD `e09e4b8e`）6 项指定检查全 ✅，**P0/P1 清零**；残留 P2×2（existing 查询不按 `consumer_name` 过滤，当前消费者与 event_type 一一对应无现实冲突；output 侧 NULL 断言盲区，turn 侧补齐且生产实现已验证写 claimed 值）与 P3×2（注释残留）均记录不阻断。**PR-A 两项 P2 认知落地**：(1) epoch 读前置已由批次1 `conversation_purge_revision` 自持 FOR UPDATE 落实；(2) anti-forgery 保持代码级来源证明。评分 90（Original）。验证：S4-C 批次1-3 + S3-E 邻近 48 passed；ruff/mypy 0 回归；Draft 阶段 `Backend iteration` 绿（run `31171138749`）→ Ready 最新 HEAD `Backend full` SUCCESS + 三路 CI 全绿（run `31172448451`）；batch3 tenant 种子 fixture 修 CI fresh 库 `fk_agent_transport_reconcile_tenant` 外键违规（本地共享库掩盖、仅 CI 暴露，删 tenant 模拟验证）；TD-032 `agent_control_plane.py` 1086 行登记待拆分。`erase_available` 保持 False、不改 migration 040、不实现 041、不启用 S5。**merged-boundary**：PR-A + PR-B 联合验收完成——四跳传播链（Conversation snapshot → outbox metadata → claim envelope → inbox metadata）全链路落地，六元 CAS + 双事务协议 + 重放三分支合并后可声明「四跳一致」；遗留 S4-D/E/F、S5 scheduler、真实 Pi Worker、云对象存储生产 adapter 明确排除。

**R1（旧 C1 hop1/C2，P0-1 数据面 + P1-4 并发面）— epoch 快照源与「禁止伪造」拆分，统一为 Conversation 列 + 同事务行锁**：workspace 侧 `submit_turn`（workspace `bridge.py:156`）经 `reserve_user_turn`（`repository.py:509`，`_require_owned_row_for_update` 取 Conversation `FOR UPDATE` 行锁）在**外层事务结束前持续持有**该行锁，`add_turn_outbox`（`bridge_repository.py:62`）在同一事务内创建 outbox 行——行锁全程持有，无需重取。execution 侧 `commit_terminal` publish 分支（`execution_repository.py:853`）经 `fenced_commit_terminal` 持 execution fence 但**未持 Conversation 行锁读**。**冻结为**——C1 hop1/hop2 必须同事务、Conversation `FOR UPDATE` 行锁仍持有时读取并写入：workspace 侧**复用** `submit_turn` 已持有的行锁（禁止实现者误加重复锁链，round-3 修订）；execution 侧在 `commit_terminal` 建 outbox 行前显式取（或复用调用方持有的）Conversation 行锁并读 `Conversation.purge_revision`，**不得**用 `fence.purge_revision` 或 `fence.revision` 冒充（`require_body_write_fence_for_update` 在 active 下会把 fence token 单调对齐到 Conversation token `erasure_repository.py:475-487`，是「已同步值」而非「生产时快照」，不满足 R1 快照语义）。C1 hop1「禁止用 fence 行 CAS `revision`、Conversation `revision`、checkpoint、时间戳冒充」增补为「含 fence `purge_revision`」。epoch > 当前分支改为：fence 对齐路径可能制造「列已推进但 fence 未对齐」窗口，一律 fail closed 不消费、不登记（数据异常，无受控 issue_code，不新增枚举，C7 不变）。

**R2（旧 C1 hop3/C3，P0-2 数据面 + P1-1/P1-4/P2-1 并发面）— 六元 CAS 收敛为「claim-装载源固定 + 非 NULL 成员比对 + 两/三源一致性按路径定」**：claim 装载源固定为**claim 短事务内对 outbox 行 `FOR UPDATE SKIP LOCKED` 的锁定读取**（C1 hop3），且该读取与 `status='claimed'`/`attempt_count+=1` 同事务原子。六元 CAS（C3）成员比对规则：
- `event_id`/`payload_digest`/`attempt_count`/`claimant_id`：行值在**消费事务内 `FOR UPDATE` 重读**后取得（与 claim 装载隔离，防 claim→consume 间被接管），逐项与 envelope 比对，不符 `*IntegrationConflictError`（takeover 拒绝仍完全由 `attempt_count`+`claimant_id` 承载，两新列不参与接管拒绝、C6 takeover 行措辞改正）。
- `conversation_id`：**当该成员非 NULL 时**参与比对。**turn 与 output 路径都是三源** `row == envelope == event`，且三者都与 Guard 锁定 Conversation 一致（round-3 S1 修订：workspace outbox 明确存在独立 `conversation_id` 列 `models.py:479`，S4-C writer 又要求填该列，故 turn 与 output 都校验 `row == envelope == event == Guard Conversation`——防止 workspace outbox 行被回填或污染后绕过行值校验；任一非 NULL 成员不符即 fail closed）。S4-B backfill `_backfill_source_row` 在 claim 后可回填 row scope，故消费事务 `FOR UPDATE` 重读（R2）使 claim 后回填的行被 CAS 判 `*IntegrationConflictError` 重试、不静默接受。
- `producer_purge_revision`：**当该成员非 NULL 时**参与比对（行 == envelope，均 claim 装载自同锁行）；消费事务内重读后与 envelope 比对。NULL（历史/backfill 期行）不参与 CAS 值比对，由 C3 epoch 分类处理。
- **NULL-scope 行处理**：**row/envelope 的 `conversation_id` 为 NULL 但 event 非 NULL**（历史未回填行）→ **fail closed、不消费**（round-3 S1 措辞修正：`envelope` 装载自 row，row 为 NULL 则 envelope 同为 NULL，不存在「envelope 非 NULL、row NULL」的组合），由 S4-C catch-up 回填 scope（已填后重试成功）或登记 `tenant_scope` scope 类 issue（不可解析则事件保持未消费、随 backfill 收敛，最终 verify 双维 fail closed）——**不得**因 claim 时 NULL 而静默接受，也**不得**在消费路径把 NULL-scope 行当作当前 scope 消费（防复活正文到未知会话）。

**R3（旧 C4，P0-3 并发面 + P1-2/P2-1 并发面）— consumer 集合锁目标、owner_key 与「锁序-行锁-注册」不变量**：consumer 登记 `epoch_unresolvable`/scope 冲突 issue 时，集合锁目标 = **ledger 行自身的 `source_table/source_row_id`**（inbox 行用 inbox 行 PK），**不是** B2 scope 来源的 outbox 行；`owner_key` = 该 source_table 的 transport owner（`workspace.transport.v1`/`execution.transport.v1`，与 backfill `OWNER_BY_TABLE` 同源），**不得**用 consumer 的正文 owner（`workspace.core.v1`/`execution.core.v1`）——否则 consumer 与 backfill 对同一源行 issue 集用不同 advisory key，投影 lost-update（B4 要防的失效）。锁序不变量：consumer 的 Guard 事务在**同一事务**内完成 (a) inbox metadata 写 + (b) receipt/状态写 + (c) issue 插入 + (d) 投影重算，(c)(d) 在集合锁临界区内、按 D8「集合锁 → 源行 FOR UPDATE」取锁，**先取集合锁再写 inbox 行投影**；`begin_*_receipt` 的 inbox 行 `FOR UPDATE`（幂等重读）与集合锁之间无「先持 inbox 行锁再等集合锁」的反向等待——envelope 在 claim 时已携带 epoch/scope 状态，consumer 在 begin_receipt 前即可判定是否需要集合锁。scope 冲突（A≠B，两源均非 NULL）检测在 6 元 CAS（fence 前）fail closed，**冲突降级 `tenant_scope` 的登记归 backfill discovery**（B4 已实现），consumer 不登记 scope 冲突（C4/C6 措辞改正，防「CAS 拒绝后注册路径不可达」自矛盾）。S4-D/E transport participant 取集合锁时点须位于 Conversation 行锁/owner 之后（与消费者同序），禁止在取得 Conversation 行锁前取集合锁（C4 补一句，P2-2 并发面）。

**R4（旧 C3/C6，P1-3 并发面 + P1-2 测试面 + P1-3 测试面）— stale/unknown epoch 的确定性终态与 tombstone-resolve 双相**：stale epoch（< 当前）在**消费时点**（Guard + Conversation 行锁后、fence 裁决位置）判定。**round-5 P1-1 修订：stale 统一走 round-4 S2 双事务协议（Tx1 正常提交 tombstone 证据、Tx2 终态化），不再「写 inbox 前 raise」**；`LateBodyWriteRejectedError`/`LateOutputReadRejectedError`（S3-E 已接）在 S4-C 仅用于**正文写路径的 fence 裁决**（workspace `project_assistant_message` 裁决、execution `dispatch_output` terminalize），**不是** stale 消费的终态机制。**turn 侧新增确定性终态**：`consume_turn_event` 的 stale/unknown epoch 不得 retry-forever→dead_letter，须落 deterministic 终态（镜像 `terminalize_output_late_write` 的 claim-CAS + `decision_reason` 语义，round-1 P1-3 并发面）。**双事务协议以 round-4/round-5 状态表为准（round-5 S2 修订，见 C3「unknown/stale 的双事务协议」）**：unknown 与 stale 拆开、inbox 冻结 `rejected` + tombstone 证据、workspace outbox 用既有字段（无 migration）、execution outbox 写 decision 四元含 `decision_actor_id`。epoch 分类与 purge_state 关系：stale 判定必须**同时**考虑 fence 状态（`purge_state in {running, completed}` 或 fence erasing/erased 才 stale）；soft-delete（SCHEDULED）/restore 推进 `Conversation.purge_revision` 但 fence 仍 active 时，pre-existing 事件**不得**仅因 token 推进被 tombstone（正文从未 erase、fence 允许写，R1 快照语义下该事件 epoch 本就该是旧值但正文可写）——若契约坚持 token 比较，则须显式声明「pre-delete 在途事件在 SCHEDULED/restore 后一律 tombstone」及产品代价（首轮 P1-1 并发面，数据面 P0-3 同源）。

**R5（旧 C5/C6/C8，P1-3/P2-1/P2-2/P2-5/P2-6/P3-1 测试面 + P2-4 数据面）— catch-up 扫描谓词、verify 与验收矩阵明细化**：
- C5 catch-up 扫描谓词写全：`_select_actionable_batch` 四分支（NULL-scope 未处理 + ref 未登记 + scope-set mismatch + scope-set 但 epoch NULL），不只 NULL-scope 一行；catch-up 扫描的 `scope_reconcile_state IS NULL` 守卫**只用于扫描去重，不得**用于 final verify——verify 按原始数据维度逐行检查（`conversation_id IS NULL`→scope 类 issue、`producer_purge_revision IS NULL`→`epoch_unresolvable`），已投影 pending 的行同样必须通过（修复「投影非 NULL 后 verify 豁免」歧义）。
- C5 「capability 清零」定义：删除该抽象，改为「S4-C writer 全量部署且新写路径已带 scope/epoch（040 列新写非 NULL）后」触发 catch-up，并绑定 C8「四跳一致」验收。
- C6 补两行：**claim lease 过期**（`claimed_at <= stale_before` B 重 claim 同一事件、A 旧 attempt 仍持旧 epoch）→ claim CAS 拒旧 attempt；**partial ACK**（transport/external owner 未全 ACK 不得写 `completed`，D6）→ 不复活正文、不推进 completed。
- C6 takeover 措辞改正：接管拒绝由 `attempt_count`+`claimant_id` 承载（6 元扩展是身份/scope 校验，NULL 成员不参与，非接管拒绝增强）。
- C8 改为编号矩阵（对齐 B8 命名项）：六元 CAS 表驱动 / 幂等重放不重写 / claim 短事务无死锁（并发 claim）/ inbox metadata 与 receipt 同事务 / unknown epoch 集合锁 + tombstone-resolve / catch-up 无游标 + verify 双维 / 反例矩阵逐项真实 PG + 变异 kill / S4-B 专项 + 邻近回归 + 全量 pytest。C8 是 **merged-boundary 验收**：若拆两 PR，producer propagation PR 只验证 outbox 行真实性与重放，claim/consumer PR 只验证 CAS 与 inbox，不得单 PR 声明「六元 CAS」「四跳一致」。
- C9 补一句：三面首轮复审结果（P0/P1/P2/P3 计数）必须记录到 work-log，P0/P1 清零后才开实现 PR。

**R6（旧 C2/C6，P3-1 数据面 + P3-2 数据面 + P3 测试面）— 措辞与 NULL 细节**：C2「已持久化即保留」增补「重放遇 040 列仍 NULL 的旧行不得由 S4-C writer 回填（NULL 不补写，归 backfill/catch-up）」，与 B3「禁拿当前值伪造历史 epoch」一致；C1/C3 措辞统一「六元全部从 claim 短事务锁定读取的 outbox 行装载（event_id 取 row.id；event 仅作 payload 校验），不从 event parse 派生任何 CAS 字段」；C8 全量测试表述用「全量 pytest 0 failed（`external_network` 手工 opt-in 除外）」。

**R 复核提示（round-1 修订落点，round-8 复审重点）**：R1 epoch 快照同事务行锁（workspace 复用既有锁、不重复取）；R2 claim 装载原子性 + 非 NULL 成员比对 + **turn/output 均三源**（round-3 S1）；R3 consumer 集合锁目标/owner_key + 先集合锁后 inbox 行；R4 stale/unknown 确定性终态 + tombstone-resolve 双相 + **双事务协议状态表**（round-4/5/6/7/8 S2）+ fence 状态 gating；R5 catch-up 全谓词 + verify 不用守卫 + C6 两新行 + C8 编号矩阵；R6 措辞；**S3** orphan 仅 catch-up/discovery 可达（round-3）；**round-4 S2** unknown/stale 拆开 + inbox `rejected` 冻结 + workspace outbox 无 migration 证据；**round-5 S2** stale 统一走双事务（不 raise）+ `epoch_unresolvable` ledger 生命周期（resolved + 证据 + 重放匹配）+ 状态表按 workspace/execution 展开 + execution `decision_actor_id`；**round-6 S2** 重放锁后检查 outbox 精确终态三分支（ledger resolved 不代替 Tx2）；**round-7 S2** 精确终态谓词（workspace 精确 `last_error_code`+Message `abandoned` / execution decision 四元精确+Run `suppressed`），续做只接受 `claimed`；**round-8 S2** 具名 code（`epoch_unknown_rejected`/`epoch_stale_rejected`）+ `decision_digest` envelope 冻结（`snapshot_digest` 同一 helper、版本化键名、workspace 两 error_code 同 code）。

**C1. scope/epoch 传播链（D2 完整化，冻结四跳）**

传播链冻结为四跳，每跳都是**同事务**写入、不并入 V1 event payload（`integration_event_digest`/payload digest 不变，D2）：

1. **Conversation snapshot**：epoch = `Conversation.purge_revision`（Conversation 行的 fencing token，**在 Guard + Conversation 行锁仍持有时同事务读取**）。**值域唯一**：`Conversation.purge_revision`；**禁止**用 fence 行 CAS `revision`（`agent_erasure_fences.revision`）、fence 行 `purge_revision`、Conversation `revision`、checkpoint 或可观察时间戳冒充（R1，B3/不变量 2）。`require_body_write_fence_for_update`（`erasure_repository.py:475-487`）在 active 下把 fence token 单调对齐到 Conversation token，是「已同步值」而非「生产时快照」，**不得**作为 epoch 源。
2. **outbox metadata**：workspace turn outbox 与 execution output outbox 在**产生同事务**写入 `conversation_id`（该 Conversation UUID）与 `producer_purge_revision`（第 1 跳快照值）。**与第 1 跳同事务、Conversation 行锁仍持有时**写入（R1）：workspace 侧 `submit_turn` 已在 `reserve_user_turn` 持有 Conversation `FOR UPDATE` 行锁并持续到事务结束，`add_turn_outbox` **复用**该锁（round-3 修订：不重复取锁）；execution 侧在 `commit_terminal` 建 outbox 行前显式取（或复用调用方持有的）Conversation 行锁并读 `Conversation.purge_revision`。
3. **claim envelope**：`ClaimedWorkspaceEvent`/`ClaimedExecutionEvent` 增 `conversation_id` + `producer_purge_revision` 两字段，claim 短事务内**从 outbox 行 `FOR UPDATE SKIP LOCKED` 锁定读取**装载（**不**从 event parse 派生任何 CAS 字段），且与 `status='claimed'`/`attempt_count+=1` 同事务原子（R2）。
4. **inbox metadata**：consumer 在 Guard 内消费时，把 **envelope 的** scope/epoch 写入 inbox 行的 `conversation_id`/`producer_purge_revision`（与 receipt 同事务）；合法源为**消费事务内重读的源 outbox 行当前值**，且须与 envelope 字段一致（不符 fail closed，R2；对齐 B2 inbox 回填源规则）。

现状盘点（main `a52d8c03`）——S4-C 需要接线的**真实生产入口**：
- workspace turn outbox 生产在 `WorkspaceBridgeRepository.add_turn_outbox`（workspace `bridge_repository.py:62`）；execution output outbox 生产在 `ExecutionRepository.commit_terminal` publish 分支（`execution_repository.py:853`）。两处当前都不写 `conversation_id`/`producer_purge_revision`（040 列保持 NULL）。
- claim envelope 当前为 4 元组（`ClaimedWorkspaceEvent` workspace `bridge.py:72` / `ClaimedExecutionEvent` execution `bridge.py:31`），不携带 scope/epoch；claim 事务边界已合规（`_claim_turn`/`_claim_output` 各自 `session.begin()` + `skip_locked`，不持 outbox 行锁等 Guard）。
- consumer 当前 `validate_turn_claim`（workspace `bridge_repository.py:169`）/`validate_output_claim`（execution `bridge_repository.py:307`）为 4 元 CAS（status/digest/attempt/claimant），缺 conversation_id/epoch 两元；位置已在 Guard + Conversation 行锁之后（`consume_turn_event` `agent_control_plane.py:162` / `consume_output_event` `:248`）。
- inbox 生产在 `ExecutionBridgeRepository.begin_turn_receipt`（execution `bridge_repository.py:45`）/`WorkspaceBridgeRepository.begin_output_receipt`（workspace `bridge_repository.py:546`），当前不写 scope/epoch。

**C2. writer 真实 scope/epoch 契约（禁止伪造）**

- 新写（S4-C 起）必须写真实 `conversation_id` 与 `producer_purge_revision`（产生同事务快照的 `Conversation.purge_revision`）。**workspace 与 execution 两侧都从 Conversation 行锁内读 `Conversation.purge_revision`（R1）**：workspace 侧**复用** `submit_turn` 已持有的 Conversation 行锁（`reserve_user_turn` 取锁、事务结束前持续，round-3 修订：不重复取锁）；execution 侧在 `commit_terminal` 建 outbox 行前显式取 Conversation 行锁并读其 `purge_revision`。**不得**用 `fence.purge_revision`（对齐值非快照）或 `fence.revision` 冒充（R1）。
- **幂等重放不重写**：`add_turn_outbox` 命中既有行 / `commit_terminal` `terminal_digest_match=True`（idempotent replay）时，scope/epoch 已持久化即保留，重放不重写、不推进（与 S3 `created`/`idempotent_replay` 标志驱动的 checkpoint 推进解耦）。**重放遇 040 列仍 NULL 的旧行不得由 S4-C writer 回填（NULL 不补写，归 backfill/catch-up）**（R6，与 B3 禁伪造历史 epoch 一致）。
- 身份一致性：writer 写 scope/epoch 前必须与 event 身份一致（跨 Conversation 写防 A→B；沿用 S3-C `_require_run_identity`/`_require_fence_identity` 同模式）。
- **回填边界**：历史行 `producer_purge_revision` 保持 NULL + 登记 `epoch_unresolvable`（B3），S4-C 只负责新写，**不得**拿当前值回填历史行。

**C3. consumer Guard 内六元组 CAS**

Guard 内、Conversation 行锁后、fence 裁决处（`consume_turn_event`/`consume_output_event` 现 `validate_*_claim` 位置），claim 验证从 4 元扩为 **6 元**：

```text
event_id（= outbox row.id = envelope.event.event_id）
+ payload_digest（row = envelope）
+ attempt_count（row = envelope）
+ claimant_id（row = envelope）
+ conversation_id（row = envelope = event 三源一致，见下）
+ producer_purge_revision（row = envelope）
```

**成员比对规则（R2，round-3 S1 修订）**：
- 行值一律在**消费事务内 `FOR UPDATE` 重读**后取得（与 claim 装载隔离，防 claim→consume 间被接管）；不持行锁的陈旧读取不得用于 CAS。
- `event_id`/`payload_digest`/`attempt_count`/`claimant_id`：逐项与 envelope 比对，不符 `*IntegrationConflictError`。**takeover 拒绝仍完全由 `attempt_count`+`claimant_id` 承载**（worker A 的 envelope 携 attempt N，行现为 N+1/claimant B → 拒绝），两新列不参与接管拒绝（C6 takeover 措辞改正）。
- `conversation_id`：**当该成员非 NULL 时**参与比对。**turn 与 output 路径都是三源** `row == envelope == event`，且三者都与 Guard 锁定 Conversation 一致（round-3 S1：workspace outbox 明确存在独立 `conversation_id` 列 `models.py:479`，S4-C writer 又要求填该列，故 turn 与 output 都校验三源——防止 workspace outbox 行被回填或污染后绕过行值校验）。任一非 NULL 成员不符即 fail closed。
- `producer_purge_revision`：**当该成员非 NULL 时**参与比对（行 == envelope，均 claim 装载自同锁行）；消费事务内重读后与 envelope 比对。NULL（历史/backfill 期行）不参与 CAS 值比对，由下方 epoch 分类处理。
- **NULL-scope 行处理**：**row/envelope 的 `conversation_id` 为 NULL 但 event 非 NULL**（历史未回填行）→ **fail closed、不消费**（round-3 S1 措辞修正：`envelope` 装载自 row，row 为 NULL 则 envelope 同为 NULL，不存在「envelope 非 NULL、row NULL」的组合），由 S4-C catch-up 回填 scope（已填后重试成功）或登记 `tenant_scope` scope 类 issue（不可解析则事件保持未消费、随 backfill 收敛，最终 verify 双维 fail closed）；**不得**因 claim 时 NULL 而静默接受，也**不得**在消费路径把 NULL-scope 行当作当前 scope 消费。

任一不符 fail closed（`*IntegrationConflictError`），不盲写 inbox、不复活正文。

**epoch 语义**（消费时点在 Guard + Conversation 行锁后、fence 裁决位置比对当前 `Conversation.purge_revision` 与 fence 状态）：
- producer epoch == 当前 且 fence active → 正常消费，scope/epoch 写入 inbox（C1 第 4 跳）。
- producer epoch < 当前（purge/restore 已推进 epoch）→ **stale epoch**：迟到写，只能 tombstone/reconcile，**不得复活正文**。**判定须同时看 fence/purge_state**（R4）：仅当 `purge_state in {running, completed}` 或 fence erasing/erased 才 stale；soft-delete（SCHEDULED）/restore 推进 `Conversation.purge_revision` 但 fence 仍 active 时，pre-existing 事件**不得**仅因 token 推进被 tombstone（正文从未 erase、fence 允许写）。**stale 的处理统一走 round-4 S2 双事务协议**（round-5 修订，消除「写 inbox 前 raise」与「Tx1 正常提交」冲突）：消费事务在 Guard + Conversation 行锁后、fence 裁决位置**检测** stale（不 raise、不回滚），按下方「**unknown/stale 的双事务协议**」状态表执行——Tx1 **正常提交** inbox `rejected` + tombstone 证据，Tx2 按 claim CAS 终态化 outbox（workspace `status='cancelled'` + 清 claim + 受控 `last_error_code`；execution 写既有 decision 列）。**workspace 的 `LateBodyWriteRejectedError` 在 S4-C 仅用于正文写路径的 fence 裁决**（S3-E §8 已接），**不是** stale 消费的终态机制；`consume_turn_event` 的 stale/unknown epoch 不得 retry-forever→dead_letter，须落 S2 双事务确定性终态。
- producer epoch > 当前 → **数据异常**：fence 对齐路径可能制造「列已推进但 fence 未对齐」窗口（R1），一律 fail closed 不消费、不登记（无受控 issue_code，不新增枚举，C7 不变），不得伪造终态。
- producer epoch NULL/缺失（历史行）→ **unknown epoch**：tombstone-resolve 双相（R4）——**先**在集合锁临界区内写 inbox `receipt_tombstone_state='redacted'` + `receipt_tombstone_digest`（B1f，同事务），**再**登记 `epoch_unresolvable` reconcile（consumer 可达分支：scope 已知 `conversation_scope` 阻该 Conversation purge / scope 未知 `tenant_scope` 阻 tenant enable；**orphan 分支仅 S4-B catch-up/discovery 可达**，见下 round-3 S3），**不得当作当前 epoch 正常消费**；B4 resolved 证据只能从集合锁临界区内产生。**orphan 分支可达性（round-3 S3）**：consumer 在分类前先执行 Guard + Conversation 行锁（`consume_turn_event` `agent_control_plane.py:178`/`consume_output_event` `:260`，`include_deleted=False`），Conversation 已物理删除时在分类前即失败——**orphan 登记只由 S4-B catch-up/discovery 可达**（B4 具名 orphan reconcile），consumer 的 unknown-epoch 分支实际只覆盖 `conversation_scope`（scope 已知）/`tenant_scope`（scope 未知）；契约在此删除「consumer 登记 orphan」的路径（避免「先锁 Conversation 又要求 Conversation 不存在」自矛盾）。

**unknown/stale 的双事务协议（round-4 S2 修订，冻结，状态表）**：当前 dispatcher 在消费异常时回滚消费事务、再走独立失败/terminalize 事务（`agent_control_plane.py:575` 消费事务、`:592` ACK 事务、`:630` 独立 terminalize），消费事务内提交的 tombstone/ledger 会被回滚。**冻结「无 migration」选择**（C7 边界保持）：workspace outbox 无 `decision_*`/`decided_at` 列（仅 `last_error_code`，`models.py:476`），execution outbox 有（`models.py:870-872` 决策 CHECK，S3-E 已用）；**不得**为 S4-C 新增 migration 添加 outbox 证据列。**stale 与 unknown 拆开**：stale（producer epoch 已知旧值）只写 inbox tombstone deterministic evidence、**不**登记 `epoch_unresolvable`；unknown（epoch NULL，不可解析）才写 inbox tombstone + `epoch_unresolvable` ledger。**第一事务提交后的 inbox 状态冻结为既有 `rejected`**（`processing/consumed/rejected` 枚举，workspace `models.py:497`/execution `models.py:955`）。

状态表（round-5 修订，按 workspace/execution × unknown/stale × Tx1/Tx2/replay 展开；execution Tx2 补 `decision_actor_id`）：

| 维度 | 表 | unknown epoch（`producer_purge_revision IS NULL`） | stale epoch（已知旧值 < 当前，fence 非 active） |
|------|-----|---------------------------------------------------|--------------------------------------------------|
| **Tx1 消费事务**（具名 outcome，正常提交不 raise） | workspace inbox | `status='rejected'` + `last_error_code=<具名 code：unknown→`epoch_unknown_rejected` / stale→`epoch_stale_rejected`>` + `receipt_tombstone_state='redacted'` + `receipt_tombstone_digest=<64-hex>`（集合锁临界区内，同事务）；ledger：登记 `epoch_unresolvable`（scope 已知 `conversation_scope` / 未知 `tenant_scope`；orphan 仅 catch-up/discovery，round-3 S3） | 同左 inbox：`status='rejected'` + `last_error_code='epoch_stale_rejected'` + `receipt_tombstone_state='redacted'` + `receipt_tombstone_digest`；ledger：**不**登记 `epoch_unresolvable`（P1-b） |
| | execution inbox | 同左（`execution_inbox` 的 `rejected` + `last_error_code=<同具名 code>` + tombstone 证据） | 同左 |
| **Tx2 终态化**（第二独立事务，claim CAS） | workspace outbox | `status='cancelled'` + 清 claim（`claimed_by/claimed_at=NULL`）+ `last_error_code=<具名 code>`（`models.py:476` 唯一受控字段）；**同事务**把对应 Message 置 `turn_dispatch_state='abandoned'` + `turn_dispatch_error_code=<同一具名 code>`（workspace 两个 error_code 字段用**同一 code**，round-8 冻结；schema 已支持 `abandoned`，`models.py:211-212`）；**不写** decision 列（workspace 无此列，无 migration） | 同左 |
| | execution outbox | `status='cancelled'` + 清 claim + 既有 decision 列**四元全写**：`decision_actor_id=uuid.UUID(int=0)`（系统裁决 sentinel，S3-E `terminalize_output_late_write` 同款）+ `decision_reason=<具名 code>` + `decision_digest=<snapshot_digest(digest envelope)>` + `decided_at=<now>`（满足 `ck_agent_exec_outbox_decision` 全有或全无，`models.py:870-872`；**缺 `decision_actor_id` 会违反 CHECK**）；**同事务**把 Run 置 `output_publish_state='suppressed'`（S3-E 同模式，`bridge_repository.py:548+`） | 同左 |
| **Tx2 后重放**（第二步失败/崩溃） | 两表 | 识别已提交证据（inbox `status='rejected'` + `receipt_tombstone_digest` 存在 + ledger `epoch_unresolvable` 已存在）→ **锁后检查 outbox 精确终态**（round-7：任意 `cancelled`+清 claim 不视为本次终态）：**精确终态 =** `status='cancelled'` + 清 claim + workspace `last_error_code == 具名 code（unknown→`epoch_unknown_rejected` / stale→`epoch_stale_rejected`）` 且 Message `turn_dispatch_state='abandoned'` + `turn_dispatch_error_code == 同一具名 code` 匹配 / execution decision 四元精确匹配（`decision_actor_id=UUID(0)` + `decision_reason == 同一具名 code` + 重算 `decision_digest` 匹配 + `decided_at` 非空）且 Run `suppressed` → **no-op**；未终态且 **outbox `status='claimed'`** 且 claim 四元匹配 → 续做 Tx2；未终态且状态为 `pending/dead_letter/published/其他 cancelled` 或 claim 不匹配 → **fail closed**（`*IntegrationConflictError`，不静默吞掉）。**不重复写证据、不回到 retry** | 识别已提交证据（inbox `status='rejected'` + `receipt_tombstone_digest` 存在）→ **锁后检查 outbox 精确终态**（round-7）：同上三分支（workspace 侧精确终态不含 ledger 判据；execution 侧同左精确判据）；**不重复写证据、不回到 retry** |
| **claim CAS（Tx2）** | 两表 | `event_id` + `payload_digest` + `attempt_count` + `claimant_id` 全匹配才终态化；不匹配 → `*IntegrationConflictError`（takeover，不覆盖新 claim） | 同左 |

**证据承载（P1-a）**：deterministic 终态证据由 **inbox `receipt_tombstone_digest`（64-hex，B1f）+ ledger `resolution_digest`/`resolved_at`** 承载；workspace outbox 不新增证据列（无 migration），`status='cancelled'` + `last_error_code` 仅作终态标记、不承担证据。B4 resolved 证据只能从集合锁临界区内产生。unknown epoch（NULL）tombstone-resolve 双相：**先**在集合锁临界区内写 inbox `receipt_tombstone_state='redacted'` + `receipt_tombstone_digest`（B1f，同事务），**再**登记 `epoch_unresolvable`。

**具名 reason code 与 digest 契约（round-8 冻结 + round-9 拆分落点）**：
- **两个具名 code 冻结**（**实现时**加入 `SUPPRESSION_REASON_CODES` allowlist，`agent_suppression_reasons.py:13`，随第二实现 PR 落地并配参数化回归测试，round-9 拆分）：unknown epoch → **`epoch_unknown_rejected`**；stale epoch → **`epoch_stale_rejected`**。二者与既有 `late_body_write_rejected`/`operator_suppressed` 同域受控枚举；**不**登记新 code 会被归一成 `operator_suppressed`，unknown/stale 将失去可区分身份（round-8 P1 根因）。Tx1 inbox `last_error_code`、Tx2 workspace outbox `last_error_code` 与 Message `turn_dispatch_error_code` **三者用同一具名 code**（workspace 两个 error_code 字段不分裂，round-8 冻结）；execution `decision_reason` 同用该 code。
- **execution `decision_digest` envelope 冻结**（round-8）：`decision_digest = snapshot_digest({...})`，复用 `app.contexts.agent_execution.domain.snapshots.snapshot_digest`（SHA-256 over canonicalized dict，`snapshots.py:149`），与 S3-E `terminalize_output_late_write` 同一 helper。envelope 输入（版本化键名）：
  ```text
  {
    "schema_version": 1,
    "actor_id": str(uuid.UUID(int=0)),        # 系统裁决 sentinel，与 decision_actor_id 同值
    "reason": <具名 code>,                     # epoch_unknown_rejected / epoch_stale_rejected
    "event_id": str(event_id),                 # 该 outbox 事件 id
    "receipt_tombstone_digest": <64-hex>,      # Tx1 已提交的 inbox tombstone digest（证据绑定）
  }
  ```
  **重算匹配** = 用上述同一输入（envelope 里已存的值）重算 `snapshot_digest` 与 `decision_digest` 比对；键名/版本/helper 冻结，不同实现不得自造 digest 输入（round-8 P1：否则互不兼容的「精确终态」）。

**`epoch_unresolvable` ledger 生命周期（round-5 P1-2 + round-6 P1 冻结）**：登记在 Tx1（集合锁临界区内，同事务）；状态机沿用 B4 单条 `open -> acknowledged -> resolved`（`(id, revision)` CAS，`revision+1` 不回退）；**最终状态 = `resolved`**，须带证据——`resolution_digest`（解决结果的 canonical digest）+ `resolved_at`，由 `ck_..._resolution_evidence` 强制（`(state='resolved') = (resolution_digest IS NOT NULL AND resolved_at IS NOT NULL)`）。**resolve 触发与证据源**：S4-D transport participant 完成对旧 epoch 事件的 tombstone 后，用 **inbox `receipt_tombstone_digest`**（Tx1 已提交的 64-hex）作为 `resolution_digest` 写入并置 `resolved`；**不得**在未 tombstone 的情况下置 resolved（B4）。**重放匹配条件（round-6 + round-7 修正：ledger resolved 不能代替 Tx2 终态；精确终态须验身份与投影）**：ledger `resolved` 只证明 **tombstone evidence 有效**（inbox receipt tombstone digest 与 `resolution_digest` 匹配），**不证明独立 Tx2 已把 outbox 置精确终态**——S4-D resolve 与 Tx2 outbox 更新是两个独立动作，Tx1 提交 → Tx2 崩溃 → S4-D resolve → 重放时 outbox 仍可能 `claimed`、claim 未清、execution decision 四元未写。**重放流程（round-7/8 冻结）**：重放识别 `epoch_unresolvable` 已存在且 inbox `rejected` + `receipt_tombstone_digest` 匹配后，**仍须锁后检查 outbox 精确终态**（round-7 精确谓词 + round-8 具名 code/digest，见状态表 Tx2 后重放行与「具名 reason code 与 digest 契约」）——(a) outbox 已处**精确终态**（workspace：`status='cancelled'` + 清 claim + `last_error_code == 具名 code` + Message `turn_dispatch_state='abandoned'` + `turn_dispatch_error_code == 同一具名 code`；execution：`status='cancelled'` + 清 claim + decision 四元精确匹配含 `decision_actor_id=UUID(0)` + `decision_digest` 重算匹配 + Run `suppressed`）→ no-op 返回；(b) outbox `status='claimed'` 且当前 claim 匹配（`event_id`+`payload_digest`+`attempt_count`+`claimant_id`）→ **续做 Tx2**（补终态化 + 清 claim + 写投影）；(c) outbox 状态为 `pending/dead_letter/published/其他 cancelled` 或 claim 不匹配 → `*IntegrationConflictError` fail closed（不静默吞掉）。ledger `resolved`/`resolution_digest` 只作 tombstone evidence 校验，不作为 Tx2 已完成的判据。epoch 分类与 purge_state 关系：stale 判定必须**同时**考虑 fence 状态（`purge_state in {running, completed}` 或 fence erasing/erased 才 stale）；soft-delete（SCHEDULED）/restore 推进 `Conversation.purge_revision` 但 fence 仍 active 时，pre-existing 事件**不得**仅因 token 推进被 tombstone（正文从未 erase、fence 允许写，R1 快照语义下该事件 epoch 本就该是旧值但正文可写）——若契约坚持 token 比较，则须显式声明「pre-delete 在途事件在 SCHEDULED/restore 后一律 tombstone」及产品代价（首轮 P1-1 并发面，数据面 P0-3 同源）。

**C4. claim 独立短事务 + 锁序矩阵（D8 保持 + 扩展）**

- claim 保持独立短事务：`_claim_turn`/`_claim_output` 各自 `session.begin()`、`skip_locked`，**不持 outbox row lock 等待 Guard**（不变量 1）。S4-C 不改变 claim 事务边界；仅在 claim 事务内**锁定读取**两字段到 envelope（R2，C1 第 3 跳）。**claim 期间 scope/epoch 列可被并发变更**（S4-B backfill `_backfill_source_row` 的 `UPDATE ... SET conversation_id ... WHERE conversation_id IS NULL` 无 status 谓词，可回填仍 `claimed` 行）——六元 CAS 在**消费事务内 FOR UPDATE 重读**行值（R2）把 claim 装载值当参考、以重读值为准：若 claim 后 scope 被 backfill 回填，row 现值 ≠ claim 时值 → CAS 判 `*IntegrationConflictError`（不消费，重试）；若 backfill 登记 issue 使行投影非 NULL，行已不可消费、重试至退避/放弃（事件交付由 backfill reconcile 语义承载）。此「重读为准」正是 claim 装载与消费重读隔离的目的（R2），不构成静默接受 NULL。
- 消费锁序（D8 冻结保持）：`Guard -> Conversation 行锁 -> owner advisory lock -> fence 重验 -> **transport/external aggregate 集合 advisory lock（最内层）** -> 源 transport 行 FOR UPDATE 投影写`。任何路径不得在链前取集合锁（禁 `aggregate -> Guard` 与 `Guard -> owner/fence -> aggregate` 反向 AB-BA）。
- **集合锁何时取（R3）**：仅当同事务写该源行的 reconcile issue / 重算投影时才取集合锁（S4-B B4 流程）；纯 outbox/inbox metadata 写（不含 ledger）不取集合锁。consumer 登记 `epoch_unresolvable`（unknown epoch）时，**集合锁目标 = ledger 行自身的 `source_table/source_row_id`**（inbox 行用 inbox 行 PK），**不是** B2 scope 来源的 outbox 行；`owner_key` = 该 source_table 的 transport owner（`workspace.transport.v1`/`execution.transport.v1`，与 backfill `OWNER_BY_TABLE` 同源），**不得**用 consumer 的正文 owner。锁序不变量：consumer 的 Guard 事务在**同一事务**内完成 (a) inbox metadata 写 + (b) receipt/状态写 + (c) issue 插入 + (d) 投影重算，(c)(d) 在集合锁临界区内、按 D8 先取集合锁再写 inbox 行投影；`begin_*_receipt` 的 inbox 行 `FOR UPDATE`（幂等重读）不得先于集合锁——envelope 在 claim 时已携带 epoch/scope 状态，consumer 在 begin_receipt 前即可判定是否需要集合锁（防「先持 inbox 行锁再等集合锁」反向等待）。
- **scope 冲突降级登记归 backfill（R3）**：A≠B（两源均非 NULL）在 6 元 CAS（fence 前）fail closed；冲突降级 `tenant_scope`/`ambiguous_mapping` 的**登记由 backfill discovery 完成**（B4 已实现），consumer 不登记 scope 冲突（防「CAS 拒绝后注册路径不可达」自矛盾）。
- 锁序矩阵（S4-C 生产路径全集）：writer 生产 outbox / consumer 消费 + 写 inbox / consumer 登记 `epoch_unresolvable` 三条路径均遵循 `Guard -> Conversation -> owner -> fence -> [集合锁]`；纯 backfill/运维路径只取集合锁（B4）。**S4-D/E transport participant 取集合锁时点须位于 Conversation 行锁/owner 之后**（与消费者同序），禁止在取得 Conversation 行锁前取集合锁。

**C5. S4-B catch-up 与 verify 门禁（B7 收敛）**

- **触发时机（R5）**：S4-C writer 全量部署且新写路径已带 scope/epoch（040 列新写非 NULL）后，从 **tenant 起点**执行 S4-B catch-up（`python -m app.composition.agent_transport_backfill` 幂等重扫）。「capability 清零」抽象删除，绑定 C8「四跳一致」验收。
- **不保留跨调用 UUID 游标**：每表存量行做完整幂等重扫；`--max-rows` 仅截断单次调用，续跑从 tenant 起点重扫、不跨调用持久化游标（B7，弃 UUID max 高水位）。
- **catch-up 扫描谓词写全（R5）**：对齐 `_select_actionable_batch` 四分支——(1) `conversation_id IS NULL AND scope_reconcile_state IS NULL`（NULL-scope 未处理）、(2) ref-bearing outbox 行 ref 未登记、(3) scope-set 但 A≠B mismatch（discovery）、(4) `conversation_id IS NOT NULL AND producer_purge_revision IS NULL AND scope_reconcile_state IS NULL AND 无 mismatch`（epoch-only）。已登记 issue 的行经 `scope_reconcile_state IS NULL` 守卫退出 actionable 扫描（不饥饿后续行）。
- **最终 verify 不豁免 NULL 行 + 不用扫描守卫（R5）**：每表凡 `conversation_id IS NULL` 必须匹配**具名 scope 类 issue**；凡 `producer_purge_revision IS NULL` 必须匹配 `epoch_unresolvable`——双维度各自独立 fail closed、互不豁免（B7）；禁时间谓词豁免、禁以任意 issue 充数。**verify 按原始数据维度逐行检查，`scope_reconcile_state IS NULL` 守卫只用于扫描去重、不得用于 verify**——已投影为 pending 的行同样必须通过（修复「投影非 NULL 后 verify 豁免」歧义）。
- **catch-up 幂等性**：已填行不被覆盖、已登记 reconcile 不重复（ON CONFLICT DO NOTHING），全量重扫安全且能捕获 point-in-time 窗口漏掉的并发新写。
- **期间并发新写**：S4-C 部署窗口内旧 writer 仍可能产生 NULL scope 行 → 部分唯一索引（`IS NOT NULL` 作用域）不阻塞、不误回填；catch-up 收敛 + verify 清零后才允许 purge（S5 scheduler gate 前置，B7 并发新写处理）。

**C6. 反例矩阵（实现与复审共用）**

| 反例 | 触发 | 期望行为（fail closed） | 不得发生 |
|------|------|------------------------|----------|
| stale epoch | producer 在 purge_revision=5 写 outbox；Conversation 已 erase（=7，fence erasing/erased 或 purge_state running/completed）；consumer 读 fence 非 active、envelope epoch=5 | 迟到写 tombstone/reconcile（`LateBodyWriteRejectedError`/`LateOutputReadRejectedError` deterministic），正文不复活 | 按当前 epoch 正常消费并写正文 |
| stale epoch（soft-delete/restore） | Conversation 仅 SCHEDULED 或已 restore（token 推进但 fence 仍 active、正文从未 erase） | **不**仅因 token 推进 tombstone（R4：stale 判定须看 fence/purge_state）；pre-existing 事件按当前 epoch 处理 | 把 token 推进误判为 stale 并 tombstone 未 erase 的正文 |
| 跨 tenant | envelope.tenant_id ≠ outbox 行 tenant，或事件 tenant ≠ Conversation tenant | fail closed；不跨 tenant 映射（B2 tenant 谓词） | 把 A tenant 行映射到 B tenant Conversation |
| scope mismatch（A≠B） | row.conversation_id ≠ event.conversation_id（两源均非 NULL；turn/output 均三源，round-3 S1） | 6 元 CAS fail closed；`tenant_scope`/`ambiguous_mapping` 降级登记归 backfill discovery（R3） | 用任意一方继续消费 / consumer 登记冲突 |
| NULL-scope 行 | row/envelope.conversation_id 均为 NULL 但 event 非 NULL（历史未回填；envelope 装载自 row，round-3 S1） | fail closed、不消费；catch-up 回填 scope 或登记 `tenant_scope`；verify 双维收敛 | 因 claim 时 NULL 而静默接受 / 当当前 scope 消费 |
| unknown epoch | `producer_purge_revision IS NULL`（历史行） | tombstone-resolve 双相（R4）：集合锁内先写 inbox receipt tombstone 证据、再登记 `epoch_unresolvable`（scope 已知 `conversation_scope` / 未知 `tenant_scope`；**orphan 仅 catch-up/discovery 可达**，round-3 S3），双事务协议终态化 outbox，不当作当前 epoch | 当作当前 epoch 消费 / 静默通过 gate / resolved 无证据 |
| orphan | 源 Conversation 已物理删除 | 具名 orphan reconcile（**仅 S4-B catch-up/discovery 登记**，round-3 S3：consumer 先锁 Conversation 后 orphan 不可达），不猜 UUID、不并入现存 Conversation；不阻塞 purge、需运维确认到 resolved | 猜测 UUID / 并入现存 Conversation / 复活正文 |
| takeover | worker A claim attempt N；B 接管 attempt N+1；A 的 stale consume/terminalize | claim CAS 拒绝（`attempt_count`+`claimant_id` 承载，R2），不覆盖新 claim | 清掉后来 worker 的 claim 或覆盖同期裁决 |
| claim lease 过期 | `claimed_at <= stale_before` B 重 claim 同一事件、A 旧 attempt 仍持旧 epoch | claim CAS 拒 A 旧 attempt；新 delivery 按新 claim 处理 | 旧 attempt 覆盖新 claim / 复用旧 epoch 消费 |
| partial ACK | transport/external owner 未全部 ACK | 任一 owner 未 ACK，purge operation 不得写 `completed`（D6）；不复活正文、不推进 completed | 部分 ACK 把 operation 标 completed |
| 重放（replay） | 同一事件重复 delivery（inbox receipt 已 consumed / terminal digest 命中） | 幂等命中，不新建 Run、不重写 scope/epoch、不推进 checkpoint（`created=False`）；purge 后重放被 fence verdict 拒 | 重复建 Run / 重写 producer metadata / 复活正文 |
| purge-win | purge suppress/erase 与 claim 竞争（purge-before-claim 或 claim-before-purge） | claim-before-purge 暂停后 purge suppress，worker 恢复但 fence 裁决拒正文写（deterministic）；purge-before-claim 的 tombstone 行不再被正常 claim（S4-D 态） | 在 purge 后经 claim 复活正文 |

**C7. 明确不做（S4-C 边界）**：不写 schema/migration（不改 040）；不实现 041 guard 演进（S4-E）；不实现 `workspace.transport.v1`/`execution.transport.v1`/`external.payload.v1`/`runtime.private.v1` participant（S4-D/E）；不做 fault 矩阵（S4-F）；不启用 purge scheduler（S5）；`erase_available` 保持 `False`；不收紧既有列为 NOT NULL；不新增 inbox status 枚举；不实现真实 Pi Worker / 云对象存储生产 adapter。

**C8. 验收矩阵（S4-C 实现时逐项验证，merged-boundary 验收）**：C8 为**合并边界验收**——若拆两 PR，各 PR 只验证其风险域子集（见 C9），不得单 PR 声明「六元 CAS」「四跳一致」。编号矩阵（对齐 B8 命名项）：
1. 传播链四跳一致：新写 outbox 行带真实 `conversation_id`/`purge_revision`（Conversation 行锁内读，R1）、claim envelope 携带（claim 短事务锁定装载，R2）、inbox 行带（消费事务内重读源 outbox 一致，R2）。
2. 六元组 CAS 表驱动：行值 `FOR UPDATE` 重读、非 NULL 成员比对、**turn/output 均三源**（round-3 S1）、NULL-scope fail closed（row/envelope NULL、event 非 NULL）、takeover 由 attempt+claimant 承载（R2）。
3. C6 各反例（含 stale soft-delete/restore、NULL-scope、claim lease、partial ACK、**orphan 仅 catch-up/discovery 可达**）真实 PostgreSQL 复现 + 变异验证（逐项还原缺陷实现均被测试击杀）。
4. writer 禁伪造 epoch（不用 `fence.purge_revision`/`fence.revision`/Conversation `revision`/时间戳，R1）。
5. 幂等重放不重写 scope/epoch、NULL 旧行不补写（R6）。
6. claim 短事务不持 outbox 行锁等 Guard（并发 claim 无死锁）；两新列与 claim 同事务锁定读取。
7. consumer 写 inbox metadata 与 receipt 同事务；unknown/missing epoch 集合锁临界区 tombstone-resolve 双相（先证据后 `epoch_unresolvable`，R4）+ **双事务协议状态表**（round-4/5/6/7/8 S2：unknown 才登记 `epoch_unresolvable` / stale 不登记；stale 统一走双事务不 raise；Tx1 inbox `status='rejected'` + tombstone 证据 + **具名 code**（`epoch_unknown_rejected`/`epoch_stale_rejected`）、Tx2 按 claim CAS 终态化 outbox——workspace `cancelled`+清 claim+同一具名 code+Message `abandoned` 投影、execution decision 四元含 `decision_actor_id`+**冻结 digest envelope**+Run `suppressed`；`epoch_unresolvable` ledger resolved + 证据；**重放锁后检查 outbox 精确终态三分支（round-7 精确谓词 + round-8 具名 code/digest，续做只接受 `claimed`）**）。
8. consumer 集合锁目标/owner_key 正确（inbox PK + transport owner，R3）；先集合锁后 inbox 行 FOR UPDATE，无反向等待。
9. catch-up 自 tenant 起点、无跨调用游标、扫描谓词四分支（R5）；verify 双维独立 fail closed、不用 `scope_reconcile_state IS NULL` 守卫豁免。
10. S4-B 专项 + 邻近回归全绿 + 全量 pytest 0 failed（`external_network` 手工 opt-in 除外，R6）+ ruff 0 + mypy baseline 0 回归 + docs gate + `git diff --check`。
11. **具名 code 参数化回归测试（round-9，随第二实现 PR）**：`suppression_reason_code("epoch_unknown_rejected") == "epoch_unknown_rejected"`、`suppression_reason_code("epoch_stale_rejected") == "epoch_stale_rejected"`（不归一成 `operator_suppressed`）；变异验证——从 `SUPPRESSION_REASON_CODES` 剔除任一新 code 对应测试变红（击杀回退变异）；允许对照：既有 5 code 归一行为不变。

**C9. PR 拆分与评审/收敛流程（接 TD-092）**

- **第一 PR（本 PR）纯文档**：本 delta，docs gate + `git diff --check`；同 HEAD 三面首轮并行复审（数据/状态机、并发/锁序、测试/运维），P0/P1 清零后再开实现 PR。**三面首轮复审结果（P0/P1/P2/P3 计数）必须记录到 work-log，P0/P1 清零后才可开实现 PR（R5）**。
- **实现 PR（round-3 冻结为至少两 PR，round-4 S2 修订措辞）**：S4-C 已同时涉及 producer（outbox 写 scope/epoch）、claim/consumer（envelope + 六元 CAS + inbox）、deterministic terminalization（stale/unknown 双事务协议状态表）与 catch-up 四个风险域，超单风险域——**不再「范围过大时」才拆，冻结为至少两个实现 PR**（round-3 P2 修订）：
  1. **Producer propagation + replay/catch-up**：writer 写 scope/epoch（R1/C1/C2）+ 幂等重放 + S4-B catch-up（C5）。验证 C8 项 1/4/5/9。
  2. **Claim/consumer CAS + deterministic terminalization**：envelope 扩展 + 六元 CAS（C3）+ inbox 写 + stale/unknown 双事务协议**状态表**（round-4 S2）+ consumer 集合锁（R3）。验证 C8 项 2/6/7/8/10。**round-9 追加**：本 PR 承接 `SUPPRESSION_REASON_CODES` 新增 `epoch_unknown_rejected`/`epoch_stale_rejected`（`agent_suppression_reasons.py:13`，允许重复剔除时测试变红的参数化回归测试见 C8 项 11）——**契约 PR 保持纯文档，allowlist 源码改动不提前混入**。
  各 PR 只验证其风险域子集，不得单 PR 声明「六元 CAS」「四跳一致」（C8 merged-boundary 验收）。禁止单超大 PR（S2-D/E 7 轮复审教训）。
- **实现期间保持 Draft**，`Backend iteration` risk-targeted（TD-092 治理：Draft 只产生非 required check）；代码稳定后转 Ready，最新 HEAD 执行 Backend full。
- **收敛目标 2-3 轮**；连续两轮出现新 P1 立即停止补丁式修复，回契约或拆分/重构（TD-092 首个后续验证任务）。
- **findings 按根因族一次返修**，并横向检查等价入口：writer（`add_turn_outbox`/`commit_terminal` outbox 生产）、claim（`claim_turn_outbox`/`claim_output_outbox` + envelope 装载）、consumer（`consume_turn_event`/`consume_output_event` + 6 元 CAS + inbox 写）、heal（reconcile issue `open->acknowledged->resolved` CAS + 投影重算）、verify（S4-B 五维 + catch-up 重扫）及 S3-E 迟到写/terminalize 等价路径。

#### R1-S4-D Transport Participant 契约细化（2026-08-07，先于代码冻结，纯文档）

> **实现 PR #542 round-1 三面首轮复审与 5 根因族一次返修（2026-08-08，commit `24c2b601`）**：三面（数据/状态机 0/1/3/2、并发/锁序 0/0/2/3、测试/运维 0/5/4/3，P1=6）按 5 根因族一次返修：① **Run 投影维度**——execution final scan 同时检查 `agent_runs.output_publish_state`（**`pending`/`dead_letter` 计入残留 blocked；`not_required`/`published`/`suppressed` 为终态 pass**——`not_required` 是 failed/cancelled/expired Run 的合法终态，S3-D 不会改写成 suppressed，若计入残留则 purge 永久 blocked），participant **只读判定不清理 execution.core 字段**（Run 正文清除归 S3-D `_clear_terminal_outputs`）；② **scan 反向判别**——补残留 → blocked/fail-closed 直接反例（`purge_blocked_by_transport_scan_nonzero` + checkpoint/operation 三方一致；scan 排除某状态、inbox scan 恒零变异被击杀）；③ **谓词分支**——payload_ref only 行清除用例 + cancelled 并入清除循环 + claim 列 NULL 断言（不依赖 DB CHECK 偶然拦截）；④ **capability gate**——gate 测试断言拒绝后 fence/checkpoint/outbox/inbox 五方零变更（gate 位置错误变异被击杀）；⑤ **契约与实现一致性**——plan 冻结集合锁免取条件（纯 outbox/inbox metadata 写 + transport scan 不写 ledger/投影时可免取；写 reconcile issue/投影必须按全局锁序取）+ `purge_erasure` reason 键值冻结为共享常量 `RECEIPT_TOMBSTONE_REASON`（participant 不得自造字符串）+ 死属性删除。验证：S4-D-A 矩阵 32 passed + 邻近 133 + S2-D/E 58 = 165 passed；ruff 0；mypy 0。**batch3 顺序污染为既有 main 问题**（main 单独跑 6 failed、与矩阵同跑 4 failed、单个通过——TD-080 同类，与 S4-D-A 无关，另记录）。
>
> **定向复核（2026-08-08，HEAD `24c2b601`）与「终态与证据互操作」根因批次（commit `f9903e9e`）**：定向复核 P0=0 / P1=3（附件 P2-1 不成立——`pytest.raises` 已捕获异常、fixture 不进入 rollback、同事务断言可击杀 gate 后移）/ P3=4。按 3 个 P1 一次修复：① **S4-C tombstone 互操作**——purge 侧 inbox 已 tombstone 行接受两类精确匹配（`purge_erasure` 重算匹配 no-op；`status='rejected'` + `last_error_code` 为 `epoch_unknown_rejected`/`epoch_stale_rejected` 之一 + 按该 code 重算 digest 精确匹配 no-op 保留原证据），其余 fail closed——两侧 × 两个 epoch code 参数化测试 + 非 epoch code 反例（含 Tx1 epoch-rejected receipt 的 conversation purge 不再卡死）；② **Run scan 终态谓词统一**——`IN ('pending','dead_letter')` 计入残留、`not_required/published/suppressed` pass（修掉 `<> 'suppressed'` 对合法 `not_required` 的永久阻塞；plan 已统一终态集合）；③ **blocked 三方一致落地**——残留测试改名为 erased-replay fail-closed（ValueError 路径）+ 新增 scan 检测注入残留用例（erase body 后注入 → scan 非零，击杀 scan 恒零变异）+ Run pending 真 blocked 用例断言 reason_code/operation.failure_code/Conversation.purge_state 三方（outbox/inbox 首次-erase-blocked 在构造上不可达——UPDATE 清除一切 scan 计数行，唯一真 blocked 触发是 Run pending，已记录）。P3×4：基类 docstring 同步只读判定、plan commit 回填、claimed/published/dead_letter 循环补 claim 列 NULL 断言、工作台同步。**不翻 registry、不做 ledger resolve、不启动 S4-D-B。**
>
> **S4-D-A merged-boundary 与合并记录（2026-08-09，实现 PR #542，squash merge `5fc5c33b`，评分 93）**：判别力批次（commit `312da9f1`）后轻量复核 P1=2——S4-C tombstone 三元条件判别力（合法 epoch code + 错误 digest fail closed / 合法 code + 正确 digest 但 status != 'rejected' fail closed，两侧 × 两 code 参数化）+ Run `dead_letter` 分支参数化（pending/dead_letter 均 blocked，谓词退化只留 pending 被击杀）——一次修复（commit `3c97d5a5` 判别力 + 文档同步），最终定向核对 **P0/P1=0 通过**（52 passed / 9.94s）。正式评分 93（Original，基线 `3c97d5a5`，commit `875e4e99` 纯文档评分记录）→ 最新 HEAD required checks 全绿（Backend full 10m38s）→ squash merge `5fc5c33b` + 分支清理 + docs closeout（工作台归档 + work-log 索引 + 本记录）。**merged-boundary 结论**：S4-D-A 完成 transport participant 主体（outbox/inbox tombstone + 正文事实谓词 scan + Run 只读判定 + ACK/fencing 全套 + capability gate + S4-C tombstone 互操作），registry 保持 False；遗留 S4-D-B（Ledger Resolve + Activation：共享 ledger API + `epoch_unresolvable` evidence/CAS resolve + 两类 gate 查询 + participant 接入 resolve + merged-boundary 后 registry 统一翻 True 带 mutation kill）、S4-E/F、S5 scheduler、真实 Pi Worker、云对象存储生产 adapter 明确排除。batch3 顺序污染为既有 main 问题（main 单独跑 6 failed、单个通过——TD-080 同类）另记录。
>
> **实现 PR #544 round-1 三面首轮复审与 5 根因族一次返修（2026-08-09，commit `7f58d9ec`）**：三面（数据/状态机 0/2/2/2、并发/锁序 1/2/2/1、测试/运维 0/4/4/2，P0=1/P1=8）按 5 根因族一次返修：① **P0 锁序 AB-BA**——participant「inbox 行锁先于集合锁」↔ backfill「集合锁先于行锁」死锁（真实 PG 双连接实验复现 DeadlockDetectedError）；修复：`_acquire_inbox_aggregate_locks` 在源行 UPDATE 之前取该 Conversation 全部 inbox 行集合锁，erase + resolve 全在临界区内（全链路「集合锁→行锁」与 backfill/consumer 同序）；② **gate blocked 路径**——gate 分支 `expected_revision=N` 与 mark-running 后 `N+1` 恒不匹配必 raise（blocked 契约不可达）；修复：`expected_revision=None`（与 final-scan 对齐）+ participant 级 gate blocked 集成测试（两侧，blocked 三方一致 + resolve 后解除 ACK，revision 1→2→3 追踪）；③ **resolve 与 Tx2/历史出口**——exact-terminal replay 测试（ledger resolved 不代替 Tx2，resolve 不触碰 outbox）+ consumed 无证据行出口冻结（plan D-B-2 补「历史 consumed 行 resolve 由 S5/运维处理」，反例测试证明无证据不伪造）；④ **CAS 并发冲突**——CAS 0 行命中 False 测试（两侧，行不存在 False + rev2 续做）+ participant 忽略 False 记录（集合锁已串行化，CAS 是第二道防线）；⑤ **验证口径与记录**——工作台 149→613 口径修正（CI risk-targeted 实际 613 passed/4m45s）+ batch3 记录更新（现 main 单独跑 10 passed 全绿，原「既有 main 污染」不可复现）。
>
> **S4-D-B merged-boundary 与合并记录（2026-08-09，实现 PR #544，squash merge `81cf83b8`，评分 88）**：定向复核（HEAD `1c829c3e`）P0/P1/P2=0（P3×2 已修：plan consumed 出口段落去重）→ 正式评分 88（Original，基线 `1c829c3e`，评分记录 commit `5d7a5136`）→ 最新 HEAD required checks 全绿（Backend full 10m59s）→ squash merge `81cf83b8` + 分支清理 + docs closeout（工作台归档 + work-log 索引 + 本记录）。**merged-boundary 结论**：S4-D-B 完成 transport participant 的 ledger 闭环——共享 ledger service（backfill/consumer/participant 同一投影实现）+ `epoch_unresolvable` evidence/CAS resolve（只 resolve `conversation_scope` 行）+ 两类 gate 查询 + participant 接入（gate blocked 三方一致 + resolve）+ `workspace.transport.v1`/`execution.transport.v1` registry 激活（merged-boundary 后翻 True，断言同 commit 更新）；`tenant_scope`/`orphan` 不 resolve（留 S5/运维）、历史 consumed 行出口由 S5/运维处理；external/runtime owner 保持 False。**S4-D 全线闭环**：S4-D-A（participant 主体，`5fc5c33b`）+ S4-D-B（resolve + 激活，`81cf83b8`）——transport 两 owner 的 purge eraser + ledger resolve + gate 全链路落地；遗留 S4-E（External payload + Runtime fake：external.payload.v1 participant + migration 041 guard 演进 + RuntimeErasureParticipant conformance fake，`external.payload.v1`/`runtime.private.v1` 激活待 S4-E merged-boundary）、S4-F、S5 scheduler、S6、C1 总验收明确排除。
>
> #### R1-S4-E External payload + Runtime conformance 契约细化（2026-08-09，先于代码冻结，纯文档）
>
> 按 S4-A D1-D8 / S4-B B1-B8 / S4-C C1-C9 / S4-D D-A-1~D-B-3/D-Act-1 冻结 `external.payload.v1` / `runtime.private.v1` 契约。**本 delta 只写文档：不写业务代码、不改 migration 040、不新增 outbox CHECK migration、不实现 migration 041、`erase_available` 全程保持 `False`、不启用 purge scheduler（S5）、不进 S4-F/S6。** 现状盘点基于 main `f7a8a850`（S4-D-A/S4-D-B 已合并，transport 两 owner 激活）。
>
> **三面首轮复审与 8 根因族一次返修（2026-08-09，HEAD `5f655281`，commit `ba881ee4`）**：三面（数据/状态机 1/9/3/1、并发/锁序 2/6/4/1、测试/运维 3/5/5/0，P0=6/P1=20/P2=12/P3=2）横向消化全部 findings，按 8 根因族一次重写本段（不逐条补丁）：① **E-0a 与现 CHECK/已合并测试硬冲突**——冻结「inline-only 清除 + ref-bearing 行 transport 零修改 blocked + external receipt 后清 ref」，**不新增 outbox CHECK migration**（无「suppressed 保留 ref」形态）；② **`registered` 产生者缺失**——冻结由 **staging/reference lifecycle port（B1）** 产生，eraser 只消费；③ **并发 token 无推进者**——`lease_epoch` 推进/接管归 **S5**（S4-E 只验证），`checkpoint.attempt` 按 **participant invocation** 增，测试手动推进 lease 模拟 takeover；④ **`checkpoint_digest` 双语义**——冻结**状态相关语义**（erasing=intent.v1、acked=final scan）；⑤ **receipt 证据链**——`receipt_digest` 直接承载 canonical adapter receipt evidence，不新增列，重放走 receipt lookup/同 key 重算；⑥ **timeout**——可能已生效统一 `unknown`，可证明未发送才 `blocked/erase_timeout`；⑦ **运维**——S4-E 只做 blocked/unknown 查询 + 有证据 reconcile，HTTP/CLI 归 S5，禁无 receipt 强制 erased；⑧ **测试迁移**——inline 用例保持、ref-only 用例改 blocked 零修改、receipt 后清 ref 断言移 B2 互操作矩阵。
>
> **E-0 根因 1：S4-D transport participant 提前清 payload_ref 与 D5 顺序冲突（先冻结修复）**
>
> - 现状（代码实证）：S4-D `erase_transport_body`（workspace/execution `transport_erasure_participant.py:197/218`）用正文事实谓词 `payload_inline IS NOT NULL OR payload_ref IS NOT NULL` **同时清两列**转 `suppressed`——`payload_ref` 被提前清除。
> - 冲突：D5（S4-A）冻结「**先删 external object 取 receipt，再清 transport DB ref**」——transport 提前清 ref 时 external object 可能未删，违反 **receipt-before-clear 顺序**（先清 DB ref 会让 external object 失去追踪入口，`ledger` 仍可定位——问题在**清除顺序违规**而非无法定位）。且 transport 清 ref 无 external receipt 证据。
> - **冻结修复（E-0a）**：transport participant 的 outbox 清除改为**只清 inline-only 行**（`payload_ref IS NULL`）——`SET payload_inline = NULL, status='suppressed'`，满足现 `ck_*_outbox_payload` suppressed 分支（inline/ref 均 NULL）。**ref-bearing 行（`payload_ref IS NOT NULL`）transport 零修改并 blocked（`purge_owner_unavailable`）**——不清 inline、不清 ref、不转 suppressed，整行原样保留。非 suppressed 分支 CHECK 强制 inline/ref 恰一非空，故不存在「inline+ref 混合行」形态。**不新增 outbox CHECK migration**：本契约下不存在「suppressed 保留 ref」形态，`suppressed` 仅由 ref 已 NULL 的行达到；external receipt 后由 `ExternalPayloadErasureParticipant` 清 ref 并转 `suppressed`（ref-bearing 行 inline 本已 NULL，满足现 CHECK）。
> - **E-0b（落地归属）**：本修复作为 **S4-E-A** 的一部分落地——改 transport `scan_transport_body`/`erase_transport_body`（清除谓词收窄为 inline-only + ref-bearing 行提前 blocked）+ 补「transport-before-external」反例 + **已合并测试迁移**（见 E-6 判别点）：inline-only 用例保持原断言；`test_outbox_payload_ref_only_cleared` 等 ref-only 用例**改为断言 transport blocked 且行零修改**（`payload_ref` 仍存在、status 不变）；「external receipt 后清 ref + 转 suppressed」断言**移入 S4-E-B2 互操作矩阵**，不再由 S4-D-A 测试承担。
>
> **E-1 根因 2：external ledger 为删除事实源（source 已空/源行缺失不得漏删或伪造 receipt）**
>
> - external ledger（`agent_external_object_refs`）是 external object 删除的**唯一事实源**（B5）。purge 时以 ledger 为准扫 3 个 ref-bearing source（RunEvent/两 outbox payload_ref）。
> - **`registered` 的产生者（冻结）**：**staging/reference lifecycle port（S4-E-B1）是 `registered` 的唯一正常生产者**——对象 staging/publish 时登记并转 `registered`；external eraser（B2）**只消费 `registered` 行，不生产**。当前 backfill 写 `blocked/unknown_scheme`（`_register_external_ref` 一律 `unknown` scheme，backfill L406-407）——**`blocked/unknown_scheme -> registered` 仅当 scheme 被明确识别且 adapter capability 验证通过时允许**（B1 adapter contract 判定），不满足则保持 blocked。
> - **source ref 匹配规则（新增）**：source 同 ref 时（source ref 仍存在且 == ledger `ref_value`）-> receipt 后清除（D5）；**source 已 NULL/缺失时仍可凭已验证 ledger 完成删除留证**（E-1a 历史兼容——source ref 被并发清但 ledger registered 未 erased，ledger 是唯一事实源，不因 source 已空而漏删）；**不同非 NULL ref 或绑定冲突 -> fail closed**（source ref 存在但 != ledger `ref_value`，或 ledger 绑定与 source 身份冲突，不覆盖、不伪造 receipt）。
> - 源行生命周期：ledger 未 erased 前源行不得物理删除（保留至少为 tombstone，与 B4 源行规则对齐）；orphan（Conversation 已删）由运维/S5 确认；ledger 行自身生命周期（erased 后何时清理）与 S6 365 天 audit prune 一并处理，不并入本 Slice。
> - **E-1a 历史兼容**：source ref 已 NULL（历史/并发清除）但 ledger `registered` 未 erased——仍执行 adapter 删除（以 ledger 为事实源）并写 `erased` + receipt；不伪造「source 仍存在」的假象。
>
> **E-1b 三 source DB ref 唯一清除者（根因 6 补充）**
>
> - **`ExternalPayloadErasureParticipant`（B2）是 3 个 source 的 DB ref 唯一清除者**：RunEvent.payload_ref（经 migration 041 guard）、workspace outbox payload_ref、execution outbox payload_ref——均在 external receipt 后统一清除（清 ref 与 inline 并转 `suppressed`，满足现 outbox CHECK）。
> - **transport participant（S4-D）在 receipt 前零修改 ref-bearing 行并 blocked**：E-0a 修复后 transport 只清 inline-only 行；`payload_ref` 存在时 transport blocked（`purge_owner_unavailable`），不清 inline/ref/status——transport-before-external 反例验证。
> - **清除者之外的其他写路径（不构成 ref 清除）**：backfill `_register_external_ref` 只改 ledger 行（blocked 时修 `conversation_id`），不清 source DB ref；execution.core.v1 gate（RunEvent.payload_ref 存在即 blocked，S3-D）是前置守卫，不清 ref。
> - **ref 承载点边界**：`RuntimeSessionBinding.runtime_session_ref` 归 `runtime.private.v1`（E-5-C），不在 external 扫描范围；`staging_object` capability 当前**无实现、无清除路径**（无 staging 表/列），S4-E 不覆盖，登记 B2 边界外。
>
> **E-2 根因 3：adapter 调用双事务协议（禁持锁做外部 I/O；双事务身份与证据）**
>
> - 冻结为**双事务协议**（镜像 S4-C Tx1/Tx2 模式）。**并发承载（冻结）**：operation 用 `lease_epoch`（**推进/接管归 S5，S4-E participant 只验证**）；checkpoint 用 `state='erasing'` + `attempt`（**按 participant invocation 增**，跨 takeover 递增）+ `checkpoint_digest`（**状态相关语义，E-2c**）。**不使用** external ledger `(id, revision)` CAS 或 `updated_at` CAS——external ledger 无 revision 列，且并发身份不由 ledger 状态承载。
> - **E-2c checkpoint_digest 状态相关语义（冻结，消解 body-scan/intent 双语义）**：`state='erasing'` 时 `checkpoint_digest` = **`external_delete_intent.v1` digest**——对**完整稳定 ledger identity 集合**（`ref_scheme`/`ref_value`/`source_table`/`source_row_id`/`conversation_id` 的 canonical digest，版本化键名 `schema_version:1 + kind:'external_delete_intent'`）的持久化 intent；**`state='acked'` 时 `checkpoint_digest` = final scan digest**（与 workspace/execution/transport 现语义一致）。**attempt 可变但 intent digest 跨 takeover 不变**——takeover 重跑 Tx1 重算 intent digest 与已持久化值精确相等，旧 attempt 的 intent 不覆盖新 intent。
> - **Tx1（短事务）**：原子推进——checkpoint `state: pending/blocked -> erasing`（条件 CAS，**单一 adapter 窗口准入点**）+ `attempt += 1` + 持久化 `external_delete_intent.v1` 至 `checkpoint_digest`；operation `lease_epoch` **验证**（与当前 operation 精确匹配，推进由 S5）；external ledger 确认 `registered`（窗口内保持）；**提交释放全部数据库锁**。
> - **adapter 调用（无锁）**：释放锁后调用外部 adapter 删除 object；携带**跨 takeover 稳定的 idempotency key**（E-2b）与 adapter version。**禁持锁做外部 I/O**——S4-E 不实现 claim lease/调度，双事务窗口的并发正确性由**共享 fence 跨 operation 串行化**（每 conversation+owner 一行，只有持 `erasing` 的 operation 可进 adapter 窗口）+ **同 operation 内 Tx1 checkpoint CAS 防重放** + **E-2a 精确重验** + **idempotency key 抑制副作用**承载（见 E-2b/E-6）。
> - **Tx2（第二独立事务）**：**精确重验**（E-2a）后写 `erased` + `receipt_digest` **再清对应 DB ref**（RunEvent 经 migration 041 / outbox 由 external participant 清 ref 与 inline 并转 suppressed）。
> - **锁序（冻结，对齐 D8）**：Tx1/Tx2 取锁顺序与既有链一致（Guard/Conversation -> owner lock -> fence -> 集合锁 -> 源行，D8 全局链）；Tx2 清 RunEvent 经 **041 行级白名单 guard**（沿 039 行级函数扩展，**非 DDL**，不引入 ACCESS EXECLUSIVE 升级——参考 execution round-1 P1-2 DROP TRIGGER 死锁教训）；`source_table+source_row_id` 多态无 FK，E-1a 的「source 已 NULL/缺失」路径即多态空行场景，Tx2 清 ref 时集合锁仍可获但行级锁可能落空，须按 D8 矩阵显式入链。
>
> **E-2a Tx2 精确重验（非「fence 仍 active」）**：Tx2 重验改为——**operation `lease_epoch` 精确匹配**（同 purge_revision）+ **checkpoint `state='erasing'` + `attempt` 匹配 + `checkpoint_digest` 匹配（== Tx1 持久化的 intent digest，跨 takeover 不变）** + **fence（`state='erasing'` 且 `purge_revision` == operation.purge_revision，即同一 purge 实例）** + **registry digest** 匹配 + **hold revision** 匹配；且 **external ledger 仍为 `registered` 且 `receipt_digest IS NULL`**（adapter 调用窗口内不变——`registered` 是窗口不变量，但**并发身份由 lease_epoch + checkpoint state/attempt/intent digest 承载**，非 ledger 状态）。任一不符 fail closed（stale lease / 旧 attempt 拒绝）。不得写「fence 仍 active」。
>
> **E-2b adapter idempotency key 与 receipt digest（冻结，跨 takeover 稳定）**：idempotency key = canonical digest（`ref_scheme` + `ref_value` + `adapter_key`/`adapter_version` 派生，**不含 lease_epoch/attempt**——takeover 后 key 不变，防「新 lease 用旧 key 误去重」）；**adapter 支持幂等重放或 `receipt lookup` 是 B1 adapter contract 的硬性前置**（不满足则 S4-E-B1/B2 不得开工，E-6 反例验证）。**`receipt_digest` 直接承载 canonical adapter receipt evidence**：`receipt_digest = snapshot_digest({schema_version:1, kind:'external_erase_receipt', adapter_key, adapter_version, idempotency_key, adapter_receipt_evidence, ref_digest, erase_outcome})`（复用 `snapshots.py:149` 同一 helper 与版本化键名约定，64-hex 满足 `ck_*_receipt_digest`；**不新增 `adapter_receipt_digest` 列**）。**禁止仅凭本地 outcome 自造 receipt**——`receipt_digest` 必须由 adapter 返回的可验证 `adapter_receipt_evidence` 重算（E-6 反例：伪造本地 outcome 无 adapter evidence 不得 `erased`）。**重放比对（冻结）**：崩溃后重放经 adapter `receipt lookup`（同 stable idempotency key）取回 evidence，或按同 key 重算 snapshot digest，与已持久化 `receipt_digest` **精确匹配**——匹配则 no-op 终态，不匹配 fail closed。**分工（冻结）**：`checkpoint.attempt` 匹配**识别旧 Tx2**（防写错证据），idempotency key **抑制副作用**（防重复删）——attempt 是每 participant invocation 一次，不是去重机制本身。**崩溃后可能重复调用 adapter**——承认重复调用存在，但**不得重复产生副作用**（幂等删除，fake adapter 调用计数断言 == 1）；`unknown outcome` 默认**不自动重试**（见 E-3a）。
>
> - 崩溃恢复（冻结）：Tx1 提交后崩溃 -> checkpoint `erasing`/attempt/intent digest 已持久化；**重放 = 同 invocation 重做**（attempt 不变，adapter 幂等去重）——区别于**重试**（`blocked/unknown -> registered` 后重新发起，E-3a/E-3b）。重放精确重验（E-2a）后重做 adapter/Tx2 或回退；idempotency key 防副作用。
>
> **E-3 根因 4：external ledger 状态机合法迁移 + timeout/unknown 矩阵**
>
> - 状态（**复用现有枚举，不新增 `erasing`**）：`pending -> registered -> erased | blocked | unknown`。`pending`/`registered` 由 **staging/reference lifecycle port（B1）** 产生；`registered` = 已登记待删（adapter 调用窗口期间保持 `registered`）。
> - 合法迁移：`pending->registered`（B1 登记）；`registered->erased`（Tx2 成功 + receipt）；`registered->blocked`（timeout 且**可证明未发送** / digest mismatch / adapter unavailable，记 `blocked_reason`）；`registered->unknown`（请求**可能已生效**但 outcome 未知）；`blocked/unknown_scheme -> registered`（仅当 **scheme 明确识别 + adapter capability 验证通过**，B1 判定；其余 blocked/unknown 见 E-3b）。禁 `erased` 回退。
> - **E-3a timeout/unknown 状态矩阵（请求是否可能已生效决定 blocked vs unknown；可能已生效统一 `unknown`，可证明未发送才 `blocked/erase_timeout`）**：
>
> | adapter 结果 | 请求是否可能已生效 | 状态 | 是否自动重试 |
> |--------------|-------------------|------|-------------|
> | 明确失败（非幂等错误，**可证明未产生副作用**） | 否 | `blocked`（`adapter_unavailable`） | 可重试（重试 `registered`，须满足 B1 capability 判定） |
> | 超时（请求可能已发出，**无法证明未发送**） | 是 | **`unknown`/`outcome_unknown`**（统一进入，不排除已生效） | **不自动重试**；仅 adapter 支持幂等重放/`receipt lookup` 时允许（E-2b key 去重），否则运维/人工确认（E-3b 查询入口） |
> | 超时（**可证明未发送**，连接前失败） | 否 | `blocked`（`erase_timeout`） | 可重试 |
> | outcome 未知（adapter 返回 unknown） | 是 | `unknown` | **不自动重试**；仅 adapter 支持幂等重放或 `receipt lookup` 时才允许，否则运维/人工确认 |
> | 成功 + 可验证 adapter evidence | — | `erased`（receipt_digest 由 adapter evidence 重算，E-2b） | 终态 |
> | digest mismatch | — | `blocked`（`digest_mismatch`）不得 ACK | 不自动重试 |
>
> - **「可证明未发送」判据（冻结）**：adapter 在**建立连接/发出请求前**失败（连接错误、前置校验失败）即为可证明未发送；无法区分是否已发出的一律视为**可能已生效** -> `unknown`。fake/conformance adapter 须支持注入两类失败（发送前连接错误 / 发送后 TimeoutError）以分别验证两行（E-6）。
> - **E-3b blocked/unknown 处理（运维可观察性，冻结）**：S4-E-B2 实现 **blocked/unknown 行查询**（`agent_external_object_refs` 按 `erase_state` + `blocked_reason` 过滤）与**有证据 reconcile service**（仅当 adapter `receipt lookup` 返回可验证 evidence 时补写 `erased` + receipt；**禁止无 receipt 强制 `erased`**）。HTTP/CLI 接线与操作入口归 **S5**，本 Slice 只提供查询/reconcile 能力与测试。**收场（冻结）**：Tx2 fail closed 但 adapter 副作用已发生（registry/hold 变化等）时——若 `receipt lookup` 可得 evidence -> reconcile 补写 `erased`；否则转 `unknown` 交运维人工确认（E-3a）。
> - 崩溃恢复：并发重放：checkpoint `erasing`+attempt 承载防双删；重复删除 -> 已 `erased` + `receipt_digest` 匹配 no-op。`blocked`/`unknown` **不得 ACK**（不变量 5）。
>
> **E-4 根因 5：registry 激活条件（确定选择——external/runtime 均保持 False）**
>
> - **确定性选择（根因 7 修正）**：当前仓库**没有具体生产级 db_local adapter**（B5 db_local allowlist 为空、无可证明 DB-local 格式、无 adapter 实现）——因此 `external.payload.v1` / `runtime.private.v1` **`erase_available` 均保持 `False`**。**registry owner 定义固定不可删**（spec §4.1 V1 owner registry），本 Slice 只是**不把「registry 激活」列为验收项**（不含任何 registry 定义/断言改动）。
> - **fake adapter / conformance fake 不构成激活依据**（spec §10.2「fake 只证明契约，不得宣称生产对象已删除」）。`RuntimeErasureParticipant` 是 conformance fake，`runtime.private.v1` 全程 False；真实 Runtime eraser 归 REQ-043。
> - 若未来引入**具体生产级 db_local 格式与 adapter**（可证明格式 + 真实删除 + receipt），`external.payload.v1` 才允许**同 commit 激活**（S3-D P1-7：断言测试同 commit 更新 + mutation kill 缺 adapter 变红）——届时作为独立任务入账，不并入本 Slice。
>
> **E-5 根因 6：四串行风险域拆分（TD-092 单风险域）**
>
> 1. **S4-E-A：ref tombstone + transport 清除边界**——migration 041 guard 演进（清 RunEvent.payload_ref 严格 tombstone，行级白名单，非 DDL）+ **E-0 修复**（transport 只清 inline-only 行；ref-bearing 行零修改 blocked）+ **已合并测试迁移**（inline 用例保持；ref-only 用例改 blocked 零修改）。验证 041 roundtrip + 变异（清 ref 复活 inline 击杀）+ E-0 反例。
> 2. **S4-E-B1：lifecycle registration + adapter contract**——staging/reference lifecycle port（`registered` 唯一正常生产者；`blocked/unknown_scheme -> registered` 仅 scheme 明确识别 + adapter capability 验证通过）+ **adapter contract**（幂等重放/`receipt lookup` 硬前置 + 失败分类注入：发送前连接错误 / 发送后 TimeoutError）。
> 3. **S4-E-B2：external erasure participant**——`ExternalPayloadErasureParticipant`（消费 `registered` 行 + scan 3 source + E-1b 唯一 ref 清除者 + ledger 状态机 E-3 + 双事务协议 E-2 + 清除顺序 D5 + source-NULL 历史兼容 E-1a + blocked/unknown 查询与有证据 reconcile E-3b）。**registry 不激活**（E-4）。验证 E-1/E-2/E-3 反例 + mutation kill（「缺 adapter/缺 participant」变红指调用被 capability gate 拒绝或扫描逻辑报错，而 registry 断言仍 False）+ **B2 互操作矩阵**（「receipt 后清 ref + 转 suppressed」「transport 已 suppressed 行再扫 no-op」）。
>
> **E-5-2 B1/B2 锁序与互操作顺序冻结（三面首轮 P1 前瞻，S4-E-A 后开工前置）**：outbox `payload_ref` 行的**唯一写者是 B1（`registered` 生产者）/B2（ref 清除者）**——二者写入/清除必须按 D8 全局锁序与 transport/backfill 同序：**Guard -> Conversation 行锁 -> owner advisory lock -> fence -> 集合锁 -> 源行**；**禁止** B1/B2 不经 Conversation 行锁直接 INSERT/UPDATE outbox ref 行（否则 S4-E-A 的 `count_ref_bearing_outbox_rows` 裸 SELECT 与 transport erase 之间的 TOCTOU 窗口在 B2 落地后成为真实竞态——后果 fail-closed 但 reason 误导运维）。**mixed 互操作顺序冻结（三面首轮 D-5/T-7）**：同一 Conversation 混合 inline-only + ref-bearing 行时——**transport 整次零修改 blocked**（`purge_owner_unavailable`，inline-only 行也不得提前清）-> **B2 只清 ref-bearing 行并转 `suppressed`**（清 ref + inline 一并，满足现 outbox CHECK；**禁止 B2 同时清 inline-only 行**——inline-only 行归 transport 清除）-> **transport replay 清 inline-only 行并 ACK**（count=0 后重试）。**final-scan reason 分野冻结（三面首轮 D-6/C-1）**：正常前置命中（ref-bearing count>0）用 `purge_owner_unavailable`；**只有竞态/历史异常绕过前置**（count=0 后并发写 ref，final scan 非零）才落 `purge_blocked_by_transport_scan_nonzero`——B2 互操作矩阵须显式覆盖这两种 reason 的可诊断区分。
> 4. **S4-E-C：runtime conformance fake**——`RuntimeErasureParticipant` conformance suite（session destroy + 旧 epoch event + 迟到 seq + unknown outcome + ACK 重放，spec §10.3）；`runtime.private.v1` 保持 False。验证 conformance 各反例 + fake 不冒充真实 spool。
>
> **E-6 根因 7：验收反例矩阵（S4-E 实现时逐项，含判别点/注入机制）**
>
> | 反例 | 触发 | 期望行为（fail closed） | 判别点 / 注入 |
> |------|------|------------------------|--------------|
> | transport-before-external | S4-D transport 提前清 outbox payload_ref | E-0 修复后 transport 只清 inline-only 行；ref-bearing 行**零修改 blocked**（`purge_owner_unavailable`），external receipt 前不清 ref | 断言 ref-only 行 transport 后 `payload_ref` 仍存在、status 不变；变异：transport 仍清 ref（旧行为）/ 转 suppressed 保留 ref（违反现 CHECK）-> 红 |
> | receipt 写入前崩溃 | Tx1 提交后、Tx2 receipt 前崩溃 | ledger 保持 `registered` + checkpoint `erasing`/attempt/intent；重放（同 invocation）精确重验（E-2a）后重做 adapter/Tx2；不伪造 receipt | **崩溃注入机制（冻结）**：test 可控 adapter 回调抛异常 + 事务分离回滚（S4-C 先例，模拟 Tx2 前崩溃）；断言 ledger 仍 registered + checkpoint erasing + receipt_digest NULL |
> | adapter 成功但 Tx2 崩溃 | adapter 删 object 后、Tx2 写 receipt 前崩溃 | 重放精确重验（E-2a）后写 receipt 清 ref；不重复删 | fake adapter **调用计数 == 1**（幂等 key + checkpoint attempt 去重） |
> | stale lease Tx2 | Tx2 时 operation lease_epoch 已被接管/过期 | Tx2 精确重验（E-2a：lease_epoch + checkpoint erasing/attempt/intent + fence/registry/hold）不符 -> fail closed；不写 receipt | **测试手动推进 operation `lease_epoch` 模拟 takeover**（S4-E 不实现 scheduler claim，只测验证侧） |
> | **lease takeover 后 idempotency key 不变** | purge 被接管（新 lease_epoch），adapter 重调用 | idempotency key 不含 lease_epoch/attempt（E-2b），跨 takeover 稳定——新 lease 用同 key 去重，不重复删 | 固定 ref_scheme+ref_value+adapter_key 输入下 key 值相等断言；fake adapter 计数仍 == 1 |
> | **旧 attempt Tx2 被拒** | Tx1 attempt=N 提交、takeover 后 attempt=N+1 推进，旧 Tx2 重放 | Tx2 精确重验 checkpoint attempt 匹配失败 -> fail closed（不覆盖新 intent）；intent digest 跨 takeover 不变 | 断言旧 Tx2 拒绝 + checkpoint_digest 仍为新 intent；变异：Tx2 不校验 attempt -> 红 |
> | **伪造本地 outcome 无 adapter evidence** | adapter 未返回可验证 evidence，仅凭本地「已调用」写 erased | receipt_digest 须由 adapter evidence 重算（E-2b）；缺 evidence -> 不得 `erased` | 测试按 E-2b 冻结字段集**重算 snapshot digest** 比对 receipt_digest；变异：写本地自造 receipt -> 重算不匹配红 |
> | **可能已生效 timeout -> unknown** | adapter 超时且无法证明未发送 | 统一进入 `unknown`/`outcome_unknown`（E-3a），不自动重试；仅幂等重放/receipt lookup 时允许 | fake adapter 注入**发送后 TimeoutError** -> 断言 unknown + blocked_reason 为 outcome_unknown；变异：一律 blocked 自动重试 -> 红 |
> | **可证明未发送 timeout -> blocked** | adapter 连接前失败（请求未发出） | `blocked`（`erase_timeout`）可重试 | fake adapter 注入**连接前错误** -> 断言 blocked + erase_timeout；与上行区分（E-3a「可证明未发送」判据） |
> | source 已 NULL 的历史兼容 | source ref 被并发清但 ledger `registered` 未 erased | 仍凭已验证 ledger 完成删除留证（E-1a），写 `erased` + receipt；不伪造「source 仍存在」 | 种子：B1 登记 registered 行 + 将 source ref 置 NULL；断言 adapter 仍被调用 + erased |
> | 不同 ref 冲突 | source ref 存在但 != ledger `ref_value`，或绑定冲突 | fail closed（不覆盖、不伪造 receipt） | 与 source-NULL 反例的**判别边界**：source 有非 NULL ref 且不同 -> 拒绝；source 无 ref -> 继续（E-1a） |
> | 重复删除 | 同一 object 两 purge 并发 | **同 Conversation 并发 purge**：共享 fence（每 conversation+owner 一行）串行化——只有持 `erasing` 的 operation 可进 adapter 窗口，另一 operation 因 fence `erasing` 无法推进 fail closed（E-2a 精确重验）；**跨 Conversation 同一 object**（ref_value 出现在不同 conversation）：无共享 DB 锁，靠 **idempotency key + adapter 幂等去重**防双删；已 `erased` + receipt_digest 匹配 no-op | fake adapter **调用计数 == 1**；双 purge 并发（两事务）断言只一次 adapter 调用；变异：绕过 fence/checkpoint 双推进或同 object 跨 conversation 双调 -> 红 |
> | 错误 receipt digest | adapter 返回 evidence 与 E-2b 冻结 envelope 重算不符 | `blocked`（`digest_mismatch`）不得 ACK；不自动重试 | 断言 blocked_reason == digest_mismatch；adapter 返回被篡改 evidence |
> | 未知 scheme | ref_scheme 不在 allowlist | blocked（`unknown_scheme`）禁 ACK（B5） | B1 判定未通过则保持 blocked；不转 registered |
> | unknown outcome 禁自动重试 | adapter 返回 unknown（请求可能已生效） | `unknown` 状态，**不自动重试**（E-3a）；仅幂等重放/receipt lookup 时允许，否则运维/人工确认（E-3b 查询入口） | 断言无自动重试（后续 scheduler 不 claim）+ reconcile service 仅在 evidence 可验证时补 erased |
>
> **E-7 边界（明确不做）**：不实现 S4-F（fault 矩阵）、不启用 S5 scheduler、不实现 S6（365 天 audit prune）、不实现真实 Pi Worker/云对象存储生产 adapter（REQ-043/生产）、`runtime.private.v1` 不激活；不改 migration 040、不新增 outbox CHECK migration、不新增 inbox status 枚举；不实现 operation `lease_epoch` 推进/接管（归 S5）；不实现 blocked/unknown 的 HTTP/CLI 接线（归 S5）；不实现 scheduler claim/租约（S4-E 双事务窗口并发正确性由共享 fence 跨 operation 串行化 + 同 operation Tx1 checkpoint CAS 防重放 + E-2a 精确重验 + idempotency key 承载）。
>
> **S4-E merged-boundary 与合并记录（2026-08-09，实现契约 PR #546，squash merge `c243c36d`）**：三面首轮（数据/状态机 1/9/3/1、并发/锁序 2/6/4/1、测试/运维 3/5/5/0，P0=6/P1=20/P2=12/P3=2）按 8 根因族一次返修（`ba881ee4` 一次重写 E-0~E-7）+ plan 回填（`e968c9da`）+ 根因族定向复核（不重开三面，`1d9b98d6` 微调）-> 最终 P0/P1=0，7 项限定对 GitHub 实际 diff 只读核对全命中（inline-only/ref-bearing 两分支与现 CHECK 一致、`registered` 生产者属 B1 lifecycle port、operation lease 归 S5 participant 只验证、checkpoint attempt/digest 状态语义、receipt evidence 与 unknown 收敛、external/runtime registry 全程 False、B1/B2/C 边界与工作台一致）-> Ready 三路 required checks SUCCESS（Backend/Frontend/Engineering docs）-> mergeStateStatus CLEAN -> squash merge `c243c36d` + 分支清理 + docs closeout（工作台归档 + work-log 索引 + 本记录）。**merged-boundary 结论**：S4-E 完成 `external.payload.v1`/`runtime.private.v1` 契约冻结——E-0a 冻结 inline-only 清除 + ref-bearing 行 transport 零修改 blocked（不新增 outbox CHECK migration，消解 S4-D-A 已合并测试冲突，测试迁移：inline 用例保持、ref-only 用例改 blocked、receipt 后清 ref 断言移 B2 互操作矩阵）；`registered` 由 S4-E-B1 staging/reference lifecycle port 唯一产生、eraser 只消费；双事务协议（Tx1 checkpoint erasing+attempt+intent digest / 无锁 adapter / Tx2 精确重验）与 receipt evidence 证据链冻结；external/runtime registry 均保持 False（无生产 db_local adapter）。**S4-E 全线闭环**：契约冻结完成，`erase_available` 全程 False；遗留实现 S4-E-A（Ref Tombstone：041 + transport 清除边界，下一任务）、S4-E-B1/B2、S4-E-C、S4-F、S5 scheduler、S6、C1 总验收明确排除。
>
> **S4-E-A merged-boundary 与合并记录（2026-08-10，实现 PR #548，squash merge `0797e70c`，评分 91）**：三面首轮（数据/状态机 0/2/6/1、并发/锁序 0/0/2/3、测试/运维 0/0/4/6，P0=0/P1=2/P2=12/P3=10 归 6 根因族）按 12 条决策一次返修（`f6885ca5` + `93ac2794`）：① revision id 缩短为 `041_run_event_ref_tombstone`（27 字符 ≤ varchar(32)）删除 alembic 版本表 DDL（无不可逆残留）+ plan file/revision 映射（文件名保持冻结名 `041_run_event_external_ref_tombstone.py`，与 revision id 解耦）；② 分支 2 补 `TG_OP='UPDATE'` 防御子句；③ 新增 `test_guard_rejects_tombstone_on_old_row_without_ref`（archived+ref NULL 拒绝，击杀 `OLD.payload_ref IS NOT NULL` 退化）；④ visibility 变异改 `'internal'`；⑤ ref-only 补 `operation.failure_code`、mixed 补 `checkpoint.state`；⑥ mutation 测试复合击杀归因；⑦ plan E-5-2 冻结 B1/B2 锁序 + mixed 互操作顺序 + final-scan reason 分野。定向复核 6 根因族全消解 -> P0/P1=0 -> 评分 91（`e315f71c`）-> Ready Backend full 三路 CI 全绿（Backend 11m7s/Frontend/Engineering docs）-> mergeStateStatus CLEAN -> squash merge `0797e70c` + 分支清理 + docs closeout（工作台归档 + work-log 索引 + 本记录）。**merged-boundary 结论**：S4-E-A 完成 migration 041（guard 分支 2 严格 ref tombstone，downgrade 还原 039）+ transport E-0a 修复（inline-only 清除 + ref-bearing 零修改 blocked `purge_owner_unavailable`，fence 保持 active）——D5「先删 external object 取 receipt 再清 transport DB ref」的 transport 侧顺序违规已消除，ref 归 external.payload.v1（S4-E-B2）清除。**S4-E-A 全线闭环**：`external.payload.v1`/`runtime.private.v1` registry 保持 False；遗留实现 S4-E-B1（Lifecycle Registration + Adapter Contract，下一任务）、S4-E-B2（External Erasure Participant）、S4-E-C（Runtime Conformance Fake）、S4-F、S5 scheduler、S6、C1 总验收明确排除。
>
> **S4-E-B1 merged-boundary 与合并记录（2026-08-10，实现 PR #550，squash merge `683d8c06`，评分 90）**：三面首轮（数据/状态机 P0=1/P1=3/P2=4/P3=2 + 并发/锁序 P0=0/P1=2，P2/P3 未单独留档）归 3 根因族一次返修（`1141caad`）：① **集合锁 owner 与 backfill 同源**（P0-1/P1-1，E-5-2/D8）——register/promote 对 outbox 源行此前恒用 `external.payload.v1` 取集合锁，与 backfill `_backfill_source_row`（transport owner）同源行两把不同 advisory key，同源行 ledger 写不互斥；新增 `_EXTERNAL_REF_COLLECTION_OWNER_BY_SOURCE` + `_collection_owner(source_table)`（run_events→external、两 outbox→transport owner），与 backfill `OWNER_BY_TABLE` 逐表一致；② **promote 锁内诚实返回域**（P1-2）——gate 失败不再无条件早退返回 `'blocked'`（并发下可能谎报——行已被并发推进为 registered/erased）；改为先取集合锁锁内读实际当前态，scheme 未识别 / adapter 前置不满足时返回行真实态，成功推进才返回 `'registered'`；③ **测试判别力**（P2-1/P2-2）——补 `test_collection_owner_matches_backfill_for_all_ref_sources`（锁 owner 与 backfill 逐表一致 + advisory key 相等断言）+ 真实 PG 双连接并发测试（`test_concurrent_promote_serializes_to_single_registered`/`test_concurrent_register_is_unique`）。定向复核 3 根因族全消解。独立测试/运维面首轮（P0=0/P1=3/P2=4/P3=1，HEAD `b45f9e32`）统一返修（`c5d51865` + `06c048dc`）：P1-1「326/1 顺序污染」不可复现移除更正、P1-3 backfill 计数 54→44、P1-2/P2-2 补 erased 不覆盖 + 并发 erased 判别、P2-3 补 gate 诚实返回判别。定向复核 P0/P1=0 -> 评分 90（Original）-> Ready Backend full 三路 CI 全绿（Backend 11m35s/Frontend/Engineering docs）-> mergeStateStatus CLEAN -> squash merge `683d8c06` + 分支清理 + docs closeout（工作台归档 + work-log 索引 + 本记录）。**merged-boundary 结论**：S4-E-B1 完成 `external.payload.v1` 的 lifecycle registration port + adapter contract——`register_external_object_ref`（`registered` 唯一正常生产者，B5 scheme 未识别 fail closed）+ `promote_external_ref_to_registered`（`blocked/unknown_scheme -> registered` 唯一受控入口，仅 scheme 明确识别 + E-2b capability 验证通过时放行）+ adapter contract（E-2b 硬前置 + E-3a 失败分类矩阵 + 跨 takeover 稳定 idempotency key + receipt digest 由 adapter evidence 重算）。**E-1/E-2b/E-3a/E-5-2/E-6 契约落地**：`registered` 唯一正常生产者已就位（backfill 只写 `blocked/unknown_scheme`，B1 是升级到 `registered` 的唯一受控入口）；集合锁 owner 与 backfill 同源（同源行 ledger 写与 backfill 互斥，D8 锁序保持 Guard -> Conversation 行锁 -> owner advisory lock -> fence -> 集合锁 -> 源行）；adapter 失败分类矩阵与 idempotency key/receipt digest 契约冻结在代码（B2 消费）。**S4-E-B1 全线闭环**：`external.payload.v1`/`runtime.private.v1` registry 保持 False（E-4，无生产 db_local adapter，B5 allowlist 冻结为空）；不改 migration 040/041；遗留实现 S4-E-B2（External Erasure Participant：消费 `registered` 行 + scan 3 source + E-1b 唯一 ref 清除者 + ledger 状态机 E-3 + 双事务协议 E-2 + blocked/unknown 查询与有证据 reconcile E-3b，下一任务）、S4-E-C（Runtime Conformance Fake）、S4-F、S5 scheduler、S6、C1 总验收明确排除。
>
> **S4-E-B2 merged-boundary 与合并记录（2026-08-11，实现 PR #552，squash merge `a6aee2e7`，评分 91）**：三面首轮（数据/状态机 P0=0/P1=3/P2=4/P3=6 + 并发/锁序 P0=2/P1=3/P2=4/P3=1 + 测试/运维 P0=0/P1=4/P2=3/P3=3，**首轮原始合计 P0=2/P1=10/P2=11/P3=10 保留不覆盖**）-> 两项 P0 降级（C-1 AB-BA 理论面：Tx1/Tx2 均严格「集合锁在源行 UPDATE 之前」+ backfill/reconcile 从不取 conversation 行锁，未实例化；C-2 重放 revision CAS：`_mark_operation_running` 对已 RUNNING 不 bump revision，重放以当前 revision CAS 可续做，无数据损坏）-> **P0=0/P1=12** 按 5 根因族一次返修（`1728bd7f`）：① 并发/重放证据缺失（补崩溃重放正向 + 双 B2 并发串行化）；② checkpoint_digest 双形式统一（erased-fence 重放用 `final_scan.digest()` ExternalRefScan 形式）+ digest_mismatch 冻结 vacuous；③ reconcile 收场闭环（补清源 ref + 取集合锁 D8）；④ 验证口径 349->353 + reason 分派 + rowcount 校验 + gate revision CAS；⑤ execution outbox 源覆盖 + 空 evidence 拒。定向复核 **P0/P1=0** -> 判别力增强批次（仅测试 `54fb1d50`：DR-1 并发总调用==1 / DR-2 崩溃留证 / DR-3 Tx2 fence 真实分支 / DR-4 记录 P3）-> 评分 91（Original，`8af21ad8` -> 纠偏 `41be58e2` 净 diff 仅 +1 行）-> Ready Backend full 三路 CI 全绿（Backend 11m16s/Frontend/Engineering docs）-> mergeStateStatus CLEAN -> squash merge `a6aee2e7` + 分支清理 + docs closeout（工作台归档 + work-log 索引 + 本记录）。**merged-boundary 结论**：S4-E-B2 完成 `external.payload.v1` 的 external erasure participant——**3 个 source 的 DB ref 唯一清除者**（RunEvent 经 041 guard 转 redacted / 两 outbox 转 suppressed，E-1b）；双事务协议（Tx1 checkpoint erasing+attempt+intent / 无锁 adapter / Tx2 E-2a 精确重验 + 写 erased+receipt 再清源 ref + ACK）；E-1a source 已 NULL 历史兼容；E-3a 失败矩阵 5 行；E-3b blocked/unknown 查询 + 有证据 reconcile（补清源 ref 闭环）。**E-1/E-1a/E-1b/E-2/E-2a/E-2b/E-2c/E-3/E-3a/E-3b/E-5-2 契约落地**：D5「先删 external object 取 receipt 再清 transport DB ref」在 B2 侧闭环（receipt 后清源 ref）；B2 是唯一清除者（transport 前置 blocked `purge_owner_unavailable` 归 E-0a 已落地）。**S4-E-B2 全线闭环**：`external.payload.v1`/`runtime.private.v1` registry 保持 False（E-4）；不改 migration 040/041；遗留实现 S4-E-C（Runtime Conformance Fake，下一任务）、S4-F、S5 scheduler、S6、C1 总验收明确排除。
>
> **S4-E-C merged-boundary 与合并记录（2026-08-12，实现 PR #557，squash merge `c31df023`，评分 92）**：三面首轮（数据/状态机 P0=0/P1=1/P2=4/P3=5 + 并发/锁序 P0=0/P1=1/P2=3/P3=3 + 测试/运维 P0=0/P1=1/P2=2/P3=8，**首轮原始合计 P0=0/P1=3/P2=9/P3=16/P4=4 保留不覆盖**）-> **P0=0/P1=3/P2=9** 按 5 根因族一次返修（`cbdad3a9`）：① 族A retry 窗口含 blocked/unknown 重删 + Tx1 双 purge 未串行化——`_load_active_bindings` 排除 `status IN ('closed','invalid')`（B2 registered-only 窗口镜像，invalid=blocked/unknown 不自动重试 destroy，只经 E-3b reconcile）+ Tx1 fence ERASING 分支 same-purge-instance 门禁（`fence.purge_revision == purge_revision`，E-6「重复删除」串行化）+ erased-fence 重放 purge_revision 一致性门禁；② 族B Tx2 精确重验 fail-closed 分支整体缺测 + ORM identity map 掩盖并发 takeover——生产补 `self._session.expire_all()` 使 Tx2 重验观察已提交态，补真实双连接 race 测试命中五重 fail-closed（fence 非 erasing / purge_revision 不匹配 / checkpoint attempt 不匹配 / intent digest 不匹配 / operation lease_epoch 接管 / second-purge-instance）；③ 族C 并发判别力缺失——补双连接并发 erase 串行化 + 共享 key→evidence adapter 断言总 distinct destroy==1（E-2b「不得重复产生副作用」）；④ 族D 证据链 + 状态卫生——`receipt_digests` 折入 `RuntimeErasureSummary.ack_digest()`（证据链）、关 binding 清流租约（`active_stream_id`/`stream_lease_expires_at` 同 NULL 满足 CHECK）、缺失 binding 行 fail closed；⑤ 族E P3 清理（idempotency key 签名断言、spool 无清除路径判别、reason 归并 3 例、TD-032、E-5 引用）。定向复核 **P0/P1/P2=0** -> 评分 92（Original，基线 `3ee9d537`，净 diff 仅 Score Log 1 行）-> Ready Backend full 三路 CI 全绿（Backend 11m46s 2346 passed/Frontend/Engineering docs）-> mergeStateStatus CLEAN/MERGEABLE -> squash merge `c31df023` + 分支清理 + docs closeout（工作台归档 + work-log 索引 + 本记录）。**merged-boundary 结论**：S4-E-C 完成 `runtime.private.v1` 的 RuntimeErasureParticipant conformance fake——**只证明协议一致性、不得宣称真实 Pi Worker/spool 已删除**（spec §10.2，D7）；session destroy 双事务协议（E-2 镜像：Tx1 checkpoint erasing+attempt+intent / 无锁 adapter / Tx2 E-2a 精确重验含 `expire_all` 观察已提交态 + 清 binding ref 关 binding + ACK）；binding 状态表达（无独立 ledger：ref 非空即残留 fail-closed、`invalid`=blocked/unknown 不进窗口、`closed`=erased）；E-3a 失败矩阵 + E-3b 查询/有证据 reconcile；E-2a same-purge-instance 门禁 + receipt_digests 证据链。**spec §10.3 五项 conformance 契约落地**（session destroy + 旧 epoch event + 迟到 seq + unknown outcome + ACK 重放，写路径 4 例回归证据）：Runtime binding 的 epoch/seq late-write 在 purge 窗口 fail closed 不重建正文。**S4-E-C 全线闭环**：`external.payload.v1`/`runtime.private.v1` registry 保持 False（E-4）；不改 migration 040/041；遗留实现 S4-F（fault 矩阵，下一任务）、S5 scheduler、S6、C1 总验收明确排除。


按 S4-A D1-D8 / S4-B B1-B8 / S4-C C1-C9 冻结 `workspace.transport.v1` / `execution.transport.v1` participant。**本 delta 只写文档：不写业务代码、不改 migration 040、不实现 migration 041、`erase_available` 全程保持 `False`、不启用 purge scheduler（S5）、不进 S4-E/F。** 现状盘点基于 main `5ff4b620`（S4-C PR-A/PR-B 已合并，四跳一致声明成立）。

**D 边界与 PR 拆分（TD-092 单风险域约束）**：transport participant 拆两个串行 PR，**不并行修改共享 ledger/registry**：

1. **S4-D-A：Transport Participant Core**——两个 participant（`WorkspaceTransportErasureParticipant`/`ExecutionTransportErasureParticipant`）、outbox/inbox tombstone、final scan、ACK/重放、锁序与集合锁。**registry 两个 transport owner 保持 `erase_available=False`**（ledger resolve 与 purge gate 尚未闭环，不得对外声明完整 erase 能力）；**不导入 backfill 私有函数、不实现 ledger resolve**。
2. **S4-D-B：Ledger Resolve + Activation**——提取共享 ledger API（backfill/consumer/participant 同一投影实现）；`epoch_unresolvable` evidence/CAS resolve；两类 gate 查询；participant 接入 resolve；**merged-boundary 联合验收通过后 registry 统一翻 True**（缺 participant/缺 resolve 做 mutation kill 实证）。

**D-A-1. transport participant 主体（S4-D-A）**

- 两个 participant 分别持有 `workspace.transport.v1` / `execution.transport.v1`，镜像 S2-D/S3-D 模式（scan + erase + ACK + 锁序）。**锁序固定**：`Guard -> Conversation 行锁 -> owner advisory lock（transport owner）-> fence 重验 -> transport aggregate 集合 advisory lock（最内层）-> 源 transport 行 FOR UPDATE 投影写`；集合锁复用 `acquire_transport_aggregate_lock`（`agent_erasure_locks.py`，key 独立前缀 `metaedu.agent.transport.agg.v1\x00`）；**禁止**在 Guard/Conversation/owner/fence 之前取集合锁（C4 锁序矩阵 / D8 锁链矩阵，防 AB-BA）。**集合锁免取条件（族 5 冻结）**：纯 outbox/inbox metadata 写 + transport scan **不写 ledger/投影**时可免取（S4-D-A：只清 outbox/inbox 行，不 resolve、不写 reconcile issue、不重算行内投影）；**一旦写 reconcile issue 或投影（S4-D-B 接入 resolve），必须按全局锁序取集合锁**。源 transport 行 UPDATE 隐式取得行锁（不额外 SELECT ... FOR UPDATE）。
- **outbox scan 与清除（正文事实谓词，round-1 冻结）**：final scan 以**正文事实**为核心——`payload_inline IS NOT NULL OR payload_ref IS NOT NULL` 命中的行即待清除，**不依赖状态白名单**（`pending/claimed/published/dead_letter/cancelled` 一律命中，`suppressed` 已清正文自然不命中）。命中后统一清 `payload_inline`/`payload_ref` 并转 `status='suppressed'`（既有 `ck_*_outbox_status` 枚举，不新增），保留 `payload_digest`。**`cancelled` 行（S4-C 双事务协议 Tx2 / S3-E 终态化产物）保留 S4-C 终态证据**：execution 侧 `decision_*` 四元（`ck_agent_exec_outbox_decision`）、workspace 侧 `last_error_code`（具名 code）**均不得清除或重写**——转 suppressed 只清正文列，终态证据随行保留（与「digest 留证」一致）。**Run 投影（族 1 修订 + 终态互操作）**：execution 侧 final scan **同时检查**关联 Run 的 `output_publish_state`——`pending`/`dead_letter` 计入残留必须 blocked，`not_required`/`published`/`suppressed` 为终态 pass（`not_required` 是 failed/cancelled/expired Run 的合法终态，S3-D 不改写成 suppressed）；participant **只读判定并报告**（**不清理 execution.core 字段**——Run 正文清除归 S3-D execution.core.v1 `_clear_terminal_outputs`，S4-D-A 不碰 `terminal_output_ref` 等正文字段）。
- **inbox receipt tombstone（B6，状态矩阵 round-1 冻结）**：清 receipt 时置 `receipt_tombstone_state='redacted'` + `receipt_tombstone_digest=<64-hex>`（marker 与 digest 同生同灭，`ck_*_receipt_tombstone`；digest 复用 S4-C Tx1 已提交的 `snapshot_digest` 同一 helper 与版本化 envelope 键名，**不得自造 digest 输入**；**reason 键值冻结为 `purge_erasure`（族 5 修订，共享常量 `RECEIPT_TOMBSTONE_REASON`，participant 不得自造字符串）**）。`status` 迁移矩阵（不新增枚举，`processing/consumed/rejected` 既有集合）：
  - `processing`（未决 receipt）→ **`rejected` + tombstone**（与 S4-C Tx1 消费侧 `rejected`+tombstone 对齐）；
  - 已 `consumed`/`rejected` → 保留原 `status` 与既有 outcome，仅补幂等 tombstone（marker + digest）；
  - 已 tombstone 且 digest **精确匹配** → no-op（幂等重放）；已 tombstone 但 digest **不匹配** → fail closed（`*IntegrationConflictError`）。
  - 禁空串/`{}`/伪值。
- **final transport scan（正文事实谓词续）**：workspace 侧扫 outbox（`payload_inline IS NOT NULL OR payload_ref IS NOT NULL`，**不排除 `cancelled`**）+ inbox（`receipt_tombstone_state IS NULL` 且 `status='processing'` 未决 receipt）；execution 侧同表结构扫描 + Run `output_publish_state` 未终态（`pending`/`dead_letter`；`not_required`/`published`/`suppressed` 为终态，`ck_agent_run_output_publish_state`）。scan 为零才 ACK。已 `suppressed` 的 outbox 行、已 `consumed`/`rejected`+tombstone 的 inbox 行不进入扫描。
- **ACK/重放（Spec §4.2「没有查到正文不是隐式 ACK」）**：镜像 S2-D `erase_conversation_body` 全套 fencing 要素——`purge_operation_id` + `expected_operation_revision` 必填、fence 缺失时 owner lock 下建立、registry digest drift -> `OwnerRegistryChangedError` fail closed、lease_epoch/hold_revision_snapshot/owner_version/capability_digest CAS、`_record_blocked` 的 `expected_revision` 透传、ACK digest 契约；`active->erasing`（重试 `blocked->erasing`；crash 恢复 `erasing` 继续）、`erasing->erased` + owner checkpoint CAS->acked；**erased fence 幂等重放先于 purge 前置**（ACK 丢失恢复，修复 pending checkpoint）；**final scan 非零 -> `erasing->blocked` 正常返回**（不抛异常），blocked 记 scan digest、operation/checkpoint/Conversation 三方一致，重试 `blocked->erasing`；active legal hold -> blocked 正常返回。**不复活正文**：purge 前 fence 裁决拒正文写、六元 CAS 已保证消费侧旧 attempt 不得覆盖新 claim（C6 takeover/claim lease）。
- **不实现**：ledger resolve（S4-D-B）、external ref / runtime（S4-E）、fault 矩阵（S4-F）。

**D-B-1. ledger 共享层（S4-D-B）**

- 提取 `_register_issue`/`_recompute_projection`（当前 backfill 模块私有，`agent_transport_backfill.py:378/463`）为共享层（如 `agent_transport_ledger_service.py`；`agent_transport_ledger.py` 已被 migration 040 的 ORM 模块占用，**不得落该文件**），backfill、consumer（S4-C PR-B 已写 ledger）、participant（resolve）**同一投影实现**，杜绝两份投影漂移（B4 唯一事实源 + 同事务一致性）。
- 共享层保持：集合锁临界区内调用、owner 维度绑定（`_recompute_projection` P2-2）、`(id, revision)` 单 issue CAS、`ON CONFLICT DO NOTHING` 幂等。

**D-B-2. `epoch_unresolvable` resolve（S4-D-B，round-5 P1-2 + round-6 P1 冻结落地）**

- **resolve 边界（round-1 冻结）**：S4-D participant **只处理目标 Conversation 的 `conversation_scope` issue**（带 conversation_id，`ck_..._class_scope` 强制）——且该源行已取得 tombstone 证据。`tenant_scope` 与 `orphan` 类 issue **不 resolve、不改投影**，留给 S5 scheduler/运维闭环（tenant_scope 由 S5 fail closed；orphan 由运维确认到 resolved 才清零）；**participant 不得**对 `tenant_scope`/`orphan` 行置 resolved（否则绕过 B4 gate 谓词 `state <> 'resolved'`）。
- participant 完成对目标 Conversation 内未达 fence 的旧 epoch 事件 tombstone 后，以 **inbox `receipt_tombstone_digest`**（Tx1 已提交 64-hex）作为 `resolution_digest` 写入并置 `resolved` + `resolved_at`（`ck_..._resolution_evidence` 强制）；**不得**在未 tombstone 情况下置 resolved（B4）。
- resolve 流程：集合锁临界区内 → 读该源行完整 issue 集（ledger 唯一事实源）→ `(id, revision)` CAS `open/acknowledged -> resolved`（`revision+1` 不回退，0 行命中即并发冲突重读重试，B1(d) CAS 规则）→ 重算行内投影（**orphan 类 issue 存在 -> 'orphan' 最高优先级**；其次任一 unresolved -> `pending`；全 resolved -> `reconciled`——与 `_recompute_projection` 逐条对齐，冻结为共享层唯一实现）。
- **重放匹配（round-6/7 修正不变）**：ledger `resolved` 只证明 tombstone evidence 有效，**不代替** S4-C Tx2 已把 outbox 置精确终态——resolve 与 Tx2 是两个独立动作；重放仍须锁后检查 outbox 精确终态三分支（S4-C 状态表 Tx2 后重放行）。
- **历史 consumed 行出口（三面 P1 冻结）**：backfill（B3）为历史 `producer_purge_revision IS NULL` 的**已 `consumed`** inbox 行（无 receipt_tombstone 证据）登记 `conversation_scope/epoch_unresolvable`——participant 的 resolve 谓词只命中已 tombstone 行，这类行**无法由 participant resolve**（无证据不伪造，fail closed），gate 持续命中。**出口冻结**：历史 consumed 行的 resolve 由 S5 scheduler/运维路径处理（本 PR 只冻结 Tx1 新写场景的 resolve）；participant 不得为无证据行伪造 resolution_digest。

**D-B-3. 两类 gate（区分）**

- **conversation_scope gate**：`conversation_scope AND state <> 'resolved'` 命中即 blocked——S4-D-B 必须在 participant 内对目标 Conversation fail closed（防直接调用绕过 scheduler；purge 前置查与 S5 同一谓词）。
- **tenant_scope gate**：`tenant_scope AND state <> 'resolved'` 命中即该 tenant scheduler/canary enable fail closed——**只提供共享查询/API，由 S5 scheduler 消费**；**不**让单个 Conversation participant 因租户内无法归属的历史行全部阻塞。
- **orphan**：不阻塞 Conversation purge（对象已删），需运维确认到 resolved 才清零（B4，冻结保持）。

**D-Act-1. registry 翻 True 时序（S4-D-B 最终激活提交）**

- `workspace.transport.v1` / `execution.transport.v1` 的 `erase_available` 在 **S4-D-B 联合验收通过后**统一翻 True（`agent_erasure_registry.py`）；**registry 翻 True 与断言更新只属于 S4-D-B 最终激活提交**（S3-D P1-7 先例：registry 断言测试须与翻 True **同 commit** 更新，否则全量 CI 红被误判为回归）。`external.payload.v1`（S4-E）、`runtime.private.v1`（E/fake）保持 False。
- 翻 True 须带 mutation kill：缺 participant（回退 `erase_available=False`）与缺 resolve（回退为只登记不 resolve）对应测试变红。
- **S4-D-A 阶段隔离（round-1 冻结）**：S4-D-A registry 始终保持 False；**契约测试矩阵可提前冻结，但不得在 A 阶段声称 capability 已开放**（任何 A 阶段验收不得包含「transport owner erase 可用」断言，`require_capability(transport_owner, "erase")` 在 A 阶段 fail closed 是预期、不是缺陷）。

**D 验收矩阵（S4-D 实现时逐项验证；反例命名分开，避免「重放三分支」同名混淆）**：

1. **S4-D-A：participant ACK replay/fencing 矩阵**——两 participant 同锁序（Guard -> Conversation -> owner -> fence -> 集合锁）真实 PG 并发反例无 AB-BA；**outbox scan 正文事实谓词**（`payload_inline IS NOT NULL OR payload_ref IS NOT NULL`，**含 `cancelled` 行**——S4-C Tx2 终态化残留、S3-E terminalize 产物）统一清正文转 `suppressed` 留 `payload_digest`，**execution `decision_*` 四元 / workspace `last_error_code` 终态证据保留**（清除或重写即 fail）；**payload_ref only 行清除**（谓词退化只查 inline 的变异被击杀）；**inbox 状态矩阵**（`processing` -> `rejected`+tombstone；已 `consumed`/`rejected` 保留原 status 仅补幂等 tombstone；已 tombstone digest 精确匹配 no-op / 不匹配 fail closed）；**execution Run 维度（族 1 + 终态互操作）**——`output_publish_state IN ('pending','dead_letter')` 计入残留必须 blocked、`not_required`/`published`/`suppressed` 为终态 pass、participant 只读不改写 Run 行（投影缺失/谓词漏状态/谓词过宽误伤 not_required 的变异被击杀）；**残留 -> blocked 反向判别（族 2）**——outbox 残留、inbox 未决 receipt 残留各补反例，断言 `reason_code` + checkpoint/operation 三方一致（scan 排除某状态、inbox scan 恒零的变异被击杀）；final scan 为零才 ACK；**participant ACK replay/fencing**——ACK 丢失重放幂等（erased fence 先于 purge 前置）、fencing 全套（registry drift/lease_epoch/hold_revision_snapshot/owner_version/capability_digest CAS）、scan 非零 -> blocked 三方一致、legal hold -> blocked；**capability gate**——A 阶段 `require_capability(transport_owner, "erase")` fail closed + **拒绝后 fence/checkpoint/outbox/inbox 三方零变更**（gate 位置错误变异被击杀，族 4）；**claim 交错**——claim 中行被 participant tombstone -> consumer 重放 fail closed 不复活正文、tombstone 后（`suppressed`/`cancelled`）行不被 claim 拾取（claim 谓词放宽的变异被击杀）；**partial ACK（D6）**——部分 owner ACK 不得写 `completed`、全部 owner ACK 才 completed（变异：把部分 ACK 判为 completed 变红）；**跨 tenant/跨 Conversation 反例**（S2-D/E 表驱动模式）；mutation kill（缺 tombstone、跳过 scan、退化 ACK 谓词、入口缺 capability gate、claim 谓词纳入 suppressed、partial ACK 误判 completed、scan 谓词误排除 `cancelled` 泄漏）。
2. **S4-D-B：resolve + activation 矩阵**——`epoch_unresolvable` resolve 证据（`receipt_tombstone_digest` -> `resolution_digest`）+ `(id, revision)` CAS + 投影重算同事务（orphan 最高优先级聚合）；**resolve 边界**——participant 只 resolve `conversation_scope` 行、`tenant_scope`/`orphan` 不 resolve 不改投影（变异：尝试 resolve tenant_scope 行被击杀）；**S4-C outbox exact-terminal replay（round-6/7 三分支）**——Tx1 提交 → Tx2 崩溃 → resolve → 重放时 outbox 仍 `claimed`：锁后检查 outbox 精确终态（已终态 no-op / claimed+CAS 续做 / 其余 fail closed），ledger `resolved` 不代替 Tx2；conversation_scope gate 内嵌 fail closed（绕过 scheduler 直调 participant 仍 blocked）；tenant_scope gate 共享查询（S5 消费）；backfill/consumer/participant 同一共享层投影实现（无两份漂移）；registry 翻 True 带 mutation kill（缺 participant / 缺 resolve 变红）+ 断言测试同 commit 更新。
3. 全量：S4-B/S4-C 专项 + 邻近回归全绿 + 全量 pytest 0 failed（`external_network` 手工 opt-in 除外，R6）+ ruff 0 + mypy baseline 0 回归 + docs gate + `git diff --check`；`erase_available` 在 S4-D-A 保持 False、S4-D-B 最终激活提交翻 True；**真实 PG 反例沿用/参照 S4-C batch3 `_ensure_test_tenant` 种子 fixture**（S4-C 教训：本地共享库掩盖 CI fresh 库 `fk_agent_transport_reconcile_tenant` 外键缺失，仅 CI 暴露）；不改 migration 040、不实现 041、不启用 S5。

#### R1-S4-F Fault 矩阵 + S4 收口 契约细化（2026-08-12，先于实现冻结，纯文档）

> 按 S4-A D1-D8 / S4-B B1-B8 / S4-C C1-C9 / S4-D D-A-1~D-B-3/D-Act-1 / S4-E E-0~E-7 冻结 S4 阶段 fault 矩阵与收口契约。**本 delta 只写文档：不写业务代码、不改 migration 040/041、不翻 registry、不启用 purge scheduler（S5）、不进 S6/C1、不改 S4-C/D/E 已合并终态语义。** 现状盘点基于 main `5f5a5bfc`（S4-E-C 已合并，S4-A..E 全部 merged-boundary 关闭，S4 阶段 participant 全落地：migration 040/041 + backfill + writer/claim fence + transport participant + ledger resolve + external/runtime conformance fake；registry 4 owner True、external/runtime 2 owner False）。S4-E E-7 边界曾把 S4-F（fault 矩阵）排除在 S4-E 契约外；现 S4-E 已关闭，S4-F 独立契约冻结启动，作为 R1-S4 最后子项与 S4 收口。
>
> **F-0. 定位与证据层次（冻结）**：S4-F = S4 阶段 fault 矩阵 + S4 收口。**只证明「已合并的 S4-C/D/E participant 契约中的故障处理主张」有当前提交证据，供 S6/C1 的 R1-AC1..12 联合验收复用**；证据层次为 **contract-tested**（fake adapter 注入 + 真实 PostgreSQL 并发/崩溃，SQLite/mock 只覆盖纯状态转换——真实 PG 故障基线见本 plan §6 全局验证命令与 R1-AC7「真实 PostgreSQL 测试」）——**不冒充 S5 scheduler 验收（真实调度/claim 租约/运维接线）、不冒充 S6 真实故障注入（Worker kill/retention clocks/备份恢复 drill）、不冒充生产 adapter 验收（真实 Pi Worker/spool/云对象存储，REQ-043）**。R1-S4 段头「验证：每个 inbox/outbox crash point、claim 与 purge lock inversion、历史回填不确定行、external erase timeout/outcome unknown、旧 runtime seq tombstone」（line 642）即为 S4-F 的验收范围来源。
>
> **F-1. 故障点清单（冻结）**——按风险域冻结故障点，明确「已覆盖（已合并测试）/ S4-F 动作」分工，杜绝重复实现与冒充：
>
> | # | 故障点（风险域） | 载体（participant/协议） | 已覆盖（已合并测试证据） | S4-F 动作 |
> |---|----------------|------------------------|------------------------|-----------|
> | 1 | 崩溃：Tx1 提交后、Tx2 前（checkpoint `erasing`/attempt/intent 持久化） | S4-E-B2 external / E-C runtime 双事务 | `test_*_crash_after_tx1_replays_to_completion`（B2 `:1001` / C `:791`）、`test_erase_checkpoint_erasing_replay_fail_closed`（B2 `:1305`） | 消费证据 + 互操作确认 |
> | 2 | 崩溃：adapter 调用后、Tx2 receipt 写前 | S4-E-B2/E-C | `test_crash_replay_shared_adapter_distinct_destroy_once`（**C** `:1588`，总 distinct destroy==1）；external 侧同保证由 `test_erase_crash_after_tx1_replays_to_completion`（B2，`adapter.calls==1`）承载 | 消费证据 |
> | 3 | ACK 丢失（erased fence 重放修复 pending checkpoint） | S4-D transport / S4-E | `test_ack_lost_erased_fence_repairs_pending_checkpoint`、`test_erased_fence_replay_repairs_pending_checkpoint` | 消费证据 |
> | 4 | 超时：可能已生效 -> `unknown`（不自动重试） | S4-E E-3a | `test_*_timeout_marks_unknown`（B2 `:713` / C `:582`）、`test_destroy_timeout_marks_unknown` | 消费证据 |
> | 5 | 超时：可证明未发送 -> `blocked`/`erase_timeout` | S4-E E-3a | `test_*_not_sent_blocks_erase_timeout`（B2 `:670` / C `:558`） | 消费证据 |
> | 6 | `unknown` outcome 禁自动重试 + reconcile 需 evidence | S4-E E-3b | `test_query_blocked_unknown_*`（B2 `:1661` / C `:978`）、`test_reconcile_requires_receipt_lookup_capability` | 消费证据 + 互操作确认 |
> | 7 | stale lease_epoch（takeover） | S4-D/E fencing + E-2a 重验 | `test_erase_stale_lease_epoch_fail_closed`（**仅 runtime**，E-C `:1338`） | **external 需新增（族 B）**——external Tx2 缺 `expire_all` 新鲜重读，跨进程 takeover 不可检测（见 F-6） |
> | 8 | stale revision/attempt（Tx2 精确重验） | S4-E Tx2 | `test_erase_tx2_checkpoint_attempt_mismatch_fail_closed`、`test_erase_tx2_checkpoint_intent_mismatch_fail_closed` | 消费证据（同族 7，external 需在族 B 反例中确认） |
> | 9 | 重复调用（idempotency key + 共享 fence 串行化） | S4-E-B2/E-C | `test_concurrent_double_*_erase_serializes`（B2 `:1146` / C `:1536`）、`test_idempotency_key_stable_across_lease_epoch` | **新增跨 Conversation 同一 object 双删互操作**（限定幂等重放 adapter，族 D） |
> | 10 | 并发 takeover（lease 推进 + checkpoint attempt 承载） | S4-E | 手动推进 lease 模拟（S4-E 先例）；runtime 侧 `expire_all` 已落地（E-C `:697`） | **external 需新增（族 B）**——`expire_all` 移植 + 跨进程 takeover 反例 |
> | 11 | receipt/intent mismatch（伪造本地 receipt / digest 篡改） | S4-E E-2b/E-6 | `test_erased_fence_replay_checkpoint_digest_form`（C `:1679`）+ intent digest 重验 fail-closed（raise） | **无 `digest_mismatch` 终态写者（vacuous，族 D）**——不得为实现该终态新增死代码 |
> | 12 | claim 交错（claim 中行被 tombstone） | S4-D | inbox tombstone 矩阵 + S4-C 互操作 | 消费证据 |
> | 13 | **跨 tenant / 跨 Conversation（R1-AC9）** | 全部 participant | resolve `tenant_scope`/`orphan` fail-closed（部分） | **新增系统性矩阵**（伪造 ACK、owner scope mismatch、跨 tenant 同 ref 值） |
> | 14 | **日志/指标/operation 脱敏（R1-AC10）** | 全部 participant | 无专门测试（schema 结构性不承载正文，缺行为证据） | **新增**（正文/ref 原值不入 operation/checkpoint/日志/指标） |
> | 15 | **partial ACK（D6）** | operation 聚合（跨 owner） | 部分（S4-D 单 owner 断言） | **补强跨 owner 互操作**（任一 owner 未 ACK 不 completed） |
> | 16 | legal hold / capability gate 不被绕过 | 全部 | gate fail-closed + hold blocked（已合并） | 消费证据 + 互操作确认 |
>
> **F-2. 五方状态一致不变量（冻结）**——每个故障终态断言 operation/checkpoint/fence/Conversation/ledger（runtime 为 binding）五方一致。`reason_code` 按**三层冻结**（participant 不得自造字符串）：① **conversation 级 reason**（`REASON_EXTERNAL_*`/`REASON_RUNTIME_*`/`purge_blocked_by_*_scan_nonzero` 等）；② **行级 `blocked_reason`**（`erase_timeout`/`outcome_unknown`/`adapter_unavailable`/`unknown_scheme`，写入 external ledger 行 / runtime binding）；③ **tombstone/epoch reason**（`RECEIPT_TOMBSTONE_REASON='purge_erasure'`、S4-C epoch code，inbox/outbox 证据保留）。**blocked 三方一致断言**：**单 owner blocked** 时 `checkpoint.reason_code == operation.failure_code`（精确相等，conversation 级 reason 键值）**且** `Conversation.state='deleted'` 且 `purge_state IN ('running','blocked')`（非终态，可重试/运维）**且 fence 终态按触发点三族发散**（见矩阵，不得写死单一值）。**`Conversation` 列一律用 `state` + `purge_state` + `purged_at` 三元表达**：`purge_state` CHECK 仅允许 `not_scheduled/scheduled/running/blocked/failed/completed`（`deleted` 是 `conversation.state` 值、`purged` 不是任何列值——不得混淆两层）。**`checkpoint_digest` 三形式（按状态固定，E-2c/D-1 不可互换）**：`erasing`=intent digest（`external_delete_intent.v1`/`runtime_destroy_intent.v1`）、`blocked`=`TransportBodyScan.digest()`、`acked`=owner final scan digest——S4-F 断言必须按状态选对形式。
>
> **F-2a. 多 owner 聚合架构裁决（Option A：聚合完全归 S5，冻结，S4-F 纠偏升级）**——独立复核新增 P0=0/P1=5/P2=2 触发 TD-092 升级规则，停止在 `_mark_operation_running`/`_record_blocked` 上叠加局部条件，改为架构裁决。**裁决：S4 participant 是 owner-scoped eraser（只写自己的 checkpoint/fence/ledger/binding），不再把共享 operation/Conversation 当作最终聚合事实源；`operation.state`/`failure_code` 与 `Conversation.purge_state` 由 S5 scheduler 按全部 owner checkpoint 统一计算。** `checkpoint.reason_code` owner-specific（逐 checkpoint 精确）；`operation.failure_code` 是 S5 从 blocked checkpoint 集合确定性计算的聚合投影（非任何 participant 的单次写入）。
>
> **失败 reason 严重度优先级（S5 reducer 的排序，高→低；`failure_code` 取 blocked reason 集合最高者）**：
>
> 1. `purge_blocked_by_legal_hold`（法律 hold，最高）
> 2. `purge_blocked_by_unresolved_action`
> 3. `purge_blocked_by_conversation_scope_gate`
> 4. outcome_unknown 族（`purge_blocked_by_external_outcome_unknown` / `purge_blocked_by_runtime_outcome_unknown`，不自动重试）
> 5. erase_timeout 族（`purge_blocked_by_external_erase_timeout` / `purge_blocked_by_runtime_erase_timeout`）
> 6. adapter_unavailable 族（`purge_blocked_by_external_adapter_unavailable` / `purge_blocked_by_runtime_adapter_unavailable`）
> 7. scan_nonzero 族（`purge_blocked_by_external_ref_scan_nonzero` / `purge_blocked_by_runtime_binding_scan_nonzero` / `purge_blocked_by_transport_scan_nonzero` / `workspace_body_scan_nonzero` / `execution_body_scan_nonzero`）
> 8. `purge_owner_unavailable`
> 9. `operator_suppressed`（fallback，最低）
>
> **同严重度 tie-break（冻结）**：同严重度 reason（如 external outcome_unknown 600 vs runtime outcome_unknown 600）按 **owner_key 字典序**（registry 排序）取最小者——确定性、与 S5 固定 owner 处理顺序一致；**禁用「先提交者保留」与「最后提交者覆盖」**。
>
> **写者所有权（冻结）**：
>
> | 实体 | 写者 | 状态迁移 |
> |------|------|---------|
> | owner checkpoint | participant | `pending -> erasing -> acked/blocked` |
> | owner fence | participant | `active -> erasing -> erased/blocked` |
> | external ledger / runtime binding | participant | `registered -> erased/blocked/unknown` |
> | operation.state / failure_code | **S5** | `scheduled -> running -> blocked/completed`（从全部 checkpoint 集合聚合） |
> | Conversation.purge_state | **S5** | 投影 operation.state |
>
> **S4 期间临时投影与 S5 接管边界（冻结）**：当前 S2-D/S3-D/S4-D/E participant 直接写 operation/Conversation 是 **S4 期间临时投影**（S5 未实现的占位），**不构成最终聚合事实源**——S5 实现后由 reducer 替换。本 PR（S4-F）**只冻结本裁决，不越界实现 S5 reducer、不改 core participant 的临时投影写者**；「owner-scoped participant 重构（6 owner 移除对 operation/Conversation 的写）+ S5 聚合 reducer」拆为**独立 contract-first PR**（先冻结 reducer 状态表/写者所有权/迁移边界，再实现）。**延期项登记（归独立 contract-first PR，不在 #561）**：① `_repair_checkpoint_if_pending` 对共享 failure_code 的临时投影风险（erased-fence 重放清他 owner blocked failure_code）；② 六 owner 移除 operation/Conversation 写入；③ S5 aggregation reducer + blocked 单调性 + reason tie-break + completed/failure_code 清除权；④ receipt-lookup-only adapter 的 Tx2 双重外部 I/O 约束；⑤ `_load_registered_refs` 锁序 `ORDER BY`（除非测试证明结果依赖顺序）。
>
> **六不变量（冻结，任何实现须满足）**：
>
> 1. 任一 checkpoint blocked → operation/Conversation **不得被后到 ACK owner 重开 running**。
> 2. `failure_code` 从**当前 blocked checkpoint 集合**确定性计算（非 last-writer-wins）。
> 3. 同严重度 reason 用 owner_key 字典序 tie-break（非先提交者保留 / 最后提交者覆盖）。
> 4. ACK / blocked / erased-replay / retry 任意提交顺序结果一致。
> 5. 全部 owner ACK 后 completed / failure_code 清除仍归 S5。
> 6. 单 owner 重试（S5 重跑该 owner）与多 owner 聚合（S5 重算全部 checkpoint）语义分离——「本 owner 重试」不得清除其他 owner 的 blocked 事实。
>
> **临时投影方法 × owner 横向审计（冻结，S4-F 纠偏）**：`_mark_operation_running`/`_record_blocked`/`_repair_checkpoint_if_pending` 三方法对 operation/Conversation 的写是 S4 期间临时投影，**共 3 份独立实现**（非单一基类）：① `app/composition/transport_erasure_participant.py` 基类（workspace.transport.v1 / execution.transport.v1 / external.payload.v1 / runtime.private.v1 共 4 owner 复用）；② `app/contexts/agent_workspace/infrastructure/workspace_erasure_participant.py`（workspace.core.v1 自有 last-writer-wins 副本）；③ `app/contexts/agent_execution/infrastructure/execution_erasure_participant.py`（execution.core.v1 自有 last-writer-wins 副本）。**不得只改 transport 基类却声明全 owner 聚合已落地**；core 两 owner 的 last-writer-wins 副本由「owner-scoped 重构 + S5 reducer」独立 PR 一并替换。#561 的 fault 矩阵测试只断 owner-scoped（checkpoint/fence/ledger/binding），**不断 operation/Conversation 聚合**（S5 reducer 职责）。
>
> | 故障终态 | operation（`agent_conversation_purges`） | checkpoint（`agent_conversation_purge_owners`） | fence（`agent_erasure_fences`） | Conversation（`state`+`purge_state`+`purged_at`） | external ledger / runtime binding |
> |---------|-----------------------------------------|-----------------------------------------------|-------------------------------|----------------------------------|----------------------------------|
> | 已合并可达成功态（单 owner ACK） | `running`（**`completed` 正向判定归 S5，S4-F 只断负向**，族 C） | `acked` + `ack_digest`（owner summary digest）+ `checkpoint_digest`（=final scan digest） | `erased` + `ack_digest` + `acked_at`（`ck_..._ack` 强制） | `state='deleted'` + `purge_state='running'` + `purged_at IS NULL` | external `erased`+`receipt_digest`；runtime `closed`（ref 清空） |
> | S5 目标态（全部 owner ACK 聚合后） | `completed`（`completed_at` 非空）——**无 S4 已合并写者，S5 前置契约，不作 S4-F 断言** | — | — | `purge_state='completed'`/`purged_at` 非空——同左 | — |
> | blocked：**前置 gate 命中**（legal hold / owner scope / ref-bearing 前置） | `blocked` + `failure_code`（= reason 键值） | `blocked` + `reason_code`（= failure_code） | **`active`**（gate 前置命中，adapter 窗口未开） | `state='deleted'` + `purge_state='blocked'` + `purged_at IS NULL` | external `blocked`+`blocked_reason`；runtime `invalid`（ref 保留，不进窗口） |
> | blocked：**adapter 失败 / 残留后段**（Tx1 已推进 `erasing`） | `blocked` + `failure_code` | `blocked` + `reason_code`（=failure_code）+ `checkpoint_digest`（=`TransportBodyScan.digest()` 留证） | **`erasing`**（Tx2 `_record_blocked` 不碰 fence，**不回退 `active`**——owner 一旦离开 active 不得重开 writer 窗口）；core 族（S2-D/S3-D）final scan 非零为 **`blocked`**（三族发散，F-4 登记） | `state='deleted'` + `purge_state='blocked'` + `purged_at IS NULL` | external `blocked`+`blocked_reason`；runtime `invalid` |
> | unknown（outcome 未知，不自动重试） | `blocked` + `failure_code`=`purge_blocked_by_external_outcome_unknown`（不自动重试，S5 后接运维） | `blocked` + `reason_code` 同值 | **`erasing`**（Tx1 已推进，不回退） | `state='deleted'` + `purge_state='blocked'` + `purged_at IS NULL` | external `unknown`+`blocked_reason=outcome_unknown`；runtime `invalid` |
> | fail closed（E-2a 精确重验任一不符） | **零写：Tx2 `raise` 回滚，保持 Tx1 已提交态**（`running`） | `erasing`（Tx1 已提交态，不写 blocked、不写 receipt） | `erasing`（Tx1 已提交态） | `state='deleted'` + `purge_state='running'` + `purged_at IS NULL` | 保持 Tx1 窗口态（external `registered`；runtime binding ref 保留）——不覆盖、不伪造 |
> | partial ACK（D6） | **`running`/`blocked`（任一 owner 未 ACK 不 completed；正向 completed 归 S5）** | 已 ACK owner `acked`、未 ACK owner `pending`/`blocked` | 各 owner 各自态 | `state='deleted'` + `purge_state` 依 owner 聚合 | 各 owner 各自态 |
> | `failed`/`cancelled`（operation）/ `failed`（checkpoint） | **无 S4 已合并写者（S5 保留），不得作为 S4-F 断言** | 同左 | — | — | — |
>
> **F-3. 故障注入机制（冻结）**——S4-F 实现只允许下列注入机制，**故障场景必须真实 PostgreSQL**：
>
> 1. **fake adapter 故障注入**（external `ExternalObjectAdapter` / runtime `RuntimeSessionDestroyAdapter`）：发送前连接错误（可证明未发送）→ `blocked`/`erase_timeout`；发送后 `TimeoutError`（可能已生效）→ `unknown`；`unknown` outcome；明确失败；成功 + 可验证 evidence；`receipt_lookup` 两分支（有/无 evidence）。注入点必须与 E-2b capability 前置判定正交（缺幂等重放且缺 receipt lookup 的 adapter 不得进入窗口）。
> 2. **崩溃注入**：可控 adapter 回调抛异常 + 事务分离回滚（S4-C 先例，模拟 Tx1 提交后 / Tx2 receipt 前崩溃）；断言持久化残留（checkpoint `erasing`/attempt/intent、ledger `registered`、fence `erasing`），重放精确重验后收敛。
> 3. **真实 PG 双连接并发**：`session_factory` + `asyncio.gather`（S4-E-B1/B2/C 先例）；断言串行化、总调用数、CAS 冲突降级。
> 4. **手动推进 lease_epoch / attempt / revision**：模拟 takeover（S4-E 先例）；断言 E-2a 精确重验 fail closed + idempotency key 跨 takeover 稳定。
> 5. **DB 篡改注入**：直接改行制造 receipt_digest / checkpoint_digest / intent digest / status / `blocked_reason` mismatch；断言 fail closed 不覆盖、不伪造。
> 6. **日志脱敏注入（R1-AC10）**：**可判别 sentinel（真实种入源数据）**——正文（transport outbox inline body）、external ref（ledger `ref_value`）、runtime ref（binding `runtime_session_ref`）三类，断言 operation/checkpoint/fence 不含这些 sentinel、reason 落冻结 code 集合（禁自由文本 reason）。**结构性不可达（不做 caplog 判别）**——CoT、secret 无对应 DB 字段（spec §9.3「不保存原始 CoT」），S4 participant 无 logger（F-5 禁做日志管道，caplog 空真不构成证据）——均标注「结构性无」，不假称 caplog/sentinel 判别。**ledger 例外（冻结）**：external ledger（`agent_external_object_refs`）按设计**必须**保存 `ref_scheme`/`ref_value` 作为外部对象唯一身份（E-1 ledger 是唯一事实源），**仅此身份字段例外**——ledger 不得承载正文、Runtime session ref、CoT、secret、自由文本 reason（`blocked_reason` 必须是冻结 code 集合值）。
> 7. **跨 tenant / 跨 Conversation 注入（R1-AC9）**：双 tenant 同 ref 值、跨 Conversation 同一 external object（idempotency key 去重）、伪造 ACK / operation revision 重放、owner scope mismatch。**多族混合故障**（F-6 行 5）由机制 1（各族 adapter 注入不同故障）+ 机制 3（真实 PG 双连接 `asyncio.gather` 并发）按 F-4 装配——机制清单未列不代表跳过，而是组合装配。
>
> **F-4. 互操作回归矩阵（冻结）**——共享行为跨 participant 族（workspace / execution / transport / external / runtime conformance）验证一致性，S4-F 的**新增维度**是「同一 Conversation 多 participant 族混合故障」组合（已合并测试均为单族隔离）：
>
> - **final scan 谓词一致性**：outbox 正文事实谓词（`payload_inline IS NOT NULL OR payload_ref IS NOT NULL`，含 `cancelled`）、inbox 未决 receipt、execution Run `output_publish_state`（`pending`/`dead_letter` 残留；`not_required`/`published`/`suppressed` 终态）、external ref scan（`registered`/`blocked`/`unknown`）、runtime binding scan（**`runtime_session_ref IS NOT NULL`——含 `invalid` 行，blocked/unknown 保留 ref 即残留不得 ACK；仅 `closed` 因 ref 置空天然排除**；`invalid` 不入 adapter 窗口=不自动重试，窗口语义与 scan 语义分离）——五族谓词各自为零才 ACK，混合 conversation 下互不误伤。
> - **锁序一致性（D8 全局链）**：Guard -> Conversation 行锁 -> owner advisory lock -> fence 重验 -> 集合 advisory lock -> 源行；所有 participant 族同序，混合 fault 下无 AB-BA。**集合锁 owner 与 backfill 同源**（`_EXTERNAL_REF_COLLECTION_OWNER_BY_SOURCE`：outbox→transport owner、run_events→external owner，与 backfill `OWNER_BY_TABLE` 逐表一致）——同一源行并发写必须落同一把集合锁；owner 漂移变异击杀（族 D）。
> - **capability gate**：4 owner True 放行、external/runtime 2 owner False fail closed（拒绝后 fence/checkpoint/源行零变更）；gate 位置后移变异击杀。
> - **legal hold 不绕过**：active hold -> blocked（`purge_blocked_by_legal_hold`），hold/purge CAS 排序不被 fault 路径绕过；`expires_at` 过期判定归 S1 F6 已登记项，S4-F 只按 `has_active_legal_hold` 现状断言（族 E）。
> - **partial ACK（D6）**：**只冻结负向断言**（任一 owner 未 ACK -> operation 不 completed、未 ACK owner checkpoint 保持 pending/blocked）；正向 completed 判定依赖 S5 跨 owner 聚合，S4-F 不实现（族 C）。
> - **fence 终态三族发散（族 A，登记为互操作维度）**：blocked 时 core 族（S2-D/S3-D final scan 非零）=`blocked`、transport/external/runtime 后段（Tx1 已推进）=`erasing`、仅前置 gate 命中=`active`——S4-F 断言不得写死单一值，按触发点选择。**注意同 gate 类型触发点随 participant 不同**：transport 基类 conversation_scope gate 在 fence→`erasing` 之后（blocked 后 fence=`erasing`），runtime scope gate 在 fence 推进前（fence=`active`）——断言按实际代码路径推导，不得硬编码。
> - **跨 tenant 隔离**：双 tenant 并行 fault 无交叉污染（R1-AC9）。
>
> **F-5. 与 S5/S6 分工与 registry/迁移边界（冻结）**：
>
> - **不实现/不启用 S5**（穷举 R1-S5 全部交付项，list 即禁做）：scheduler claim/租约（`conversation_purge_scheduler` + PostgreSQL clock + bounded claim lease）、operation `lease_epoch` 推进/接管、blocked/unknown 的 HTTP/CLI 接线、inspect/retry/reconcile 内部 API 接线、tenant 限流/指数退避、scheduler 并发 claim、**legal hold 数据治理 API（create/release/list，显式 permission + purpose + reason code，first decision/CAS 审计）**、**owner 顺序执行与 checkpoint 部分失败重试**、**registry/hold revision 变化新建 revision**、**指标与脱敏日志 pipeline（queue age、owner latency/attempt、blocked reason、late writes、retention lag、external orphan）**。S4-F 只验证 participant 侧对 takeover/租约变化的 fail-closed 反应，不实现推进者。legal hold `expires_at` 过期判定归 S1 F6 已登记项，S4-F 不涉及（族 E）。
> - **不实现 S6**（穷举 R1-S6 交付项）：真实 PostgreSQL Worker kill、retention clocks（`run_event_retention` payload expiry/连续 envelope prune/`first_available_event_seq`；`run_audit_retention` 365 天 prune）、seq gap、outbox claim 运维闭环、hold revision 全局联动、备份恢复 drill、body/ref orphan 巡检（tenant mismatch/digest conflict/event gap/unknown ref scheme/missing fence-owner scope）、owner/writer conformance suite 枚举、expand/backfill/enforce/enable 演练。S4-F 的故障注入是 participant 契约级（fake adapter + 真实 PG 并发），**不等于 S6 的真实故障注入验收**。
> - **registry 不变**：4 owner True / `external.payload.v1`+`runtime.private.v1` False 全程保持（E-4 确定性选择，无生产 db_local adapter）；不把 S4-F 的 contract-tested 证据当作激活依据（spec §10.2）。
> - **无契约依据不新增 migration/schema**；不改 S4-C/D/E 已合并终态语义；不新增 inbox/outbox status 枚举、不新增 ledger 列、不翻 `erase_available`。
>
> **F-6. 验收反例矩阵（S4-F 实现时逐项；已由 E-6 冻结并实现的故障点不再重开，只互操作确认）**：
>
> | 反例 | 触发 | 期望行为（fail closed） | 判别点 / 注入 |
> |------|------|------------------------|--------------|
> | 跨 tenant 伪造 ACK（R1-AC9） | tenant A 的 operation/revision 在 tenant B 的 conversation 上重放 | 拒绝：operation 身份/tenant scope 不匹配 fail closed，不写任何终态 | 双 tenant 种子 + 跨 tenant 重放；断言 tenant-B 侧零变更（fence 仍 active、无新增 checkpoint）；变异：**删除全部 tenant 维度校验**（`_load_verified_operation`/`_load_verified_checkpoint` 的 tenant 谓词同时去掉）-> 红 |
> | owner scope mismatch（R1-AC9） | 与 conversation owner 不符的 owner 直调 participant | capability gate（`OwnerCapabilityUnavailableError`）/ conversation-tenant 校验 / owner checkpoint 缺行（`_load_verified_checkpoint` 按 owner_key 找不到）均 fail closed，不 bypass（`purge_owner_unavailable` 是 E-0a ref-bearing 前置 reason，**不是** wrong-owner 直调的 reason） | S4-F 测试走 owner checkpoint 缺行路径（registry 翻 True 隔离 gate，conversation 只登记 transport owner 行）；gate 路径由既有 registry fail-closed 套件承载；断言拒绝后 fence/checkpoint/源行零变更 |
> | operation revision 重放（R1-AC9） | 旧 revision 的 purge operation 重放 | revision CAS 拒绝（stale revision），不重复清除 | 断言 fail closed + operation revision 不变；变异：跳过 revision CAS -> 红 |
> | **跨 purge 实例 erased-fence 重放（族 B）** | 同 conversation 部分 ACK 后 S5 建新 purge op2（rev2），op2 重放 op1 已 `erased` fence | **拒绝、零 ACK 修复**——erased-fence 重放须校验 `fence.purge_revision == purge_revision`（跨 purge 实例 ack 摘要不得污染）；runtime 已实现（E-C），**S4-F 实现补齐 external/transport**。**族 A 补充（实现返修）**：external/transport 的 **ERASING 分支**（fence 已 erasing 时）同加 `fence.purge_revision == purge_revision` 门禁（镜像 runtime `:594-606`）——op2 在 op1 中段不得进 adapter 窗口（E-6「重复删除」串行化），判别测试 `test_external_erasing_fence_second_purge_instance_rejected`（adapter.calls==0） | 种子：op1 已 erased fence + op2 pending checkpoint；断言 op2 拒绝且 pending 不修复；变异：去掉 purge_revision 门禁 -> 红 |
> | **external 跨进程 takeover（族 B）** | Tx1 提交后、Tx2 前由第二连接 bump operation.lease_epoch / checkpoint.attempt / checkpoint_digest | Tx2 精确重验（E-2a）fail closed + 零写；**external 现状缺 `expire_all` 无法观测并发 takeover，S4-F 实现需移植 runtime `expire_all`（E-C `:697`）并固化「Tx2 重验须观察已提交态」为跨族不变量** | 双连接：连接1 Tx1 提交 → 连接2 UPDATE 篡改 lease/attempt/digest → 连接1 Tx2 断言五重 fail-closed + 零写；变异：Tx2 不新鲜重读 -> 红 |
> | 跨 Conversation 同一 object 双删 | 同一 external object ref 出现在两个 conversation，两 purge 并发 | **两 conversation 共用 idempotency key**（ref_scheme+ref_value+adapter identity，不含 conversation/tenant）+ 共享 adapter 幂等去重——**仅对幂等重放 adapter 保证 distinct delete==1**；receipt-lookup-only adapter 跨 conversation 并发由 adapter 层负责（S4-F fake 用 key→evidence 共享 store 镜像 `_SharedDedupCrashAdapter`） | 双 conversation 同 ref 种子 + 并发 purge；共享 adapter 总 distinct delete==1 |
> | 混合 conversation 多族同时故障 | 同一 conversation 内 external ref + runtime binding + transport outbox（**ref-bearing 前置故障**）同时故障，**三族并发执行**（external/runtime/transport 各真实调用 `erase_external_payload`/`erase_runtime_session`/`erase_transport_owner`，transport **不得**仅用 workspace outbox 作 external ref 种子冒充 transport 覆盖） | 各 owner 独立 blocked/unknown/erased，`checkpoint.reason_code` 逐 owner 精确（owner-specific）；`operation.failure_code`/`Conversation.purge_state` 聚合断言**归 S5**（F-2a，S4-F 不断） | 混合种子（external ref + runtime binding + transport ref-bearing outbox，**external/transport 同源**）+ **`asyncio.gather` 并发**三族各注入**不同** reason 的故障；断言逐 owner checkpoint/fence/source ledger/binding 五方一致（owner-scoped）+ 未 ACK owner 保持；**不断** operation.failure_code 聚合（S5 reducer 职责） |
> | 日志脱敏（R1-AC10） | purge 路径触发（含故障） | operation/checkpoint/fence 不含正文/external ref/runtime ref sentinel（**真判别**，三类真实种入源数据）；**external ledger 仅允许 external ref identity（`ref_value` 保留 sentinel），不得含正文/runtime ref**（F-3 机制 6 ledger 例外）；reason 落冻结 code 集合（禁自由文本 reason）；CoT/secret 结构性不可达（spec §9.3 不落库）、日志结构性无（S4 无 logger）——不做 caplog/sentinel 假判别 | 种正文（transport outbox inline body）/external ref（ledger `ref_value`）/runtime ref（binding `runtime_session_ref`）三类 sentinel；断言 operation/checkpoint/fence 不含三类 sentinel + ledger 仅含 external ref identity + reason 落冻结集合；变异：把 ref sentinel 写入 reason/failure_code -> 红 |
> | partial ACK（D6） | 部分 owner 故障 blocked、部分 ACK | **负向断言**：operation 不得 `completed`；未 ACK owner checkpoint 保持 pending/blocked；正向 completed 依赖 S5 跨 owner 聚合不测 | 混合故障种子；断言 operation 非 completed；变异：部分 ACK 判 completed -> 红 |
> | 迟到 runtime write + purge 窗口（R1-AC8 的 S4 部分） | purge 窗口内旧 epoch/迟到 seq 写正文 | fail closed 不重建正文（spec §10.3 五项 conformance） | 已覆盖（S4-E-C 写路径回归）；S4-F 互操作确认 |
> | old/missing producer revision（R1-AC8 的 S4 部分） | 旧 producer revision / 缺失 scope 的事件在 purge 后重投 | tombstone/reconcile，不复活正文 | 已覆盖（S4-C producer propagation）；S4-F 互操作确认 |
>
> **F-7. S4 阶段验收证据与收口（冻结）**：S4-F 实现产出的证据锚定 **R1-AC2（owner registry snapshot/digest、未知 owner、**版本变化**（`OwnerRegistryChangedError`/registry digest drift）和缺失 capability 均 fail closed）、R1-AC4（participant 分步 ACK、部分失败、重试、lease 接管可恢复）、R1-AC8（pending/queued projection、outbox claim、旧 producer revision、Runtime 迟到 event、external erase unknown 不盲重试正文写）、R1-AC9（跨 tenant/伪造 ACK/revision 重放拒绝）、R1-AC10（正文/ref 不入 purge operation/checkpoint/日志/指标）** 的 S4 相关子项，以 evidence inventory 形式汇入 plan/PR（每项：AC -> 证据测试文件 -> contract-tested 层次）。**S4 收口**：S4-A..F 全部 merged-boundary 关闭后 R1-S4 段头交付 checkbox 全部勾选、plan 补 S4-F merged-boundary 记录；S5/S6/C1 明确不启动。**退出条件**：S4-F 实现 Draft 稳定且三面 P0/P1=0（contract-tested 证据完整、互操作矩阵全绿、registry 保持 4 True/2 False）。
>
> **S4-F 契约冻结 merged-boundary 与合并记录（2026-08-12，契约 PR #559，squash merge `d658f6eb`，评分 92）**：落点对账证实 plan 无 S4-F 冻结矩阵（真实故障矩阵归属 R1-S6、工作台候选卡自述需「实现前契约冻结」），经用户裁定先冻结契约再实现，符合 S4-D（PR #541）/S4-E（PR #546）契约冻结先例。**本 delta 只写文档**：冻结 `R1-S4-F Fault 矩阵 + S4 收口` F-0~F-7（F-0 定位与证据层次 contract-tested、F-1 故障点清单 16 项含「已覆盖/需新增」分工、F-2 五方状态一致不变量矩阵、F-3 注入机制 7 种真实 PG 强制、F-4 互操作回归、F-5 与 S5/S6 分工穷举、F-6 验收反例矩阵 11 项、F-7 R1-AC2/AC4/AC8/AC9/AC10 锚定与 S4 收口），净 diff 仅 plan + current-work 两纯文档文件，registry external/runtime 保持 False、4 owner True 不变，不改 migration 040/041，不启用 S5、不进 S6/C1。三面首轮（数据/状态机 P0=0/P1=4/P2=5/P3=3 + 并发/锁序 P0=0/P1=2/P2=3/P3=2 + 测试/运维/文档 P0=0/P1=0/P2=1/P3=4，**首轮原始合计 P0=0/P1=6/P2=9/P3=9 保留不覆盖**）按 5 根因族一次返修（`1625920b`）：族A F-2 矩阵与已合并实现对齐（fence 三族终态发散/fail-closed 零写/Conversation 两层/checkpoint_digest 三形式/reason 三层）、族B runtime 独有并发防护跨族化（external `expire_all` + 跨 purge 实例门禁 + 集合锁 owner 同源）、族C completed 正向归 S5、族D 矩阵精度、族E 文档引用/穷举；定向复核曾发现 **1 条返修引入的新 P1**（F-2 `reason_code` 误写为 scan digest）已纠正（`facd8768`）-> 最终 **P0/P1=0** -> 评分 92（Original，基线 `202c5512`，净 diff 仅 Score Log 1 行）-> Ready 三路 required checks 全绿（Backend/Frontend/Engineering docs）-> mergeStateStatus CLEAN/MERGEABLE -> squash merge `d658f6eb` + 分支清理 + docs closeout（工作台归档 + work-log 索引 + 本记录）。**merged-boundary 结论**：S4-F 契约冻结完成——F-0~F-7 冻结 S4 阶段 fault 矩阵与收口；**跨族不变量固化**「Tx2 精确重验必须观察已提交态（`expire_all`，external 现状缺失，S4-F 实现移植）」与「erased-fence 跨 purge 实例门禁（`fence.purge_revision==purge_revision`，external/transport 现状缺失，S4-F 实现补齐）」为 S4-F 实现 PR 落地项；F-6 反例矩阵 11 项（含族 B external 跨进程 takeover + 跨 purge 实例重放）为实现验收清单。**S4-F 契约冻结全线闭环**：registry `external.payload.v1`/`runtime.private.v1` 保持 False（E-4）；遗留实现 S4-F（fault 矩阵，下一任务，工作台候选已登记）、S5 scheduler、S6、C1 总验收明确排除。
>
> **S4-F 实现 merged-boundary 与合并记录（2026-08-13，实现 PR #561，squash merge `bc3234bd`，评分 90）**：**多轮广域复审持续发现 P1 触发 TD-092 升级规则，采用 Option A 架构裁决（operation/Conversation 聚合完全归 S5 scheduler）**——S4 participant 只写 owner-scoped checkpoint/fence/ledger/binding，当前对 operation/Conversation 的写入标注「S5 未实现期间临时投影 last-writer-wins」不构成最终聚合事实源。**#561 仅完成 S4-F fault matrix**：生产修复 4 处（external Tx2 `expire_all` 跨进程 takeover 可观测；external/transport erased-fence 跨 purge 实例门禁；external/transport ERASING same-purge-instance 门禁）各带失败反例 + mutation kill；18 个反例测试（跨 tenant 伪造 ACK / owner scope mismatch / operation revision 重放 / 跨 purge 实例 erased-fence 重放×2 / external takeover×3 参数化 / 跨 Conversation 双删 / 混合多族 owner-scoped / 三 owner 同源 owner-scoped 含各 fence 终态断言 / 同源正序列 receipt-then-replay / AC10 三路径 external+transport+runtime / partial ACK 负向 / ERASING 门禁 external+transport）+ 零写/零变更快照（op+Conversation+fence+checkpoint+source）+ Event 有界 timeout。**架构决策冻结入 plan F-2a**（六不变量 + 严重度优先级 + owner_key 字典序 tie-break + 写者所有权 + 六 owner × method 横向审计 + 5 项延期登记）。**历程（历史计数保留不覆盖）**：首轮三面 P0=0/P1=3/P2=9/P3=13 → 独立复审 P1=3/P2=1 → HEAD 523be1c1 广域复核 P1=5/P2=2 → Option A 后两轮广域三面各 P1=1（plan F-6 未同步 owner-scoped 家族：行 5 聚合断言 + partial ACK 负向断言，已清零）→ 最终广域三面（数据/状态机 P0=0/P1=0/P2=3/P3=4、并发/锁序 P0=0/P1=0/P2=2/P3=4、测试/运维 P0=0/P1=0/P2=2/P3=4）+ Ready 前 delta 复核 **P0/P1/P2=0**（P3=3 可选）-> 评分 90（Original，基线 `832fad74`，净 diff 仅 Score Log 1 行）-> Ready Backend full **2364 passed / 1 skipped / 4 deselected** + 三路 required checks 全绿 -> mergeStateStatus CLEAN/MERGEABLE -> squash merge `bc3234bd` + 分支清理 + docs closeout（工作台归档 + work-log 索引 + 本记录）。**merged-boundary 结论**：S4-F 实现完成 fault matrix 反例与 owner-scoped 判别力（不断 operation/Conversation 聚合）；**未实现 S5 reducer、未移除六 owner 临时投影写、未改 core participant**——operation/Conversation 的聚合与「owner-scoped participant 重构 + S5 aggregation reducer」归**独立 contract-first PR**（工作台候选已登记，含 5 项延期：`_repair_checkpoint_if_pending` 临时投影风险、六 owner 移除 operation/Conversation 写入、S5 reducer + blocked 单调性 + tie-break + completed 清除权、receipt-lookup-only Tx2 双重 I/O、`_load_registered_refs` ORDER BY）。**S4-F 实现全线闭环**：registry 4 True / external+runtime False 不变；不改 migration 040/041；S5/S6/C1 明确排除。

### R1-S5-A：Owner Aggregation Reducer 契约（contract-first，先冻结后实现）

> Status: Draft（本 PR 仅纯文档契约冻结；不实现 S5 reducer、不改六 owner participant 临时投影写、不改 schema / migration 040/041 / registry、不启动 S5/S6/C1）
> 依据：Spec §5.2/§8；Plan F-2/F-2a（Option A 架构裁决，已冻结）；#561 登记 5 项延期
> 分支：`docs/req041-047-r1-s5a-owner-aggregation-contract`

本契约把 F-2a 的「Option A：聚合完全归 S5」裁决细化到可测试的 reducer 状态表、写者所有权、reason 聚合、fencing 与切换边界。它是「owner-scoped participant 重构 + S5 aggregation reducer」实现 PR 的前置冻结物，**不**在本 PR 内落地任何实现。

#### S5-A-0 横向事实对账（冻结）

对账结果（截至 `main@99a3ffac`，即 #561 之后）：

**三份独立「临时投影」实现**（F-2a 冻结，非单一基类）：六 owner 通过各自 participant 写共享 `operation`/`Conversation`，方法同名但独立实现，共 3 份：

| 独立实现 | 承载 owner | 写 operation/Conversation 的方法（各一份） |
|---------|-----------|------------------------------------------|
| `composition/transport_erasure_participant.py` 基类 | `workspace.transport.v1` / `execution.transport.v1` / `external.payload.v1` / `runtime.private.v1`（4 owner 复用） | `_mark_operation_running` / `_record_blocked` / `_repair_checkpoint_if_pending` |
| `contexts/agent_workspace/infrastructure/workspace_erasure_participant.py` | `workspace.core.v1` | 同上三方法（自有副本） |
| `contexts/agent_execution/infrastructure/execution_erasure_participant.py` | `execution.core.v1` | 同上三方法（自有副本） |

**三方法对共享实体的写（对账后冻结）**：

| 方法 | operation 写 | Conversation.purge_state 写 | 已识别的跨 owner 风险 |
|------|-------------|---------------------------|----------------------|
| `_mark_operation_running` | `scheduled/blocked → running`；清 `failure_code`；`started_at` 仅首次；`revision+1` | 无条件写 `running` | 清 `failure_code` 无 owner 归属 |
| `_record_blocked` | `→ blocked` + `failure_code=reason`；已 blocked 且 reason 变则**覆写** `failure_code`（last-writer-wins） | 无条件写 `blocked` | 覆写无视 severity，结果依赖提交顺序 |
| `_repair_checkpoint_if_pending` | `scheduled/blocked → running`；**无条件清 `failure_code`（非 None 即清，不论 owner）**；`revision+1` | 无条件写 `running` | **invariant-1 可观测违反**：erased-fence 重放重开 running + 清他 owner blocked failure_code |
| `_ack_owner_checkpoint` | **不写**（写 checkpoint `acked` + `ack_digest` + `checkpoint_digest` + 清 `reason_code`；transport/workspace 副本锁 operation FOR UPDATE，execution 副本不锁 operation） | 不写 | 无 |

> 注：上表「Conversation.purge_state 写」列是 **transport 基类**（4 owner 复用）的精确形态；`workspace.core.v1` 三方法不写 `purge_state`（caller `erase_conversation_body` 写），`execution.core.v1` 的 `_repair_checkpoint_if_pending` 不写（caller 写）、`_mark_operation_running`/`_record_blocked` 写——完整移除范围以 S5-A-1 与 S5-A-7 ② 为准。

关键事实（冻结）：
- **`operation.completed_at` 与 `Conversation.purged_at` 在全部 participant 中均从不写入**——终态只作为 guard 读取（`completed/failed/cancelled` 拒绝继续写）。但 **`cancelled` 已有合并写者**：restore 路径 `cancel_scheduled_operations_for_restore`（erasure_repository.py:871）把 `scheduled` operation 置 `cancelled`（保留审计行）。故 `operation.state` 共有**三类写者**：`create_purge_operation`（`scheduled`）、restore-cancel（`cancelled`）、participant 临时投影（`running/blocked`）；`completed`/`failed`/`completed_at`/`purged_at` 仍无写者（S5 保留态）。
- **`Conversation.purge_state` 的写者分两层**：`not_scheduled/scheduled` + `purge_revision++` 是 workspace 的**合法生命周期写**（`soft_delete_after_guard` / `restore_after_guard`），**必须保留**；`running/blocked/failed/completed` + `purged_at` 才是聚合投影（目标归 S5，当前是 participant 临时投影）。**去共享写只移除 `running/blocked` 投影，不得移除 delete/restore 的 `scheduled/not_scheduled` 写。**
- **checkpoint 无 `revision` 列**（`attempt` + 状态白名单 + fence `owner_version`/capability digest 守卫），`operation`/`fence`/`Conversation` 有 `revision` 列。
- **schema CHECK 不承载跨实体不变量**（如「completed ⟺ 全 acked」「failure_code 仅 blocked 非空」「blocked 单调」）——这些是应用层不变量，S5 reducer 是唯一执行者；`Conversation.purge_state` CHECK 无 `cancelled`（`operation.state` 有 `cancelled`），投影映射非 1:1。
- 已知注释漂移（对账发现，不属本契约修复范围，记入 S5-A-7 归属）：execution `_ack_owner_checkpoint` docstring 声称「operation 标记 owner ACKed」但实际只写 checkpoint；workspace 注释称 `_mark_operation_running` 是「failure_code 唯一清除点」但 `_repair_checkpoint_if_pending` 也清。execution 聚合写实际顺序 `AgentRun → CompatibilityOutput → RunEvent → TurnInput` 与 docstring `AgentRun → RunEvent → CompatibilityOutput → TurnInput` 不符。

**reason 全集（冻结；1/5-12 层 participant 可写且代码中已有常量，2/3/4 层为本契约新增冻结的 coordinator-level reason——不得再延期到实现时裁决）**：

| 严重度 | 层 | reason code（operation.failure_code / checkpoint.reason_code 值域） |
|-------|----|------------------------------------------------------------------|
| 1 | 最高 | `purge_blocked_by_legal_hold`（participant 前置 gate 或 coordinator live hold 查询，同 code 双来源） |
| 2 | coordinator-level（新增冻结） | `blocked_registry_changed`（Spec §4.2；registry drift，scheduler 重建触发） |
| 3 | coordinator-level（新增冻结） | `blocked_hold_revision_changed`（hold drift，scheduler 重建触发） |
| 4 | coordinator-level（新增冻结） | `purge_owner_ack_conflict`（completed 逐 owner 五方验证矛盾；与 Spec §9.2 同 code 复用） |
| 5 | | `purge_blocked_by_unresolved_action` |
| 6 | | `purge_blocked_by_conversation_scope_gate` |
| 7 | outcome_unknown 族 | `purge_blocked_by_external_outcome_unknown` / `purge_blocked_by_runtime_outcome_unknown`；**增补（回填自 S5-B-8 第 11 项，事实源 R1-S5-C S5-C-1 输出态 5/6）**：`purge_blocked_by_external_settlement_deadline_expired` / `purge_blocked_by_runtime_settlement_deadline_expired` / `purge_blocked_by_external_adapter_unresolvable` / `purge_blocked_by_runtime_adapter_unresolvable`（同为 level 7，不新增 level） |
| 8 | erase_timeout 族 | `purge_blocked_by_external_erase_timeout` / `purge_blocked_by_runtime_erase_timeout` |
| 9 | adapter_unavailable 族 | `purge_blocked_by_external_adapter_unavailable` / `purge_blocked_by_runtime_adapter_unavailable` |
| 10 | scan_nonzero 族 | `purge_blocked_by_external_ref_scan_nonzero` / `purge_blocked_by_runtime_binding_scan_nonzero` / `purge_blocked_by_transport_scan_nonzero` / `workspace_body_scan_nonzero` / `execution_body_scan_nonzero` |
| 11 | | `purge_owner_unavailable` |
| 12 | fallback | `operator_suppressed` |

注：`operation.failure_code` 值域 = 上表全部 12 层；`checkpoint.reason_code` 值域 = participant 可写部分（1/5-12 层；2/3/4 为 coordinator-level，participant **不得**写）。与 Spec §9.2 API 错误码分层：`blocked_registry_changed` 是 operation.failure_code 值（与 Spec §4.2 命名一致），`purge_registry_changed` 是 §9.2 的 API 层名字；`purge_owner_ack_conflict` 同 code 双用于 §9.2 API 码与 failure_code 值。checkpoint `reason_code` 是逐 owner 精确值（owner-scoped），`operation.failure_code` 是 coordinator 从「blocked checkpoint 集合 + coordinator-level gate」按严重度表算出的聚合值。

#### S5-A-1 写者所有权（冻结）

| 实体 | 写者（目标态） | 状态迁移 | 现状（临时投影） | 移除点 |
|------|--------------|---------|----------------|--------|
| owner checkpoint | participant | 按 owner 族分叉：external/runtime `pending → erasing → blocked/acked`；core/transport 仅 `pending → blocked/acked`（不写 `erasing` checkpoint 态） | 已正确 owner-scoped（`_ack_owner_checkpoint`/`_record_blocked`/`_repair_checkpoint_if_pending` 写 checkpoint） | **保留**（checkpoint 本来就是 participant 写的 owner 事实） |
| owner fence | participant | `active → erasing → erased/blocked`（`blocked → erasing`） | 已正确 owner-scoped（`transition_fence_state`） | **保留** |
| external ledger / runtime binding | participant | `registered → erased/blocked/unknown` | 已正确 owner-scoped | **保留** |
| operation.state / operation.failure_code | **transactional projection coordinator** | `scheduled → running → blocked/completed`（从全 checkpoint 集合聚合） | 三方法临时投影（last-writer-wins） | **移除** `_mark_operation_running`/`_record_blocked`/`_repair_checkpoint_if_pending` 中所有对 `operation.state`/`failure_code`/`started_at`/`revision` 的写 |
| Conversation.purge_state（`running/blocked/failed/completed`）+ `purged_at` | **transactional projection coordinator** | 投影 `operation.state` | 三方法临时投影（transport 基类在三方法内；workspace/execution 在 caller `erase_conversation_body`/`erase_execution_body` 内，见 S5-A-7 ②） | **移除** 六 participant 全部 `conversation.purge_state = running/blocked` 写（含 caller 级，非仅三方法内） |
| Conversation.purge_state（`not_scheduled/scheduled`）+ `purge_revision` | workspace（delete/restore 生命周期） | `not_scheduled ↔ scheduled`（delete/restore） | 已正确 | **保留**（非本契约移除对象） |

**写者增补（回填自 S5-B-8 第 6/10 项，事实源见 R1-S5-B S5-B-2 / R1-S5-C S5-C-7）**：
- **checkpoint 第三写者**：rebuild seeding（一次事务、仅 quiesce 后 rebuild、证据可重验，S5-B-3 阶段 1）——与 participant 写者、coordinator 读者边界按 S5-B-2/S5-B-3 冻结。**coordinator 不写 checkpoint**（derived lineage conflict 只写 operation/Conversation 投影，S5-A-2 G4——不新增第四写者、不新增 `acked→blocked` 转移、不写 checkpoint.reason_code）。
- **settlement fence `erasing→blocked` 写者（4 非 core owner）** + **scheduler settlement 进入点**：对 S4-F「Tx2 不碰 fence」的显式变更，CAS token 与适用范围见 R1-S5-C S5-C-7；core owner 不适用（其 scan-nonzero 落账已写 fence）。

**六 owner × 临时投影方法现状/目标/移除点矩阵（冻结）**：六 owner 中，`workspace.core.v1` / `execution.core.v1` / 四个 transport+external+runtime owner（复用 transport 基类）各自通过 `_mark_operation_running` / `_record_blocked` / `_repair_checkpoint_if_pending` 写 `operation`，并通过 caller（workspace `erase_conversation_body` / execution `erase_execution_body` / transport `erase_transport_owner`）写 `Conversation.purge_state`。目标态：三方法 + caller 退化为**只写 owner-scoped checkpoint/fence/ledger/binding，零 operation/Conversation 写**；`operation`/`Conversation` 聚合写入收敛到 transactional projection coordinator 单一实现。移除点即上述「三方法 + caller」内的共享实体写块（逐方法/逐 caller 在 I2 内删除）。**participant 入口的 `expected_lease_epoch`/`expected_operation_revision`/`purge_revision` 全 fencing token 保留**（participant 仍以 `_load_verified_operation` 锁 operation 行并校验 fencing 后才写 checkpoint/fence——只删共享写，不删 fencing 入参，也不删 operation 行锁）；`_ack_owner_checkpoint` 不写 operation/Conversation，仅需修正 docstring 漂移。

#### S5-A-2 reducer 输入与状态表（冻结）

**输入（固定）**：transactional coordinator 以一次 operation 的**持久化 registry snapshot**（`registry_snapshot` JSONB 列，Spec §4.2「保存排序后的 (owner_key, owner_version, capability_digest) 列表及 registry digest」，决定 owner 全集与顺序）+ **该 operation 的全部 owner checkpoint 行**（`state`/`reason_code`/`attempt`）+ **全部 owner fence 行**（`state`/`owner_version`/`purge_revision`/`ack_digest`/`ingress_checkpoint`/`ingress_digest`）为唯一输入，另校验 `registry_digest`（与已安装 registry 一致）、`hold_revision_snapshot`（与 Conversation 当前 `hold_revision` 一致）、active legal hold（live `has_active_legal_hold` 查询）、最终正文扫描（跨 owner 全零、逐 owner 可归属）。coordinator **不得**以现有 `operation.state`/`failure_code`/`Conversation.purge_state` 值为输入（它们是派生投影，可能已被 participant 临时投影污染）。**输入增补（回填自 S5-B-8 第 2/7 项）**：predecessor 定位 facts + lineage 六项校验结果（**聚合期重验结果**，R1-S5-B S5-B-3 阶段 2——seeding 期校验不产出聚合输入）+ per-owner **`lineage_status`（valid/conflict/not_applicable，携带 owner_key）** 与 **`expected_obligation_kind`（native_pending/inherited_acked/carried_blocked/carried_failed）**（均 derived 非持久，输入公式 = `f(current operation.registry_snapshot, immediate predecessor.registry_snapshot, immediate predecessor checkpoint/fence 的 S5-C terminal fact, fence 原生终态锚点)`——**权威定义见 R1-S5-B S5-B-3 阶段 2，逐字同构**；重启后相同投影）+ S5-C settlement terminal facts（per-owner 输出态/已落账/failed 收敛，rebuild 输入映射见 R1-S5-C S5-C-9）；**RecoveryDescriptor 六字段及历史装配归 scheduler settlement 前置项，不进入本输入集**。

**组合结果真值表（冻结，全函数——任何输入组合都有唯一结果）**：

**gate 层（先于 checkpoint 聚合，按序判定，任一命中即定）**：

| gate | 判定 | operation.state | operation.failure_code | Conversation.purge_state / purged_at |
|------|------|----------------|------------------------|--------------------------------------|
| G1 registry drift | `registry_digest` ≠ 已安装 registry digest | `blocked` | `blocked_registry_changed` | `blocked` / `purged_at` NULL |
| G2 hold drift | `hold_revision_snapshot` < Conversation 当前 `hold_revision` | `blocked` | `blocked_hold_revision_changed` | `blocked` / `purged_at` NULL |
| G3 live active hold | live `has_active_legal_hold` 为真 | `blocked` | `purge_blocked_by_legal_hold` | `blocked` / `purged_at` NULL |
| G4 derived lineage conflict | 任一 snapshot owner 的 `lineage_status=conflict`，或存在 snapshot 外 owner 的 checkpoint 行（视同 conflict；derived，R1-S5-B S5-B-3 阶段 2；含 seeded 缺行） | `blocked` | `purge_owner_ack_conflict` | `blocked` / `purged_at` NULL |

G4 判定**先于 checkpoint 聚合**（先于 completed/running/缺行判断，partial-ACK 状态下即时浮出不被优先级 6 掩蔽）；**checkpoint 保持原 owner 事实零修改（含 acked），coordinator 只写 operation/Conversation 投影**；多 conflict owner 诊断按 owner_key 字典序，`failure_code` 单一。

**checkpoint 聚合层（gate 全过时按优先级 1→7 判定）**：

| 优先级 | 输入条件 | operation.state | operation.failure_code | Conversation.purge_state / purged_at |
|-------|---------|----------------|------------------------|--------------------------------------|
| 1 completed | 全 owner `acked` + 五方验证全过 + 最终扫描全零 | `completed`（`completed_at` 非空） | `None` | `completed` / `purged_at` 非空 |
| 2 五方矛盾 | 全 owner `acked` + **任一 owner 五方验证矛盾（与 scan 结果无关，扫描零/非零均判矛盾）** | `blocked` | `purge_owner_ack_conflict` | `blocked` / `purged_at` NULL |
| 3 scan nonzero | 全 owner `acked` + 五方验证全过 + 最终扫描非零 | `blocked` | 逐 owner 扫描非零结果映射其 scan reason（`workspace_body_scan_nonzero`/`execution_body_scan_nonzero`/`purge_blocked_by_transport_scan_nonzero`/`purge_blocked_by_external_ref_scan_nonzero`/`purge_blocked_by_runtime_binding_scan_nonzero`），severity-max + owner_key 字典序 tie-break | `blocked` / `purged_at` NULL |
| 4 blocked | 任一 checkpoint `blocked` | `blocked`（**不得**被后到 ACK 重开 `running`） | checkpoint `reason_code` severity-max 聚合（见 S5-A-3） | `blocked` / `purged_at` NULL |
| 5 failed | 任一 checkpoint `failed` 且无 `blocked` | `failed`（终态，覆盖禁令） | failed checkpoint 的 `reason_code` severity-max 聚合（全部 NULL → `None`）——**checkpoint=`failed` 由 S5 scheduler slice 产生**（重试预算耗尽时写，`reason_code` = 该 owner 最后一次 blocked reason；不存在 participant 写 failed，三份实现对 failed 一律 raise），coordinator 只读聚合 | `failed` / `purged_at` NULL |
| 6 running | 任一 `pending`/`erasing`，或 snapshot owner **缺** checkpoint 行 | `running`（`started_at` 首次非空） | `None` | `running` / `purged_at` NULL |
| 7 scheduled | **零** checkpoint 行 | `scheduled` | `None` | `scheduled` / `purged_at` NULL |

**优先级唯一裁决（冻结）**：G1 > G2 > G3 > G4 > 1 > 2 > 3 > 4 > 5 > 6 > 7。缺 checkpoint 行的 snapshot owner 按 **`expected_obligation_kind`（derived，S5-B-3 阶段 2 权威公式重算）**处置：`native_pending` 缺行 → 视为 `pending`（绝不 `completed`、绝不因缺行跳过该 owner）；**`inherited_acked` / `carried_blocked` / `carried_failed` 缺行 → `lineage_status=conflict` → G4**（seeded/carry 义务丢失 = 事实漂移，**禁止当 pending 重跑、禁止二次 adapter 调用**）。「零行」与「部分缺行」区分（**均仅限 `native_pending` 期望**）：零行 → `scheduled`；部分缺行 → `running`（经优先级 6）。**补两条全函数边界（冻结）**：snapshot 外 owner 的 checkpoint 行（DB 篡改/遗留）→ `lineage_status=conflict` → G4；优先级 4 blocked 聚合全部 `reason_code` 为 NULL → `operator_suppressed`（fallback，level 12 因此可达）。**derived conflict 可重算性（冻结）**：G4 投影由 `f(current operation.registry_snapshot, immediate predecessor.registry_snapshot, immediate predecessor checkpoint/fence 的 S5-C terminal fact, fence 原生终态锚点)` 确定性重算（**权威定义见 R1-S5-B S5-B-3 阶段 2，逐字同构**），无需新增 schema/持久列；重启后重算得到相同投影。

**关键规则（冻结）**：
- **`unknown` 不是 checkpoint 状态**：external/runtime 的 `outcome_unknown` 由 participant 落为 `checkpoint=blocked` + `reason_code=purge_blocked_by_*_outcome_unknown`（F-2a 五方矩阵已冻结），coordinator 视其为普通 `blocked` 参与聚合（优先级 4）；ledger/binding 行的 `unknown` 是 owner-scoped 行级态，不进 coordinator 输入。**增补（回填自 S5-B-8 第 7/11 项，事实源 R1-S5-C S5-C-1）**：`settlement_deadline_expired` / `adapter_unresolvable` 同为 checkpoint blocked reason（level 7），同按优先级 4 聚合且 **reconcile-only**——不进优先级 4 重开路径、不重开 pending。
- **blocked 单调性**：任一 checkpoint `blocked` 后，**后续任意其他 owner 的 ACK 不得把 operation 重开为 `running`**（六不变量 1）；`blocked → running` 只允许 S5 显式重试（S5 重跑该 owner，六不变量 6 语义分离）这一条路径，且**只限 reason 白名单内**（族 B 封闭，见 S5-A-3）。
- **partial ACK 不得 `completed`**：只要存在任一非 `acked` checkpoint（含 `pending/erasing/blocked/failed`）或任一缺行，coordinator 不得写 `completed`/`purged_at`。
- **`completed` 必要条件逐项冻结（缺一不 completed）**：(a) G1/G2/G3 全过；(b) registry snapshot 内**全部** owner 的 checkpoint 均为 `acked`；(c) 最终正文/ref 扫描全零（Spec §5.2「最后正文扫描为零」，逐 owner 可归属；scan **不是**五方验证分量）；(d) **逐 owner 五方验证（不含 scan，S2 拆分裁决）**：checkpoint=`acked` + fence=`erased` + owner/version 匹配（checkpoint.owner_version == snapshot owner_version；fence.owner_version 匹配已安装 registry）+ **fence.purge_revision 双分支（回填自 S5-B-8 第 1 项，事实源 R1-S5-B S5-B-3）**：native 等值 `fence.purge_revision == operation.purge_revision`，或 inherited 例外 `fence.purge_revision < operation.purge_revision` + lineage 六项全过（二选一，均记入「全 owner acked」；`>` → 矛盾 fail closed）+ `checkpoint.ack_digest == fence.ack_digest` + ingress 证据满足（`fence.ingress_digest == canonical_digest(ingress_checkpoint)`）——**任一矛盾 fail closed（优先级 2，`blocked` + `purge_owner_ack_conflict`，与 scan 结果无关），不得先 completed 再等运维 reconcile**；(e) 无 active legal hold（G3 live 查询 + G2 hold drift 双门禁）。completed 时 `failure_code=None`。
- **终态覆盖禁令**：`cancelled/failed/completed` 是终态，coordinator 不得把终态重开为 `running/blocked`；participant 亦不得写终态（现有 `_repair_checkpoint_if_pending` 已以「终态拒绝修复」守卫，coordinator 须保留并强化为 CAS 层不变量）。

#### S5-A-3 reason 聚合（冻结）

- **严重度表**：见 S5-A-0 reason 全集（12 层，1 最高）。**聚合公式限定为「仅 gate 全过后 checkpoint 聚合层」（S4 分层裁决）**：`failure_code` 取当前 blocked checkpoint 集合各 `reason_code` 的**最高严重度**对应值；**gate 命中时 gate reason 独占 `failure_code`，不参与 severity-max**（gate 优先级覆盖严重度表，严重度表仅用于 checkpoint 聚合层）。多个来源只产生一个 `failure_code`。
- **同严重度 tie-break**：同严重度（如 external/runtime 各 `outcome_unknown`，或 final scan 多 owner 非零）按 **owner_key 字典序**（registry 排序）取最小者。**禁用「先提交者保留」与「最后提交者覆盖」**——即 `_record_blocked` 现「已 blocked 但 reason 变则覆写」的 last-writer-wins 行为必须由 coordinator 的确定性聚合替换。
- **双提交顺序等价**：blocked 事实的提交顺序（owner A 先 block、owner B 后 block，或反之）**不得**改变最终 `failure_code`；`failure_code` 只由「当前 blocked checkpoint 集合 + 严重度表 + owner_key 字典序」决定（六不变量 2/4）。反例矩阵 S5-A-8 行 4/5 锁定。
- **设置/保留/唯一清除者**：
  - **设置**：仅 coordinator（聚合写入 `operation.failure_code`）。
  - **保留**：operation 处于 `blocked` 期间 `failure_code` 保持非空，任何 participant 的 ACK/重放不得清它。
  - **唯一清除者**：仅 coordinator，且仅在两条路径——(a) S5 显式重试：**reason 白名单（冻结，族 B 封闭）**——仅 S5-B-2 已冻结的 reopenable 域（`erase_timeout`/`adapter_unavailable`/scan 族 + pre-window gate 具名域）可重试；**`outcome_unknown`/`settlement_deadline_expired`/`adapter_unresolvable`/`purge_owner_ack_conflict`/dirty-data/G1/G2-blocked 一律禁止 `blocked→running`**（零 adapter 调用、零状态推进）。白名单通过时：仅当被重试 owner 是唯一 blocked owner 时 operation 才 `blocked → running` 且清 `failure_code` 并重跑该 owner；**若另有 owner 仍 blocked，重试不清 `failure_code`、operation 保持 `blocked`，`failure_code` 从剩余 blocked 集合重算**（六不变量 6）。**G1/G2-blocked 不适用显式重试（S6 拆分裁决）——只走 scheduler 以新 `purge_revision` 重建**；(b) 全 owner ACK 后 `completed`（`failure_code=None`）。**participant 永久失去清 `failure_code` 的写权**（`_repair_checkpoint_if_pending` 的 `failure_code=None` 无条件清除删除）。
  - `checkpoint.reason_code` 仍归 participant 逐 owner 写（owner-scoped 精确事实），coordinator 只读不写。

#### S5-A-4 并发与 fencing（冻结）

- **时钟**：scheduler 与 coordinator 一律用 PostgreSQL `clock_timestamp()`（生产裁决不依赖 API/Worker 本机时间；测试可注入 clock）。`started_at/completed_at/next_retry_at/updated_at` 落库时钟，不落应用时钟。
- **reducer 双组件（冻结，架构再裁决）**：S5 聚合拆为两个明确组件——(a) **纯 projection calculator**：只接收规范化 facts（snapshot、checkpoint 集、fence 集、registry/hold/final-scan 结果），按 S5-A-2 全函数返回确定性投影 `(operation.state, failure_code, purge_state, completed/purged 标志)`，**无 I/O、无副作用、可单测**；(b) **transactional projection coordinator**：按下方冻结锁序加载 operation、全部 checkpoint、全部 owner fence、registry/hold/final-scan facts，调用 calculator 后 CAS 落库。二者分文件实现，calculator 不 import repository/session。
- **锁序（coordinator 重验点/CAS 谓词，冻结，S1 拆分裁决）**：coordinator 完整聚合取锁顺序固定为 `Conversation 行锁 FOR UPDATE → operation 行 FOR UPDATE → 全 owner checkpoint FOR UPDATE（按 owner_key 字典序）→ 全 owner fence 只读（按 owner_key 字典序，**不加 FOR UPDATE**）→ 最终扫描 → calculator → CAS 写 operation + Conversation`。**不取 owner advisory lock、fence 不加行锁**。冻结不变量「**Conversation 行锁 = 本 coordination 域全局互斥：任何取 operation/fence/checkpoint 行锁的事务必须先取 Conversation 行锁**」——fence 写全部发生在 participant 取 operation 行锁之后，coordinator 持 operation 行锁期间 fence 读集一致；fence↔operation 的取锁逆序（participant/单 owner 重试为 fence→operation，coordinator 为 operation→fence 只读）因 Conversation 先行互斥而不并发持锁成 AB-BA。Conversation 行锁**必取**：coordinator 写 `purge_state/purged_at`，须与 delete/restore（`soft_delete_after_guard`/`restore_after_guard`）串行；否则锁序 reverse 成 operation→Conversation，与 participant 的 Conversation→operation 形成 AB-BA 死锁，且 restore 可提交 `state=ACTIVE` 却带 `purged_at`。
- **revision 语义（冻结，S5 拆分裁决按代码事实）**：coordinator 的 CAS 基线 = **锁内读到的当前 `operation.revision`/`lease_epoch`**（FOR UPDATE 后的当前值，不用外部传入的 expected 值）；**聚合结果与存储投影元组一致时零写（不 bump revision）**——零写比较集 = 完整投影元组 `(operation.state, operation.failure_code, operation.started_at, operation.completed_at, Conversation.purge_state, Conversation.purged_at)`。零写规则动机 = **保护 Tx1 的 `_mark_operation_running`/`_record_blocked` revision CAS 与编排方逐 entry 记账**；冻结「**每 participant entry 前按当前 operation 行重读 revision**」。仅当计算出的投影与存储值**不同**时才写 + revision+1。
- **一次事务 participant 与 Tx1/Tx2 token 语义（冻结，按代码事实）**：core/transport participant 保持**单事务**（checkpoint/fence/ledger 写与投影写原同事务提交——I2 后同事务只剩 owner-scoped 写）；external/runtime 保持 **Tx1（推进 `erasing` + intent）→ Tx2 双事务协议不变**。**Tx2 精确重验集（冻结）= `purge_revision`/`lease_epoch`/`registry_digest`/`hold_revision_snapshot` + fence 态/`purge_revision` + checkpoint 态/attempt/intent——不含 `operation.revision`**（external/runtime Tx2 的 `_load_verified_operation` 均省略 `expected_revision`，代码事实）。coordinator 零写规则保证 Tx1→Tx2 之间的正常聚合不 bump revision；真实状态变化 bump 发生在 coordinator 持 operation 行锁时（与 Tx2 的行锁互斥串行），Tx2 重验不依赖 revision、不受正常聚合 bump 影响。
- **claim lease**：scheduler 以 bounded claim lease 认领到期 deleted Conversation（`conversation_purge_scheduler`），`lease_epoch` 单调（`operation.lease_epoch >= 0`，CHECK 已锁）。接管/重复 scheduler 只能通过 `lease_epoch` CAS（`expected_lease_epoch`）推进，stale lease 的写被 CAS 拒绝。
- **revision / purge_revision**：`operation.revision` 是 coordinator 写的 CAS token（**仅状态/`failure_code` 真实变化时 +1**）；`Conversation.purge_revision` 是 fencing token（delete/restore/purge 单调推进，旧 purge lease/revision 失效）。
- **registry / hold revision drift**：`registry_digest` 不匹配已安装 registry → G1（`blocked` + `blocked_registry_changed`）；`hold_revision_snapshot` < Conversation 当前 `hold_revision` → G2（`blocked` + `blocked_hold_revision_changed`）。drift 时 coordinator **写冻结的 blocked 结果（不再延期裁决）**，随后由 S5 scheduler 以新 `purge_revision` 重建 operation/owner checkpoint（Spec §4.2；重建动作归 scheduler slice）。
- **一致性快照**：coordinator 聚合前**全部 owner checkpoint 行已存在**（scheduler 先建全 owner checkpoint 再放行任何 participant 进 `erasing`）；snapshot owner 缺 checkpoint 行**且 `expected_obligation_kind=native_pending`** 时按 S5-A-2 优先级 6 视为 `pending`（绝不 `completed`；`inherited_acked`/`carried_*` 期望缺行 → G4，S5-B-3 权威公式）。若 `create_owner_checkpoint` 采用惰性逐 owner 建行，须在聚合前完成，或改「取 operation 行 FOR UPDATE 后 INSERT」——否则 READ COMMITTED 下 `SELECT FOR UPDATE` 不阻并发 INSERT，读到过期 `running` 态。
- **单 owner 重试（S5 重跑该 owner）**：复用 participant 入口，取锁顺序 = `Conversation 行锁 → 该 owner advisory lock → fence FOR UPDATE → operation 行 FOR UPDATE → 其 checkpoint FOR UPDATE`（与 participant 完全一致）。**任何路径不得在持 operation 行锁时反取 owner advisory lock / fence，也不得先取 checkpoint 再取 operation。** 重试的 operation CAS = `(lease_epoch, revision)` 匹配 + `_load_verified_operation` 的 fencing 全集。
- **settlement 例外（回填自 S5-B-8 第 9 项，事实源 R1-S5-C S5-C-2/7，不复制第二套规则）**：drift（G1/G2）下 settlement 通道以 frozen-snapshot 基准校验（六条条件，三条硬绑定 = 旧 operation 仍为 top revision / 精确 attempt·intent·fence token / 禁新 Tx1）；ACK-lost repair 的 `expected_operation_revision` 重基准 = 锁内当前 `operation.revision`。
- **I2 门禁增补（回填自 S5-B-8 第 8 项）**：五份 participant 的 `_load_verified_operation` 补 `operation.purge_revision == conversation.purge_revision` 旧 revision 拒绝门禁（含 `_repair_checkpoint_if_pending`/`_record_blocked`/`_ack_owner_checkpoint`/coordinator CAS）；`workspace.core.v1`/`execution.core.v1` 补 `fence.purge_revision == purge_revision` 门禁（镜像 transport:746）——归 I2 实现。
- **hold_revision 生产者前置（冻结，独立实现 PR I1，先于 I2 合并）**：当前 `create_legal_hold`/release **不推进 `Conversation.hold_revision`**，故 G2 漂移永不触发。I1 冻结内容：**create 与 release 均先取 Conversation 行锁 + 同事务推进 `Conversation.hold_revision`（均 bump）**；I1 验收 re-scope 为 **pre-I2 可测项**：bump 串行化（Conversation 行锁）+ drift 拒绝 in-flight participant entry（现有 `_load_verified_operation` hold 校验可观测）。「hold-create vs completed 拦截」断言归 I2；「release 后 retry 续跑」断言归 scheduler slice。**G1/G2-blocked operation 不可原地重试（S6 拆分裁决）**——S5-A-3 显式重试仅适用于 checkpoint-reason blocked；G1/G2-blocked 只走 scheduler 以新 `purge_revision` 重建，而重建对「fence 已 erased（旧 revision）」owner 的 checkpoint seeding 与五方验证例外**整体移出本契约**，归 scheduler slice 独立契约冻结。I1 落地后 G2 成为可观测 fencing token；I1 落地前 G2 vacuous、G3（live 查询）承担 hold 门禁，且「I1 已合并」是 completed 判定（G3 live 查询无 TOCTOU）的前置。完整 permission/HTTP/CLI API 仍归后续 S5 slice。
- **CAS 谓词** = 锁内当前 `(operation.lease_epoch, operation.revision)` 基线 + state 白名单（终态覆盖禁令）。
- **takeover / 重复 scheduler / participant 重放**：重复 scheduler 经 `lease_epoch` CAS 串行，败者退避；participant 重放（erased-fence replay）只写 owner-scoped checkpoint/fence，**不再**触及 operation/Conversation（S5-A-1 移除后重放天然无跨 owner 副作用）。coordinator 对任意输入幂等：同一 facts 集合重复聚合得到同一 `(state, failure_code)`。

#### S5-A-5 切换与兼容窗口（冻结）

- **无人写窗口禁令**：禁止出现「participant 已停止写共享投影，但 coordinator 尚未接管」的无人写窗口。`operation.state`/`Conversation.purge_state` 在任意时刻都必须有单一写者（先 participant 后 coordinator，二者不可同时写、不可同时缺位；投影短暂陈旧不算缺位，见「coordinator 调用点」）。
- **原子切换单元**：**「transactional projection coordinator + 纯 calculator 接入」与「六 owner 去共享写」必须同一原子实现 PR（I2）**（见 S5-A-6）。二者不可拆为「先停 participant 投影」与「后接 coordinator」两段发布，也不接受「先接 coordinator 仍保留 participant 投影」的双写窗口。
- **coordinator 调用点（冻结）**：coordinator 以**独立事务**在 participant 事务**提交之后**运行——**不嵌套**进 participant 单事务、**不进** external/runtime Tx1/Tx2 协议内部；由编排调用方在每次 participant 入口返回后触发。S5 scheduler 仅增加「定时/claim 触发的全量重算」与「单 owner 重试」，不改此触发点。participant 提交与 coordinator 落库之间投影可能短暂陈旧——**无害**（投影是派生的，coordinator 重算覆盖；正确性不依赖投影新鲜度）。**无人写窗口禁令针对「投影写者缺失」，不针对「投影短暂陈旧」**：I2 后 coordinator 是 operation/Conversation 投影的**唯一写者**，无写者缺失窗口。
- **滚动发布前提（冻结）**：切换安全性依赖「切换时生产无 purge 执行路径在网」（scheduler 未启用、无 in-flight operation、participant 入口仅测试可达）。I2 落地一条测试门禁：**六 participant 的 `erase_*` 入口在生产组合根不可达（仅测试可构造）**；后续 S5 scheduler slice 只能在单写者 coordinator 落地后启用。
- **in-flight operation 重算**：切换时已存在的 in-flight operation（`scheduled/running/blocked`）不迁移、不回填 projection——coordinator 接管后**从 facts（checkpoint/fence/scan）重算** `operation.state`/`failure_code`/`Conversation.purge_state`，覆盖既有临时投影值。checkpoint/fence/ledger 是 source of truth，`operation`/`Conversation` 是派生投影。
- **reconcile/backfill 判定**：**禁止默认假设旧临时投影可信**。不需要 backfill（projection 是派生的，可重算）；需要 reconcile 的是「checkpoint 与 fence/ledger 终态不一致」的既有脏数据（如已 `acked` checkpoint 但 fence 非 `erased`，或 `blocked` checkpoint 但对应 ledger 已 `erased`）——该类 reconcile 归 S5 实现 slice 的运维 API（inspect/retry/reconcile），本契约只冻结「不信任旧投影、一律重算」原则，不实现 reconcile 命令。

#### S5-A-6 实现 PR 拆分（冻结）

- **契约 PR（本 PR）** 与 **实现 PR** 分离。本 PR 净 diff 仅 plan + current-work（纯文档），不改代码/测试/schema/migration 040/041/registry。
- **实现拆分（冻结，TD-092 架构再裁决后）**：
  - **I1（前置实现 PR，先于 I2 合并）**：legal-hold revision fencing producer——create/release 均先取 Conversation 行锁 + 同事务推进 `Conversation.hold_revision`（均 bump）。**I1 验收 re-scope（S6 拆分裁决，pre-I2 可测）**：bump 串行化（Conversation 行锁）+ drift 拒绝 in-flight participant entry（现有 `_load_verified_operation` hold 校验可观测）；「hold-create vs completed 拦截」断言归 I2；「release 后 retry 续跑」断言归 scheduler slice。完整 permission/HTTP/CLI API 仍归后续 S5 slice。
  - **I2（原子实现 PR）**：transactional projection coordinator + 纯 projection calculator + 六 owner 去共享写（移除 participant 全部 operation/Conversation 写 + 修正三处注释漂移）。**三件事同一 PR，保持原子边界**。participant 的 `expected_lease_epoch`/`expected_operation_revision`/`purge_revision` 全 fencing token 保留（只删共享写，见 S5-A-1/S5-A-4）。三处注释漂移：①execution `_ack_owner_checkpoint` docstring「operation 标记 owner ACKed」实为只写 checkpoint；②workspace `_ack_owner_checkpoint` 注释「`_mark_operation_running` 是 failure_code 唯一清除点」实为 `_repair_checkpoint_if_pending` 也清；③execution 聚合写顺序 docstring 与代码不符（`AgentRun → RunEvent → CompatibilityOutput → TurnInput` vs 实际 `AgentRun → CompatibilityOutput → RunEvent → TurnInput`）。
- **保持后续独立 slice（不在 I1/I2 内）**：full S5 scheduler（claim/租约/tenant 限流/指数退避/owner 顺序执行/checkpoint 部分失败重试/registry·hold revision 变化新建 revision 的调度侧动作）、legal hold 数据治理完整 API（permission + purpose + reason code + first decision/CAS 审计 + list）、运维 API（inspect/retry/reconcile）、指标与脱敏日志 pipeline——均按 R1-S5 交付项继续独立 slice。S6（retention clocks / 真实故障矩阵 / 备份恢复）与 C1（总验收）明确排除。

#### S5-A-7 五项延期逐项归属（冻结，禁止「后续处理」含糊）

| # | 延期项（#561 登记） | 归属任务 | 验收方式 |
|---|-------------------|---------|---------|
| ① | `_repair_checkpoint_if_pending` 对共享 `failure_code` 的临时投影风险（erased-fence 重放清他 owner blocked failure_code） | **I2**（六 owner 去共享写） | 移除该方法内 `operation.state/failure_code/started_at/revision` 写 + `conversation.purge_state` 写；反例「erased replay after blocked」落地为失败反例（去共享写后重放不改 operation/Conversation） |
| ② | 六 owner 移除 operation/Conversation 写入 | **I2** | 移除**全部** `operation`/`Conversation.purge_state ∈ {running,blocked}` 写：transport 基类在三方法内（`_mark_operation_running`/`_record_blocked`/`_repair_checkpoint_if_pending`）；workspace 的投影写在 **caller**（`erase_conversation_body`）而非三方法内；execution 的投影写在 **三方法内**（`_mark_operation_running`/`_record_blocked`）+ **caller**（`erase_execution_body`）两处，须一并移除。**mutation-kill 方向（冻结）**：守卫测试断言「participant 擦除全程零 operation/Conversation 写」；变异 = **重新引入共享写**（在任一写点加回 `operation.state=...`/`conversation.purge_state=...`）→ 守卫测试必须变红。`_ack_owner_checkpoint` docstring 漂移同步修正；participant 的 `expected_lease_epoch`/`expected_operation_revision`/`purge_revision` fencing token **保留不动** |
| ③ | S5 aggregation reducer + blocked 单调性 + reason tie-break + completed/failure_code 清除权 | **I2**（coordinator + calculator 本体） | 本契约 S5-A-2 全函数 / S5-A-3 聚合规则 / 五方验证全反例（S5-A-8）落地；`failure_code` 仅 coordinator 写、清仅两条路径；blocked 单调 + tie-break 双顺序等价测试；calculator 纯函数单测（无 I/O） |
| ④ | receipt-lookup-only adapter 的 Tx2 双重外部 I/O 约束 | 后续 S5 运维 slice（I2 不触及 adapter，无条件归后续） | 冻结「receipt-lookup-only 无幂等重放能力时，Tx2 精确重验不得二次调用外部删除」；单 conversation 内 distinct delete==1 由 adapter conformance 测试锁定；跨 conversation 去重对 receipt-lookup-only 由 adapter 层负责（S4-F F-6 已冻结），本契约不做 coordinator 层保证 |
| ⑤ | `_load_registered_refs` 锁序 `ORDER BY`（除非测试证明结果依赖顺序） | **I2**（external participant 去共享写时一并） | 要么给 `_load_registered_refs`（external_ref_erasure_participant.py:292）加确定性 `ORDER BY`，要么补测试证明其结果顺序不影响聚合/锁序正确性；不得留「无 ORDER BY 但静默依赖自然序」 |

#### S5-A-8 反例矩阵（冻结，实现 PR 逐项落地）

| # | 反例 | 触发 | 期望行为 | 判别点 |
|---|------|------|---------|--------|
| 1 | blocked → 另一 owner ACK | owner A `blocked` 后 owner B `acked` | operation 保持 `blocked`，`failure_code` 不变（不重开 `running`） | 断言 `state=blocked` + `failure_code` 未被 B 的 ACK 清/改；变异「后到 ACK 把 operation 重开 running」→红 |
| 2 | ACK → 另一 owner blocked | owner A `acked` 后 owner B `blocked` | operation 由 `running` 转 `blocked`，`failure_code` = B 的 reason | 断言 `state=blocked` + `failure_code`=severity 聚合值；变异「failure_code 取 last-writer-wins（后提交者覆盖）」→红 |
| 3 | erased replay after blocked | owner A `blocked`，owner B fence 已 erased 重放 | B 重放只写 B checkpoint `acked`，**不**重开 `running`、**不**清 `failure_code` | 断言 `state=blocked` + `failure_code` 保留 + B checkpoint `acked`；变异「重放重开 running / 清 failure_code」→红 |
| 4 | 同严重度双顺序 | A/B 各 block 同严重度 reason，提交顺序 A→B vs B→A | 两顺序 `failure_code` 相同（owner_key 字典序取最小） | 参数化双顺序断言 failure_code 相等；变异「先提交者保留」→红 |
| 5 | 不同严重度双顺序 | A block 严重度 8，B block 严重度 1，两顺序 | 两顺序 `failure_code` = 严重度 1（非 last-writer-wins） | 断言取最高严重度，与提交顺序无关；变异「先提交者保留」→红 |
| 6 | core + transport 混合 owner | `workspace.core.v1`（严重度 10 `workspace_body_scan_nonzero`）+ `execution.core.v1`（严重度 5 `purge_blocked_by_unresolved_action`）+ `workspace.transport.v1`（严重度 10 `purge_blocked_by_transport_scan_nonzero`）各 block 不同 reason | 聚合 `failure_code` = `purge_blocked_by_unresolved_action`（severity 5 最高）；同严重度 10 tie-break 变体（仅两 owner）取 owner_key 字典序小者（`workspace.core.v1` < `workspace.transport.v1` → `workspace_body_scan_nonzero`） | 断言聚合值具名 + 逐 owner checkpoint reason 精确 + tie-break 变体；变异「单 owner 聚合误用 last-writer-wins」→红；三份独立实现均被判别（去共享写落地由 S5-A-7 ② mutation-kill 保证） |
| 7 | partial ACK | 部分 owner `acked`、部分 `blocked/pending` | operation 不得 `completed`、`purged_at` NULL | 断言非 completed；变异「partial ACK 判 completed」→红 |
| 8 | 全 owner ACK 正向 completed | 全部 owner `acked` + digest/scan/hold 满足 | operation `completed` + `completed_at` 非空 + `failure_code=NULL` + `purge_state=completed` + `purged_at` 非空 | 正向断言五项 completed 必要条件全满足 + `failure_code IS NULL`；参数化变异「去除任一 completed 必要条件（pending owner / digest mismatch / active hold / scan 非零）→ 断言不写 completed/purged_at → 红」 |
| 9 | stale lease / revision | 旧 `lease_epoch` / 旧 `revision` 重放 coordinator 写 | CAS 拒绝，零写 | 断言 operation 未变；变异跳过 CAS→红 |
| 10 | registry / hold drift | registry digest 或 hold revision 漂移后聚合 | coordinator 写冻结结果：G1 → `blocked` + `blocked_registry_changed`；G2 → `blocked` + `blocked_hold_revision_changed`（不基于旧快照续算）；scheduler 以新 `purge_revision` 重建归 scheduler slice | 断言 `state=blocked` + 对应 coordinator-level failure_code + 零 checkpoint 改动；变异「drift 时静默按旧快照续算」→红 |
| 11 | 重复 scheduler / takeover | 双连接并发 coordinator 写 / stale `lease_epoch` 接管 | coordinator 写以 `(lease_epoch, revision)` CAS 串行，stale 方零写，无 AB-BA | 双连接并发断言单写者 + 锁序；变异「stale 方仍写（去掉 revision 基线）」→红；claim/lease 接管半程 deferred 到 scheduler slice（S5-A-6） |
| 12 | 切换时已有 operation 重算与幂等 | in-flight operation 带污染 projection 交给 coordinator | coordinator 从 facts 重算覆盖 projection；重复聚合幂等 | 断言重算后 `(state,failure_code)` 由 facts 决定 + 幂等；变异「coordinator 信任旧投影不重算」→红 |
| 13 | 全 owner ACK 但最终扫描非零 | 全 checkpoint `acked` 但正文/ref 残留 | operation `blocked` + `failure_code` = scan 族聚合（**不** completed） | 变异「省略最终扫描 gate 直接 completed」→红；断言 `state=blocked` + scan 族 failure_code |
| 14 | S5 重试某 blocked owner，另有 owner 仍 blocked | 严重度最高 owner 被 S5 重试，另一 owner 仍 `blocked` | operation 保持 `blocked`，`failure_code` 从**剩余** blocked 集合重算（非 None、非不变） | 断言重试不清 failure_code、operation 不重开 running、failure_code=剩余 owner reason；变异「重试无条件清 failure_code」→红 |
| 15 | 全 owner ACK + active hold（G3） | 全 checkpoint `acked` 但 live 存在 active hold | operation `blocked` + `failure_code=purge_blocked_by_legal_hold`（**不** completed） | 断言 G3 拦截 completed；变异「completed gate 省略 live hold 查询」→红 |
| 16 | 五方验证矛盾（G-completed 逐 owner） | 全 `acked` 但任一 owner 五方矛盾（fence 非 `erased` / `ack_digest` 不一致 / owner·version 不匹配 / **fence.purge_revision 不匹配（native 路径，回填自 S5-B-8 第 3 项收窄）** / ingress 证据不符；**与 scan 结果无关**） | operation `blocked` + `failure_code=purge_owner_ack_conflict`（**不** completed、不先 completed 再等 reconcile） | 参数化四类矛盾各一；断言 fail closed；变异「矛盾仍判 completed」→红 |
| 17 | failed checkpoint 聚合 | 任一 checkpoint `failed`（scheduler slice 写）且无 `blocked` | operation `failed` + `failure_code` = failed `reason_code` severity-max（全 NULL → `None`） | 断言 `state=failed` + reason 聚合 + 全 NULL 变体；变异「failed 判定为 blocked」→红 |
| 18 | 零 checkpoint 行 | operation 存在但无任何 checkpoint 行 | operation `scheduled` + `failure_code=NULL` + `purge_state=scheduled` | 断言 scheduled；变异「零行判 running/completed」→红 |
| 19 | snapshot owner 缺行 | 部分 owner 有 checkpoint 行、部分缺行 | 缺行视为 `pending` → `running`（绝不 `completed`） | 断言 running + 非 completed；变异「缺行跳过该 owner 判 completed」→红 |
| 20 | snapshot 外 owner 行（G4 载体，derived-conflict 裁决） | checkpoint 行 owner_key 不在 registry snapshot（DB 篡改/遗留） | `lineage_status=conflict` → G4 投影 `blocked` + `purge_owner_ack_conflict`（checkpoint 零修改） | 断言 G4 投影 + checkpoint 零修改；变异「忽略 snapshot 外行」→红 |
| 21 | coordinator × in-flight participant 并发 | coordinator 聚合与 participant/单 owner 重试并发（coordinator fence 只读） | 无 AB-BA（Conversation 全局互斥 + fence 不加行锁）；coordinator 读到一致 fence 集 | 双连接并发断言无死锁 + 一致读集；变异「coordinator fence 加 FOR UPDATE」→红（死锁/超时） |
| 22 | inherited-ACK 正向（回填自 S5-B-8 第 3 项，前向指针 R1-S5-B S5-B-9 行 3） | checkpoint=acked + `fence.purge_revision < operation.purge_revision` + lineage 六项全过 | 计入「全 owner acked」（与 native 同权重），completed 可达 | 断言 completed 可达；变异「inherited ACK 不计入全 acked」→红 |
| 23 | inherited-ACK 负向 / outcome_unknown 不重开（回填自 S5-B-8 第 3/7 项） | lineage 任一失败；或 blocked reason ∈ {`outcome_unknown`, `settlement_deadline_expired`, `adapter_unresolvable`} | lineage 失败 → **G4 derived conflict**（投影 `blocked` + `purge_owner_ack_conflict`，checkpoint 零修改）；3/5/6 reason → 保留 blocked carry，**不得重开 pending、不得二次 adapter 调用** | 断言 G4 投影 / carry + 零重开；变异「3/5/6 重开 pending / 信任 seeded 副本跳过重验」→红 |

> 反例矩阵覆盖 F-2a 六不变量 + 本契约 S5-A-2 全函数/S5-A-3 聚合规则；I2 的测试必须映射到本矩阵（每行一个失败反例 + 变异判别），复用 S4-F 已冻结的注入机制（真实 PostgreSQL、fake adapter 故障注入、双连接 `asyncio.gather`、DB 篡改、跨 tenant/跨 Conversation）。行 10/11 的 scheduler 半程（新 revision 重建、claim/lease 接管）明确 deferred 到 S5 scheduler slice，不在 I2 落地；I1 的 hold race（hold-create vs completed、hold-release vs retry）另由 I1 验收。

#### S5-A-9 三面首轮复审与返修记录（Draft 状态，未 merge）

**首轮三面原始计数（保留不覆盖）**：数据/状态机 P0=0/P1=2/P2=4/P3=1 + 并发/锁序 P0=0/P1=2/P2=3/P3=1 + 测试/运维 P0=0/P1=3/P2=5/P3=3 → **合计 P0=0/P1=7/P2=12/P3=5**（24 findings）。

**根因族（一次返修，9 族）**：①写者归属不完整（`cancelled` restore 写者 + caller 级 `purge_state` 写 + operation.state 三类写者）②reducer 锁序/切换欠定（Conversation 行锁必取 + 一致性快照 + 单 owner 重试锁序 + 生产调用点 + 滚动发布前提）③`hold_revision` 无生产者（completed 条件(d) 空洞 → live `has_active_legal_hold` + 生产者前置）④状态表组合不完备（scan-nonzero 行 + 优先级 + 重试清除语义限定）⑤三份实现事实过度泛化（checkpoint `erasing` 分叉 / `_ack_owner_checkpoint` 细节 / failure_code 值域）⑥registry-changed 命名分层 ⑦反例矩阵判别力（row 6/8/10/11 修复 + 补 row 13/14）⑧注释漂移计数与延期④归属 ⑨文档精度。

**返修**：commit `e7746b1d`（9 根因族一次返修）+ 定向复核后 4 处 P2 精度修正（row 14 标题自相矛盾、S5-A-7 ② execution 投影写位置、S5-A-0 表过度泛化注、completed(d) 残余 TOCTOU 明示）。

**独立定向复核结论**：**PASS——无新 P1，7 项 P1 全清零，24 findings 全 RESOLVED（逐项核对代码/spec，非橡皮图章）**；残余 4 处 P2 已修。未触发 TD-092（返修未引入新 P1）。

**HEAD `2ef4a6c6` 独立广域复核（新增计数，保留不覆盖首轮）**：**P0=0/P1=5/P2=3**。返修后出现新 P1 → **触发 TD-092：停止局部措辞修补，先架构再裁决**（用户裁定 6 项决策，落地为 S5-A-0/S5-A-2/S5-A-3/S5-A-4/S5-A-5/S5-A-6/S5-A-7/S5-A-8 更新）：

1. legal-hold fencing producer 拆为独立前置实现 PR **I1**（create/release 先锁 Conversation + 同事务推进 `hold_revision` + 真实 PG race：hold-create vs completed、hold-release vs retry；完整 API 归后续 slice）。
2. reducer 拆为**纯 projection calculator**（规范化 facts → 确定性投影，无 I/O）+ **transactional projection coordinator**（按冻结锁序加载 operation/全部 checkpoint/全部 fence/registry/hold/final-scan facts → calculator → CAS 落库）。
3. 保留 participant 入口 `expected_lease_epoch`/`expected_operation_revision`/`purge_revision` 全 fencing token（只删共享写）；冻结单事务 participant 与 Tx1/Tx2 token 语义；coordinator revision 用锁内当前值、零写不 bump——其他 owner 正常聚合不得误杀 Tx2。
4. 状态表改**全函数**：G1 registry drift → `blocked_registry_changed`、G2 hold drift → `blocked_hold_revision_changed`、G3 live hold → `purge_blocked_by_legal_hold`、五方矛盾 → `purge_owner_ack_conflict`、final scan nonzero 逐 owner 归属 + tie-break、failed reason 来源、零/缺 checkpoint 唯一结果；coordinator-level reason 不再延期裁决。
5. completed 增加**逐 owner 五方验证**（checkpoint=acked + fence=erased + owner/version/purge_revision 匹配 + ack_digest 一致 + ingress/final-scan 证据）；任一矛盾 fail closed，不 completed-后-reconcile。
6. 实现拆分 **I1 / I2**（I2 = coordinator + calculator + 六 owner 去共享写，保持原子边界）；full scheduler、完整 API、限流/退避、运维入口继续后置。

同步修正：S5-A-5 切换措辞（coordinator 独立事务、不嵌套 participant/Tx1-Tx2、投影陈旧无害、写者缺失才是禁令对象）、S5-A-7 mutation-kill 方向（变异 = 重新引入写 → 守卫变红）、current-work 实际状态。

**全新广域三面复审**：裁决落地后于 commit `883068a2` 执行，**新增计数（保留不覆盖首轮与 2ef4a6c6 轮）**：测试/运维 P0=0/P1=4/P2=4/P3=3 + 数据/状态机 P0=0/P1=4/P2=3/P3=5 + 并发/锁序 P0=0/P1=2/P2=2/P3=2 → **合计 P0=0/P1=10/P2=9/P3=10**（29 findings）。**再次出现新 P1 → 触发 TD-092 二次拆分，停止局部补丁**。去重后 8 个独立 P1：①真值表「全 acked + 扫描非零」无行可匹配（五方验证内嵌 scan 致优先级 2/3 自相矛盾）；②反例矩阵 row 6 severity 违反 12 层域（participant 不得写 2/3/4 层）；③锁序 fence↔operation 逆置（coordinator operation→fence vs participant/重试 fence→operation）；④I1 验收在 I2 前不可落地（completed 无写者）；⑤优先级 5「failed reason 来源是 participant」虚构（无 participant 写 failed）；⑥S5-A-3 聚合公式与 gate 层「任一命中即定」矛盾；⑦Tx2 校验集描述与代码不符（Tx2 不校验 operation.revision）；⑧I1 release-bump + G2 + E-2a 门禁 + 显式重试构成 liveness 死路。二次拆分裁决见 **S5-A-10**。

**二次拆分裁决（TD-092，见 S5-A-10）落地**：本轮不再逐条改词，按风险域拆分——锁序统一（Conversation 全局互斥 + fence 只读）、真值表全函数重构（五方验证去 scan 化）、failed 产生者归 scheduler slice、聚合公式分层、Tx2 token 语义按代码事实、hold 漂移 rebuild 移出本契约、反例矩阵域修正。

**状态**：Draft（拆分后待复核）。按用户指令停在 Draft（不转 Ready、不评分、不合并）；「转 Ready → 评分 → 合并」由用户后续单独指令触发，I1/I2 实现前必须先把本契约 PR 合并为冻结基线。

#### S5-A-10 二次拆分裁决（fresh 广域三面后，TD-092）

**拆分原则**：8 个独立 P1 的共同根因是「一个契约段同时冻结三个耦合风险域（participant 写者/token 语义、coordinator 全函数/聚合、hold 生命周期），跨段规则互相覆盖导致自相矛盾」。本轮不再逐条改词，按风险域拆分冻结边界：

- **S1 锁序统一（P1③）**：冻结「**Conversation 行锁 = 本 coordination 域全局互斥：任何取 operation/fence/checkpoint 行锁的事务必须先取 Conversation 行锁**」。coordinator 读 fence **不加 FOR UPDATE（只读校验）**——fence 写全部发生在 participant 取 operation 行锁之后，coordinator 持 operation 行锁期间 fence 读集一致，且 fence↔operation 逆序不会并发持锁。删除「operation→checkpoint 同序即无 AB-BA」的错误归因；单 owner 重试保持 participant 序（fence→operation）。S5-A-4 锁序 bullet 已按此改写。
- **S2 真值表全函数重构（P1①）**：五方验证**不含 scan**（scan 是独立条件(c)，去五方化后优先级 2/3 互斥且覆盖全集）；all-acked 三分支：五方矛盾（与 scan 无关）→ 优先级 2 `purge_owner_ack_conflict`；五方全过 + scan 非零 → 优先级 3 scan 族聚合；五方全过 + scan 零 → 优先级 1 completed。补两条全函数边界：snapshot 外 owner 的 checkpoint 行 → fail closed（`purge_owner_ack_conflict`）；blocked 聚合全 reason NULL → `operator_suppressed` fallback（level 12 因此可达）。S5-A-2 已按此改写。
- **S3 failed 产生者归 scheduler slice（P1⑤）**：不存在 participant 写 checkpoint=`failed`（三份实现对 failed 一律 raise，failed 只出现在 DB 篡改测试）。冻结：checkpoint=`failed` 由 **S5 scheduler slice** 产生（重试预算耗尽时写），`reason_code` = 该 owner 最后一次 blocked reason；coordinator 只按优先级 5 聚合（全 NULL → `None`）。删除「participant 写 failed」的虚构来源。
- **S4 聚合公式分层（P1⑥）**：S5-A-3 聚合公式限定为「仅 gate 全过后 checkpoint 聚合层」；**gate 命中时 gate reason 独占 failure_code，不参与 severity-max**；gate 优先级覆盖严重度表（严重度表仅用于 checkpoint 聚合层）。删除 vacuous 的「coordinator-level 视为字典序最小键」tie-break 条款。S5-A-3 已按此改写。
- **S5 Tx2 token 语义按代码事实（P1⑦）**：Tx2 实际重验集 = `purge_revision`/`lease_epoch`/`registry_digest`/`hold_revision_snapshot` + fence 态/`purge_revision` + checkpoint 态/attempt/intent，**不含 `operation.revision`**（external/runtime Tx2 的 `_load_verified_operation` 均省略 `expected_revision`）。零写规则保留，动机改写为「保护 Tx1 的 `_mark_operation_running`/`_record_blocked` revision CAS 与编排方逐 entry 记账」；冻结「**每 participant entry 前按当前 operation 行重读 revision**」。S5-A-4 已按此改写。
- **S6 hold 漂移 rebuild 移出本契约（P1⑧④）**：保留用户裁决「I1 create 与 release 均 bump `hold_revision`」不动，但冻结：**G1/G2-blocked operation 不可原地重试**（S5-A-3 显式重试仅适用于 checkpoint-reason blocked）；重建（新 `purge_revision`）对「fence 已 erased（旧 revision）」owner 的 checkpoint seeding 与五方验证例外**整体移出本契约**，归 scheduler slice 独立契约冻结（本 PR 在 scheduler slice 前置契约项登记；**前向指针已落地（回填自 S5-B-8 第 5 项）：R1-S5-B 契约（#564）S5-B-2/S5-B-3**）。I1 验收 re-scope 为 pre-I2 可测：bump 串行化（Conversation 行锁）+ drift 拒绝 in-flight participant entry（现有 `_load_verified_operation` hold 校验可观测）；「hold-create vs completed 拦截」断言归 I2；「release 后 retry 续跑」断言归 scheduler slice。S5-A-6/S5-A-4 已按此改写。
- **S7 反例矩阵域修正与全覆盖（P1②）**：row 6 改用 participant 可写 reason（`execution.core.v1` = severity 5 `purge_blocked_by_unresolved_action`；`workspace.core.v1` vs `workspace.transport.v1` = severity 10 scan 族同严重度 owner_key tie-break）并具名期望 code；补 rows：failed 聚合、零行 scheduled、缺行 running、snapshot 外 owner 行 fail closed、coordinator 与 in-flight participant 并发（fence 只读）；补齐全部行的命名 mutation。S5-A-8 已按此改写。

**拆分后边界**：本契约冻结「participant 去共享写 + coordinator 全函数 + I1 生产者 primitive」三层；**不冻结** scheduler 的 rebuild/seeding、重试预算/选择、claim/限流语义——后者在 scheduler slice 契约 PR 单独冻结，本 PR 仅登记为前置契约项。

> **merged-boundary（2026-08-16，实现 PR #569，squash merge `ac77d563`）**：I2 原子实现已并入 main——纯 projection calculator（S5-A-2 全函数真值表 + state×reason 合法矩阵 + capability 五方校验）+ transactional projection coordinator（Conversation-first 锁序 + operation 三键限定 + 锁内 CAS 六元组零写 + 终态覆盖禁令 + 时间归一化 + 旧 revision 门禁）+ 六 owner participant 去共享投影写（fencing token/operation 行锁/owner-scoped 写全保留；S5-A-6 三处注释漂移修正）。**冻结门禁全落地**：五份 `_load_verified_operation` 旧 revision 拒绝（含 coordinator CAS）+ workspace/execution core erased-fence 跨实例门禁 + create_legal_hold completed 拦截（I1 交接项）+ S5-A-7 ⑤ `_load_registered_refs` ORDER BY + S5-A-5 组合根不可达静态门禁。历史复审计数链见 S5-A-9/10 与 Score Log（首轮 P0=1/P1=7/P2=10/P3=14 → 族 A~N 返修 → 纠偏 P1=4 → 第二轮 P1=2 → TD-092 停止 → 用户裁决收口 → 定向复核 9/9，最终 P0/P1=0）；评分 88（Original，基线 `c6ffab0b`）；I2 专项 95 passed + 22 项 mutation kill + Ready Backend full 2474 passed/1 skipped/4 deselected。**边界**：I2 完成不代表 S5 scheduler 完成——**尚未实现** claim/lease、owner execution、rebuild/seeding、retry/reconcile、settlement integration、完整 legal-hold permission/HTTP/CLI API、S6、C1；「release 后 retry 续跑」断言归 scheduler slice（S5-A-10 S6 re-scope 保持）。follow-up **REQ-047**（R1-S5 implementation conformance：零 checkpoint `scheduled` 生命周期投影写者边界、五份 participant operation 锁查询三键收窄、现存 P2/P3 与 td-032 测试文件拆分；不宣称已修复）。

> **merged-boundary（2026-08-15，实现 PR #567，squash merge `edeabcd0`）**：I1 legal-hold revision fencing producer 已并入 main——`create_legal_hold`/`release_legal_hold` 均 Conversation-first `FOR UPDATE` + 同事务 SQL 侧原子自增 bump `Conversation.hold_revision`（均 bump，S5-A-4/S5-A-10 冻结语义不变）；**G2 hold_revision 生产者从 vacuous 变为可观测**（drift 拒绝 in-flight participant entry，双侧 participant 已接入测试可观测）；release hold 锁谓词 tenant-scoped（`id + tenant_id + conversation_id FOR UPDATE`）经 Ready 前纠偏落地（外租户行锁零等待反例 8d + 裸 id mutation 实杀转红）；评分 90（Original，基线 `3bbcba2b`），最终 P0/P1=0，Backend full 2379 passed。**边界**：仅 producer primitive——**尚未实现** I2（纯 projection calculator + transactional projection coordinator + 六 owner participant 移除 operation/Conversation 临时投影写）、full scheduler、claim/lease、rebuild/retry、完整 legal-hold permission/HTTP/CLI API、S6、C1；「hold-create vs completed 拦截」断言归 I2、「release 后 retry 续跑」断言归 scheduler slice（S5-A-10 S6 re-scope 保持）。REQ-047 / R1-S5 implementation conformance follow-up 保留（I1 并入后续 conformance；时间预算型判别随实现 PR 加固；td-032 拆分计划已登记）。

### R1-S5-B：Purge Revision Rebuild & Evidence Seeding 契约（stacked contract-first）

> Status: Draft（stacked PR，base = `docs/req041-047-r1-s5a-owner-aggregation-contract` @ `efde24e4`，#563 正文不在本 PR 修改。**历史 stacked child**：#564 已 squash 合并入 root #563 @ `bb792547`（评分 87，2026-08-14），尚未进入 main）
> 分支：`docs/req041-047-r1-s5b-rebuild-seeding-contract`
> 仅纯文档（plan + current-work）；不写代码/测试/schema/migration/registry；不启动 I1/I2/S5 实现/S6/C1。
> 本契约是 S5-A-10 S6 拆分裁决移出项（「hold 漂移 rebuild / evidence seeding」）的独立冻结，也是 S5-A-2 五方验证「inherited ACK 例外」的前置契约。
> **架构裁决（Option D：quiesce-and-finalize，TD-092 第二轮）**：首轮「erasing-fence token 迁移 primitive」在重建时机与在途 adapter 窗口之间制造了不可判定的并发窗口。本轮停止逐 finding 补词，改为架构重写：重建前置 quiesce 阶段（等全部 owner 离开 erasing），旧 revision 只保留 settlement-only 通道，**删除 erasing-fence token 迁移 primitive**。adapter 恢复契约（S5-B-7）作为独立 split-out 候选，若广域三面再现新 P1 即拆为 S5-C。

#### S5-B-0 schema/状态机事实对账（冻结）

对账结果（截至 `main@99a3ffac` 与 #563 HEAD 一致，本契约不引入 schema 变更）：

1. **fence 每 conversation/owner 唯一**：`agent_erasure_fences` PK = `(tenant_id, conversation_id, owner_key)`（models.py:603-607）。同一 owner 在任意时刻只有一行 fence，**不存在「新 revision 新 fence 行」的可能**（无 schema 变更下）。
2. **erased fence 为不可逆终态**：`_FENCE_ALLOWED_TRANSITIONS`（erasure_repository.py:96-105）无任何 `erased → *` 边；`transition_fence_state` 显式拒绝。
3. **cross-purge erased-fence ACK repair 已明确拒绝**：transport:746/886、external:438/580/701、runtime:461/601/718 的 `fence.purge_revision != purge_revision` 门禁（S4-F 族 B）——旧 revision 的 erased fence 不能修复/重放为当前 revision 的 ACK。**core owner（`workspace.core.v1`/`execution.core.v1`）缺该门禁**（S5-B-8 接口项 backport）。
4. **operation/checkpoint 按 purge revision 新建**：`agent_conversation_purges` UK `(tenant_id, conversation_id, purge_revision)`（models.py:636-641）；checkpoint UK `(tenant_id, purge_operation_id, owner_key)`（models.py:730-735）。rebuild = 新 operation 行 + 全新 checkpoint 集合。
5. **registry 可表达性**：registry 是 code-defined（`_OWNER_DEFINITIONS`，agent_erasure_registry.py:58-115）；snapshot = 排序 `(owner_key, owner_version, capability_digest)` 列表（:141-150）+ digest（:163）。**owner 新增/移除/version/capability 变化 → `registry_digest` 变化（G1）**；旧 snapshot 与新 snapshot 的逐 owner diff 可**识别具体变化 owner**（added/removed/re-added/version-changed），无需新增 schema。
6. **adapter 窗口线性化点（冻结）**：external/runtime 双事务协议的 **Tx1 commit 是 adapter window 的线性化点**——Tx1 提交「checkpoint → `erasing` + attempt+1 + intent digest」并释放全部锁后，adapter `delete_object`/`destroy_session` 在**无锁上下文**调用（E-2「禁持锁做外部 I/O」），Tx2（第二独立事务，精确重验后写 `erased`+receipt 或 blocked/unknown）收口窗口。`checkpoint.state=erasing` 或 `fence.state=erasing` 是「owner 在窗」的可观测标记；Tx1 commit 前 = 可证明未发送，Tx1 commit 后 = 删除可能已生效。
7. **outcome 三分类（冻结，E-3a 代码事实）**：adapter outcome 已按 E-3a 分三类落账——成功（`ExternalEraseSuccess`/`RuntimeDestroySuccess` → erased）；**可证明未发送**（`NotSentError` → `purge_blocked_by_*_erase_timeout`；`FailedError` → `purge_blocked_by_*_adapter_unavailable`，可重试）；**可能已生效**（`TimeoutError`/`Unknown` → `purge_blocked_by_*_outcome_unknown`，不自动重试）。settlement 必须如实保留三分类，**不得把 outcome_unknown 重写为可重试 blocked/pending**。

#### S5-B-1 Quiesce-and-finalize：rebuild 触发、quiesce 门禁与 settlement 通道（冻结）

**G1/G2 触发（冻结）**：
- **G1**：`operation.registry_digest != 当前已安装 registry digest`（精确等值判断，与 `_load_verified_operation` 的 `!=` 逐字一致）。
- **G2**：`operation.hold_revision_snapshot < conversation.hold_revision`（I1 落地后 hold_revision 有生产者；I1 前 G2 vacuous）。`snapshot > current` 不可能（hold_revision 单调无回退写者），不判，participant 侧 `!=` fail closed 兜底。

**drift 只写投影（冻结）**：G1/G2 命中时 coordinator 只写共享投影 blocked（G1 `blocked_registry_changed` / G2 `blocked_hold_revision_changed`），**不写 checkpoint/fence/ledger/binding**。hold/registry drift **不得抹掉任何已发生的 adapter outcome**——settlement 与 rebuild 都以旧 operation 冻结的事实为准。

**quiesce 门禁（冻结，Option D 核心）**：只要**任一 owner** 的 `checkpoint.state == erasing` 或 `fence.state == erasing`，scheduler **不得**推进 `conversation.purge_revision`、**不得**创建新 operation、**不得**迁移 fence token（erasing-fence token 迁移 primitive 已删除，见 S5-B-4）。旧 operation 保持 immutable blocked（drift `failure_code`），进入 settlement 等待。

**settlement-only 通道（由 S5-C 接管，本 PR 只保留依赖接口）**：settlement-only 通道（Tx2 收口/同 revision crash replay/ACK-lost repair 的路径、精确 token、写域与禁止项）、settlement 事实源与 outcome 落账的**具体裁决已拆出**，由 **R1-S5-C Settlement-only Adapter Recovery 契约**接管冻结（S5-B-11 拆分裁决落地）。本 PR 只保留依赖接口：

> **rebuild 输入必须已满足 S5-C settlement terminal contract**——quiesce 门禁「无 `erasing` checkpoint/fence」即 S5-C settlement terminal contract 的收敛面：每个 owner 必须已落账为 S5-C 输出态之一（success / 可证明未发送 / outcome_unknown / ACK-lost repair / 恢复超时 / adapter 不可解析），或进入 S5-C 定义的具名、可观察、禁止自动重试的 reconcile 状态；任一 owner 未收敛时 rebuild 不得启动。

**quiesce 收敛与 rebuild 触发（冻结）**：全部 owner 满足 S5-C settlement terminal contract 后才允许 rebuild（S5-B-2 矩阵）。settlement 不可达时的显式 reconcile 状态定义归 S5-C；rebuild 对 reconcile/outcome_unknown owner 按 S5-B-2 case A carry 保留 blocked/reconcile，**不以新 revision 二次调用 adapter 掩盖**。

#### S5-B-2 Owner obligation 全函数矩阵（冻结）

输入 = 旧 snapshot owner 集 ⊕ 当前 registry owner 集 + settlement 收敛后的旧 checkpoint/fence 状态。**四条硬约束**：不得静默丢弃旧清除义务；不得把 `outcome_unknown` / `settlement_deadline_expired` / `adapter_unresolvable`（S5-C 输出态 3/5/6）重开 pending；不得按普通新增 owner 建 pending 后撞 terminal fence；**reason 不可判定的 blocked（其他/NULL）不得落入通用 pending 分支**（dirty-data fail closed）。

**quiesce 前置（所有 change 类型通用）**：`checkpoint.state == erasing` 或 `fence.state == erasing` 的行**不进入 rebuild**（quiesce 门禁，settle 后按 settlement 结果重判）。

矩阵三轴 = checkpoint 状态/缺行 × fence 状态 × ownership change（added/removed/re-added/version-changed/unchanged）。逐 change 类型冻结：

**A. unchanged owner**（owner_key 不变，version/capability 不变）：

| checkpoint | fence | rebuild 动作 | 新 checkpoint |
|-----------|-------|-------------|--------------|
| `acked` | `erased` | **合法继承**（S5-B-3 lineage 重验全过） | `acked`（seeded） |
| `acked` | `active`/`blocked` | **矛盾** → fail closed（ack 但 fence 未 erased，S5-B-3 不满足） | — |
| `blocked`（可证明未发送/未清除：`*_erase_timeout`/`*_adapter_unavailable`/scan 族——S5-C 输出态 2） | `active`/`blocked` | 义务重开 | `pending` |
| `blocked`（`outcome_unknown` / `settlement_deadline_expired` / `adapter_unresolvable`——S5-C 输出态 3/5/6） | `active`/`blocked` | **保留 blocked/reconcile，不重开 pending** | `blocked`（carry，reason 保留） |
| `blocked`（pre-window gate reason：`purge_blocked_by_legal_hold`/`purge_blocked_by_unresolved_action`/`purge_blocked_by_conversation_scope_gate`/`purge_owner_unavailable`/`operator_suppressed`——具名域，非 catch-all） | `active`/`blocked` | 义务重开（S5-B-5 hold-release 序列依赖此行为） | `pending` |
| `blocked`（其他未知/NULL reason，不在任何命名域） | `active`/`blocked` | **dirty-data fail closed/reconcile，禁止落入通用 pending 分支** | — |
| `pending` | `active`/`blocked` | 义务重开（保持未完成） | `pending` |
| `pending` | `erased` | **矛盾** → fail closed（pending 但 fence 已 erased） | — |
| `failed` | `active`/`blocked` | 保留 failed（scheduler 重试预算语义，不重开） | `failed`（carry） |
| `failed` | `erased` | **矛盾组合 → dirty-data fail closed**（fence `erased` 证明清除已成功，与 failed 终态矛盾；不得按普通 failed carry 继续 rebuild） | — |
| 缺行 | `active`/`blocked`/`erased` | **fail closed**（旧义务未表达，不得静默丢弃） | — |

**B. added owner**（当前 registry 新增 owner_key，且**无历史 fence 行**）：新义务 → `pending`（owner_version/capability_digest 取当前 registry）。fence 行由 participant 首次写正文时按 registry 建 `active`（Spec §5.1「新正文 writer 在首次写事务中创建缺失 fence」）。

**C. re-added owner**（当前 registry 有 owner_key，且**存在历史 fence 行**）——按「历史 checkpoint 态 × reason_code × fence 态」全函数分派（族 F 收口）：

- 历史 `acked` + fence `erased` + lineage 六项全过 → **定位 fence 证据锚点**（`fence.ack_digest` 原生终态锚点 + `fence.ingress_digest`，见 S5-B-3 lineage 收窄），lineage seed → `acked`（seeded）。**不得按普通新增建 `pending` 后撞 terminal erased fence**；证据锚点缺失/lineage 失败 → **seeding 期失败 = 整事务回滚**（S5-B-3 阶段 1）。
- 历史 `blocked` + fence `active`/`blocked`，reason 为 **reopenable 族**（`erase_timeout`/`adapter_unavailable`/scan 族）或**合法 pre-window gate reason**（legal_hold/unresolved_action/conversation_scope/owner_unavailable/operator_suppressed）→ 义务重开 `pending`（旧未完成清除义务不丢弃）。
- 历史 `blocked` + reason 为 `outcome_unknown`/`settlement_deadline_expired`/`adapter_unresolvable`（S5-C 输出态 3/5/6 terminal facts）→ **blocked carry/reconcile，禁止重开、禁止第二次 adapter 调用**。
- 历史 `failed` + fence 合法非 `erased`（`active`/`blocked`）→ failed carry（scheduler 重试预算语义，不重开）。
- 历史 checkpoint/fence `erasing` → **必须先满足 S5-C settlement terminal contract，不得直接 rebuild**（quiesce 门禁，S5-B-1）。
- unknown/NULL reason、`failed × erased`、锚点缺失或其他矛盾 → **dirty-data fail closed**（seeding 期整事务回滚，交运维证据型流程；禁落入通用 pending 分支）。
- 历史 checkpoint 缺行且 fence 非 erased → 义务重开 `pending`（缺行不视为已完成）。

**D. removed owner**（当前 registry 无 owner_key，旧 snapshot 有）：
- 旧 checkpoint `acked` + fence `erased`（义务已清偿）→ 无 carry-over（不 seed、不记录）。
- 旧义务**未完成**（非 `acked`+`erased`）→ **rebuild fail closed**——不得静默丢弃旧清除义务；新 snapshot 无法表达该 owner（`create_owner_checkpoint` 对 unknown owner fail closed）→ 整个 rebuild 事务回滚，旧 operation 保持 `blocked_registry_changed`，**reconcile-only**（scheduler 不自动重试 rebuild-level fail-closed，防每 claim 周期全事务回滚；交运维证据型 data-governance 流程——恢复 owner 定义或文档化 owner-scope 移除 + 数据治理签字，**不提供「人工清除」绕过**，Spec §9.1/§12.4）。

**E. version-changed owner**（owner_key 不变，`owner_version`/`capability_digest` 变化）：
- 旧 fence `active`（未离开基线）→ 义务重开 + **versioned fence migration**：rebuild 同事务在 owner lock + fence FOR UPDATE 下把 `fence.owner_version` 单调推进到当前 registry 版本（仅 `active` 允许），新 checkpoint = `pending`（新 capability_digest）。
- 旧 fence `erasing`/`blocked`（清除路径上）→ quiesce 后按 settlement 结果分态（**S5-C terminal facts，具名分态——族 F 收口 + 关闭已登记 P2**）：**输出态 2**（可证明未发送）→ 重开 `pending`（新 capability）；**输出态 3**（`outcome_unknown`）→ blocked carry/reconcile 禁重开；**输出态 5**（`settlement_deadline_expired`）→ blocked carry/reconcile 禁重开；**输出态 6**（`adapter_unresolvable`）→ blocked carry/reconcile 禁重开、**禁第二次 adapter 调用**；**输出态 4**（ACK-lost repair，`acked` + fence `erased`）→ 同 erased 分支 fail closed（capability 视图不同，不得 lineage seed）。
- 旧 fence `erased`（旧 capability 下清除已完成）→ **fail closed reconcile-only**——旧 capability 清除结果与新 capability 视图不可互相继承/重跑（S5-B-3 item 4 capability 一致性失败）；versioned-fence 清除路径迁移为**未支持方向**，登记为 scheduler slice 契约后续项。
- 旧 checkpoint `acked` + fence `erased` → 同 erased 分支 fail closed（capability 视图不同，不得 lineage seed）。

**缺行/矛盾兜底（所有 change 类型通用）**：predecessor checkpoint/fence 缺失或矛盾（checkpoint `acked` 但 fence 非 `erased`、digest 不一致、owner_key 不在旧 snapshot）→ **seeding 期失败（S5-B-3 阶段 1）：整个 rebuild 事务回滚**——零新 operation、零新 checkpoint、旧 operation 保持原状（conflict 事实交运维 reconcile）；此阶段**不产生 conflict 事实**（无新行可承载；conflict 仅存在于聚合期 derived `lineage_status`，S5-B-3 阶段 2）。

#### S5-B-3 Evidence inheritance 模型（冻结：schema-free predecessor lineage，结论收窄）

**方向选择（三选一，已裁决）**：采用 **schema-free predecessor evidence lineage**（不新增 provenance 列/schema）。理由：(a) S5-A-0 已冻结「无契约依据不新增 schema/migration」且 040/041 之后无新迁移依据；(b) predecessor 链可由既有行唯一定位；(c) 合法继承由**每次聚合时的 lineage 重验**证明，不依赖行内 provenance。

**lineage 结论收窄（第二轮 P1，冻结）**：信任判定**只锚定 `fence.ack_digest`（原生终态锚点）**——它是 participant 在 owner ACK 时写于 fence 行的清除结果（Spec §5.1「ack_digest/acked_at：owner 清除结果；仅 `erased` 可有」），有 fence 状态机终态背书。**`checkpoint_digest` 没有 fence 锚点**：它是 checkpoint 行的本地字段（erasing 时为 intent digest、acked 时为 final scan digest，S4-F 三形式），**仅作审计副本，不参与信任判定**。本契约**不把 checkpoint_digest 纳入 lineage 信任输入**；若未来要参与判定，须补 fence↔checkpoint 的锚定方案（不在本契约内）。

**继承证据六项（冻结，缺一不可）**：

1. **predecessor 唯一定位**：predecessor operation = 同一 `(tenant_id, conversation_id)` 下 `purge_revision` = **MAX(所有 < 当前 revision 的 operation 行的 purge_revision)** 的行；且 `state=blocked` 且 `failure_code ∈ {blocked_registry_changed, blocked_hold_revision_changed}`（rebuild 只从 G1/G2-blocked 出发）。**前置顺序冻结**：rebuild 前必须已完成「drift 检测 → coordinator 聚合写 G1/G2 blocked → quiesce → 全部 owner 离开 erasing」；定位无行或状态不符分两类——predecessor 存在但尚未被 coordinator 写 blocked（gate 未跑）→ **retryable-pending-gate**（等 coordinator 聚合后重试，非 reconcile）；状态为 cancelled/其他 → fail closed。
2. **predecessor checkpoint=`acked`**（同一 owner_key）。
3. **fence=`erased`**（同一 owner_key；PK 保证唯一行）。
4. **owner identity/version/capability 一致**：fence.owner_version == predecessor checkpoint.owner_version == 当前 registry owner_version；predecessor checkpoint.capability_digest == 当前 capability_digest。
5. **信任锚点一致**：新 checkpoint（seeded）的 `ack_digest == predecessor.ack_digest == fence.ack_digest`（唯一信任锚点）；`fence.ingress_digest == canonical_digest(fence.ingress_checkpoint)`。`checkpoint_digest` 仅作审计副本复制，**不参与信任判定**。
6. **inherited ACK 识别**：新 operation 下 `checkpoint=acked` 且 `fence.purge_revision < operation.purge_revision` → 按继承路径处理（跑 lineage 重验）；`fence.purge_revision == operation.purge_revision` → native 路径（S5-A 五方）；`fence.purge_revision > operation.purge_revision` → 矛盾 → fail closed。

**合法继承 vs 伪造 ACK（族 E 收口：seeding 与 aggregation 分阶段，消除「同一 lineage 失败既回滚又 owner blocked」双值语义）**：

- **阶段 1——seeding（rebuild 事务内，提交前）**：rebuild/seeding 事务在**新 operation/checkpoint 提交前**验证 predecessor 唯一定位与前置顺序（六项 1）、checkpoint=`acked`（六项 2）、fence 原生锚点 `erased` + `ack_digest`（六项 3）、owner identity/version/capability 一致（六项 4）、信任锚点一致（六项 5）。任一验证失败 → **整个 rebuild 事务回滚**：零新 operation、零新 checkpoint、旧 operation 保持原状；此阶段**不产生 conflict 事实**（冲突事实随回滚消失，无新行可承载；conflict 仅存在于聚合期 derived `lineage_status`，见阶段 2）。
- **阶段 2——aggregation（seeding 已合法提交后，derived lineage conflict 架构裁决）**：coordinator **每次聚合都重新读取 predecessor + fence 并重验 lineage**（重读 predecessor operation/checkpoint 行 + fence 行，**不信任新 checkpoint 的 digest 副本**——seeding 只是物化派生事实的优化，事实源永远是 predecessor + fence）。**seeding 提交后**出现的缺失、篡改或事实漂移 → **per-owner `lineage_status = conflict`（derived normalized fact，不是 checkpoint 状态）**——coordinator 经 derived conflict gate（S5-A-2 G4）只写 operation/Conversation 投影（`blocked` + `purge_owner_ack_conflict`），**checkpoint 保持原 owner 事实零修改（含 acked）**；**不得回滚已提交的新 operation**（回滚只属于阶段 1）。
  - **`lineage_status` 三值（冻结）**：`valid`（lineage 六项重验全过）/ `conflict`（重验失败、predecessor 缺失或矛盾、seeded 缺行、snapshot 外 owner 行）/ `not_applicable`（无继承义务：native pending/重开/新增 owner 等非继承路径）。携带 owner_key，**derived 非持久**——由 operation snapshot + immediate predecessor + predecessor checkpoint + fence 原生锚点确定性重算，**无需新增 schema 或持久列，重启后必须得到相同投影**。
  - **`expected_obligation_kind` 权威公式（冻结，终结批次——本处为唯一权威定义，其余位置只引用不复制）**：
    `expected_obligation_kind = f(current operation.registry_snapshot, immediate predecessor.registry_snapshot, immediate predecessor checkpoint/fence 的 S5-C terminal fact, fence 原生终态锚点)`
    - **registry diff = diff(predecessor.registry_snapshot, current operation.registry_snapshot)**——两端均为**持久快照**，**不得使用 live installed registry**；live registry drift 只由 G1 处理，**不得改变同一 operation 的 derived 结果**（同一 operation 重算必须得到相同 kind）。
    - **S5-C terminal fact 必须来自 immediate predecessor 已 settlement 的 checkpoint/fence 持久事实**，**不得读取当前待判定 checkpoint**；删除当前 seeded checkpoint 后 expected kind 仍须完整可重算——**禁止「用缺失行推导该行应否存在」的循环**。
    - **current checkpoint 仅用于比较「实际值是否符合 expected kind」**，不参与 expected kind 自身推导。
    - 四值映射：`native_pending` / `inherited_acked` / `carried_blocked` / `carried_failed`（族 C，S5-A-2 优先级唯一裁决消费）。
  - **多 conflict owner 诊断顺序（冻结）**：按 **owner_key 字典序**报告首个 conflict owner；`failure_code` 始终为单一 `purge_owner_ack_conflict`（不聚合多值）。
- **阶段 2 读集一致性（冻结，族 D 收口）**：coordinator 聚合在 **Conversation 行锁 FOR UPDATE 期间**读取 predecessor operation/checkpoint 行与 fence 行——该窗口内这些行的**全部合法写者都被同一首锁串行**（S5-A-4 S1 不变量），且 predecessor 已非 top revision（`operation.purge_revision == conversation.purge_revision` 门禁拒绝 participant 对其一切写，S5-A-4 I2 门禁增补），故 predecessor 行与 fence 行在该窗口**只读、不加 FOR UPDATE 是成立的**（S5-B-8 item 4）。写者清单（冻结，任一写者绕过 Conversation 首锁即契约失败）：六 owner participant erase 入口（workspace/execution core 与 transport 基类 4 owner，均 Conversation FOR UPDATE 先行——external:408/681、transport:700、runtime:387、workspace:319、execution:404）；settlement 三进入点（live Tx2 / takeover replay / scheduler settlement，S5-C-7 锁序表）；rebuild/seeding 事务（S5-B-6）；coordinator 聚合（S5-A-4）；hold create/release（I1）；delete/restore 生命周期写（`soft_delete_after_guard`/`restore_after_guard`）。
- **双值语义消除（冻结）**：同一 lineage 失败事实按**所处阶段**唯一裁决——提交前 = 整事务回滚（阶段 1）；提交后 = owner conflict blocked（阶段 2）；不存在「既回滚又写 owner blocked」的组合。

**禁令**：不得只复制 `ack_digest` 冒充新 revision ACK（复制只是物化，证明必须重验）；不得在 rebuild 事务外单独写 seeded checkpoint；不得把 `checkpoint_digest` 当作信任锚点参与 lineage 判定。

#### S5-B-4 Fence 与新 revision 的关系（冻结）

- **普通 ACK 严格等值**：native 路径保持 S5-A 五方 `fence.purge_revision == operation.purge_revision`（不变）。
- **inherited ACK 受限例外**：仅当 `fence.purge_revision < operation.purge_revision` **且** S5-B-3 六项 lineage 全过——继承有效性由 lineage 证明，fence 行本身零修改（不推进 fence.purge_revision 到新 revision）。
- **changed owner version 的 versioned fence migration**：仅 S5-B-2 case E（`active` fence）允许同事务单调推进 `fence.owner_version`；`erasing/blocked/erased` 一律按 S5-B-2 case E 处理（fail closed 或 quiesce 后分态）。
- **erasing-fence token 迁移 primitive 已删除（Option D）**：不再存在「rebuild 同事务单调推进 `fence.purge_revision`」的 primitive。`erasing` fence 一律由 quiesce 门禁挡在 rebuild 之外，经 settlement 收口（R1-S5-C settlement terminal contract）后才进入 rebuild 矩阵；永久不可达 → 显式 reconcile（S5-C 输出态，见 S5-B-1）。
- **禁令**：不得重开 erased fence、不得覆盖旧 ack、不得重新开放 writer（fence 状态机无 `erased → *` 边与 `* → active` 边，本契约不新增任何例外）。

#### S5-B-5 Hold create/release liveness（冻结）

- **create 与 release 均 bump hold_revision 保持**（I1 裁决不动）。
- **完整状态序列**：purge 进行中 create hold → hold_revision bump → G2 命中 → 旧 operation immutable blocked（`blocked_hold_revision_changed`）→ **quiesce（等在途 erasing owner settle）** → release hold → hold_revision 再 bump → rebuild（新 revision + 新 snapshot 载当前 hold_revision + seeding）→ 正常执行/重开义务。
- **无无限 revision loop**：每次 rebuild 严格推进 `purge_revision` 并消费「本次 rebuild 所基于的 drift」（新 snapshot 载当前 hold_revision）；只有**新**的 hold 变化才产生新 drift；连续 create/release 各自最多触发一次 rebuild（每个 hold 变化事件至多一次），loop 上界 = hold 变化次数，不因 rebuild 自身产生新 drift。
- **串行点**：hold create/release（I1）与 rebuild 均以 **Conversation 行锁**为第一锁——rebuild 事务内读取 hold_revision 与 bump purge_revision 同锁提交，hold 变化要么在 rebuild 前（计入新 snapshot）、要么在 rebuild 后（产生新 drift），不存在「rebuild 半程 hold 变化」的撕裂读。
- **active hold 期间 rebuild 延迟（保持）**：G3（live active hold）存在时 rebuild 延迟（不 eager 重建——否则产生「全 pending 新 op 被 G3 block、release 后再 rebuild」的中间态）；release 后（G3 消解）再 rebuild，序列保持「每个 hold 变化至多一次 rebuild」。**quiesce 与 G3 延迟独立叠加**：即使 G3 消解，若仍有 owner 在 erasing，仍须 quiesce（二者是正交门禁）。

#### S5-B-6 并发与幂等（冻结）

- **revision 分配**：只在 Conversation 行锁内分配（唯一分配器）；双 scheduler 并发 rebuild 由 Conversation 行锁串行，第二个进入者看到 drift 已消费 → 幂等返回既有 rebuild，**只产生一个新 revision**。
- **rebuild 创建路径 DELETED 门禁（第二轮 P1，冻结）**：rebuild 创建新 operation 的路径**在 Conversation 行锁内强制 `conversation.state == DELETED`**；restore interleave（trigger 与执行之间 restore 落库，`state=ACTIVE`）→ **零新行 no-op**（不建孤儿 operation），不只靠 discriminator 事后补救。
- **锁序**：rebuild = `Conversation 行锁 FOR UPDATE → 校验 conversation.state == DELETED → 读旧 operation（FOR UPDATE）→ 新 operation INSERT → 全 checkpoint INSERT/seed（含 case E 的 owner lock + fence FOR UPDATE）`；不触碰 participant 的 owner advisory→fence→operation 序（新 operation 尚未被 participant 触及，无 AB-BA）。
- **quiesce 判定锁序**：quiesce 门禁判定（扫描是否存在 `erasing` checkpoint/fence）在 Conversation 行锁下进行，与 rebuild 同锁串行——settlement 的 Tx2/crash replay 持 owner lock + fence FOR UPDATE + operation FOR UPDATE 写 owner-scoped 事实，与 rebuild 的 Conversation 行锁互斥，不存在「rebuild 半程某 owner 仍在 erasing」的撕裂读。
- **crash/rollback**：单事务 → 不留半套 checkpoint（旧 operation 完整保留，可重放）。
- **相同 drift 重放（锁内判别）**：幂等判别在 **Conversation 行锁内**评估，命中条件 = `purge_revision == conversation.purge_revision`（当前 top）+ `hold_revision_snapshot == 当前 hold_revision` + `registry_digest == 当前 digest` + `state != cancelled` + `conversation.state == DELETED`，且 predecessor 锁内重验仍为 max-revision 且 G1/G2-blocked → 幂等返回该 operation（同一 rebuild 结果），不重复建。restore interleave → 零新行幂等 no-op（见 DELETED 门禁）。
- **settlement 幂等（由 S5-C 契约承担，本 PR 不重复冻结机制）**：settlement 幂等由 S5-C 冻结的 descriptor/token 重验、lookup/replay 规则与 fence/checkpoint CAS 单写收敛承担（S5-C-5/6/7）；本 PR 只消费 S5-C settlement terminal facts（S5-B-2 映射）。
- **rebuild 期间 registry/hold 再变化**：registry digest 变化（部署）→ rebuild 事务内 G1 校验失败 fail closed（不落库）；hold 变化 → Conversation 锁串行（见 S5-B-5）。

#### S5-B-7 Settlement-only adapter 恢复契约（已拆出 → R1-S5-C）

> 本小节原冻结 settlement（Tx2/crash replay）对 adapter 恢复行为的边界（协议语义修正、idempotent replay 自动恢复承诺、receipt-lookup-only、双支持优先 lookup、settlement 衔接）。第三轮广域三面后按任务指令**停止扩大 #564**，承载族 A/B/C/D/G/H/I 七族 P1 的具体裁决整体拆出，由 **R1-S5-C Settlement-only Adapter Recovery 契约**（独立 contract-first PR）接管冻结（S5-B-11 拆分裁决落地）。本 PR 只保留依赖接口：**rebuild 输入必须已满足 S5-C settlement terminal contract**（见 S5-B-1）；族 G 的 merged 代码事实源（external/runtime adapter Protocol docstring）回填归属亦随 S5-C 登记。

#### S5-B-8 与 S5-A/I2 的接口（冻结，八项 + S5-C 增补第 9/10/11 项；11 项已随 #564 squash 合并回填 root #563 @ bb792547）

**coordinator/calculator 输入的 normalized facts（冻结，六种）**：

1. **native ACK**：`checkpoint=acked` + `fence.purge_revision == operation.purge_revision` + S5-A 五方（去 scan 化）全过。
2. **inherited ACK**：`checkpoint=acked` + `fence.purge_revision < operation.purge_revision` + S5-B-3 六项 lineage 全过——与 native ACK 同权重（计入「全 owner acked」），但五方验证中 fence.purge_revision 条件由等值放宽为「native 等值 / inherited 小于+lineage 二选一」。
3. **pending obligation**：未完成 owner（新增 owner、重开、未完成 carry-over、可证明未发送重开）。
4. **unresolved/unsupported obligation**：removed-owner-unfinished、version-changed-on-purge-path、re-added 证据锚点缺失——**不产出**（rebuild 已在 S5-B-2 case D/E/C fail closed，不存在携带未决义务的新 operation）。
5. **conflict（derived lineage conflict 架构裁决）**：**aggregation 期（S5-B-3 阶段 2）** lineage 重验失败 / predecessor 缺失或矛盾 / seeded 缺行 / snapshot 外 owner 行 → **per-owner `lineage_status=conflict`（derived normalized fact，非 checkpoint 状态）** → derived conflict gate（S5-A-2 G4，先于 checkpoint 聚合、先于 completed/running/缺行判断）→ coordinator 只写 operation/Conversation 投影（`blocked` + `purge_owner_ack_conflict`）；**checkpoint 保持原 owner 事实零修改（含 acked）**——不新增 checkpoint 写者、不新增 `acked→blocked` 转移、coordinator 不写 checkpoint.reason_code（level-4 值域豁免要求已删除）。seeding 期（阶段 1）失败不产生 conflict 事实（整事务回滚，S5-B-2 兜底）。
6. **failed obligation**：checkpoint=`failed`（scheduler 重试预算耗尽写）→ 按 S5-A-2 优先级 5 聚合（reason = 该 owner 最后一次 blocked reason）。

**S5-A 需调整清单（八项 + S5-C 增补第 9/10/11 项；**本轮已逐项回填进本分支继承的 S5-A 正文**——S5-A-0/1/2/4/8/10 各点带精确前向/反向引用（`回填自 S5-B-8 第 N 项`），#563 分支保持 `efde24e4` 不动，随本 PR 合并后生效）**：

1. S5-A-2 五方验证 fence.purge_revision 条件改双分支（native 等值 / inherited 小于 + lineage 重验）。
2. calculator 输入增加 predecessor 定位 facts + lineage 六项校验结果 + **per-owner `lineage_status` / `expected_obligation_kind`**（derived，输入公式 = `f(current operation.registry_snapshot, immediate predecessor.registry_snapshot, immediate predecessor checkpoint/fence 的 S5-C terminal fact, fence 原生终态锚点)`——权威定义见 S5-B-3 阶段 2，逐字同构） + **S5-C settlement terminal facts**（per-owner 收敛结果，按 S5-C-9 重建输入映射表消费——「settlement outcome 三分类」旧表述废弃，由 S5-C 六输出态/已落账/failed 收敛替代）。**RecoveryDescriptor 六字段及历史装配归 scheduler slice 前置项（settlement 路径专用消费），不得登记为 reducer/calculator 输入**。
3. S5-A-8 反例矩阵**改行非补行**：row 16 的 purge_revision 不匹配参数化**收窄为 native 路径**；补 inherited-ACK 正/负行、forged-lineage 变异、outcome_unknown 不重开 pending 行（**前向指针**：本契约 S5-B-9 反例矩阵对应行）。
4. S5-A-4 锁序不变（coordinator 读 fence 与 predecessor 均只读，不加 FOR UPDATE；**读集一致论证见 R1-S5-B S5-B-3 阶段 2（族 D）**）；settlement-only 通道锁序归属（Tx2/crash replay 保持 participant 序 fence→operation，禁新 Tx1）随 settlement 契约**移入 S5-C**（S5-C 并发与写者节）。
5. S5-A-10 S6「移出项」回填指向本契约（S5-B）——**前向指针**。
6. S5-A-1 写者表补新写者例外：rebuild seeding 是 **checkpoint 第三写者**（一次事务、仅 quiesce 后 rebuild、证据可重验）；**删除**原「scheduler 的 erasing-fence token 迁移是 fence 受限新写者」条目（Option D 已删该 primitive）。
7. S5-A-2 补 **derived lineage conflict gate（G4，先于 checkpoint 聚合）** + per-owner `lineage_status`/`expected_obligation_kind` derived 输入（derived lineage conflict 架构裁决，S5-B-3 阶段 2）；`outcome_unknown`/`settlement_deadline_expired`/`adapter_unresolvable` 归 reconcile-only（**不进显式重试白名单、不进重开路径，不重开 pending**）。
8. **旧 revision settlement 门禁 + core owner family-B backport**（均归 I2）：五份 participant 的 `_load_verified_operation` 补 `operation.purge_revision == conversation.purge_revision` 门禁（旧 revision 拒绝一切写，含 `_repair_checkpoint_if_pending`/`_record_blocked`/`_ack_owner_checkpoint`/coordinator CAS）；`workspace.core.v1`/`execution.core.v1` 补 `fence.purge_revision == purge_revision` 门禁（镜像 transport:746，S5-B-0 item 3）。
9. **S5-C 增补（随 #565 落地）**：S5-A-4 Tx2 重验集在 drift 下的 settlement 例外——frozen-snapshot 基准（S5-C-2 六条校验条件，三条硬绑定 = 旧 operation 仍为 top revision / 精确 attempt·intent·fence token / 禁新 Tx1）；含 S5-C-7 ACK-lost repair 的 revision 重基准（= 锁内当前 `operation.revision`）。
10. **S5-C 增补（随 #565 落地）**：S5-A-1 写者表补「settlement fence `erasing→blocked` 写者（4 非 core owner）+ scheduler settlement 进入点」。
11. **S5-C 增补（随 #565 落地）**：S5-A-0 reason 值域 level 7 内新增 4 个 code——`purge_blocked_by_*_settlement_deadline_expired` / `purge_blocked_by_*_adapter_unresolvable`（external/runtime 各一，S5-C-1 输出态 5/6）。

#### S5-B-9 反例矩阵（冻结，scheduler slice 实现 PR 逐项落地）

| # | 反例 | 触发 | 期望行为 | 判别点 |
|---|------|------|---------|--------|
| 1 | hold create→quiesce→release→rebuild 全序列 | purge 中 create hold → G2 blocked → 在途 erasing settle → release → rebuild | 旧 op immutable blocked；在途 owner settle 后新 op `scheduled` + 新 revision + snapshot 载当前 hold_revision；循环终止（每个 hold 变化至多一次 rebuild） | 断言序列终态 + 无重复 rebuild + settlement 在 rebuild 前；变异「release 后原地重试旧 op」→红 |
| 2 | partial ACK 后 rebuild | 部分 owner erased/acked、部分 blocked，G2 触发 rebuild（quiesce 后） | acked/erased owner 继承 seed；可证明未发送 blocked 重开 `pending`；outcome_unknown 保留 blocked；partial 不 completed | 断言新 checkpoint 集合逐 owner 正确 + unknown 未被重开；变异「未完成 owner 被 seed 为 acked / unknown 被重开 pending」→红 |
| 3 | unchanged erased owner 合法继承 | 旧 op 该 owner checkpoint=acked + fence=erased + digests 一致 | 新 checkpoint=`acked` + 继承证据；fence 零修改（purge_revision 仍为旧值）；coordinator lineage 重验通过 | 断言 seeded 行 + fence 未动 + lineage 六项全过；变异「只复制 ack_digest 不重验 lineage」→红 |
| 4 | forged/mismatched predecessor evidence（seeding 期，阶段 1） | 新 checkpoint 拟 seed 但 predecessor checkpoint 非 acked / digest 不一致 / 无 predecessor | **整事务回滚：零新 operation、零新 checkpoint、旧 operation 原状**（不产生 conflict checkpoint） | 参数化三类伪造断言零新行 + 旧 operation 不变；变异「seeding 期失败仍写 owner conflict checkpoint」→红 |
| 5 | 新 owner pending | registry 新增 owner（无历史 fence）后 rebuild | 新 owner checkpoint=`pending`（新义务不丢失） | 断言新 owner 行存在且 pending；变异「只取旧 snapshot owner 集」→红 |
| 6 | removed unresolved owner 不得丢失 | registry 移除 owner 且旧义务未完成，rebuild | rebuild fail closed（事务回滚，旧 op 保持 blocked_registry_changed，零新行） | 断言零新行 + 旧 op 不变；变异「跳过 removed owner 继续 rebuild」→红 |
| 7 | version/capability change | case E：active fence vs purge-path/erased fence | active：fence.owner_version 单调推进 + checkpoint pending；erased：rebuild fail closed | 双分支断言；变异「purge-path/erased fence 也被 version bump 或 lineage seed」→红 |
| 8 | duplicate concurrent rebuild | 双 scheduler 同 drift 并发 rebuild | Conversation 行锁串行，只产生一个新 revision；后到者幂等返回既有 rebuild | 双连接并发断言新 op 唯一；变异「不幂等重复建」→红 |
| 9 | crash during seeding | rebuild 事务中途崩溃/回滚 | 零半套 checkpoint（旧 op 完整保留），重放得同一结果 | 崩溃注入断言无新行残留；变异「分批提交 seed」→红 |
| 10 | rebuild 后 coordinator 正向 completed | 继承 seed + 未完成 owner 重跑全 ACK + scan 零 | coordinator 按 S5-B-8 normalized facts 判 `completed` | 正向断言 completed + purged_at；变异「inherited ACK 不计入全 acked」→红 |
| 11 | drift 再次发生 | rebuild 提交后 registry/hold 再次变化 | 旧新 op immutable blocked + 又一次 rebuild（新 revision） | 断言二次 rebuild 链正确；变异「对已 superseded op 继续写」→红 |
| 12 | cross-tenant/cross-conversation predecessor 伪造 | 用 tenant B 的 predecessor 证据 seed tenant A 的新 op | lineage 定位按同 (tenant, conversation) 强制，跨域伪造 fail closed | 断言拒绝 + 零写；变异「lineage 定位去掉 tenant 维度」→红 |
| 13 | quiesce 门禁（erasing 挡 rebuild） | G2 命中时某 owner checkpoint/fence 仍 `erasing` | scheduler 不推进 purge_revision、不建新 op、不迁移 fence token；erasing owner 走 settlement | 断言无新 op + fence.purge_revision 未变 + settlement 后 rebuild；变异「erasing 未 settle 即 rebuild / 迁移 fence token」→红 |
| 14 | settlement-only 通道（禁新 Tx1 / 禁投影写） | **→ 移入 S5-C 反例矩阵**（本 PR 只保留编号占位与归属；settlement 通道与 drift 绕过反例见 R1-S5-C） | — | — |
| 15 | outcome_unknown 不重开 pending | settlement 落 blocked + outcome_unknown，rebuild | 保留 blocked/reconcile，不重开 pending，不以新 revision 二次调用 adapter | 断言新 checkpoint blocked（carry）+ 无二次 adapter 调用；变异「unknown 重开 pending / 二次 delete」→红 |
| 16 | re-added erased fence 证据锚点 | registry 移除后 re-added，历史 fence=erased | 定位 fence.ack_digest 原生锚点 → lineage seed acked；不建 pending 撞 terminal fence | 断言 seeded acked + 锚点定位；变异「按新增建 pending」→红；锚点缺失 → seeding 期整事务回滚（阶段 1） |
| 17 | active hold 期间不 eager rebuild | G2 命中且 hold 仍 active | rebuild 延迟（不产生全 pending 中间 op）；release 后一次 rebuild | 断言序列无中间 op；变异「active hold 期间 eager rebuild」→红 |
| 18 | restore interleave 零新行 | rebuild trigger 与执行之间 restore 落库 | Conversation 行锁内 `conversation.state==DELETED` 强制：零新行 no-op（不建孤儿 operation） | 双连接断言零新行；变异「discriminator 无 state==DELETED 门禁」→红 |
| 19 | adapter 恢复：receipt-lookup-only 先 lookup | **→ 移入 S5-C 反例矩阵**（本 PR 只保留编号占位与归属；receipt 三态语义与 lookup 反例见 R1-S5-C） | — | — |
| 20 | adapter 恢复：idempotent replay 承诺 | **→ 移入 S5-C 反例矩阵**（本 PR 只保留编号占位与归属；replay 承诺/期限反例见 R1-S5-C） | — | — |
| 21 | core owner 跨 purge ACK 污染 | `workspace.core.v1`/`execution.core.v1` erased-fence 重放用旧 revision 修复新 op checkpoint | family-B 门禁 backport 后拒绝（`fence.purge_revision != purge_revision` fail closed，零 ACK 修复） | 断言 core owner 拒绝 + 零写；变异「core participant 无 purge_revision 门禁」→红 |
| 22 | 双深链伪造（lineage item 5，聚合期阶段 2） | 篡改中间 seeded checkpoint N+1（非 fence）后 N+2 聚合 | N+2 lineage 重验失败（N+1.ack_digest != fence.ack_digest）→ **G4 derived conflict（operation/Conversation blocked 投影 + checkpoint 保持 acked 零修改，不回滚已提交 N+2）** | 断言 G4 投影 + checkpoint 零修改 + 零回滚；变异「信任 seeded 副本不逐跳重验 / 把 checkpoint_digest 当信任锚点」→红 |
| 23 | case D removed owner 已完成 | registry 移除 owner 且旧义务已 acked/erased，rebuild | rebuild 继续、无该 owner 行（义务已清偿） | 断言无行 + rebuild 成功；变异「removed completed owner 也 seed 一行」→红（rebuild 期即拒） |
| 24 | settlement 永久不可达 → 显式 reconcile | **→ 移入 S5-C 反例矩阵**（本 PR 只保留编号占位与归属；恢复超时/adapter 不可解析/reconcile 反例见 R1-S5-C） | — | — |
| 25 | seeding 前 lineage 失败（族 E 阶段 1） | rebuild 事务内 lineage 六项任一失败（fence 非 erased / ack_digest 缺失 / owner·version·capability 不符） | 整事务回滚：零新 operation、零新 checkpoint、旧 operation 原状；不产生 owner conflict checkpoint | 断言零新行 + 旧 operation 逐字段不变；变异「失败后仍提交新 op 或写 conflict checkpoint」→红 |
| 26 | seed 提交后 lineage 被篡改（族 E 阶段 2） | seeding 合法提交后篡改 predecessor/fence 行，coordinator 聚合 | 聚合重验失败 → **G4 derived conflict**（投影 `blocked` + `purge_owner_ack_conflict`；checkpoint 零修改；已提交新 operation 不回滚） | 断言 G4 投影 + checkpoint 零修改 + 新 operation 保留；变异「聚合期失败回滚已提交新 op / 写 checkpoint」→红 |
| 27 | re-added owner reason 参数化（族 F） | re-added：reopenable 族 / 3·5·6 族 / failed / unknown·NULL 各一 | reopenable + active/blocked → `pending`；3/5/6 → blocked carry 禁重开、禁二次 adapter 调用；failed + 非 erased → failed carry；unknown/NULL → dirty-data 整事务回滚 | 参数化四类断言 + adapter 调用计数零；变异「3/5/6 重开 pending / unknown 落入通用 pending」→红 |
| 28 | version-changed 3/5/6 禁重开（族 F 收口 P2） | case E：旧 fence erasing/blocked + 输出态 3/5/6 落账 | blocked carry/reconcile 禁重开（具名 reason 保留）；输出态 4 → erased 分支 fail closed | 参数化 3/5/6/4 断言；变异「settlement_deadline_expired/adapter_unresolvable 被重开 pending」→红 |
| 29 | 阶段混淆与 seeded 副本信任 mutation | 聚合期失败回滚已提交新 op；seeding 期失败写 conflict 落账（应为整事务回滚）；coordinator 信任 seeded digest 副本 | 三变异全部使守卫转红（阶段 1/2 边界 + 事实源唯一性 + derived 载体唯一性） | 变异「混淆两阶段」→红；变异「信任 seeded 副本」→红；变异「把 3/5/6 重开 pending」→红 |
| 30 | seeded 缺行禁 pending 重跑（族 C） | 删除 seeded（`inherited_acked`）checkpoint 行后聚合 | `expected_obligation_kind=inherited_acked` + 缺行 → `lineage_status=conflict` → G4（投影 blocked + `purge_owner_ack_conflict`）；不落 running、不重建 pending 重跑、零 adapter 调用 | 断言 G4 投影 + 零 checkpoint 重建 + adapter 调用计数零；变异「缺行按 native_pending 判 running / 重建 pending 行重跑」→红 |
| 31 | 显式 retry 白名单（族 B 封闭） | 3/5/6 blocked owner 经显式 retry API | 拒绝：零 adapter 调用、零状态推进（operation/checkpoint/fence 均不变） | 断言全零 + 状态不变；变异「白名单含 3/5/6 / 重试重开 blocked→running」→红 |
| 32 | 阶段 2 撕裂读（族 D） | 移除 Conversation 首锁或允许某写者绕过首锁写 predecessor/fence | predecessor/fence 撕裂读测试转红（重验读到中间态 → G4 误判或漏判） | 变异「任一写者绕过 Conversation 首锁」→红（撕裂读断言，写者清单见 S5-B-3 阶段 2） |
| 33 | expected-kind 公式判别点（终结批次） | ①删 registry diff 输入 ②删 predecessor S5-C terminal fact 输入 ③错用 live installed registry（部署漂移后重算） ④删当前 seeded 行（同行 30） | ①added/re-added 分类测试转红 ②carried_blocked/carried_failed 分类转红 ③同一 operation 重算结果不得变化，变化即红 ④仍推导 `inherited_acked` → G4 + 零 adapter 调用 | 四变异全部具名转红；权威公式见 S5-B-3 阶段 2（逐字同构，四处引用） |

> 反例矩阵复用 S4-F 已冻结注入机制（真实 PostgreSQL、双连接 `asyncio.gather`、DB 篡改、崩溃注入、fake adapter 故障注入）；rebuild 测试归属 scheduler slice 实现 PR，I2 只消费 S5-B-8 normalized facts。行 14/19/20/24 为 S5-C 归属占位（settlement/adapter 专项反例由 S5-C 反例矩阵承载，编号不再在本 PR 展开）。

#### S5-B-10 三面复审记录与 Option D 架构裁决（TD-092）

**首轮三面原始计数（保留不覆盖）**：数据/状态机 P0=0/P1=3/P2=4/P3=3 + 并发/锁序 P0=0/P1=3/P2=3/P3=4 + 测试/运维 P0=0/P1=2/P2=5/P3=4 → **合计 P0=0/P1=8/P2=12/P3=11**（31 findings，去重后 7 个独立 P1）。

**首轮裁决（保留不覆盖）**：保持 schema-free——不新增 versioned-fence schema、不新增 provenance 列；fence 单行 + 两个新 primitive（erasing-fence token 迁移、core owner family-B 门禁 backport）+ discriminator 锁内限定 + S5-A 调整清单 8 项 + 反例矩阵 18 行。落地后按任务指令停止补词。

**第二轮三面原始计数（保留不覆盖，本轮）**：数据/状态机 + 并发/锁序 + 测试/运维 → **合计 P0=0/P1=6/P2=18/P3=12**（去重后 6 个独立 P1）。

**第二轮裁决（TD-092，Option D：quiesce-and-finalize）**：6 个独立 P1 的共同根因是「首轮 erasing-fence token 迁移 primitive 在『重建时机』与『在途 adapter 窗口』之间制造不可判定并发窗口」，以及「adapter 恢复契约自相矛盾」。本轮**停止逐 finding 补词，改为架构重写**，不再逐条开列：

1. **核心状态机改为 quiesce-and-finalize（P1 族 1）**：Tx1 commit 是 adapter window 线性化点；G1/G2 只写投影 blocked；任一 owner `erasing` 即 quiesce（不推进 purge_revision、不建新 op、不迁移 fence token）；旧 revision settlement-only 通道（Tx2/同 revision crash replay 精确 token 写 owner-scoped 事实，禁新 Tx1、禁投影写）。见 S5-B-1。
2. **删除 erasing-fence token 迁移 primitive（P1 族 1 收口）**：settlement 永久不可达 → 显式 reconcile，不以新 revision 二次调用掩盖。见 S5-B-4/S5-B-1。
3. **adapter 恢复契约同步重写（P1 族 2）**：消除 Protocol「supports_idempotent_replay=False 但 delete_object 无条件称幂等」矛盾；idempotent replay 承诺（去重有效期覆盖最大恢复周期 + 可验证 evidence/明确 unknown）；receipt-lookup-only 先 lookup（None 视为不确定，禁据此再次 delete）；双支持优先 lookup。见 S5-B-7。
4. **rebuild DELETED 门禁（P1 族 3）**：rebuild 创建路径在 Conversation 锁内强制 `conversation.state == DELETED`；restore 后零新行，不只修判别器。见 S5-B-6。
5. **owner obligation 全函数矩阵（P1 族 4）**：checkpoint 状态/缺行 × fence 态 × added/removed/re-added/version-changed；re-added + erased fence 定位证据锚点，不按新增建 pending。见 S5-B-2。
6. **lineage 结论收窄（P1 族 5）**：信任锚点只留 `fence.ack_digest`（原生终态锚点）；`checkpoint_digest` 无 fence 锚点 → 仅审计副本，不参与信任判定。见 S5-B-3。
7. **S5-B→S5-A 八项接口补齐（P1 族 6）**：core family-B backport、旧 revision settlement 门禁、S5-A-8 反例归属与前向指针。见 S5-B-8。

**状态**：Draft（Option D 架构重写已落地；第三轮广域三面后按指令**停止**，拆分 S5-C）。不合并 stacked PR #564、不恢复 #563、不启动 I1/I2/S5 实现/S6/C1、不评分不转 Ready。

#### S5-B-11 第三轮广域三面（架构重写后）与 S5-C 拆分裁决（TD-092）

**第三轮三面原始计数（架构重写 commit `82c3f67f` 后，保留不覆盖）**：数据/状态机 P0=0/P1=5/P2=6/P3=4 + 并发/锁序 P0=0/P1=2/P2=3/P3=4 + 测试/运维 P0=0/P1=3/P2=8/P3=5 → **合计 P0=0/P1=10/P2=17/P3=13**（40 findings，去重后 9 个独立 P1，其中并发「settlement fencing liveness」与数据面同源去重）。

**9 个独立 P1 根因族（逐条已核验代码事实）**：

1. **settlement fencing liveness（族 A）**：settlement 通道（Tx2/同 revision crash replay）经 `_load_verified_operation` 的现行 `registry_digest`/`hold_revision_snapshot` 等值校验，在 G1/G2 drift 下必 raise——而 drift 恰是触发 quiesce 的条件，quiesce 永不收敛、adapter 已发生 outcome 无法落账。S5-B-1「drift 不得改变 settlement 判定输入」与 S5-A-4 Tx2 重验集及代码事实矛盾。（并发 P1-2 = 数据 P1-1）
2. **settlement 锁序归因错误（族 B）**：S5-B-6「quiesce 判定锁序」把互斥归因到「owner lock + fence/operation 行锁」，但该锁集与 Conversation 行锁不同域、不互斥；真正互斥来自 settlement Tx2 自身先取 Conversation 行锁（S5-A-4 全局互斥）。（并发 P1-1）
3. **fence 永留 erasing（族 C）**：4 个非 core owner 的 post-window blocked（含 outcome_unknown）fence 无 `erasing→blocked` 转移（S4-F 已冻结「Tx2 不碰 fence」），quiesce 门禁永不释放，rebuild 永久阻塞；矩阵 case A「blocked × active/blocked」对这 4 owner 是死行。（数据 P1-2）
4. **ACK-lost 第三路径缺失（族 D）**：settlement 通道只列 Tx2/同 revision crash replay 两条路径，ACK-lost（fence=erased + checkpoint≠acked）无收口路径；S4-F 族 B erased-fence repair 未被枚举，且 I2 前该 repair 会清 drift failure_code、写投影。（数据 P1-5）
5. **seeding/聚合阶段未分离（族 E）**：lineage 失败同一事实被冻结为两种互斥裁决——S5-B-2 兜底=rebuild 事务回滚 vs S5-B-3/S5-B-8 item 5=owner-level blocked；未区分 seeding 期与聚合期。（数据 P1-3）
6. **re-added reason 分派缺失（族 F）**：case C「历史 fence active/blocked → 重开 pending」未检查历史 checkpoint reason_code，outcome_unknown 历史被重开 pending，违反硬约束「outcome_unknown 不得重开 pending」。（数据 P1-4）
7. **Protocol 矛盾未消（族 G）**：`supports_idempotent_replay=False 但 delete_object 无条件称幂等`只在文档层消除，merged 代码事实源无回填归属。（测试 P1-1）
8. **idempotent replay 承诺 vacuous（族 H）**：去重窗口无载体 + 「最大恢复周期」含无界人工 reconcile 延迟 → 条件不可测、row 20 无法落地。（测试 P1-2）
9. **replay-only 死路（族 I）**：双支持优先 lookup 与承诺节冲突；「降级 reconcile」对无 lookup adapter 是零动作死路。（测试 P1-3）

**S5-C 拆分裁决（按任务指令：停止扩大 #564）**：9 个独立 P1 中，族 A/B/C/D/G/H/I（7 族）聚集在 **settlement-only adapter recovery**（settlement-only 通道 S5-B-1 + adapter 恢复契约 S5-B-7）；族 E/F（2 族）在 rebuild/obligation 矩阵（S5-B-2/S5-B-3）。按指令停止本 PR 继续返修，**把 settlement-only adapter recovery 拆为独立 S5-C contract-first PR**（scope = settlement-only 通道 + adapter 恢复契约，承载族 A/B/C/D/G/H/I 七族冻结），族 E/F 留在 S5-B 主体作后续返修项（**历史裁决**：族 E/F 已于 #564 收口批次完成，commit f1c4a9de）。不得继续扩大 #564；#563 保持 `efde24e4` 不动（**当时状态**：#564 已于 2026-08-14 squash 合并入 #563，root HEAD `bb792547`）。

**scope-cleanup（拆分归一化，本 commit 落地）**：S5-B-1 settlement-only 通道/事实源/outcome 落账与 S5-B-7 adapter 恢复契约的**具体裁决从本 PR 正文移除**，S5-B 只保留「**rebuild 输入必须已满足 S5-C settlement terminal contract**」依赖接口（S5-B-1）；S5-B-9 反例矩阵行 14/19/20/24 移入 S5-C 反例矩阵（本 PR 保留编号占位与归属）；S5-B-4/S5-B-8 的 settlement 引用改指 S5-C。第三轮计数与本拆分记录保留不覆盖；族 E/F 不在本 commit 返修（留 S5-B 主体后续）。

#### S5-B-12 Draft 收口批次（族 E/F + S5-A 前向回填；组合广域三面）

- **族 E 分阶段（seeding vs aggregation，消除双值语义）**：阶段 1——rebuild/seeding 事务在**新 operation/checkpoint 提交前**验证 predecessor/fence 原生锚点/owner·version·capability/lineage 六项，任一失败 → **整事务回滚**（零新 operation、零新 checkpoint、旧 operation 原状、不产生 conflict checkpoint）；阶段 2——seeding 合法提交后 coordinator 每次聚合重读 predecessor + fence 重验 lineage，缺失/篡改/漂移 → owner-level `blocked` + `purge_owner_ack_conflict`（不回滚已提交新 op、不信任 seeded 副本）。落地：S5-B-2 兜底、S5-B-3、S5-B-8 item 2/5、S5-B-9 行 4/16/22。
- **族 F 全函数**：case C re-added 按「历史 checkpoint × reason × fence」全函数分派（acked+erased+lineage → seeded；reopenable 族/pre-window gate → pending；3/5/6 → carry 禁重开禁二次调用；failed+非 erased → failed carry；unknown/NULL/failed×erased/锚点缺失 → dirty-data 回滚；erasing → S5-C terminal contract 先行）；case E 对输出态 3/5/6/4 具名分态（**关闭已登记 P2**）。
- **S5-A 前向回填（本分支内，不带 #563）**：S5-B-8 最终 11 项逐项回填进继承的 S5-A 正文——S5-A-0 reason 7 层增补 4 code、S5-A-1 写者增补（seeding 第三写者 + settlement fence 写者/进入点）、S5-A-2 输入增补/五方 fence.purge_revision 双分支/关键规则 3·5·6 reconcile-only、S5-A-4 settlement 例外 + I2 门禁、S5-A-8 行 16 收窄 + 行 22/23、S5-A-10 S6 前向指针；每点带「回填自 S5-B-8 第 N 项」精确引用，不复制第二套规则；RecoveryDescriptor 不进 reducer/calculator 输入。
- **反例矩阵补强**：S5-B-9 行 25-29（seeding 回滚零新行、聚合冲突不回滚、re-added 参数化、version-changed 3/5/6、三 mutation 转红）。
- **本轮计数（组合 S5-A+S5-B+S5-C 全新广域三面，历史计数全部保留不覆盖）**：数据/状态机 P0=0/P1=3/P2=7/P3=5 + 并发/锁序 P0=0/P1=2/P2=4/P3=3 + 测试/运维/文档 P0=0/P1=0/P2=8/P3=3 → **合计 P0=0/P1=5/P2=19/P3=11**（35 findings）。去重 4 个 P1 根因族：①**阶段 2 conflict 落账载体缺口**（owner-level `purge_owner_ack_conflict` checkpoint 需未登记的第四写者（coordinator）+ `acked→blocked` 转移边 + level-4 值域豁免——数据 P1-1 + 并发 P1-2）；②**reconcile-only 封闭性缺口**（3/5/6 未从 S5-A-3 显式重试路径排除，禁二次 adapter 调用可被绕过——数据 P1-2）；③**seeded 行缺失裁决冲突**（阶段 2 conflict vs S5-A-2 缺行 pending 互斥——数据 P1-3）；④**阶段 2 predecessor 只读重验缺读集一致论证**（并发 P1-1）。

**四族统一定向返修（架构裁决：derived lineage conflict——用户裁决，不再次架构拆分）**：阶段 2 lineage conflict 是 **coordinator-derived normalized fact，不是 checkpoint 状态**；**不新增 checkpoint 第四写者、不新增 `acked→blocked` 转移、不允许 coordinator 写 checkpoint.reason_code**。四族落地：
- **A. conflict 载体**：calculator 输入增补 per-owner `lineage_status`（valid/conflict/not_applicable，携带 owner_key）+ `expected_obligation_kind`（native_pending/inherited_acked/carried_blocked/carried_failed），均 derived 非持久、可由 operation snapshot + immediate predecessor + predecessor checkpoint + fence 原生锚点确定性重算、重启后相同投影；G4 gate（先于 checkpoint 聚合、先于 completed/running/缺行判断）命中 → coordinator 只写 operation/Conversation 投影（`blocked` + `purge_owner_ack_conflict`），checkpoint 保持原 owner 事实零修改（含 acked）；多 conflict owner 按 owner_key 字典序诊断、failure_code 单一；S5-A-0/1/2/3、S5-B-3/8 删除「owner-level blocked checkpoint」与 level-4 值域豁免要求。
- **B. reconcile-only 封闭性**：S5-A-3 显式重试改 **reason 白名单**（仅 S5-B-2 冻结 reopenable 域）；`outcome_unknown`/`settlement_deadline_expired`/`adapter_unresolvable`/`purge_owner_ack_conflict`/dirty-data/G1/G2 一律禁止 `blocked→running`；S5-C-2「不限制显式重试」收窄为「不限制经 S5-A-3 白名单批准的 owner 重试，明确排除输出态 3/5/6」；反例行 31 断言 3/5/6 经显式 retry API 零 adapter 调用、零状态推进。
- **C. seeded 缺行**：`expected=inherited_acked`（或 carried_blocked/carried_failed）缺行 → `lineage_status=conflict` → G4，禁止当 pending 重跑；仅 `expected=native_pending` 缺行按 pending/running；不新增 provenance 列；反例行 30（删 seeded 行落 running 或再次调用 adapter → 红）。
- **D. 阶段 2 读集一致性**：明示 Conversation FOR UPDATE 窗口内全部合法写者被统一首锁串行 + predecessor 非 top revision（purge_revision 门禁拒绝 participant 写）+ 写者清单（六 owner erase 入口 / settlement 三进入点 / rebuild / coordinator / hold / delete-restore，任一绕过首锁即契约失败）；predecessor/fence 只读不加 FOR UPDATE 成立；反例行 32（移除首锁或允许绕过 → 撕裂读转红）。

**四族定向复核（本轮返修后，不重开完整三面；历史计数保留不覆盖）**：**P0=0/P1=1/P2=4/P3=2**。架构裁决约束 1-4 全部核验通过（derived normalized fact / 不新增第四写者 / 无 acked→blocked 转移 / coordinator 不写 reason_code）；B/C/D 三族全过（白名单 7 拒绝项、S5-C-2 排除 3/5/6、行 31/30/32 mutation 具名可执行、写者清单七类齐全）。**新 P1-1（族 A）**：`expected_obligation_kind` 重算输入集两处分叉——S5-A-2 输入增补与 G4 可重算性共用「operation snapshot + immediate predecessor + predecessor checkpoint + fence 原生锚点」公式，漏 S5-B-3 阶段 2 冻结公式中的「registry diff（新/re-added owner 判别）与 S5-C terminal facts（carried_blocked/carried_failed 判别）」两个输入源。P2×4（阶段 1 残留旧载体术语、S5-A-8 行 20 未同步 G4 表述、S5-A-4 缺行语句未带 native-only 限定、写者清单 workspace:270 引证漂移）+ P3×2。按任务指令停止；derived-conflict 裁决未被推翻。

**expected_obligation_kind 公式对齐终结批次（用户裁决批准；本批次为最后一次局部公式修正，若复核再出现 P0/P1 不继续补词）**：
1. **权威公式唯一化**（S5-B-3 阶段 2）：`expected_obligation_kind = f(current operation.registry_snapshot, immediate predecessor.registry_snapshot, immediate predecessor checkpoint/fence 的 S5-C terminal fact, fence 原生终态锚点)`——registry diff 两端均为持久快照（不得用 live installed registry；live drift 只由 G1 处理）；S5-C terminal fact 必须来自 predecessor 已 settlement 持久事实（不得读当前待判定 checkpoint；删当前 seeded 行后仍完整可重算，无循环）；current checkpoint 仅用于比较实际值 vs expected kind。
2. **三处引用逐字同构**：S5-A-2 输入增补、S5-A-2 G4 可重算性、S5-B-8 item 2 全部改为同一公式串 + 「权威定义见 S5-B-3 阶段 2」指针。
3. **P2×4/P3×2 同落点清理**：阶段 1「不产生 conflict 事实」术语、S5-A-8 行 20 G4 载体表述、S5-A-4 缺行规则 native_pending-only 限定、workspace 引证改 :319、G4 触发条件字面、零行 native-only 限定。
4. **行 33 公式判别点**：删 registry diff → added/re-added 分类红；删 predecessor terminal fact → carried 分类红；错用 live registry → 部署漂移后同一 operation 重算变化红；删 seeded 行 → 仍推导 inherited_acked → G4 + 零 adapter 调用（同行 30）。

**公式同一性 + 无循环依赖定向复核（终结批次后，不重开完整三面；历史计数保留不覆盖）**：**P0=0/P1=0/P2=3/P3=2**。核验结论：四处 `expected_obligation_kind` 公式串字节级逐字同构（S5-B-3 权威唯一 + 三处引用带指针，四值映射一致）；无循环依赖成立（四输入无一指向当前待判定 checkpoint，删 seeded 行后完整可重算，缺行处置「先重算 kind 再判缺行」单一方向）；G1 边界四子句齐全（两端持久快照/禁 live registry/live drift 只归 G1/同 operation 重算不变），G1>G4 自洽；行 33 四变异全部具名可执行并与四输入一一挂钩。P2×3（lineage_status 旧短语同区残留、矩阵行 4/25 旧载体术语、行 19/表 6-7 字面未带 native-only）+ P3×2（指针前缀、引用口径）为同族精度项，**按指令不再补词**，登记归属：**REQ-047 / R1-S5 implementation conformance follow-up**（不宣称已修复）。

**Stack 收尾（历史叙述）**：#565（评分 92）→ #564 收口批次（族 E/F 完成）→ #564 正式评分 87 → **#564 squash 合并入 root #563（`bb792547`，2026-08-14）**，S5-B/S5-C 子 PR 分支已清理；A/B/C 三层契约随 root #563 一并走完剩余闭环（尚未进入 main）。

### R1-S5-C：Settlement-only Adapter Recovery 契约（contract-first，拆分自 #564）

> Status: Draft（stacked PR，base = #564 @ `da57b947`（scope-cleanup 后 HEAD）；#563/#564 正文不在本 PR 修改。**历史 stacked child**：本契约已随 #565（评分 92）squash 合并入 #564，再随 #564（评分 87）squash 合并入 root #563 @ `bb792547`，尚未进入 main）
> 分支：`docs/req041-047-r1-s5c-settlement-adapter-recovery-contract`
> 仅纯文档；不写代码/测试/schema/migration/registry；不启动 I1/I2/S5 实现/S6/C1。
> 本契约拆分自 #564 的 settlement-only adapter recovery（S5-B-1 settlement-only 通道 + S5-B-7 adapter 恢复契约），承载 S5-B-11 族 A/B/C/D/G/H/I 七族 P1 冻结；S5-B 主体保留 rebuild/obligation/lineage，族 E/F 归 S5-B 后续返修（**已完成**：#564 收口批次，commit f1c4a9de）。#564 已落地 scope-cleanup：S5-B 正文只保留「rebuild 输入必须已满足 S5-C settlement terminal contract」依赖接口。冻结后回 #564 回填「settlement/adapter 契约指向本契约」的前向指针（**已完成**：#565/#564 均已合并入 root #563）。
> **冻结方式（按任务指令）**：先冻结状态机，不按七族逐条补词——七族 P1 作为输入证据映射到各节（S5-C-0），正文按「状态机 → 四项裁决 → 并发与写者 → 反例矩阵 → 接口」组织。

#### S5-C-0 冻结范围与七族 P1 映射（输入证据；正文按风险域组织，不再逐族补词）

| 族 | P1（#564 S5-B-11，计数保留在 #564 不覆盖） | 收口节 |
|----|------------------------------------------|--------|
| A | settlement fencing liveness（drift 下 settlement 通道必 raise，quiesce 永不收敛） | S5-C-2 drift 绕过 + S5-C-8 行 1/2 |
| B | settlement 锁序归因（互斥来自 Conversation 全局锁，非 owner/fence/operation 行锁） | S5-C-7 统一锁序 |
| C | fence 永留 erasing（4 非 core owner 无 `erasing→blocked` 写者） | S5-C-7 erasing→blocked 边 + S5-C-8 行 3 |
| D | ACK-lost 第三路径缺失（fence=erased + checkpoint≠acked 无收口） | S5-C-7 ACK-lost repair + S5-C-8 行 4 |
| G | Protocol 矛盾（merged 代码事实源无回填归属） | S5-C-3/S5-C-5 + S5-C-9 回填归属 |
| H | idempotent replay 承诺 vacuous（去重窗口无载体、「最大恢复周期」无界） | S5-C-4 自动恢复期限 + S5-C-8 行 6 |
| I | replay-only 死路（「降级 reconcile」对无 lookup adapter 是零动作死路） | S5-C-5 三态 + S5-C-6 replay-only + S5-C-8 行 7 |

（其余 S5-B-1/S5-B-7 的 settlement/adapter 相关小节由本契约接管；S5-B 主体的 rebuild/obligation/lineage 保持 #564。族 E/F 的 seeding/聚合阶段分离、re-added reason 分派**已在 #564 收口批次完成**（commit f1c4a9de，历史叙述）。）

#### S5-C-1 状态机：输入域、输出态全函数与 fence 收敛（先冻结状态机）

**输入域（冻结）**。settlement 的输入 = 每 owner 的持久行组合 + 冻结 token 集：

- checkpoint.state ∈ {`pending`, `erasing`, `blocked`, `failed`, `acked`, 缺行}（CHECK `ck_agent_purge_owner_state`）；fence.state ∈ {`active`, `erasing`, `blocked`, `erased`}（`_FENCE_ALLOWED_TRANSITIONS`，erasure_repository.py:96-105）。
- 本契约裁决的 settlement 输入态（三类）：
  1. **窗口态 `erasing`**：`checkpoint.state == erasing` 或 `fence.state == erasing`（Tx1 commit 后、Tx2 未收口；Tx1 commit = adapter window 线性化点，S5-B-0 item 6）；
  2. **post-window blocked**：`checkpoint.state == blocked ∧ fence.state == erasing`（现码 **4 非 core owner** 的 blocked/unknown 落账不写 fence——族 C 输入事实；core owner 的 scan-nonzero 落账已写 fence `erasing→blocked`，不产生本输入态）；
  3. **ACK-lost**：`fence.state == erased ∧ checkpoint.state ∈ {pending, blocked}`（同一 `purge_revision`；S4-F 族 B 门禁保留）。
- 冻结 token 输入（settlement 判定只读这些持久事实）：operation（`purge_revision`/`lease_epoch`/`registry_snapshot`/`registry_digest`/`hold_revision_snapshot`/`state`）、Conversation（`purge_revision`/`hold_revision`/`state`，锁内读）、checkpoint（`attempt`/`checkpoint_digest`——erasing 期 = intent digest）、fence（`purge_revision`/`owner_version`/`revision`/`ack_digest`）、idempotency key（由 S5-C-3 解析的旧 adapter 身份 + ref/session 身份派生，不含 lease_epoch/attempt，跨 takeover 稳定）。

**输出态（冻结，全函数——任何输入组合落在六态之一，表外组合 fail closed 零写）**：

| # | 输出态 | 判定条件 | 落账（owner-scoped） | 后续 |
|---|--------|---------|---------------------|------|
| 1 | success | adapter 成功 + 可验证 evidence（重算 receipt_digest 匹配），或 lookup 有 evidence（S5-C-5） | fence `erasing→erased`（ack_digest）；checkpoint `→acked`（ack_digest + final scan digest）；ledger/binding `erased` + receipt | S5-B-2/S5-B-3 lineage 可继承 |
| 2 | 可证明未发送 | `NotSentError`/`FailedError`，或 lookup 否定证据（S5-C-5），**或 transport owner 的 final-scan non-zero blocked（可证明未清除，reason = scan 族）** | checkpoint `blocked` + `erase_timeout`/`adapter_unavailable`/scan 族 reason；fence `erasing→blocked`；ledger/binding `blocked` + reason | **reopenable**（S5-B-2 重开 pending） |
| 3 | outcome_unknown | `TimeoutError`/`Unknown`，或 lookup 不可判定（S5-C-5） | checkpoint `blocked` + **现有** `purge_blocked_by_*_outcome_unknown`（external/runtime 各一）；fence `erasing→blocked`；ledger/binding `unknown` | **reconcile-only，不重开 pending**（S5-B-2 case A carry） |
| 4 | ACK-lost repair | fence `erased` + `ack_digest` 存在 + final scan 零（S5-C-7） | checkpoint `→acked`（ack_digest = fence.ack_digest、checkpoint_digest = final scan digest、**清 `reason_code`**）；fence 零修改 | 同 success 权重 |
| 5 | 恢复超时 | deadline 过期（S5-C-4 进入点判定，checkpoint 仍 `erasing` 时；**仅适用于 external/runtime 窗口态**） | checkpoint `blocked` + **新增** `purge_blocked_by_*_settlement_deadline_expired`（external/runtime 各一，落账固化）；fence `erasing→blocked` | reconcile-only，禁自动重试 |
| 6 | adapter 不可解析 | frozen snapshot 的 (owner_key, owner_version) 在历史 resolver 中不存在，**或 resolver 命中但旧版本 adapter 实现不可加载**（S5-C-3） | checkpoint `blocked` + **新增** `purge_blocked_by_*_adapter_unresolvable`（external/runtime 各一）；fence `erasing→blocked`；**零 adapter 调用** | reconcile-only，禁自动重试 |

- 输出态 3/5/6 **各冻结独立持久 reason code**，均归 S5-A severity **level 7**（outcome_unknown 族）：态 3 用现有 `purge_blocked_by_external_outcome_unknown`/`purge_blocked_by_runtime_outcome_unknown`；态 5/6 新增 `purge_blocked_by_external_settlement_deadline_expired`/`purge_blocked_by_runtime_settlement_deadline_expired` 与 `purge_blocked_by_external_adapter_unresolvable`/`purge_blocked_by_runtime_adapter_unresolvable`（level 7 域内新增值，S5-A 回填项登记见 S5-C-9，不修改 #563）。**具名性由持久 reason code 承担**——终态后 checkpoint 已 blocked、`updated_at` 已更新，**不依赖终态后重算**。
- **已落账收敛规则（冻结，输入态 2 的收敛）**：若 checkpoint 已为 `blocked` 且 `reason_code` 已持久（post-window blocked，S5-C-7 写者归一后仅 pre-fix 遗留数据可达），settlement **只写 fence `erasing→blocked`**，checkpoint/ledger **零修改、reason 不覆写**；输出态归类按已持久 reason——现有 `outcome_unknown` → 态 3；`settlement_deadline_expired` → 态 5；`adapter_unresolvable` → 态 6；scan 族 / `erase_timeout` / `adapter_unavailable` 族 → 态 2；**其他/NULL reason → 不归类**（写行为仍零修改，登记运维视图交数据治理，dirty-data）。
- **failed 收敛（冻结）**：checkpoint=`failed`（S5 scheduler slice 写，S5-A-2 优先级 5）时 settlement 兜底——若 fence 仍 `erasing`（pre-fix 遗留/未收敛时序），写 fence `erasing→blocked`（checkpoint 零修改，failed 保留）；`(failed, blocked)`/`(failed, active)` 零写；矛盾组合（如 `(failed, erased)`）零写 + 登记运维视图交数据治理。scheduler slice 写 failed 时必须同步收敛 fence 由本契约前置项登记（S5-C-9）。
- **fence 收敛（冻结）**：全部六个输出态 + 已落账收敛/failed 收敛都写 fence 离开 `erasing`（输出态 1 → `erased`；2/3/5/6/已落账/failed → `blocked`；4 → fence 已 `erased` 零修改）。**例外条款**：fence 写本身无法完成（行缺失 / CAS 永久冲突，经 S5-C-2 settlement fence 校验后仍失败）→ fail closed 为**具名、可观察、禁止自动重试的 reconcile 状态**，reason 映射**按进入时判定的输出态全函数**——态 2 → 其自身 reopenable code（`erase_timeout`/`adapter_unavailable`/scan 族，**不降级为 reconcile-only**）；态 3/5/6 → 各自独立持久 code；**态 1/4 不适用本条款**（态 4 fence 零修改；态 1 的 fence/checkpoint/ledger 同事务，fence 写失败 = 整事务回滚零写——CAS 冲突幂等返回赢家结果，行缺失等 dirty-data 交运维视图登记，不写 blocked 伪造 reason）——不新增第 4 个 code；reconcile 语义由「fence 写失败事件登记」+ 各态自身 code 共同表达，作为 dirty-data 事件交数据治理流程（Spec §9.1/§12.4），不进入自动恢复循环。

#### S5-C-2 settlement 写域与 drift 绕过（族 A/B 收口）

**写域（冻结）**：settlement 只写 owner-scoped 事实（checkpoint/fence/ledger/binding）。**禁止**写 operation（`state`/`failure_code`/`started_at`/`revision`）与 Conversation（`purge_state`/`purged_at`）投影——I2 后零投影写（I2 前现码 `_record_blocked`/`_repair_checkpoint_if_pending` 的临时投影写由 S5-A-7 ①/② 在 I2 移除，本契约冻结目标态）。

**drift 绕过（冻结，settlement 是唯一绕过者）**：settlement 校验 operation 用 **frozen-snapshot 基准**，不以已安装 registry / Conversation 当前 hold_revision 的等值校验拒 settlement（族 A 根因：drift 恰是触发 quiesce 的条件，`_load_verified_operation` 的等值校验在 drift 下必 raise）：

1. `operation.purge_revision == conversation.purge_revision`——**旧 operation 仍为 top revision**（quiesce 保证 rebuild 未发生）；不符 = rebuild 已发生，settlement 无权再写旧行（fail closed）。
2. `operation.conversation_id == conversation.id`；`operation.state ∈ {scheduled, running, blocked}`（drift-blocked 是 `blocked`，放行；终态拒绝，镜像 `_RUNNABLE_OPERATION_STATES`）。
3. `operation.lease_epoch == expected_lease_epoch`（lease CAS 与 drift 无关，保留；expected = **caller 传入的 lease token**，同现码——stale → fail closed → 下周期新 lease 重试收敛，非死锁）。
4. **frozen-snapshot 自洽**：`snapshot_digest(operation.registry_snapshot) == operation.registry_digest`——**不**对比已安装 registry digest（G1 drift 下 `registry_digest()` 对比必 fail）；`operation.hold_revision_snapshot <= conversation.hold_revision`（hold 单调无回退，允许 G2 漂移，不判不等值）。**checkpoint 侧同基准**：`checkpoint.capability_digest == 旧 snapshot 中该 owner 的 capability_digest`、`checkpoint.owner_version == 旧 snapshot owner_version`——**替代** `_load_verified_checkpoint` 的 `capability_digest == capability_digest(owner_key)` 已安装 registry 校验（case E 下该等值必 fail，绕过集不覆盖它则族 A 只修了一半）。
5. fence：`fence.purge_revision == purge_revision`（S4-F 族 B 同 revision 门禁保留）+ `fence.owner_version == 旧 snapshot 中该 owner 的 owner_version`；checkpoint：`attempt`/intent digest **精确 token**（E-2a）。
6. settlement fence 写（`erasing→blocked`/`erasing→erased`）的 owner_version 校验基准 = 旧 operation 冻结 snapshot（**替代** `transition_fence_state` 的 `require_owner_version` 已安装 registry 校验——settlement 专用 fence 校验路径，实现归 scheduler slice 前置项；其他写者不得复用该绕过）。该专用路径**保留** `transition_fence_state` 其余全部守卫——`purge_revision >= 1`（erasure_repository.py:707-711）、purge/hold fencing token 单调非降（:715-719）、`ack_digest` 仅 `erased` 边可用（:720-728）、状态机边表（:701-704）、expected_state/revision CAS（:694）——**仅**替换 owner_version 校验基准，不得全量绕过守卫。

**禁新 Tx1（冻结，作用域 = drift 后旧 operation 的 settlement 通道）**：旧 operation（quiesce 中、G1/G2-blocked）的 checkpoint 仅 `erasing ∧ attempt >= 1 ∧ checkpoint_digest == intent digest` 可续做同一 invocation；`pending`/`blocked` 一律不得在 settlement 通道内推进 `erasing`（新 Tx1 = 新 intent/新 attempt 的 erasing 周期 = 新 adapter 删除调用，拒绝）；adapter 调用只以同一 idempotency key 重放/查询（S5-C-4 期限 + S5-C-6 条件）。**不限制**新 operation（rebuild 后）的 participant 正常入口与**经 S5-A-3 reason 白名单批准的** owner 重试 / S5-B-2 重开 pending 的 `pending/blocked → erasing` 推进——**明确排除输出态 3/5/6**（`outcome_unknown`/`settlement_deadline_expired`/`adapter_unresolvable` 一律不得经显式重试或重开路径再次进入 erasing，零 adapter 调用）；二者以「operation 是否仍为 top revision」与「fence/checkpoint 是否处于 settlement 输入态」区分，与 S5-A-3「G1/G2-blocked 不可原地重试」冻结一致。

#### S5-C-3 裁决 1：旧 adapter 身份恢复（单独裁决）

**事实（代码）**：operation 持久化的 `registry_snapshot` 只含 (owner_key, owner_version, capability_digest)（agent_erasure_registry.py:141-150）；`OwnerDefinition` 无 adapter 字段（:42-50）；participant 的 adapter 实例由组合根按**当前安装**构造注入——**现有 operation snapshot 不直接保存 adapter_key/version**。

**裁决（三选一，冻结）**：采用 **「owner_version 可重建的历史 adapter resolver」+ 显式 fail closed**，不新增持久 provenance：

- registry 模块维护 code-defined 版本化 resolver，返回**完整 immutable recovery descriptor**：
  `resolve_adapter(owner_key, owner_version) -> RecoveryDescriptor(adapter_key, adapter_version, supports_idempotent_replay, dedup_window, receipt_lookup_semantics_version, settlement_deadline)`。
  - 字段语义（冻结）：`adapter_key`/`adapter_version` = 协议身份（idempotency/receipt 派生输入）；`supports_idempotent_replay` = 幂等重放能力；`dedup_window` = idempotency key 去重窗口；`receipt_lookup_semantics_version` = receipt lookup 三态语义版本（S5-C-5）；`settlement_deadline` = 该 owner-version 的 settlement 自动恢复期限（S5-C-4）。**`receipt_lookup_semantics_version` 非空 ⇔ `supports_receipt_lookup == True`**（lookup 能力位由语义版本的存在性表达，S5-C-6 replay-only 定义输入；无 lookup 能力 = 无语义版本）。
  - descriptor 为 **immutable 值对象**（冻结 dataclass）；resolver 覆盖全部可能出现在持久 snapshot 中的历史 (owner_key, owner_version)。
- **强不变量（冻结）**：descriptor **任一字段或 adapter 路由（owner_key → 具体实现装配）发生变化，必须 bump owner_version**（新 version 新 descriptor，旧 descriptor 语义不变）；**历史 descriptor 与实现装配不得删除**（删除即破坏旧 snapshot 可解析性）。
- settlement 解析恢复事实**只用** frozen snapshot 的 (owner_key, owner_version) 经 resolver 取旧 descriptor；**禁止**「当前已安装 adapter 即旧 adapter」的假定——当前 descriptor 仅在 resolver 判定 `owner_version == 当前 registry 版本` 时才与旧身份一致。
- 解析失败（历史版本不在 resolver 域）→ **显式 fail closed**：输出态 6 adapter 不可解析（零 adapter 调用、reconcile-only）。**同样落入输出态 6**：descriptor 命中但旧版本 adapter 实现不可加载（类已删除/不可导入）——「零 adapter 调用 + fail closed」延展到实现不可用，**不允许 fallback 当前实现**（descriptor 与实现装配是两个独立事实，装配缺失不得篡改 descriptor）。
- 不选「新增持久 provenance 列」：S5-A-0 已冻结「无契约依据不新增 schema/migration」，resolver 方案在 schema-free 下达成同一保证；若未来 resolver 维护不可行，fail closed 路径已兜底。

#### S5-C-4 裁决 2：自动恢复期限（单独裁决，族 H 收口）

- **deadline 来源与载体（冻结）**：`settlement_deadline` 来自 frozen RecoveryDescriptor（S5-C-3，每 owner-version 一个有界值）；载体 = `checkpoint.updated_at`——Tx1 推进 `erasing` 时 participant 以 PostgreSQL `clock_timestamp()` 写入（代码事实：`_database_now` transport_erasure_participant.py:282-284；external Tx1 `checkpoint.updated_at = effective_now`）。判定 = settlement 恢复进入点锁内以 DB clock 计算 `clock_timestamp() <= checkpoint.updated_at + descriptor.settlement_deadline`（双侧同源 DB clock）。
- **判定窗口（冻结）**：deadline 判定**只允许在 checkpoint 仍 `erasing` 且本 settlement 尚未修改 `checkpoint.updated_at` 时执行**（进入点判定）——settlement 落账会写 checkpoint 行（`updated_at` 随之更新），**终态后不得再宣称可由 `updated_at` 重算「deadline 已过」**；判定结果以输出态 5 的独立持久 reason code（`purge_blocked_by_*_settlement_deadline_expired`）落账固化。**适用域**：输出态 5 仅适用于 external/runtime 窗口态；transport/core owner 无 adapter 窗口、无 Tx1 erasing checkpoint，不适用输出态 5/6。**测试注入（冻结，沿用 S5-A-4 时钟先例）**：deadline 过期/未过期边界由注入 clock 或 DB 篡改回填 `checkpoint.updated_at`（进入点判定前）构造，双侧同源 DB clock 下无应用时钟接缝。
- **adapter 去重期限关系（冻结）**：settlement 自动 replay 的必要条件 = `descriptor.dedup_window >= descriptor.settlement_deadline`（二者同属一个 descriptor，比较可判定；不满足 → 该 descriptor 不用于 settlement 自动 replay，落 S5-C-6 条件判定）。S5-B-7 旧文「去重有效期覆盖最大恢复周期（含人工 reconcile 延迟）」废弃——**人工 reconcile 不计入自动恢复期限**（证据型数据治理流程，非 replay 型，不依赖去重假设）。
- **过期行为（冻结）**：deadline 过期（进入点判定）→ 输出态 5 恢复超时（blocked + `settlement_deadline_expired` code + fence 离开 erasing + 禁自动重试）；人工 reconcile 可经运维入口显式执行 lookup 并以 evidence 落账（owner-scoped，同 settlement 写域）——人工路径不受 deadline 约束。

#### S5-C-5 裁决 3：receipt lookup 语义三态（单独裁决，族 I 部分收口）

- **语义三态（冻结）**：(a) **有 evidence**——lookup 返回可验证 evidence（重算 receipt_digest 匹配）→ success 收场，**禁止再 replay**；(b) **可证明未执行**——adapter 显式返回否定证据（「该 key 从未收到 delete/destroy」）→ 可证明未发送（输出态 2，reopenable）；(c) **不可判定**——`None` 或无否定证明能力 → outcome_unknown（输出态 3），**禁止据此再次调用 delete/destroy**（不得用无幂等保证的重复删除掩盖不确定）。**三态语义以 frozen descriptor 的 `receipt_lookup_semantics_version` 为准（S5-C-3）**——语义版本变化 = descriptor 字段变化 = owner_version bump，旧 settlement 仍按旧语义版本判定。
- **现有 `receipt_lookup -> str | None`（冻结映射）**：`None` **只能**映射为 (c) 不可判定，**禁止**解释为「未执行」；(b) 需要 adapter 侧显式否定证据类型（Protocol 扩展，随族 G 回填归属登记），扩展落地前 lookup 结果只落 (a)/(c)。
- lookup 只读无副作用、**可安全重放**（任何时刻可执行，不受 S5-C-4 deadline 限制）；lookup 结果的 owner-scoped 落账由 fence/checkpoint CAS **单写收敛**（S5-C-7 结果落账互斥层，同输入重放幂等，无状态分叉）——**不冻结「自动恢复循环内 lookup 至多一次」的次数限制**（无持久 **lookup 次数**载体时次数限制不可判定——`checkpoint.attempt` 只承载 delete invocation 计数，不承载 lookup 次数；重放安全由三态语义 + CAS 收敛承担）。

#### S5-C-6 裁决 4：replay-only adapter（单独裁决，族 I 收口）

- **定义**：`supports_receipt_lookup == False ∧ supports_idempotent_replay == True`。
- **deadline 内**：仅当 durable idempotency 保证成立（S5-C-4 去重窗口 ≥ deadline + 重放返回可验证 evidence/明确 unknown）才 replay；replay 成功 → 输出态 1；replay 返回 unknown → 输出态 3 终态（**单次恢复周期至多一次 replay 尝试**，unknown 后不得再次 replay）。
- **deadline 过期** → 输出态 5 恢复超时（`settlement_deadline_expired` code，reconcile-only），**不 replay、不落零动作循环**。
- **双支持 adapter（replay ∧ lookup 均 True）**：优先 lookup（三态判定）→ (a) 收场；(c) 时若 replay 条件成立才 replay，否则输出态 3。
- **零动作死路消除（族 I 收口）**：每一输入态都落在 S5-C-1 六输出态之一；不存在「不 lookup、不 replay、不落账」的悬空分支——S5-B-7 旧文「双支持优先 lookup 与承诺节冲突」「降级 reconcile 是零动作死路」由三态语义 + 全函数输出态消解。

#### S5-C-7 并发与写者（族 B/C/D 收口）

**统一锁序（冻结，逐实际方法核对）**：全局前缀沿用 S5-A-4 S1 不变量（Conversation 行锁 = coordination 域全局互斥）并补 settlement 侧核对：

| 进入点（代码事实） | 锁序 |
|-------------------|------|
| external Tx1（external_ref_erasure_participant.py:407-646） | Conversation FOR UPDATE → owner advisory → fence FOR UPDATE → operation FOR UPDATE（`_mark_operation_running`）→ 集合 advisory（最内层）→ checkpoint（推进 `erasing`） |
| external Tx2（:670-853） | Conversation → owner advisory → fence → checkpoint（`_load_verified_checkpoint`）→ operation FOR UPDATE（`_load_verified_operation`）→ 集合锁 |
| runtime Tx1/Tx2（runtime_erasure_participant.py:431-669 / :688+，与 external 同形） | 同 external Tx1/Tx2 行（Tx1 先 operation 后 checkpoint；Tx2 先 checkpoint 后 operation） |
| transport 单事务（transport_erasure_participant.py 主入口） | Conversation → owner advisory → fence → operation → 集合锁 → 源行/正文；ACK 同事务 |
| ACK-lost repair（external erased-fence 分支 :432-479；transport 同形分支 transport_erasure_participant.py:739-783） | Conversation → owner advisory → fence → scan → `_repair_checkpoint_if_pending`（内部 operation FOR UPDATE → checkpoint 写） |
| **scheduler settlement（新进入点，本契约登记）** | Conversation → owner advisory → fence FOR UPDATE → operation FOR UPDATE（frozen-snapshot 校验，S5-C-2）→ checkpoint FOR UPDATE |

- **冻结不变量**：checkpoint↔operation 相对顺序在既有方法内不一致（Tx1 先 operation 后 checkpoint；Tx2 先 checkpoint 后 operation），因二者同事务且都在「Conversation + owner advisory + fence」全局前缀之后，不构成跨事务 AB-BA；**任何新 settlement 进入点不得引入「先 checkpoint 后 fence」「先 operation 后 advisory」的逆序**；scheduler settlement 固定 operation 先于 checkpoint（与 coordinator 序一致）。
- **adapter 窗口互斥（冻结，互斥机制归因修正——族 B 首轮返修）**：代码事实——adapter 的 delete/destroy 调用只发生在 participant 窗口期（Tx1 commit 后、**无锁上下文**，E-2 禁令；external_ref_erasure_participant.py:648-668），**live Tx2 不调用 adapter**（:670+ 只做结果落账）；settlement 恢复的 adapter 调用只有 lookup/replay 两种（S5-C-5/6）。因此本契约**不承诺**「任意时刻至多一个进入点在 adapter 调用中」的锁互斥（窗口 token 在 Tx1 commit 后稳定，第二进入点锁内重验同 token 可通过，锁互斥不可达成）。真实排他机制分两层冻结：
  1. **结果落账互斥**：fence/checkpoint/ledger 的结果写由 Conversation 行锁（三进入点第一锁）+ owner advisory + fence FOR UPDATE CAS 串行——同 owner 的结果落账**至多一个写者成功**（fence CAS 唯一性），败者零写幂等返回。
  2. **adapter 调用互斥（同 invocation 语义）**：防重复副作用的保证 = **同 idempotency key**（跨 takeover 稳定、由 S5-C-3 解析的旧 adapter 身份派生，E-2b 冻结）+ **进入前精确 token 重验**（S5-C-2 校验集 + fence/checkpoint 态，`expire_all` 后重读已提交行，E-2a 形态）——token 不符的进入点 fail closed **零 adapter 调用**；同 token 的并发进入点由同 key 去重收敛为同一 invocation，结果由第 1 层 CAS 收敛为单写者。
- **erasing→blocked 边（族 C 收口，对 S4-F 的显式变更登记）**：状态机边已存在（`_FENCE_ALLOWED_TRANSITIONS` 含 (ERASING, BLOCKED)，erasure_repository.py:96-105）；缺失的是 **4 个非 core owner（`workspace.transport.v1`/`execution.transport.v1`/`external.payload.v1`/`runtime.private.v1`）的写者**——现码 blocked/unknown 落账不写 fence（external Tx2 `_record_blocked` 分支、transport final-scan 分支 :984-1004 代码事实），fence 永留 `erasing`、quiesce 永不收敛。**冻结**：settlement 收口（participant Tx2 / takeover replay / scheduler settlement 的 blocked/unknown 落账）对 4 非 core owner 写 fence `erasing→blocked`——**对 S4-F「Tx2 不碰 fence」冻结行为的显式变更，本契约登记**。**core owner（`workspace.core.v1`/`execution.core.v1`）不适用本写者**——其 scan-nonzero 落账已写 fence `erasing→blocked`（workspace_erasure_participant.py:504-513、execution_erasure_participant.py:741-748，无跨事务窗口）。CAS token = `expected_state=ERASING + expected_revision=锁内 fence.revision + purge_revision=旧 operation 冻结值 + hold_revision=锁内 Conversation.hold_revision` + owner_version 校验基准 = frozen snapshot（S5-C-2 第 6 条 settlement 专用路径，保留其余全部守卫）。已落账 blocked（reason 已持久）时按 S5-C-1 已落账收敛规则**只写 fence、checkpoint 零修改**。**mutation test**：删该写 → 断言 fence 卡 `erasing` + quiesce 不收敛 → 红；错 token（stale revision / 错 purge_revision）→ 断言 CAS 拒绝零写 → 红（S5-C-8 行 3）。
- **ACK-lost repair 第三路径（族 D 收口）**：settlement 第三条路径（与 Tx2 收口、同 revision crash replay 并列）。收口：同一 `purge_revision`（S4-F 族 B 门禁保留）下重验 `fence.ack_digest` 存在 + final scan 零 → checkpoint `→acked`（ack_digest = fence.ack_digest、checkpoint_digest = final scan digest、清 `reason_code`），fence 零修改。**repair 的 operation 校验同走 S5-C-2 frozen-snapshot 基准**（drift + ACK-lost 组合必须可收口），`expected_operation_revision` 重基准 = **锁内当前 `operation.revision`**（S5-A-4 先例——coordinator 写 G1/G2 blocked 已 bump revision，调用方旧 revision 必 fail；锁内重读后按 frozen-snapshot 校验放行，CAS 谓词同步改为锁内基线）。**I2 后只修 checkpoint**：不得写 operation.state/failure_code/revision、不得写 Conversation.purge_state（现码 `_repair_checkpoint_if_pending` 的三类共享写由 S5-A-7 ① 在 I2 移除）；**不得清 drift failure_code**（G1/G2-blocked operation 的 failure_code 归 coordinator，repair 不得清）。证据不符（scan 非零 / `ack_digest` 缺失 / digest 不一致）→ fail closed 具名 reconcile（dirty-data，数据治理流程），不自动重试。

#### S5-C-8 反例矩阵（冻结，scheduler slice 实现 PR 逐项落地；承接 S5-B-9 行 14/19/20/24）

| # | 反例 | 触发 | 期望行为 | 判别点 |
|---|------|------|---------|--------|
| 1 | drift 下 settlement 收口（族 A；承接 S5-B-9 行 14） | G1/G2 drift 后 Tx2 收口 blocked/unknown | settlement 以 frozen-snapshot 校验放行（不 raise），checkpoint blocked + fence `erasing→blocked`，quiesce 收敛 | 断言 fence 离开 erasing + 零 operation/Conversation 写；变异「settlement 仍用当前 registry digest/hold 等值校验」→红 |
| 2 | 禁新 Tx1（族 A，作用域 = drift 后旧 operation 的 settlement 通道） | drift 后旧 revision 的 settlement 通道尝试新 Tx1（attempt+1 / 新 intent / pending→erasing） | 拒绝，零写、零 adapter 调用 | 变异「settlement 通道内 checkpoint 判别放宽（pending/blocked 放行进 erasing）」→红；新 operation 正常入口不受限（正向断言保留） |
| 3 | fence erasing→blocked（族 C） | blocked/unknown 落账 | fence 写 `erasing→blocked`；quiesce 可收敛 | 变异「删 settlement fence 写」→红（fence 卡 erasing）；变异「stale revision 写」→红（CAS 拒绝零写） |
| 4 | ACK-lost repair 第三路径（族 D） | fence=erased + checkpoint=pending（同 revision） | repair 只修 checkpoint→acked；fence 零修改；不清 failure_code | 变异「repair 清 operation.failure_code / 写 purge_state」→红 |
| 5 | receipt 三态（裁决 3；承接 S5-B-9 行 19） | lookup None / 否定证据 / evidence | None→不可判定→禁再次 delete；否定证据→可证明未发送；evidence→success 禁 replay | 变异「None 视为未执行再次 delete」→红；变异「evidence 后仍 replay」→红 |
| 6 | replay 承诺判定（族 H；承接 S5-B-9 行 20） | 去重窗口 < deadline；重放返回不可验证成功 | 不 replay（不用于 settlement 自动恢复）；不可验证成功拒绝落账 | 变异「窗口不足仍 replay」→红 |
| 7 | replay-only 收敛（裁决 4；族 I） | 无 lookup adapter：deadline 内 replay unknown / deadline 过期 | replay unknown → outcome_unknown 终态（零二次 replay）；过期 → 恢复超时具名态 | 变异「unknown 后自动再 replay 形成循环」→红 |
| 8 | 恢复超时（裁决 2；承接 S5-B-9 行 24） | deadline 过期（进入点判定） | blocked + `settlement_deadline_expired` 独立 code + fence blocked + 零自动重试（终态后不重算，code 落账固化） | 变异「过期仍自动 replay/lookup」→红 |
| 9 | adapter 不可解析（裁决 1；承接 S5-B-9 行 24 半程） | snapshot (owner_key, owner_version) 不在历史 resolver | fail closed：零 adapter 调用 + blocked + `adapter_unresolvable` code + reconcile-only | 变异「fallback 当前已安装 adapter」→红 |
| 10 | 三进入点：结果落账单写者 + token 重验（互斥机制归因修正） | live Tx2 与 scheduler settlement 双连接并发同 owner | 结果落账单写者（fence CAS 唯一性）；token 不符进入点零 adapter 调用；同 token 进入点同 idempotency key 去重收敛 | 变异「进入点删除精确 token 重验（attempt/intent 等值）」→红（不同 invocation 产生第二次 adapter 调用） |
| 11 | takeover replay 精确 token | takeover 后 attempt/intent 不符 | 拒绝续做，零 adapter 调用 | 变异「token 校验放宽」→红 |
| 12 | settlement 幂等 | 同输入重放 settlement | 同一 owner-scoped 结果，零跨 owner 副作用 | 变异「重放跳过已收口 fence/checkpoint 白名单判定（对已 blocked fence 重写、对已 acked checkpoint 重写第二份）」→红 |
| 13 | reconcile 例外登记（fence 收敛例外条款） | settlement fence 写永久失败 | 具名 reconcile（checkpoint blocked + 进入时判定的输出态对应持久 code——态 2/3/5/6 各自身 code，态 1/4 不适用见例外条款 + 运维视图可查）+ 零自动重试 | 变异「例外态自动重试」→红 |
| 14 | frozen descriptor 语义（裁决 1 强不变量） | Tx1 后部署新 registry 版本（当前 deadline/adapter descriptor 变化），旧 settlement 收口 | 旧 settlement 仍使用 frozen owner-version descriptor（旧 adapter 身份/旧 deadline/旧去重窗口）；当前版本变化不影响旧收口 | 变异「settlement 用当前 registry 版本 descriptor」→红（收口事实随部署漂移） |
| 15 | 输出态 reason 精确判别（纠偏批次） | checkpoint 转 blocked（终态，`updated_at` 已更新）后按 reason 识别输出态 | reason code 精确识别 3/5/6（`outcome_unknown` / `settlement_deadline_expired` / `adapter_unresolvable` 三码互异，逐 owner 变体） | 参数化三态断言 reason 互异且稳定；变异「3/5/6 共用同一 code」→红 |
| 16 | lookup 重放无分叉（纠偏批次） | 同一次 lookup 在落账前崩溃，重放同输入 | 同一 owner-scoped 结果（fence/checkpoint CAS 单写收敛），无状态分叉、零跨 owner 副作用 | 崩溃注入后重放断言终态一致；变异「lookup 结果落账去 CAS / 第二次写入不同值」→红 |

> 反例矩阵复用 S4-F 已冻结注入机制（真实 PostgreSQL、双连接 `asyncio.gather`、DB 篡改、崩溃注入、fake adapter 故障注入）；settlement 测试归属 scheduler slice 实现 PR。行 1-4/8/9/13 的 fence 收敛断言与 S5-B quiesce 门禁（S5-B-9 行 13）交叉验证。

#### S5-C-9 接口、变更登记与前向指针

- **对 S5-B（#564）**：依赖接口 =「rebuild 输入必须已满足 S5-C settlement terminal contract」（已在 #564 scope-cleanup 落地）。**S5-B rebuild 输入映射（冻结，逐项唯一——每个 S5-C terminal fact 恰映射一行）**：

| S5-C terminal fact | S5-B-2 case A rebuild 输入（checkpoint × fence） | rebuild 动作 |
|--------------------|------------------------------------------------|--------------|
| 输出态 1 success | `acked` × `erased` | lineage 可继承（S5-B-3 重验） |
| 输出态 2 可证明未发送 | `blocked` + `erase_timeout`/`adapter_unavailable`/scan 族 × `blocked` | 义务重开 `pending` |
| 输出态 3 outcome_unknown | `blocked` + `outcome_unknown` × `blocked` | **carry，不重开 pending** |
| 输出态 4 ACK-lost repair | `acked` × `erased`（fence 零修改） | 同输出态 1（lineage 继承） |
| 输出态 5 恢复超时 | `blocked` + `settlement_deadline_expired` × `blocked` | **carry，不重开 pending** |
| 输出态 6 adapter 不可解析 | `blocked` + `adapter_unresolvable` × `blocked` | **carry，不重开 pending** |
| 已落账 blocked（pre-fix 遗留，S5-C-1 已落账收敛） | 按已持久 reason 归上四类 blocked 行之一 | 同对应行（fence 已收敛） |
| failed（非矛盾，S5-C-1 failed 收敛） | `failed` × `blocked`/`active` | failed carry（scheduler 重试预算语义） |
| failed × `erased` 矛盾 / 其他未知·NULL reason | 矛盾/不可判定（S5-B-2 dirty-data 行） | **dirty-data fail closed**，禁止普通 carry/重开 |

- **对 S4-F 的显式变更（本契约登记，两项）**：①「Tx2 不碰 fence」→ settlement 收口写 fence `erasing→blocked`（4 非 core owner，S5-C-7）；② erased-fence repair 枚举为 settlement 第三路径（I2 后仅修 checkpoint，S5-C-7）。
- **对 S5-A**：S5-A-4 Tx2 重验集在 drift 下的 settlement 例外（frozen-snapshot 基准，S5-C-2 六条校验条件，其中三条硬绑定 = 旧 operation 仍为 top revision / 精确 attempt·intent·fence token / 禁新 Tx1；含 S5-C-7 ACK-lost repair 的 revision 重基准）；S5-A-1 写者表补「settlement fence `erasing→blocked` 写者（4 非 core owner）+ scheduler settlement 进入点」；**S5-A-0 reason 值域 7 层内新增 4 个 code**（external/runtime × `settlement_deadline_expired`/`adapter_unresolvable`，S5-C-1 输出态 5/6）。**三项补登记已在本 PR 展开为 S5-B-8 清单第 9/10/11 项增补**——**已随 #564 squash 合并入 root #563（`bb792547`）生效**（历史动作已完成；本契约正文随合并生效，不再存在「待回填」状态）。
- **实现回填归属（族 G/H，scheduler slice 前置项）**：external/runtime adapter Protocol docstring 幂等矛盾消除 + receipt 三态/否定证据类型扩展 + 版本化 adapter resolver（S5-C-3，返回 immutable RecoveryDescriptor + descriptor/路由变化必须 bump owner_version 强不变量）+ **scheduler 写 failed 时同步收敛 fence（S5-C-1 failed 收敛）** → scheduler slice 实现 PR 落地；本契约不启动实现/migration。
- **收尾约束（当时状态，历史叙述）**：#565 合并前不回 #563（保持 `efde24e4`）、不处理 S5-B 族 E/F、不转 Ready、不评分、不合并、不启动 I1/I2/S5 实现/S6/C1——**均已按序完成**：#565（评分 92）→ #564 收口批次（族 E/F 完成）→ #564（评分 87）→ 合并入 root #563（`bb792547`）。

#### S5-C-10 三面复审记录（Draft 状态，未 merge）

**首轮三面原始计数（保留不覆盖；#564 七族 P1 与三轮历史计数保留在 #564 S5-B-10/11）**：数据/状态机 P0=0/P1=3/P2=5/P3=1 + 并发/锁序 P0=0/P1=3/P2=5/P3=2 + 测试/运维 P0=1/P1=1/P2=5/P3=1 → **合计 P0=1/P1=7/P2=15/P3=4**（27 findings）。

**首轮根因族（去重 11 族，一次统一返修，逐条已核验代码事实）**：

1. **互斥机制归因错误（P0-1/P1-1，族 B 再现）**：adapter 调用在无锁上下文，「排他由 fence CAS + Conversation 锁承担」是伪保证（窗口 token 在 Tx1 commit 后稳定，第二进入点重验同 token 可通过）；live Tx2 不调 adapter（只写结果）；row 10 mutation「去 Conversation 首锁」判别点不成立。→ S5-C-7 互斥段重写（结果落账互斥 + 同 idempotency key/token 重验两层）+ row 10 重写。
2. **drift 绕过集不完整（P1-2/P1-3 并发面，族 A 再现）**：漏 `_load_verified_checkpoint` 的 capability 等值校验（case E 下必 fail）；ACK-lost repair 路径 frozen-snapshot 基准 + revision CAS 重基准未冻结（coordinator 写 G1/G2 blocked 已 bump revision）。→ S5-C-2 第 4 条 checkpoint 侧同基准 + S5-C-7 repair 段重基准。
3. **状态机全函数缺口（P1-1/P1-2 数据面 + P1-2 测试面，族 C 收口落空）**：post-window blocked（scan-nonzero）无输出行可映射；transport owner 的 settlement 输入无输出态；`failed` 入输入域但无输出行；已 blocked 的 reason 覆写语义未冻结。→ S5-C-1 态 2 判定扩展（transport scan-nonzero）+ 已落账收敛规则（只写 fence、reason 不覆写）+ failed 收敛兜底 + 输入态 2 限定 4 非 core owner。
4. **禁新 Tx1 作用域未限定（P1-3 数据面）**：「pending/blocked 一律不得推进 erasing」按字面杀 S5-A-3 显式重试 / S5-B-2 重开 pending 路径。→ 限定「drift 后旧 operation 的 settlement 通道」+ row 2 判别面修正。
5. **锁序表覆盖不全（P2-2/P2-7/P3-1）**：缺 runtime Tx1/Tx2 与 transport repair 分支。→ S5-C-7 表补两行。
6. **归因/载体精度（P2-3/P2-1 并发 + P2-1/P2-3 数据 + P3-2 + P2-5）**：core 不适用归因错误（真实原因 = core scan-nonzero 落账已写 fence erasing→blocked）；deadline 载体对 transport owner 不成立；输出态 5/6 适用域未限定；lease_epoch 基准未钉。→ 逐处修正（S5-C-1/4/7 + S5-C-2 第 3 条）。
7. **绕过边界/reason 值域未钉（P2-5/P2-2 数据）**：settlement 专用 fence 路径未明示保留 `transition_fence_state` 其余守卫；例外条款 reason 未钉 12 层域。→ S5-C-2 第 6 条明示保留全部守卫 + S5-C-1 例外条款 reason 钉 outcome_unknown 族（7 层域）。
8. **裁决不完整（P2-4 数据）**：resolver 命中但旧 adapter 实现不可加载未映射。→ S5-C-3 延展输出态 6。
9. **可测性/判别力（P2-3/P2-4 测试）**：deadline 测试注入边界未冻结（S5-A-4 时钟先例未沿用）；row 12 mutation 未具名代码级。→ S5-C-4 注入边界 + row 12 具名 mutation。
10. **接口登记载体脱节（P2-5/P2-6 测试）**：「三条绕过条件」与 S5-C-2 六条计数不符；S5-A 两项补登记未入 S5-B-8 回填载体。→ S5-C-9 统一计数表述 + 绑定「#564 前向指针回填写入 S5-B-8 第 9/10 项」。
11. **工作台保留（P3-8）**：S5-A 停放状态踪迹丢失。→ current-work S5-B 卡补回。

**返修**：commit（本次统一返修 commit）——11 根因族一次返修，S5-C-1/2/3/4/7/8/9 逐节落地。

**定向复核（返修 diff 逐族核对，不重开三面）**：11 族逐条核对全部落地（互斥两层重写、绕过集 checkpoint 侧补齐、已落账/failed 收敛、禁新 Tx1 作用域、锁序表两行、归因/载体修正、fence 路径守卫与 reason 域钉死、resolver 延展、注入边界与具名 mutation、S5-B-8 载体绑定、S5-A 踪迹补回）；复核发现 2 处返修引入的交叉引用缺口（S5-C-9 failed 收敛前置项缺失、ACK-lost repair revision 重基准未入 S5-A 登记）→ 已修正（P2 级，非状态机级）。**无新状态机级 P1，不触发上层架构裁决**。

**Ready 前事实载体纠偏批次（定向批次，不重开完整三面）**：

1. **历史 resolver 返回完整 immutable RecoveryDescriptor**（S5-C-3）：`adapter_key`/`adapter_version`/`supports_idempotent_replay`/`dedup_window`/`receipt_lookup_semantics_version`/`settlement_deadline` 六字段；**强不变量** = descriptor 任一字段或 adapter 路由变化必须 bump owner_version、历史 descriptor 与实现装配不得删除。
2. **deadline 判定窗口**（S5-C-4）：判定只在 checkpoint 仍 `erasing`、本 settlement 尚未修改 `checkpoint.updated_at` 时执行（进入点判定）；删除「终态后可由 `updated_at` 重算」宣称；判定结果以独立 reason code 落账固化。
3. **输出态 3/5/6 独立持久 reason code**（S5-C-1）：均归 S5-A level 7；态 3 用现有 `purge_blocked_by_*_outcome_unknown`，态 5/6 新增 `purge_blocked_by_*_settlement_deadline_expired` / `purge_blocked_by_*_adapter_unresolvable`（external/runtime 各一，共 4 新 code）；S5-A 回填项登记（S5-B-8 第 11 项增补），不修改 #563。fence 收敛例外条款 reason 映射同步改为**按进入时判定的输出态全函数**（态 2 → 自身 reopenable code 不降级；态 3/5/6 → 各自独立 code；态 1/4 不适用）。
4. **删除「自动恢复循环 lookup 至多一次」承诺**（S5-C-5）：lookup 可安全重放；owner-scoped 结果由 fence/checkpoint CAS 单写收敛；不冻结次数限制（无持久 attempt 载体时次数限制不可判定）。
5. **补三条反例**（S5-C-8 行 14/15/16）：frozen descriptor 语义（部署新版本不影响旧收口）、终态后 reason 精确判别输出态、lookup 落账前崩溃重放无分叉。

**独立定向复核（本批次 commit 后执行，不重开完整三面）**：六项指令逐项核对——①✓ ②✓ ⑤✓ ⑥✓；③④主文落地但 **S5-C-8 行 8 残留旧表述**（「可重算」+ outcome_unknown reason，P1）；批次改窄例外条款 reason 映射致**偏函数缺口**（态 1/2 无码可写，P1）；另 P2×3（descriptor 缺 lookup 能力位映射声明、「无持久 attempt 载体」措辞不精确、已落账归类缺其他/NULL reason 兜底）+ P3×3（行 9 未具名新 code、S5-C-6 旧措辞残留、批次记录未登记例外条款映射变更）。**补正 commit**：行 8 改新 code + 终态不重算；例外条款 reason 映射改全函数（态 2 不降级、态 1/4 不适用）；`receipt_lookup_semantics_version` 非空 ⇔ supports_receipt_lookup 映射声明；「lookup 次数载体」措辞；归类兜底；行 9 具名；S5-C-6 措辞；记录登记。复核员判定两条 P1 均为**文档契约层事实载体问题（残留/回归）**，不触发上层架构裁决；补正后六项事实载体问题清零（补正 diff 逐项核对）。

**Ready 前 stacked 边界纠偏批次（定向批次，不重开完整三面、不重开单行 fence + 双事务架构裁决；#564 base 保持 `da57b947`、#565 边界修正全部落地在本 PR）**：

1. **S5-B-2 reason 分区（四命名域 + dirty 兜底，废除「其他 participant reason」catch-all）**：`erase_timeout`/`adapter_unavailable`/scan 族 → `pending`；`outcome_unknown`/`settlement_deadline_expired`/`adapter_unresolvable`（S5-C 输出态 3/5/6）→ blocked carry 禁止重开；pre-window gate reason（具名域：legal_hold/unresolved_action/conversation_scope/owner_unavailable/operator_suppressed）→ `pending`（S5-B-5 hold-release 序列依赖，具名非 catch-all）；其他未知/NULL → dirty-data fail closed/reconcile，禁止落入通用 pending 分支。`failed × erased` 矛盾组合 → dirty-data fail closed（不得按普通 failed carry 继续 rebuild）。
2. **S5-B-6 settlement 幂等收窄**：删除「Tx2/crash replay 天然幂等」具体机制宣称，只引用 S5-C descriptor/token 重验、lookup/replay 与 fence/checkpoint CAS 契约。
3. **S5-B-8 消费 S5-C terminal facts**：item 2「settlement outcome 三分类」旧表述由 S5-C 六输出态/已落账/failed 收敛替代；**RecoveryDescriptor 六字段及历史装配归 scheduler slice 前置项（settlement 路径专用），不误登记为 reducer/calculator 输入**；第 9/10/11 项增补展开（frozen-snapshot 基准 + ACK-lost revision 重基准 / settlement fence 写者 / 4 个 level-7 reason code）。
4. **S5-C-9 rebuild 输入映射表**：六输出态 + 已落账 blocked + failed/dirty-data **逐项唯一**映射到 S5-B-2 case A。
5. S5-C-9 对 S5-A 登记同步（三项补登记已在 S5-B-8 展开）+ current-work 同步。

**边界审计计数（独立 stacked 接口定向复核；首轮三面与事实载体纠偏历史计数保留不覆盖）**：**P0=0/P1=0/P2=3/P3=3**。四项结论：①六输出态 + 已落账 + failed/dirty 共 9 个 terminal fact 逐项唯一映射（无缺漏无歧义；`settlement_deadline_expired`/`adapter_unresolvable` 在硬约束/carry/映射三处逐字一致）；②blocked reason 空间与 S5-A-0 12 层逐一对号全覆盖，checkpoint×fence 组合每组合恰一行，hold-release 序列仍通；③#564 边界无具体 settlement 机制裁决残留（S5-B-1/6/7 全部为消费/引用 S5-C 形态）；④S5-B-8 第 9/10/11 项与 S5-C-2/7/1 逐项对应无缺无多，RecoveryDescriptor 正确排除出 reducer/calculator 输入。P2×3（已落账「其他/NULL」与 pre-window 具名域归类分叉待核、case E 分态行未具名输出态 5/6、S5-B-0 item 7 末句建议补 S5-C-1 交叉引用）+ P3×3（记号/措辞精度）为后续精度项，不计入本轮清零要求。

**状态**：Draft（当时状态，历史叙述）。按任务指令：不回 #563、不处理 S5-B 族 E/F、不转 Ready、不评分、不合并、不启动实现或 migration——**均已按序完成**：#565 已 squash 合并入 #564（2026-08-14，评分 92），再随 #564（评分 87）合并入 root #563（`bb792547`），尚未进入 main。

> **merged-boundary（2026-08-14）**：#563 root squash merge `6f86f959`（评分 86）；子 PR #564（评分 87）/#565（评分 92）已随 root 进入 main；**R1-S5-A/B/C 三层契约冻结完成**；REQ-047 / R1-S5 implementation conformance follow-up 保留（P2×5/P3×3 精度项，不宣称已修复）；**尚未实现** I1/I2/scheduler/运维 API/S6/C1——本 merged-boundary 是契约冻结的完成边界，不是 S5 实现完成。

### R1-S5：Legal hold、Scheduler 与运维闭环

**复杂度/执行**：极高，Sol `xhigh`；人工数据/安全签字。

交付：

- [ ] 数据治理 API：create/release/list legal hold，显式 permission + purpose + reason code，first decision/CAS 审计。
- [ ] `conversation_purge_scheduler` 使用 PostgreSQL clock、bounded claim lease、tenant 限流和指数退避。
- [ ] operation inspect/retry/reconcile 内部 API，只返回状态/digest/reason；没有 force-skip ACK。
- [ ] owner 顺序执行、checkpoint、部分失败重试、registry/hold revision 变化新建 revision。
- [ ] 指标与脱敏日志：queue age、owner latency/attempt、blocked reason、late writes、retention lag、external orphan。

明确不做：前端数据治理页面、任意角色隐式读取正文。

验证：hold/purge race、hold expiry/release、lease takeover、重复 scheduler、无权限/跨 tenant、日志 payload 扫描。

### R1-S6：Retention clocks 与真实故障矩阵

**复杂度/执行**：极高，Sol `xhigh` 主修；第二模型 `max` 仅做对抗审查，不修改核心代码。

交付：

- [ ] `run_event_retention` 完成 payload expiry、连续 envelope prune 与 `first_available_event_seq` 更新。
- [ ] `run_audit_retention` 完成 365 天 prune，服从 hold、非终态、unknown outcome 和业务保留。
- [ ] 建立 owner/writer conformance suite，并列举所有已安装 Conversation-owned writer；遗漏 writer 使门禁失败。
- [ ] 真实 PostgreSQL 故障注入覆盖 Worker kill、lease/ACK 丢失、部分 ACK、seq gap、outbox claim、hold revision 和 writer/purge pause race。
- [ ] 运行 body/ref orphan 巡检：tenant mismatch、digest conflict、event gap、unknown ref scheme、missing fence/owner scope。
- [ ] 演练 expand -> writer capability -> batched backfill -> verify -> canary enable；旧 Writer 在线或 backfill 未完成时 scheduler fail closed。
- [ ] 建立备份恢复门禁：从旧快照恢复后先重放独立 erasure ledger/body scan，再开放服务；无法本地跑基础设施 drill 时明确登记生产门禁，不冒充已验证。

退出条件：R1-AC1..12 全部有当前提交证据；fake Runtime/external adapter 只标 contract-tested。


### R1-S5-D：Scheduler 契约（contract-first，纯文档；承接 S5-A-10 S6 拆分裁决 + S5-B/C 前置契约项）

> Status: Draft（本 PR 仅纯文档契约冻结；不命名 I3，不写代码/测试/schema/migration/registry/CI，不启动任何 Scheduler 实现/S6/C1）
> 依据：S5-A-10 S6 拆分裁决、S5-B（Option D quiesce-and-finalize、rebuild/seeding/lineage、S5-B-6 并发与幂等）、S5-C（settlement-only adapter recovery、六输出态、RecoveryDescriptor、ACK-lost repair）、I1/I2 merged-boundary（#567/#569 已并入 main）。
> 本契约冻结 scheduler 全函数状态机、统一锁序/事务边界/崩溃恢复点、写者所有权矩阵、单风险域实现 PR 拆分与反例矩阵；**不复制** S5-B/S5-C 已冻结规则，全部以精确指针引用。首轮三面复审原始计数（保留不覆盖）：数据/状态机 P0=0/P1=2/P2=12/P3=7 + 并发/锁序 P0=0/P1=3/P2=4/P3=3 + 测试/运维/文档 P0=0/P1=2/P2=5/P3=4 → 合计 P0=0/P1=7/P2=21/P3=14，按族 A~G 统一返修一次（本版）。

#### S5-SCH-0 横向事实对账（冻结，截至 main@ca0b64a0）

**operation（agent_conversation_purges）写者全集**：
| 写者 | 迁移/写值 | 事务 |
|------|----------|------|
| `create_purge_operation`（repository:742；**生产唯一调用方 = scheduler claim/rebuild**） | `scheduled` + registry/retention/hold snapshot | 调用方事务 |
| `cancel_scheduled_operations_for_restore`（repository:809） | `scheduled → cancelled`（restore 生命周期，Conversation 锁内） | 调用方事务 |
| transactional projection coordinator（`_apply_projection`） | `scheduled/running/blocked → running/blocked/failed/completed` + failure_code/started_at/completed_at + revision+1；零写六元组；终态覆盖禁令 | 独立事务（Conversation-first） |
| **scheduler（本契约新增，唯一产生者）** | `lease_epoch` 单调推进（claim/takeover/续期 CAS）；`next_retry_at` 退避；rebuild 新 operation（新 purge_revision） | 见 S5-SCH-2 自有写事务清单 |

**checkpoint（agent_conversation_purge_owners）写者全集**：
`create_owner_checkpoint`（`pending`，repository:886）· participant 三方法（`blocked/acked`；external/runtime Tx1 加 `erasing`）· **scheduler 写 `failed`**（重试预算耗尽，S5-SCH-1.4；优先级 5 唯一产生者，S5-A-2 冻结）· rebuild seeding（S5-B-3 阶段 1，一次事务）。coordinator 不写 checkpoint（S5-A-1 冻结，derived-conflict 裁决）。**编排方不写 blocked**——「记 blocked」一律经 participant 入口（`_record_blocked`），编排方只写 `failed` 与 `next_retry_at`。

**fence（agent_erasure_fences）写者全集**：
participant（ensure/transition，owner lock 内）· **settlement fence `erasing→blocked` 写者（4 非 core owner，S5-C-7）**· **rebuild 的 case-E versioned fence migration（`fence.owner_version` 单调推进，仅 `active` fence，owner lock + fence FOR UPDATE 内，S5-B-2 case E / S5-B-4）**。scheduler **不写 fence 状态机边**（state 转移仅经 settlement/participant；case-E `owner_version` 迁移为唯一例外）。

**external ledger / runtime binding 写者**：participant（registered→erased/blocked/unknown）· settlement（S5-C-1 输出态落账）。

**Conversation purge_state/purged_at 写者**：coordinator（`running/blocked/failed/completed` + `purged_at`，S5-A-1）；delete/restore 生命周期（`not_scheduled/scheduled` + `purge_revision`）。**零 checkpoint `scheduled` 投影唯一写者 = 生命周期**（S5-SCH-5 正式冻结，REQ-047 分流）。

**I1/I2 接口（冻结事实）**：`create_legal_hold`/`release_legal_hold`（Conversation-first + 同事务 SQL 原子 bump + tenant-scoped 锁谓词 + completed 拦截）；coordinator `aggregate_projection`（Conversation-first + operation 三键限定 + 锁内 CAS + 零写 + 旧 revision 门禁 + 时间归一化 + state×reason 校验）；participant `_load_verified_operation`（fencing 全集 + 旧 revision 门禁；operation 锁查询三键收窄为 REQ-047 实现 PR 项，S5-SCH-5，开工时由工作台指定承接 PR）。

**组合根可达性**：六 participant erase 入口生产不可达（`test_six_erase_entries_unreachable_from_production_composition` 静态守卫，test_s5i2_production_wiring_boundary.py，S5-A-5 滚动发布前提）；coordinator 无生产调用方（S5-A-5 编排触发点由本契约 SCH-B 接线，周期全量重算触发见 S5-SCH-1.3b）；registry `erase_available` 值域 = 4 True / 2 False（生产）。

**PostgreSQL 锁序（S1 不变量，冻结）**：Conversation 行锁 = 本 coordination 域全局互斥——任何取 operation/fence/checkpoint 行锁的事务必须先取 Conversation 行锁；participant `Conversation → owner advisory → fence FOR UPDATE → operation → checkpoint`；coordinator `Conversation → operation → checkpoints（owner_key 序）→ fence 只读 → scan → CAS`；Tx2 的 checkpoint→operation 逆序子序由 Conversation 首锁保护不成环（S5-A-4 已冻结并测试）；delete/restore 仅 Conversation；I1 hold `Conversation → hold 行`。时钟一律 `clock_timestamp()` 落库。`lease_epoch` 的 CHECK 锁非负（models.py:656），**单调推进由 claim/takeover/续期的 SQL CAS 保证**。

#### S5-SCH-1 Scheduler 全函数状态机（冻结）

**1.1 claim / lease / takeover / 限流退避**
- claim 谓词（锁内判定，全部 tenant 限定）：`conversation.state=deleted` + `purged_at IS NULL` + `purge_after` 已过 + **无 active hold（S5-B-5 对齐：active hold 期间 claim 延迟——不产生「全 pending 新 op 被 G3 block、release 后再 rebuild」的中间态）** + **quiesce 门禁（S5-B-1：任一 owner 的 checkpoint/fence 仍 erasing → 不得创建新 operation，转入 settlement 收口等待）** + 无在租 claim（lease 未到期）。
- 建行判据分两条（互斥，不合并术语）：(i) **无行/旧 purge_revision**：Conversation 锁内「首 claim 幂等判别」——top operation 行不存在 → `create_purge_operation`（当前 `conversation.purge_revision`）+ 全 owner checkpoint 建行（惰性建行必须在首次聚合前完成，一致性快照，S5-A-4）；存在同 purge_revision 行 → 幂等返回既有 operation（**首 claim 无 predecessor，S5-B-6 的 predecessor 子句不可评估、不适用**；重复 rebuild 的幂等判别方用 S5-B-6）；(ii) **同 revision G1/G2 drift**（operation 仍为 top revision、registry/hold snapshot 失配）：**不建行**，分派 S5-SCH-1.5 序列（quiesce → settlement 收口 → rebuild），详见 1.5。
- bounded lease：claim 以 `lease_epoch` SQL 侧原子 CAS 推进（统一 CAS 谓词：expected = 锁内当前值，成功后 = current+1）；**lease 续期**：每 entry 前 scheduler 自有短事务（Conversation-first）推进 lease（心跳写），lease 上界冻结默认 10 分钟且必须大于单 owner 最大执行时长；**settlement_deadline 上界冻结默认 ≤ 10 分钟（与 lease 上界一致；SCH-D 验收断言 descriptor deadline 不得越过该上界）**。
- takeover：仅 `expected_lease_epoch` CAS 推进；stale lease 败者**零写退避**；重复 scheduler 同 conversation 由 Conversation 锁串行 + 幂等判别收敛为单一写者。
- tenant 限流与退避（冻结默认值）：per-tenant 并发 claim 上限 4；退避 `next_retry_at = clock_timestamp() + min(5s × 2^attempt, 5m)`（attempt 为 per-owner checkpoint.attempt 锁内重算值）；**next_retry_at 仲裁 = min（多 owner 各自排程取最早者；takeover 后按 attempt 锁内重算，不依赖持久 jitter）**。

**1.2 零 checkpoint `scheduled` 投影唯一写者**（S5-SCH-5 正式冻结）：`scheduled/not_scheduled` purge_state 与 `purge_revision` 唯一写者 = delete/restore 生命周期；coordinator 对 scheduled 聚合结果**保留** Conversation 既有 purge_state（I2 已实现语义）；scheduler 不得直接写 `scheduled/not_scheduled`；全 owner checkpoint 建行后 coordinator 聚合自然离开 scheduled。

**1.3 owner 顺序执行与编排**
- 顺序：registry snapshot owner_key 字典序（与 coordinator 锁序/聚合 tie-break 同序）。
- **每 entry 前两步**：(a) **周期级 token 重验**——重读 operation `(revision, lease_epoch, purge_revision)` + Conversation `(purge_revision, hold_revision)` + registry digest；任一不匹配 → 该 cycle fail closed 重入 claim 判定（不写任何行）；(b) **owner 级 checkpoint/fence 态重读**——该 owner checkpoint `acked/failed` → 跳过（零副作用）；`erasing` → 交 settlement 通道收口，**不得重跑**；`blocked` 且 reason 不在白名单 → 跳过（reconcile-only）；其余 → participant entry。
- 每 owner entry 返回后调用 coordinator `aggregate_projection`（独立事务，S5-A-5 触发点在本契约接线）。entry 抛错/超时的 reason 映射（冻结）：infra 类错误（drift raise 除外）→ 经 participant 入口记 `blocked` + `purge_owner_unavailable`（level 11，白名单内）；drift 类 raise（旧 revision/registry/hold 门禁）→ **不写 checkpoint**，fail closed 重入 claim 判定。
- 单 owner 重试复用 participant 入口，锁序与 participant 完全一致（S5-A-4 冻结），**任何路径不得持 operation 行锁时反取 owner advisory/fence，不得先 checkpoint 后 operation**。

**1.3b 周期全量重算触发（liveness，冻结）**：S5-A-5「定时/claim 触发的全量重算」接线——(i) **lease 到期 takeover 后强制一次 `aggregate_projection`**（先聚合后 cycle 分派）；(ii) 定时 tick（间隔冻结默认 1 分钟）对 claim 候选集全量聚合。任何「quiescent 状态」（全部 owner 非 pending/erasing 且无后续 entry）都经 (i)/(ii) 推进：drift 检测、failed/completed 后的 hold/registry 变化、reconcile-only blocked 的重判均依赖此触发。归属：SCH-A（takeover 后聚合）与 SCH-B（tick）。

**1.4 checkpoint retry 白名单、预算与 failed**
- 重试白名单（S5-A-3 族 B 封闭，逐字引用）：`erase_timeout`/`adapter_unavailable`/scan 族 + pre-window gate 具名域（legal_hold/unresolved_action/conversation_scope_gate/owner_unavailable/operator_suppressed）；`outcome_unknown`/`settlement_deadline_expired`/`adapter_unresolvable`/`purge_owner_ack_conflict`/dirty-data/G1/G2-blocked **一律禁止重开**（零 adapter 调用、零状态推进，S5-C 输出态 3/5/6 reconcile-only）。
- 重试计数（冻结）：基于该 owner checkpoint.attempt（锁内重读），每 entry 一次 attempt+1 语义由 participant 协议承担；**pre-window gate reason（legal_hold 等）不计入重试预算**（S5-B-2 对 legal_hold 冻结「义务重开 pending」——长期 hold 不得因周期重试耗尽预算落 failed 终态）；**hold 变化（G2 drift）重置预算**（新 revision 新 attempt 起点）。
- 预算耗尽（per-owner 重试上限，冻结默认 3，pre-window gate 豁免后计数）：scheduler 写该 owner checkpoint `failed` + `reason_code` = 最后一次 blocked reason（全 NULL → NULL）+ 清 `next_retry_at`；**fence 同步收敛 = S5-C-1 failed 收敛**（fence 已 blocked → 不推进不重置；fence 仍 erasing（pre-fix 遗留/未收敛时序）→ 经 settlement 进入点写 erasing→blocked），触发归属 = scheduler failed 写入点同步经 settlement 进入点收口（SCH-B 验收含该反例）。coordinator 按优先级 5 只读聚合 failed（S5-A-2 冻结）。
- `blocked → running` 唯一路径 = 白名单内重试且被重试 owner 是唯一 blocked owner（S5-A-3/S5-A-10 冻结）；G1/G2-blocked 只走重建（S5-A-3 + S5-B-5 指针）。

**1.5 G1/G2 drift、Option D quiesce 与 rebuild/seeding**
- 检测与触发（闭合链路，冻结）：周期全量重算（1.3b）触发 coordinator 聚合 → G1/G2 写冻结 blocked（I2 已实现）→ scheduler 检测 blocked 族 → **Option D quiesce**（等全部 owner 离开 erasing；quiesce 判定在 Conversation 锁下，S5-B-1；erasing owner 由 settlement 收口，S5-C）→ G3 消解（release hold）→ 新 purge_revision rebuild + seeding（S5-B-2 owner obligation 全函数矩阵 + S5-B-3 六项 lineage 重验 + S5-B-6 并发幂等/DELETED 门禁）。
- **purge_revision 派生（对账 S5-B-5，冻结）**：rebuild 在 Conversation 锁内读当前 `conversation.purge_revision`，**新 operation 的 purge_revision = 当前值 + 1 并同事务写回 Conversation.purge_revision**——rebuild 是 Conversation.purge_revision 的第二写者（第一写者 delete/restore 生命周期），S5-SCH-2 矩阵登记；`create_purge_operation` 的 purge_revision 入参来源即此派生值。
- rebuild 单事务：零新 operation/零新 checkpoint 或全提交；seeding 期失败 = 整事务回滚（S5-B-3 阶段 1）；聚合期漂移 → derived conflict（G4，阶段 2）。每 hold 变化事件至多一次 rebuild（S5-B-5）；重复 rebuild 幂等判别 = S5-B-6（predecessor 锁内重验）。

**1.6 settlement 集成与内部命令**
- 六输出态（S5-C-1）、ACK-lost repair（**S5-C-7**）、RecoveryDescriptor 六字段历史装配、adapter lookup/replay receipt 三态（S5-C-5）——scheduler settlement 进入点按 S5-C-7 锁序表接线；**不复制规则，只引用**。
- inspect/retry/reconcile 内部命令边界：inspect = 只读；retry = 白名单内单 owner 重跑；reconcile = 有证据（receipt/ack_digest）才收敛（**S4-E E-3b**）；**无 force-skip ACK**——任何路径不得绕过五方验证/最终扫描/证据持有直接写 acked/completed。

#### S5-SCH-2 并发与崩溃（冻结）

**统一锁序**：scheduler 全部进入点 Conversation-first（claim/rebuild/quiesce 判定/settlement 进入/单 owner 重试编排/周期全量重算）；settlement 进入点锁序表 = S5-C-7 逐字引用（**单事务**：Conversation → owner advisory → fence FOR UPDATE → operation FOR UPDATE（frozen-snapshot）→ checkpoint FOR UPDATE，fence+checkpoint CAS 同事务原子；**Tx1-Tx2 双事务协议仅存在于 external/runtime participant 窗口期，settlement 通道禁新 Tx1**）。

**scheduler 自有写事务清单（冻结，均 Conversation-first）**：(a) lease claim/takeover/续期（operation.lease_epoch CAS，短事务）；(b) 预算耗尽写 checkpoint `failed` + fence failed 收敛（经 settlement 进入点收口）；(c) `next_retry_at` 退避写（随 claim/续期短事务）；(d) rebuild 单事务（operation/checkpoint seeding + case-E fence.owner_version + Conversation.purge_revision+1）。S5-B-3 阶段 2 读集一致性写者清单前向增补：scheduler 上述四类写入均持 Conversation 首锁，符合「任一写者绕过 Conversation 首锁即契约失败」。

**崩溃恢复点（四分支，冻结）**：claim 后崩溃 → lease 到期 takeover（lease_epoch CAS）；rebuild 崩溃 → 单事务回滚零残留（旧 operation 完整保留可重放）；participant Tx1 后崩溃（Tx2 未收口）→ E-2a 重放续做（settlement 收口前崩溃同路径）；**循环中途崩溃/接管 → 重入前按 checkpoint 态恢复账本**（1.3b 触发聚合 + 1.3 owner 级态重读：acked/failed 跳过、erasing 交 settlement、不得重跑已完成 owner）。任何恢复路径重入前必须 token 重验（1.3a）。

**旧 lease/revision 零写**：takeover CAS 败者零写退避；旧 purge_revision operation 的 participant/coordinator 写一律旧 revision 门禁拒绝（I2 已落地）；scheduler 对旧 token 的 claim/retry 重放零写（反例矩阵 SCH-4 行 7）。

**写者所有权矩阵（目标态全表）**：

| 实体/列 | 唯一写者 | 备注 |
|---------|---------|------|
| operation.state/failure_code/started_at/completed_at/revision | coordinator | 终态覆盖禁令；scheduler 不写 |
| operation.lease_epoch | scheduler（claim/takeover/续期 CAS） | 单调由 CAS 保证；其余写者只读重验 |
| operation.next_retry_at | scheduler（退避写，min 仲裁） | 见 1.1 |
| operation `scheduled` 初建 | `create_purge_operation`（scheduler claim/rebuild 调用） | 见 S5-SCH-0 |
| operation `cancelled` | restore-cancel（生命周期） | — |
| checkpoint 全列 | participant / scheduler（`failed`）/ seeding | 编排方不写 blocked（经 participant 入口）；coordinator 只读 |
| fence.state（状态机边） | participant / settlement（S5-C-7） | scheduler 不写状态机边 |
| fence.owner_version（case E migration） | rebuild/scheduler（仅 active fence，owner lock + fence FOR UPDATE 内） | S5-B-2 case E / S5-B-4 |
| ledger / binding | participant / settlement | — |
| Conversation.purge_state（running/blocked/failed/completed）+ purged_at | coordinator | — |
| Conversation.purge_state（not_scheduled/scheduled） | delete/restore 生命周期 | scheduler 不写 |
| Conversation.purge_revision | delete/restore 生命周期 / **rebuild（+1 同事务写回，S5-B-5 对账）** | 第二写者仅 rebuild |
| hold_revision | I1 producer | — |

#### S5-SCH-3 实现 PR 拆分（单风险域，冻结；不预设一个大实现 PR）

四个 slice 各自独立契约验收，每个 slice 一个原子实现 PR（merged-boundary 在各自 PR 记录）；不命名 I3。

- **SCH-A Claim & Lease**：claim 谓词（含 quiesce 门禁 + active hold 延迟）+ 首 claim 幂等判别 + lease_epoch CAS/takeover/续期 + tenant 限流/退避 + operation/全 owner checkpoint 建行 + **takeover 后强制聚合（1.3b-i）**。验收：SCH-4 行 1/2/5/6/7 + 首 claim 幂等。
- **SCH-B Owner Execution Orchestrator**：编排循环（owner 字典序 + 周期 token 重验 + owner 级态重读 + 每 owner 后 coordinator）+ 周期 tick（1.3b-ii）+ retry 白名单 + 预算耗尽写 `failed` + fence failed 收敛（经 settlement 进入点）+ **组合根启用门禁**（见下）。验收：SCH-4 行 4/8 编排相关项 + SCH-3（hold-release race）跨 slice 联合验收（归 SCH-C，见 SCH-4 归属表）+ participant/coordinator 互操作回归。
- **SCH-C Rebuild & Seeding**：G1/G2 drift → quiesce → 新 revision rebuild/seeding（S5-B 全卷落地）+ purge_revision 派生写回 + 幂等判别（S5-B-6）。验收：S5-B-9 反例矩阵**实义 29 行**前向映射（剔除占位行 14/19/20/24——其内容由 S5-C-8 承载、归 SCH-D）+ settlement 耦合行（13 等）标注跨 slice 联合验收。
- **SCH-D Settlement & Retry-Reconcile 集成**：S5-C 六输出态/ACK-lost repair（S5-C-7）/RecoveryDescriptor 装配/内部命令（inspect/retry/reconcile，无 force-skip ACK）。验收：S5-C-8 反例矩阵 16 行前向映射 + S5-B-9 占位行 14/19/20/24。
- **组合根启用门禁（冻结）**：SCH-B 的 erase 入口生产可达性翻转（wiring 门禁）**不得早于 SCH-C（quiesce+rebuild）与 SCH-D（settlement 进入点最小子集，含 failed 收敛）同窗口交付**——B/C/D 三 slice 联合 merged-boundary；否则 erase 入口保持不可达。S5-A-5 滚动发布前提由此延续：启用时 drift/窗口崩溃的收口路径必须已在网。
- 依赖顺序：SCH-A → SCH-B；SCH-C / SCH-D 无相互依赖；**B/C/D 联合 merged-boundary**（B 不单独上生产）。
- **排除**：完整 legal-hold permission/HTTP/CLI API、指标与脱敏日志 pipeline、S6（retention clocks / 真实故障矩阵 / 备份恢复）、C1 总验收。

#### S5-SCH-4 反例矩阵（冻结；前向映射 + 新增项）

**前向映射（不复制第二套规则）**：**S5-B-9** 反例矩阵（plan 行 1757-1793）实义 29 行 → SCH-C 验收逐行映射（占位行 14/19/20/24 由 S5-C-8 承载、归 SCH-D；settlement 耦合行标注联合验收）；**S5-C-8** 反例矩阵 16 行 → SCH-D 验收逐行映射。S5-A-8 反例矩阵由 I2 已覆盖，SCH-B 回归复用。**全部新增行复用 S4-F 已冻结注入机制**（真实 PostgreSQL、双连接 `asyncio.gather`、DB 篡改、崩溃注入、fake adapter 故障注入、跨 tenant/跨 Conversation）。行间判别点与 mutation 命名沿用原矩阵（不新增第二套规则）。

**新增反例（每项具名 mutation，实施 PR 逐项落地；slice 归属表）**：

| # | 反例 | 归属 | 触发 | 期望行为 | 判别点（mutation） |
|---|------|------|------|---------|-------------------|
| SCH-1 | claim takeover | SCH-A | 双 scheduler 并发 claim 同一 conversation，lease 到期后第二个实例 takeover | 单一写者；lease_epoch 单调 +1；stale lease 败者零写退避 | 「stale 方仍写」→红 |
| SCH-2 | 重复 scheduler 幂等 | SCH-A | 同 conversation 重复 claim（无 drift） | Conversation 锁内首 claim 幂等判别：只产生一个 operation/一次全 owner 建行，重复 claim 返回既有 operation | 「重复建 operation」或「重复建 checkpoint 行」→红 |
| SCH-3 | hold-release race | SCH-C | purge 进行中 create hold（G2）→ release → 新 revision 续跑 | 序列 = G2 blocked → quiesce → release → rebuild → 正常执行；每个 hold 变化至多一次 rebuild | 「release 后原地重试旧 operation」→红（与 S5-B-9 行 1 同判别点，S5-A-10 移交项闭环） |
| SCH-4 | 预算耗尽写 failed | SCH-B | 白名单内 owner 重试达上限 | checkpoint `failed` + reason = 最后 blocked reason + next_retry_at 清；fence 已 blocked 不推进不重置（fence 仍 erasing → settlement 收敛，归 SCH-D 验收） | 「fence 已 blocked 时被推进/重置」或「failed reason 丢失」→红 |
| SCH-5 | 崩溃恢复四分支 | SCH-A/B | claim 后崩溃 / rebuild 崩溃 / participant Tx1 后崩溃（settlement 收口前）/ 循环中途崩溃 | lease 到期 takeover / 单事务回滚零残留 / E-2a 续做 / 按 checkpoint 态恢复账本不重跑已完成 owner；恢复路径重入前 token 重验 | 「恢复路径跳过 token 重验」或「重跑 acked owner」→红 |
| SCH-6 | 跨 tenant | 全 slice | claim/retry/takeover/全量重算携带错误 tenant | 全部谓词 tenant 限定，错配零写 fail closed | 「裸 id 谓词」→红 |
| SCH-7 | 旧 token 重放 | 全 slice | 旧 lease_epoch / 旧 revision / 旧 purge_revision 重放 claim 与 retry | 零写（CAS/门禁拒绝） | 「旧 token 仍写」→红 |
| SCH-8 | 组合根启用门禁 | SCH-B/C/D 联合 | merged-boundary 前后 | 前：erase 入口生产不可达（wiring 静态守卫）；后：编排方可达且每 entry 后 coordinator 触发、settlement 进入点与 quiesce/rebuild 在网 | 「settlement/rebuild 收口路径未在网即启用 erase 入口」或「未接线 coordinator 即启用」→红 |

#### S5-SCH-5 REQ-047 follow-up 分流（冻结）

- **零 checkpoint `scheduled` 生命周期写者边界**：本契约正式冻结（S5-SCH-1.2）——delete/restore 为唯一写者；coordinator 对 scheduled 结果保留语义正式化（I2 实现不再标注「未决」）；REQ-047 该项标记「已冻结」（跟踪点 = 本契约 + I2 merged-boundary follow-up 清单，C1 conformance 批次回写）。
- **五份 participant operation 锁查询三键收窄 + td-032 测试文件拆分（REQ-047 新拆分项——原 TD-032 债务已关闭，指称新项勿用已关闭编号）**：指定实现 PR 承接（SCH-A 或独立 conformance PR，开工时由工作台指定）——本纯文档批次**不顺手修改**代码/测试。
- 其余 REQ-047 项（现存 P2/P3 精度、拆分计划）保留至 C1 conformance。

---

> **merged-boundary（2026-08-16，契约 PR #571，squash merge `253e53e4`）**：R1-S5-D Scheduler 契约冻结并入 main（评分 87，Original，基线 `fcd40565`；首轮三面 P0=0/P1=7/P2=21/P3=14 → 族 A~G 统一返修 → 定向复核 8/8 → 最终 P0/P1=0）。**契约完成不代表 Scheduler 实现完成**：SCH-A Claim&Lease / SCH-B Owner Execution / SCH-C Rebuild&Seeding / SCH-D Settlement&Retry-Reconcile 均未开工（B/C/D 联合 merged-boundary 为启用门禁）；53 项反例矩阵（S5-B-9 实义 29 + S5-C-8 16 前向映射 + 新增 8）为冻结验收载体，随各实现 PR 逐行落地。REQ-047 / R1-S5 scheduler implementation conformance follow-up 保留（SCH-A..D 逐 slice 验收映射、B/C/D 联合 merged-boundary 门禁核验、零 checkpoint scheduled 写者与 participant 三键收窄随实现 PR 闭环；不宣称本契约已实现任何 scheduler 功能）。

（契约段位置：R1-S5 综述区之后、## 4 之前；首轮三面返修版）

## 4. C1：Durable Core 总验收与文档收口

**复杂度/执行**：高，Sol `high` 集成，Sol `xhigh` 最终 Review。

- [ ] 联合运行 W1/E0/E1/B1/A1/D1/R1 conformance/fault suite 与完整 hermetic backend。
- [ ] 确认旧 `/ai/chat/evidence`、Conversation API、Run query/SSE 和 migration 往返无回归。
- [ ] 只在代码、迁移、组合根真实存在后更新 `ARCHITECTURE.md`。
- [ ] REQ-041 标 Done；REQ-047 仅标 `Durable Core Done / Extended Contracts Shaping`。
- [ ] 更新 Backlog、Milestone、Iteration、current-work、work-log、review scorecard 和真实验证数据。
- [ ] 下一步切到 REQ-042 Workspace；不在 C1 顺手实现 UI、TD-085、Runtime 或 extended entities。

## 5. PR 与模型分工矩阵

| PR | 复杂度 | 推荐主模型 | 第二评审 | 人工门禁 |
|----|--------|------------|----------|----------|
| S0 docs | 高 | Sol `xhigh` | 可选 `max` 架构复核 | 用户确认 Spec §12 |
| S1 schema/fence | 极高 | Sol `xhigh` | 独立 `max` | 架构负责人 |
| S2 workspace | 极高 | Sol `xhigh` | GLM-5.2 `max` | 数据负责人抽查 tombstone |
| S3 execution | 极高 | Sol `xhigh` | 独立 `max` | 架构负责人 |
| S4 transport/external | 极高 | Sol `xhigh` | GLM-5.2 `max` | 安全负责人 |
| S5 hold/operations | 极高 | Sol `xhigh` | 独立 `max` | 数据 + 安全签字 |
| S6 fault/retention | 极高 | Sol `xhigh` | 独立 `max` | 发布签字 |
| C1 closeout | 高 | Sol `high` | Sol `xhigh` | 产品/架构确认范围 |

Kimi K3 适合后续 REQ-042 UI，不分配到 R1 核心状态机、迁移或数据删除。GLM-5.2 可承担边界冻结后的 repository/test slice，但不能单独定案删除语义。

## 6. 全局验证命令

各 Slice 按范围运行专项；S6/C1 至少执行：

```bash
cd packages/server-python
uv run pytest tests/contexts/agent_workspace tests/contexts/agent_execution tests/composition -q --tb=line
uv run pytest -q -m 'not external_network' --tb=line
uv run ruff check app/ tests/
uv run python scripts/check_mypy_baseline.py
uv run alembic downgrade -1
uv run alembic upgrade head
cd ../..
scripts/check-engineering-docs --full
git diff --check
```

故障场景必须使用真实 PostgreSQL；SQLite/mock 只能覆盖纯状态转换。涉及 external/Runtime 的 fake adapter 验证结果必须在 PR 中标注为 contract evidence，不得写成生产 Pilot。

## 7. 停止条件

出现以下任一情况暂停当前 Slice，回到 Spec/人工门禁：

- 需要改变 CR-1/2/4/10/13/16 或共享 ORM/repository。
- 发现新的 Conversation-owned writer/owner，但没有稳定 owner key、fence 或 erase capability。
- migration 无法可靠回填 conversation owner scope/fence。
- external erase 返回 unknown 但实现准备自动重试或强制 ACK。
- 为通过测试需要保存正文到 audit/checkpoint/log，或需要删除 catalog/业务源资产。
- Runtime conformance 依赖尚不存在的 Pi Worker，却准备将 fake 结果标为生产完成。

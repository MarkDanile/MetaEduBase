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
- **D8 claim 锁与 Guard 顺序（不变量 1，现状已合规，冻结保持）**：claim 在独立短事务（`_claim_output`/`_claim_turn` 各自 `session.begin()`，`skip_locked`），**不持 outbox row lock 等待 Guard**；消费在另一事务（`consume_output_event`/`consume_turn_event`）按 Guard -> Conversation 行锁（`lock_output_conversation`/`lock_projection_conversation`）-> owner lock -> fence 重验。S4-C/D 的 claim 外短事务 + Guard 内 cancel/suppress/tombstone 必须保持此顺序，不得引入 AB-BA。

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
| `owner_key` | `String(40)` NOT NULL | 属 `workspace.transport.v1`/`execution.transport.v1`/`external.payload.v1` |
| `source_table` | `String(40)` NOT NULL | `ck_..._source_table`: `IN ('agent_workspace_outbox','agent_workspace_inbox','agent_execution_outbox','agent_execution_inbox','agent_run_events')` |
| `source_row_id` | `UUID` NOT NULL | 源表主键 |
| `conversation_id` | `UUID` NULL | 已知候选时填；未知/已删除保持 NULL |
| `reconcile_class` | `String(20)` NOT NULL | `ck_..._class`: `IN ('conversation_scope','tenant_scope','orphan')`（D3 三态） |
| `reason_code` | `String(64)` NOT NULL | 受控枚举（B4） |
| `state` | `String(20)` NOT NULL default `'open'` | `ck_..._state`: `IN ('open','acknowledged','resolved')` |
| `created_at` / `resolved_at` | `DateTime(tz)` NOT NULL / NULL | — |

唯一键：`uq_agent_transport_reconcile_source (tenant_id, owner_key, source_table, source_row_id)`（同一源行同一 owner 只一条 reconcile 记录，幂等重放命中既有行）。索引：`ix_agent_transport_reconcile_tenant_state (tenant_id, state)`（tenant scheduler gate 查询）、`ix_agent_transport_reconcile_conv (tenant_id, conversation_id) WHERE conversation_id IS NOT NULL`（conversation purge gate 查询）。

*(e) `agent_external_object_refs`（D5 external ref ledger，新表）：*

| 列 | 类型 | 约束 |
|----|------|------|
| `id` | `UUID` PK default uuid4 | — |
| `tenant_id` | `UUID` NOT NULL | `fk_..._tenant` -> `tenants(id)` |
| `conversation_id` | `UUID` NULL | 溯源；可 NULL（源行 scope 未知时） |
| `owner_key` | `String(40)` NOT NULL default `'external.payload.v1'` | — |
| `ref_scheme` | `String(40)` NOT NULL | `db_local` / 其他 scheme；`ck_..._ref_scheme`: `char_length>0` |
| `ref_value` | `String(500)` NOT NULL | external object 引用值 |
| `source_table` | `String(40)` NOT NULL | `ck_..._source_table`: `IN ('agent_run_events','agent_workspace_outbox','agent_execution_outbox')`（D5 全覆盖） |
| `source_row_id` | `UUID` NOT NULL | 源行主键 |
| `erase_state` | `String(20)` NOT NULL default `'pending'` | `ck_..._erase_state`: `IN ('pending','registered','erased','blocked','unknown')`（B5） |
| `receipt_digest` | `String(64)` NULL | `ck_..._receipt_digest`: `receipt_digest IS NULL OR char_length=64`；erase 取得 receipt 后填（先删对象取 receipt、再清 DB ref 的证据） |
| `blocked_reason` | `String(64)` NULL | unknown scheme/timeout/digest mismatch 等 |
| `created_at` / `updated_at` | `DateTime(tz)` NOT NULL | — |

唯一键：`uq_agent_external_ref_source (tenant_id, source_table, source_row_id, ref_value)`（同一源行的同一 ref 只登记一次，幂等）。索引：`ix_agent_external_refs_conv (tenant_id, conversation_id)`、`ix_agent_external_refs_state (tenant_id, erase_state)`。

*(f) inbox tombstone marker/digest（D4，2 张 inbox 各增 2 列）：*

| 列 | 类型 | 约束 |
|----|------|------|
| `receipt_tombstone_state` | `String(16)` NULL | `ck_*_receipt_tombstone_state`: `receipt_tombstone_state IS NULL OR receipt_tombstone_state IN ('redacted')` |
| `receipt_tombstone_digest` | `String(64)` NULL | `ck_*_receipt_tombstone`: `(receipt_tombstone_state IS NULL AND receipt_tombstone_digest IS NULL) OR (receipt_tombstone_state = 'redacted' AND char_length(receipt_tombstone_digest) = 64)`（marker 与 digest 同生同灭；digest 非空 64-hex） |

不改既有 `ck_agent_*_inbox_status`（`processing/consumed/rejected`）枚举。

**B2. 回填来源矩阵（conversation_id 溯源）**

| 目标表 | 源关联 | 映射规则 | 歧义/缺失 |
|--------|--------|----------|-----------|
| `agent_workspace_outbox` | `aggregate_id = agent_messages.id`（event_type='turn.requested.v1'，`aggregate_type='workspace.message'`） | `conversation_id = message.conversation_id`（Message 该列 NOT NULL，1:1） | message 缺失/跨 tenant -> `tenant_scope`/`orphan` reconcile |
| `agent_execution_outbox` | `aggregate_id = agent_runs.id`（event_type='assistant_message.publish_requested.v1'，`aggregate_type='execution.run'`） | `conversation_id = run.conversation_id`（Run 该列 NOT NULL，1:1） | run 缺失/跨 tenant -> reconcile |
| `agent_workspace_inbox` | `event_id = agent_execution_outbox.id`（assistant_publish 消费的源事件） | `conversation_id = 源 execution_outbox.conversation_id`（先回填 outbox 再回填 inbox，保证可 join） | 源 outbox 缺失/scope 未知 -> reconcile |
| `agent_execution_inbox` | `event_id = agent_workspace_outbox.id`（turn_requested 消费的源事件） | `conversation_id = 源 workspace_outbox.conversation_id` | 同上 |

回填顺序：先两张 outbox（直接经 Message/Run），再两张 inbox（经已回填的源 outbox）。所有 UPDATE 带 `tenant_id` 谓词 + 源行 tenant 一致性校验（跨 tenant 不映射，记 reconcile）。

**B3. 历史 `producer_purge_revision` 不可推断 -> 保持未知（NULL）**：backfill **只**回填 `conversation_id`；`producer_purge_revision` 对历史行**保持 NULL（未知）并进入 reconcile**，**禁止**拿当前 `Conversation.purge_revision` 伪造历史 epoch（生产时快照无法事后重建）。仅新写（S4-C 起）在产生同事务快照真实 `purge_revision`。含历史行的 Conversation 在 purge 时须由 reconcile/S4-C 消费端按「未知 epoch -> tombstone/reconcile」处理（不变量 2/3），不得当作当前 epoch。

**B4. 三态 reconcile ledger 语义（`agent_transport_scope_reconcile`）**

- `reconcile_class` / 触发 / gate：
  - `conversation_scope`：已知候选 Conversation、但 scope 回填有冲突（如同 conversation 多源不一致）-> **阻塞该 Conversation purge**（purge 前置查 `conversation_scope AND state='open'` 命中即 blocked）。
  - `tenant_scope`：scope 真正未知（源 Message/Run/outbox 缺失或歧义，无法确定 Conversation）-> **阻断该 tenant scheduler/canary enable**（S5 scheduler 启动前查 `tenant_scope AND state='open'` 命中即 fail closed）。
  - `orphan`：Conversation 已物理删除（源行 conversation_id 在 `agent_conversations` 无对应）-> 具名 orphan reconcile，**不猜 UUID、不并入现存 Conversation**；不阻塞 purge（对象已删），但需运维确认 `acknowledged/resolved`。
- `reason_code` 受控枚举（封闭集，新增需新版本）：`source_message_missing`、`source_run_missing`、`source_outbox_missing`、`cross_tenant_mismatch`、`ambiguous_mapping`、`conversation_deleted_orphan`、`epoch_unresolvable`。
- 状态机：`open -> acknowledged -> resolved`（单向，不回退；`resolved` 需 digest/证据）。幂等：同一 `(tenant_id, owner_key, source_table, source_row_id)` 重放命中既有行不新建（唯一键 + ON CONFLICT DO NOTHING）。

**B5. external ref ledger 语义（`agent_external_object_refs`）**

- 来源唯一性：`uq_agent_external_ref_source (tenant_id, source_table, source_row_id, ref_value)`——每个 ref-bearing source 行（`agent_run_events.payload_ref`、`agent_workspace_outbox.payload_ref`、`agent_execution_outbox.payload_ref`）的每个非空 ref 恰好一条 ledger 记录。
- `erase_state` 状态机：`pending -> registered -> erased | blocked | unknown`。`registered`：已登记待删；`erased`：external object 已删并取得 `receipt_digest`（**先于**清 transport DB ref）；`blocked`：unknown scheme/timeout/digest mismatch（记 `blocked_reason`，不得 ACK，不变量 5）；`unknown`：erase outcome 未知（不得 ACK）。仅 `erased` 允许后续清对应 transport `payload_ref`。
- 仅 `db_local` scheme 在 S4-E 可实装删除；其余 scheme 一律 `blocked`/`unknown`。

**B6. inbox tombstone（D4）**：purge 清 receipt 时置 `receipt_tombstone_state='redacted'` + `receipt_tombstone_digest=<64-hex digest of receipt envelope>`（marker 与 digest 同写同事务）；`status` 保持既有 `consumed`/`rejected` 等不变，不新增枚举。digest 复用 shared `canonical_digest`，禁空串/`{}`/伪值。

**B7. backfill 执行契约（可恢复 / 分批 / tenant 限流 / 幂等 / 并发安全 / 最终 verify）**

- **分批 + keyset 游标**：按 `(tenant_id, id)` keyset 分页，`batch_size>=1`，报告带 `next_after_id` + `completed`；失败样本封顶，游标越过失败行不重试（沿用 S1 backfill 契约）。
- **tenant 限流**：逐 tenant 处理 + 每批间隔；不锁整表。
- **幂等恢复**：所有回填 UPDATE 仅命中 `conversation_id IS NULL`（或 scope 未决）的行，重复执行/中断重跑不产生重复或覆盖已填值；reconcile 写入 ON CONFLICT DO NOTHING。
- **并发新写处理**：S4-C 完成前旧 writer 仍可能产生 `conversation_id`/`producer_purge_revision` 为 NULL 的新行 -> backfill 与部分唯一索引均以 `IS NOT NULL` 为作用域，NULL 行不参与唯一约束、不阻塞新写；**不得在本 Slice 收紧 NOT NULL 或开启 purge**（scheduler 在 S5，且需 reconcile ledger 清零前置）。
- **最终 verify**：backfill 后校验（每表）——`conversation_id IS NULL` 的行要么是新写（`created_at` 晚于 backfill 起点），要么已登记 reconcile；存在既未填 scope 又未登记 reconcile 的历史行则 verify 失败（fail closed）。

**B8. 验收矩阵（S4-B 实现时逐项验证）**：migration 040 upgrade/downgrade 往返（含既有数据 + downgrade 还原）；跨 tenant（A tenant 行不得映射到 B tenant Conversation）；歧义映射（多源不一致 -> conversation_scope reconcile）；Conversation 已删除（-> orphan reconcile，不猜 UUID）；重复执行（幂等，不产生重复 reconcile/ledger 行）；中断恢复（keyset 游标续跑）；未知 epoch（历史行 `producer_purge_revision` 保持 NULL + 登记，不伪造）；全 ref-bearing source（`agent_run_events` + 两张 outbox 的非空 `payload_ref` 均登记 ledger，无遗漏）；backfill 期间并发新写 NULL 行不被唯一索引阻塞、不被误回填。

**S4-B 边界（明确不做）**：不创建 migration 040、不改业务代码（本 delta 纯文档）；不改 writer/claim（S4-C）；不实现 transport/external/runtime participant（S4-D/E）；不做 fault 矩阵（S4-F）；不启用 scheduler（S5）；`erase_available` 保持 `False`；不收紧既有列为 NOT NULL。

**S4-B 验证（本 delta 阶段）**：纯文档；docs gate + `git diff --check` 通过；三路 CI 全绿。返修后提交独立 `max`/Codex 复审；P0/P1 清零后再实现 migration 040 + backfill。

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

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

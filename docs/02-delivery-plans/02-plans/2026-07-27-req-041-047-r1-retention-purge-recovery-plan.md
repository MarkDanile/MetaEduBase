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
- **migration 039 guard 演进（复核 #1/#4，为 S4-E 清 RunEvent.payload_ref 预留）**：现有 `guard_agent_run_event_append_only()` 白名单只放行 `payload_inline`/`payload_state` 变化，`to_jsonb(OLD)-'payload_inline'-'payload_state' = to_jsonb(NEW)-...` 强制**其余列含 `payload_ref` 全不变**——S4-E 取得 external receipt 后无法清 RunEvent.payload_ref。且既有 `ck_agent_run_event_payload` 允许 `external`（必须持 ref）**与 `redacted/expired/archived`（`payload_inline IS NULL`，可不持 ref）** 行携带 `payload_ref`——这些「非 external 但残留 ref」正是 final scan 必须处理的历史矛盾形态。冻结：**新增具名 migration `041_run_event_external_ref_tombstone`**（不在 040，与 S4-B scope 列解耦）扩展 guard 白名单，放行**持 ref 旧状态（`external` 或 `redacted/expired/archived` 带非空 `payload_ref`）-> redacted 无 ref** 的严格 tombstone 形态：`OLD.payload_ref IS NOT NULL AND NEW.payload_ref IS NULL AND NEW.payload_state='redacted' AND NEW.payload_inline IS NULL`，且 `to_jsonb` 差集在原豁免列基础上仅再豁免 `payload_ref`/`payload_state`（`OLD.payload_state` 可为 `external`/`redacted`/`expired`/`archived` 任一），**`payload_inline` 必须 OLD/NEW 均 NULL（清 ref 不同时复活 inline）、其余 envelope 列强制不变**；downgrade 还原 039 白名单。S4-B 不实现 041，仅冻结其形态供 S4-E 落地。

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

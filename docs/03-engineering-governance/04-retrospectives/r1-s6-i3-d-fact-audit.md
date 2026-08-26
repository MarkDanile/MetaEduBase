# R1-S6-I3-D 事实审计（contract-to-code）

> Status: 🟡 进行中（事实审计阶段）—— **本轮不实施业务代码**；本审计文档仅做 contract-to-code 读审查
>
> 任务卡：`docs/03-engineering-governance/current-work.md` TASK-R1-S6-I3-D
>
> PR 基线：main `aff5488381e0e84878dd386cbc83be5abad3745a`（2026-08-27 closeout of PR #596/#597）
>
> 实施 HEAD：implementation HEAD = `aff54883`（未变更）
>
> 冻结契约：Plan §S6-8 / §S6-12 / §S6-13 / §S6-14 / §S6-15.5（已随 PR #586 / #591 / #592 / #596 合入 main）

## 0. 审计范围与边界

**包含（本审计）**：
- 当前 main `@aff54883` 真实代码能力 vs 冻结契约 §S6-8/12/13/14 实施要求 逐项对照
- 已有能力、缺失能力、P0/P1 风险点
- 实施矩阵（9 项）
- 6 项阻塞问题答案
- PR-D 是否可单 PR 执行的推荐

**不包含（本审计明确排除）**：
- 业务代码实现（ledger export executor / archive sink / restore replay executor / restore-before-open runbook）
- 复制、恢复旧 `c07c031c` scaffold
- 修改 Plan / 技术债总账 / work-log / Score Log / Metrics / migration 043 / schema / registry capability / 门禁脚本 / KNOWN_ISSUES / CI 配置
- 启动 PR-E / C1 / S5 production wiring / capability flip / 六 erase 入口生产可达

---

## 1. 独立 ledger 连续导出 / 归档

### 冻结契约（§S6-8.2）

> S5-SCH-0 持久化账本（operation `agent_conversation_purges` + checkpoint `agent_conversation_purge_owners` + external ref `agent_external_object_refs` + reconcile `agent_transport_scope_reconcile`）**必须连续导出/归档到独立于 DB 备份的存储**（receipt/ack_digest 变更日志）—— Spec §3「从**独立保存**的 erasure operation/receipt 账本重放」字面要求；DB 内账本停在备份快照时点，**快照之后完成的 purge 在恢复库中既留有正文又无账本记录**，body scan 永不为零（永久 fail-closed）或按账本裁剪则正文复活。

### 现状审计

| 项 | 状态 |
|----|------|
| 独立于 DB 备份的安全存储 sink | **缺失**——`scripts/` 仅含 mutation kill 驱动（`s6_td106_settlement_ledger_mutation_kill.py` / `s6i3_f10_mutation_kill.py` / `s6i3_fault_matrix_mutation_kill.py`），无独立 archive sink、CLI、调度入口 |
| Ledger 导出 CLI（连续/增量） | **缺失**——`packages/server-python/alembic/` migrations 无 export/ledger 类迁移；无 `app/composition/s6i3_ledger_export.py`（旧 scaffold 已随 #586 scope 收敛撤回） |
| Ledger 归档调度入口 | **缺失**——`S6I2_PENDING_WRITERS` 登记 `restore_replay_executor` 仅字符串 pending，无 ledger exporter 登记；spec §10.4 backfill CLI 存在（`agent_erasure_backfill.py` / `agent_transport_backfill.py`），但 backfill ≠ archive |
| JSON serialize 冒充连续归档完成 | **禁止**——冻结契约明确区分 export（连续导出）与 JSON serialize（仅状态 dump）；不得用 JSON dump 冒充 ledger archive |

### P0/P1 风险

- **P0**：独立 archive sink 完全缺失——恢复库中快照后 purge 既留有正文又无账本记录，body scan 永不为零或按账本裁剪则正文复活（永久 fail-closed 或正文复活二选一）——**冻结契约 §S6-8.2 缺独立 sink 即未交付**。
- **P1**：DB 内账本快照时点滞后于真实 purge 完成时间——任何 30/90/365 天级 purge 都可能产生「快照后已完成但恢复库缺账本」窗口。

---

## 2. 快照格式与导入校验

### 冻结契约（§S6-13.3）

> 导入快照必须带 record kind/table identity（operation/checkpoint/ref/reconcile 四类具名区分）：避免相同 `state` 字段跨 operation/checkpoint/fence 混读；快照 schema version 变更须显式 bump。

### 现状审计

| 字段 | 状态 |
|------|------|
| Schema version 字段 | **缺失**——`agent_conversation_purges` / `agent_conversation_purge_owners` / `agent_external_object_refs` / `agent_transport_scope_reconcile` 均无 `schema_version` 列（migration 034/040 已冻结）；快照导出需新增列或在导出端 codec 强绑定 |
| Record kind/table identity 区分 | **缺失**——四类 record 在导出端必须分别命名（`agent_purge_operation` / `agent_purge_owner_checkpoint` / `agent_external_ref_erase_state` / `agent_transport_reconcile`），导出端 codec 无现成基座 |
| Tenant 字段 | ✅ 现有 `tenant_id` 列全 4 表；导出端需 tenant scope 隔离（Plan §S6-1 时钟 + tenant scope） |
| Count 字段 | **缺失**——四表无 `record_count` 字段；导出端需在 manifest 记录 |
| SHA-256 digest 字段 | **缺失**——`agent_conversation_purges` 无 `digest` 列（settlement 用 settlement-time 计算非持久化），其余三表亦无；导出端需在 manifest 计算 snapshot digest |
| Operation 字段（operation） | ✅ `agent_conversation_purges` 持久化 `state` / `failure_code` / `revision` / `registry_digest` / `retention_policy_digest` / `hold_revision_snapshot` / `lease_epoch` / `next_retry_at` |
| Checkpoint 字段（per owner） | ✅ `agent_conversation_purge_owners` 持久化 `owner_key` / `owner_version` / `capability_digest` / `state` / `attempt` / `checkpoint_digest` / `ack_digest` / `reason_code`（`ck_agent_purge_owner_ack` 要求 state='acked' ⇒ 64-hex ack_digest） |
| Ref 字段（external ref） | ✅ `agent_external_object_refs` 持久化 `ref_scheme` / `ref_value` / `source_table` / `source_row_id` / `conversation_id` / `payload_ref` + `erase_state` / `receipt_digest`（TD-106 方案 A 已落地） |
| Reconcile 字段（transport ledger） | ✅ `agent_transport_scope_reconcile` 持久化 `issue_code` / `owner_key` / `source_table` / `class_scope` / `conversation_scope` / `resolved_at`（migration 040 落地） |
| TD-106 per-ref receipt 完整性 | ✅ `agent_external_object_refs.erase_state='erased'` 时 `receipt_digest` 非 NULL（TD-106 方案 A 验证）；runtime binding 同样在 `agent_runtime_session_bindings`（`runtime_session_ref IS NULL` + `status='closed'`） |
| 正文 / payload / secret / 自由文本泄露 | ✅ 4 表均无正文/事件 payload 列（`agent_run_events.payload_inline` / `payload_ref` 不在本审计四表范围；`agent_conversation_purge_owners` / `agent_external_object_refs` 仅存 digest）；导出端需复检每条 record 字段名白名单 |
| Owner 六元组（§S6-13.2） | **部分缺失于持久化**：`checkpoint.state` / `owner_key` / `ack_digest` / `owner_version` / `capability_digest` / `purge_revision` 中 5 个字段全持久化（`ack_digest` 在 checkpoint 表；`purge_revision` 在 operation 表），恢复端必须跨表 join 重构六元组——单 record 内不齐全 |

### P0/P1 风险

- **P0**：四表无 `schema_version` / `digest` / `record_count` 列——导出端需 codec 层绑 schema version 并写 manifest；恢复端 codec 必须按 version 显式 bump——**无 schema version 字段 ⇒ 快照不可版本化**。
- **P1**：六元组跨表 join 恢复——单 record 不含全六元组，restore 端需 join + digest 校验——增加恢复复杂度。
- **P1**：spec §10「无法可靠回填行进入 reconcile 并阻止对应 Conversation purge」需 export 端对账本无法重建行（如 `checkpoint.ack_digest` 缺失）的 fail closed 语义——目前无此 fail closed 检查。

---

## 3. Replay operation 六态

### 冻结契约（§S6-12.1）

| operation.state | replay 路由 |
|-----------------|------------|
| `scheduled` | **不执行**（restore-cancel 专属，零写） |
| `running` | **条件可重放**（owner 级；过六元组；**无 adapter 调用**） |
| `blocked` | **条件可重放**（owner 级；external/runtime 保持 `blocked` + reconcile） |
| `failed` | **默认不重放**（fail closed，人工） |
| `completed` | **只校验**（verify-only，不重复 side effect） |
| `cancelled` | **跳过** |

### 现状审计

| 路由 | 状态 |
|------|------|
| `scheduled` → 零写（归 restore-cancel） | ✅ 既有 `cancel_scheduled_operations_for_restore`（`erasure_repository.py:890-965`，scheduled→cancelled）已冻结；replay executor 对 scheduled 零写 |
| `running` → 条件可重放（owner 级；无 adapter） | **缺失**——`restore_replay_executor` 仅字符串 pending 登记（S6I2_PENDING_WRITERS），无本地清除 helper（与 purge 同谓词）实际实现 |
| `blocked` → 条件可重放（external/runtime 保持 blocked + reconcile） | **缺失**——同上；external/runtime 保持 `blocked` 路径未实现（依赖本地可证明清除 + 六元组 + 不调用 adapter） |
| `failed` → fail closed 人工 | **缺失**——replay executor 未实现；默认不重放语义未落地 |
| `completed` → verify-only（不重复 side effect） | **缺失**——ledger receipt/ack_digest 校验路径未独立化（嵌入 settlement `_ack_lost_repair`，非独立 replay executor） |
| `cancelled` → 跳过 | ✅ 既有 cancel-scheduled 路径已冻结 cancelled 状态；replay executor 跳过 cancelled 是默认 |
| 派生术语 `quiesced`/`rebuilding`（**不是**持久化状态） | ✅ §S6-12.4 明确禁止 imported ledger 出现此类值；当前 DB CHECK 闭集内确无此值（migration 034 冻结） |
| 跨层状态（同名 `erasing`/`blocked` 在 operation/checkpoint/fence 语义不同） | ✅ §S6-13 明确禁止跨层混读；现状严格按各 enum 闭集读 |

### P0/P1 风险

- **P0**：`running`/`blocked` 重放路径完全缺失——`restore_replay_executor` 是 PR-D 唯一主任务；缺失即 PR-D 未交付。
- **P1**：completed verify-only 嵌入 settlement ACK-lost repair 而非独立 replay executor——`ack_digest`/`checkpoint_digest` 校验在 settlement 中非独立路径，restore 端无法复用。

---

## 4. Owner 六元组

### 冻结契约（§S6-13.2）

> owner 是否可重放必须再结合六元组判定：`checkpoint.state` + `owner_key` + `ack_digest` + `owner_version` + `capability_digest` + `purge_revision`——**禁止只凭 operation.state 执行本地清除**；本地可证明清除 = 六元组全部与 ledger 快照自洽且 owner 属本地可清除类（workspace/execution/transport 域）。

### 现状审计

| 字段 | 持久化位置 | 状态 |
|------|-----------|------|
| `checkpoint.state` | `agent_conversation_purge_owners.state`（`ck_agent_purge_owner_state` 闭集：pending/erasing/blocked/failed/acked） | ✅ 持久化 |
| `owner_key` | `agent_conversation_purge_owners.owner_key`（registry 6 owner：workspace.core.v1 / execution.core.v1 / workspace.transport.v1 / execution.transport.v1 / external.payload.v1 / runtime.private.v1） | ✅ 持久化 |
| `ack_digest` | `agent_conversation_purge_owners.ack_digest`（state='acked' ⇒ 64-hex 非 NULL，ck_agent_purge_owner_ack 约束） | ✅ 持久化（仅 acked 时） |
| `owner_version` | `agent_conversation_purge_owners.owner_version` | ✅ 持久化 |
| `capability_digest` | `agent_conversation_purge_owners.capability_digest` | ✅ 持久化 |
| `purge_revision` | `agent_conversation_purges.purge_revision`（operation 表，跨 checkpoint 表 join） | ✅ 持久化（跨表） |

### 现状关键事实

- **六元组跨 2 表**：5 个字段在 `agent_conversation_purge_owners`（per-owner），`purge_revision` 在 `agent_conversation_purges`（per-operation）——恢复端必须跨表 join 重构。
- **本地可证明清除 owner 域**：workspace.core.v1 / execution.core.v1 / workspace.transport.v1 / execution.transport.v1 4 个 owner 域内的可证明清除 helper 已落地（`_erase_conversation_title` / `_anonymize_conversation_actors` / `_redact_messages` / `_delete_message_parts` / `_delete_user_states` / `_clear_terminal_outputs` / `_clear_context_snapshots` / `_clear_event_payloads` / `_clear_compatibility_outputs` 等——S6-4 矩阵行）。
- **external.payload.v1** / **runtime.private.v1** 不是「本地可证明清除」类——replay 时必须保持 `blocked` + reconcile（不调用 adapter、不冒充已 erase）。

### P0/P1 风险

- **P1**：六元组跨表 join 恢复——单表 record 不齐全，需带（`operation_id` 索引 + `owner_key`）join 重建——增加恢复复杂度与失败面。
- **P1**：owner 版本兼容性检查（`owner_version` + `capability_digest` 必须与 ledger 快照自洽）——当前 recovery 路径未独立化校验逻辑。

---

## 5. 实际执行语义

### 冻结契约（§S6-8.3 + §S6-13）

> 重放机制为 **M 类 sanctioned 维护路径**（集合锁 + 显式登记 S6-4；与 retention/audit jobs 互斥——重放期间暂停，冻结为显式声明）；**进行中 operation 处置**：一次性 replay 执行器完成剩余 owner 的本地清除（与 purge 同谓词、**无 adapter 调用**；external/runtime 未 acked 项 → `blocked` + reconcile 记录，**不冒充已 erase**）；不依赖生产 scheduler（S6-7.1 冻结生产不可达）；**digest 失配（旧代码账本 vs 新代码重算）**：重算基准 = 账本快照自身 owner_version，失配走 runbook 人工确认。

### 现状审计

| 项 | 状态 |
|----|------|
| 真实 DB 写入、CAS、回滚、幂等（execute 真 DB 写） | **缺失**——`restore_replay_executor` 仅字符串 pending 登记，无实现；PR-D 必须真实 DB 写而非仅生成 verdict/notes |
| 仅生成 verdict/notes 就称为 executor（**禁止**） | **冻结**——契约明确禁止；PR-D 实现必须真实执行本地清除 helper（`_erase_conversation_title` 等） |
| 本地 owner 清除复用既有 sanctioned helper | ✅ `_erase_conversation_title` / `_anonymize_conversation_actors` / `_redact_messages` / `_delete_message_parts` / `_delete_user_states` / `_clear_terminal_outputs` / `_clear_context_snapshots` / `_clear_event_payloads` / `_clear_compatibility_outputs` 全部已落地于 `packages/server-python/app/composition/workspace_erasure_participant.py` / `execution_erasure_participant.py`（S6-4 矩阵行） |
| `external.payload.v1` / `runtime.private.v1` 未 ACK → 保持 `blocked` + reconcile | **缺失**——路径未独立化（settlement 端 `_apply_window_outcome` 已落地 TD-106 方案 A，但 restore replay 路径未实现） |
| **禁止调用 external/runtime adapter** | ✅ 契约 §S6-8.3 明确「无 adapter 调用」；S6-4 restore 重放执行器矩阵行标注「不重复 adapter 调用，external/runtime 未 acked 项记 blocked+reconcile」；replay 实现必须严格遵守 |

### P0/P1 风险

- **P0**：实际 DB 写入能力完全缺失——replay executor 字符串登记，仅生成 verdict/notes 不构成 PR-D 交付。
- **P1**：external/runtime 未 ACK 项的 `blocked` + reconcile 路径未独立化——restore 端必须新建独立 helper（不复用 settlement helper），保持契约一致性。

---

## 6. M 类维护路径（集合锁 + 维护互斥）

### 冻结契约（§S6-4 + §S6-8.3）

> `restore 重放执行器`（S6-8 item 3；对恢复库执行账本记录的清除步骤；锁 = **M 类集合锁**；事务 = 一次性维护事务；tenant ✓；revision 无；**与 retention/audit jobs 互斥（重放期间暂停）**；不重复 adapter 调用，external/runtime 未 acked 项记 blocked+reconcile）

### 现状审计

| 项 | 状态 |
|----|------|
| 集合锁真实 API（`acquire_transport_aggregate_lock` 等） | ✅ 已落地：`packages/server-python/app/composition/agent_erasure_locks.py`（`acquire_owner_lock` / `acquire_transport_aggregate_lock`）——settlement `_close_window_ledger` 已使用（D8 锁协议：external `_collection_owner(ref.source_table)` + runtime `RUNTIME_PRIVATE_OWNER`） |
| M 类维护路径与 retention/audit jobs 互斥 | **缺失**——replay executor 未实现，无 `retentions_audits_paused` 互斥协调机制；spec §10.4 不存在 retentions_audits_paused 字段 |
| `retentions_audits_paused=True` 常量冒充互斥（**禁止**） | **冻结**——契约明确禁止；互斥必须是真实协调（修改持久化 flag + retention/audit jobs 启动前检查） |
| retention/audit jobs 启动前检查 paused flag | **缺失**——`run_event_retention` / `run_audit_retention` 启动路径未检查 paused 协调 flag |
| paused 协调 flag schema | **缺失**——无 migration 增加 paused 字段；属于 M 类路径新增 schema 项 |

### P0/P1 风险

- **P0**：M 类路径互斥机制完全缺失——`retentions_audits_paused` flag schema 缺失——**需新 schema/migration ⇒ 触发 §S6-10 停止条件「需要新 schema/migration」**。
- **P0**：retention/audit jobs 启动前 paused 检查未实现——replay 期间 retention/audit 可能并发执行，破坏「M 类与 retention/audit 互斥」契约。

---

## 7. Restore-before-open

### 冻结契约（§S6-8.1 + §S6-8.5 + §S6-8.6）

> 恢复顺序（Spec §3 末段逐字引用）：从旧快照恢复后**服务保持不可对外读写** → **先重放独立 erasure ledger** → **body/ref 扫描为零** → 才开放流量。
>
> body/ref 扫描：**复用 S5 六 owner 终态扫描**（scan_execution_body 等，`execution_erasure_participant.py:263-379` 谓词：payload_inline/payload_ref/terminal_output/compat output/context snapshot/actor 全覆盖）+ S6-6 巡检（tenant/digest/gap/ref/missing-fence 五类）。
>
> drill 降级声明：真实 pg_dump/恢复/流量开关演练**无法在本地执行**——**明确登记生产门禁**，完成声明降级为「重放机制与扫描经真实 PG 验证（contract-tested 级别）」，**不冒充已跑 restore drill**（R1-AC12 字面降级）。

### 现状审计

| 步骤 | 状态 |
|------|------|
| 旧快照恢复后服务保持不可对外读写 | ✅ traffic 开关层面（K8s/Docker Compose 维护窗口）——本仓无生产基建，spec §10.1 冻结「V1 不支持 purge 开启时仍有旧 Writer 进程在线」 |
| 独立 erasure ledger 重放 | **缺失**——replay executor 未实现；PR-D 唯一主任务 |
| Body/ref 扫描（六 owner 终态扫描） | ✅ 已落地 `scan_execution_body` 等 + S6-6 巡检 CLI（`scripts/verify_inspection`）——可复用 |
| 全部 owner scan 为零才开放流量 | **缺失**——restore-before-open 流程编排未实现；spec §10.5 冻结「人工签字后按 tenant/canary 开启 scheduler」 |
| 真实 pg_dump/恢复/流量开关演练 | **无法本地执行**——按 R1-AC12 字面降级为 contract-tested 验证；登记生产门禁 |
| restore-before-open runbook | **缺失**——`docs/02-delivery-plans/03-runbooks/` 不存在 `restore-before-open.md`（旧 scaffold 已随 #586 scope 收敛撤回） |

### P0/P1 风险

- **P0**：replay executor + 编排流程完全缺失——PR-D 唯一主任务；PR-D 完成后才能谈 restore-before-open runbook。
- **P1**：drill 降级声明需登记生产门禁——本仓无生产基建承接，runbook 完成度受生产门禁制约。

---

## 8. Writer / Conformance 登记

### 冻结契约（§S6-4 + §S6-2）

> `S6I2_PENDING_WRITERS` 登记 `restore_replay_executor` 仅 pending 不实现（M 类归属 S6-I3）。
>
> conformance suite 门禁（冻结）：实现阶段新增 `writer_conformance` 套件——静态枚举本矩阵全部写者（**含 S6 自身三 N 类写者 + 一 M 类写者**，遗漏任一 → 门禁失败）；`M` 写者逐项断言裁定理由（维护路径）。

### 现状审计

| 项 | 状态 |
|----|------|
| `S6I2_PENDING_WRITERS` 登记 `restore_replay_executor` | ✅ PR #584 I3 merge `ad7ac3e5` 后已登记（仅字符串 pending）——待 PR-D 完成后转 `registered` |
| conformance suite 静态枚举 `restore_replay_executor` | **缺失**——PR-D 完成后须新增 `_required_writer_specs()`（M 类：集合锁 + 一次性维护事务 + 与 retention/audit jobs 互斥声明 + 不调 adapter） |
| M 类写者裁定理由断言 | **缺失**——conformance 套件须新增 M 类断言（理由 = 维护路径 + 集合锁 + 一次性维护事务 + 不调 adapter） |
| 不接 production scheduler wiring | ✅ 契约 §S6-7.1 冻结「生产不可达」；PR-D 实现仍保持 M 类路径（不接线 scheduler） |
| 不翻 capability | ✅ 契约 §S6-4 冻结 capability_digest 不变更；PR-D 不修改 registry capability |

### P0/P1 风险

- **P1**：conformance suite 须新增 M 类写者枚举与裁定理由——PR-D 实现 + PR-D 测试同步。
- **P1**：`S6I2_PENDING_WRITERS` 转 `registered` 需 conformance suite 全绿——本任务 PR-D 仅做审计不实施，实施阶段需另起 stacked PR。

---

## 9. 测试与 mutation

### 冻结契约（§S6-5 / §S6-8 / §S6-14）

> PR-D 实现阶段：快照带 record kind/table identity；导入 + 重放 + body/ref 扫描 + S6-I2 verify + 全零才开放流量；每条路由至少一个真实 PG 正例和 fail-closed 负例；mutation 必须对应实际执行路径；NOT-RED 必须如实登记。

### 现状审计

| 项 | 状态 |
|----|------|
| 每条路由真实 PG 正例 | **缺失**——PR-D 实现 + 测试均未启动 |
| 每条路由 fail-closed 负例 | **缺失**——同上 |
| mutation kill（real PG execution path） | **缺失**——scaffold 已撤回；PR-D 须新建 `s6i3_d_ledger_replay_mutation_kill.py`（类似 `s6_td106_settlement_ledger_mutation_kill.py` 模式） |
| NOT-RED 如实登记 | **缺位**——本审计首次登记 PR-D 路由判别载体缺失清单（见下） |

### 判别载体缺失清单（PR-D 实施后须覆盖）

- 独立 ledger 连续导出/归档：
  - **正例缺失**：连续导出真实 ledger 4 表到独立 sink，端到端往返 = 同一 record
  - **负例缺失**：sink 不可达 / archive 中途崩溃 / 增量导出基点错位 → fail closed
- 快照格式与导入校验：
  - **正例缺失**：四表 record 各自 round-trip + schema version bump 后旧版本 codec fail closed
  - **负例缺失**：未知 record kind / table identity 失配 / 跨层 enum 混读 → `UNRECOGNIZED_STATE`
- Replay operation 六态：
  - **正例缺失**：`running`/`blocked` 重放本地可证明 owner → fence erased + checkpoint acked + body/ref scanned
  - **负例缺失**：`scheduled`/`failed`/`cancelled`/`completed` → 零写不调用 adapter
- Owner 六元组：
  - **正例缺失**：六元组全自洽 → 本地清除
  - **负例缺失**：任一字段不一致 → `DIGEST_MISMATCH`/`OWNER_VERSION_MISMATCH` fail closed
- M 类维护路径：
  - **正例缺失**：集合锁正确持有 + 一次性维护事务 + retention/audit 暂停
  - **负例缺失**：retention/audit 期间 replay 发起 → fail closed（互斥违规）
- Restore-before-open：
  - **正例缺失**：ledger 导入 + replay + body/ref scan 全零 → 开放流量模拟
  - **负例缺失**：body/ref scan 非零 → 服务保持不可读写

### P0/P1 风险

- **P0**：所有测试 + mutation 缺失——PR-D 实施后须补齐；本审计不实施。
- **P1**：NOT-RED 登记体系缺失——PR-D 实施后须严格登记无法 kill 的 mutation。

---

## 6 项阻塞问题答案

### Q1：导出原始 ref/session 值时，恢复库如何安全完成 source-ref CAS 清除？

**答案**：**禁止导出原始 `ref_value` / `runtime_session_ref`**——冻结契约 §S6-8.2「账本独立保存」原文限定 receipt/ack_digest 变更日志，**不包含**原始敏感 ref（spec §10 末段「不持久化原始 Chain-of-Thought、密钥、长期 Token 或未裁剪敏感响应」字面要求）。

恢复库 source-ref CAS 清除 = 重新调用 `write_erased_and_clear_ref`（B2 唯一清除路径，已落地于 `external_ref_erasure_participant.py`）但**以 adapter 未 ACK 为由保持 `blocked` + reconcile 记录**——**不冒充已 erase**（§S6-8.3 + §S6-13 字面要求「无 adapter 调用」）。

### Q2：当前是否有足够 receipt/digest 证明 per-ref/binding 收口？

**答案**：✅ 足够——TD-106 方案 A 已落地（PR #586 合 main）：

- per-ref `receipt_digest = external_erase_receipt_digest(adapter_key, adapter_version, idempotency_key, adapter_receipt_evidence, ref_digest, erase_outcome='erased')`（`external_ref_erasure_participant.py`）
- per-binding `runtime_destroy_receipt_digest`（`runtime_erasure_participant.py`）
- 集合锁 D8 内层逐源行（external `_collection_owner(ref.source_table)` + runtime `RUNTIME_PRIVATE_OWNER`）
- per-ref receipt 与 ledger `erase_state='erased'` + `receipt_digest` 同时落账

恢复端判定 = `ack_digest` 与 ledger 快照自洽 + `capability_digest` 一致 + `owner_version` 自洽 + `purge_revision` 自洽（§S6-13.2 六元组）——**充足**。

### Q3：仓库是否已有真正独立于数据库备份的归档 sink？

**答案**：❌ **完全缺失**——`scripts/` 仅含 mutation kill 驱动，无独立 archive sink、CLI、调度入口。

PR-D 必须新建：
- `scripts/s6i3_d_ledger_archive.py`（独立 archive sink）
- 调度入口：与 retention/audit jobs 互斥（需新 schema/migration 增设 `retentions_audits_paused` flag ⇒ **触发 §S6-10 停止条件「需要新 schema/migration」**）
- CLI 命令行入口（与 S6-6 `verify_inspection` 一致的 argparse + exit code 模式）

### Q4：M 类互斥是否有可执行协调机制？

**答案**：❌ **缺失**——

- 集合锁 API 已有（`acquire_transport_aggregate_lock`），但**与 retention/audit jobs 互斥**的协调 flag（`retentions_audits_paused`）未实现
- retention/audit jobs 启动前 paused 检查未实现
- replay executor 字符串登记但无 impl

PR-D 实施阶段须：
- 新增 `retentions_audits_paused` 字段（migration 044 或后续）⇒ **新 schema/migration**
- 实现 paused 协调机制（`retention_workers.py` 启动路径检查 paused + paused 时拒绝执行；replay executor 启动时设 paused = True + 完成后设 paused = False）
- **触发 §S6-10 停止条件「需要新 schema/migration」**——PR-D 实施前须由用户裁决是否批准新 migration

### Q5：completed verify-only 与 running/blocked 实际重放如何避免重复 side effect？

**答案**：✅ **契约已冻结避免路径**——

- `completed` 状态：`verify-only` 路径**不重复清除、不调用 adapter**（§S6-12.1 明确）；只校验 `ack_digest` / `checkpoint_digest` 与 ledger receipt + body/ref scan 一致
- `running`/`blocked` 状态：本地可证明清除 owner（workspace/execution/transport 域）走与 purge 同谓词 helper（`_erase_conversation_title` 等），但**不调 adapter**——与 settlement `_apply_window_outcome` SUCCESS 同事务收口机制一致（TD-106 方案 A 已验证）
- `ack_digest` 非 NULL 即**禁止重复 side effect**（§S6-12.2 checkpoint.state='acked' 路由）；`ck_agent_purge_owner_ack` 保证 64-hex digest 唯一性
- replay 端通过 ack_digest 唯一键 + owner_version 自洽 + 严格 M 类路径（一次性维护事务，不重复）保证幂等

### Q6：快照后完成、但数据库备份中不存在 ledger 记录的 purge 如何 fail closed？

**答案**：✅ **契约已冻结**——§S6-8.2：

> DB 内账本停在备份快照时点，**快照之后完成的 purge 在恢复库中既留有正文又无账本记录**，body scan 永不为零（永久 fail-closed）或按账本裁剪则正文复活——**冻结：快照后 purge 处置 = fail-closed 范围（该部分 conversation 保持服务关闭）+ 人工 reconcile 门禁（runbook 步骤），不得静默放行**。

具体执行：
- restore-before-open 阶段：body/ref scan 严格全零
- 若 scan 非零（snapshot 后 purge 产生残留）→ 该 conversation 保持服务关闭
- 人工 reconcile（runbook 步骤）记录具名 issue + 阻断 scheduler-enable + 不开放流量
- §S6-8.6 冻结「不冒充已跑 restore drill」（R1-AC12 字面降级）——**真实 restore drill 在生产门禁外不可执行**

---

## 已有能力 / 缺失能力 / P0/P1 风险汇总

### 已有能力（main @aff54883）

| 能力 | 位置 |
|------|------|
| TD-106 per-ref/binding 收口 | ✅ `agent_external_object_refs.erase_state='erased'` + `receipt_digest` + `agent_runtime_session_bindings.status='closed'` + `runtime_session_ref IS NULL` |
| Owner 六元组持久化（5/6 字段） | ✅ `agent_conversation_purge_owners`（5 字段）+ `agent_conversation_purges.purge_revision`（跨表） |
| 集合锁 API（D8） | ✅ `acquire_transport_aggregate_lock` / `acquire_owner_lock`（`agent_erasure_locks.py`） |
| Body/ref 六 owner 终态扫描 | ✅ `scan_execution_body` 等 + S6-6 `verify_inspection` 巡检 CLI |
| cancel_scheduled_operations_for_restore | ✅ `erasure_repository.py:890-965`（scheduled → cancelled） |
| 本地 owner 清除 sanctioned helper | ✅ `_erase_conversation_title` / `_redact_messages` / `_delete_message_parts` / `_delete_user_states` / `_clear_terminal_outputs` / `_clear_context_snapshots` / `_clear_event_payloads` / `_clear_compatibility_outputs` / `_anonymize_conversation_actors` |
| 三层 CHECK 闭集 | ✅ `ck_agent_purge_state`（operation 6 态）/ `ck_agent_purge_owner_state`（checkpoint 5 态）/ `ck_agent_erasure_fence_state`（fence 4 态） |
| S6I2_PENDING_WRITERS 登记 | ✅ `restore_replay_executor` 仅字符串 pending |

### 缺失能力（PR-D 须补齐）

| 能力 | 触发停止条件 |
|------|------------|
| **独立 archive sink / CLI / 调度入口** | 缺失 — PR-D 主任务 |
| **Ledger 连续导出（operation/checkpoint/ref/reconcile 四类）** | 缺失 — PR-D 主任务 |
| **快照 schema version + manifest digest + record_count** | 缺失 — PR-D 主任务（属 codec 层，无新 schema 字段） |
| **Restore replay executor（M 类路径 + 一次性维护事务 + 集合锁 + 与 retention/audit jobs 互斥）** | 缺失 — PR-D 主任务 |
| **`retentions_audits_paused` 协调 flag** | 缺失 — **需新 schema/migration ⇒ 触发 §S6-10 停止条件** |
| **retention/audit jobs 启动前 paused 检查** | 缺失 — 与 paused flag 同步 |
| **`running`/`blocked` 本地可证明 owner 重放 + `failed`/`completed`/`cancelled`/`scheduled` 路由** | 缺失 — PR-D 主任务 |
| **external/runtime 未 ACK 项 `blocked` + reconcile 路径** | 缺失 — restore 端须独立 helper（不复用 settlement helper） |
| **Restore-before-open 编排流程** | 缺失 — PR-D 主任务 |
| **`docs/02-delivery-plans/03-runbooks/restore-before-open.md`** | 缺失 — PR-D 主任务 |
| **drill 降级声明 + 生产门禁登记** | 缺失 — runbook 同步 |
| **PR-D 真实 PG 测试 + mutation kill** | 缺失 — PR-D 测试 + mutation 同步 |
| **`S6I2_PENDING_WRITERS.restore_replay_executor` 转 `registered`** | 缺失 — PR-D 完成 + conformance suite 全绿后 |

### P0/P1 风险（PR-D 实施前须用户裁决）

| 风险 | 级别 | 触发停止条件 |
|------|------|------------|
| 独立 archive sink 完全缺失 | **P0** | 不触发停止条件（PR-D 主任务） |
| replay executor 与 retention/audit jobs 互斥机制缺失 | **P0** | **需新 schema/migration ⇒ §S6-10 停止条件**（`retentions_audits_paused` flag） |
| restore-before-open 真实 PG 演练 | **P0** | 无生产基建 ⇒ R1-AC12 字面降级 + 生产门禁登记（§S6-8.6 冻结） |
| ledger snapshot 后 purge 的残留 conversation | **P0** | fail-closed 范围（§S6-8.2 冻结）+ 人工 reconcile（runbook） |
| 四表无 `schema_version` / `digest` / `record_count` 列 | **P1** | 不触发停止条件（codec 层绑定） |
| 六元组跨表 join 恢复 | **P1** | 不触发停止条件（实现复杂度） |
| external/runtime 未 ACK 项独立 `blocked` + reconcile helper | **P1** | 不触发停止条件（新增 helper，不修改 S5） |
| conformance suite M 类写者枚举 + 裁定理由断言 | **P1** | 不触发停止条件（实施同步） |

---

## 推荐：PR-D 是否可单 PR 执行 / 是否需拆 D1/D2

### 推荐：**拆 D1 / D2 两步走**

#### D1（本 PR 任务继续推进阶段，contract-first）

**Scope**：
- 独立 archive sink + ledger 连续导出 CLI（operation/checkpoint/ref/reconcile 四类）
- 快照 schema version + manifest digest + record_count（codec 层绑定，无 schema 字段）
- Restore 端 ledger 导入 + 六元组 join 重构 + schema version bump fail closed
- real PG 验证：ledger round-trip + schema version mismatch fail closed
- **不动 schema/migration**（`retentions_audits_paused` flag 暂缓）

**理由**：D1 交付 ledger 存档 + restore 端导入路径，与 §S6-10 停止条件「需要新 schema/migration」最小冲突；可独立完成 + 真实 PG 验证 + 评分 + 合并 + closeout。

#### D2（独立后续 PR，须用户裁决 schema 新增）

**Scope**：
- **`retentions_audits_paused` 新 schema flag**（migration 044 或后续）—— **须用户授权**
- Restore replay executor（M 类路径 + 一次性维护事务 + 集合锁 + 与 retention/audit jobs 互斥）
- replay operation 六态路由（`running`/`blocked`/`scheduled`/`failed`/`completed`/`cancelled`）
- external/runtime 未 ACK 项独立 `blocked` + reconcile helper
- Restore-before-open 编排 + body/ref scan 集成
- `docs/02-delivery-plans/03-runbooks/restore-before-open.md`
- `S6I2_PENDING_WRITERS.restore_replay_executor` 转 `registered`
- conformance suite M 类写者枚举与裁定理由
- real PG 验证：六态路由 + 互斥 + body/ref scan + 服务开关编排

**理由**：D2 涉及新 schema/migration（D8 paused flag）+ capability 翻转路径——属 §S6-10 停止条件边界，**须用户裁决后再启动**。

### 推荐理由（事实审计依据）

- D1 不涉及新 schema/migration / capability 翻转 / S5 状态机修改——符合 §S6-10 现有 PR-D 期望范围（contract-first + 真实 PG 验证）
- D2 必须新增 paused flag（属「M 类与 retention/audit jobs 互斥」契约必备）——单一 PR 实施时必然触及 §S6-10 停止条件「需要新 schema/migration」——须用户裁决
- 拆分后 D1 评分 ≤ 100 可独立完成；D2 须专项评审 paused flag schema + capability 决策

---

## 本轮明确「零业务代码实现」

- 本审计文档**不实施**任何业务代码
- 不创建 ledger export executor / archive sink / restore replay executor
- 不创建 restore-before-open runbook 文档
- 不实现 paused flag schema / migration
- 不实现 replay operation 六态路由
- 不实现 external/runtime 未 ACK 项独立 `blocked` + reconcile helper
- 不实施 conformance suite M 类写者枚举

---

## 关键引用

- 任务卡：`docs/03-engineering-governance/current-work.md` TASK-R1-S6-I3-D
- Spec: `docs/02-delivery-plans/01-specs/2026-07-27-req-041-047-r1-retention-purge-recovery.md` §3 / §10 / §11
- Plan: `docs/02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md` §R1-S6-8 / §R1-S6-12 / §R1-S6-13 / §R1-S6-14 / §R1-S6-15.5
- REQ-047: `docs/01-product-planning/05-requirements/REQ-047-agent-run-artifact-approval-center.md`
- 工程门禁：`docs/03-engineering-governance/01-rules/quality-gates.md`、`engineering-principles.md`、`data-integrity.md`、`testing.md`
- PR-D 基线：main `aff5488381e0e84878dd386cbc83be5abad3745a`（2026-08-27 closeout of PR #596/#597）
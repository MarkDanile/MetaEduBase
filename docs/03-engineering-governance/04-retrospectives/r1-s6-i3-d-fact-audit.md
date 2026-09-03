# R1-S6-I3-D 事实审计（contract-to-code，第二轮事实纠偏 + merged-boundary 收口标注）

> Status: 🟡 TASK-R1-S6-I3-D 整体仍进行中（PR-D 剩余 operational closeout / PR-E / C1 / S5 wiring / capability flip / 六 erase 入口生产可达仍未启动）；**D1a 子阶段 🟢 已完成并入 main**（PR #598 squash mergeCommit `5868831e`，source head `ca9f4404`，FINAL_IMPL_HEAD `8a836733`，评分 97 Original；评审对象 main@`aff54883`..`8a836733` 净 diff 7 文件 4941+/1-）；**D1b 子阶段 🟢 已完成并入 main**（PR #600 squash mergeCommit `01c84f7c`，source head `467e8d24`，FINAL_IMPL_HEAD `061f4a66`，评分 commit `1293ea51`，correction commit `467e8d24`，评分 94 Original；评审对象 main@`5e1d4dff`..`061f4a66` 净 diff 7 文件 3088+/5-）；**D2 子阶段 🟢 已完成并入 main**（PR #602 squash mergeCommit `ae7f3c98`，source head `177a226a`，FINAL_IMPL_HEAD `4bc22328`，评分 92 Original；评审对象 main@`b88704a7`..`4bc22328` 净 diff 14 文件 6814+/48-；Round-8/8.1 三面复审 P0/P1/P2/P3=0；writer `restore_replay_executor` 保持 `registered=FENCE_M`）；**pure-docs closeout PR #603 squash mergeCommit `4b92b980`**（仅 3 治理文件 current-work / work-log / §17.7 零代码/测试/schema/migration/registry/CI 改动）
>
> 任务卡：`docs/03-engineering-governance/current-work.md` TASK-R1-S6-I3-D
>
> 本审计范围仅作为 contract-to-code 推导依据保留——D1a 已落 main 不再需要评审触发审计；本文档不修改冻结 Plan 文字，「待用户裁决」章节已 supersede（见下）
>
> 本轮输入 baseline：`4cf3ab369af240873754d6e6c9890a92c2c03e39`（不要在 committed 文档写"当前 HEAD"——每次提交后自我陈旧）
>
> 冻结契约：Plan §S6-8 / §S6-12 / §S6-13 / §S6-14 / §S6-15.5（已随 PR #586 / #591 / #592 / #596 合入 main）
>
> 净 diff 统计仅在 PR body 记录，不嵌入 committed 文档（易漂移）
>
> **⚠️ 历史文档 supersede 说明**：本文档 §1 「archive sink 待用户裁决」、§6 「M 类互斥三方案 / 待用户裁决 A/B/C」、§10 「runtime per-binding proof 路径用户裁决 a/b/c」三处章节的所有「待用户裁决」表述，**已被 current-work §17.5 用户裁决完全 supersede**（2026-08-27）：
> - Runtime per-binding proof = **c**（用户裁决 c：仅显式标记 `runtime_per_binding_proof_available=False`，不重算 per-binding receipt）
> - D1b archive sink = **专用 MinIO archive bucket**（不复用 `minio_bucket=metaedu-resources`）
> - D2 M 类互斥 = **A 方案**（PostgreSQL advisory maintenance lock；须写作 S6-4 锁序登记修订）
> - D1a-D1b-D2 = **三独立 PR**
> - 顺序 = **D1a → D1b → D2**
>
> 本审计保留历史讨论**仅作为 contract-to-code 推导依据**——任何读 PR #598 / current-work TASK-R1-S6-I3-D 章节请以 §17.5 裁决为准；本文档不修改冻结 Plan 文字，但「待用户裁决」章节已不再代表当前待办。

## 0. 审计范围与边界 + 本轮 correction 目标

**包含（本轮 correction）**：
- 修正前版事实错误：Runtime per-binding proof 不足 / CAS 描述混层 / Advisory lock 边界描述不完整 / D1a/D1b/D2 边界错位 / 元数据状态更新
- 当前 main `@aff54883` 真实代码能力 vs 冻结契约 §S6-8/12/13/14 实施要求 逐项对照
- 三方案互斥决策矩阵（A. advisory lock / B. external coordinator / C. persistent lease）——**仅并列评估，本轮不正式选择**
- 已有能力、缺失能力、P0/P1 风险点（含未决 P1/stop condition 登记）
- D1a/D1b/D2 边界与拆分推荐 + 待用户裁决项

**不包含（本审计明确排除）**：
- 业务代码实现（ledger export executor / archive sink port / restore replay executor / restore-before-open runbook）
- 复制、恢复旧 `c07c031c` scaffold
- 修改 Plan / 技术债总账 / work-log / Score Log / Metrics / migration 043 / schema / registry capability / 门禁脚本 / KNOWN_ISSUES / CI 配置
- 启动 PR-E / C1 / S5 production wiring / capability flip / 六 erase 入口生产可达
- 新增 `retentions_audits_paused` schema / migration（具体载体待用户裁决）
- 本轮**不正式选择** A / B / C 任一互斥方案
- 不修改冻结 Plan（§S6-8 / §S6-12 / §S6-13 / §S6-14 / §S6-15.5 文字原样保留）

---

## 1. 独立 ledger 连续导出 / 归档

### 冻结契约（§S6-8.2）

> S5-SCH-0 持久化账本（operation `agent_conversation_purges` + checkpoint `agent_conversation_purge_owners` + external ref `agent_external_object_refs` + reconcile `agent_transport_scope_reconcile`）**必须连续导出/归档到独立于 DB 备份的存储**（receipt/ack_digest 变更日志）—— Spec §3「从**独立保存**的 erasure operation/receipt 账本重放」字面要求；DB 内账本停在备份快照时点，**快照之后完成的 purge 在恢复库中既留有正文又无账本记录**，body scan 永不为零（永久 fail-closed）或按账本裁剪则正文复活。

### 现状审计

| 项 | 状态 |
|----|------|
| 独立于 DB 备份的安全存储 sink | **缺失**——`scripts/` 仅含 mutation kill 驱动；无独立 archive sink |
| Ledger 导出 CLI（连续/增量） | **缺失**——`packages/server-python/alembic/` migrations 无 export/ledger 类迁移；旧 `__pycache__/s6i3_ledger_export.cpython-314.pyc` 是已撤回 scaffold 的 stale 缓存，源码已删 |
| Ledger 归档调度入口 | **缺失**——`S6I2_PENDING_WRITERS` 登记 `restore_replay_executor` 仅字符串 pending，无 ledger exporter 登记 |
| CLI ≠ sink 区分 | **冻结区分**——CLI 是 producer；sink 是**独立于数据库备份**的持久目标，二者必须分别落地；不得将 CLI 称为 sink |

### archive sink 最小正确性（contract-first 推导，非冻结契约；待用户裁决）

| 属性 | 要求 |
|------|------|
| **原子发布** | export 完成必须原子可见（write-then-rename / segment+manifest atomic）——避免半文件被恢复端误读 |
| **manifest/content digest** | manifest 自带 content digest（SHA-256），恢复端导入前先校验 manifest digest 匹配全部 record；否则 `DIGEST_MISMATCH` fail closed |
| **record count** | manifest 记录每个 record kind 的 record count；恢复端对账不符时 `COUNT_MISMATCH` fail closed |
| **tenant 隔离** | manifest + records 必须按 tenant 隔离；恢复端按 tenant 维度逐个导入 |
| **monotonic cursor/watermark** | 增量导出必须单调推进 watermark（per record kind + tenant）；崩溃后可从 watermark 重放不丢不重 |
| **crash 后半文件判定** | sink 上必须不出现「写一半」的 record 或 manifest；写失败必须 atomic rollback；恢复端可拒绝任何 part-file |
| **重复导出幂等** | 同一 watermark 重导必须 idempotent（sink 端去重 / UPSERT 语义）；manifest 应记录 export_id + parent_export_id 链 |
| **sink 不可达处理** | sink 不可达（非零退出 + 抛异常）⇒ export 端 **保持旧 watermark 不前进** + 不抹掉上次成功 manifest；DB 内 ledger 仍存，retry 可恢复 |

### 生产级 sink 候选（实仓只读核对，**不推荐具体实现**）

| 候选 | 仓库现状 | 备注 |
|------|---------|------|
| Object storage（MinIO/S3/GCS/blob） | `packages/server-python/app/config.py` 含 `minio_endpoint` / `minio_access_key` / `minio_secret_key` / `minio_bucket`（**仅作 Conversation 资源存储**）——**未实现专用 ledger archive sink port** | 资源存储 ≠ ledger archive sink；现有 MinIO 用于 Conversation 资源上传，不携带 ledger 语义、manifest 与 watermark |
| Atomic file write/rename helper | 无 `app/composition/s6i3_d_ledger_archive.py` 等 archive helper | 通用 `os.rename` 可用但需配套 manifest + atomic-publish helper |
| 加密 / 权限 / retention policy | **缺失**——无 ledger archive 的密钥 / IAM / retention 配置 | spec §10.5 未冻结细节 |
| Scheduler / CLI 配置入口 | `scripts/` 仅 mutation kill 驱动；无 ledger archive CLI / cron | retention workers 由 `conversation_purge_scheduler` claim 路径触发，**非 cron 调度** |

### 结论

- **CLI ≠ sink**：D1a（codec + 导出 CLI）≠ D1b（独立 archive sink port）
- **生产 durable sink 若仓库缺配置**，只能登记生产门禁，**不能冒充连续独立归档完成**（§S6-8.6 drill 降级声明同等适用）
- **D1a** = codec + manifest + bounded snapshot/segment exporter + decode/validate（**只读 / 不持久推进 watermark / 不发布到 sink / 不做 DB mutation**——详见 §4 D1a/D1b/D2 边界）
- **D1b** = archive sink port + 原子发布 + 持久 cursor/watermark + crash/retry/idempotency → 才形成 continuous archive
- D1a 与 D1b 不可合并于 single PR（语义不同：read-only vs write-persistent）

---

## 2. 快照格式与导入校验

### 冻结契约（§S6-13.3）

> 导入快照必须带 record kind/table identity（operation/checkpoint/ref/reconcile 四类具名区分）：避免相同 `state` 字段跨 operation/checkpoint/fence 混读；快照 schema version 变更须显式 bump。

### 现状审计

| 字段 | 状态 |
|------|------|
| Schema version 字段 | **缺失**——`agent_conversation_purges` / `agent_conversation_purge_owners` / `agent_external_object_refs` / `agent_transport_scope_reconcile` 均无 `schema_version` 列；快照导出需 codec 层绑 schema version 并在 manifest 写 |
| Record kind/table identity 区分 | **缺失**——四类 record 在导出端必须分别命名（`agent_purge_operation` / `agent_purge_owner_checkpoint` / `agent_external_ref_erase_state` / `agent_transport_reconcile`），导出端 codec 无现成基座 |
| Tenant 字段 | ✅ 现有 `tenant_id` 列全 4 表 |
| Count 字段 | **缺失**——manifest 记录（codec 层，非 schema 列） |
| SHA-256 digest | **缺失**——manifest digest（codec 层） |

### 重要事实修正：四层 CAS / 唯一约束 严格分离

下表**严格区分四层**各自证明什么；**不得用任一层证明另一层的特性**：

| 层 | 约束 / 机制 | 证明什么 | **不**证明什么 |
|----|------------|---------|------------|
| **DB 结构层 #1（checkpoint ACK CHECK）** | `ck_agent_purge_owner_ack`（migration 034）| `state='acked'` ⇒ `ack_digest IS NOT NULL AND char_length(ack_digest) = 64`；`state<>'acked'` ⇒ `ack_digest IS NULL` ——**只约束「acked 必有 64-char digest；非 acked 必须 NULL」**，**不校验 hex 内容** | hex 字符合规、digest 单调、digest 唯一性、runtime per-binding receipt |
| **DB 结构层 #2（owner row UNIQUE）** | `uq_agent_purge_owner(tenant_id, purge_operation_id, owner_key)`（migration 034）| **同一 conversation + owner 仅允许一行 checkpoint**——不同 owner 可独立 ACK；同一 owner 重 ACK 必走同一 row CAS | ack_digest 唯一性、external ref CAS 幂等、runtime binding CAS 幂等、digest 正确性 |
| **应用层 digest 生成** | `external_erase_receipt_digest(adapter_key, adapter_version, idempotency_key, adapter_receipt_evidence, ref_digest, erase_outcome='erased')` | 64-char hex digest 计算（`canonical_digest` via SHA-256 over canonical JSON envelope，schema_version=1） | DB 落账成功、CAS 收敛、idempotency_key 全局唯一 |
| **应用层 digest 生成（runtime）** | `runtime_destroy_receipt_digest(adapter_key, adapter_version, idempotency_key, adapter_receipt_evidence, session_digest, destroy_outcome)` | 同上（runtime private envelope） | DB 落账成功、CAS 收敛、idempotency_key 全局唯一 |
| **CAS 收敛层 #1（checkpoint ACK 写）** | `_apply_window_outcome` SUCCESS 路径（settlement.py:1361-1377）| **ORM 状态转换 + flush**（Conversation/operation/checkpoint 锁 + T2 token 重验保护下）| checkpoint 写幂等需由 `uq_agent_purge_owner`（同 operation+owner 仅一行）+ ORM transaction 保证；**不是 SQL rowcount CAS 谓词** |
| **CAS 收敛层 #2（external ref 写）** | `write_erased_and_clear_ref` 路径（`external_ref_erasure_participant.py:308`）`UPDATE agent_external_object_refs SET erase_state='erased', receipt_digest=:d, blocked_reason=NULL WHERE id = :id AND erase_state='registered' AND receipt_digest IS NULL` + 随后按 source row 匹配清 `payload_ref` | **single-writer guarded transition**——rowcount=1 成功；rowcount=0 fail closed（不冒充 helper 自身幂等成功）| checkpoint 写幂等、binding 写幂等、digest 重算正确性（需 adapter evidence）|
| **CAS 收敛层 #3（runtime binding 写）** | `write_erased_and_close_binding` 路径（`runtime_erasure_participant.py`）`UPDATE agent_runtime_session_bindings SET runtime_session_ref=NULL, status='closed', ... WHERE tenant_id = :t AND id = :id AND runtime_session_ref = :rv` | **single-writer guarded transition**——rowcount=1 成功；rowcount=0 fail closed | checkpoint 写幂等、external ref 写幂等、digest 重算正确性（需 adapter evidence）|
| **CAS 收敛层 #4（runtime binding failure 写）** | `_write_binding_failure` 路径（`runtime_erasure_participant.py:983`）`UPDATE agent_runtime_session_bindings SET status='invalid', revision=revision+1, ... WHERE tenant_id = :t AND id = :id AND runtime_session_ref IS NOT NULL` | **single-writer guarded transition**——rowcount=1 成功；rowcount=0 fail closed | 同上 |

### 重要修正（明确删除前版错误表述）

- ❌ **删除**「`ck_agent_purge_owner_ack` 要求 64-hex `ack_digest`」——该约束**只校验长度 64**，**不校验 hex 字符**；hex 校验在应用层（`canonical_digest` 经 SHA-256 自动产出 64-char hex）
- ❌ **删除**「`ack_digest` 唯一性保证幂等」——`ack_digest` 本身**没有 DB 唯一约束**；幂等性由 `uq_agent_purge_owner`（owner row 唯一）+ 应用层 CAS（rowcount=1）共同保证
- ❌ **删除**「`ack_digest` 64-hex 唯一键」——`ack_digest` 不是键；唯一键是 `(tenant_id, purge_operation_id, owner_key)`
- ❌ **删除**「`uq_agent_purge_owner` 证明 ref/binding CAS 幂等」——owner row 唯一约束与 ref/binding CAS 幂等是**完全独立**的两层保证
- ❌ **删除**「external receipt 可从 DB 重算」隐含语义——`receipt_digest` 列**可从 DB 导出**（是 64-char hex），但**缺 `adapter_receipt_evidence` 时无法重算原始 receipt**（recompute 失败）；仅可作为已落账 receipt digest 的**载体**而非**证明重算来源**

### Operation / Checkpoint / Ref / Reconcile 字段映射

| 字段 | 持久化位置 | 备注 |
|------|-----------|------|
| Operation | `agent_conversation_purges`（state / failure_code / revision / registry_digest / retention_policy_digest / hold_revision_snapshot / lease_epoch / next_retry_at） | ✅ 齐全 |
| Checkpoint（per owner） | `agent_conversation_purge_owners`（owner_key / owner_version / capability_digest / state / attempt / checkpoint_digest / ack_digest / reason_code） | ✅ 齐全（**ack_digest 仅 acked 时非 NULL**） |
| External ref | `agent_external_object_refs`（ref_scheme / ref_value / source_table / source_row_id / conversation_id / erase_state / receipt_digest） | ✅ 齐全（TD-106 方案 A） |
| | ⚠️ **不导出原始 `ref_value`**——spec §10「不持久化原始 Chain-of-Thought、密钥、长期 Token 或未裁剪敏感响应」字面要求；恢复端**由 ledger 快照 + 恢复库源行 identity join 重构**，不依赖原 ref | |
| Reconcile | `agent_transport_scope_reconcile`（issue_code / owner_key / source_table / class_scope / conversation_scope / resolved_at） | ✅ 齐全（migration 040） |
| Body / payload / secret / 自由文本泄露 | ✅ 4 表均无正文/事件 payload 列 | 导出端需复检每条 record 字段名白名单 |

### Owner 六元组（持久化跨 2 表）

5 字段在 `agent_conversation_purge_owners`（per-owner），1 字段 `purge_revision` 在 `agent_conversation_purges`（per-operation）——恢复端必须跨表 join 重构。

### P0/P1 风险

- **P0**：四表无 `schema_version` / `digest` / `record_count` 列——导出端需 codec 层绑 schema version 并写 manifest；恢复端 codec 必须按 version 显式 bump——**无 schema version 字段 ⇒ 快照不可版本化**
- **P1**：六元组跨表 join 恢复——单 record 不齐全，需 join 重建——增加恢复复杂度
- **P1**：spec §10「无法可靠回填行进入 reconcile 并阻止对应 Conversation purge」需 export 端对账本无法重建行（如 `checkpoint.ack_digest` 缺失）的 fail closed 语义

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
| `scheduled` → 零写 | ✅ `cancel_scheduled_operations_for_restore`（`erasure_repository.py:890-965`）已冻结 |
| `running` → 条件可重放（owner 级；无 adapter） | **缺失**——`restore_replay_executor` 仅字符串 pending 登记 |
| `blocked` → 条件可重放 | **缺失**——同上；external/runtime 保持 `blocked` + reconcile 路径未实现 |
| `failed` → fail closed 人工 | **缺失**——同上 |
| `completed` → verify-only | **缺失**——ledger receipt/ack_digest 校验嵌入 settlement `_ack_lost_repair`，非独立 replay executor |
| `cancelled` → 跳过 | ✅ cancel-scheduled 路径已冻结 cancelled 状态 |
| 派生术语 `quiesced`/`rebuilding` | ✅ §S6-12.4 明确禁止 imported ledger 出现此类值；migration 034 CHECK 闭集内确无此值 |
| 跨层状态（同名字段不同语义） | ✅ §S6-13 明确禁止跨层混读 |

### P0/P1 风险

- **P0**：`running`/`blocked` 重放路径完全缺失——`restore_replay_executor` 是 D2 主任务
- **P1**：completed verify-only 嵌入 settlement ACK-lost repair 而非独立 replay executor
- **P1（runtime proof 缺口）**：runtime per-binding receipt 不可重算（详见 §6 Runtime per-binding proof）——**runtime completed verify-only 路径须在 P1 裁决前**——详见 §4 D2 runtime 边界

---

## 4. Owner 六元组

### 冻结契约（§S6-13.2）

> owner 是否可重放必须再结合六元组判定：`checkpoint.state` + `owner_key` + `ack_digest` + `owner_version` + `capability_digest` + `purge_revision`——**禁止只凭 operation.state 执行本地清除**

### 现状审计（六元组字段跨 2 表）

| 字段 | 持久化位置 | 状态 |
|------|-----------|------|
| `checkpoint.state` | `agent_conversation_purge_owners.state`（`ck_agent_purge_owner_state` 闭集） | ✅ 持久化 |
| `owner_key` | `agent_conversation_purge_owners.owner_key` | ✅ 持久化 |
| `ack_digest` | `agent_conversation_purge_owners.ack_digest`（**仅 acked 时非 NULL**） | ✅ 持久化（条件性） |
| `owner_version` | `agent_conversation_purge_owners.owner_version` | ✅ 持久化 |
| `capability_digest` | `agent_conversation_purge_owners.capability_digest` | ✅ 持久化 |
| `purge_revision` | `agent_conversation_purges.purge_revision` | ✅ 持久化（跨表） |

### 本地可证明清除 owner 域

`workspace.core.v1` / `execution.core.v1` / `workspace.transport.v1` / `execution.transport.v1` 4 个 owner 域内的可证明清除 helper 已落地（`_erase_conversation_title` / `_anonymize_conversation_actors` / `_redact_messages` / `_delete_message_parts` / `_delete_user_states` / `_clear_terminal_outputs` / `_clear_context_snapshots` / `_clear_event_payloads` / `_clear_compatibility_outputs` 等——S6-4 矩阵行）。

### `external.payload.v1` / `runtime.private.v1`

不是「本地可证明清除」类——replay 时必须保持 `blocked` + reconcile（**不调用 adapter、不冒充已 erase**）。

### P0/P1 风险

- **P1**：六元组跨表 join 恢复——单表 record 不齐全
- **P1**：owner 版本兼容性检查（`owner_version` + `capability_digest` 必须与 ledger 快照自洽）

---

## 5. 实际执行语义

### 冻结契约（§S6-8.3 + §S6-13）

> 重放机制为 **M 类 sanctioned 维护路径**（集合锁 + 显式登记 S6-4；与 retention/audit jobs 互斥——重放期间暂停，冻结为显式声明）；**进行中 operation 处置**：一次性 replay 执行器完成剩余 owner 的本地清除（与 purge 同谓词、**无 adapter 调用**）；不依赖生产 scheduler；**digest 失配**：重算基准 = 账本快照自身 owner_version。

### 现状审计

| 项 | 状态 |
|----|------|
| 真实 DB 写入、CAS、回滚、幂等 | **缺失**——`restore_replay_executor` 仅字符串 pending 登记 |
| 仅生成 verdict/notes 就称为 executor（**禁止**） | **冻结禁止** |
| 本地 owner 清除复用既有 sanctioned helper | ✅ `_erase_conversation_title` / `_redact_messages` / `_delete_message_parts` / `_delete_user_states` / `_clear_terminal_outputs` / `_clear_context_snapshots` / `_clear_event_payloads` / `_clear_compatibility_outputs` / `_anonymize_conversation_actors` |
| `external.payload.v1` / `runtime.private.v1` 未 ACK → `blocked` + reconcile | **缺失**——settlement `_apply_window_outcome` 已落地 TD-106 方案 A；restore replay 路径未独立实现 |
| **禁止调用 external/runtime adapter** | ✅ §S6-8.3 + §S6-13 字面要求 |

### P0/P1 风险

- **P0**：实际 DB 写入能力完全缺失——replay executor 字符串登记，仅生成 verdict/notes 不构成 D2 交付
- **P1**：external/runtime 未 ACK 项的 `blocked` + reconcile 路径未独立化

---

## 6. M 类维护路径（集合锁 + 维护互斥）

### 冻结契约（§S6-4 + §S6-8.3）

> `restore 重放执行器`（S6-8 item 3；对恢复库执行账本记录的清除步骤；锁 = **M 类集合锁**；事务 = 一次性维护事务；tenant ✓；revision 无；**与 retention/audit jobs 互斥（重放期间暂停）**；不重复 adapter 调用，external/runtime 未 acked 项记 blocked+reconcile）

### 重要修正（明确删除前版错误结论）

- ❌ **删除**「`retentions_audits_paused` flag 缺失 ⇒ 需新 schema/migration 044」
- ❌ **删除**「M 类路径互斥机制完全缺失」作为结论性事实
- ✅ **修正为**：**冻结契约只规定 replay 与 retention/audit jobs 互斥**，**未指定互斥载体**——具体载体（A/B/C 三方案）由用户裁决；本审计列出 3 个候选方案供用户抉择
- ✅ **本轮不正式选择 A/B/C**——三方案各有边界条件，等用户裁决；不修改冻结 Plan 文字

### 三方案互斥决策矩阵（仅评估，不选择）

#### A. PostgreSQL advisory maintenance lock

| 维度 | 评估 |
|------|------|
| 跨进程有效性 | ✅ `pg_advisory_lock`（session-level）/ `pg_advisory_xact_lock`（transaction-level）；跨进程互斥 |
| crash 自动释放 | ⚠️ **session-level**：session/backend 终止时自动释放；**风险**：连接仍存活但遗漏 unlock（应用代码 bug / 异常路径未 unlock）——**transaction-level 在 commit/rollback/session failure 时释放**（**推荐事务级**，自动随事务边界清理） |
| stale owner / takeover | **N/A**——advisory lock 无持久 lease owner / ttl / 接管语义；等待者在锁释放后继续，**不接管已释放的锁持有者身份** |
| 是否需要 schema | ❌ 否——纯 PostgreSQL 内置 |
| **是否修改 retention workers** | ✅ **非零改动**：两个 retention worker（`run_event_retention` / `run_audit_retention`）的**每个事务**都须取 shared lock（`pg_advisory_xact_lock_shared`）；replay 事务取 exclusive lock（`pg_advisory_xact_lock`）——**A 方案并非"零代码 wiring"** |
| **锁序影响** | ⚠️ 新锁**必须**在 Run 行锁 / Conversation 行锁 / owner advisory lock / collection 锁（`_collection_owner` 集合锁）**之前**取得；使用同一稳定 namespace/scope（避免与 D8 集合锁冲突）；**写作 S6-4 锁序登记修订**——冻结 Plan §S6-4 未含此锁，**须用户授权登记**（即使不修改 schema） |
| 测试方式 | real PG 双连接验证（类似 F10 `_BlockingLookupAdapter` 模式） |
| production wiring 依赖 | ❌ 无——纯 DB 层 |
| 是否满足当前冻结契约 | ✅ §S6-4 M 类路径未限定具体锁类型；§S6-8.3「与 retention/audit jobs 互斥」字面满足 |

**优点**：零 schema 改动；DB 内置；事务边界自动释放；跨进程。
**缺点**：无 owner/ttl（不能 stale takeover）；须明确锁序位置（写作 S6-4 锁序修订）；须 retention worker 启动路径加 shared lock（**非零代码改动**）。

#### B. 外部 deployment/maintenance coordinator

| 维度 | 评估 |
|------|------|
| 跨进程有效性 | ⚠️ 依赖外部系统（K8s / Docker Compose / systemd / 部署协调器）；**仓内无 maintenance coordinator 实现** |
| crash 自动释放 | ⚠️ 取决于外部系统——若 coordinator 本身 crash，须人工介入 |
| stale owner / takeover | ⚠️ 取决于外部系统设计 |
| 是否需要 schema | ❌ 否 |
| 是否修改 retention workers | ⚠️ 须在 retention worker 启动前检查 coordinator token / gate |
| 锁序影响 | ❌ 无 |
| 测试方式 | ⚠️ 仓内 mock external coordinator；真实端到端需生产基建——**本地无法验证** |
| production wiring 依赖 | ✅ **高**——必须部署 K8s coordinator / maintenance service / 类似基建；本仓无此基建 |
| 是否满足当前冻结契约 | ⚠️ §S6-8.6「drill 降级声明」原文「无生产基础设施、无备份保留 runbook 执行环境」——本仓无生产基建，外部 coordinator 路径等同于不可本地验证 |

**优点**：零 schema 改动；零 DB 锁影响；语义清晰（deployment 显式 maintenance mode）。
**缺点**：**本仓无 production wiring 基建**（spec §10.5「V1 不支持 purge 开启时仍有旧 Writer 进程在线」原文）——若只能靠 runbook 声明、代码无法 fail closed，则**不得称为 executor 互斥已闭合**。

#### C. 持久化 DB maintenance lease/flag

| 维度 | 评估 |
|------|------|
| 跨进程有效性 | ✅ DB 行级锁；跨进程；CAS 收敛 |
| crash 自动释放 | ⚠️ 取决于 lease expiry + takeover 设计；**stale lease 须 takeover** |
| stale owner / takeover | ✅ 可设计 `owner` / `lease_expires_at` / `takeover` |
| 是否需要 schema | ✅ **是**——migration 044+ 新增 maintenance_lease 表 / 列 |
| 是否修改 retention workers | ✅ 须在 retention worker 启动前检查 lease 状态；并支持 takeover |
| 锁序影响 | ⚠️ lease 取锁须在 Run 行锁之前或独立连接池；新增写者须 S6-4 矩阵登记 |
| 测试方式 | real PG（lease 取/续/takeover/expire） |
| production wiring 依赖 | ⚠️ 中——lease 本身不需生产基建，但 takeover 须 K8s readiness 等 |
| 是否满足当前冻结契约 | ⚠️ §S6-8.3 文字「互斥」满足；但 §S6-10 停止条件「需要新 schema/migration」**直接触发**——须用户授权 migration 044 |

**优点**：明确 owner / takeover / expiry 语义；可被 restore-before-open 复用；与 §S6-8.6 drill 降级协调（生产门禁登记）。
**缺点**：**需新 schema/migration**——直接触发 §S6-10 停止条件；新增 writer 须 S6-4 矩阵登记；migration roundtrip 风险。

### 三方案对比总览

| 维度 | A. advisory lock | B. external coordinator | C. persistent lease |
|------|------------------|-------------------------|---------------------|
| 跨进程 | ✅ | ⚠️ | ✅ |
| crash 安全 | ⚠️（事务级 OK） | ⚠️ | ✅（lease expiry） |
| stale takeover | **N/A** | ⚠️ | ✅ |
| 无 schema 改动 | ✅ | ✅ | ❌ |
| 无 production wiring | ✅ | ❌ | ⚠️ |
| 本地真实 PG 可测 | ✅ | ❌ | ⚠️ |
| 满足冻结契约 | ✅ | ⚠️ | ⚠️（触发 §S6-10 停止条件） |
| 复杂度 | 中（须 retention worker 取 shared lock + 锁序修订） | 高（须外部基建） | 中-高（须新 schema + writer 矩阵） |

### 推荐

**本审计阶段不做方案选择**——三方案各有边界条件，需用户裁决。本轮明确：
- **不创建 migration 044**（A 方案无须 schema；B 方案不依赖 schema；C 方案须用户授权）
- **不修改冻结 Plan**（§S6-4 锁序登记修订须用户授权）
- **不正式选择 A / B / C 任一互斥方案**——评估已并列列出，等用户裁决

### P0/P1 风险（修正后）

- **P0（修正）**：互斥机制**具体载体**缺失（无 flag、无 advisory lock 接线、无 maintenance coordinator）——**修复路径见三方案决策**，**冻结契约未强制具体载体**
- **P1**：retention/audit jobs 启动前 paused 检查未实现——三种方案均须修改 retention worker（但 A 改动最小）
- **P1**：原结论「需新 schema/migration」——**已撤回**；具体载体由用户裁决

---

## 7. Restore-before-open

### 冻结契约（§S6-8.1 + §S6-8.5 + §S6-8.6）

> 恢复顺序：旧快照恢复后**服务保持不可对外读写** → **先重放独立 erasure ledger** → **body/ref 扫描为零** → 才开放流量。
>
> body/ref 扫描：复用 S5 六 owner 终态扫描（`scan_execution_body` 等，`execution_erasure_participant.py:263-379`）+ S6-6 巡检（tenant/digest/gap/ref/missing-fence 五类）。
>
> drill 降级声明：真实 pg_dump/恢复/流量开关演练**无法在本地执行**——**明确登记生产门禁**，完成声明降级为「重放机制与扫描经真实 PG 验证（contract-tested 级别）」，**不冒充已跑 restore drill**。

### 现状审计

| 步骤 | 状态 |
|------|------|
| 旧快照恢复后服务保持不可对外读写 | ✅ spec §10.1 冻结「V1 不支持 purge 开启时仍有旧 Writer 进程在线」——K8s/Docker Compose 维护窗口 |
| 独立 erasure ledger 重放 | **缺失** |
| Body/ref 扫描 | ✅ `scan_execution_body` + S6-6 `verify_inspection` 巡检 CLI 可复用 |
| 全部 owner scan 为零才开放流量 | **缺失**——restore-before-open 编排未实现 |
| 真实 pg_dump/恢复/流量开关演练 | **无法本地执行**——按 R1-AC12 字面降级为 contract-tested 验证 |
| restore-before-open runbook | **缺失**——`docs/02-delivery-plans/03-runbooks/` 不存在 `restore-before-open.md` |

### P0/P1 风险

- **P0**：replay executor + 编排流程完全缺失——D2 主任务
- **P1**：drill 降级声明需登记生产门禁

---

## 8. Writer / Conformance 登记

### 冻结契约（§S6-4 + §S6-2）

> `S6I2_PENDING_WRITERS` 登记 `restore_replay_executor` 仅 pending 不实现（M 类归属 S6-I3）。
>
> conformance suite 门禁（冻结）：实现阶段新增 `writer_conformance` 套件——静态枚举本矩阵全部写者（**含 S6 自身三 N 类写者 + 一 M 类写者**）。

### 现状审计

| 项 | 状态 |
|----|------|
| `S6I2_PENDING_WRITERS` 登记 `restore_replay_executor` | ✅ PR #584 I3 merge `ad7ac3e5` 后已登记（仅字符串 pending） |
| conformance suite 静态枚举 | **缺失**——D2 完成后须新增 `_required_writer_specs()`（M 类：集合锁 + 一次性维护事务 + 与 retention/audit jobs 互斥声明 + 不调 adapter） |
| M 类写者裁定理由断言 | **缺失**——conformance 套件须新增 M 类断言 |
| 不接 production scheduler wiring | ✅ §S6-7.1 冻结「生产不可达」；D2 实现仍保持 M 类路径 |
| 不翻 capability | ✅ §S6-4 冻结 capability_digest 不变更 |

### P0/P1 风险

- **P1**：conformance suite 须新增 M 类写者枚举与裁定理由——D2 实现 + 测试同步
- **P1**：`S6I2_PENDING_WRITERS` 转 `registered` 需 conformance suite 全绿——本任务 PR-D 仅做审计

---

## 9. 测试与 mutation

### 冻结契约（§S6-5 / §S6-8 / §S6-14）

> PR-D 实现阶段：快照带 record kind/table identity；导入 + 重放 + body/ref 扫描 + S6-I2 verify + 全零才开放流量；每条路由至少一个真实 PG 正例和 fail-closed 负例；mutation 必须对应实际执行路径；NOT-RED 必须如实登记。

### 现状审计

| 项 | 状态 |
|----|------|
| 每条路由真实 PG 正例 | **缺失**——D1a / D1b / D2 实现 + 测试均未启动 |
| 每条路由 fail-closed 负例 | **缺失**——同上 |
| mutation kill（real PG execution path） | **缺失**——D1a / D2 须新建 mutation kill 脚本（类似 `s6_td106_settlement_ledger_mutation_kill.py` 模式） |
| NOT-RED 如实登记 | **缺位**——本审计首次登记 PR-D 路由判别载体缺失清单（见下） |

### 判别载体缺失清单（D1a/D1b/D2 实施后须覆盖）

- 独立 ledger 连续导出/归档（D1a / D1b）：
  - **正例缺失**：连续导出真实 ledger 4 表到独立 sink，端到端往返 = 同一 record
  - **负例缺失**：sink 不可达 / archive 中途崩溃 / 增量导出基点错位 → fail closed
- 快照格式与导入校验（D1a）：
  - **正例缺失**：四表 record 各自 round-trip + schema version bump 后旧版本 codec fail closed
  - **负例缺失**：未知 record kind / table identity 失配 / 跨层 enum 混读 → `UNRECOGNIZED_STATE`
- Replay operation 六态（D2）：
  - **正例缺失**：`running`/`blocked` 重放本地可证明 owner → fence erased + checkpoint acked + body/ref scanned
  - **负例缺失**：`scheduled`/`failed`/`cancelled`/`completed` → 零写不调用 adapter
- Owner 六元组（D2）：
  - **正例缺失**：六元组全自洽 → 本地清除
  - **负例缺失**：任一字段不一致 → `DIGEST_MISMATCH`/`OWNER_VERSION_MISMATCH` fail closed
- M 类维护路径（D2）：
  - **正例缺失**：互斥机制正确（方案 A/B/C 任一选定后）→ 集合锁正确持有 / 一次性维护事务 / retention/audit 暂停
  - **负例缺失**：互斥违规（retention/audit 期间 replay 发起）→ fail closed
- Restore-before-open（D2）：
  - **正例缺失**：ledger 导入 + replay + body/ref scan 全零 → 开放流量模拟
  - **负例缺失**：body/ref scan 非零 → 服务保持不可读写

### P0/P1 风险

- **P0**：所有测试 + mutation 缺失——D1a / D1b / D2 实施后须补齐
- **P1**：NOT-RED 登记体系缺失——D1a / D2 实施后须严格登记无法 kill 的 mutation

---

## 10. Runtime per-binding proof（第二轮核心纠偏 — 登记为未决 P1 / 停止条件）

### 关键事实（重新核对）

> **RuntimeErasureSummary.receipt_digests 是 `runtime_erasure_participant.py:163` 内存态**——`receipt_digests: tuple[str, ...] = ()` 字段仅在 `_DestroyResult`/`RuntimeErasureSummary` 内存对象中持有；**adapter_receipt_evidence** 同样仅在内存中传递给 `runtime_destroy_receipt_digest` 重算函数，**未持久化**。
>
> 持久化路径：`runtime_erasure_participant.py:932` `ack_digest = summary.ack_digest()` 把内存 receipt_digests 列表**折叠为单一聚合 ack_digest** 后写入 `agent_conversation_purge_owners.ack_digest`（一次性 commit）。**adapter_receipt_evidence 不落库**。
>
> `agent_runtime_session_bindings` 表**无 receipt_digest 列**（`runtime_session_ref` / `status` / `active_stream_id` / `stream_lease_expires_at` 等）——binding 行即事实源（closed + ref NULL = erased；status='closed' + ref 保留 = blocked/unknown）。
>
> ⚠️ **恢复端不能逐 binding 重算 `runtime_destroy_receipt_digest`**——`adapter_receipt_evidence` 缺失 ⇒ `runtime_destroy_receipt_digest` 重算必失败（envelope 输入不齐全）。

### 重要事实修正（前版误述删除）

- ❌ **删除**「runtime 有完整 per-binding receipt 载体」——**无独立 receipt_digest 列**
- ❌ **删除**「恢复端可逐 binding 重算 receipt digest」——**adapter_receipt_evidence 未持久化，重算必失败**
- ❌ **删除**「`RuntimeErasureSummary.receipt_digests` 可作为 per-binding 证明」——**内存态，仅被折叠为聚合 ack_digest**
- ❌ **删除**「runtime per-binding receipt 充足」结论——**仅聚合 ack_digest 充足**；per-binding 不可独立证明
- ❌ **删除**「RuntimeErasureSummary + ack_digest 聚合 + Tx2 final scan 联合证明」表述——**Tx2 final scan 仅证明 `runtime_session_ref IS NULL`（session 终止），不证明 receipt 正确性**

### 实际可证明 / 不可证明 边界

| 可证明（恢复后） | 不可证明（恢复后） |
|---------------|-----------------|
| ✅ `agent_runtime_session_bindings` 行存在 + `runtime_session_ref IS NULL` + `status='closed'`（session 已销毁） | ❌ 单个 binding 的 `runtime_destroy_receipt_digest`（缺 adapter_receipt_evidence + session_digest 不可独立重建）|
| ✅ `agent_conversation_purge_owners.ack_digest` 非 NULL（聚合 ack，**不是 per-binding receipt**）| ❌ per-binding receipt 的 hex 内容（ack_digest 是 SHA-256 over sorted receipt_digests 列表，**不可逆**）|
| ✅ `agent_runtime_session_bindings.runtime_session_ref` 由 session ref → NULL（adapter 已 destroy 的副作用） | ❌ adapter 是否真实 destroy（adapter_receipt_evidence 已丢失）|
| ✅ Tx2 final scan `runtime_session_ref IS NOT NULL` 计数 | ❌ per-binding adapter evidence 与 destroy outcome |

### 未决 P1 / 停止条件登记

**runtime per-binding receipt 不可重算 + 不可独立证明 = D2 范围内 runtime completed verify-only 路径的硬阻塞**。

候选方案（**仅列出，不选择**）：

| 方案 | 描述 | 触发停止条件 |
|------|------|------------|
| **a. 新增可持久化的 per-binding archive evidence** | 新增 `agent_runtime_session_bindings.archive_evidence` 列（migration 044+）+ adapter_receipt_evidence 落库 + 恢复端可逐 binding 重算 | 触发 §S6-10「需要新 schema/migration」 |
| **b. 契约明确允许 aggregate verify-only** | §S6-12.1 `completed` 路由允许 `ack_digest` 聚合验证替代 per-binding 证明——需用户裁决（**当前冻结契约 §S6-13.2 六元组不含此放宽**） | 触发「冻结契约与当前可执行能力冲突」停止条件 |
| **c. runtime restore 路径零写 fail-closed + 人工 reconcile** | runtime completed 状态 replay 时**拒绝**逐 binding 重算 → 标记 `blocked` + reconcile 记录 + runbook 人工——runtime 不通过 D2 自动恢复 | 不触发停止条件（保守实现） |

**关联 TD-106 已登记 runtime per-binding receipt P2**（`docs/03-engineering-governance/technical-debt.md#td-106`）：
> (P2-1) runtime per-binding receipt 形参零使用（`write_erased_and_close_binding` 接收形参零使用，语义=ACK 证据链输入，不加列）

**TD-106 P2-1 在本审计中**：
- ⚠️ 不得写成已解决
- ⚠️ 不得被 D2 自动覆盖（runtime completed verify-only 路径仍存在 per-binding 证明缺失）

### D2 启动前置条件（runtime proof 路径必须先裁决）

D2 在 `runtime per-binding proof` 路径未裁决前**不得宣称完整覆盖 runtime completed verify-only**。

**本轮明确不**：
- 不正式选择 a / b / c 任一方案
- 不修改 §S6-12.1 / §S6-13.2 冻结契约
- 不实施 D2 runtime completed verify-only 路径
- 不将 TD-106 P2-1 标记为已解决

---

## 11. D1a / D1b / D2 边界（第二轮核心纠偏）

### D1a：只读 codec + manifest + bounded snapshot/segment exporter + decode/validate

**严格限定**（**只读**）：
- ✅ Ledger snapshot codec（schema version 绑 manifest）
- ✅ Manifest 设计（content digest + record count + tenant 隔离 + monotonic cursor/watermark 字段）
- ✅ **Deterministic bounded snapshot/segment exporter**（导出一致性证明 + 字节级确定性）
- ✅ **Decode / validate**（恢复端导入前 manifest digest 校验 + schema version 校验 + record count 对账）
- ✅ **只读 identity reconstruction**（恢复端按 row identity + ledger snapshot join 重建六元组）

**严格禁止**（**D1a 不得称 continuous archive**）：
- ❌ **不得持久推进 watermark**（即 D1a 不持有"上次成功 cursor"——watermark 概念属 D1b sink 端）
- ❌ **不得发布到 sink**（D1a 是 read-only codec + decoder + bounded exporter；sink 选择/接线属 D1b）
- ❌ **不得做 DB mutation**（D1a 不调 adapter / 不写 ref / 不清 binding / 不动 checkpoint / 不动 fence / 不动 operation）
- ❌ **不得称 replay executor**（D1a 不执行 owner 重放；replay executor 属 D2）
- ❌ **不得称 restore replay executor / restore-before-open runbook**

**D1a 是后续代码 PR**（**删除前版"puredocs-only" 表述**）——D1a 实施需新增 codec 模块 + 测试 + mutation kill 脚本，但**不动 schema / 不接 sink / 不做 DB mutation**。

### D1b：archive sink port + 原子发布 + 持久 cursor/watermark + crash/retry/idempotency

**限定**：
- ✅ 独立 archive sink port 实现（依赖用户裁决：本地 minio / 外部 S3 / 文件系统）
- ✅ 原子发布（write-then-rename / segment+manifest atomic）
- ✅ 持久 cursor/watermark（per record kind + tenant，sink 端存储）
- ✅ Crash 安全（half-file detection + recovery）
- ✅ Retry 语义（指数退避 + sink 不可达 fail closed）
- ✅ Idempotency（同一 watermark 重导）

**D1b + D1a 合并评估**：
- ✅ **若 sink 选型明确**（本地 minio）+ D1a 与 D1b 评审面可控 ⇒ **可合并为单 PR D1**
- ❌ **若 sink 选型未定**（外部 S3 / 自建 object store）⇒ **必须分拆**

D1b 与 D1a **不可合并于**「D1a 是只读 codec + decoder + bounded exporter + identity reconstruction」的语义层——D1b 引入 sink 持久推进 watermark 改变了语义边界。

### D2：消费已验证 archive + 执行 DB mutation + 六态路由 + 维护互斥 + scan + restore-before-open

**限定**：
- ✅ 消费 D1a 验证后的 archive（decode/validate 已通过）
- ✅ 执行 DB mutation（六元组验证通过后的本地清除）
- ✅ 六态路由（`scheduled` / `running` / `blocked` / `failed` / `completed` / `cancelled`）
- ✅ M 类维护路径互斥（依赖 §6 三方案用户裁决）
- ✅ body/ref 扫描（复用 S5 六 owner + S6-6 巡检）
- ✅ Restore-before-open 编排

**D2 启动前置条件（必须先裁决）**：
- ⚠️ **§6 M 类互斥方案用户裁决**（A / B / C 任一）
- ⚠️ **§10 runtime per-binding proof 路径用户裁决**（a / b / c 任一）
- ⚠️ D1a codec 必须先就绪（恢复端必须能 decode/validate）

**D2 在 runtime proof 裁决前**：
- ❌ **不得宣称完整覆盖 runtime completed verify-only 路径**
- ❌ **不得宣称覆盖 §S6-8.6「drill 降级声明」中的"重放机制经真实 PG 验证"完成**
- ❌ **不得将 runtime completed 状态加入 D2 mutation 判别载体**

---

## 12. 三方案互斥决策矩阵（汇总）

见 §6。

**本轮不正式选择 A / B / C**——评估已并列列出，等用户裁决；不修改冻结 Plan 文字。

---

## 13. 6 项阻塞问题答案（fact-audit 第二轮 correction）

### Q1：导出原始 ref/session 值时，恢复库如何安全完成 source-ref CAS 清除？

**答案（修正）**：

**禁止导出原始 `ref_value` / `runtime_session_ref`**——冻结契约 §S6-8.2「账本独立保存」原文限定 receipt/ack_digest 变更日志，**不包含**原始敏感 ref（spec §10 末段「不持久化原始 Chain-of-Thought、密钥、长期 Token 或未裁剪敏感响应」字面要求）。

恢复库 source-ref CAS 清除必须分 owner 状态：

| Operation 状态 | 恢复库 identity 重建路径 | 行为 |
|---|---|---|
| `completed` / `acked` | 恢复库**旧 ledger 行**（`agent_external_object_refs` 行的 `id` / `source_table` / `source_row_id` ——非敏感）+ **旧源行**（`agent_workspace_outbox` 等）——**identity join 重建六元组**（按 row identity 与 ledger snapshot join）| `B2 唯一清除路径 write_erased_and_clear_ref`（`external_ref_erasure_participant.py:308`）**CAS** `UPDATE ... WHERE id = :id AND erase_state = 'registered' AND receipt_digest IS NULL` → ledger `erase_state='erased'` + `receipt_digest` + 源 outbox `payload_ref=NULL` |
| `running` / `blocked` | 恢复库**旧 ledger 行**（per-ref）+ **旧源行**（已残留/未清除）——不需原始 `ref_value`——`B2` helper 需 `ref_value` 仅用于 B2 内部 identity 重验；**identity 重验后可调 `write_erased_and_clear_ref` 的简化路径**（详见 `external_ref_erasure_participant.py:870-878` 「ref_value 仅用于身份重验」字面要求）| `B2` CAS（同上）；仅本地可证明 owner（workspace/execution/transport）走；external/runtime 未 ACK 仍保持 `blocked` + reconcile |
| `external.payload.v1` / `runtime.private.v1` 未 ACK | 恢复库**旧 ledger 行**提供 identity；但 adapter 不可调（无生产可达 + spec §10「不冒充已 erase」）——**禁止 CAS cleared** | **保持 `blocked` + reconcile**（§S6-8.3 + §S6-13 字面要求）；replay executor **不调用 adapter** |

**任一 CAS 所需值无法证明 ⇒ 零写 + fail closed + runbook 人工处置**（§S6-13.4 字面要求 `DIGEST_MISMATCH` / `OWNER_VERSION_MISMATCH` / `UNRECOGNIZED_STATE`）。

### Q2：当前是否有足够 receipt/digest 证明 per-ref/binding 收口？

**答案（严格修正 — runtime proof 不可重算）**：

| Owner | per-ref/binding receipt 状态 | 证明载体 | 恢复端可独立重算？ |
|------|---------------------------|----------|---------------|
| **`external.payload.v1`** | ✅ **per-ref 持久化**：`agent_external_object_refs.receipt_digest` | `external_erase_receipt_digest(adapter_key, adapter_version, idempotency_key, adapter_receipt_evidence, ref_digest, erase_outcome='erased')` 重算（64-char hex，SHA-256 over canonical JSON envelope，schema_version=1）| ⚠️ **条件性可重算**——**仅当 `adapter_receipt_evidence` 可重建**（如 adapter log / 第三方 receipt service 持久化）；缺 evidence 时**重算失败** |
| | CAS 收敛 | `WHERE id = :id AND erase_state = 'registered' AND receipt_digest IS NULL`（CAS 幂等） | ✅ single-writer guarded transition（rowcount=1 成功；rowcount=0 fail closed） |
| | | ⚠️ `receipt_digest` 列**可从 DB 导出**（是 64-char hex）；但**不能**从列值重算原始 envelope | ❌ 缺 `adapter_receipt_evidence` |
| **`runtime.private.v1`** | ❌ **无 per-binding 持久化**——`agent_runtime_session_bindings` 表**无 `receipt_digest` 列** | `RuntimeErasureSummary.receipt_digests`（**内存态**）→ 折叠为聚合 `ack_digest` → 写入 `agent_conversation_purge_owners.ack_digest` | ❌ **不可逐 binding 重算**——`adapter_receipt_evidence` 未持久化 |
| | 持久化载体 | binding 行 `runtime_session_ref IS NULL` + `status='closed'`（**仅 session 终止证明**） | ✅ session ref → NULL（adapter 已 destroy 副作用）|
| | CAS 收敛 | `write_erased_and_close_binding`：`WHERE tenant_id = :t AND id = :id AND runtime_session_ref = :rv` | ✅ single-writer guarded transition（rowcount=1 成功；rowcount=0 fail closed） |
| | 聚合载体 | `agent_conversation_purge_owners.ack_digest`（聚合 digest，**不是 per-binding receipt**）| ⚠️ 聚合收口证明 + 不可逆 |
| | ⚠️ **TD-106 P2-1 仍登记未关**（runtime per-binding receipt 形参零使用） | — | 不得标记已解决 |

**严格禁止**：
- ❌ **不得用 `checkpoint.ack_digest` 聚合 digest 冒充 per-binding receipt**——`ack_digest` 是聚合 ack，**不是** per-binding receipt
- ❌ **不得恢复端跳过 per-binding identity 重验**（`ref_value` 已 NULL/缺失可跳过；非 NULL 但 mismatch ⇒ fail closed）
- ❌ **不得用 `RuntimeErasureSummary.receipt_digests` 作为恢复后 per-binding 证明**——`receipt_digests` 是**内存态**，adapter_receipt_evidence 同样未持久化，**不可重算**

**结论**：
- ✅ **external 有完整 per-ref receipt 载体**（条件性重算依赖 `adapter_receipt_evidence` 可重建）
- ❌ **runtime 无 per-binding receipt 独立证明**——详见 §10 未决 P1 登记（runtime proof 路径必须用户裁决 a / b / c 任一方案）
- ❌ **不得将 runtime per-binding receipt 路径作为 D2 实施载体**——D2 启动前 runtime proof 必须先裁决

### Q3：仓库是否已有真正独立于数据库备份的归档 sink？

**答案**：

**已识别候选**：
- ✅ `packages/server-python/app/config.py` 含 MinIO 配置（`minio_endpoint` / `minio_access_key` / `minio_secret_key` / `minio_bucket`）——**但仅用于 Conversation 资源存储**（用户上传文件等），**不携带 ledger 语义、manifest 与 watermark**
- ✅ 通用 `os.rename` / `tempfile.NamedTemporaryFile` 可作为原子 publish helper 基座——但**无 ledger archive sink port 封装**
- ❌ **无 ledger archive 专用配置**（密钥 / IAM / retention policy）
- ❌ **无 ledger archive scheduler / cron 入口**（retention workers 由 `conversation_purge_scheduler` claim 路径触发，**非 cron**）

**关键修正**：
- ❌ **前版误称 `scripts/s6i3_d_ledger_archive.py` 为"独立 archive sink"**——**CLI 是 producer**（产生 archive 输出）；**sink 是独立于 DB 备份的持久目标**（CLI + sink 是 producer/consumer 关系）
- ✅ **D1a** = codec + manifest + bounded snapshot/segment exporter + decode/validate（**只读 / 不持久推进 watermark / 不发布到 sink / 不做 DB mutation**）
- ✅ **D1b** = archive sink port + 一个明确验证层级的实现（**依赖 sink 选型**——用户裁决：本地 minio / S3 / 其他 object store / 文件系统）
- ⚠️ **生产 durable sink 若仓库缺配置**——**只能登记生产门禁，不能冒充连续独立归档完成**（§S6-8.6 drill 降级声明同等适用）

### Q4：M 类互斥是否有可执行协调机制？

**答案（修正）**：

**前版结论已撤回**：❌ 不得继续主张「必须新增 `retentions_audits_paused` 字段/migration 044」——**冻结契约只规定 replay 与 retention/audit 互斥，未指定互斥载体**。

**当前事实**：互斥机制**具体载体**缺失；具体载体（A / B / C 三方案）由用户裁决——见 §6 三方案互斥决策矩阵。

**任一方案下，互斥实现要点**：

| 方案 | 实现要点 | 约束 |
|------|---------|------|
| A. advisory lock | 两个 retention worker（`run_event_retention` / `run_audit_retention`）的**每个事务**取 `pg_advisory_xact_lock_shared`；replay 事务取 exclusive lock（`pg_advisory_xact_lock`）；新锁**必须**在 Run/Conversation/owner/collection 锁**之前**取得，使用同一稳定 namespace/scope | A 方案**非零代码改动**（两个 retention worker 启动路径）；写作 S6-4 锁序登记修订（须用户授权） |
| B. external coordinator | 仓内无 production wiring 基建——若只能靠 runbook 声明，**不得称为 executor 互斥已闭合** | spec §10.5「V1 不支持 purge 开启时仍有旧 Writer 进程在线」 |
| C. persistent lease | migration 044+；新增 maintenance_lease 表/列；takeover 设计 | **触发 §S6-10 停止条件**「需要新 schema/migration」 |

**本轮明确不创建 migration 044**（A 方案无须 schema；B 方案不依赖 schema；C 方案须用户授权）。
**本轮明确不修改冻结 Plan**——S6-4 锁序登记修订须用户授权。

### Q5：避免 completed verify-only 与 running/blocked 重放重复 side effect

**答案（修正 — 严格四层分离）**：

| 维度 | 保证机制 |
|------|---------|
| `completed` 不重复 side effect | §S6-12.1 字面「verify-only」——**只校验 ledger receipt + body/ref scan**；**不调用 adapter、不执行本地清除** |
| `running`/`blocked` 不重复 owner side effect | `uq_agent_purge_owner(tenant_id, purge_operation_id, owner_key)` 同 owner 仅一行 checkpoint + 单事务保护（Conversation/operation/checkpoint 锁 + T2 token 重验）|
| checkpoint ACK 写 | ORM 状态转换 + flush（Conversation/operation/checkpoint 锁 + T2 token 重验保护下）| ORM 单事务保证（**不是 SQL rowcount CAS 谓词**）|
| external ref 写 | `UPDATE ... WHERE id = :id AND erase_state='registered' AND receipt_digest IS NULL` + 源 row `payload_ref` 匹配 | single-writer guarded transition（rowcount=1 成功；rowcount=0 fail closed）|
| runtime binding 写 | `UPDATE ... WHERE id = :id AND runtime_session_ref = :rv` | single-writer guarded transition（rowcount=1 成功；rowcount=0 fail closed）|
| `ack_digest` 唯一性 | ❌ **`ack_digest` 没有 DB 唯一约束**——仅有 `ck_agent_purge_owner_ack` 约束长度 64 | 幂等性由 owner row 唯一 + 应用层 CAS 共同保证 |
| M 类路径一次性维护事务 | replay executor 一次性 commit；不留中间状态 | |
| 不调用 adapter | §S6-8.3 + §S6-13 字面要求 | |
| 跨 purge 周期幂等 | 同 operation 重复 replay ⇒ 同一 owner row（`uq_agent_purge_owner`）⇒ ack_digest 已非 NULL ⇒ CAS rowcount=0 ⇒ fail closed（不再二次写） | |
| 跨 conversation 幂等 | 不同 conversation 不同 `purge_operation_id` ⇒ 不同 owner row ⇒ 不冲突 | |

**关键修正**：
- ❌ 不得用 `ack_digest` "唯一性"作为幂等保证——`ack_digest` 不唯一约束
- ✅ 幂等保证 = `uq_agent_purge_owner`（owner row 唯一）+ 四层 single-writer guarded transition（checkpoint ORM 状态转换 + external ref rowcount guard + runtime binding rowcount guard + runtime binding failure rowcount guard）——**互不替代** |

### Q6：快照后完成、但数据库备份中不存在 ledger 记录的 purge

**答案（修正）**：✅ §S6-8.2 字面冻结：

> DB 内账本停在备份快照时点，**快照之后完成的 purge 在恢复库中既留有正文又无账本记录**，body scan 永不为零（永久 fail-closed）或按账本裁剪则正文复活——**冻结：快照后 purge 处置 = fail-closed 范围（该部分 conversation 保持服务关闭）+ 人工 reconcile 门禁（runbook 步骤），不得静默放行**。

**关键事实**：
- ❌ **不得按账本裁剪**（会正文复活）
- ✅ **保持服务关闭 + 人工 reconcile**——snapshot 后 purge 范围 conversation 保持不可读写
- ❌ **不得静默放行**——§S6-8.6 字面要求

---

## 14. 已有能力 / 缺失能力 / P0/P1 风险汇总（第二轮 correction）

### 已有能力（main @`aff54883`）

| 能力 | 位置 |
|------|------|
| TD-106 per-ref receipt（external） | ✅ `agent_external_object_refs.receipt_digest`（`external_erase_receipt_digest` 重算，64-char hex SHA-256）——**条件性可重算**（依赖 `adapter_receipt_evidence` 可重建） |
| Runtime 聚合 receipt 载体 | ✅ `agent_conversation_purge_owners.ack_digest`（聚合 digest，**不是 per-binding receipt**）——`RuntimeErasureSummary.receipt_digests` 内存态折叠 |
| Runtime session 终止证明 | ✅ `agent_runtime_session_bindings.runtime_session_ref IS NULL` + `status='closed'` |
| TD-106 P2-1 runtime per-binding receipt | ⚠️ **仍登记未关**（详见 §10 + technical-debt.md#td-106 P2-1）——**不得写成已解决** |
| `ck_agent_purge_owner_ack` | ✅ 长度 64 + state 条件非 NULL/IS NULL（**不校验 hex**） |
| `uq_agent_purge_owner` | ✅ (tenant_id, purge_operation_id, owner_key) 唯一——**owner row CAS 幂等层**（**不证明** ref/binding CAS 幂等） |
| 四层 single-writer guarded transition | ✅ checkpoint ORM 状态转换 + external ref rowcount guard + runtime binding rowcount guard + runtime binding failure rowcount guard（详见 §2 表）|
| Owner 六元组持久化（5/6 字段） | ✅ `agent_conversation_purge_owners`（5 字段）+ `agent_conversation_purges.purge_revision`（跨表）|
| 集合锁 API（D8） | ✅ `acquire_transport_aggregate_lock` / `acquire_owner_lock`（`agent_erasure_locks.py`）|
| Body/ref 六 owner 终态扫描 | ✅ `scan_execution_body` 等 + S6-6 `verify_inspection` 巡检 CLI |
| `cancel_scheduled_operations_for_restore` | ✅ `erasure_repository.py:890-965`（scheduled→cancelled）|
| 本地 owner 清除 sanctioned helper | ✅ `_erase_conversation_title` / `_redact_messages` / `_delete_message_parts` / `_delete_user_states` / `_clear_terminal_outputs` / `_clear_context_snapshots` / `_clear_event_payloads` / `_clear_compatibility_outputs` / `_anonymize_conversation_actors` |
| 三层 CHECK 闭集 | ✅ `ck_agent_purge_state` / `ck_agent_purge_owner_state` / `ck_agent_erasure_fence_state` |
| MinIO 资源存储（**非 ledger archive**） | ✅ `packages/server-python/app/config.py` MinIO 配置 |
| `S6I2_PENDING_WRITERS` 登记 | ✅ `restore_replay_executor` 字符串 pending |

### 缺失能力（PR-D 须补齐）

| 能力 | 触发停止条件 / 依赖 |
|------|------------|
| **D1a**：codec + manifest + bounded snapshot/segment exporter + decode/validate + 只读 identity reconstruction | 缺失（**D1a 是后续代码 PR**）——不动 schema / 不持久推进 watermark / 不发布 sink / 不做 DB mutation |
| **D1b**：archive sink port + 原子发布 + 持久 cursor/watermark + crash/retry/idempotency | 缺失 ——**用户裁决**：专用 MinIO archive bucket（不复用 `minio_bucket=metaedu-resources`）；本轮不实现 D1b |
| **D2**：replay executor + 维护互斥 + 六态路由 + restore-before-open | 缺失 ——**依赖**：(1) M 类互斥方案裁决（A / B / C）(2) runtime proof 路径裁决（a / b / c）(3) D1a codec 就绪 |
| **§6 M 类互斥机制具体载体** | 缺失（**具体载体由用户裁决**） |
| **§10 runtime per-binding proof 路径** | 缺失（**具体路径由用户裁决**）——TD-106 P2-1 仍登记未关 |
| PR-D 真实 PG 测试 + mutation kill | 缺失 ——D1a / D1b / D2 实施后须补齐 |

### P0/P1 风险（第二轮 correction）

| 风险 | 级别 | 触发停止条件 / 状态 |
|------|------|------------|
| 独立 archive sink 完全缺失 | **P0** | 不触发停止条件（PR-D 主任务；sink 选型待用户裁决） |
| M 类路径互斥机制具体载体缺失 | **P0** | **修正**：具体载体由用户裁决（A/B/C 三方案）——A 无 schema 改动但**非零代码 wiring**；B 须 production wiring；C 触发 §S6-10 停止条件 |
| restore-before-open 真实 PG 演练 | **P0** | R1-AC12 字面降级 + 生产门禁登记 |
| ledger snapshot 后 purge 残留 conversation | **P0** | fail-closed + 人工 reconcile |
| **runtime per-binding receipt 不可重算** | **P1（未决 / 停止条件）** | **必须先裁决 a / b / c 路径**——D2 runtime 路径不可启动；TD-106 P2-1 仍登记未关 |
| 四表无 `schema_version`/`digest`/`record_count` 列 | **P1** | 不触发（codec 层绑定） |
| 六元组跨表 join 恢复 | **P1** | 不触发（实现复杂度） |
| external per-ref receipt 缺 `adapter_receipt_evidence` 时无法重算 | **P1** | 不触发（恢复端必须检测并 fail closed） |
| conformance suite M 类写者枚举 + 裁定理由 | **P1** | 不触发（实施同步） |

---

## 15. 推荐：D1a / D1b / D2 三步拆分（第二轮 correction）

### 推荐：**拆 D1a / D1b / D2 三步走**

#### **D1a**（后续代码 PR — 删除前版"puredocs-only"表述）

**Scope**：
- Ledger snapshot codec + schema version + manifest digest + record_count（codec 层绑定，无 schema 改动）
- Deterministic bounded snapshot/segment exporter（**只读**，**不持久推进 watermark**、**不发布到 sink**、**不做 DB mutation**）
- Restore 端 decode/validate（manifest digest 校验 + schema version bump fail closed）
- **只读 identity reconstruction**（按 row identity + ledger snapshot join 重建六元组）
- real PG 验证：ledger round-trip + schema version mismatch fail closed
- **D1a 不得称 continuous archive / 不得称 replay executor / 不得做 DB mutation**

**理由**：D1a 不触及 §S6-10 停止条件（无新 schema/migration / 无 S5 状态机修改）；**D1a 是后续代码 PR**（新增 codec 模块 + 测试 + mutation kill 脚本）。

#### **D1b**（独立后续 PR，依赖 sink 选型裁决）

**Scope**：
- 独立 archive sink port 实现（依赖用户裁决：本地 minio / 外部 S3 / 文件系统）
- 原子发布（write-then-rename / segment+manifest atomic）
- 持久 cursor/watermark（per record kind + tenant，sink 端存储）
- Crash 安全（half-file detection + recovery）
- Retry 语义（指数退避 + sink 不可达 fail closed）
- Idempotency（同一 watermark 重导）
- 与 D1a codec 对接
- drill 降级声明（若本地 sink 与生产 sink 选型不一致）+ 生产门禁登记
- real PG 验证：连续导出 + archive round-trip + crash 安全

**理由**：D1b 须用户裁决 sink 选型（**生产 wiring 选型是 §S6-10 边界**）——D1a 可独立 PR 落地，D1b 在 sink 裁决后启动。

**D1a + D1b 合并评估**：
- ✅ **若 sink 选型明确**（本地 minio）+ D1a 与 D1b 评审面可控 ⇒ **可合并为单 PR D1**
- ❌ **若 sink 选型未定**（外部 S3 / 自建 object store）⇒ **必须分拆**

#### **D2**（独立后续 PR，须用户裁决互斥方案 + runtime proof 路径 + 不依赖 sink 选型）

**Scope**：
- M 类维护路径互斥机制（依赖 §6 三方案用户裁决——**A 方案推荐起步**）
- Restore replay executor（M 类路径 + 一次性维护事务 + 集合锁 + 与 retention/audit jobs 互斥）
- replay operation 六态路由（`running`/`blocked`/`scheduled`/`failed`/`completed`/`cancelled`）
- external/runtime 未 ACK 项独立 `blocked` + reconcile helper
- Restore-before-open 编排 + body/ref scan 集成
- `docs/02-delivery-plans/03-runbooks/restore-before-open.md`
- `S6I2_PENDING_WRITERS.restore_replay_executor` 转 `registered`
- conformance suite M 类写者枚举与裁定理由
- real PG 验证：六态路由 + 互斥 + body/ref scan + 服务开关编排

**D2 启动前置条件**（**全部必须先裁决**）：
1. **§6 M 类互斥方案**（A / B / C 任一）——A 推荐起步（零 schema 改动，但**非零代码 wiring**）
2. **§10 runtime per-binding proof 路径**（a / b / c 任一）——runtime per-binding receipt 不可重算是 D2 硬阻塞
3. **D1a codec 已就绪**（恢复端必须能 decode/validate）

**D2 在 runtime proof 裁决前**：
- ❌ **不得宣称完整覆盖 runtime completed verify-only 路径**
- ❌ **不得宣称覆盖 §S6-8.6「drill 降级声明」中的"重放机制经真实 PG 验证"完成**
- ❌ **不得将 runtime completed 状态加入 D2 mutation 判别载体**

### 推荐理由（fact-audit 第二轮 correction 依据）

- **CLI ≠ sink** 区分明确：producer 与 consumer 必须分别落地
- **runtime per-binding receipt 不可重算**是 D2 硬阻塞——TD-106 P2-1 仍登记未关
- **A 方案并非"零代码 wiring"**——两个 retention worker 启动路径 + replay 事务都须取锁；A 改动最小但非零
- **D1a 是后续代码 PR**——不是 puredocs-only；新增 codec 模块 + 测试 + mutation kill 脚本
- **拆分按 sink 分离 + 互斥决策 + runtime proof 裁决** ——前版 D1/D2 拆分已撤回

---

## 16. 本轮明确「零业务代码实现」

- ✅ **不实施**任何业务代码：ledger export executor / archive sink port / restore replay executor / restore-before-open runbook / D1b sink port 全部未创建
- ✅ **不修改**：Plan / 技术债总账 / work-log / Score Log / Metrics / migration 043 / schema / registry capability / 门禁脚本 / KNOWN_ISSUES / CI 配置 / F10/TD-105 已合并内容 / **TD-106 P2-1 runtime per-binding receipt 状态**
- ✅ **不实现 paused flag schema/migration**（具体载体由用户裁决——A/B/C 三方案均不通过本 PR 启动）
- ✅ **不启动**：PR-E / C1 / S5 production wiring / capability flip / 六 erase 入口生产可达
- ✅ **不复制 / 恢复旧 `c07c031c` scaffold**
- ✅ **不创建 migration 044**
- ✅ **不正式选择 A / B / C 任一互斥方案**
- ✅ **不修改冻结 Plan**（§S6-4 锁序登记修订须用户授权）

---

## 17. 仍待用户裁决项

1. **Runtime per-binding proof 路径**（决定 D2 启动 + runtime completed 路径是否覆盖）：
   - a. 新增可持久化的 per-binding archive evidence（migration 044+）——触发 §S6-10 停止条件
   - b. 契约明确允许 aggregate verify-only——需修改 §S6-12.1 / §S6-13.2
   - c. runtime restore 路径零写 fail-closed + 人工 reconcile（保守实现）
   - **TD-106 P2-1 仍登记未关**——与本次选型绑定

2. **Sink 选型**（决定 D1b 启动）：
   - 本地 minio（仓库已有 `minio_endpoint` 配置）
   - 外部 S3 / GCS / 其他 object store
   - 文件系统（atomic rename）+ 加密 + retention policy 自建

3. **M 类互斥方案 A / B / C**（决定 D2 启动）：
   - A. PostgreSQL advisory maintenance lock（**非零代码 wiring**——两个 retention worker 每个事务取 shared lock；replay 取 exclusive；新锁须在 Run/Conversation/owner/collection 锁之前取得，使用同一稳定 namespace/scope；写作 S6-4 锁序登记修订）
   - B. 外部 deployment/maintenance coordinator（需 production wiring 基建）
   - C. 持久化 DB maintenance lease/flag（触发 §S6-10 停止条件）

4. **D1a + D1b 是否合并为单 PR D1**（依赖 sink 选型）：
   - 若本地 minio 选型 + D1b 评审面可控 ⇒ 合并
   - 否则保持分拆

5. **D1b / D2 启动顺序**：
   - D2 须在 runtime proof 路径（#1）+ 互斥方案（#3）用户裁决后启动
   - D1b 可与 D2 并行（sink port 与互斥机制独立），但 D1b 须在 sink 选型（#2）裁决后启动

---

## 17.5. 用户裁决记录（Phase 0 启动，D1a only）

| 议题 | 裁决 | 含义 |
|------|------|------|
| 1. Runtime per-binding proof 路径 | **c** | archived completed runtime 缺 per-binding proof 时返回具名 `RUNTIME_BINDING_EVIDENCE_UNPROVABLE`；**零 DB 写**、不修改 terminal operation、不伪造 blocked/acked、不写假 receipt；restore-before-open 保持关闭，转 runbook 人工处置；running/blocked + runtime 未 ACK 仍按冻结契约 `blocked` + reconcile |
| 2. D1b sink 选型 | **专用 MinIO archive bucket**（后续）| 不复用 `minio_bucket=metaedu-resources`；本轮**不实现 D1b** |
| 3. D2 维护互斥方案 | **A**（后续）| 全局 transaction-level advisory lock；retention/audit 每个事务取 `pg_advisory_xact_lock_shared`；replay 事务取 `pg_advisory_xact_lock`；新锁必须在 Run/Conversation/owner/collection 锁**之前**取得；同一稳定 namespace/scope；本轮**不实现 D2**、不修改冻结 Plan |
| 4. D1a / D1b / D2 阶段 | **独立 PR** | 各自独立 PR 阶段 |
| 5. 固定顺序 | **D1a → D1b → D2** | |

**Phase 1 启动 D1a only**——本轮实施 D1a（只读 codec + bounded snapshot/segment exporter + decode/validate + 只读 identity reconstruction），不实现 D1b / D2 / PR-E / C1 / S5 production wiring / capability flip。

## 17.6. D1b merged-boundary 收口标注（2026-08-28）

> 本节为 D1b 子阶段 merge 入 main 的事实收口。审计责任范围：D1b 实现本体（专用 MinIO ledger archive sink + 不可变 commit-graph 发布协议 + 两阶段 API 拆分 + per-kind generation sink 端语义）；不宣称 D2 / PR-D / PR-E / C1 / S5 wiring / capability flip / 六 erase 入口生产可达已交付。

**集成事实链**：

1. **PR #600 squash merge 入 main `01c84f7c`**（2026-08-28，mergeCommit.oid `01c84f7c44de693642ac71150f9bf377e8685539`，mergedAt `2026-08-28T10:15:08Z`，feature branch `feature/req041-047-r1-s6-i3-d-d1b-minio-archive` 已 `--delete-branch` 删除）
2. source head `467e8d24a74f0c68ef2325340f7f86e2cca4397c` + FINAL_IMPL_HEAD `061f4a66` + 评分 commit `1293ea5194ccef9086188acf5677c51a4bf1d932`（首次 #600 Original 94 行落入 Score Log）+ correction commit `467e8d24`（同 #600 Original 行 in-place 修订事实更正：`#598 mergeCommit 8a836733` → `#598 FINAL_IMPL_HEAD 8a836733，squash mergeCommit 5868831e`；D1b 实现本体已明确为本 PR 完成评审；普通新 commit + push，**非** amend / 非 rebase / 非 force-push）
3. 评审对象 main@`5e1d4dff`..`061f4a66` 净 diff 7 文件 3088+/5-：codec + tests + 真实 MinIO opt-in + mutation script + 1 production config `minio_ledger_archive_bucket` + 2 governance（current-work + td-032）+ Score Log 1 行
4. main 累积 diff（5e1d4dff..01c84f7c = 8 文件 3089+/5-）含 D1b 实现 + 测试 + 真实 MinIO acceptance + mutation + 唯一 #600 评分行

**契约事实校核（contract-to-code）**：

- **专用 MinIO archive bucket**（用户裁决 2）= `metaedu-ledger-archive` ≠ `minio_bucket=metaedu-resources`；`app/config.py:30` 新增 `minio_ledger_archive_bucket: str = "metaedu-ledger-archive"` 但**当前实现无任何 production caller**——settings 注册但 scheduler / producer / cursor / continuous capture 全部未启动
- **不可变 commit-graph 协议**：segment key = sha256(segment_bytes)，commit marker key = `{generation:020d}-{export_id}.json`，segment PUT 先于 marker PUT（marker 出现 = 提交成功），per-tenant single publisher（V1）并发 fork fail-closed
- **D1a bytes → archive → D1a decoder round-trip**：phase-1 事务内 D1a export 后立即 D1a decoder 二次校验；phase-2 publish 后 GET-back digest verify；D1a round-trip 真实 MinIO 测试首轮发现并修复两处真 bug（`stable_identity` 必须 == `f"{kind}:{fields.id}"` 共享 UUID 变量绑定 + `table_identity` 必须 == 真实 DB 表名 `agent_conversation_purges` / `agent_conversation_purge_owners` 非字面 `purge_operation` / `purge_checkpoint` + `fields` 集合必须 ⊆ kind 闭集不允许 `created_at` 之类未授权字段）
- **idempotent retry**：marker 字节确定性由 segment_sha256 / export_id / generation / parent_export_id / per-kind 共同保证，**不依赖**任何 wall-clock 字段
- **三 P1 修复闭环**（用户裁决 1+2+3）：
  - **A-1 语义伪造**：`CommitMarker.published_at_unix` 字段删除 + `build_commit_marker` 无 `now_unix` 参数 + `to_canonical_dict` 不输出 wall-clock 字段
  - **B-1 事务持网络 I/O**：拆两阶段 API（`export_ledger_segment_for_archive(session, *, tenant_id)` L804-856 接收 session 强制 RR+RO 事务内 D1a export + decode 双校验零 sink I/O；`publish_ledger_segment(*, sink, tenant_id, segment_bytes, manifest, parent_export_id=None, sleeper=None)` L859-1011 不接收 AsyncSession 严格 sink I/O 零 DB I/O；`archive_ledger_segment` 删除 caller 显式编排；mask-style sink 写入集合断言 `_publish_two_phase` helper L436-479）
  - **C-1 零真实 MinIO 验收**：新增 `tests/composition/test_s6i3_d_ledger_archive_real_minio.py` opt-in `@pytest.mark.external_network` 模块已执行 6/6 PASS
- **A-5 per-kind generation 修订**：写入当前 commit marker 的实际 publication generation（=顶层 `CommitMarker.generation`），sink 端语义（**非** DB source cursor）；同 marker 内 per-kind 共享顶层值；marker 间单调推进；新增 `test_d1b_per_kind_generation_advances_with_marker_generation` 真实 PG 双代验证 first gen=1 / second gen=2

**验证事实**：

- **47/47 D1b composition**（31 纯内存 in-memory + 12 真实 PG via `snapshot_factory` fixture 连接 `metaedu_test` + 4 transient retry + per-kind generation 双代 `test_d1b_per_kind_generation_advances_with_marker_generation` L514-558 真实 PG 验证 first gen=1 / second gen=2 + per-kind 与顶层 generation 一致）
- **6/6 opt-in real MinIO acceptance**（per-run UUID bucket `metaedu-d1b-acceptance-{uuid4.hex[:12]}-{pid}-{ts_ms_low16}` + try/finally cleanup + 三层防御 `bucket != "metaedu-resources"` / `bucket != settings.minio_bucket` / `bucket not in FORBIDDEN_BUCKETS`；测试后 dev MinIO `total buckets: 0`，metaedu-resources 未被创建/触碰；`@pytest.mark.external_network` opt-in `RUN_REAL_MINIO_TESTS=1`）
- **11/11 behavioral mutation KILLED**（M1-M11 全部 subprocess pytest 真实 red→green 驱动；byte backup + try/finally + SHA-256 byte-identical `1d1e3bfd5509f0e3bc26139232d083bb1de701b792e40ce21acaef4e8860f3ab` 一致；M2/M4/M10 重定义为独立故障：M2 = segment 不存在时仍 PUT marker / M4 = 吞 segment PUT 异常 + 继续 marker PUT / M10 = 跳过 phase-1 decode；新增 3 项 invariant test `test_d1b_m2_segment_required_for_marker` / `test_d1b_m4_segment_failure_does_not_commit_marker` / `test_d1b_m10_phase1_calls_decode_validator`）
- **三套独立验证口径禁止合并**：opt-in MinIO 6 + 常规 47 + mutation 11 各自独立，**不得**合并相加或混入常规 CI 报告
- ruff clean + 官方 mypy baseline gate `cd packages/server-python && uv run --frozen --extra dev python scripts/check_mypy_baseline.py` → `passed: 243 historical errors across 76 keys; 0 regressions`（D1b 文件在 main 上 → baseline 覆盖）+ git diff --check clean + engineering-docs `--full` 全绿（31 known issues allowlisted；本 PR `engineer docs checks passed (31 known issue(s) allowlisted)` 落地门禁）
- PR #600 Ready 三路 required checks 全 SUCCESS（run `33160395058` Backend 19m53s SUCCESS + Frontend 2m17s SUCCESS + Engineering docs 19s SUCCESS）

**三面复审 + 评分事实**：

- 独立三面复审 P0=0/P1=0/P2=5/P3=6：面 A 契约/scope/facts 2+3 + 面 B 事务/并发/原子发布/数据完整性 3+1 + 面 C 测试/mutation/真实 MinIO/运维 0+2
- 维度评分（15/17/19/15/15/9/4 = 94/100）：范围与需求匹配 15 + 实现质量 17 + 测试与验证证据 19 + 事实源与流程遵守 15 + 风险与行为变化控制 15 + 可评审性与交接质量 9 + 持续改进信号 4
- 保留 5 P2：同步 MinIO SDK `put_object` / `get_object` / `list_objects` 在 asyncio 事件循环中阻塞未通过 `asyncio.to_thread` 移交未做性能硬化 / V1 single publisher 非 linearizable / `response.close()` + `response.release_conn()` 无 spy / 真实 MinIO 未覆盖 transient/collision/concurrent fork / D1a double-decode 性能
- 保留 6 P3：A-P3-1 `test_d1b_marker_contains_per_kind_counts_and_digests` 残留旧 assertion / A-P3-2 真实 MinIO 两阶段 API 测试 table_identity 字面量 `purge_operation` / `purge_checkpoint` 不一致 / A-P3-3 TD-032 split 待办 / B-P3-1 Protocol 命名混淆 / C-P3-1 真实 MinIO 非 CI 默认 opt-in / C-P3-2 M10 spy 仅次数未断言参数
- **正式评分门禁真实 PASS** `scripts/check-review-score-submit --base 061f4a66 --pr 600` → `review-score-submit: passed (base 061f4a66, PR #600, one Original row, Metrics unchanged)`（PR #555 / commit `2b801a60` 落地门禁脚本 `scripts/check-review-score-submit` + `scripts/engineering/review_score_submit.py` + `tests/engineering/test_review_score_submit.py`）
- 历史 finding 永久保留：TD-032（D1b `s6i3_d_ledger_archive_sink.py` 1052 行 + `test_s6i3_d_ledger_archive_sink.py` 1117 行 双超 1000 行硬限制已登记 🟢 待拆分）+ REQ-047（R1-S6 implementation conformance：B/C/D 联合启用门禁 — D1b/D2 合并后由 conformance 验收；D1b 评审完成 + 三 P1 修复闭环 + 47/6/11 测试与 mutation = D1b 实施合规事实）+ A-2 13 命名 `LedgerArchiveError` 子类精确目录（用户裁决）+ 5 P2 + 6 P3

**D1b 完成不等于以下后续事项已完成（merged-boundary 不变式）**：

- ❌ **D1b production wiring 未启动**（scheduler 接入 / capability flip / 六 erase 入口生产可达）——`minio_ledger_archive_bucket` settings 注册但无 production caller
- ❌ **D2 未启动**（replay executor + M 类互斥 A advisory lock + restore-before-open 编排 + restore 端 DB mutation）——须先解决：(1) Runtime per-binding proof 路径用户裁决 a/b/c（D2 硬阻塞）+ (2) M 类互斥 A 方案接法（须写作 S6-4 锁序登记修订）+ (3) D1a codec 已被 D2 消费
- ❌ **PR-D 未启动**（ledger export additional safety drills）
- ❌ **PR-E 未启动**（release drill 五阶段 canary）
- ❌ **C1 未启动**（Durable Core 总验收）
- ❌ **S5 production wiring 未启动**
- ❌ **registry capability flip 未启动**（external/runtime 仍 `erase_available=False`）
- ❌ **六 erase 入口生产可达 未启动**
- ❌ **F-matrix 7/12 NOT-RED mutation 增强 PR 未启动**（保持原编号与状态）
- ❌ **M-F3/F5/F8 mutation 停止条件登记保持**
- ❌ **TD-104 未启动**（PR-A schema/test alignment 残项）

**用户裁决 5 项冻结（merged-boundary 不变式）**：

1. Runtime per-binding proof = c（archived completed runtime 缺 per-binding proof 时返回具名 `RUNTIME_BINDING_EVIDENCE_UNPROVABLE`；零 DB 写、不修改 terminal operation、不伪造 blocked/acked、不写假 receipt；restore-before-open 保持关闭，转 runbook 人工处置）
2. D1b = 专用 MinIO archive bucket（`metaedu-ledger-archive` ≠ `metaedu-resources`）—— 已落地
3. D2 = A advisory lock（全局 transaction-level advisory lock；retention/audit 取 `pg_advisory_xact_lock_shared`，replay 取 `pg_advisory_xact_lock`；新锁必须在 Run/Conversation/owner/collection 锁之前取得；同一稳定 namespace/scope）—— 未启动
4. D1a / D1b / D2 阶段 = 各自独立 PR —— 已遵守（D1a → D1b 顺序）
5. 固定顺序 D1a → D1b → D2 —— 已遵守（D1a 已合 main，D1b 已合 main，D2 待启动）

**未覆盖边界的真实性声明**：

- 真实 MinIO acceptance **仅覆盖主路径**（PUT/GET / marker / find_committed_tip / bucket 构造器拒绝 / 两阶段 API publish / D1a round-trip），**未覆盖** transient/collision/concurrent fork 三类错误路径（属 P2 follow-up）
- 真实 MinIO 测试结束后 dev MinIO `total buckets: 0`，per-run bucket 全部清理；metaedu-resources 未被创建/触碰
- D1b 三套验证口径禁止合并：opt-in MinIO 6 + 常规 47 + mutation 11 各自独立
- 任何后续声称 D1b 完成的工作，必须同时满足：(1) 评分 94 Original 已登记 (2) 三 P1 修复闭环 (3) 47/6/11 验证基线 (4) merged-boundary 不冒充 D2/PR-D/PR-E/C1/S5 wiring/capability flip/六 erase

## 17.7. D2 merged-boundary 收口标注（2026-09-01）

> 本节为 D2 子阶段 merge 入 main 的事实收口。审计责任范围：D2 实现本体（bounded read-only restore replay executor + M 类互斥 A 方案 advisory lock + restore-before-open gate）；不宣称 D2 production wiring / PR-D / PR-E / C1 / S5 wiring / capability flip / 六 erase 入口生产可达已交付。**§17.6 中「D2 未启动」是 D1b closeout 时点（2026-08-28）的历史事实，已由本次 D2 merged-boundary supersede。**

**集成事实链**：

1. **PR #602 squash merge 入 main `ae7f3c98`**（2026-09-01，mergeCommit.oid `ae7f3c9814d7258dab288aceaeb2ff1bd00d77ee`，mergedAt `2026-09-01T12:29:10Z`，feature branch `feature/req041-047-r1-s6-i3-d-d2-restore-replay` 已 `--delete-branch` 删除）
2. source head = score commit `177a226a03be6181df1970be1e36216f4777d4a3`（FINAL_IMPL_HEAD `4bc22328` = Round-8.1 纯文档 docs commit 之后追加 #602 Original 评分行的最终 source head；implementation baseline main `b88704a7`；评分 92 Original 落入 Score Log）
3. 评审对象 main@`b88704a7`..`4bc22328` 净 diff 14 文件 6814+/48-：2 plan 文档 + `restore_replay.py` 1876 行 + `test_s6i3_d_restore_replay.py` 2559 行 + `test_s6i3_d_mutation_classifier.py` 253 行 + `test_s6i3_d_restore_replay_locks.py` 230 行 + `s6i3_d_restore_replay_mutation_kill.py` 671 行 + 3 既有 production/test M（`agent_erasure_locks.py` / `retention_workers.py` / `s6i2_orphan_inspection.py` M 类 writer 注册 FENCE_M）+ `test_s5i2_production_wiring_boundary.py` / `test_s6i2_orphan_inspection.py` + 2 governance（current-work + td-032）+ Score Log 1 行
4. main 累积含 D2 实现 + 测试 + mutation script + 唯一 #602 评分行

**实现事实（contract-to-code）**：

- **两阶段 replay**：phase 1 从 D1b committed graph 取输入（`asyncio.to_thread(find_committed_tip)` + `CommitMarker.from_bytes` + `fetch_segment_bytes`）；pass A 零写六元组 + operation fence 全字段对账（archive facts 严格来源 `_require_field`/`_require_strict_int`/`_require_str`/`_require_canonical_uuid`/`_require_64hex_lower` helper 族，禁止 LIVE 值回填）；pass B 单一 exclusive maintenance tx 调 4 owner participant 公共入口（Conversation→owner→fence→aggregate 全锁序 + ACK）
- **M-class advisory lock**（用户裁决 3 = A 方案）：frozen prefix `metaedu.agent.maintenance.v1\x00`；retention/audit 每事务取 `pg_advisory_xact_lock_shared`，replay 事务取 `pg_advisory_xact_lock` exclusive；新锁在 Run/Conversation/owner/collection 锁之前取得
- **restore-before-open gate**：强制消费 `RestoreReplayReport`（error / pass_a_drift / toctou_drift / participant_failures / runtime_proof_c_present / external_verification_failed 全部自动阻断）
- **pass B 报告提交边界**（Round-8）：事务内 verdict 仅 provisional，仅 `async with session.begin()` 成功退出后发布 committed verdict；rollback 时 6 个 pass-B except handler 一律 `_rolled_back_evidence` 改标 `ACTION_ROLLED_BACK`，不保留已回滚 success verdict
- **participant outcome 结构化分类**（Round-7）：blocked → BLOCKED_KEPT + gate 消费保持关闭；非 blocked 必须 erased+64-hex ack → LOCAL_CLEARED；非法 shape → PARTICIPANT_OUTCOME_INVALID fail closed
- **writer `restore_replay_executor` 保持 registered=FENCE_M**（`app.composition.restore_replay.replay_archive_segment_for_tenant`，登记于 `s6i2_orphan_inspection.py`）

**验证事实**：

- **90 restore_replay 专项 + 18 classifier 自测 = 108 D2 专项全 pass**
- **composition 全量 992 passed / 6 skipped**
- **mutation 21/21 用修正后分类器重跑 KILLED**（byte-identical restore，不沿用旧数字；Round-8 修正 crash/setup 优先于 killed）
- ruff clean + 官方 mypy baseline `passed: 243 historical errors / 76 keys / 0 regressions` + `restore_replay.py` targeted mypy no issues + git diff --check clean + engineering-docs `--full` 全绿
- **CI 如实登记（不掩饰为首次成功）**：Draft 首轮 Backend iteration run `33462867892` hermetic runner ~33min 无 pytest 输出后超时 CANCELLED（job conclusion=cancelled 非 failure）→ 同 HEAD `gh run rerun --failed` 14m38s PASS；Round-8.1 run `33469001980` 三路全 SUCCESS；Ready run `33474589073`（Backend 14m4s / Eng docs 9s / Frontend 4s）+ post-score run `33476012685`（Backend 15m1s / Eng docs 8s / Frontend 5s）全 SUCCESS

**三面复审 + 评分事实**：

- Round-8/8.1 三面复审 P0=0/P1=0/P2=0/P3=0
- 维度评分（15/17/19/14/15/8/4 = 92/100）：范围与需求匹配 15 + 实现质量 17 + 测试与验证证据 19 + 事实源与流程遵守 14 + 风险与行为变化控制 15 + 可评审性与交接质量 8 + 持续改进信号 4
- 扣分如实登记：TD-032（`restore_replay.py` 1876 + test 2559 双超 1000 硬限制，实现质量 -2 + 可评审性 -1）；单模块聚合 + 6814+/48- 长链降可评审性（可评审性 -1）；mutation classifier 自身缺陷到 Round-8 才被发现（测试 -1 + 持续改进 -1）；current-work 事实漂移经 Round-8.1 才修正（事实源 -1）；Draft 首次 Backend iteration 超时 CANCELLED 后同 HEAD rerun 成功（如实登记非首次成功）
- **正式评分门禁真实 PASS** `scripts/check-review-score-submit --base 4bc22328 --pr 602` → `review-score-submit: passed (base 4bc22328, PR #602, one Original row, Metrics unchanged)`

**D2 完成不等于以下后续事项已完成（merged-boundary 不变式）**：

- ❌ **D2 production wiring 未启动**（scheduler 接入 / capability flip / 六 erase 入口生产可达）
- ❌ **PR-D 剩余 operational closeout 未启动**（production-neutral continuous ledger export/archive orchestration entry + restore-before-open runbook + D1a→D1b→D2→gate cross-layer safety drill/contract verification + crash/retry/post-snapshot purge/manual reconcile ops 步骤；详见 plan §S6-14 post-D2 rebaseline 注解；**禁止** scheduler production caller / S5/D1b/D2 production wiring / capability flip / 六 erase 入口生产可达；旧 `c07c031c` scaffold 已随 #586 scope 收敛撤回，禁止 cherry-pick）
- ❌ **PR-E 未启动**（release drill 五阶段 canary；前置依赖 = PR-D 剩余 operational closeout，禁止 PR-D 未落地先启动 PR-E）
- ❌ **C1 未启动**（Durable Core 总验收）
- ❌ **S5 production wiring 未启动**
- ❌ **registry capability flip 未启动**（external/runtime 仍 `erase_available=False`）
- ❌ **六 erase 入口生产可达 未启动**
- ❌ **TD-032 保持待拆分不关闭**（`restore_replay.py` 1876 行 + `test_s6i3_d_restore_replay.py` 2559 行 双超 1000 行硬限制已登记 🟢 待拆分）
- ❌ **TD-104 未启动**（PR-A schema/test alignment 残项）；**待重新审计**是否已被 #586 scope 收敛撤回的 scaffold / D1a `#598` / D2 `#602` 三个 merged-boundary 落 main supersede（**仅注册审计需要**，本 PR 不修改 `technical-debt.md`，不单方面关闭 TD-104）
- **REQ-047 保持后续联合验收归属**（R1-S6 implementation conformance：B/C/D 联合启用门禁 — D2 合并后由 conformance 验收）

**用户裁决 5 项冻结（merged-boundary 不变式）**：runtime per-binding proof = c / D1b = 专用 MinIO archive bucket（已落地）/ D2 = A advisory lock（已落地）/ D1a / D1b / D2 = 三独立 PR（已遵守）/ 固定顺序 D1a → D1b → D2（已遵守，三者均合 main）

## 17.8. GOV closeout merged-boundary 收口标注（2026-09-02）

> 本节为 R1-S6-I3-D 工作台精简 + PR-D 剩余边界重定基 GOV 子卡 merge 入 main 的事实收口。审计责任范围：**纯文档 3 文件治理归位**——`current-work.md` slim + plan §S6-14 post-D2 rebaseline 注解 + 本文档 §17.7 4 处过期修复。**§17.7 中「TD-104 未启动...待重新审计是否已被 #586 scope 收敛撤回的 scaffold / D1a `#598` / D2 `#602` 三个 merged-boundary 落 main supersede」属 D2 closeout 时点（2026-09-01）的历史事实，已由本次 GOV closeout 审计 supersede：#586 / #598 / #602 三个 merged-boundary 均已 supersede 该 scaffold；TD-104 仍 ⚫ 待办保持不关闭。**本节不宣称 PR-D / PR-E / F-matrix 7/12 + F10 M6 / C1 / S5 production wiring / capability flip / 六 erase 入口生产可达已交付。

**集成事实链**：

1. **PR #604 squash merge 入 main `e37561fe`**（2026-09-02，mergeCommit.oid `e37561fea2cc9859651fb462ee71472d581b9224`，mergedAt `2026-09-02T01:34:20Z`，feature branch `docs/req041-047-r1-s6-i3-d-gov` 已 `--delete-branch` 删除）
2. source head = score commit（single squash commit mergeCommit = source head = FINAL_IMPL_HEAD `e37561fe`；implementation baseline main `68fafd81` = PR #586 root squash mergeCommit 入 main）
3. 评审对象 main@`68fafd81`..`e37561fe` 净 diff 3 文件 8+/127-：仅 `current-work.md` slim + `2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md` §S6-14 APPEND + `r1-s6-i3-d-fact-audit.md`（本文件）§17.7 4 处过期修复
4. main 累积含 D1a（#598）+ D1b（#600）+ D2（#602）+ F10 真实 PG（#596）+ R1-S6-I3 root（#586）+ GOV closeout（#604）+ GOV sub-TASK closeout 独立 PR 6 个 merged-boundary + 各自评分行
5. **GOV 子卡 = pure-docs 治理归位，不引入任何业务代码 / 测试 / 评审 Score Log Metrics 字段 / technical-debt / plan 既有 rebaseline 内容修改**

**GOV 完成内容（pure-docs 3 文件）**：

- **`current-work.md` slim**：
  - 从「当前进行中」移除 TASK-R1-S6-I3-D-GOV 子卡，回归 `当前无活跃任务。` 硬门禁（`current-work-in-progress-pollution` gate 触发）
  - 候选表保留 3 行（PR-D → F-matrix → PR-E），顺序严格 PR-E depends on PR-D
  - 「最近完成」表追加 #604 行（首位），摘要 213 字符（< 220 字符硬限制）
  - 总行数裁剪至 12 行（移除 5 行最旧：R1-S5 SCH-D / SCH-C / SCH-A / D-A / D）
- **plan §S6-14 post-D2 rebaseline 注解 APPEND 块**（不改写既有 rebaseline 内容）：
  - PR-D 剩余交付边界精确冻结：(1) production-neutral continuous ledger export/archive orchestration entry；(2) restore-before-open runbook；(3) D1a→D1b→D2→gate cross-layer safety drill/contract verification；(4) crash/retry、post-snapshot purge、manual reconcile ops 步骤
  - 明确禁止：scheduler production caller、S5/D1b/D2 production wiring、capability flip、六 erase 入口生产可达
  - PR-D 与 F-matrix 7/12 / F10 M6 / PR-E 三者依赖关系在 §S6-14 段落统一冻结
- **本文档 §17.7 4 处过期修复**（不改写历史事实段，仅删过期措辞）：
  - 移除 3 处过期 main mergeCommit 引用（如 `#586 mergeCommit 68fafd81` 早已固定，删去"待合并"措辞）
  - 修 1 处 TASK-R1-S6-I3 状态措辞（从 🟢 → 🟡；GOV 子卡完成 ≠ TASK 整体完成）

**严格禁止面零触碰**（merged-boundary 不变式，已核对）：

- ❌ **Score Log Metrics 字段未触动**（仅新增 #604 Original 单行，Metrics byte-identical，`git diff 68fafd81..e37561fe -- docs/03-engineering-governance/04-retrospectives/review-score-log.md` 仅 +1 行）
- ❌ **`technical-debt.md` 未修改**——TD-104 保持 ⚫ 待办不关闭（PR-A schema/test alignment 残项：三个 merged-boundary supersede scaffold 后**仍保持 ⚫ 待办**属历史事实，本 PR 不单方面关闭）；TD-032 保持 🟢 待拆分不关闭
- ❌ **plan 既有 §S6-14 rebaseline 内容未改写**（仅 APPEND 块）
- ❌ **业务代码 / 测试 / migration 043 / schema / enum / CHECK / registry / 门禁脚本 / KNOWN_ISSUES 未触碰**

**GOV closeout merged-boundary 不变式（与 §17.6 / §17.7 一致口径）**：

- ✅ GOV closeout = pure-docs 治理归位（current-work slim + plan §S6-14 APPEND + fact-audit §17.7 4 处过期修复）= TASK-R1-S6-I3-D-GOV 子卡完成
- ❌ GOV closeout ≠ TASK-R1-S6-I3-D TASK 整体完成（任务卡整体仍 🟡 进行中）
- ❌ GOV closeout ≠ PR-D / PR-E / F-matrix 7/12 + F10 M6 / C1 / S5 production wiring / capability flip / 六 erase 入口生产可达任何一项已交付
- ❌ GOV closeout ≠ TD-104 / TD-032 任何一项已关闭
- ❌ GOV closeout ≠ runtime per-binding proof 路径任何决策已落地（用户裁决 5 项冻结仅重申既有，未做新决策）

**三面复审 + 评分事实**：

- 三面独立复审 P0=0/P1=0/P2=0/P3=5（non-blocking）
- 维度评分（15/17/14/15/14/10/6 = 91/100）：范围与需求匹配 15 + 实现质量 17 + 测试与验证证据 14 + 事实源与流程遵守 15 + 风险与行为变化控制 14 + 可评审性与交接质量 10 + 持续改进信号 6
- 扣分如实登记：5 P3 non-blocking（A-P3-1 评估 PD-7 实质等同 contract-first / B-P3-1 Ready `gh pr ready` 跨 PR 时机 / B-P3-2 评分双 metric（fact-audit 缺独立 metric）/ C-P3-1 plan §S6-14 旧 PR-D 块追加「post-D2 改 supersede 关系」 / C-P3-2 Score Log `#604` row 加事实源列字段说明）；5 P3 全部登记不冒充收口
- **正式评分门禁真实 PASS** `scripts/check-review-score-submit --base e37561fe --pr 604` → `review-score-submit: passed (base e37561fe, PR #604, one Original row, Metrics unchanged)`

**GOV closeout 验证事实**：

- pure-docs `git diff --check` clean + `scripts/check-engineering-docs --full` 全绿
- Ready 三路 required checks 全 SUCCESS（合并前最后一次推送）
- 评分提交后重跑三路全 SUCCESS
- 零业务代码 / 测试 / migration / schema / enum / CHECK / registry / Score Log Metrics / 门禁脚本 / KNOWN_ISSUES 改动
- **本地验证**：local main `e37561fe` == origin/main `e37561fe` == closeout mergeCommit `e37561fe` ✓

**GOV 完成边界（精确登记，不越界）**：

- **已完成**：工作台 slim（TASK-R1-S6-I3-D-GOV 子卡移除 + 候选表 3 行 + 最近完成 12 行）+ PR-D 剩余边界重定基冻结（plan §S6-14 APPEND 块）+ 评审流程合规（5 P3 non-blocking）+ 评分 91 Original + main closeout
- **未启动**：PR-D / F-matrix 7/12 + F10 M6 / PR-E / C1 / S5 production wiring / capability flip / 六 erase 入口生产可达
- **未关闭**：TD-104（PR-A schema/test alignment 残项保持 ⚫ 待办）+ TD-032（D1a/D1b/D2 三对超 1000 行硬限制保持 🟢 待拆分）+ REQ-047（R1-S6 implementation conformance 联合闭环）
- **5 P3 follow-up non-blocking**：A-P3-1 / B-P3-1 / B-P3-2 / C-P3-1 / C-P3-2（详见三面复审事实段）

**§17.6 / §17.7 / §17.8 关系关系**：

- §17.6（D1b closeout 标注，2026-08-28）：D1b merged-boundary 收口 + D2 未启动的历史事实
- §17.7（D2 closeout 标注，2026-09-01）：D2 merged-boundary 收口 + supersede §17.6「D2 未启动」+ PR-D 未启动历史事实
- §17.8（本节，GOV closeout 标注，2026-09-02）：GOV 子卡 merged-boundary 收口 + supersede §17.7「TD-104 未启动...待重新审计」+ 任务卡整体仍 🟡 进行中 + PR-D / PR-E / F-matrix / C1 / S5 wiring / capability flip / 六 erase 全部未启动
- **三节关系 = 累积 supersede 关系**（每节都 supersede 前一节中"待启动"或"待重新审计"措辞为 merged-boundary 事实，但**不** supersede 前一节"未启动"清单（PR-D/PR-E/C1/S5 wiring/capability flip/六 erase 仍全部未启动）

**用户裁决 5 项冻结（merged-boundary 不变式，与 §17.7 一致）**：runtime per-binding proof = c / D1b = 专用 MinIO archive bucket（已落地）/ D2 = A advisory lock（已落地）/ D1a / D1b / D2 = 三独立 PR（已遵守）/ 固定顺序 D1a → D1b → D2（已遵守）

## 17.9. PR-D merged-boundary 收口标注（2026-09-03）

> 本节为 R1-S6-I3-D PR-D 剩余 operational closeout（PR #606）merge 入 main 的事实收口。审计责任范围：PR-D 实现本体（production-neutral continuous ledger export / archive orchestration entry + restore-before-open runbook + D1a→D1b→D2→gate cross-layer safety drill / contract verification + crash/retry / post-snapshot purge / M-class 并发窗口 / blocked + manual reconcile ops 步骤）。**§17.8 中「PR-D / PR-E / F-matrix / C1 / S5 wiring / capability flip / 六 erase 全部未启动」属 GOV closeout 时点（2026-09-02）的历史事实，已由本次 PR-D merged-boundary supersede PR-D 自身（PR #606 / mergeCommit `d196d7f0` / source head `ad9a8fd2` + FINAL_IMPL_HEAD `69803364` 已并入 main）；其他历史事实（PR-E / F-matrix / C1 / S5 wiring / capability flip / 六 erase 入口生产可达 / REQ-047 conformance）仍保持未启动。**本节不宣称 PR-E / F-matrix 7/12 + F10 M6 / C1 / S5 production wiring / capability flip / 六 erase 入口生产可达 / REQ-047 conformance 已交付。

**集成事实链**：

1. **PR #606 squash merge 入 main `d196d7f0a829d3bc45653d5bca3d08bf663b3346`**（2026-09-03T07:35:58Z，source head `ad9a8fd20ff0e39c49088caa7dcebb9f85f723ff` = `69803364` + 评分 row commit `ad9a8fd2`）
2. implementation baseline main `840bcaf22267a9f8bdb769d21db99c3c6de7da11` + FINAL_IMPL_HEAD `69803364a1df1d6e1e840a7c80875dfefd9751f4` 双记
3. 评审对象 main@`840bcaf2`..`69803364`，净 diff 4 文件 851 insertions(+)/1(-)：`packages/server-python/app/composition/s6i3_d_ledger_orchestration.py` 107 行 + `packages/server-python/tests/composition/test_s6i3_d_cross_layer_drill.py` 361 行 + `docs/02-delivery-plans/03-runbooks/2026-09-03-r1-s6-i3-d-restore-before-open.md` 344 行 + `docs/03-engineering-governance/current-work.md` +38/-1（活跃卡）
4. main 累积 diff（`840bcaf2`..`d196d7f0` = 5 文件 852 insertions(+)/1(-)：)）含 PR-D 实现 + 测试 + runbook + 活跃卡 + 评分 row 提交
5. **PR-D closeout = 4 文件治理归位 + 1 行评分（pure-docs 收口），不引入任何业务代码 / 测试 / 评审 Score Log Metrics 字段 / technical-debt / plan 既有 rebaseline 内容修改**

**PR-D 完成内容（4 文件 production-neutral 边界）**：

1. **`app/composition/s6i3_d_ledger_orchestration.py`** 新增（107 行）：`export_and_archive_ledger_segment(session_factory, *, sink, tenant_id) -> PublishOutcome` thin composition —— caller-managed RR+RO tx 入口 `SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY` + D1b phase-1（`export_ledger_segment_for_archive` D1a export + decode 双校验）+ D1b phase-2（`publish_ledger_segment` 纯 sink I/O 零 DB）；`async with (session_factory() as session, session.begin())` PEP 654 严格分立 tx / sink 边界；严格保持 D1a RR+RO phase-1 与 D1b sink-only phase-2 边界
2. **`tests/composition/test_s6i3_d_cross_layer_drill.py`** 新增（361 行）：5 项 acceptance / contract test（真实 PG + in-memory sink）—— `test_cross_layer_drill_full_path_open_allowed` 完整路径 happy / `test_cross_layer_drill_continuous_export_advances_generation` 同 export_id + generation 推进（验证 audit 4 fresh-snapshot series）/ `test_cross_layer_drill_gate_blocks_on_runtime_proof_c` gate fail-closed / `test_cross_layer_drill_cross_tenant_decoder_rejects` TENANT_BINDING_MISMATCH / `test_cross_layer_drill_asserts_metaedu_test` DB hard boundary；仅做 callable composition 不复制 D1a decoder 21 / D1b publish  / D2 6×5 路由矩阵 / D2 pass A / pass B 任一实现；不新增 mutation script
3. **`docs/02-delivery-plans/03-runbooks/2026-09-03-r1-s6-i3-d-restore-before-open.md`** 新增（344 行）：9 章 restore-before-open runbook —— 入口与参数 / 不变式 / caller 必接字段 / report 消费约定 / blocked_reasons 责任路径 / crash-retry 路径 / post-snapshot purge 处置 / M-class 并发窗口 / blocked + manual reconcile ops / 生产门禁登记；6 owner manual reconcile 路径明确 + 9 个稳定事实源链接
4. **`docs/03-engineering-governance/current-work.md`** 活跃卡（+38/-1）：TASK-R1-S6-I3-D-PR-D 10 模板字段齐全（state/branch/mode/工具/类型/需求/进展/下一步/验证/事实源）

**契约事实校核（contract-to-code）**：

- **production-neutral continuous ledger export / archive orchestration entry**：thin composition of D1b `export_ledger_segment_for_archive` + `publish_ledger_segment` 两阶段 API；不引入 schema / migration / cursor / watermark / 增量状态表；orchestration 入口**仅消费** D1b 公开 API（`__all__`），不重复 D1a / D1b 业务逻辑；caller 负责 cadence / 并发 fork 防护（V1 single-publisher fork fail-closed 由 caller 端串行化）
- **restore-before-open runbook**：9 章 + 9 个稳定事实源链接 + 6 owner manual reconcile 路径明确 + 生产门禁降级声明（plan §S6-8 item 6 + R1-AC12 字面）
- **D1a → D1b → D2 → restore-before-open gate 跨层 safety drill**：5 项 acceptance / contract test 真实 PG + in-memory sink 串联 D1a codec → D1b publish → fetch_segment_bytes → decode_ledger_segment → reconstruct_owner_facts → D2 replay_archive_segment_for_tenant → D2 evaluate_restore_before_open gate；不复制单层业务逻辑；不新增 mutation script
- **crash/retry / post-snapshot purge / M-class / blocked + manual reconcile ops**：runbook §4-7 完整覆盖；M-class advisory lock 协议（frozen prefix `metaedu.agent.maintenance.v1\x00`，retention/audit shared + replay exclusive）= D2 M-class advisory lock (PR #602 `ae7f3c98`) 支持；不新增任何新基础设施

**验证事实**：

- **5/5 drill test PASS**（metaedu_test，1.43s；命令 `pytest tests/composition/test_s6i3_d_cross_layer_drill.py -q`；结果 exit 0；Environment = `metaedu_test` 真实 PG via `snapshot_factory` fixture）：full_path_open_allowed / continuous_export_advances_generation / gate_blocks_on_runtime_proof_c / cross_tenant_decoder_rejects / asserts_metaedu_test
- **完整 backend composition 997 passed + 6 skipped**（命令 `pytest tests/composition -q --no-header`；结果 exit 0；Environment = `metaedu_test`；时长 227.13s 0:03:47；6 warnings pre-existing pytest warnings 与本 PR 无关）
- **ruff check**（命令 `ruff check app/composition/s6i3_d_ledger_orchestration.py tests/composition/test_s6i3_d_cross_layer_drill.py`；结果 exit 0 "All checks passed!"）—— orchestration 107 行 + drill test 361 行 5 fixable 全部修
- **mypy baseline**（命令 `python3 scripts/check_mypy_baseline.py`；结果 "passed: 243 historical errors across 76 keys; 0 regressions"）—— D1a / D1b / D2 + orchestration + drill 全部 0 regression
- **git diff --check**（命令 `git diff --check`；结果 exit 0；4 文件净 diff `840bcaf2..69803364` 无 whitespace 问题）
- **`scripts/check-engineering-docs --full`**（命令 `python3 scripts/check-engineering-docs --full`；结果 "engineering docs checks passed (32 known issue(s) allowlisted)"）
- **pre-commit hooks**（结果 All checks passed；ruff + eng-docs）
- **pre-push hooks**（结果 All checks passed）
- **Ready 三路 required checks 全 SUCCESS**（CI run `33720434968`；Backend full 15m5s + Engineering docs 9s + Frontend 5s）
- **post-score 三路 required checks 全 SUCCESS**（CI run `33722320505`；Backend + Engineering docs 7s + Frontend 5s）

**三面复审 + 评分事实**：

- 三面独立复审 P0=0/P1=0/P2=3/P3=4（保留全部不冒充收口）
- 维度评分（15/19/18/15/15/8/5 = 95/100）：范围与需求匹配 15 + 实现质量 19 + 测试与验证证据 18 + 事实源与流程遵守 15 + 风险与行为变化控制 15 + 可评审性与交接质量 8 + 持续改进信号 5
- 扣分如实登记：3 P2（B-1 orchestration DB boundary defense-in-depth / C-1 drill 缺 phase-1/2 crash + post-snapshot drift + M-class lock collision + blocked reconcile 通过 orchestration 串联实证 / C-2 runbook 缺对 D1b / D2 既有测试集交叉引用）+ 4 P3（P3-A docstring "idempotent_retry=True 当同 export_id 同 marker key 已存在（同一 DB state 重试）" 括号内例子误导 / P3-B drill 未使用 import `structlog` / P3-C drill 未使用常量 `_DIGEST_B` / P3-D drill 行内 import `CommitMarker` 应置于模块顶部）——全部登记不冒充收口
- **正式评分门禁真实 PASS** `scripts/check-review-score-submit --base 69803364 --pr 606` → `review-score-submit: passed (base 69803364, PR #606, one Original row, Metrics unchanged)`
- Score Log `Main` 行 `#606 Original | 95` 净增 1 行；Metrics Snapshot byte-identical；历史评分行未触动

**PR-D merged-boundary 不变式（与 §17.6 / §17.7 / §17.8 一致口径）**：

- ✅ PR-D closeout = 4 文件 production-neutral 边界（orchestration 107 + drill 361 + runbook 344 + current-work 活跃卡）+ 评分 95 Original + main closeout（squash mergeCommit `d196d7f0`） = TASK-R1-S6-I3-D PR-D 子阶段完成
- ❌ PR-D closeout ≠ TASK-R1-S6-I3-D TASK 整体完成（任务卡整体仍 🟡 进行中）
- ❌ PR-D closeout ≠ PR-E / F-matrix 7/12 + F10 M6 / C1 / S5 production wiring / capability flip / 六 erase 入口生产可达任何一项已交付
- ❌ PR-D closeout ≠ TD-104 / TD-032 / REQ-047 任何一项已关闭
- ❌ PR-D closeout ≠ runtime per-binding proof 路径任何决策已落地（用户裁决 5 项冻结仅重申既有，未做新决策）

**用户裁决 5 项冻结（merged-boundary 不变式，与 §17.6 / §17.7 / §17.8 一致）**：

1. Runtime per-binding proof = c（archived completed runtime 缺 per-binding proof 时返回具名 `RUNTIME_BINDING_EVIDENCE_UNPROVABLE`；零 DB 写、不修改 terminal operation、不伪造 blocked/acked、不写假 receipt；restore-before-open 保持关闭，转 runbook 人工处置）—— **未做新决策**
2. D1b = 专用 MinIO archive bucket（`metaedu-ledger-` ≠ `metaedu-resources`）—— **已落地**（PR #600 `01c84f7c`）
3. D2 = A advisory lock（全局 transaction-level advisory lock；retention/audit 取 `pg_advisory_xact_lock_shared`，replay 取 `pg_advisory_xact_lock` exclusive；新锁必须在 Run/Conversation/owner/collection 锁之前取得；同一稳定 namespace/scope）—— **已落地**（PR #602 `ae7f3c98`）
4. D1a / D1b / D2 = 三独立 PR —— **已遵守**（PR #598 / #600 / #602 + closeout PR #603）
5. 固定顺序 D1a → D1b → D2 —— **已遵守**（三者均合 main）

**未覆盖边界的真实性声明**：

- orchestration 不接 scheduler caller（V1 single-publisher fork fail-closed 由 caller 端串行化）
- 真实 pg_dump / restore / 流量开关演练无法本地执行（无生产基础设施）—— 生产门禁由生产基础设施负责人承接（runbook §8）
- 真实 MinIO acceptance **仅覆盖主路径**（PUT/GET / marker / find_committed_tip / bucket 构造器拒绝 / 两阶段 API publish / D1a round-trip）；**未覆盖** transient/collision / concurrent fork（属 D1b P2 follow-up 保持登记）
- D1a / D1b / D2 mutation 全部独立覆盖（11/11 + 21/21）；drill 仅为 acceptance / contract 验证层，**不重复**单层 mutation
- 任何后续声称 PR-D 完成的工作，必须同时满足：(1) 评分 95 Original 已登记 (2) 5/5 drill test PASS (3) 完整 backend composition 997 passed (4) merged-boundary 不冒充 PR-E / F-matrix / C1 / S5 wiring / capability flip / 六 erase

**§17.6 / §17.7 / §17.8 / §17.9 关系（累积 supersede）**：

- §17.6（D1b closeout 标注，2026-08-28）：D1b merged-boundary 收口 + D2 未启动的历史事实
- §17.7（D2 closeout 标注，2026-09-01）：D2 merged-boundary 收口 + supersede §17.6「D2 未启动」+ PR-D 未启动历史事实
- §17.8（GOV closeout 标注，2026-09-02）：GOV 子卡 merged-boundary 收口 + supersede §17.7「TD-104 未启动...待重新审计」+ 任务卡整体仍 🟡 进行中 + PR-D / PR-E / F-matrix / C1 / S5 wiring / capability flip / 六 erase 全部未启动
- §17.9（本节，PR-D closeout 标注，2026-09-03）：PR-D merged-boundary 收口 + supersede §17.8「PR-D 未启动」+ 任务卡整体仍 🟡 进行中 + **PR-E / F-matrix / C1 / S5 wiring / capability flip / 六 erase 仍全部未启动**（PR-D 完成 ≠ 其他任务完成；前置依赖解除：PR-E 可启动）
- **四节关系 = 累积 supersede 关系**（每节都 supersede 前一节中"待启动"或"待重新审计"措辞为 merged-boundary 事实，但**不** supersede 前一节"未启动"清单）

## 18. 关键引用

- 任务卡：`docs/03-engineering-governance/current-work.md` TASK-R1-S6-I3-D
- Spec: `docs/02-delivery-plans/01-specs/2026-07-27-req-041-047-r1-retention-purge-recovery.md` §3 / §10 / §11
- Plan: `docs/02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md` §R1-S6-8 / §R1-S6-12 / §R1-S6-13 / §R1-S6-14 / §R1-S6-15.5
- 工程门禁：`docs/03-engineering-governance/01-rules/quality-gates.md`、`engineering-principles.md`、`data-integrity.md`、`testing.md`
- ~~PR-D 基线：main `aff5488381e0e84878dd386cbc83be5abad3745a`（2026-08-27 closeout of PR #596/#597）~~ → **supersede（2026-09-01）**：D1a / D1b / D2 已分别 squash merge 入 main（PR #598 / #600 / #602 + closeout PR #603），旧 PR-D 基线 `aff54883` 仅作为 D1b closeout 时点的历史事实保留；PR-D 剩余 operational closeout 范围以 plan §S6-14 post-D2 rebaseline 注解为唯一依据
- TD-106 P2-1（runtime per-binding receipt）：`docs/03-engineering-governance/technical-debt.md#td-106` 仍登记未关
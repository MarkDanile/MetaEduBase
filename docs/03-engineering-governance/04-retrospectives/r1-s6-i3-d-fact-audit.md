# R1-S6-I3-D 事实审计（contract-to-code，fact-audit correction）

> Status: 🟡 进行中（事实审计 + correction 阶段）—— **本轮不实施业务代码**；本审计文档仅做 contract-to-code 读审查 + 修正前版事实错误
>
> 任务卡：`docs/03-engineering-governance/current-work.md` TASK-R1-S6-I3-D
>
> PR：#598（Draft, base=main, head=`6ab44fd2`）
>
> 实施 HEAD：implementation HEAD = `aff54883`（main 未变更）
>
> 冻结契约：Plan §S6-8 / §S6-12 / §S6-13 / §S6-14 / §S6-15.5（已随 PR #586 / #591 / #592 / #596 合入 main）

## 0. 审计范围与边界 + 本轮 correction 目标

**包含（本审计 + correction）**：
- 修正前版事实错误（ack 约束描述 / M 类互斥结论 / archive sink 口径）
- 当前 main `@aff54883` 真实代码能力 vs 冻结契约 §S6-8/12/13/14 实施要求 逐项对照
- 三方案互斥决策矩阵（A. advisory lock / B. deployment coordinator / C. persistent lease）
- 已有能力、缺失能力、P0/P1 风险点
- D1a/D1b/D2 拆分推荐 + 待用户裁决项

**不包含（本审计明确排除）**：
- 业务代码实现（ledger export executor / archive sink / restore replay executor / restore-before-open runbook）
- 复制、恢复旧 `c07c031c` scaffold
- 修改 Plan / 技术债总账 / work-log / Score Log / Metrics / migration 043 / schema / registry capability / 门禁脚本 / KNOWN_ISSUES / CI 配置
- 启动 PR-E / C1 / S5 production wiring / capability flip / 六 erase 入口生产可达
- 新增 `retentions_audits_paused` schema / migration（具体载体待用户裁决）

---

## 1. 独立 ledger 连续导出 / 归档

### 冻结契约（§S6-8.2）

> S5-SCH-0 持久化账本（operation `agent_conversation_purges` + checkpoint `agent_conversation_purge_owners` + external ref `agent_external_object_refs` + reconcile `agent_transport_scope_reconcile`）**必须连续导出/归档到独立于 DB 备份的存储**（receipt/ack_digest 变更日志）—— Spec §3「从**独立保存**的 erasure operation/receipt 账本重放」字面要求；DB 内账本停在备份快照时点，**快照之后完成的 purge 在恢复库中既留有正文又无账本记录**，body scan 永不为零（永久 fail-closed）或按账本裁剪则正文复活。

### 现状审计

| 项 | 状态 |
|----|------|
| 独立于 DB 备份的安全存储 sink | **缺失**——`scripts/` 仅含 mutation kill 驱动（`s6_td106_settlement_ledger_mutation_kill.py` / `s6i3_f10_mutation_kill.py` / `s6i3_fault_matrix_mutation_kill.py`），无独立 archive sink |
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
| Object storage（MinIO/S3/GCS/blob） | `packages/server-python/app/config.py` 含 `minio_endpoint` / `minio_access_key` / `minio_secret_key` / `minio_bucket`（仅作 Conversation 资源存储）——**未实现专用 ledger archive sink port** | 资源存储 ≠ ledger archive sink；现有 MinIO 用于 Conversation 资源上传，不携带 ledger 语义、manifest 与 watermark |
| Atomic file write/rename helper | 无 `app/composition/s6i3_d_ledger_archive.py` 等 archive helper | 通用 `os.rename` 可用但需配套 manifest + atomic-publish helper |
| 加密 / 权限 / retention policy | **缺失**——无 ledger archive 的密钥 / IAM / retention 配置 | spec §10.5 未冻结细节 |
| Scheduler / CLI 配置入口 | `scripts/` 仅 mutation kill 驱动；无 ledger archive CLI / cron | retention workers 由 `conversation_purge_scheduler` claim 路径触发，**非 cron 调度** |

### 结论

- **CLI ≠ sink**：D1a（codec + 导出 CLI）≠ D1b（独立 archive sink port）
- **生产 durable sink 若仓库缺配置**，只能登记生产门禁，**不能冒充连续独立归档完成**（§S6-8.6 drill 降级声明同等适用于 archive sink 缺位）
- **D1a** 可独立 PR 落地（codec 层，无 schema 改动）
- **D1b** 须用户裁决 sink 选型（本地 minio / S3 / 其他 object store / 文件系统）后才能开始实现

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

### DB / 应用 / CAS 三层约束职责分离（重要事实修正）

下表严格区分三层各自证明什么；**不得用任一层证明另一层的特性**：

| 层 | 约束 / 机制 | 证明什么 | **不**证明什么 |
|----|------------|---------|---------------|
| **DB 结构层** | `ck_agent_purge_owner_ack`（migration 034）| `state='acked'` ⇒ `ack_digest IS NOT NULL AND char_length(ack_digest) = 64`；`state<>'acked'` ⇒ `ack_digest IS NULL` ——**只约束「acked 必有 64-char digest；非 acked 必须 NULL」**，不校验 hex 内容 | hex 字符合规、digest 单调、digest 唯一性 |
| **DB 结构层** | `uq_agent_purge_owner(tenant_id, purge_operation_id, owner_key)`（migration 034）| **owner row 唯一性**——同一 conversation + owner 仅允许一行 checkpoint | ack_digest 单调、digest 唯一、CAS 收敛 |
| **应用层 digest 生成** | `external_erase_receipt_digest(adapter_key, adapter_version, idempotency_key, adapter_receipt_evidence, ref_digest, erase_outcome='erased')` | **64-char hex digest 计算**（`canonical_digest` via SHA-256 over canonical JSON envelope，schema_version=1）| DB 落账成功、CAS 收敛、idempotency_key 全局唯一 |
| **应用层 digest 生成** | `runtime_destroy_receipt_digest(adapter_key, adapter_version, idempotency_key, adapter_receipt_evidence, session_digest, destroy_outcome)` | 同上（runtime private envelope）| 同上 |
| **CAS 收敛层** | `_apply_window_outcome` SUCCESS 路径 `UPDATE ... WHERE id = :id AND ack_digest IS NULL` / `WHERE id = :id AND runtime_session_ref = :ref`（`external_ref_erasure_participant.py:863-910` / `runtime_erasure_participant.py:940-980`）| **owner row CAS 幂等**——rowcount=1 收敛；rowcount=0 ⇒ raise fail closed | hex 校验、digest 全局唯一（CAS 仅保证同 row 内幂等，跨 row 不保证） |
| **唯一约束层** | `uq_agent_purge_owner`（**唯一键 = (tenant_id, purge_operation_id, owner_key) **）| **一行 checkpoint per owner per operation**——不同 owner 可独立 ACK；同一 owner 重 ACK 必走同一 row CAS | digest 唯一性、hex 字符合规 |

### 重要修正（明确删除前版错误表述）

- ❌ **删除**「`ck_agent_purge_owner_ack` 要求 64-hex `ack_digest`」——该约束**只校验长度 64**，**不校验 hex 字符**；hex 校验在应用层（`canonical_digest` 经 SHA-256 自动产出 64-char hex）
- ❌ **删除**「`ack_digest` 唯一性保证幂等」——`ack_digest` 本身**没有 DB 唯一约束**；幂等性由 `uq_agent_purge_owner`（owner row 唯一）+ 应用层 CAS（rowcount=1）共同保证
- ❌ **删除**「`ack_digest` 64-hex 唯一键」——`ack_digest` 不是键；唯一键是 `(tenant_id, purge_operation_id, owner_key)`

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

- **P0**：`running`/`blocked` 重放路径完全缺失——`restore_replay_executor` 是 PR-D 唯一主任务
- **P1**：completed verify-only 嵌入 settlement ACK-lost repair 而非独立 replay executor

---

## 4. Owner 六元组

### 冻结契约（§S6-13.2）

> owner 是否可重放必须再结合六元组判定：`checkpoint.state` + `owner_key` + `ack_digest` + `owner_version` + `capability_digest` + `purge_revision`——**禁止只凭 operation.state 执行本地清除**

### 现状审计（六元组字段跨 2 表）

| 字段 | 持久化位置 | 状态 |
|------|-----------|------|
| `checkpoint.state` | `agent_conversation_purge_owners.state`（`ck_agent_purge_owner_state` 闭集） | ✅ 持久化 |
| `owner_key` | `agent_conversation_purge_owners.owner_key` | ✅ 持久化 |
| `ack_digest` | `agent_conversation_purge_owners.ack_digest`（**仅 acked 时非 NULL**，见 §2 DB 结构约束修正） | ✅ 持久化（条件性） |
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

- **P0**：实际 DB 写入能力完全缺失——replay executor 字符串登记，仅生成 verdict/notes 不构成 PR-D 交付
- **P1**：external/runtime 未 ACK 项的 `blocked` + reconcile 路径未独立化

---

## 6. M 类维护路径（集合锁 + 维护互斥）

### 冻结契约（§S6-4 + §S6-8.3）

> `restore 重放执行器`（S6-8 item 3；对恢复库执行账本记录的清除步骤；锁 = **M 类集合锁**；事务 = 一次性维护事务；tenant ✓；revision 无；**与 retention/audit jobs 互斥（重放期间暂停）**；不重复 adapter 调用，external/runtime 未 acked 项记 blocked+reconcile）

### 重要修正（明确删除前版错误结论）

- ❌ **删除**「`retentions_audits_paused` flag 缺失 ⇒ 需新 schema/migration 044」
- ❌ **删除**「M 类路径互斥机制完全缺失」作为结论性事实
- ✅ **修正为**：**冻结契约只规定 replay 与 retention/audit jobs 互斥**，**未指定互斥载体**——具体载体（持久 flag / advisory lock / 部署协调 / 其他）由用户裁决；本审计列出 3 个候选方案供用户抉择

### 三方案互斥决策矩阵

#### A. PostgreSQL advisory maintenance lock

| 维度 | 评估 |
|------|------|
| 跨进程有效性 | ✅ session-level `pg_advisory_lock` / transaction-level `pg_advisory_xact_lock`；跨进程互斥 |
| crash 自动释放 | ⚠️ session-level 不跨 crash（连接死则泄漏）；transaction-level 跨事务边界 commit/rollback 自动释放（**推荐事务级**） |
| stale owner / takeover | ❌ 无；不像 lease 那样带 owner/ttl |
| 是否需要 schema | ❌ 否——纯 PostgreSQL 内置 |
| 是否修改 retention workers | ✅ 需在 `run_event_retention` / `run_audit_retention` 启动路径取 shared lock（`pg_advisory_xact_lock_shared`） |
| 锁序影响 | ⚠️ 须明确新锁在 Run/Conversation/owner/collection lock **之前**还是之后——若在 Run 行锁之后取，可能与现有 retention 路径互锁（deadlock 风险）；**建议在 Run 行锁之前取** |
| 测试方式 | real PG 双连接验证（类似 F10 `_BlockingLookupAdapter` 模式） |
| production wiring 依赖 | ❌ 无——纯 DB 层 |
| 是否满足当前冻结契约 | ✅ §S6-4 M 类路径未限定具体锁类型；§S6-8.3「与 retention/audit jobs 互斥」字面满足 |

**优点**：零 schema 改动；DB 内置；事务边界自动释放；跨进程。
**缺点**：无 owner/ttl（不能 stale takeover）；须明确锁序位置（写作 S6-4 锁序修订）；须 retention worker 启动路径加 shared lock。

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
**缺点**：**需新 schema/migration**——直接触发 §S6-10 停止条件；新增 writer 须 S6-4 矩阵登记；migration roundtrip 风险（详见 §S6-10）。

### 三个方案推荐对比

| 维度 | A. advisory lock | B. external coordinator | C. persistent lease |
|------|------------------|-------------------------|---------------------|
| 跨进程 | ✅ | ⚠️ | ✅ |
| crash 安全 | ⚠️（事务级 OK） | ⚠️ | ✅（lease expiry） |
| stale takeover | | ⚠️ | ✅ |
| 无 schema 改动 | ✅ | ✅ | ❌ |
| 无 production wiring | ✅ | ❌ | ⚠️ |
| 本地真实 PG 可测 | ✅ | ❌ | ⚠️ |
| 满足冻结契约 | ✅ | ⚠️ | ⚠️（触发 §S6-10 停止条件） |
| 复杂度 | 中（须 retention worker 取 shared lock） | 高（须外部基建） | 中-高（须新 schema + writer 矩阵） |

### 推荐

**本审计阶段不做方案选择**——三方案各有边界条件，需用户裁决：

1. **若接受零 schema 改动 + 事务级 advisory lock**：选 A；可在 D1 后续 PR 内追加；无须 §S6-10 停止条件解除
2. **若接受生产 wiring 依赖**：选 B；需先建 maintenance coordinator，本仓无基建
3. **若接受新 schema/migration**：选 C；须用户授权 migration 044 + S6-4 writer 矩阵登记

**本轮明确不创建 migration 044**——A 方案无须 schema；B 方案不依赖 schema；C 方案须用户裁决。

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

- **P0**：replay executor + 编排流程完全缺失——PR-D 主任务
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
| conformance suite 静态枚举 | **缺失**——PR-D 完成后须新增 `_required_writer_specs()`（M 类：集合锁 + 一次性维护事务 + 与 retention/audit jobs 互斥声明 + 不调 adapter） |
| M 类写者裁定理由断言 | **缺失**——conformance 套件须新增 M 类断言 |
| 不接 production scheduler wiring | ✅ §S6-7.1 冻结「生产不可达」；PR-D 实现仍保持 M 类路径 |
| 不翻 capability | ✅ §S6-4 冻结 capability_digest 不变更 |

### P0/P1 风险

- **P1**：conformance suite 须新增 M 类写者枚举与裁定理由——PR-D 实现 + 测试同步
- **P1**：`S6I2_PENDING_WRITERS` 转 `registered` 需 conformance suite 全绿——本任务 PR-D 仅做审计

---

## 9. 测试与 mutation

### 冻结契约（§S6-5 / §S6-8 / §S6-14）

> PR-D 实现阶段：快照带 record kind/table identity；导入 + 重放 + body/ref 扫描 + S6-I2 verify + 全零才开放流量；每条路由至少一个真实 PG 正例和 fail-closed 负例；mutation 必须对应实际执行路径；NOT-RED 必须如实登记。

### 现状审计

| 项 | 状态 |
|----|------|
| 每条路由真实 PG 正例 | **缺失**——PR-D 实现 + 测试均未启动 |
| 每条路由 fail-closed 负例 | **缺失**——同上 |
| mutation kill（real PG execution path） | **缺失**——PR-D 须新建 `s6i3_d_ledger_replay_mutation_kill.py`（类似 `s6_td106_settlement_ledger_mutation_kill.py` 模式） |
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
  - **正例缺失**：互斥机制正确（方案 A/B/C 任一选定后）→ 集合锁正确持有 / 一次性维护事务 / retention/audit 暂停
  - **负例缺失**：互斥违规（retention/audit 期间 replay 发起）→ fail closed
- Restore-before-open：
  - **正例缺失**：ledger 导入 + replay + body/ref scan 全零 → 开放流量模拟
  - **负例缺失**：body/ref scan 非零 → 服务保持不可读写

### P0/P1 风险

- **P0**：所有测试 + mutation 缺失——PR-D 实施后须补齐
- **P1**：NOT-RED 登记体系缺失——PR-D 实施后须严格登记无法 kill 的 mutation

---

## 6 项阻塞问题答案（fact-audit correction）

### Q1：导出原始 ref/session 值时，恢复库如何安全完成 source-ref CAS 清除？

**答案（修正）**：

**禁止导出原始 `ref_value` / `runtime_session_ref`**——冻结契约 §S6-8.2「账本独立保存」原文限定 receipt/ack_digest 变更日志，**不包含**原始敏感 ref（spec §10 末段「不持久化原始 Chain-of-Thought、密钥、长期 Token 或未裁剪敏感响应」字面要求）。

恢复库 source-ref CAS 清除必须分 owner 状态：

| Operation 状态 | 恢复库 identity 重建路径 | | 行为 |
 |---|---| | |
 | **` completed` / `acked`** | 恢复库自身**旧 ledger 行 + 旧源行**已提供 identity：`agent_external_object_refs` 行的 `id` / `source_table` / `source_row_id`（保留——非敏感）+ `ref_value`（恢复库原始值）——restore 端按 row identity 与 ledger snapshot 双向 join 重建六元组 | | `B2 唯一清除路径 write_erased_and_clear_ref`（`external_ref_erasure_participant.py:863-910`，**CAS** `WHERE id = :id AND ack_digest IS NULL`）→ ledger `erase_state='erased'` + `receipt_digest` + 源 outbox `payload_ref=NULL` |
 | **` running` / `blocked`** | 恢复库**旧 ledger 行**（per-ref）+ **旧源行**（已残留/未清除）——不需原始 `ref_value`——`B2` helper 需 `ref_value` 仅用于 B2 内部 identity 重验，**identity 重验后可调 `write_erased_and_clear_ref` 的简化路径**（详见 `external_ref_erasure_participant.py:870-878` 「ref_value 仅用于身份重验」字面要求）| | `B2` CAS（同上）；仅本地可证明 owner（workspace/execution/transport）走；external/runtime 未 ACK 仍保持 `blocked` + reconcile |
 | **` external.payload.v1` / `runtime.private.v1` 未 ACK** | 恢复库**旧 ledger 行**提供 identity；但 adapter 不可调（无生产可达 + spec §10「不冒充已 erase」）——**禁止 CAS cleared** | | **保持 `blocked` + reconcile**（§S6-8.3 + §S6-13 字面要求）；replay executor **不调用 adapter** |

**任一 CAS 所需值无法证明 ⇒ 零写 + fail closed + runbook 人工处置**（§S6-13.4 字面要求 `DIGEST_MISMATCH` / `OWNER_VERSION_MISMATCH` / `UNRECOGNIZED_STATE`）。

### Q2：当前是否有足够 receipt/digest 证明 per-ref/binding 收口？

**答案（修正）**：✅ **per-owner receipt 充足**——TD-106 方案 A 已落地（PR #586 合 main）：

- **`external.payload.v1` per-ref receipt**：`agent_external_object_refs.receipt_digest` —— `external_erase_receipt_digest(adapter_key, adapter_version, idempotency_key, adapter_receipt_evidence, ref_digest, erase_outcome='erased')` 重算（**64-char hex，SHA-256 over canonical JSON envelope，schema_version=1**）
  - **重算基准** = adapter evidence（**不依赖原始 `ref_value`**）
  - **持久化载体** = `agent_external_object_refs.receipt_digest` 列
  - **CAS 收敛** = `_apply_window_outcome` SUCCESS 路径 `UPDATE ... WHERE id = :id AND ack_digest IS NULL`
- **`runtime.private.v1` per-binding receipt 承载**：
  - ⚠️ **`agent_runtime_session_bindings` 无独立 `receipt_digest` 列**——这是**事实修正**（前版误称 runtime 有 receipt digest 列）
  - **证明载体** = RuntimeErasureSummary `receipt_digests: tuple[str, ...]`（`runtime_erasure_participant.py:163`）+ `ack_digest`（聚合 digest）+ Tx2 后 final scan `runtime_session_ref IS NOT NULL`
  - **`runtime_destroy_receipt_digest`** 重算：基于 adapter evidence + session_digest + destroy_outcome
  - **持久化载体** = binding 行 `runtime_session_ref IS NULL` + `status='closed'`（**binding 行即事实源**，不需独立 receipt 列）
  - **CAS 收敛** = `UPDATE ... WHERE id = :id AND runtime_session_ref = :ref`（`runtime_erasure_participant.py:940-980`）

**严格禁止**：
- ❌ 不得用 `checkpoint.ack_digest` 聚合 digest 冒充 per-binding receipt——`ack_digest` 是聚合 ack，**不是** per-binding receipt
- ❌ 不得恢复端跳过 per-binding identity 重验（`ref_value` 已 NULL/缺失可跳过；非 NULL 但 mismatch ⇒ fail closed）

**结论**：external 有完整 per-ref receipt 载体；runtime 无独立 receipt 列但 binding 行 + ACK summary 足够——恢复端必须**逐 binding 重算 receipt digest**（不能用 ack_digest 聚合替代）。

### Q3：仓库是否已有真正独立于数据库备份的归档 sink？

**答案（修正）**：

**已识别候选**：
- ✅ `packages/server-python/app/config.py` 含 MinIO 配置（`minio_endpoint` / `minio_access_key` / `minio_secret_key` / `minio_bucket`）——**但仅用于 Conversation 资源存储**（用户上传文件等），**不携带 ledger 语义、manifest 与 watermark**
- ✅ 通用 `os.rename` / `tempfile.NamedTemporaryFile` 可作为原子 publish helper 基座——但**无 ledger archive sink port 封装**
- ❌ **无 ledger archive 专用配置**（密钥 / IAM / retention policy）
- ❌ **无 ledger archive scheduler / cron 入口**（retention workers 由 `conversation_purge_scheduler` claim 路径触发，**非 cron**）

**关键修正**：
- ❌ **前版误称 `scripts/s6i3_d_ledger_archive.py` 为"独立 archive sink"**——**CLI 是 producer**（产生 archive 输出）；**sink 是独立于 DB 备份的持久目标**（CLI + sink 是 producer/consumer 关系）
- ✅ **D1a** = codec + manifest + export/import validation（CLI 形态，puredocs-only 可独立 PR 落地）
- ✅ **D1b** = archive sink port + 一个明确验证层级的实现（**依赖 sink 选型**——用户裁决：本地 minio / S3 / 其他 object store / 文件系统）
- ⚠️ **生产 durable sink 若仓库缺配置**——**只能登记生产门禁，不能冒充连续独立归档完成**（§S6-8.6 drill 降级声明同等适用）

### Q4：M 类互斥是否有可执行协调机制？

**答案（修正）**：

**前版结论已撤回**：❌ 不得继续主张「必须新增 `retentions_audits_paused` 字段/migration 044」——**冻结契约只规定 replay 与 retention/audit 互斥，未指定互斥载体**。

**当前事实**：互斥机制**具体载体**缺失；具体载体（A / B / C 三方案）由用户裁决——见 §6 三方案互斥决策矩阵。

**任一方案下，互斥实现要点**：

| 方案 | 实现要点 | 约束 |
|------|---------|------|
| A. advisory lock | retention/audit worker 启动路径取 `pg_advisory_xact_lock_shared`；replay 取 exclusive；事务边界自动释放 | 须 S6-4 锁序修订 |
| B. external coordinator | 仓内无 production wiring 基建——若只能靠 runbook 声明，**不得称为 executor 互斥已闭合** | spec §10.5「V1 不支持 purge 开启时仍有旧 Writer 进程在线」 |
| C. persistent lease | migration 044+；新增 maintenance_lease 表/列；takeover 设计 | **触发 §S6-10 停止条件**「需要新 schema/migration」 |

**本轮明确不创建 migration 044**（A 方案无须 schema；B 不依赖 schema；C 须用户授权）。

### Q5：避免 completed verify-only 与 running/blocked 重放重复 side effect

**答案（修正）**：

| 维度 | 保证机制 |
|------|---------|
| `completed` 不重复 side effect | §S6-12.1 字面「verify-only」——**只校验 ledger receipt + body/ref scan**；**不调用 adapter、不执行本地清除** |
| `running`/`blocked` 不重复 owner side effect | `ck_agent_purge_owner_ack` + `uq_agent_purge_owner(tenant_id, purge_operation_id, owner_key)`：同 owner 仅一行 checkpoint；CAS UPDATE 谓词 `WHERE id = :id AND ack_digest IS NULL`（external）/ `AND runtime_session_ref = :ref`（runtime）——rowcount=1 收敛；rowcount=0 ⇒ raise fail closed |
| ack_digest 唯一性 | ❌ **ack_digest 没有 DB 唯一约束**（仅有 `ck_agent_purge_owner_ack` 约束长度 64）；幂等性由 owner row 唯一 + 应用层 CAS（rowcount=1）共同保证 |
| M 类路径一次性维护事务 | replay executor 一次性 commit；不留中间状态 |
| 不调用 adapter | §S6-8.3 + §S6-13 字面要求 |
| 跨 purge 周期幂等 | 同 operation 重复 replay ⇒ 同一 owner row（`uq_agent_purge_owner`）⇒ ack_digest 已非 NULL ⇒ CAS rowcount=0 ⇒ fail closed（不再二次写） |
| 跨 conversation 幂等 | 不同 conversation 不同 `purge_operation_id` ⇒ 不同 owner row ⇒ 不冲突 |

**关键修正**：
- ❌ 不得用 `ack_digest` "唯一性"作为幂等保证——`ack_digest` 不唯一约束
- ✅ 幂等保证 = owner row 唯一约束 + 应用层 CAS rowcount=1

### Q6：快照后完成、但数据库备份中不存在 ledger 记录的 purge

**答案（修正）**：✅ §S6-8.2 字面冻结：

> DB 内账本停在备份快照时点，**快照之后完成的 purge 在恢复库中既留有正文又无账本记录**，body scan 永不为零（永久 fail-closed）或按账本裁剪则正文复活——**冻结：快照后 purge 处置 = fail-closed 范围（该部分 conversation 保持服务关闭）+ 人工 reconcile 门禁（runbook 步骤），不得静默放行**。

**关键事实**：
- ❌ **不得按账本裁剪**（会正文复活）
- ✅ **保持服务关闭 + 人工 reconcile**——snapshot 后 purge 范围 conversation 保持不可读写
- ❌ **不得静默放行**——§S6-8.6 字面要求

---

## 已有能力 / 缺失能力 / P0/P1 风险汇总（修正）

### 已有能力（main @`aff54883`）

| 能力 | 位置 |
|------|------|
| TD-106 per-ref receipt | ✅ `agent_external_object_refs.receipt_digest`（`external_erase_receipt_digest` 重算，64-char hex SHA-256）|
| TD-106 per-binding receipt 承载 | ✅ `agent_runtime_session_bindings.runtime_session_ref IS NULL` + `status='closed'`（binding 行即事实源，**无独立 receipt 列**——RuntimeErasureSummary `receipt_digests` + ack_digest 聚合 + Tx2 final scan 联合证明）|
| `ck_agent_purge_owner_ack` | ✅ 长度 64 + state 条件非 NULL/IS NULL（**不校验 hex**）|
| `uq_agent_purge_owner` | ✅ (tenant_id, purge_operation_id, owner_key) 唯一——owner row CAS 幂等 |
| Owner 六元组持久化（5/6 字段） | ✅ `agent_conversation_purge_owners`（5 字段）+ `agent_conversation_purges.purge_revision`（跨表）|
| 集合锁 API（D8） | ✅ `acquire_transport_aggregate_lock` / `acquire_owner_lock`（`agent_erasure_locks.py`）|
| Body/ref 六 owner 终态扫描 | ✅ `scan_execution_body` 等 + S6-6 `verify_inspection` 巡检 CLI |
| `cancel_scheduled_operations_for_restore` | ✅ `erasure_repository.py:890-965`（scheduled→cancelled）|
| 本地 owner 清除 sanctioned helper | ✅ `_erase_conversation_title` / `_redact_messages` / `_delete_message_parts` / `_delete_user_states` / `_clear_terminal_outputs` / `_clear_context_snapshots` / `_clear_event_payloads` / `_clear_compatibility_outputs` / `_anonymize_conversation_actors` |
| 三层 CHECK 闭集 | ✅ `ck_agent_purge_state` / `ck_agent_purge_owner_state` / `ck_agent_erasure_fence_state` |
| MinIO 资源存储（**非 ledger archive**） | ✅ `packages/server-python/app/config.py` MinIO 配置 |
| `S6I2_PENDING_WRITERS` 登记 | ✅ `restore_replay_executor` 字符串 pending |

### 缺失能力（PR-D 须补齐）

| 能力 | 触发停止条件 |
|------|------------|
| **独立 archive sink port** | 缺失（**sink 选型待用户裁决**：本地 minio / S3 / 其他 object store / 文件系统）——D1b |
| **Ledger 连续导出 CLI**（operation/checkpoint/ref/reconcile 四类） | 缺失 ——D1a |
| **快照 codec + schema version + manifest digest + record_count** | 缺失（codec 层绑定）——D1a |
| **Restore 端 ledger 导入 + 六元组 join 重构** | 缺失 ——D1a |
| **M 类维护路径互斥机制** | 缺失（具体载体三方案待用户裁决）——D2 |
| **Restore replay executor**（M 类路径 + 一次性维护事务 + 集合锁 + 与 retention/audit jobs 互斥） | 缺失 ——D2 |
| **`running`/`blocked` 本地可证明 owner 重放** + `failed`/`completed`/`cancelled`/`scheduled` 路由 | 缺失 ——D2 |
| **external/runtime 未 ACK 项 `blocked` + reconcile 路径** | 缺失 ——D2 |
| **Restore-before-open 编排 + runbook** | 缺失 ——D2 |
| **drill 降级声明 + 生产门禁登记** | 缺失 ——D2 |
| **PR-D 真实 PG 测试 + mutation kill** | 缺失 ——D1a + D2 |
| **`S6I2_PENDING_WRITERS.restore_replay_executor` 转 `registered`** | 缺失 ——D2 |

### P0/P1 风险（修正）

| 风险 | 级别 | 触发停止条件 |
|------|------|------------|
| 独立 archive sink 完全缺失 | **P0** | 不触发（PR-D 主任务；sink 选型待用户裁决） |
| M 类路径互斥机制具体载体缺失 | **P0** | **修正**：具体载体由用户裁决（A/B/C 三方案）——A 无 schema 改动；B 须 production wiring；C 触发 §S6-10「需要新 schema/migration」 |
| restore-before-open 真实 PG 演练 | **P0** | R1-AC12 字面降级 + 生产门禁登记 |
| ledger snapshot 后 purge 残留 conversation | **P0** | fail-closed + 人工 reconcile |
| 四表无 `schema_version`/`digest`/`record_count` 列 | **P1** | 不触发（codec 层绑定） |
| 六元组跨表 join 恢复 | **P1** | 不触发（实现复杂度） |
| runtime 无独立 `receipt_digest` 列 | **P1** | 不触发（binding 行即事实源 + RuntimeErasureSummary 证明载体；**不得用 ack_digest 聚合替代 per-binding receipt**） |
| external/runtime 未 ACK 项独立 helper | **P1** | 不触发（新增 helper，不修改 S5） |
| conformance suite M 类写者枚举 + 裁定理由 | **P1** | 不触发（实施同步） |

---

## 推荐：D1a / D1b / D2 三步拆分（修正）

### 推荐：**拆 D1a / D1b / D2 三步走**（前版 D1/D2 拆分已撤回——按 sink 分离与互斥决策进一步细分）

#### **D1a**（本 PR 任务继续推进阶段，contract-first）

**Scope**：
- Ledger snapshot codec + schema version + manifest digest + record_count（codec 层绑定，无 schema 改动）
- Ledger 连续导出 CLI（operation/checkpoint/ref/reconcile 四类 record kind）
- Restore 端 ledger 导入 + 六元组 join 重构 + schema version bump fail closed
- real PG 验证：ledger round-trip + schema version mismatch fail closed
- **不动 schema/migration / 不实现 archive sink port / 不实现 replay DB mutation**

**理由**：D1a 不触及 §S6-10 停止条件（无新 schema/migration / 无 S5 状态机修改）；可独立完成 + 真实 PG 验证 + 评分 + 合并 + closeout。

#### **D1b**（独立后续 PR，依赖 sink 选型裁决）

**Scope**：
- 独立 archive sink port 实现（依赖用户裁决 sink 选型：本地 minio / S3 / 其他 object store / 文件系统）
- 归档最小正确性属性：原子发布 / manifest+content digest / record count / tenant 隔离 / monotonic cursor/watermark / crash 安全 / 重复导出幂等 / sink 不可达 fail closed
- 与 D1a codec 对接（manifest + records 写入 sink）
- drill 降级声明（若本地 sink 与生产 sink 选型不一致）+ 生产门禁登记
- real PG 验证：连续导出 + archive round-trip + crash 安全

**理由**：D1b 须用户裁决 sink 选型（**生产 wiring 选型是 §S6-10 边界**）——D1a 可独立 PR 落地，D1b 在 sink 裁决后启动。

**D1a + D1b 合并评估**：
- ✅ 若 sink 选型明确（本地 minio）+ D1a 与 D1b 评审面可控 ⇒ **可合并为单 PR D1**
- ❌ 若 sink 选型未定（外部 S3 / 自建 object store）⇒ **必须分拆**（D1a codec + 导出 + 导入；D1b sink port + 生产门禁）

#### **D2**（独立后续 PR，须用户裁决互斥方案 + 不依赖 sink 选型）

**Scope**：
- M 类维护路径互斥机制（依赖 §6 三方案用户裁决：建议 A 起步）
- Restore replay executor（M 类路径 + 一次性维护事务 + 集合锁 + 与 retention/audit jobs 互斥）
- replay operation 六态路由（`running`/`blocked`/`scheduled`/`failed`/`completed`/`cancelled`）
- external/runtime 未 ACK 项独立 `blocked` + reconcile helper
- Restore-before-open 编排 + body/ref scan 集成
- `docs/02-delivery-plans/03-runbooks/restore-before-open.md`
- `S6I2_PENDING_WRITERS.restore_replay_executor` 转 `registered`
- conformance suite M 类写者枚举与裁定理由
- real PG 验证：六态路由 + 互斥 + body/ref scan + 服务开关编排

**理由**：D2 涉及互斥机制选型（**A 方案无 schema 改动；B 须 production wiring；C 触发 §S6-10「需要新 schema/migration」**）——A 方案推荐起步，但具体选型由用户裁决；D2 在互斥方案完成契约裁决前**禁止启动**。

### 推荐理由（fact-audit correction 依据）

- **CLI ≠ sink** 区分明确：producer 与 consumer 必须分别落地
- **三方案互斥决策**已并列评估（A advisory lock / B external coordinator / C persistent lease），**A 推荐起步**（零 schema 改动 + 真实 PG 可测 + 无 production wiring 依赖），但用户裁决
- **runtime receipt 事实修正**：binding 行即事实源（无独立 receipt 列），需 RuntimeErasureSummary + ack_digest 聚合 + Tx2 final scan 联合证明——**不得用 ack_digest 聚合冒充 per-binding receipt**
- **ack 约束三层职责分离明确**：DB 结构约束（长度 64）/ 应用层 digest 生成（hex 校验）/ CAS 唯一约束（owner row 唯一）——不得跨层证明
- **拆分按 sink 分离 + 互斥决策** ——前版 D1/D2 已撤回

---

## 本轮明确「零业务代码实现」

- ✅ **不实施**任何业务代码：ledger export executor / archive sink port / restore replay executor / restore-before-open runbook / D1b sink port 全部未创建
- ✅ **不修改**：Plan / 技术债总账 / work-log / Score Log / Metrics / migration 043 / schema / registry capability / 门禁脚本 / KNOWN_ISSUES / CI 配置 / F10/TD-105 已合并内容
- ✅ **不实现 paused flag schema/migration**（具体载体由用户裁决——A/B/C 三方案均不通过本 PR 启动）
- ✅ **不启动**：PR-E / C1 / S5 production wiring / capability flip / 六 erase 入口生产可达
- ✅ **不复制 / 恢复旧 `c07c031c` scaffold**
- ✅ **不创建 migration 044**

---

## 仍待用户裁决项

1. **Sink 选型**（决定 D1b 启动与否）：
   - 本地 minio（仓库已有 `minio_endpoint` 配置）？
   - 外部 S3 / GCS / 其他 object store？
   - 文件系统（atomic rename）+ 加密 + retention policy 自建？
2. **M 类互斥方案**（决定 D2 启动与否）：
   - A. PostgreSQL advisory maintenance lock（**推荐起步**）？
   - B. 外部 deployment/maintenance coordinator（需 production wiring 基建）？
   - C. 持久化 DB maintenance lease/flag（触发 §S6-10 停止条件）？
3. **D1a + D1b 是否合并为单 PR D1**（依赖 sink 选型）：
   - 若本地 minio 选型 + D1b 评审面可控 ⇒ 合并
   - 否则保持分拆
4. **D1b / D2 启动顺序**：
   - D2 须在互斥方案用户裁决后启动
   - D1b 可与 D2 并行（sink port 与互斥机制独立），但 D1b 须在 sink 选型裁决后启动

---

## 关键引用

- 任务卡：`docs/03-engineering-governance/current-work.md` TASK-R1-S6-I3-D
- Spec: `docs/02-delivery-plans/01-specs/2026-07-27-req-041-047-r1-retention-purge-recovery.md` §3 / §10 / §11
- Plan: `docs/02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md` §R1-S6-8 / §R1-S6-12 / §R1-S6-13 / §R1-S6-14 / §R1-S6-15.5
- 工程门禁：`docs/03-engineering-governance/01-rules/quality-gates.md`、`engineering-principles.md`、`data-integrity.md`、`testing.md`
- PR-D 基线：main `aff5488381e0e84878dd386cbc83be5abad3745a`（2026-08-27 closeout of PR #596/#597）
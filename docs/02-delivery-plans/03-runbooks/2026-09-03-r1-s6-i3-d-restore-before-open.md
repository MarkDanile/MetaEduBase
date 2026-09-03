# R1-S6-I3-D PR-D: Restore-before-Open 运维 runbook

> Status: Draft（本 runbook 随 R1-S6-I3-D PR-D 落地 + closeout 同步）
> Branch: `feature/req041-047-r1-s6-i3-d-pr-d-operational-closeout`
> 事实基线: plan [`§S6-14 post-D2 rebaseline 注解`](../../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md#L2354-L2366) + [`§S6-8 item 3/4/5/6`](../../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md#L2235-L2243) + fact-audit [`§17.6 / §17.7 / §17.8`](../../../03-engineering-governance/04-retrospectives/r1-s6-i3-d-fact-audit.md#L840-L1021)

本 runbook 记录 PR-D 落地的 4 项运维步骤：**restore-before-open 入口**、**crash/retry 处置**、**post-snapshot purge 处置**、**M-class 并发窗口 + blocked/manual reconcile ops**。所有步骤严格保持 production-neutral；**不**依赖 scheduler caller、不做 capability flip、不进入六 erase 入口生产可达路径。

---

## 1. 何时用 restore-before-open runbook

**触发场景**：从旧 PostgreSQL 备份恢复数据库 + 服务保持不可对外读写 → **重放独立 erasure ledger（archive）** → **body/ref 扫描为零** → 才开放流量（Spec §3 末段 + plan §S6-8 item 1）。

**前置事实**：
- 服务必须先置于不可对外读写状态（maintenance 模式 / 反向代理 503 / 关闭 listener）
- D1b archive 已存在（commit-graph monotonic；由 D1a 持续导出 + D1b publish 累积）
- 旧快照本身已冻结 operation / checkpoint / external_ref / reconcile 四类账本（migration 034/040）

**责任分工**：
- **平台 / SRE**：控制 service availability（maintenance 模式）
- **数据合规 / DPO**：触发 runbook 的决策权
- **R1-S6 PR-D orchestration entry 调用方**（CLI / ops script / 维护工具）：执行 replay 与 gate
- **生产基础设施负责人**（plan §S6-8 item 6 + R1-AC12）：承接 drill 真实 PG / MinIO 演练（本地无法执行 → 生产门禁登记）

---

## 2. restore-before-open 入口与参数

### 2.1 orchestration entry（PR-D 主交付）

```python
from app.composition.s6i3_d_ledger_orchestration import (
    export_and_archive_ledger_segment,
)
from app.composition.s6i3_d_ledger_archive_sink import (
    InMemoryLedgerArchiveSink,  # for tests
    MinioLedgerArchiveSink,      # for production
)
from app.composition.restore_replay import (
    replay_archive_segment_for_tenant,
    evaluate_restore_before_open,
)

# step 1: 持续 ledger export/archive（caller-managed cadence）
outcome = await export_and_archive_ledger_segment(
    session_factory,        # async_sessionmaker
    sink=MinioLedgerArchiveSink(
        bucket="metaedu-ledger-archive",  # 必须 ≠ metaedu-resources
        endpoint=...,
        access_key=...,
        secret_key=...,
    ),
    tenant_id=tid,
)
# → PublishOutcome(export_id, generation, marker_key, segment_key, segment_sha256,
#                  idempotent_retry)

# step 2: replay（DB tx 外读 archive → pass A drift → pass B participant）
replay_report = await replay_archive_segment_for_tenant(
    session_factory,
    sink=sink,
    tenant_id=tid,
)
# → RestoreReplayReport(
#     operations_total, owners_total,
#     owners_local_cleared, owners_blocked_kept, owners_non_local_blocked,
#     owners_verify_only, owners_skipped, owners_fact_drift, owners_no_repeat,
#     runtime_binding_evidence_unprovable, external_verified, external_verification_failed,
#     verdict, error, toctou_drift, pass_a_drift, participant_failures)

# step 3: restore-before-open gate（强制消费 replay_report）
gate_report = await evaluate_restore_before_open(
    session_factory,
    tenant_id=tid,
    replay_report=replay_report,
    runtime_proof_c_present=False,  # 由 caller 显式传入（**不可**绕 0/False）
)
# → RestoreBeforeOpenReport(
#     open_allowed, blocked_reasons, owner_scan_findings, s6_6_findings)
```

### 2.2 入口契约不变式（**禁止**绕过）

| # | 不变式 | 强制点 |
|---|--------|--------|
| 1 | phase-1 必须 RR + READ ONLY | D1a `_assert_transaction_attrs` 强校验 `SHOW transaction_isolation / transaction_read_only` |
| 2 | phase-1 不得触发 sink I/O | D1a / D1b docstring 显式登记 + 既有 `_publish_two_phase` 测试已验证 |
| 3 | phase-2 不接收 AsyncSession | D1b `publish_ledger_segment` 函数签名 |
| 4 | tenant_id 严格规范 UUID | D1a `_assert_canonical_uuid` + D1b `_assert_canonical_uuid` |
| 5 | segment bytes 字节级 deterministic | `json.dumps(sort_keys=True, separators=(",", ":"))` |
| 6 | marker 不含 wall-clock 字段 | 用户裁决 A-1；`published_at_unix` 已删除 |
| 7 | bucket ≠ `metaedu-resources` | D1b `FORBIDDEN_BUCKETS` |
| 8 | cross-tenant artifact 拒绝 | D1a `TENANT_BINDING_MISMATCH`（在 records 解析前 fail closed） |
| 9 | DB hard boundary 仅 `metaedu_test` | 仓库级 CI 强校验 + 本 PR 不主动连接 `metaedu` |

### 2.3 caller 必须显式接住的字段

| 字段 | 类型 | 含义 | 缺省行为 |
| ------|------|------|----------|
| `session_factory` | `async_sessionmaker[AsyncSession]` | 连接 `metaedu_test`（PR-D 不接入 production） | None → TypeError |
| `sink` | `LedgerArchiveSink` | InMemory / MinIO；caller 构造 | None → TypeError |
| `tenant_id` | `uuid.UUID`（规范 lowercase hyphenated） | D1a / D1b 双侧 tenant binding | 非法 → `LedgerSnapshotError("TENANT_ID_NOT_UUID")` |
| `parent_export_id` | `Optional[str]`（D1b phase-2 专用） | 显式跟随已知 tip；`None` = 跟随当前 tip | `None` → 跟随 tip |
| `sleeper` | `Optional[Callable[[float], ...]]` | 测试可注入 fake sleeper 禁止真实 sleep | `None` = 默认 `asyncio.sleep` |
| `runtime_proof_c_present` | `bool`（D2 gate） | **caller 显式传入**，不可绕 0/False | 默认值 = False |

---

## 3. RestoreReplayReport / RestoreBeforeOpenReport 消费约定

### 3.1 RestoreReplayReport 内部 blocking 项（gate 自动消费）

```text
error:                str | None       # archive read / pass A / pass B 任何失败 → gate 阻断
pass_a_drift:         int             # pass A drift → gate 阻断
toctou_drift:         int             # pass B TOCTOU drift → gate 阻断
participant_failures: int             # participant 抛错 → gate 阻断
owners_fact_drift:    int             # 跨层状态混读 / 字段 drift → gate 阻断
owners_blocked_kept:  int             # local owner participant blocked=True → 保留不清 → gate 阻断
runtime_binding_evidence_unprovable: int  # runtime + completed + per-binding 不可证 → gate 阻断
external_verification_failed: int     # external.receipt drift / state≠erased → gate 阻断
owners_non_local_blocked: int         # non_local_blocked + runtime_blocked → gate 阻断
```

`has_blocking_finding()` 是统一 gate 判定方法（不绕过 0/False）。

### 3.2 RestoreBeforeOpenReport 输出

```text
open_allowed: bool                  # 全部 blocking 项 == 0 且 runtime_proof_c_present=False
blocked_reasons: tuple[str, ...]    # 阻断项具名列表（caller 必须显式处理）
owner_scan_findings: tuple[(label, total), ...]  # 6 owner body-scan 残量（per-conversation 累计）
s6_6_findings: tuple[(inspection, total), ...]   # S6-6 巡检 6 类发现（tenant/digest/event_gap/...）
```

### 3.3 blocked_reasons 处理路径

| blocked_reasons 前缀 | 含义 | 责任路径 |
|----------------------|------|----------|
| `replay_error:*` | archive 读 / pass A drift / pass B exception | **检查 archive 完整性 + 备份时点一致性** |
| `pass_a_drift:*` | archive 与 LIVE 六元组 + operation fence 不一致 | **回滚备份，重做 restore**（不可自动修复） |
| `toctou_drift:*` | pass B 锁内 LIVE 变化 | **回滚备份，重做 replay** |
| `participant_failure:*` | local owner participant 抛错 | **检查 owner capability / runtime adapter availability** |
| `fact_drift:*` | 跨层状态混读 / 字段 drift | **回滚备份，回 runbook 人工确认** |
| `blocked_kept:*` | local owner participant blocked=True | **保留原状态；走 runbook 人工 reconcile** |
| `RUNTIME_BINDING_EVIDENCE_UNPROVABLE:*` | runtime per-binding proof 缺失 | **保持服务关闭；走 runbook 人工 reconcile**（用户裁决 5 = c） |
| `external_verification_failed:*` | external.receipt / state drift | **回滚备份，重做 replay** |
| `non_local_blocked:*` | non-local owner 无 adapter | **保持服务关闭；走 runbook 人工 reconcile** |
| `<owner>_residual:*` | owner body-scan 残量 > 0 | **回滚备份，确认 body 已擦除**（plan §S6-8 item 5） |
| `<owner>_scan_error:*` | scan provider 抛错 | **检查 build_scan_providers 配置** |
| `s6_6_inspection_error:*` | S6-6 巡检 抛错 | **检查 verify_inspection 调用** |

---

## 4. crash / retry 处置（计划 §S6-8 item 3）

### 4.1 phase-1 阶段崩溃（caller-managed RR+RO 事务内）

| 崩溃点 | 自动行为 | 人工路径 |
|--------|----------|----------|
| `SET TRANSACTION ISOLATION LEVEL` 失败 | `async with session.begin()` 自动 rollback；orchestration raise | 检查 PG 连接 + isolation 设置 |
| `export_ledger_segment_for_archive` 内 D1a 失败 | 同上 → `PublishPreconditionFailedError("D1A_EXPORT_FAILED")` | 检查 schema / fixture / capability digest |
| D1a decoder 校验失败（put 前） | 同上 → `PublishPreconditionFailedError("D1A_DECODE_PRE_PUBLISH_FAILED")` | 检查 archive 完整性 + D1a envelope |

**关键**：phase-1 失败 = **零** sink I/O（用户裁决 B-1） → archive tip 不变 → 重试安全（同一 segment_bytes 重新导出）。

### 4.2 phase-2 阶段崩溃（D1b publish）

| 崩溃点 | 自动行为 | 人工路径 |
|--------|----------|----------|
| `find_committed_tip` 抛错 | `LedgerArchiveError("ARCHIVE_TIP_NOT_FOUND")` 或 `RestoreReplayError("ARCHIVE_TIP_NOT_FOUND")` | 检查 sink / bucket / fork / generation regression |
| segment PUT 失败（transient） | D1b `_retry_with_backoff` 重试（MAX_PUBLISH_RETRIES=3 + RETRY_BACKOFF_SECONDS=(0.05, 0.2, 0.5)） | 监控 transient 网络 |
| segment PUT 失败（重试耗尽） | `ArchiveUnavailableError("PUBLISH_RETRY_EXHAUSTED")` | 检查 MinIO / network / credentials |
| segment GET-back digest 不匹配 | `SegmentDigestMismatchError` | **不重试**：MinIO 端字节损坏 → 人工处置 |
| marker PUT 失败 | D1b retry；`ObjectIdentityCollisionError` 转换 `ExistingPayloadDivergesError` | **不重试**：现有 marker payload 不同 → 人工处置（不可变模型禁止覆盖） |
| 跨调用 retry（同 export_id） | D1b `idempotent_retry=True`（同 marker key 复用） | 无需人工；caller 重试安全 |

**关键**：phase-2 不接收 AsyncSession → DB 事务**已结束** → segment PUT 成功但 marker PUT 失败时，**该 segment 已是孤儿**（committed tip 不变；新 generation + new export_id 才能推进）→ caller 重试必须传新 export_id（依赖 D1a segment_bytes 变化；如果 DB state 没变，**永远不会**产生新 export_id）→ **D1a 字节确定性保证**。

### 4.3 phase-3 阶段崩溃（restore-before-open gate）

| 崩溃点 | 自动行为 | 人工路径 |
|--------|----------|----------|
| `evaluate_restore_before_open` 抛错 | `open_allowed=False`；`blocked_reasons` 含具名 code | 检查 `build_scan_providers` / `verify_inspection` / session_factory |
| 6 owner body-scan 任一抛错 | gate 阻断 + `blocked_reasons` 含 `<owner>_scan_error:<ExceptionType>` | **不放过**（保留关闭） |
| S6-6 巡检抛错 | gate 阻断 + `s6_6_inspection_error:<ExceptionType>` | 检查 verify_inspection 配置 |

---

## 5. post-snapshot purge 处置（计划 §S6-8 item 2 / 3 / 4）

### 5.1 快照时间窗冲突（backup cutover 期间）

**事实**：DB 备份停止 + 服务 stop + pg_dump 完成之间可能仍在执行 purge operation → backup 内含未 ACK operation / checkpoint → restore 时 operation 处于 `running` 状态。

**处置**：
- restore 后 → D2 `replay_archive_segment_for_tenant` 触发 pass A → 检测 drift（archive snapshot ≠ current archive）+ operation `state='running'` → **失败闭合零写**（spec §3 + plan §S6-8 item 3）
- 不重试，不静默修复 → **保持服务关闭** + 走 runbook 人工 reconcile（无自动化路径）

### 5.2 快照后完成 purge（snapshot pre-purge；ledger 已 advance）

**事实**：D1b archive 已含 pre-snapshot 完成 purge 的 marker → restore 时 archive 与 LIVE 一致 → pass A 六元组对账通过 → pass B 走 NO_REPEAT 或 VERIFY_ONLY。

**处置**：
- D2 replay → pass A 无 drift → pass B 走 `NO_REPEAT`（LIVE state=acked + archive cp∈{pending,erasing} → 完整 terminal evidence 单向推进）→ **不调 participant**
- D2 replay → pass B 走 `VERIFY_ONLY`（local owner completed + acked）→ **不调 participant**
- D2 replay → pass B 走 `EXTERNAL_VERIFIED`（external.payload.v1 completed + acked）→ 验证 receipt + final scan → **不调 adapter**
- D2 replay → pass B 走 `RUNTIME_BINDING_EVIDENCE_UNPROVABLE`（runtime.private.v1 completed + acked）→ **零 DB 写**，gate 阻断 → runbook 人工 reconcile

### 5.3 快照后未 ACK owner（snapshot mid-purge）

**事实**：operation state='running'，部分 owner `state='erasing'`，部分 `state='pending'`，部分 `state='acked'`

**处置**：
- D2 replay → pass A drift（operation state=running ≠ archive snapshot state 终态）→ `RestoreReplayError("FACT_DRIFT_FIELDS")` → caller 不 catch → `async with session.begin()` 自动 rollback → `RestoreReplayReport.error = 'pass_a_drift:*'` → gate 阻断
- **不可自动修复** → 走 runbook 人工 reconcile（operator 决定：(a) 接受 archive = 旧 state → rebuild 重建；(b) 接受 LIVE = 新 state → 重做 restore 流程 + 验证 archive 完整）

---

## 6. M-class advisory lock 并发窗口（计划 §S6-8 + D2 M-class=A）

### 6.1 lock 协议

- frozen prefix: `metaedu.agent.maintenance.v1\x00`
- retention/audit 每事务取 `pg_advisory_xact_lock_shared`
- replay 事务取 `pg_advisory_xact_lock` exclusive
- 新 lock 必须在 Run / Conversation / owner / collection 锁**之前**取得

### 6.2 并发窗口事实

| 并发场景 | lock 行为 | 影响 |
|----------|----------|------|
| replay 与 retention worker 并发 | replay exclusive + retention shared **互斥** → retention blocked → replay 先完成 | replay 安全；retention 等待 |
| 多个 replay 实例并发 | 第一个取 exclusive → 后续阻塞 → 第一个完成后下一个取 lock | V1 single-replay 隐式约束 |
| replay 与 audit prune 并发 | 同上（retention/audit 都 shared → replay exclusive 互斥） | audit 等待 |
| replay 与 production scheduler 并发 | **生产 scheduler 未启动**（registry external/runtime `erase_available=False` + `scheduler_composition.py` 联合门禁） | **不可能**冲突（plan §S6-10 + §S6-7 冻结） |

### 6.3 lock 持有期间崩溃

**事实**：replay 事务 crash → `async with session.begin()` 自动 rollback → exclusive lock 自动释放 → 其他事务继续

**处置**：
- 无需人工 lock 释放
- crash 期间 partial committed = 无（lock 与 tx 同生命周期）
- 重试安全（同 tenant 重做 replay = 同 commit-graph tip → idempotent）

### 6.4 M-class writer registration

`restore_replay_executor` 在 `app.composition.s6i2_orphan_inspection.S6I2_PENDING_WRITERS` 中 pending；**V1 不在 production writer matrix 中**（plan §S6-4 + S6-7.1 三重 fail-closed）→ 与 caller 重做 replay 无冲突。

---

## 7. blocked + manual reconcile ops

### 7.1 owner_blocked_kept（local owner participant blocked=True）

**触发**：`RestoreReplayReport.owners_blocked_kept > 0`

**处置**：
1. 查 `RestoreReplayReport.verdict`：每个 blocked owner 含 `reason_code`（来自 participant outcome `block_reason`）
2. 走对应 owner 的 manual reconcile runbook（**不在本 runbook 详列**——属各 owner 单独 runbook）：
   - `workspace.core.v1` → 检查 message / part / user_state 残留 + actor 匿名化
   - `workspace.transport.v1` → 检查 workspace outbox 未 ack delivery
   - `execution.core.v1` → 检查 RunEvent payload / terminal_output / compat output 残留
   - `execution.transport.v1` → 检查 execution outbox 未 ack delivery
3. **不**重做 replay：blocked 状态保留为审计证据
4. **不**打开流量：gate 阻断 `open_allowed=False`

### 7.2 runtime_binding_evidence_unprovable

**触发**：`RestoreReplayReport.runtime_binding_evidence_unprovable > 0`（用户裁决 5 = c：archived completed runtime 缺 per-binding proof）

**处置**：
1. **不**自动重试：runtime per-binding receipt **不可重算**（`adapter_receipt_evidence` 未持久化，TD-106 P2-1 仍登记）
2. **不**伪造 receipt / blocked / acked
4. **保持服务关闭**：gate 阻断
3. 走 runbook 人工处置：operator 决定是否接受 runtime 不完整 ack + 后续人工执行 runtime eraser

### 7.3 external_verification_failed

**触发**：`RestoreReplayReport.external_verification_failed > 0`

**处置**：
1. 查 `RestoreReplayReport.verdict`：`reason_code` 携带具体 binder code（`EXTERNAL_ARCHIVE_MISSING` / `EXTERNAL_ARCHIVE_DUPLICATE` / `ARCHIVE_FACTS_TYPE_INVALID` / `external_receipt_mismatch` / `external_state_not_erased` / `external_final_scan_residual:<N>` / `external_live_row_missing` / `external_scan_provider_missing` / `external_scan_total_invalid`）
2. **不**自动重试：drift 表示 archive 与 LIVE 不一致
3. **保持服务关闭**：gate 阻断
4. 走 runbook 人工处置：
   - `external_receipt_mismatch` / `external_live_row_missing` → 检查 external adapter receipt + DB state
   - `external_state_not_erased` → 检查 adapter 是否完成 erase
   - `external_final_scan_residual:<N>` → 检查 external body 是否真正清除（可能 adapter 已发请求但实际未完成）

### 7.4 fact_drift / pass_a_drift / toctou_drift

**触发**：archive 与 LIVE 字段不一致

**处置**：
1. **不**自动重试：drift 表示 snapshot 中途 state 变化
2. **保持服务关闭**：gate 阻断
3. 走 runbook 人工处置：operator 决定接受 archive 还是 LIVE → 重建 snapshot 或重做 restore

### 7.5 owner scan residual

**触发**：`<owner>_residual:<N>`（`N > 0`）

**处置**：
1. 查具体 owner → 走各 owner manual reconcile runbook
2. **不**自动重试：residual 表示 body 未擦除
3. **保持服务关闭**：gate 阻断

---

## 8. 生产门禁登记（plan §S6-8 item 6 + R1-AC12 字面降级）

**真实 PG drill**：重放机制 + body/ref 扫描经真实 PG 验证（contract-tested）。

**无法本地执行的项**（**不**冒充已验证）：
- 真实 pg_dump / restore / 流量切换（无生产基础设施）
- 多实例 canary（无生产基础设施）
- 完整基础设施 drill（无备份保留 runbook 执行环境）

**生产负责人承接标记**：
- 完整 release drill 由生产基础设施负责人在生产环境执行
- PR-E 任务卡（plan §S6-14 item 4 排除项）依赖 PR-D 落地 → 五阶段 fail-closed 判别 + canary 测试环境限定
- 完成声明降级为 R1-AC12 字面：`"重放机制与扫描经真实 PG 验证（contract-tested 级别）"`，**不冒充已跑 restore drill`"

---

## 9. 相关事实源

- Plan [`§S6-14 post-D2 rebaseline 注解`](../../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md#L2354-L2366)
- Plan [`§S6-8 item 1..7`](../../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md#L2235-L2243)
- Plan [`§S6-7.1 冻结 三重 fail-closed`](../../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md#L2227-L2229)
- Plan [`§S6-12 / §S6-13 routing 表 + 判定方式`](../../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md#L2305-L2339)
- Plan [`§S6-15.5 settlement SUCCESS ledger 写缺口 + TD-106 方案 A 落地`](../../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md#L2422-L2424)
- Fact-audit [`§17.6 D1b merged-boundary`](../../../03-engineering-governance/04-retrospectives/r1-s6-i3-d-fact-audit.md#L840-L908)
- Fact-audit [`§17.7 D2 merged-boundary`](../../../03-engineering-governance/04-retrospectives/r1-s6-i3-d-fact-audit.md#L910-L958)
- Fact-audit [`§17.8 GOV closeout merged-boundary`](../../../03-engineering-governance/04-retrospectives/r1-s6-i3-d-fact-audit.md#L960-L1028)
- Spec [`§10 备份恢复门禁`](../../02-delivery-plans/01-specs/2026-07-27-req-041-047-r1-retention-purge-recovery.md#L248-L259)
- Spec [`§11 R1-AC12 字面降级`](../../02-delivery-plans/01-specs/2026-07-27-req-041-047-r1-retention-purge-recovery.md#L273-L274)
- D1a 实现：`packages/server-python/app/composition/s6i3_ledger_snapshot.py`
- D1b 实现：`packages/server-python/app/composition/s6i3_d_ledger_archive_sink.py`
- D2 实现：`packages/server-python/app/composition/restore_replay.py`
- PR-D orchestration：`packages/server-python/app/composition/s6i3_d_ledger_orchestration.py`
- PR-D drill test：`packages/server-python/tests/composition/test_s6i3_d_cross_layer_drill.py`
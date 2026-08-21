# R1-S6-I3 Restore-Before-Open Runbook

> 状态：Draft（S6-I3 实现期）
> 契约：Plan §R1-S6-8 item 5（body/ref 扫描）+ item 6（drill 降级声明）+ Spec §3 末段
> 负责人：R1-S6-I3 实现者 + 生产部署负责人（见"门禁负责人"段）
> 关联：s6i3_ledger_export.py（ledger 导出）+ s6i3_restore_replay.py（replay 执行器）

## 0. 范围与降级声明（必读）

- 本 runbook 覆盖**已通过 R1-S6-I3 真实 PG 验证**的 restore-before-open 流程。
- **真实 pg_dump / 恢复 / 流量开关 drill 无法在本地执行**（无生产基础设施、无备份保留 runbook 执行环境）——本 runbook 在生产首次启用前必须由生产负责人**逐项演练并签字**。
- 完成声明降级为「重放机制与扫描经真实 PG 验证（contract-tested 级别）」，**不冒充已跑 restore drill**（R1-AC12 字面降级，Plan §R1-S6-8 item 6 冻结）。
- 本 runbook 不引入新 schema / 不修改 migration 043 / 不修改 S5 状态机/锁序/写者矩阵 / 不翻转 registry capability / 不做 production scheduler wiring / 不调用 external/runtime adapter。

## 1. 恢复顺序（冻结字面）

```
[step 1] 服务保持不可对外读写（流量开关 → maintenance 模式）
   ↓
[step 2] 从独立存储导入/校验 erasure ledger 快照
   ↓
[step 3] ledger import 校验 = schema version + content_sha256 双向对账
   ↓
[step 4] replay executor 主编排（replay 已完成 + 进行中 operation）
   ↓
[step 5] S5 六 owner body/ref 终态扫描（scan_execution_body + 其他五 owner）
   ↓
[step 6] S6-I2 六类 verify 巡检（verify_inspection）
   ↓
[step 7] 失配 / orphan / 阻塞判别（owner_version / digest / external 未 ACK）
   ↓
[step 8] 全部扫描为零 + 门禁通过 → 开放流量
```

**任一阶段失败 → 保持服务关闭 + 报告 root cause + 转人工 runbook**（不静默放行）。

## 2. 详细步骤

### 2.1 服务关闭 + maintenance 模式

- 目标：恢复期间所有读写流量隔离，仅运维访问。
- 操作：
  - 切流量开关（gateway / load balancer 层）→ maintenance 模式。
  - 应用层 health-check 返回 503；保持进程运行（不重启，便于 S5/S6 状态连续）。
- 验证：合成请求 100% 命中 503；运维 admin 接口仍可达。

### 2.2 Ledger 快照导入

- 工具：`s6i3_ledger_export.export_ledger_snapshot` + `serialize_snapshot`。
- 来源：生产 DB 备份**之外**的独立归档存储（具体存储类型由生产负责人决定）。
- 格式：JSON Lines（首行 header，后续每行一个 record）；schema version = `s6i3_ledger_v1`。
- 校验：
  - header.schema == `s6i3_ledger_v1`；
  - header.content_sha256 == 实际内容 SHA-256；
  - sentinel 扫描（不出现 payload_inline / payload_ref / session_ref / reply / free_reason）。
- 失败处理：sentinel 命中 → 拒绝导入 + 转人工 runbook（疑似正文/ref 泄露）。

### 2.3 Replay executor

- 工具：`s6i3_restore_replay.run_replay_executor`。
- 输入：
  - ledger operations（来自 step 2.2 导入快照）；
  - ledger checkpoints（同上）；
  - 当前 registry owner_versions（来自 `owner_registry()`）。
- 输出：每 operation 一个 ReplayDecision（`replayed` / `in_progress_locally_cleared` / `external_blocked` / `runtime_blocked` / `skipped` / `owner_version_mismatch` / `digest_mismatch` / `unrecognized_state`）。
- 约束：
  - **不调用 external/runtime adapter**；
  - **不创建新 Tx1**；
  - **不依赖生产 scheduler**；
  - 与 retention/audit jobs 互斥（replay 期间暂停，frozen 字面）。
- 失败处理：
  - `owner_version_mismatch` → 失配 fail closed → 报告 runbook 人工处置；
  - `digest_mismatch` → digest 不一致 → fail closed → runbook 人工处置；
  - `unrecognized_state` → 未识别 state → runbook 人工处置。

### 2.4 S5 六 owner body/ref 终态扫描

- 工具：`execution_erasure_participant.scan_execution_body`（已存在）等六个 owner 扫描器。
- 范围：所有 owner（workspace.core.v1 / execution.core.v1 / workspace.transport.v1 / execution.transport.v1 / external.payload.v1 / runtime.private.v1）。
- 校验：扫描计数 == 0（无 payload_inline / payload_ref / terminal_output / compat output / context snapshot / actor 残留）。
- 失败处理：任何 owner 扫描非零 → 报告 owner_key + 行 ID（仅 ID，不含正文）→ 转人工 runbook。

### 2.5 S6-I2 六类 verify 巡检

- 工具：`s6i2_orphan_inspection.verify_inspection`。
- 巡检：tenant mismatch / digest conflict / event gap / unknown ref scheme / missing fence or owner scope / orphan transport。
- 校验：`total_findings == 0`。
- 失败处理：见 findings → 转人工 runbook（每个 finding 都有 owner_key / table / row_id 字面记录，不暴露正文/ref）。

### 2.6 失配 / orphan / 阻塞判别

- 来源：
  - replay executor 的 `registry_owner_version_mismatches`；
  - replay executor 的 `digest_mismatch_count`；
  - S6-I2 verify findings；
  - S5 body scan 计数。
- 全部清零 = 通过；任一非零 = 失败。
- 失败处理：**保持服务关闭 + 报告全部非零项**。

### 2.7 开放流量

- 全部判别通过 → 切流量开关 → production 模式 → health-check 200 → 流量恢复。
- 操作者：生产运维 + S6 负责人双签字（frozen 流程）。
- 后续：进入正常 retention/audit 周期。

## 3. 失配处置（runbook 人工分支）

| 失配类型 | 处置 |
|----------|------|
| owner_version_mismatch | 比对账本 owner_version 与 registry snapshot；若账本为旧版本 → 升级 registry 后重试 replay；若账本为新版本 → 检查 rollback 痕迹 → 转 R1 负责人 |
| digest_mismatch | 三 digest（checkpoint/intent/ack）任一不一致 → 与生产 receipt 备份交叉比对 → 若仍不一致 → 转 R1 负责人（疑似账本损坏） |
| external 未 ACK | 写入 `blocked + reconcile` → 重启 adapter 或走 reconcile 路径；**不冒充已 erase** |
| runtime 未 ACK | 同上 |
| body scan 非零 | 列出 owner_key + 行 ID → 比对 production DB 终态扫描 → 决定手动清理路径 |

## 4. 门禁负责人

- 生产首次启用前：生产部署负责人 + R1-S6-I3 实现者**联合演练并签字**。
- 后续每次恢复：生产部署负责人按 runbook 操作；任何判别异常 → 转 R1 负责人 + 研发 on-call。
- runbook 升级路径：与 R1 维护批次协同（与 R1-S5/S6 维护窗口同步）。

## 5. 已知缺口（生产门禁登记）

- 真实 pg_dump / 恢复 / 流量切换 drill 无法在本地执行 → **生产首次启用前必须由生产部署负责人演练并签字**。
- replay executor 与 retention/audit jobs 互斥 → 通过单进程标志或外部协调器承载（frozen 字面）；具体协调机制由生产环境决定。
- 跨租户 / actor / 伪造 ACK 拒写：现有 `S6-I2` verify tenant mismatch 巡检 + S5 transport scope owner scope mismatch + S4-F 伪造 ACK 拒写 + R1-S5-I1 无 permission hold 拒写（统一在 step 2.5 覆盖）。
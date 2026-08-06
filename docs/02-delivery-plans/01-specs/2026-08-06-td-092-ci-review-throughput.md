# TD-092 CI 反馈周期与复审收敛治理 Spec

## 背景

PR #530 的 Backend required check 用时 `10m22s`，其中全量 pytest 用时 `9m06s`。选择器判定原因是 `database-migration:alembic/versions/040_transport_external_scope.py`。选择器比较整个 PR 相对 base 的净差异，因此 migration 一旦进入 PR，后续修订提交即使只修改测试或文档，也会持续触发 full。

同一 PR 同时承载 migration、transport ledger、锁、backfill、verify、CLI 和大型测试文件，共新增约 6021 行，导致复审以串行 finding 的方式逐层发现契约遗漏，最终需要 11 轮返修。

## 目标

1. Draft 高风险 PR 的中间修订使用可审计的风险定向套件，目标 Backend 反馈时间不超过 3 分钟；不降低最终 full 门禁。
2. Draft 只产生非 required 的 `Backend iteration`；高风险 PR 在 Ready 状态的最新 HEAD 才产生 required `Backend` 并运行完整 hermetic Backend，Ready 后任何代码推送重新触发 full。
3. main push、schedule、workflow_dispatch、未知路径和 CI/选择器/共享基础设施修改继续 full fail-closed。
4. 复审由“串行找一个修一个”改为同一 HEAD 的数据/并发/测试运维三路并行审查，再统一按根因族返修。
5. 高风险 Slice 按单一主要风险域拆分 PR，避免 schema、writer、participant、CLI/fault 混在一个实现 PR。

## 非目标

- 不减少测试、删除测试、增加 skip/xfail 或改变 required check 名称。
- 不在本任务引入 pytest-xdist；共享 PostgreSQL 的并行安全另立测量任务。
- 不修改 R1 业务逻辑、migration 034-040、erase_available 或 scheduler。
- 不允许 Draft risk-targeted 结果作为高风险 PR 的最终合并证据。

## CI 策略

### 状态分层

| PR 状态 | 普通修改 | 可迭代高风险修改 | 始终全量修改 |
|---|---|---|---|
| Draft | targeted | risk-targeted | full |
| Ready | targeted | full | full |
| main/schedule/manual | full | full | full |

可迭代高风险范围包含 migration、`app/composition` Agent 组合根、`agent_workspace`、`agent_execution` 及其直接测试；始终全量范围包含 CI/workflow、选择器、shared、identity/security、全局 fixture、依赖锁和未知路径。

### Risk-targeted 套件

Risk-targeted 采用稳定 Agent core 文件集，并按 transport、erasure、migration 追加专项：

- S3-C writer fence、S3-E no-bypass 和 late-write 核心测试；
- Agent control-plane 的 run/turn/output bridge、writer fence 与竞态测试；
- Agent execution 的 coordinator/state/runtime/snapshot 测试；
- `agent_workspace` 与 Direct RAG compatibility；
- 按改动路径追加 transport、erasure 或 migration/schema/roundtrip 专项；
- `tests/shared/test_health.py` 与数据库不可用 smoke。

该套件只服务 Draft 反馈，不是最终合并门禁。risk-targeted 保留 Ruff、数据库初始化与风险定向 pytest；mypy baseline 由 pre-push 和 Ready full 承担。普通 targeted、Draft fail-closed full 与最终 full 仍执行 mypy；最终 full 仍执行 `pytest -m "not external_network"`。

### Draft/Ready 事件

workflow 必须监听 `opened`、`synchronize`、`reopened`、`ready_for_review`、`converted_to_draft`。Draft 返修期间保持 Draft；完成返修后转 Ready，使用最新 HEAD 重新执行 full。

Draft 与 Ready 不复用同一 check context：Draft job 名为 `Backend iteration`，Ready/main job 名为 required `Backend`。这样同一 SHA 上旧的 Draft success 不能冒充 Ready 最终门禁；PR 转 Ready 后必须等待新的 `Backend` check。

## 复审策略

### 复审包

PR 描述必须提供：不变量、状态真值表、来源/类型裁决矩阵、锁序图、失败/重试/幂等矩阵、测试到不变量的映射、明确非目标和当前 HEAD SHA。

### 并行审查面

首轮复审在同一 HEAD 并行覆盖：

1. 数据、migration、状态机、tenant 与证据完整性；
2. 锁序、事务边界、幂等、lease、故障和 late write；
3. 测试判别力、CLI 退出语义、运维操作、文档和交接事实源。

各面先完整列出 findings，协调者去重后按根因族形成一批返修任务。单个反例修复必须横向审计 selector、writer、heal、verify 和所有等价入口。

### 升级规则

- 连续两轮出现新的 P1，暂停补丁式返修，先做架构复盘或拆分 PR。
- 新增源文件超过 1000 行不得在功能 PR 中新增例外；测试按不变量拆分。
- 高风险实现 PR 默认只承载一个主要风险域。

## 验收

- 选择器对 Draft/Ready、Agent、migration、始终 full、未知路径均有工程测试。
- 临时 Draft 探针证明 Agent 高风险修改走 risk-targeted，且 Backend wall time <= 3 分钟。
- 探针转 Ready 后，最新 HEAD 走 full；Ready 后代码推送再次走 full。
- main push、schedule/manual 和 selector 自身修改继续 full。
- 全量测试数量不减少，required checks 不变，docs gate、ruff、mypy、diff-check 通过。
- 首个后续高风险 Slice 使用复审包和三路并行首轮；目标 3 轮内完成，连续两轮新 P1 时触发升级规则。

# TD-032 源码文件行数基线

本文件是 TD-032 治理超大源码文件的**行数事实源**。与 `technical-debt.md#td-032` 证据段
互为镜像：本文件给"清单 + 状态 + 拆分说明"，技术债总账给"任务卡 + 完成标准 + 验证
方式"。每切片交付后必须回写本文件。

## 维护规则

- 扫描命令（DOC-042 脚本化后以 ``scripts/scan-source-sizes`` 为准）：

  ```bash
  # 脚本化扫描（推荐）
  scripts/scan-source-sizes --threshold 500
  scripts/scan-source-sizes --diff           # 与上次基线对比
  scripts/scan-source-sizes --refresh        # 刷新 JSON 基线 + Markdown 行数列
  ```

  历史手工命令（仅供参考，已被脚本替代）：

  ```bash
  rg --files -0 packages scripts tests \
    -g '*.py' -g '*.ts' -g '*.tsx' -g '*.vue' -g '*.css' -g '*.scss' \
    -g '!**/.venv/**' -g '!**/uploads/**' -g '!**/node_modules/**' -g '!**/dist/**' \
    | xargs -0 wc -l | sort -nr | head -40
  ```

- 4 档分组：>1000 / >500 / 500 附近 / 合规样例。
- 每行至少有 1 句「例外 / 拆分说明」；例外也要写「后续切片计划」，不允许长期 `🔵`。
- 每切片交付后必须回写本文件：状态变化 / 行数变化 / 新增文件；不允许连续 2 个复盘周期
  无更新。
- 行数与 `technical-debt.md#td-032` 证据段如有差异，以本文件最近一次扫描为准，并在
  末尾「扫描历史」段记录。

## 文件清单

### >1000 行（必须明确例外或拆分计划）

| 文件 | 行数 | 状态 | 例外 / 拆分说明 |
|------|------|------|-----------------|
| `packages/server-python/app/composition/external_ref_erasure_participant.py` | 1072 | 🟢 已登记（待拆分） | REQ-041/047 R1-S4-E-B2 ExternalPayloadErasureParticipant：双事务协议（Tx1 checkpoint erasing + attempt + intent digest / 无锁 adapter / Tx2 精确重验 + erased + receipt 再清源 ref）+ 3 source ref 清除（RunEvent 经 041 guard / 两 outbox 转 suppressed）+ E-1a source 已 NULL 历史兼容 + E-3a 失败矩阵 + E-3b blocked/unknown 查询 + 有证据 reconcile + ACK/fencing/重放复用基类，单文件聚合至 1072 行超 1000 硬限制。本次只登记新增风险，不在 R1-S4-E-B2 中拆 participant。后续应按职责切片：(a) 双事务协议主编排（Tx1/Tx2 + adapter 调用）；(b) source ref 清除 + E-1/E-1a 身份重验；(c) E-3b 查询 + reconcile；(d) ExternalRefScan/Summary/Row dataclass + intent/receipt digest 构造；目标单文件 ≤500 行。 |
| `packages/server-python/tests/composition/test_s4eb2_external_erasure.py` | 1214 | 🟢 已登记（待拆分） | REQ-041/047 R1-S4-E-B2 测试矩阵：E-1b 三 source ref 清除 + E-1a source 已 NULL 历史兼容 + E-1 绑定冲突 fail closed + E-2 双事务协议（Tx1 checkpoint erasing / Tx2 精确重验 attempt/intent/digest fail closed）+ E-2b idempotency key 稳定性 + E-3a 失败矩阵 5 行（success/not-sent/timeout/unknown/failed）+ E-3b 查询/reconcile 4 例 + B2 互操作（transport 已 suppressed no-op / 非 registered 行不消费）+ registry fail closed，单文件聚合至 1214 行超 1000 硬限制。本次只登记新增风险，不在 R1-S4-E-B2 中拆测试。后续应按测试主题拆成聚焦文件：(a) 三 source 清除 + E-1a/E-1 冲突；(b) E-2 双事务 + E-2a 重验；(c) E-3a 矩阵；(d) E-3b 查询/reconcile；(e) B2 互操作 + registry gate；目标单文件 ≤500 行。 |
| `packages/server-python/app/contexts/agent_execution/infrastructure/execution_repository.py` | 1018 | 🟢 已登记（待拆分） | REQ-041/047 R1-S4-C PR-A producer propagation 落地：`commit_terminal` 增 `producer_purge_revision` 参数并写入 execution outbox（`conversation_id` + `producer_purge_revision`），单文件从 999 增至 1008 行超 1000 硬限制；round-1 复审返修补 COMPLETED 非 NULL epoch 守卫，1008→1018。本次只登记新增风险，不在 PR-A 中拆 repository。后续应按职责切片：(a) Run 生命周期 writer（create/start/transition/resume/mark_resume/commit_terminal）；(b) event 追加/ingest；(c) catalog/binding 查询；(d) outbox/inbox 生产者；目标单文件 ≤500 行。 |
| `packages/server-python/tests/contexts/knowledge/test_ai_chat_service.py` | 1167 | 🟢 已登记（待拆分） | REQ-016 / REQ-018 合并后该测试文件超过 1000 行硬限制；本次只登记新增风险，不在视觉主题任务中拆测试。后续应按 AI Chat service 核心行为、context packer / diagnostics、graph edge recall、query understanding 等测试主题拆成多个聚焦文件，目标单文件 ≤500 行。 |
| `packages/server-python/app/contexts/knowledge/application/ai_chat_service.py` | 1016 | 🟢 已登记（待拆分） | REQ-052 Task 7 tool calling 编排 + REQ-056 Task 2 request-bound QueryService + REQ-056 Task 3 catalog_id 双键路由叠加至 1016 行（961 + 55）。本次只登记新增风险，不在本任务中拆 service。后续应按职责切片：(a) tool 声明 + tool_call handler；(b) retrieval/fusion/packing；(c) hydration/document-source；(d) chat 主流程骨架；目标单文件 ≤500 行。 |
| `packages/server-python/tests/real_world/req056_business_samples.py` | 1099 | 🟢 已登记（待拆分） | REQ-056 Task 5 落地真实业务样例（10 个 e2e 验收）。本文件聚合了"成功/空结果/权限/字段缺失/企业过滤/多 catalog 双键"6 类场景的端到端测试，每个测试用例都依赖较厚的 fixture setup / assert 段，所以单文件超 1000 行硬限制。本任务只登记新增风险，不在本任务拆测试。后续可按"成功样例 / 空结果样例 / 权限样例 / 多 catalog 路由样例"拆分，目标单文件 ≤500 行。 |
| `packages/server-python/tests/composition/test_agent_erasure_schema.py` | 1637 | 🟢 已登记（待拆分） | REQ-041/047 R1-S1 schema 基座 + 三轮复审反例 + round4 复审 F1/F2/F3/F5/F10 变异杀手 + round5 复审 P1 状态机 4×4 表驱动 + P2.4 backfill 失败恢复契约反例叠加，单文件聚合至 1637 行超硬限制。本次只登记新增风险，不在 R1-S1 中拆测试。后续应按测试主题拆成聚焦文件：(a) fence CRUD/CAS/版本守卫/单调守卫/状态机转移表/并发唯一性；(b) tombstone（Message/Conversation/Run/CompatibilityOutput/outbox 正负分支）；(c) purge operation/checkpoint snapshot 绑定/registry drift；(d) backfill 游标/幂等/参数守卫/failures 上界/失败恢复契约/CLI 退出码；目标单文件 ≤500 行。 |
| `packages/server-python/app/contexts/agent_workspace/infrastructure/bridge_repository.py` | 1006 | 🟢 已登记（待拆分） | REQ-041/047 R1-S2 S2-A Codex 复审返修叠加：正文 writer fence 注入（`project_assistant_message`）、suppressed tombstone `allow_purge_fenced` 贯穿、受控 suppression reason code 白名单，单文件聚合至 1006 行超 1000 硬限制。本次只登记新增风险，不在 R1-S2 中拆 repository。后续应按职责切片：(a) turn outbox / turn event 解析与校验；(b) assistant output 投影（`project_assistant_message` / `project_suppressed_output` / output receipt / projection state）；(c) conversation 锁与 purge fence（`_lock_projection_conversation` / writer fence 协作）；目标单文件 ≤500 行。 |
| `packages/server-python/tests/contexts/agent_control_plane/test_s2de_workspace_erasure.py` | 1961 | 🟢 已登记（待拆分） | REQ-041/047 R1-S2 S2-D/E round-2/round-3 复审返修叠加：6 场景表驱动 operation/checkpoint fencing 反例（cross-conversation / purge_revision / lease_epoch / hold_revision / operation revision / owner_version / capability_digest）+ erased fence pending checkpoint 恢复 + erased + 非零 scan fail closed + erased repair 终态 operation fail closed + scan archived_by/deleted_by + 已 redacted author_id 残留清除 + DB 时钟 + now 参数不被接受 + tenant 谓词 + 生产 fail-fast + 版本契约 + blocked 重试状态一致 + round-4 legal-hold revision CAS / legal-hold purge_state 投影 / record_blocked reason change bump / erased ACKed digest 验证 / erased blocked->running+三方一致 / agent author digest / V1 版本冻结，单文件聚合至 1961 行超 1000 硬限制。本次只登记新增风险，不在 R1-S2 中拆测试。后续应按测试主题拆成聚焦文件：(a) P1-1 purge 前置反例 + blocked 重试状态一致；(b) P1-2 HMAC actor digest + 版本契约 + 强度校验；(c) P1-3 operation/checkpoint fencing 表驱动反例 + archived_by/deleted_by 清除；(d) P1-4 ACK CAS + erased fence 恢复 + 非零 scan/终态 fail closed；(e) P1-5 blocked 可靠提交 / 重试 / legal hold + scan 完整性 + author_id 残留清除；(f) P2 DB 时钟 / now 不被接受 / tenant 谓词 + 主路径 / 幂等 / fail-closed；目标单文件 ≤500 行。 |
| `packages/server-python/app/contexts/agent_workspace/infrastructure/workspace_erasure_participant.py` | 1319 | 🟢 已登记（待拆分） | REQ-041/047 R1-S2 S2-D/E round-2/round-3 复审返修叠加：正文清除原语 + final body scan + ACK fencing（operation revision CAS / lease / hold / registry drift / checkpoint owner_version+capability_digest）+ erased fence 恢复 + operation 投影/revision bump + actor HMAC digest（版本契约 + 强度校验）+ round-4 legal-hold revision CAS / legal-hold purge_state 投影 / record_blocked reason change bump / erased ACKed digest 验证 + blocked->running 修复 / erased 三方一致 / agent author digest 全类型 / V1 版本冻结，单文件聚合至 1319 行超 1000 硬限制。本次只登记新增风险，不在 R1-S2 中拆 participant。后续应按职责切片：(a) scan_body + WorkspaceBodyScan/Summary/Outcome dataclass；(b) erase_conversation_body 主编排 + 前置/hold/blocked 路径；(c) operation/checkpoint fencing 加载与 CAS（_load_verified_operation / _load_verified_checkpoint / _mark_operation_running / _record_blocked / _ack_owner_checkpoint / _repair_checkpoint_if_pending）；(d) 清除动作（title / actor 匿名化 / message redact / part / user_state 删除）+ actor digest + secret 校验；目标单文件 ≤500 行。 |
| `packages/server-python/app/contexts/agent_execution/infrastructure/execution_erasure_participant.py` | 1388 | 🟢 已登记（待拆分） | REQ-041/047 R1-S3-D ExecutionErasureParticipant：execution.core.v1 正文清除（terminal output suppress + terminal code/reason 裁剪 + context snapshot 清除 + compatibility output 清除 + RunEvent payload tombstone + actor 匿名化）+ final body scan（无条件覆盖 inline + ref + suppressed envelope + terminal_reason/code）+ ACK fencing（operation/checkpoint CAS + erased 幂等重放 + pending checkpoint repair）+ blocked 前置（nonterminal / external payload_ref / runtime binding ref 直查 / legal hold）+ clock_timestamp + 共享 actor_digest / suppression_reasons helper。**round-1 复审返修**（2026-08-03，7 P1 + 2 P2）：新增 `ExecutionErasureSummary` 真实清除计数驱动 ACK digest、operation FOR UPDATE + 可运行状态白名单、`_record_blocked` 接 conversation/scan 投影 purge_state 与 checkpoint_digest、清除动作返回受影响行数、scan 不按 publish_state 跳过 suppressed envelope（1107→1344）。**round-3 复审返修**（2026-08-03，P1）：`_record_blocked` 先完成 checkpoint 白名单裁决再改任何实体（原子 fail closed，防 ValueError 后 commit 造成部分复活），1344→1388（+44，含注释）。后续应按职责切片：(a) scan_execution_body + ExecutionBodyScan dataclass；(b) erase_execution_body 主编排 + 前置/blocked 路径；(c) fencing helpers（_load_verified_operation / _load_verified_checkpoint / _mark_operation_running / _record_blocked / _ack_owner_checkpoint / _repair_checkpoint_if_pending）；(d) 清除动作（terminal / context / compatibility / event / actor）；(e) ExecutionErasureSummary + ACK digest 构造；目标单文件 ≤500 行。 |
| `packages/web/src/assets/css/main.css` | 9 | 🟢 已拆分 | TD-033 完成（[PR #103](https://github.com/MarkDanile/MetaEduBase/pull/103) / merge `25ca165`）：原 1343 行单文件拆为入口 `main.css`（9 行 `@import` 聚合）+ 8 个模块文件：`tokens.css`（119 行 `@theme` token） / `themes.css`（256 行 4 主题变量） / `base.css`（35 行 `@layer base` reset） / `components.css`（281 行 `ui-*` + `liquid-card*` + `sidebar-shell` + liquid `ui-panel` 覆盖） / `compat-liquid.css`（313 行 `liquid-input/btn/tag/dialog` + Notion 主题 `liquid-*` 覆盖） / `animations.css`（86 行 `@keyframes` + `stagger-*` + `liquid-rise` + `reduced-motion`） / `markdown.css`（214 行 `.markdown-body` + `content-bg` + `mesh-bg` + `wet-line`） / `toast.css`（52 行 `.toast-container` + `.toast-item`）；全部 ≤500 行；以 `pnpm typecheck / lint / build` 退出码 0 + `git diff --check` 退出码 0 为依据（Vite 产物 CSS diff / hash 未做机械对比，"build output identical" 仅基于 import 顺序与级联分析推断，详见 DOC-045） |
| `packages/web/src/views/skill-registry/SkillListView.vue` | 1104 | 🟢 已登记（待拆分） | REQ-045 Task 4 最小管理 UI 单文件聚合（列表 + 注册导入 + 启停 + 版本 + 删除 + 审计分页 + 试运行），超过 1000 行硬限制。本次只登记新增风险，不在 REQ-045 closeout 中拆视图。后续应按职责切片：(a) 注册 / 导入模板 modal；(b) 审计查询 drawer；(c) 试运行面板；(d) 版本切换 / 删除确认；目标单文件 ≤500 行。 |
| `scripts/engineering/check_engineering_docs.py` | 131 | 🟢 已拆分 | 切片 2 已合并 ([PR #93](https://github.com/MarkDanile/MetaEduBase/pull/93) / merge `7e468fb`)：原 1003 行单文件拆为入口主文件 72 行 + 8 个聚焦 `checks/*.py` 模块（38-233 行）+ `checks/__init__.py` 注册表 `KNOWN_CHECKS`；入口脚本 `scripts/check-engineering-docs` (17 行 `runpy.run_path`) 不动；16 个 pytest 行为零变化 |
| `scripts/validate_req024_p2_real_validation.py` | 23 | 🟢 已拆分 | TD-032 slice 8 已合并 ([PR #373](https://github.com/MarkDanile/MetaEduBase/pull/373))：原 1955 行单文件（REQ-024 起算 ~600 → REQ-026/028/030/031/032/033/034 长链叠加至 1955）拆为薄入口 23 行 + `scripts/rag_validation/` 包 9 文件（`__init__.py` 9 / `models.py` 119 / `loader.py` 86 / `coverage.py` 305 / `runner.py` 374 / `report.py` 397 / `report_quality.py` 196 / `report_chain.py` 457 / `main.py` 142）；全部 ≤500 行；调用路径 `python scripts/validate_req024_p2_real_validation.py ...` 不变（`run_req027_validation.py` subprocess 引用未动）；零业务逻辑变化，dry-run 同输入下新 render 路径输出与拆分前 byte-identical（喂入拆分前 ScenarioRun JSON 经新 `_render_report` 重渲染，除 db_url mask 输入串外完全一致） |

| `packages/server-python/app/composition/agent_control_plane.py` | 1086 | 🟢 已登记（待拆分） | REQ-041/047 R1-S4-C PR-B 批次3 unknown/stale 双事务协议（Tx1 inbox rejected + tombstone 证据 + ledger + 投影重算、Tx2 turn/output claim-CAS 终态化 + decision 四元 + 重放三分支 + read_fence_state + data_anomaly fail-closed）叠加至 1086 行超 1000 硬限制。本次只登记新增风险，不在 PR-B 中拆协调器。后续应按职责切片：(a) ConversationExecutionCoordinator（consume/start/submit 编排）独立文件；(b) AgentBridgeDispatcher（claim/ACK/failure/Tx2 终态）独立文件；(c) epoch 分类 / verdict / outcome dataclass 独立模块；(d) guard / lock key helper；目标单文件 ≤500 行。 |
| `packages/server-python/tests/composition/test_s4da_transport_participant_matrix.py` | 1759 | 🟢 已登记（待拆分） | REQ-041/047 R1-S4-D-A transport participant 对称矩阵（workspace/execution 两侧参数化：outbox 正文事实谓词 / cancelled 终态证据保留 / payload_ref only / inbox 三态矩阵 / Run 维度只读判定 / 残留→blocked 反向判别 / ACK 重放 fencing / capability gate 零变更 + tenant 种子 fixture + 测试内临时激活 registry fixture）聚合至 1333 行超 1000 硬限制（三面首轮 5 根因族返修补 8 用例叠加）。**R1-S4-E-A ref tombstone**（2026-08-10）：`test_outbox_payload_ref_only_cleared` 迁移为 `test_outbox_payload_ref_only_blocked_zero_change`（五方零变更 + operation/checkpoint/Conversation blocked 三方一致）+ 新增 `test_mixed_inline_and_ref_whole_op_blocked`（receipt-before-clear 整次 blocked）+ `test_ref_bearing_blocked_mutation_old_clear_revived`（mutation kill），1333→1759。本次只登记新增风险，不在 S4-E-A 中拆测试。后续应按测试主题拆成聚焦文件：(a) outbox scan/清除谓词（含 cancelled/payload_ref）；(b) inbox 三态矩阵；(c) ACK 重放 + fencing + gate；(d) 残留→blocked 反向判别；(e) 种子/tenant fixture 共享；目标单文件 ≤500 行。 |

| `packages/server-python/app/contexts/agent_execution/infrastructure/models.py` | 1005 | 🟢 已登记（待拆分）
| `packages/server-python/tests/composition/test_agent_transport_backfill_m4.py` | 1067 | 🟢 已登记（待拆分）
| `packages/server-python/app/composition/agent_transport_backfill.py` | 1098 | 🟢 已登记（待拆分） | REQ-041/047 R1-S4-B backfill 主模块（扫描/discovery + 源解析 + 冲突/epoch/external 登记 + 五维 verify + CLI/runner），三轮独立复核返修（#1-#6 / discovery / 锁序 / batch interval）聚合至 1098 行超 1000 硬限制。本次只登记新增风险，不在 R1-S4-B 中拆模块。后续应按职责切片：(a) 扫描/discovery 批次选择；(b) 源解析与冲突登记；(c) verify 五维；(d) CLI/runner（独立 `main.py`）；目标单文件 ≤500 行。 | | REQ-041/047 R1-S4-B M4 并发/中断/全 ref-bearing + 三轮独立复核真实反例（P1-1 ref / P2-2 投影 owner / P2-3 批次边界 / #1 饥饿 / #2 ref_value / #3 多表重扫 / #4 冲突 / #5 投影漂移+零 issue / #6 mismatch / 第三轮 #2 非扫描冲突 + CLI 退出码 0/1/2）单文件聚合至 1067 行超 1000 硬限制。本次只登记新增风险，不在 R1-S4-B 中拆测试。后续应按测试主题拆成聚焦文件：(a) 并发集合锁 / 中断恢复 / 幂等；(b) 冲突登记 （A≠B / 跨 tenant / mismatch / ref_value）；(c) verify 各维反例；(d) CLI 退出码契约；目标单文件 ≤500 行。 | | REQ-041/047 R1-S4-B migration 040 落地：`ExecutionOutboxModel`/`ExecutionInboxModel` 各加 3 个 owner scope 列（`conversation_id`/`producer_purge_revision`/`scope_reconcile_state`）+ inbox 2 个 receipt_tombstone 列（state/digest），单文件聚合至 1005 行（979 + 26）超 1000 硬限制。本次只登记新增风险，不在 R1-S4-B 中拆 ORM models。后续应按上下文内聚切片（如按聚合拆 `run.py`/`run_event.py`/`outbox_inbox.py`/`runtime.py` 等模型模块），目标单文件 ≤500 行。 |
| `packages/server-python/app/composition/transport_erasure_participant.py` | 1033 | 🟢 已登记（待拆分） | REQ-041/047 R1-S4-E-A ref tombstone（E-0a）：transport participant 共享基类新增 `count_ref_bearing_outbox_rows` 抽象 + `erase_transport_owner` 内 ref-bearing 前置 blocked（`purge_owner_unavailable`，fence 保持 active），单文件从 969 增至 1033 行超 1000 硬限制。本次只登记新增风险，不在 S4-E-A 中拆 participant（共享基类承担 ACK/fencing/锁序/blocked 全管道，重构会触碰已激活两 owner）。后续应按职责切片：(a) scan/erase 抽象 + TransportBodyScan/Outcome dataclass；(b) erase_transport_owner 主编排 + 前置/blocked 路径；(c) fencing helpers（_load_verified_operation / _load_verified_checkpoint / _mark_operation_running / _record_blocked / _ack_owner_checkpoint / _repair_checkpoint_if_pending）；目标单文件 ≤500 行。 |

### >500 行业务 / 工程源码

| 文件 | 行数 | 状态 | 例外 / 拆分说明 |
|------|------|------|-----------------|
| `packages/server-python/app/contexts/document/application/tasks.py` | 0 (0) → tasks/ 包 1000 行 | 🟢 已拆分 | 切片 3 已合并 ([PR #94](https://github.com/MarkDanile/MetaEduBase/pull/94) / merge `5beb938`)：原 929 行单文件拆为 `tasks/` 包（9 文件，27-217 行/个）：`__init__.py` re-export 6 task + 2 helper；`pipeline_guard.py`（53 行）+ `extract_template_prompts.py`（88 行）+ 6 个 task 子文件（`parse.py` 138 / `chunk.py` 160 / `embed.py` 145 / `index.py` 94 / `extract_template.py` 217 / `extract_knowledge_graph.py` 178）；所有子文件 ≤500 行；`@shared_task(name=...)` 10 个名字全部 byte-equivalent；`app/shared/tasks/lifecycle.py`（TD-005 产物）未动；`app/contexts/document/tasks.py` Celery autodiscover 代理未动；55 个 pytest 聚焦测试 0 改动通过 |
| `packages/web/src/views/database/DatabaseView.vue` | 320 | 🟢 已拆分 | 切片 4 已合并 ([PR #95](https://github.com/MarkDanile/MetaEduBase/pull/95) / merge `d4d2720`)：原 701 行单文件拆为 `views/database/` 包 7 文件：`DatabaseView.vue` 320 行（主入口：顶层 state + 9 个 Vue Query 编排 + 编排函数 + 6 个子组件标签 + 3 个对话框）；6 个聚焦子组件 `DatasetListPanel.vue` 132 / `KgOverviewPanel.vue` 52 / `DatasetDetailMetaBar.vue` 40 / `PipelineStatusPanel.vue` 101 / `DatasetTabsPanel.vue` 139 / `UploadDatasetDialog.vue` 116（每个 ≤200 行）；所有 `ui-*` 共享类 / `var(--*)` token / 4 主题视觉表现 byte-equivalent；`v-model` 改 `:value + @input` 显式 emit 链避免 prop mutation；`router.ts:37` lazy import 仍解析；`queries.ts` 9 个 composable 不动 |
| `packages/server-python/app/contexts/structured_data/application/tasks.py` | 0 (0) → tasks/ 包 746 行 | 🟢 已拆分 | 切片 3 已合并 ([PR #94](https://github.com/MarkDanile/MetaEduBase/pull/94) / merge `5beb938`)：原 671 行单文件拆为 `tasks/` 包（5 文件，23-282 行/个）：`__init__.py` re-export 4 task + 4 个 task 子文件（`ds_parse.py` 118 / `ds_embed.py` 149 / `ds_extract_kg.py` 282 / `ds_cross_dataset_edges.py` 174）；所有子文件 ≤500 行；`@shared_task(name=...)` 4 个名字全部 byte-equivalent；`app/shared/tasks/lifecycle.py` 未动；`app/contexts/structured_data/tasks.py` Celery autodiscover 代理未动 |
| `packages/web/src/views/admin/TemplateModal.vue` | 333 | 🟢 已拆分 | 切片 4 已合并 ([PR #95](https://github.com/MarkDanile/MetaEduBase/pull/95) / merge `d4d2720`)：原 665 行单文件拆为 `views/admin/` 包 3 文件：`TemplateModal.vue` 333 行（主入口：dialog 壳 + header/footer + 顶层 state + resetForm/handleSave/handleClose + scoped 壳样式）；2 个聚焦子组件 `TemplateFormFields.vue` 255 / `TemplateAiPanel.vue` 207（每个 ≤260 行）；`v-model` 改 `:value + @input` 显式 emit 链；`TemplateListView.vue:71, 95` 显式 import `./TemplateModal.vue` 仍解析；`FieldItem.vue` 不动；`regenerateAI` + `handleFileSelect` + `ensureIds` 全部迁到 `TemplateAiPanel` 内部 |

### 500 行附近高风险候选

| 文件 | 行数 | 状态 | 例外 / 拆分说明 |
|------|------|------|-----------------|
| `packages/server-python/app/contexts/document/interfaces/api/router.py` | 29 | 🟢 已拆分 | 切片 5 已合并 ([PR #96](https://github.com/MarkDanile/MetaEduBase/pull/96) / merge `4b03064`)：原 494 行单文件拆为 5 个聚焦子 router 文件（位于 `interfaces/api/` 同目录）：`router.py` 29 行（主入口：4 行 `router.include_router(X_router)` + 顶层 re-export `parse_document` 让 `patch("app.contexts.document.interfaces.api.router.parse_document")` 仍工作，tests/conftest.py:24）；`folders.py` 123 行（5 endpoint + 2 helper `_folder_row_to_dto` / `_build_tree`）；`files.py` 231 行（6 endpoint + 1 helper `_file_row_to_dto` + reinitialize_file 函数内 `from sqlalchemy import text` 保持原位）；`chunks.py` 43 行（1 endpoint）；`tasks.py` 121 行（2 endpoint + `_TASK_TYPE_LABELS` 常量 + list_file_tasks / retry_file_tasks 函数内 import 保持原位）；13 个 `@router.*` endpoint 字符串 / HTTP method / path / response_model / status_code 全部 byte-equivalent；`app/main.py:6` 的 `from app.contexts.document.interfaces.api.router import router as document_router` 仍解析；`pytest tests/shared/ tests/contexts/document/ tests/contexts/structured_data/ -q` 115 passed；`ruff check` All checks passed!；**pre-existing 重复路由**（`router.py:402` ≡ `task_router.py:36` 都注册 `GET /files/{file_id}/tasks` + `router.py:442` ≡ `task_router.py:53` 都注册 `POST /files/{file_id}/retry`）**不**在本切片处理；已登记为 `DOC-041` 候选 |
| `packages/web/src/views/resource/ResourceLibraryView.vue` | 286 | 🟢 已拆分 | 切片 6 已合并 ([PR #97](https://github.com/MarkDanile/MetaEduBase/pull/97) / merge `6728151`)：原 490 行单文件拆为 `views/resource/` 包 4 文件：`ResourceLibraryView.vue` 286 行（主入口：19 ref + 7 编排函数 + 3 子组件标签 + 删除文件 ConfirmDialog + `flatFolders` computed + `onMounted`）；3 个聚焦子组件 `FolderTreePanel.vue` 142 / `FileListPanel.vue` 160 / `UploadOptionsDialog.vue` 51（每个 ≤200 行）；`fileInput` ref 在 `FileListPanel` 内部持有（沿用切片 4 模式）；emit 名 kebab-case 化（`update:new-folder-name` / `update:inline-renaming-name` / `update:filter-status` / `update:doc-type`）匹配 `vue/v-on-event-hyphenation` lint 规则；7 个 `documentApi.*` 调用（listFolders / createFolder / updateFolder / deleteFolder / listFiles / uploadFile / deleteFile）仍由 ResourceLibraryView 编排；`router.ts:27` lazy import 仍解析；`pnpm typecheck / lint / build` 3 项全过 |
| `packages/web/src/views/resource/FileDetailView.vue` | 214 | 🟢 已拆分 | 切片 7 已合并 ([PR #98](https://github.com/MarkDanile/MetaEduBase/pull/98) / merge `3e7f827`)：原 416 行单文件拆为 `views/resource/` 包 4 文件：`FileDetailView.vue` 181 行（主入口：顶层 state + 5 Vue Query 编排 + 3 mutation + 3 子组件标签 + 删除/返回 action + watch(polling)）；3 个聚焦子组件 `FileMetaBar.vue` 41 / `FileDetailPipelineStatusPanel.vue` 97 / `FileTabsPanel.vue` 171（每个 ≤200 行）；所有 helper（statusLabel / statusTagClass / formatSize / templateFieldLabel / getFieldLabel + stepIcon/stepBgClass 6 helper）迁到对应子组件内部；emit 名 kebab-case 化（update:active-tab / node-click）；`router.ts:32` lazy import 仍解析；`views/resource/queries.ts` 8 composable 不动 |

### 切片 5+ 候选清单（已全部收口）

| 优先级 | 候选文件 | 当前行数 | 状态 |
|--------|----------|----------|------|
| - | ~~全部完成~~ | - | TD-032 7 切片 + TD-033（`main.css` 模块化）全部合并，500 附近已全部拆分到位 |

> TD-033 完成后的 8 个 CSS 子模块 + main.css 入口均 ≤500 行，TD-032 整体目标达成。

### 合规样例（≤500 行，证明原则可被满足）

| 文件 | 行数 | 状态 | 备注 |
|------|------|------|------|
| `packages/web/src/views/LayoutView.vue` | 400 | 🟢 已合规 | 共享骨架组件，按 TD-008 / TD-025 已收敛 |
| `packages/web/src/views/auth/LoginView.vue` | 426 | 🟢 已合规 | 品牌背景例外保留，文件规模符合原则 |
| `packages/web/src/views/admin/FieldCard.vue` | 437 | 🟢 已合规 | 共享字段卡组件，TD-028 后规模合理 |
| `packages/web/src/views/admin/TemplateModal.vue` | 333 | 🟢 已合规（**切片 4 收口**） | 主入口 + 2 子组件；规模 ≤500 |
| `packages/web/src/views/database/DatabaseView.vue` | 320 | 🟢 已合规（**切片 4 收口**） | 主入口 + 6 子组件；规模 ≤500 |
| `packages/server-python/app/shared/parsing/chunker.py` | 398 | 🟢 已合规 | TD-005 范围外的共享解析模块，规模合理 |
| `packages/web/src/views/resource/ResourceView.vue` | 305 | 🟢 已合规 | 资源视图，TD-025 切片 1 收口 |
| `packages/web/src/views/ai-chat/AiChatView.vue` | 442 | 🟢 已合规 | AI 聊天视图，TD-025 切片 1 收口 |
| `docs/03-engineering-governance/01-rules/coding-style.md` | n/a | 🟢 已合规 | 规则文档，规模可被维护 |

> 行数随交付滚动；本表只列"治理后仍在 ≤500 的代表性共享 / 入口文件"作为基线对照。

## 治理节奏

- 复盘频率：与 `technical-debt.md#定期复盘规范` 一致（每周或每两周一次）。
- 复盘必读：1) 本文件；2) `technical-debt.md#td-032`；3) 最近一次扫描输出。
- 复盘输出：把 1-3 个 `⚪ 待切片` 推进到具体切片的 spec / plan，或升级为 `🔵 例外已登记`
  并写明「后续切片计划」。

## 扫描历史
- 2026-07-29：REQ-041/047 R1-S2 S2-D/E round-7 复审返修后回写 - `test_s2de_workspace_erasure.py` 1879 -> 1961 行（+仓库已知 placeholder 拒绝测试 actor/JWT/ctor 3 项 + 并发测试改独立 SimpleNamespace cfg 不污染全局 settings），`workspace_erasure_participant.py` 1302 -> 1319 行（+_KNOWN_ACTOR_ERASURE_PLACEHOLDERS denylist + 启动期/构造期 placeholder 拒绝）；`auth_service.py` +JWT placeholder denylist。本次仅登记，不在 R1-S2 中拆，后续按测试主题 / participant 职责切片。
- 2026-07-29：REQ-041/047 R1-S2 S2-D/E round-6 复审返修后回写 - `test_s2de_workspace_erasure.py` 1757 -> 1879 行（+并发首启 same/different secret + mismatch error redaction 3 个 round-6 测试），`workspace_erasure_participant.py` 1292 -> 1302 行（+compare_digest 常量时间比较 + 移除校验函数内 commit + redacted error）；新增 `test_agent_erasure_migration_roundtrip.py` 037 表/PK/CHECK downgrade->upgrade 专属回归。本次仅登记，不在 R1-S2 中拆，后续按测试主题 / participant 职责切片。
- 2026-07-29：REQ-041/047 R1-S2 S2-D/E round-5 复审返修后回写 - `test_s2de_workspace_erasure.py` 1573 -> 1757 行（+ACKed+blocked/scheduled operation 修复反例 + V1 key fingerprint lock-in/mismatch/构造器禁覆盖/非生产跳过 6 个 round-5 测试叠加），`workspace_erasure_participant.py` 1185 -> 1292 行（+_repair_checkpoint_if_pending ACKed 分支 fall through 到 operation 修复 + _actor_erasure_key_fingerprint + validate_production_actor_erasure_key_fingerprint 异步持久化校验 + 构造器生产禁覆盖 + V1 冻结文案统一）；新增 migration 037 `system_key_fingerprints` 表（round-5 P1-2 fingerprint 持久化）。本次仅登记，不在 R1-S2 中拆，后续按测试主题 / participant 职责切片。
- 2026-07-29：REQ-041/047 R1-S2 S2-D/E round-4 复审返修后回写 - `test_s2de_workspace_erasure.py` 1335 -> 1573 行（+legal-hold stale revision fail closed / legal-hold purge_state=blocked 投影 / record_blocked reason change bump revision / erased ACKed digest mismatch fail closed / erased blocked operation->running + 三方一致 / V1 版本冻结 / agent author digest 全类型 7 个 round-4 测试叠加），`workspace_erasure_participant.py` 1119 -> 1185 行 （+_record_blocked expected_revision CAS + reason change bump / legal-hold purge_state 投影 / erased ACKed digest 验证 / erased blocked->running 修复 + purge_state 三方一致 / agent author digest 全类型 / V1 版本冻结构造校验）；本次仅登记，不在 R1-S2 中拆，后续按测试主题 / participant 职责切片。
- 2026-07-29：REQ-041/047 R1-S2 S2-D/E round-3 复审返修后回写 - `test_s2de_workspace_erasure.py` 1082 -> 1335 行（+operation revision CAS / erased 非零 scan fail closed / erased 终态 operation fail closed / now 不被接受 / 版本契约 / blocked 重试状态一致测试叠加），`workspace_erasure_participant.py` 980 -> 1119 行（+revision CAS / erased scan guard / 终态 operation guard / secret 强度+版本 / now 移除 / owner_version 去硬编码），两文件均新增登记为 🟢 已登记（待拆分）；本次仅登记，不在 R1-S2 中拆，后续按测试主题 / participant 职责切片。
- 2026-07-29：REQ-041/047 R1-S2 S2-D/E round-2 复审返修后回写 - `test_s2de_workspace_erasure.py` 1082 行（6 场景表驱动 fencing 反例 + erased fence pending checkpoint 恢复 + scan archived_by/deleted_by + 已 redacted author_id 残留清除 + DB 时钟 + tenant 谓词 + 生产 fail-fast 叠加），新增登记为 🟢 已登记（待拆分）；本次仅登记，不在 R1-S2 中拆测试，后续按 P1-1 前置 / P1-2 HMAC / P1-3 fencing / P1-4 ACK+恢复 / P1-5 blocked+retry / P2+主路径 测试主题切片。
- 2026-07-21：REQ-045 Task 4 完成后回写 - `SkillListView.vue` 1104 行（skill-registry 最小管理 UI 单文件：列表 + 注册导入 + 启停 + 版本 + 删除 + 审计 + 试运行），新增登记为 🟢 已登记（待拆分）；本次仅登记，不在 closeout 中拆视图，后续按注册导入 modal / 审计 drawer / 试运行面板 / 版本删除切片。
- 2026-07-16：REQ-056 Task 3 完成后回写 — `ai_chat_service.py` 961 → 1016 行（tool 声明加 `catalog_id` 字段 + tool_call handler 双键 / 单键分支），新增登记为 🟢 已登记（待拆分）；本次仅登记新增风险，不在本任务中拆 service，后续按职责切片（tool/fusion/hydration/chat 骨架）。
- 2026-06-20：`scripts/scan-source-sizes --refresh` 自动刷新行数列。
- 2026-06-20：`scripts/scan-source-sizes --refresh` 自动刷新行数列。
- 2026-06-10：`scripts/scan-source-sizes --refresh`（DOC-055 收口）刷新 baseline — `--diff` 恢复 `(no differences from baseline)`；本轮 refresh 吸收了 PR #143 squash merge 时带入的 TD-034 代码行数变化（`extract_template_prompts.py` 88 → 93；`test_extract_template_prompts.py` 263 → 261），原 baseline 由 DOC-042 收口时建立（彼时 `--diff` 在 PR #143 合并后即报 2 个差异但被遗漏）。

- 2026-06-08：与 `technical-debt.md#td-032` 证据段同步，基线建立。
- 2026-06-08（切片 4 收口后回写）：5 个 >500 / 500 附近文件全部转 `🟢 已拆分` 或维持 `⚪ 待切片` 标记；新增 `FileDetailView.vue` 416 为 500 附近候选；新增「切片 5+ 候选清单」段；扩展「合规样例」段加入 `TemplateModal.vue` 333 / `DatabaseView.vue` 320 / `chunker.py` 320 / `ResourceView.vue` 305 / `AiChatView.vue` 304。本次回写由 DOC-xxx 任务承接。
- 2026-06-09（TD-032 评审后回写）：扫描命令改为 `rg --files -0 ... | xargs -0 wc -l`，并显式排除 `.venv` / `uploads` / `node_modules` / `dist`，避免本地未跟踪文件或带空格路径污染行数基线；脚本化候选入账 `DOC-042`。
- 2026-06-09：`main.css` 设计系统级 CSS 模块化从 TD-032 例外转为独立就绪任务 `TD-033`。
- 2026-06-09：TD-033 完成（[PR #103](https://github.com/MarkDanile/MetaEduBase/pull/103) / merge `25ca165`）：`main.css` 1343 → 9 行（`@import` 入口）+ 8 个 CSS 模块（全部 ≤500 行）；以 `pnpm typecheck / lint / build` 退出码 0 与 `git diff --check` 退出码 0 为依据（Vite 产物未做 hash / diff 机械对比，详见 DOC-045）；TD-032 >1000 / >500 / 500 附近全部收口。

- 2026-08-05：REQ-041/047 R1-S4-B 第四轮复核返修后回写 - `test_agent_transport_backfill_m4.py` 1067 行（三轮复核真实反例 + CLI 退出码契约叠加），新增登记为 🟢 已登记（待拆分）；本次仅登记，不在 R1-S4-B 中拆测试，后续按并发/冲突登记/verify 反例/CLI 退出码测试主题切片。

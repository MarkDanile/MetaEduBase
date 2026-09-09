# 当前开发工作台

本文件是所有 AI IDE、插件和人工协作的当前任务入口。开始任何开发任务前，先阅读本文件，再按任务卡片中的链接渐进式读取相关 spec、plan、技术债或架构约束。

不同任务类型的开工条件、必读文档和完成标准见 `docs/03-engineering-governance/task-modes.md`。

## 使用规则

- 本文件只保留当前任务、近期候选和少量最近完成任务；任何修改本文件或任务状态前，必须先读 `docs/03-engineering-governance/01-rules/workbench.md`。
- 开发前确认本次任务卡片，并按卡片链接渐进式读取 spec、plan、技术债或架构约束。
- 涉及跨文件开发、计划接力、状态交接或后续继续开发时，必须登记或更新任务卡片。
- 代码、验证或 Git 阶段变化后，必须同步任务状态、当前进展、下一步和验证结果。
- 提交、PR、合并或声明完成前，运行 `scripts/check-engineering-docs` 并执行 `docs/03-engineering-governance/01-rules/quality-gates.md#完成门禁`；门禁主实现位于 `scripts/engineering/check_engineering_docs.py`。

## 当前进行中

### TASK-REQ-042-WS-S1-DURABLE-READ-SHELL: Workspace durable read/recovery 三栏 shell（只读，零写路径）

状态：🟡 进行中
类型：新需求开发（REQ-042 首个实施 Slice WS-S1）
领域：前端 Workspace（packages/web）
当前执行模式：plan-do（Phase 0 只读审计已批准 WS-S1；本任务卡即实施边界，不另建 spec/plan）
最近接手工具：Claude Code
分支：feature/req042-ws-s1-durable-read-shell

需求来源：
- Spec: [REQ-042](../01-product-planning/05-requirements/REQ-042-agent-workspace-three-pane-experience.md)（Status ⚫ Candidate，本 Slice 不翻 Done）
- Plan: 无独立 plan 文档——以 Phase 0 审计报告 + 本任务卡为实施边界（用户明确禁止本轮新建/修改 spec、plan）
- 技术债：无
- 架构约束：数据只读自已落地 real PG 的 [REQ-041 Conversation/Message API] 与 [REQ-047 Run/Event query]；不开放新 submit-turn

允许范围：
- 前端 Workspace 路由、页面、组件、store、service、类型与前端测试
- 现有 Playwright 导航/布局测试与必要测试 fixture
- 本文件（current-work.md）本任务 active card
- 具体：接通已有 agent_workspace feature flag + 路由守卫；三栏 shell（左 Conversation 列表/搜索/创建/切换/重命名/置顶/归档/恢复/删除；中 Message history after_seq/before_seq keyset 分页 + 加载/空/错态；右栏无 Run 诚实空态、有 Run 只读 GET /agent-runs/{id} 终态/状态/序号窗口）；前端 service 层按现有后端 DTO/错误语义消费 Conversation/Message-history/Run-query；Workspace store（会话选择、loading/empty/error/404/权限、切换刷新、keyset 游标）；草稿 store（tenant/owner/conversation 隔离、刷新恢复、不存 token/凭据）；复用现有导航/RBAC/主题/EmptyState/Loading/Toast/消息渲染组件；desktop 1280×800 + Pixel 5 + 中间断点布局；真实 DTO fixture 前端测试（mock 仅用于界面状态，不作生产能力证据）。

禁止范围：
- 新增/开放 Workspace submit-turn；调用/接入 /ai/chat/evidence；Composer 真实发送
- SSE / EventSource / after_seq 事件订阅 / 断线重连 / live token；Run cancel/stop
- AgentTurnLoopRuntime；Approval/HumanInput；Tool/Grant/Snapshot；run-scoped Evidence；Artifact；thinking/plan summary emitter；SkillRunner 时间线 producer
- erase_available / production wiring / capability flip；REQ-043/062/063/TD-085
- 修改生产后端、migration、schema、registry、CI、门禁
- 修改 requirements、spec、plan、work-log、fact-audit、technical-debt、Score Log、Metrics
- 用静态卡片/假事件/占位数据/disabled UI 冒充 AC-3/4/5/7/8；composer 仅可为明确非提交态，不得有假成功发送路径

验证计划：
- Workspace route/feature flag/RBAC；Conversation list/search/create/switch/rename/pin/archive/restore/delete；Message history 首屏/分页/空态/错误态/序号连续性；Run 终态读取 + 无 Run 空态；刷新后草稿恢复；tenant/owner 切换隔离；404/403/409/410 错误映射；desktop 1280×800 + mobile Pixel 5 + 中间断点无重叠/横向溢出/明显跳动
- 门禁：前端 lint + typecheck + unit/component tests + Playwright desktop/mobile + `git diff --check` + `check-engineering-docs --full` + pre-commit/pre-push hooks
- 不启动数据库、不跑 mutation harness；Playwright mock 结果不写成 real PG 验证

当前进展：实现 + 修复轮 + 覆盖补强 + restore 证据边界收紧完成——service 层（agentWorkspace DTO/端点/parseApiError）+ workspace store（keyset 分页/run 三态含 410 event_history_expired→runUnavailable/If-Match CAS/race GUARD：`loadSelectedConversation` / `loadMessages` / `loadOlderMessages` / `selectRun` 全部 selectedId GUARD；`messagesLoadingOlder` 切换重置；archive/restore/rename/delete in-flight guard）+ workspaceDraft store（tenant+owner+conversation 隔离草稿）+ 三栏 shell（ConversationList/MessageTimeline/RunDetail/Composer + AgentWorkspaceView）+ agent_workspace 路由 flag 门控；8 个 base..HEAD 线性 commit（active card 注册 bfb2d71d + ff449511/b9f61ddf/f17f68e8/d63f1969/878d6da5/68d39435/c265f229 + 本 restore 证据边界收紧 commit）；OPEN/Draft PR #618 已创建；修复轮 4 例 + 覆盖补强 8 例 unit tests（含 2 例真实 deferred A→B conversation/message race + 3 例 restore/rename/delete 双击 guard + 3 例 409 transparency）+ restore 失败 mock UI contract 1 例 Playwright（桌面+移动双 project）。
**Restore 证据边界（手动验收复审 + 本轮收紧）**：`restoreConversationById` 的 UI（按钮 `:disabled="store.restoreInFlight"` 绑定）/ store / endpoint（POST /agent-workspace/conversations/{id}/restore + If-Match）/ 409 + `conversation_restore_not_allowed` 错误透传到 toast / finally 复位 + 后续可重发均已实现；前端 mock UI contract 1 例 e2e 已新增（409 + fence ledger incomplete 错误透传）。**真实 PG 正向 restore 不在 WS-S1 scope**：后端 fail-closed 要求完整六-owner erasure fence（[bridge.py:90-126](../../packages/server-python/app/contexts/agent_workspace/application/bridge.py#L90) `_require_restorable_fences`）；普通新建会话只建 `workspace.core.v1` 一根 baseline fence（[repository.py:101-120](../../packages/server-python/app/contexts/agent_workspace/infrastructure/repository.py#L101)），其余 5 owner 由 backfill 补齐。手动验收「新建 → archive → restore 返回 409」是预期 fail-closed，不是前端缺陷；后端 fail-closed 由 [test_restore_recovery.py:260/275/305/333](../../packages/server-python/tests/contexts/agent_control_plane/test_restore_recovery.py#L260) `ConversationRestoreNotAllowedError` 反例真实 PG 覆盖，正向路径需经 `agent_erasure_backfill` 建完整六-owner baseline fence——该 fixture 准备不属于 WS-S1。REQ-042 AC-1 原文不含 restore。
下一步：等 Draft PR #618 三路 CI SUCCESS 后停止；不 Ready/评分/合并/closeout/启动下一 Slice，等用户裁决 WS-S2/S3 与 AC-4/8。
验证状态：本地全绿——前端 lint 0 error；typecheck（app+e2e 双 tsconfig）0 error；unit/component **382/382**（Node 20 对齐 CI，新增 56 例 + nav.spec 业务 leaf 23→24；其中修复轮 4 例 + 覆盖补强 8 例：2 例 deferred A→B race + 3 例 restore/rename/delete 双击 guard + 3 例 409 transparency）；Playwright **66 CI 执行**（chromium-desktop 31 + chromium-mobile 35，覆盖 45 unique test()），含本轮新增 restore 失败 mock UI contract 1 unique / 2 CI 执行；**本地 desktop 1 个 pre-existing failure**（navigation-desktop.spec.ts:33 /ai-chat activeNav 在 main 分支独立验证同样失败 + spec 未被本 PR 修改 + CI ubuntu-latest 通过 → macOS local 时序 flake，与本 PR 无关）；git diff --check clean；check-engineering-docs --full passed（32 known allowlisted 与基线一致）。未启动数据库、未跑 mutation harness。
**post-review tightening（三面复审 P2 闭环）**：restore 失败 mock UI contract e2e 的 If-Match 断言从 `toBeTruthy()` 收紧为精确值 `toBe("5")`（mock 中 archived conversation revision = 5），捕获"前端发送非当前会话 revision / 固定错误值 / revision 链路漂移"；其余断言（endpoint / 409 / toast / 不显示成功 / 按钮复位 / 无 submit-turn/SSE/evidence）保持不变。测试数量不变：仍为 382 unit + 66 Playwright CI 执行 + 45 unique + Workspace 8 unique / 10 CI；restore 仍仅为 mock UI contract，不是 real PG 正向路径。
交接备注：本 Slice 完成后仅可宣称 AC-1（**会话生命周期[不含 restore] + 草稿恢复**）、AC-2 读半边（刷新/重进 durable read）、AC-6 基础 desktop/mobile 布局；AC-3 仅呈现已有真实 Message/Evidence 引用；AC-4/AC-8 保持未完成（待 REQ-043 + REQ-047 Extended）；AC-5/AC-7 保持受限。**restore = UI/API wiring 已实现（mock UI contract e2e 已覆盖），不表示真实 PG 正向 restore 已通过；正向路径需 backfill 完整六-owner baseline fence（六 owner 定义见 agent_erasure_registry.py:84-122，runtime/external owner erase_available 仍 False，registry 冻结 6 owner）**。REQ-042 不翻整体 Done。交付到 OPEN/Draft PR + 三路 CI SUCCESS 后停止，不 Ready/评分/合并/closeout/启动下一 Slice。

## 下一批候选任务

按"建议执行顺序"排序；候选区只保留近期 1 到 3 个入口，完整任务池回 `docs/01-product-planning/04-backlog.md` / `docs/03-engineering-governance/technical-debt.md`。

| 优先级 | 任务 | 状态 | 建议下一步 | 事实源 |
|--------|------|------|------------|--------|
| P0 | REQ-042: Codex 式 Agent Workspace 三栏体验（Durable Core 已完成，事件协议稳定可依托） | 🟡 WS-S1 进行中（durable read/recovery shell 已开活跃卡，见上方「当前进行中」；REQ-042 整体仍 ⚫ Candidate） | WS-S1 实施 + 本地验证 + OPEN/Draft PR；剩余 WS-S2/WS-S3 与 AC-4/AC-8 依赖待本 Slice 交付后另行裁决；不直接跳到 Pi Worker / 不开放 submit-turn | [REQ-042](../01-product-planning/05-requirements/REQ-042-agent-workspace-three-pane-experience.md) / [backlog](../01-product-planning/04-backlog.md) |
| P0 | REQ-062: 动态数据采集、填报与报表发布平台 contract shaping | ⬜ 未启动（仅登记候选，不在本 closeout 开工） | 在 Run/Artifact 契约上塑形 Campaign/FormSchemaVersion/Submission/ReportSnapshot；AI 草案审核后才发布；仅契约塑形不实现自由表单引擎 | [REQ-062](../01-product-planning/05-requirements/REQ-062-dynamic-data-collection-and-reporting.md) / [backlog](../01-product-planning/04-backlog.md) |
| P0 | REQ-063: 受治理的外部数据采集与研究证据链 source spike | ⬜ 未启动（仅登记候选，不在本 closeout 开工） | 先做授权来源/许可/网络/快照策略 spike，不提前实现自由爬虫；Connector 等待 Tool Gateway | [REQ-063](../01-product-planning/05-requirements/REQ-063-governed-external-data-acquisition.md) / [backlog](../01-product-planning/04-backlog.md) |

> 后续顺序保持：TD-085 Boundary Closure、REQ-043 Runtime/Tool Gateway 按 backlog 既定顺序承接，不在本批候选开工。

## 最近完成

最近完成区默认最多保留 20 行（按 `docs/03-engineering-governance/01-rules/workbench.md#保留策略` 强约束）。超过 20 行时，必须一次性批量归档，只保留最新 12 行；第 13 行及以后全部移出。不得每次只移动 1 行。本表只承担"近期完成窗口"的角色，详细验证、行为变化、PR 描述和复盘见 `docs/03-engineering-governance/work-log.md`、对应技术债总账、plan 或 PR。

按"最近优先"（最新任务在最上）排序：

| 日期 | 任务 | 状态 | 摘要 | 事实源 |
|------|------|------|------|------|
| 2026-09-08 | TASK-R1-S6-C1：R1-S6 C1 Durable Core 联合契约/conformance 总验收 Phase 1（5 类 B 类缺口判别测试 + ARCHITECTURE.md 落地事实修正）+ 独立 pure-docs closeout（TASK-R1-S6-C1-CLOSEOUT 子卡） | 🟢 完成（C1 子阶段 + CLOSEOUT 子卡；R1-S6/TASK-R1-S6-I3-D 翻 Durable Core 完成；REQ-041 翻 Done、REQ-047 标 Durable Core Done 保持 Shaping；S5 wiring/capability flip/六 erase/Extended REQ-047/完整 P3 保持未启动） | PR #614 squash mergeCommit `62eef1a3`；评分 94 Original；5 类 B 类测试+ARCHITECTURE 修正；11/11 mutation harness（sch_d 12/12）+全量 2966/0；C1=Durable Core 完成非生产 enable；无 G-1；保留 P3 既有 | [PR #614](https://github.com/MarkDanile/MetaEduBase/pull/614)（mergeCommit `62eef1a3`）/ [work-log](work-log.md) / [score 94](04-retrospectives/review-score-log.md) / [fact-audit §17.14](04-retrospectives/r1-s6-i3-d-fact-audit.md) |
| 2026-09-08 | TASK-R1-S6-SCH-D-MUTATION-HARNESS-MAINTENANCE：sch_d mutation harness stale anchor 重锚维护（settlement.py #586 重构漂移）+ 独立 pure-docs closeout | 🟢 完成（sch_d harness 维护子任务；REQ-041/047 完成态与 C1 总验收不受此影响、仍按各自边界推进） | PR #615 squash mergeCommit `6a804a1d`；评分 94 Original；sch_d 6 stale anchor 重锚当前 settlement.py + sch_d 12/12 mutation-level KILLED；合并后 main 11 harness 串行全绿；零生产/测试改动；G-1 顺序偏差 + all(...) limitation 两 P3 真实保留未消除 | [PR #615](https://github.com/MarkDanile/MetaEduBase/pull/615)（mergeCommit `6a804a1d`）/ [work-log](work-log.md) / [score 94](04-retrospectives/review-score-log.md) / [fact-audit §17.13](04-retrospectives/r1-s6-i3-d-fact-audit.md) |
| 2026-09-07 | R1-S6 PR-E release drill 五阶段 fail-closed canary contract（pure test harness）+ 独立 closeout 治理收口（TASK-R1-S6-I3-D-PR-E-CLOSEOUT 子卡） | 🟢 完成（PR-E 子阶段 + CLOSEOUT 子卡；TASK-R1-S6-I3-D 整体仍 🟡 进行中——C1/S5 wiring/capability flip/六 erase/REQ-047 未启动） | PR #612 squash mergeCommit `25aefc74`；score 95 Original；PR-E 15/15 + composition 1014/6；P3×2 闭环 follow-up=无；PR-E=production-neutral contract-tested test harness 非生产 release enable；真实 pg_dump/多实例 canary 保持生产门禁未执行 | [PR #612](https://github.com/MarkDanile/MetaEduBase/pull/612)（mergeCommit `25aefc74`）/ [work-log](work-log.md) / [score 95](04-retrospectives/review-score-log.md) / [fact-audit §17.12](04-retrospectives/r1-s6-i3-d-fact-audit.md) |
| 2026-09-06 | R1-S6 F-matrix M-F8 单独判别（test-contract / shared-observation gap 闭合）+ 独立 closeout 治理收口（TASK-R1-S6-FMATRIX-MF8-CLOSEOUT 子卡） | 🟢 完成（F-matrix M-F8 单独判别 + CLOSEOUT 子卡；TASK-R1-S6-I3-D 整体仍 🟡 进行中——PR-E/C1/S5/capability flip/六 erase/REQ-047 未启动） | PR #610 squash mergeCommit `b8daa934`；score 95；F-matrix 12/12 + F10 8/8 = 20/20 KILLED（PR #608 19/20 口径保持）；跨变独立性双证明；G-1 [P3] 真实保留 | [PR #610](https://github.com/MarkDanile/MetaEduBase/pull/610)（mergeCommit `b8daa934`）/ [work-log](work-log.md) / [score 95](04-retrospectives/review-score-log.md) / [fact-audit §17.11](04-retrospectives/r1-s6-i3-d-fact-audit.md) |
| 2026-09-04 | R1-S6 F-matrix + F10 M6 test contract 增强（独立后续 PR；Phase 0 审计修正 3 项 M-F3/M-F5 错映射 + F10 M6 不可达路径解除；5 文件 pure test contract + mutation harness 修正） | 🟢 完成（F-matrix + F10 M6 子阶段；TASK-R1-S6-I3-D 整体仍 🟡 进行中——F-matrix M-F8 NOT-RED test-contract/shared-observation gap / PR-E/C1/S5/capability flip/六 erase/REQ-047 未启动） | PR #608 squash mergeCommit `e07c601b`；评分 94 Original；**F-matrix 11/12 KILLED + F10 8/8 KILLED = 19/20**（M-F8 NOT-RED 真实 harness issue 不冒充 KILLED）；zero-touch；TD-104/TD-032 保持登记 | [PR #608](https://github.com/MarkDanile/MetaEduBase/pull/608)（mergeCommit `e07c601b`）/ [work-log](work-log.md) / [score 94](04-retrospectives/review-score-log.md) / [fact-audit §17.10](04-retrospectives/r1-s6-i3-d-fact-audit.md) |
| 2026-09-03 | R1-S6-I3-D PR-D 剩余 operational closeout（production-neutral 4 项：orchestration entry + restore-before-open runbook + D1a→D1b→D2→gate cross-layer safety drill + crash/retry/post-snapshot purge/M-class/blocked-manual reconcile ops） | 🟢 完成（PR-D 子阶段；TASK-R1-S6-I3-D 整体仍 🟡 进行中——F-matrix/PR-E/C1/S5/capability flip/六 erase 未启动） | PR #606 squash mergeCommit `d196d7f0`；评分 95 Original；4 文件净 diff 851 insertions(+)/1(-)；zero-touch（无 migration/schema/CHECK/CI）；TD-104 保持 ⚫ 待办 / TD-032 保持 🟢 待拆分不关闭 | [PR #606](https://github.com/MarkDanile/MetaEduBase/pull/606)（mergeCommit `d196d7f0`）/ [work-log](work-log.md) / [score 95](04-retrospectives/review-score-log.md) / [fact-audit §17.9](04-retrospectives/r1-s6-i3-d-fact-audit.md) |
| 2026-09-02 | R1-S6-I3-D 工作台精简 + PR-D 剩余边界重定基 GOV closeout（pure-docs；TASK-R1-S6-I3-D-GOV 子卡） | 🟢 完成（GOV 子卡；TASK-R1-S6-I3-D 整体仍 🟡 进行中——PR-D/PR-E/C1/S5/capability flip 未启动） | PR #604 squash mergeCommit `e37561fe`；评分 91 Original；pure-docs 3 文件（current-work slim + plan §S6-14 APPEND + fact-audit 4 处过期修复）；P3=5 non-blocking；TASK-R1-S6-I3-D 整体仍 🟡（PR-D/PR-E/C1/S5/capability flip 未启动）；零业务代码改动 | [PR #604](https://github.com/MarkDanile/MetaEduBase/pull/604)（mergeCommit `e37561fe`）/ [work-log](work-log.md) / [score 91](04-retrospectives/review-score-log.md) / [fact-audit](04-retrospectives/r1-s6-i3-d-fact-audit.md) |
| 2026-09-01 | R1-S6-I3-D D2 restore replay executor + restore-before-open gate（M 类；Round-8/8.1 三面复审 P0/P1/P2/P3=0 + squash merge 入 main） | 🟢 完成（D2 子阶段；TASK-R1-S6-I3-D 仍 🟡 进行中——PR-D 未启动） | PR #602 squash mergeCommit `ae7f3c98`；评分 92 Original；108 D2 专项 + 992 composition + 21/21 mutation；D2 wiring / PR-D / PR-E / C1 / S5 wiring / capability flip / 六 erase 未启动 | [PR #602](https://github.com/MarkDanile/MetaEduBase/pull/602)（mergeCommit `ae7f3c98`）/ [work-log](work-log.md) / [score 92](04-retrospectives/review-score-log.md) / [fact-audit](04-retrospectives/r1-s6-i3-d-fact-audit.md) |
| 2026-08-28 | R1-S6-I3-D D1b 专用 MinIO ledger archive sink + 不可变 commit-graph 发布协议（两阶段 API 拆分；三面 P1 修复闭环 + squash merge 入 main） | 🟢 完成（D1b 子阶段；TASK-R1-S6-I3-D 仍 🟡 进行中） | PR #600 squash mergeCommit `01c84f7c`；评分 94 Original；47/47 composition + 6/6 opt-in real MinIO + 11/11 mutation；D1b wiring / D2 / PR-D / PR-E / C1 / S5 wiring / capability flip / 六 erase 未启动 | [PR #600](https://github.com/MarkDanile/MetaEduBase/pull/600)（mergeCommit `01c84f7c`）/ [work-log](work-log.md) / [score 94](04-retrospectives/review-score-log.md) / [fact-audit](04-retrospectives/r1-s6-i3-d-fact-audit.md) |
| 2026-08-28 | R1-S6-I3-D D1a bounded read-only ledger snapshot codec（三轮 P1 治理闭环 + squash merge 入 main） | 🟢 完成（D1a 子阶段；TASK-R1-S6-I3-D 仍 🟡 进行中） | PR #598 squash mergeCommit `5868831e`；评分 97 Original；57/57 D1a + 828 composition + 20/20 mutation；D1a 已并入 main，D1b/D2/PR-D 未启动 | [PR #598](https://github.com/MarkDanile/MetaEduBase/pull/598)（mergeCommit `5868831e`）/ [work-log](work-log.md) / [score 97](04-retrospectives/review-score-log.md) / [fact-audit](04-retrospectives/r1-s6-i3-d-fact-audit.md) |
| 2026-08-26 | R1-S6-I3-F10 settlement T1/T2 hold 推进故障矩阵真实 PG 判别 + TD-105 实现承接 | 🟢 完成 | PR #596（squash `c0ec008d`）；评分 97 Original；8 项 PG 测试 + 7/8 mutation 真红（M6 NOT-RED）；净 diff 3 文件 1005+/23- 无生产代码；**TD-105 已完成并关闭**；F10 不直接 completed；PR-D/E/C1/S5 wiring 未启动 | [PR #596](https://github.com/MarkDanile/MetaEduBase/pull/596)（squash `c0ec008d`）/ [work-log](work-log.md) / [score 97](04-retrospectives/review-score-log.md) |
| 2026-08-26 | R1-S6-I3 root bounded integration: S6-F1..F14 故障矩阵 + TD-106 方案 A + scope 收敛 + main closeout | 🟢 完成 | root PR #586（squash `68fafd81`）+ main closeout；评分 94 Original；scope = F1-F14 故障矩阵 + TD-106 方案 A bounded integration；PR-D/E scaffold 已撤回；**TD-106 已完成并关闭**；F10 仍 skip（TD-105 承接）+ PR-D/PR-E/C1/S5 wiring/capability flip 均未启动 | [PR #586](https://github.com/MarkDanile/MetaEduBase/pull/586)（squash `68fafd81`）/ [work-log](work-log.md) / [score 94](04-retrospectives/review-score-log.md) |
| 2026-08-25 | R1-S6-I3-F10 S6-F10 契约核对纠偏 + TD-106 决策门禁（contract-first，纯文档） | 🟢 完成 | PR #591（squash `738be6f9`）；评分 89（Original）；§S6-15 冻结入 main；**TD-106 实现已随 #586 入 main 完成**（详细见 work-log + [TD-106](technical-debt.md#td-106-r1-s6-settlement-success-不写-ledgerbinding实现-vs-s5-c-1-冻结契约缺口pre-existing)） | [PR #591](https://github.com/MarkDanile/MetaEduBase/pull/591)（squash `738be6f9`）/ [work-log](work-log.md) / [score 89](04-retrospectives/review-score-log.md) |
| 2026-08-24 | R1-S6-I3-A schema/test alignment bounded repair（squash 入 #586） | 🟢 完成 | squash 入 #586；评分 92（Original）；幽灵列对齐真实 schema + acked fixture 合法化 + 独立 CHECK 负例 + F3 补种；fresh PG 043 24/24 + composition 750；**#586 已合 main**；TD-104 保持承接 | [PR #589](https://github.com/MarkDanile/MetaEduBase/pull/589)（squash `f6062466`）/ [work-log](work-log.md) / [score 92](04-retrospectives/review-score-log.md) |
| 2026-08-24 | R1-S6-I3-B restore replay 持久状态域契约纠偏（contract-first，纯文档） | 🟢 完成 | PR #587（squash `66674f23`）；评分 85；三层 CHECK 闭集 + replay 路由表 + 判定方式冻结；**#586 已合 main**；TD-104 + REQ-047 | [PR #587](https://github.com/MarkDanile/MetaEduBase/pull/587)（squash `66674f23`）/ [work-log](work-log.md) / [score 85](04-retrospectives/review-score-log.md) |
| 2026-08-20 | R1-S6-I2 Writer conformance suite + body/ref orphan inspection | 🟢 完成 | PR #584（merge `ad7ac3e5`）；评分 88；3 writer spec + 六类 verify 巡检 + Run 行锁；21 项专项 + 726 composition；TD-100~103 + REQ-047；S6-I3/C1/S5 wiring 未启动 | [PR #584](https://github.com/MarkDanile/MetaEduBase/pull/584)（merge `ad7ac3e5`）/ [work-log](work-log.md) / [score 88](04-retrospectives/review-score-log.md) |
| 2026-08-19 | R1-S6-I1 Retention workers（run_event_retention + run_audit_retention + migration 043） | 🟢 完成 | PR #582（squash `f5072ec6`）；评分 87（基线 `d1427567`）；两 worker + 043 guard + 两处 S5 修复落地；三面返修+决 A 测试兼容升级后 P0/P1=0；Backend 2649/1/4/0 + mutation 18/18 + 043 往返稳定；S6-I2/I3/C1/S5 wiring 未启动；TD-097/098/099 + REQ-047 | [PR #582](https://github.com/MarkDanile/MetaEduBase/pull/582)（squash `f5072ec6`）/ [work-log](work-log.md) / [score 87](04-retrospectives/review-score-log.md) |

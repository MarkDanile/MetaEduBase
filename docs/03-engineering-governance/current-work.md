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

### TASK-REQ-042-WS-S2-CONTRACT-SHAPING-CLOSEOUT-FACT-CORRECTION: 收口治理（pure-docs）

状态：🟡 进行中（pure-docs 事实纠偏；前序事实纠正已落地，PR 本体等待最终独立只读复审）
类型：pure-docs 事实纠偏
领域：docs/03-engineering-governance/current-work.md（active card 与候选行状态同步）
当前执行模式：plan-do（用户明确禁止启动 WS-S2 implementation / 触碰后端 / 运行 backfill）
最近接手工具：Claude Code
分支：docs/req042-ws-s2-contract-shaping-closeout

需求来源（多轮独立只读复审的稳定事实清单）：

- work-log.md #621 行中 `1662e2f6` 是 SHA 拼写错误（实际 score base = `1661e2f6396f90103e57e08e579eb9787de3f5b5`）
- `b0fec031` 不在 PR #621 祖先链（`git merge-base --is-ancestor b0fec031 1661e2f6` exit=1）
- work-log.md 的 implementation baseline / SCORE_BASE / source-head 语义需分层表达
- PR body 多次混淆逐 commit churn 与区间净 diff
- current-work 候选行（REQ-042）状态与已合并 shaping 裁决矛盾（候选行此前写"待独立裁决"，实际 WS-S2 option B / WS-S3 已 BLOCKED）

允许范围（最终收口修订）：

- 修改 docs/03-engineering-governance/current-work.md active card 与候选行状态同步
- 修改 PR #622 body 范围摘要
- work-log.md 本轮禁止修改（已正确）

禁止范围：

- 不实现 submit-turn / SSE / after_seq / cancel / stop / steer
- 不创建公共 `/turns` 路由
- 不开放发送按钮
- 不实现前端 SSE transport
- 不启动 WS-S2 / WS-S3 / REQ-043 / REQ-062 / REQ-063 / TD-085
- 不运行 agent_erasure_backfill / 不修改 erase_available / 不触碰 metaedu 或 metaedu_test
- 不处理或 prune stale remote-tracking refs
- 不修改 review-score-log.md / Metrics / 历史评分行
- 不修改 shaping plan / requirements / REQ-042 状态 / REQ-043 / REQ-047 Extended / TD-085
- 不修改 technical-debt.md / fact-audit.md
- 不修改后端 / 前端 / 测试 / migration / schema / registry / CI / 门禁
- 不 amend / rebase / force-push / reset

验证计划（稳定门禁）：

- `git diff --check`
- `scripts/check-engineering-docs --full`
- Score Log / Metrics / shaping plan 相对 main HEAD byte-identical
- PR body 事实口径与实际 `git diff --numstat aa88e5ea..HEAD` 一致
- Draft CI 以 PR Checks 当前状态为准

当前进展（稳定事实，不列 commit 或 pending）：

- work-log.md #621 行 SHA 与评审链已正确
- PR body 的整体 Git 直接输出已正确
- current-work 候选行（REQ-042）已同步已合并 shaping 裁决（WS-S2 option B 仍 BLOCKED；WS-S3 仍 BLOCKED）
- 前序事实纠正已落地

下一步（用户裁决）：

- 等待用户裁决
- 在用户明确授权前不得 Ready、评分或合并

验证状态（已实际执行）：

- work-log.md SHA / 评审链与 Score Log #621 Original 行 byte-identical 对齐
- `git merge-base --is-ancestor` 三项验证：9fda8ae1→1661e2f6 exit=0，1661e2f6→3a37d5f0 exit=0，b0fec031≠1661e2f6 祖先 exit=1
- `scripts/check-engineering-docs --full` passed（32 known allowlisted）
- Draft CI 以 PR Checks 当前状态为准

## 下一批候选任务

按"建议执行顺序"排序；候选区只保留近期 1 到 3 个入口，完整任务池回 `docs/01-product-planning/04-backlog.md` / `docs/03-engineering-governance/technical-debt.md`。

| 优先级 | 任务 | 状态 | 建议下一步 | 事实源 |
|--------|------|------|------------|--------|
| P0 | REQ-042: Codex 式 Agent Workspace 三栏体验（Durable Core 已完成，事件协议稳定可依托） | 🟢 WS-S1 已完成（durable read/recovery shell 已 squash merge 入 main `235f4085`；REQ-042 整体仍 ⚫ Candidate — WS-S1 仅交付 AC-1[不含 restore] / AC-2 读半边 / AC-6 desktop/mobile 布局 + restore UI/API wiring；AC-3 仅呈现已有真实引用；AC-4/AC-5/AC-7/AC-8 保持未完成待 REQ-043 + REQ-047 Extended；WS-S2 option B 仍 BLOCKED；WS-S3 仍 BLOCKED） | WS-S1 完成并 squash merge 入 main；WS-S2 option B 仍 BLOCKED（4 项硬门禁：公共 submit API spec + server-selected launch policy + 最小 execution profile + 真实 PG submit-loop 端到端全部通过前）；WS-S3 仍 BLOCKED（4 项硬门禁：浏览器 SSE 鉴权 transport + cancelRun/steerRun 前端 + REQ-047 Extended spec + REQ-043 Runtime conformance spec）；不直接跳到 Pi Worker / 不开放 submit-turn | [REQ-042](../01-product-planning/05-requirements/REQ-042-agent-workspace-three-pane-experience.md) / [backlog](../01-product-planning/04-backlog.md) |
| P0 | REQ-062: 动态数据采集、填报与报表发布平台 contract shaping | ⬜ 未启动（仅登记候选，不在本 closeout 开工） | 在 Run/Artifact 契约上塑形 Campaign/FormSchemaVersion/Submission/ReportSnapshot；AI 草案审核后才发布；仅契约塑形不实现自由表单引擎 | [REQ-062](../01-product-planning/05-requirements/REQ-062-dynamic-data-collection-and-reporting.md) / [backlog](../01-product-planning/04-backlog.md) |
| P0 | REQ-063: 受治理的外部数据采集与研究证据链 source spike | ⬜ 未启动（仅登记候选，不在本 closeout 开工） | 先做授权来源/许可/网络/快照策略 spike，不提前实现自由爬虫；Connector 等待 Tool Gateway | [REQ-063](../01-product-planning/05-requirements/REQ-063-governed-external-data-acquisition.md) / [backlog](../01-product-planning/04-backlog.md) |

> 后续顺序保持：TD-085 Boundary Closure、REQ-043 Runtime/Tool Gateway 按 backlog 既定顺序承接，不在本批候选开工。

## 最近完成

最近完成区默认最多保留 20 行（按 `docs/03-engineering-governance/01-rules/workbench.md#保留策略` 强约束）。超过 20 行时，必须一次性批量归档，只保留最新 12 行；第 13 行及以后全部移出。不得每次只移动 1 行。本表只承担"近期完成窗口"的角色，详细验证、行为变化、PR 描述和复盘见 `docs/03-engineering-governance/work-log.md`、对应技术债总账、plan 或 PR。

按"最近优先"（最新任务在最上）排序：

| 日期 | 任务 | 状态 | 摘要 | 事实源 |
|------|------|------|------|------|
| 2026-09-10 | TASK-REQ-042-WS-S2-CONTRACT-SHAPING：WS-S2 / WS-S3 contract-shaping 报告（Phase 0 audit + 切片规划；pure-spec / pure-docs）+ 独立 closeout 治理收口 | 🟢 完成（Phase 0 shaping/audit 子阶段；WS-S2 唯一产品路径 option B 仍 BLOCKED；WS-S3 仍 BLOCKED；仅 pure-spec/pure-docs，0 后端 / 0 测试 / 0 migration / 0 schema / 0 CI 改动；REQ-042 仍 ⚫ Candidate；REQ-047 Extended 仍 🟣 Shaping） | PR #621 squash merge `aa88e5ea`；Original 评分 94（7 维 15+18+20+14+15+10+1）；Draft + Ready + 评分后 CI 全 SUCCESS；Phase 0 最高 L0 静态代码审计；保留 P3：3 个 stale `origin/*` remote-tracking ref 未擅自 prune | [PR #621](https://github.com/MarkDanile/MetaEduBase/pull/621)（mergeCommit `aa88e5ea`）/ [work-log](work-log.md) / [score 94](04-retrospectives/review-score-log.md) |
| 2026-09-09 | TASK-REQ-042-WS-S1-GOVERNANCE-CORRECTION：WS-S1 治理收口事实最小 pure-docs 纠正（active card 登记 + 当前进行中 placeholder + 最近完成分隔线 5 列修复） | 🟢 完成（pure-docs 子阶段；WS-S1 边界声明保留：真实 PG 正向 restore 仍不在 scope / 未运行 backfill / 未改 erase_available / 未触碰 metaedu/metaedu_test / AC-4/AC-5/AC-7/AC-8 仍保持未完成 / REQ-042 整体不翻 Done；不重开 WS-S1 / 不启动 WS-S2/S3/REQ-043/062/063/TD-085 / 不重新评分 / 不修改 review-score-log.md / Metrics / 历史评分行 / fact-audit / spec / plan / 技术债 / 后端 / migration / schema / registry / CI / 门禁） | 最小 pure-docs：active card 登记 commit + 当前进行中改回 `当前无活跃任务。` 占位 + 最近完成分隔线 1 段 → 5 段（`|------|` → `|------|------|------|------|------|`）；事实核对：`git rev-list --count 23d1c0c5..main = 2`（`235f4085` PR #618 + `ea1b51f8` PR #619，均为 squash merge）；最近完成表实际行数 19 → 20（closeout row 中「19 行」为 closeout 当时快照，本轮追加 1 行 = 20，仍 ≤ 20 窗口）；stale remote-tracking ref `origin/docs/req042-ws-s1-closeout` + `origin/feature/req042-ws-s1-durable-read-shell` **仍存在**，本任务未擅自 prune（仅如实登记） | [current-work active card](current-work.md) / [work-log](work-log.md) |
| 2026-09-09 | TASK-REQ-042-WS-S1：Workspace durable read/recovery 三栏 shell（只读，零写路径）+ 独立 closeout（TASK-REQ-042-WS-S1-CLOSEOUT 子卡） | 🟢 完成（WS-S1 + CLOSEOUT 子卡；REQ-042 仍 ⚫ Candidate — 仅交付 AC-1[不含 restore] / AC-2 读半边 / AC-6 desktop/mobile 布局 + restore UI/API wiring；AC-4/AC-5/AC-7/AC-8 保持未完成待 REQ-043 + REQ-047 Extended；WS-S2/S3/REQ-043/062/063/TD-085/erase_available/S5 wiring/capability flip 全部未启动） | PR #618 squash merge `235f4085`；评分 94 Original；382 unit + 66 Playwright + 45 unique；3 路 CI 全 SUCCESS；手动验收 9 项 pass | [PR #618](https://github.com/MarkDanile/MetaEduBase/pull/618)（mergeCommit `235f4085`）/ [work-log](work-log.md) / [score 94](04-retrospectives/review-score-log.md) |
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

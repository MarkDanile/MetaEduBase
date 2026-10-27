# REQ-064: 全局 UI 升级与可追溯设计规范

Status: 🟡 Doing
Priority: P1
Milestone: P3 / Web / Design System
Owner: S0 规划、S1a 共享基础与治理事实同步已交付；后续切片由集成者按独立任务分派
Created: 2026-10-22
Source: 用户要求以 TraeWork 为主参照、Doubao 补充 AI 聊天区域的局部体验，研究 16 套本机设计库，形成可交接且能隔离并行的实施依据。
Related: REQ-010 / REQ-020 / REQ-021 / REQ-022 / REQ-023 / REQ-042 / REQ-047 / REQ-052 / REQ-060 / REQ-061 / REQ-062 / REQ-063

## Problem

现有产品已经具有中性 light/dark 主题、语义 `ui-*` 层和权限化导航，但页面的尺寸、容器、问答排版和状态展示仍由局部实现决定。只向后续 Agent 提供“参考 TraeWork”无法保证一致性，也无法说明静态友商样例与本产品真实能力之间的边界。

用户的资料已放入项目的 `.local/design_libraries` 本地忽略目录，未跟随 Git 分支提交；新 worktree 需按参考矩阵准备副本并校验。此前多个 Agent 依次使用同一 checkout；后续并行必须隔离文件、共享层所有权、测试服务和集成顺序。

## Users / Scenarios

| 对象 | 需求 |
|---|---|
| 业务用户 | 清楚阅读问答、引用和问数结果；进入知识、资源、数据和应用页面时保持一致操作习惯 |
| 管理员 / Builder | 高密度列表、表单、详情和设置可扫描；权限和危险动作清楚 |
| 设计 / 实现 Agent | 能找到原始参考代码、区分可借鉴结构与演示逻辑，依照同一 Token/组件/验收标准开发 |
| 集成 / 评审 Agent | 知道每个切片的文件边界、前置能力、基线 commit 和验证证据，不靠对话追溯 |

## Scope

- TraeWork 为全站视觉主参照，覆盖外壳、导航、页面布局、字体、间距、控件、表格、表单、卡片、菜单、确认弹窗及默认/悬停/焦点/禁用/加载/空/错误/成功/无权限等状态。
- Doubao 为 AI 聊天区域的局部参考，覆盖输入区、消息排列、回答阅读区、消息操作与滚动体验；配色、字体、基础控件服从统一设计系统，确认弹窗不属于 Doubao 参考范围。区分原资料支持的结构/交互与本项目自行设计的适配，详见参考矩阵。
- 其他参考库只补充必要的信息组织，不建立独立视觉体系；涉及未被主参照覆盖的模式时仍使用统一 Token 和共享控件。
- 沿用 Vue 3、Tailwind、Lucide、现有 Token/`ui-*` 与双主题；不引入整套友商 CSS、React 运行时或品牌资产。
- 覆盖已交付路由和其子组件，包括应用、知识/数据、资源、管理、背调、分享与 403；登录页纳入全站视觉一致性验收与必要样式升级，保留既有鉴权、表单语义和 REQ-023 项目品牌约束；不能仅用兼容回归代表升级完成。
- 对未来 Memory、采集/报表、外部来源和审批/产物提供布局、状态、来源与权限呈现规则；业务功能仍由所属 REQ 交付。
- S0 规划阶段只交付文档、源文件校验清单和登记；后续 S1a 已按 plan 交付共享基础，业务页面、API、数据库和运行时仍不在该子切片修改范围。

## Acceptance

| ID | 验收结果 | 证据 |
|---|---|---|
| AC-1 | 16 套库都有实际来源、候选模式、取舍、可信度和必读文件；不冒称官方源码 | 参考矩阵 + 带 SHA-256 的 manifest；S0 已由 #664 合入，静态校验记录见 plan §7 |
| AC-2 | TraeWork 全站覆盖、Doubao 聊天局部范围、Token 映射、布局尺寸、完整状态与无障碍明确；确认弹窗归统一共享层 | 设计 spec；S1a 已有外壳截图与度量，S1 全量共享控件基线仍待完成 |
| AC-3 | 问答输入/消息/回答/操作/滚动区分原资料证据与项目适配；证据和 Workspace 能力遵循原契约，不借换样式启用未交付功能 | spec 问答状态矩阵 + 既有契约链接 |
| AC-4 | 每个现有路由及共享层有实施归属；未交付占位页不因升级上线 | plan 路由覆盖表 |
| AC-5 | 每个后续 Agent 有独立 worktree/分支、文件所有权、资料读取证明、测试环境和交接模板 | plan 并行协议与任务卡 |
| AC-6 | 全站（含登录页样式升级）light/dark、桌面/平板/手机、中文输入法、长内容、权限拒绝及错误状态通过验收；登录鉴权与表单语义保持 | 各切片 PR + S8 集成验证；REQ-064 整体尚未达成 |
| AC-7 | 未实现功能可据同一规范设计，公开 API 和领域状态所有权不被 UI 规范重定义 | spec 未来功能模式；新需求引用本 spec |
| AC-8 | 后续 S1 外壳与共享控件、S2 AI 聊天页面、S4 列表/表单/详情样板均提供可运行预览与同条件截图，由用户确认后批量扩展 | spec §6 / plan §3、§8；S1a 已交付 15 组改前/改后截图（共 30 张），S1 整体、S2、S4 节点未完成，不宣称本 AC 已全达成 |

## Dependencies / Next Step

- S0 规划已完成独立评审并由 PR #664 合入 main（mergeCommit `12f71df3e2d050e2d83167db3e121d56b58e9473`，Original 97）；S1a 共享基础已由 PR #667 合入 main（mergeCommit `7a73d62ddd2b6fc66c4c4964c38ba595b4c6ff70`，Original 96）；治理事实同步已由 PR #668 squash merge 入 main（mergeCommit `81e503294767f97dadcbb509242b273a1ce1815d`，mergedAt 2026-10-26T06:06:33Z，Original 95）；**后续 UI 切片路线与验收对齐已由 PR #670 squash merge 入 main（mergeCommit `b4dd5dfb214b9831346cd6fe90806d50668a8126`，mergedAt 2026-10-26T13:08:27Z，被评 head `f96e4055d28b67893c9716cc209ecdac8c9511bd`，Original 92/100，SCORE_BASE `1d297471f0010966c611d1e3271a02a4ae0aa0ec`）**。合并后治理收口已由 PR #671 squash merge 入 main（mergeCommit `5ebff34c5364f5d775bbca8bc9cd62a86870e517`，mergedAt 2026-10-27T08:58:09Z，Original 97/100，SCORE_BASE `58d1d68ca97ea3ec1c7f3b9837c4d030b5fd07d6`）。REQ-064 因已进入实现交付窗口而更新为 🟡 Doing；上述合入均不等于 REQ-064 整体 Done。
- S1a 仅交付共享 Token、应用外壳与 Playwright 端口隔离，未新增 UiComposer、未改业务页面；S1 整体未收口，S2–S8 未启动。下一步：按 [S4 强制分页候选确认与前置规划](../../02-delivery-plans/02-plans/2026-10-27-req-064-s4-pagination-prerequisite.md) 完成候选核查与前置规划，由用户在 **D-P1（目标页面与分页对象）**、**D-P2（总数 total 来源）**、**D-P3（验收证据形态）** 明确后才派发实施任务——S4 强制分页采用方案 A：保留 design spec §6 的强制验收要求，“调整验收口径”未采用；S5 技能/MCP 审计弹窗分页只作参考、不自动纳入 S4 候选；本规划不实现业务分页。**S4 强制分页门尚未闭合**（S4 候选范围内无合格真实候选），不宣称该项通过，**S6/S7 不得派发**；S3 目录/文件归属人由用户指定，用户已明确暂不指定，S3 继续阻塞；S1b 与 S2–S8 未启动，phase-D/E 与生产 backfill 未启动，三类用户视觉确认未执行。
- TD-114 前置保持已满足：[契约 §11](../../02-delivery-plans/01-specs/2026-10-19-td-114-agent-identity-bootstrap-contract.md#11-td-114-完成判据) 的 A+B 组证据由 #659/#663 交付，#665 治理收口已合入 main `a6fc4877`；TD-114 保持 🟢 完成，TD-115 保持 ⚫ 待办。
- REQ-042 保持 ⚫ Candidate；phase-D/E、WS-S3 和 REQ-047 Extended 的实现继续走各自契约与验收。S0/S1a 合入不自动推进 phase-D/E、生产 backfill 或启用未交付能力。
- 本任务 worktree 交接事实（完成门禁第 13 条）：规划与本次收口均在主 checkout `/Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase` 进行，实时 `git worktree list --porcelain` 核验**仅 1 个注册 worktree**：同一主 checkout 在规划阶段先后使用分支 `docs/req-064-slice-alignment`、在收口阶段使用分支 `docs/req-064-slice-closeout`（worktree 一次只 checkout 一个分支，两阶段先后发生，非同时持有）。**决定保留、不退休**：该 checkout 为仓库主 checkout，后续 S4 分页规划与 REQ-064 切片仍需使用；后续清理条件为——由独立专项任务先核验 PR 合并状态、未发布提交、忽略资产归属与引用依赖后再处置。local branch `docs/req-064-slice-alignment`（已合入 main，停在 `f96e4055`）与 remote branch `origin/docs/req-064-slice-alignment`（同 SHA）**均保留**，本轮不删除任何分支或 refs；worktree 退休与分支删除是两件独立资源，不得混同。
- 新 worktree 仍从依赖已合并的明确提交创建，不依赖、复制或提交他人的未提交内容。PR #666 已合入 main `f3f87fefb88cedc2cfe99f583f7a8c64c9ec66b6`，Worktree 退休与 ignored 资产核验规则已生效；PR #666 自身 worktree 与分支退休另案核验，本需求事实同步不执行清理。

## Delivery Links

- [设计 spec](../../02-delivery-plans/01-specs/2026-10-22-req-064-ui-design-system.md)
- [参考矩阵与资料检查](../../02-delivery-plans/01-specs/2026-10-22-req-064-reference-matrix.md)
- [源文件 manifest](../../02-delivery-plans/01-specs/2026-10-22-req-064-reference-manifest.json)
- [实施计划与 Agent 接力模板](../../02-delivery-plans/02-plans/2026-10-22-req-064-ui-upgrade-plan.md)
- [后续 UI 切片路线与验收对齐](../../02-delivery-plans/02-plans/2026-10-26-req-064-ui-slice-roadmap.md)
- [工作台](../../03-engineering-governance/current-work.md) / [Backlog](../04-backlog.md)

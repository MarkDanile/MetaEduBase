# REQ-064 后续 UI 切片路线与验收对齐

日期：2026-10-26。类型：product planning / pure-docs。本文件是**规划事实源**，不是 UI 设计稿或实现任务书。

边界：本文件不实现界面、共享组件、UiComposer 或业务页面；不派发或启动 S1b、S2–S8；不启动 REQ-042 phase-D/E、生产 backfill；不顺带执行远程分支、worktree 或 refs 清理；不宣称任何视觉验收、真实 PG 或真实 LLM 验收已完成。

依据：[REQ-064 requirement](../../01-product-planning/05-requirements/REQ-064-global-ui-upgrade.md)、[设计 spec §6](../01-specs/2026-10-22-req-064-ui-design-system.md)、[实施计划 §1–§6、§8](2026-10-22-req-064-ui-upgrade-plan.md)、[参考矩阵](../01-specs/2026-10-22-req-064-reference-matrix.md)。冲突时以本文件为后续派发依据，但**不得弱化 design spec §6 的三类用户视觉确认门**；plan §3–§6 保留为历史基线。

## 0. 开工基线核验

| 事实 | 当前值 | 证据 |
|---|---|---|
| REQ-064 状态 | 🟡 Doing，非 Done | requirement `Status:`、Backlog REQ-064 行 |
| S0 规划 | 已合入 #664，mergeCommit `12f71df3`，Original 97 | plan §7、评分总账 |
| S1a 共享基础 | 已合入 #667，mergeCommit `7a73d62d`，Original 96 | plan §8、评分总账 |
| 治理事实同步 | 已合入 #668，mergeCommit `81e50329`，Original 95 | plan §1、评分总账 |
| 合并后收口 | 已合入 #669，mergeCommit `6ad038d8`，Original 95 | work-log、评分总账 |
| main / origin/main / 本地 main | `6ad038d8829f3383cb75a06757688d97163c13da` | 实时 git 核验 |
| 开放 PR | 0 个 | 实时 `gh pr list` |
| worktree | 1 个（主 checkout，工作区 clean） | `git worktree list --porcelain` |
| 远程分支 | 46 个；main 受保护 | 实时 `git ls-remote`、branch protection |
| TD-114 / TD-115 / REQ-042 | 🟢 完成 / ⚫ 待办 / ⚫ Candidate | technical-debt、REQ-042 requirement、Backlog |
| phase-D/E、生产 backfill | 未启动 | requirement、plan、Backlog |

S1a 的已交付内容与证据边界（不得扩大解释）：

- 交付物：Token/themes/components、LayoutView、Playwright 配置与截图采集、e2e README；实现净 diff 8 文件 +523/-25，含评分行后 9 文件 +524/-25。
- 明确未交付：**UiComposer、任何业务页面**；未改 router/nav/permissions、stores/services、API/DTO、数据库或后端。
- 已记录证据（均为 #667 当时实测，本规划未重跑）：Node `v20.20.2`、pnpm `9.15.0`；lint 0 errors/28 warnings；typecheck、build 通过；全量前端 Vitest 40 文件 / 382 用例；`METAEDU_E2E_PORT=3101 … test:e2e navigation` 55 passed；16 库 / 240 文件 hash 校验 `problems=0`；15 组同条件改前/改后截图共 30 张。
- 保留缺口：**未建立自动像素 diff 基线、未做人工点击流、未做多 OS 字体渲染对比、未做真实 PG 或真实 LLM 验收**；S1a 的截图不替代 design spec §6 的 S1/S2/S4 视觉确认节点。

## 1. 不可变约束（后续派发必须逐条满足）

1. **三类用户视觉确认门不可弱化**：S1 外壳与共享控件、S2 AI 聊天页面、S4 列表/表单/详情样板。代码检查通过不能代替用户视觉确认；S1a 的截图交付不替代这些节点（design spec §6）。
2. 视觉确认证据形式固定为：可运行预览 + 同一 OS/浏览器/主题/视口/数据/角色下的改前/改后截图 + worktree/commit + 启动命令 + 独占开发端口与 URL + 数据/角色准备 + fixture 标注；**用户确认记录绑定 commit 与预览/截图并写入对应切片 PR**，确认后才批量扩展对应样式；确认后的视觉修改需重新确认受影响样板。
3. 视口与主题矩阵：1440×900、1280×800、1024×768、390×844，light/dark 两套；320px 宽与 200% 缩放附加检查溢出、焦点、主要动作；Workspace 另需实际容器断点两侧检查。登录页升级前后截图与适用状态验收保留，不另设第四类样板节点。
4. 语义/几何硬条件：无全页横向溢出、无文字遮挡、无焦点丢失、无错误动作启用、无来源丢失；主按钮/状态/圆角/字体来自规范；对话框含 role/aria-modal、焦点约束、Esc 与关闭后焦点返回；详情抽屉同样验证。
5. 可审查链：参考库路径+hash → selector/行为 → 采用/适配差异 → Token → Vue 组件/页面 → fixture/截图/交互测试。不得用“参考 TraeWork”替代该链。
6. 文件所有权：共享层只有一个 owner；`assets/css/`、`components/`、`LayoutView.vue`、UiComposer、`playwright.config.ts` 与公共 e2e fixture 归共享层；`package.json`/锁文件、`app/router.ts`/nav/permission、`stores/`、`services/`、shared schema、backend、CI 门禁不在页面切片 allowlist；发现功能问题登记所属 REQ/BUG，不在 UI PR 扩范围。
7. 环境隔离：每切片独立 worktree 与明确 base SHA，不复制他人脏目录、不共享 `node_modules`/dist/测试输出；端口默认 S1=3101、S2=3102…S8=3108，`METAEDU_E2E_PORT` + baseURL/server URL 同源 + `--strictPort` + `reuseExistingServer=false`；占用直接失败，不杀进程、不自动换端口。新增 e2e 文件须匹配 `*-desktop.spec.ts` / `*-mobile.spec.ts` / `*-shared.spec.ts` 发现规则，平板视口在 desktop/shared 内显式 setViewportSize。
8. 停止边界：本路线任何阶段都不得顺带启动 phase-D/E、生产 backfill、远程分支/worktree/refs 清理，也不得把未交付能力画成已交付按钮。

## 2. S1 尚未收口的具体缺口（S1a ≠ S1）

| 编号 | 缺口 | 事实依据 |
|---|---|---|
| G1 | **UiComposer 未交付**：受控 `modelValue`、`mode: ready/busy/readonly/unavailable`、`canSubmit/canStop/placeholder/hint/inputLabel`、事件 `update:modelValue` / `submit` / `stop`、附件与工具插槽；提交须同时满足 `mode === "ready" && canSubmit && modelValue.trim().length > 0` 且输入法非 composing；`ready + canSubmit=false` 仍可编辑草稿；`busy` 仅在 `canStop` 时允许停止；组件不请求 API、不选模型、不管理 Conversation、不推断租户权限 | design spec §3；plan §8 明确“未新增 UiComposer” |
| G2 | 共享控件**全状态覆盖不足**：default、hover、focus-visible、active/selected、disabled、loading、empty、error、success、无权限等适用状态，及表格、表单、卡片、菜单、确认弹窗的统一契约 | design spec §2.1 |
| G3 | `.ui-panel:hover` 抬升效果未按 spec 修正（该共享类同时用于静态容器与可交互行，32 处使用点） | design spec §2.1；S1a 遗留风险 |
| G4 | `.ui-input` 行高未施加（82 处使用点，直接改共享类会改变全站输入框高度） | S1a 遗留风险；本规划列为 D1 待决项 |
| G5 | 代表性控件的可运行预览与同条件截图未覆盖 S1 全量共享控件（S1a 仅外壳/导航与部分控件） | design spec §6 S1 节点范围 |
| G6 | **S1 用户视觉确认未完成**，因此 S1 不能视为收口 | design spec §6；S1a 合并不替代该门 |
| G7 | 证据缺口保留：像素级自动基线、人工点击流、多 OS 字体对比、真实 PG/真实 LLM 均未做 | plan §8；不得宣称已完成 |
| G8 | 遗留主题值（paper/liquid/ink/navy/notion）目前仅验证回落 light 的启动冒烟；是否扩展为正式主题或清理任务属未决项（D7） | S1a 交付记录 |

## 3. 路线与排序理由

| 阶段 | 内容 | 允许进入的条件 | 退出后才允许 |
|---|---|---|---|
| A. 路线对齐（本文件） | 切片顺序、范围、依赖、验收门、待决项 | 已完成基线核验（本文件 §0） | 用户对路线与 D1–D8 作出裁决（门 A） |
| B. S1b 共享层收口 | 关闭 G1–G6；G7/G8 按裁决处理 | 门 A 通过 + S0/S1a 已合入 + TD-114 完成 | S1b 技术验收通过 + **S1 用户视觉确认并合入** → 才允许 C |
| C. 页面并行窗口 | S2 AI 问答、S3 Workspace、S4 知识/资源/数据、S5 应用与能力中心 | S1b 已合入且 S1 视觉确认完成；S3 另需互斥解除（D5） | S2/S4 各自视觉确认门通过后，S4 样板合入 → 才允许 D 阶段；S2/S3/S5 无新增视觉门但须沿用已确认基线 |
| D. 二级页面 | S6 管理与模板、S7 背调与外围（含登录） | S1b 合入 + **S4 列表/表单/详情样板用户确认并合入** | S6/S7 合入 → 才允许 E |
| E. 集成与收口 | S8 全路由审计、视觉矩阵、三类确认记录核对 | S2–S7 全部合入 | required checks 通过、无遗漏路由后，才可讨论 REQ-064 整体完成度 |

排序理由：

1. **共享接口唯一**：UiComposer、共享 CSS、外壳与公共 fixture 只有一个 owner，先收口可避免各页面复制公共实现。
2. **视觉基线先行**：design spec §6 要求 S1/S2/S4 先经用户确认再批量扩展，故把视觉门放在对应切片合入前，而非全站完成后补确认。
3. **样板先行**：S4 的列表/表单/详情样板决定 S6/S7 的形态，先确认样板可减少二级页面返工。
4. **互斥串行**：S3 与 WS-S2 phase-D/E、WS-S3 同目录任务不得并行，须显式解除互斥后进入窗口。
5. **集成最后**：S8 只有在 S2–S7 合入后才做全路由与三类确认记录核对，避免用局部通过冒充全站完成。

默认合入次序：S1b → S2 → S3 → S4 → S5 → S6 → S7 → S8。S2/S3/S4/S5 可在 C 窗口并行开发，但合入顺序由集成者按依赖记录；若某切片因未交付能力阻塞，其他独立切片可继续，须显式记录调整后的次序。

## 4. 切片卡片

### 4.1 S1b — S1 剩余共享层收口

- **目标**：关闭 G1–G6，使 S1 具备可派发页面切片的共享接口与已确认视觉基线。
- **包含**：UiComposer（G1 接口与提交条件）；共享控件状态矩阵（G2）；`.ui-panel:hover` 与 `.ui-input` 行高按 D1 裁决处理（G3/G4）；S1 全量共享控件的可运行预览与同条件截图（G5）；双主题、键盘、导航、旧主题回落兼容；Playwright 端口隔离沿用 S1a 配置。
- **排除**：任何业务页面、router/nav/permission 语义、stores/services/API/DTO、数据库、后端、CI 配置、依赖与锁文件；不新增流式/语音/审批能力；不把 S1a 已交付内容重复实现。
- **前置**：门 A 通过；S0/S1a 已合入；TD-114 完成；共享层 owner 与独立 worktree/端口（3101）已分配。
- **可并行**：无。共享层补丁由一个 owner 顺序提交，其他 Agent 不写共享层文件。
- **阻塞**：D1/D6/D8 未裁决；共享层文件被其他任务占用；参考库 hash 校验失败。
- **交付物**：共享层 diff、UiComposer 及测试、参考→Token→组件映射、状态矩阵、预览启动命令与 URL、同条件前后截图与结构化度量、验证命令与退出码、证据层级声明。
- **自动化验证**：`pnpm --filter @metaedu/web lint`、`typecheck`、`build`、全量前端 Vitest（theme/Layout/NavBreadcrumb/UiComposer）、`METAEDU_E2E_PORT=3101 pnpm --filter @metaedu/web test:e2e navigation`、`scripts/check-engineering-docs --full`、`git diff --check`。Node 20 环境（与 CI 一致）。
- **技术验收（非视觉）**：props/events 兼容；提交与停止条件符合 G1；default/hover/focus-visible/disabled/loading/empty/error/success/无权限等适用状态可复现；焦点不丢、键盘可达、reduced-motion 生效；交互边界对比度 ≥3:1、正文 ≥4.5:1；端口占用负例失败退出且不杀进程；无业务行为变化。
- **用户视觉确认（必须）**：S1 外壳与共享控件的可运行预览 + 同条件前后截图（含按钮/输入/表格/表单/卡片/菜单/确认弹窗及适用状态、浅色/深色与窄屏）；用户确认记录绑定 commit 并写入 S1b PR。
- **退出条件**：自动化与技术验收通过 + 用户视觉确认完成 + PR 合入。**只有此时才称 S1 收口**，才允许进入 C 窗口。

### 4.2 S2 — AI 问答页面

- **目标**：在已确认共享基线上交付 AI Chat 视觉与阅读体验，保留现有能力边界。
- **包含**：采用 UiComposer 的输入区、消息排列、长回答/代码/表格排版、已交付消息操作、建议问题、错误/停止/引用与滚动；输入区自动增高至 160px 后内部滚动；底部“回到最新”与阅读位置保持；移动键盘场景。
- **排除**：不新增流式、语音、上传、模型切换；不改 services/stores、共享 Markdown/CSS/EvidenceCard/DocumentSourceList；不造未交付工具按钮；共享组件缺口须先由共享层补丁解决。
- **前置**：S1b 合入且 S1 视觉确认完成；参考 TW-03/DB-01/DB-02/DB-03，CL-01 仅作元信息组织补充。
- **可并行**：可与 S3/S4/S5 在 C 窗口并行（不同目录、不同 worktree/端口 3102）。S2 用户确认前不得把其聊天模式扩展到其他对话表面。
- **阻塞**：共享层接口未稳定；参考库 hash 失败；真实能力缺口（如中止、引用）需要新契约时退回所属 REQ。
- **交付物**：`views/ai-chat/` diff 与新增 `e2e/req064-chat-*`、参考→组件映射、IME/滚动/错误/停止状态证据、预览与截图、验证命令与退出码。
- **自动化验证**：lint/typecheck/build、`pnpm --filter @metaedu/web test -- src/views/ai-chat`、既有 EvidenceCard/DocumentSourceList 测试、新增 chat e2e（`METAEDU_E2E_PORT=3102 … test:e2e req064-chat`）、docs gate、diff check。
- **技术验收**：中文 IME composing 不发送；空白不可提交；多行与回缩；请求身份保持；停止/恢复不伪造状态；文件链接与引用安全；无证据提示保留；无全页横向溢出；未交付能力保持门控。
- **用户视觉确认（必须）**：输入区、消息排列、长回答/引用、已交付消息操作、滚动/错误/停止与手机键盘场景的可运行预览与同条件截图；确认记录写入 S2 PR。
- **退出条件**：自动化与技术验收通过 + 用户视觉确认完成 + PR 合入；之后才允许把该聊天模式批量扩展到其他对话表面。

### 4.3 S3 — Workspace 展示

- **目标**：三栏与窄屏展示统一，消费当时已交付的真实能力。
- **包含**：会话列表/草稿/已有 Run 详情展示、容器断点（≥1180px 三栏、768–1179px 两栏+抽屉、<768px 单面板 Tab）、选中会话后进入消息面板、显式点击运行详情才切换运行面板、resize 不重建 Conversation/Run。
- **排除**：不改 workspace store/服务/事件协议；不实现 SSE、cancel/steer、审批或产物协议；未交付按钮仍门控；不与 WS-S2 phase-D/E 或 WS-S3 同目录任务并行。
- **前置**：S1b 合入且 S1 视觉确认完成；D5 互斥解除已书面确认；参考 TW-03/TC-01 与 REQ-042 契约。
- **可并行**：可与 S2/S4/S5 并行（端口 3103），但**不得**与另一正在修改 Workspace 的 Agent 同时开工。
- **阻塞**：互斥未解除、共享层接口未稳定、需要新协议能力。
- **交付物**：`views/agent-workspace/` diff 与 workspace e2e、容器断点证据、草稿/选择/恢复回归结果、预览与截图。
- **自动化验证**：workspaceDraft/workspace store 既有测试（只读回归）、WorkspaceView 测试、workspace e2e、lint/typecheck/build、docs gate、diff check。
- **技术验收**：草稿隔离、会话切换不丢草稿、显式运行详情、归档/恢复、禁用发送、各容器断点；未开放发送保持禁用并说明原因；不以视觉禁用代替服务端授权。
- **用户视觉确认**：无独立视觉确认门，但须复用 S1 已确认基线，并在 PR 提供同条件截图供审查。
- **退出条件**：自动化与技术验收通过 + PR 合入；不实现 SSE/审批协议。

### 4.4 S4 — 知识、资源与数据（含 S4 样板门）

- **目标**：交付 knowledge/resource/database 全部已交付视图与子组件的统一布局，并提供列表/表单/详情样板。
- **包含**：标题/筛选/列表/表格/空错载/分页/详情与来源辅助区；先交付 D3 裁决的首批样板页面及同条件截图，再扩展同类页面；长表格与问数结果的单位、期间、来源、空态。
- **排除**：不改共享 FieldEditor/TableRenderer/KGGraph 等（由共享层 owner 按已定义接口修正）；不改 DTO、权限、后端；不顺手删除旧文件。
- **前置**：S1b 合入且 S1 视觉确认完成；D3 首批样板组合已裁决；参考 TW-02/TW-04/VE-01/VE-02。
- **可并行**：可与 S2/S3/S5 并行（端口 3104）；S6/S7 必须等待 S4 样板确认。
- **阻塞**：样板组合未裁决、共享组件缺口、数据/上传/图谱真实行为需要新契约。
- **交付物**：目录内页面与子组件 diff、`e2e/req064-data-*`、样板预览与截图、搜索/分页/上传/详情/图谱/问数原行为回归证据、验证命令与退出码。
- **自动化验证**：对应页面 Vitest + 切片 e2e、lint/typecheck/build、docs gate、diff check。
- **技术验收**：搜索/筛选/排序/分页、上传、详情、图谱、问数原行为不变；空/错/加载/无权限状态完整；双主题与长表格、长 URL 局部滚动；表单校验、保存/取消与危险确认行为保持。
- **用户视觉确认（必须）**：列表筛选/分页、表单校验/保存、详情正文/来源/辅助面板及完整空/错/加载状态的可运行预览与同条件截图；确认记录写入 S4 PR。
- **退出条件**：自动化与技术验收通过 + **S4 样板用户确认并合入** → 才允许派发 S6/S7；其余同类页面在样板确认后批量迁移。

### 4.5 S5 — 应用与能力中心

- **目标**：ai-apps、skill-registry、mcp-registry 页面统一为可读、可扫描的卡片或紧凑列表。
- **包含**：筛选、描述、状态与操作分层；真实 Registry 状态、角色访问、错误/空态与卡片密度。
- **排除**：不写 admin 目录、导航/角色判断和 Registry 服务；不复刻示例假计数。
- **前置**：S1b 合入且 S1 视觉确认完成；参考 TW-05/TC-01。
- **可并行**：可与 S2/S3/S4 并行（端口 3105）。
- **阻塞**：Registry 真实状态或权限缺口需要后端变更（退回所属 REQ）。
- **交付物**：页面 diff、`e2e/req064-apps-*`、真实状态与权限证据、预览与截图、验证命令与退出码。
- **自动化验证**：对应页面 Vitest + 切片 e2e、lint/typecheck/build、docs gate、diff check。
- **技术验收**：真实 Registry 状态、角色访问、错误/空态、卡片密度一致；无虚构计数或假入口。
- **用户视觉确认**：无独立视觉确认门；沿用 S1 已确认基线并提供同条件截图。
- **退出条件**：自动化与技术验收通过 + PR 合入。

### 4.6 S6 — 管理与模板

- **目标**：admin 目录的表单与模板编辑体验统一。
- **包含**：分组标签、字段帮助、就地错误、底部操作区、模板字段/编辑/导入/校验显示、危险确认。
- **排除**：不改共享组件/DTO/权限；数据模板仍归知识与数据导航；不改后端校验语义。
- **前置**：S1b 合入 + **S4 列表/表单/详情样板用户确认并合入**；参考 TW-02/TW-04/VE-01/VE-02。
- **可并行**：可与 S7 并行（端口 3106），前提是 S4 样板已合入。
- **阻塞**：S4 样板未确认；共享表单组件缺口。
- **交付物**：admin 页面 diff、`e2e/req064-admin-*`、表单错误与焦点证据、保存/取消/危险确认回归、预览与截图。
- **自动化验证**：对应页面 Vitest + 切片 e2e、lint/typecheck/build、docs gate、diff check。
- **技术验收**：表单错误定位、焦点管理、保存/取消、危险确认、权限回归；敏感字段不回显；取消不提交。
- **用户视觉确认**：无新增样板门；须复用 S4 已确认样板并提供同条件截图。
- **退出条件**：自动化与技术验收通过 + PR 合入 → 才允许 S8。

### 4.7 S7 — 背调与外围页面（含登录）

- **目标**：due-diligence、HomeView、share、ForbiddenView 与登录页必要样式升级，保持鉴权与品牌约束。
- **包含**：报告/证据/制审行为不变的展示统一；登录页字体/间距/控件/表单状态升级与升级前后截图；分享 token 路由与首页权限回归；REQ-023 品牌约束保留。
- **排除**：不改认证服务、store、路由守卫；不改背调领域服务；公共控件缺口由共享层修。
- **前置**：S1b 合入 + S4 样板确认并合入；参考 TW-01/TW-02、REQ-023、VE-02 及报告/来源模式。
- **可并行**：可与 S6 并行（端口 3107）。
- **阻塞**：S4 样板未确认；鉴权或品牌约束需要新决策（退回 REQ-023 相关裁决）。
- **交付物**：页面与登录 diff、对应 e2e、报告/证据/制审回归、登录升级前后截图与适用状态、预览与验证命令。
- **自动化验证**：对应页面 Vitest + 切片 e2e、lint/typecheck/build、docs gate、diff check。
- **技术验收**：报告/证据/制审行为不变；登录鉴权、校验、提交、错误与跳转语义保持；分享 token 路由与首页权限回归；品牌差异记录完整。
- **用户视觉确认**：登录属 S8 全站视觉一致性的一部分，**必须**提供升级前后截图与适用状态验收；不另设第四类样板节点。
- **退出条件**：自动化与技术验收通过 + 登录升级截图齐备 + PR 合入 → 才允许 S8。

### 4.8 S8 — 集成与收口

- **目标**：全路由审计与全站验收矩阵，确认无遗漏路由与确认记录。
- **包含**：全路由/角色/主题/视口矩阵（含登录升级与 `/share/:token`、`/403`、教育占位路由的 feature/权限隐藏、旧链接重定向）、三类用户确认记录核对、未来功能接入核对、最终文档与状态更新。
- **排除**：不借集成名义新增页面功能或改变协议；不把占位页当成已交付产品；不清理 worktree/分支/refs。
- **前置**：S2–S7 全部合入；每批从最新 router 重新生成路由清单并与 plan §4.1 做差集，新增路由由集成者明确归属。
- **可并行**：无（集成者单独执行）。
- **阻塞**：任一切片未合入、用户确认记录缺失、路由清单差集未归属。
- **交付物**：全量前端 Vitest + 全量 Playwright 结果、lint/typecheck/build、docs/diff 门禁、完整路由/角色/主题/视口矩阵、三类确认记录清单、证据层级声明与回滚方式。
- **自动化验证**：全量前端 Vitest + 全量 Playwright、lint/typecheck/build、`scripts/check-engineering-docs --full`、`git diff --check`。
- **技术验收**：样板一致、无遗漏路由、required checks 通过、无横向溢出/文字遮挡/焦点丢失/错误动作启用/来源丢失。
- **用户视觉确认**：核对 S1/S2/S4 三类确认记录是否绑定 commit 且覆盖受影响样板；登录升级截图与全站一致性验收记录齐全。
- **退出条件**：全站验收矩阵通过 + required checks 通过 + PR 合入后，才可评估 REQ-064 整体完成度；在此之前 REQ-064 保持 Doing。

## 5. 验收分层与证据口径

| 层级 | 内容 | 不得混同 |
|---|---|---|
| A. 自动化测试 | lint/typecheck/build、相关与全量 Vitest、对应 Playwright、docs gate、`git diff --check`；CI 需区分实跑、no-op、skipped | no-op / skipped 不得写成前后端或 full hermetic 测试通过 |
| B. 技术验收（非视觉） | 行为保持（props/events、权限、路由、store/service）、可访问性（焦点、aria、reduced-motion、对比度）、端口隔离、状态矩阵、草稿/请求身份/停止恢复、无业务 API 变化 | 技术验收通过不等于用户视觉确认完成 |
| C. 用户视觉确认 | 仅 S1（S1b 承载）、S2、S4 三门：可运行预览 + 同条件前后截图 + commit 绑定 + 用户确认记录写入对应 PR；S7 登录与 S8 全站一致性按 spec §6 验收 | 未确认前不得批量扩展；S1a 的 30 张截图不替代这三门 |
| D. 不可宣称项 | 像素级自动基线、人工点击流、多 OS 字体对比、真实 PG、真实 LLM、phase-D/E、生产 backfill、REQ-064 Done | 未实际执行不得写成已完成 |

## 6. 需要用户决定的问题（门 A 待裁决项）

| 编号 | 问题 | 选项与影响 |
|---|---|---|
| D1 | `.ui-input` 行高（82 处使用点）与 `.ui-panel:hover`（32 处使用点）的处理路径 | A：S1b 内统一改共享类——一致性好，但全站输入框/面板高度与悬停行为变化，需要全站回归与更宽截图面；B：新增语义 token 与 opt-in 类，页面切片逐步采用——风险小、节奏慢、期间存在两套表现；C：拆 S1b-1（UiComposer 与控件）与 S1b-2（共享类风险修正）——多一次评审但风险面更清晰。**未裁决前不得修改这两处共享类。** |
| D2 | UiComposer 先接入 S2（AI Chat）还是 S3（Workspace），以及 C 窗口是否允许二者并行 | A：先 S2，聊天模式样板先稳定，S3 随后；B：先 S3，若 Workspace 展示阻塞更重，AI Chat 随后；C：S2/S3 在共享接口冻结后并行，合入顺序由集成者定。影响并行窗口工作量与视觉确认顺序。 |
| D3 | S4 首批“列表/表单/详情”样板页面组合 | A：knowledge 列表 + resource 详情 + database 表单/编辑；B：knowledge 列表 + data templates 编辑 + resource 详情；C：由集成者按当前路由与共享组件复用度另选一组。决定 S6/S7 的样板来源、截图范围与返工面。 |
| D4 | 视觉证据是否引入像素级自动基线 | A：沿用“同条件前后截图 + 结构化度量 + 用户确认”，不建基线（现状）；B：新增像素级基线（初始 `maxDiffPixelRatio: 0.001`），需新增基线资产、跨 OS 字体差异处理与维护成本，且不得为通过而放宽阈值或批量更新快照。 |
| D5 | S3 与 WS-S2 phase-D/E 的互斥解除条件 | 需明确 workspace 目录当前归属人、phase-D/E 是否排期，以及何种书面条件下允许 S3 进入 C 窗口；未确认前 S3 不派发。 |
| D6 | S1b 单 PR 还是按风险再拆 | A：单一 S1b PR（UiComposer + 共享 CSS + 预览证据）；B：UiComposer 与共享 CSS 风险修正分 PR，降低共享层单 PR 风险面但增加一次评审与合入顺序依赖。 |
| D7 | 遗留主题值（paper/liquid/ink/navy/notion）的范围 | A：仅保留回落 light 的启动冒烟（现状，不新增主题切换项）；B：另立独立任务评估清理或正式支持，超出本路线范围，不在本规划内实施。 |
| D8 | 用户视觉确认的记录形式与确认人 | A：在对应切片 PR 讨论中绑定 commit 的确认记录（现状）；B：另增独立 sign-off 文档记录确认人、时间、commit 与截图清单。影响 S8 的确认记录核对方式。 |

门 A 通过的定义：用户对路线顺序、S1b 范围、D1–D8 的取舍作出明确裁决；未裁决项保持“不得修改/不得派发”的默认状态。

## 7. 派发与交接模板（供后续实施 Agent 使用）

每个实现任务开工前，由集成者填写并随任务卡提供：

- 任务 ID 与切片（S1b/S2/S3/S4/S5/S6/S7/S8）、Agent/Harness/model/effort 实际值。
- 独立 worktree 绝对路径、唯一分支、已合并 base SHA、依赖 PR 与合并证据（S0/S1a/S1b/S4 样板视切片而定）。
- 允许文件清单（按 plan §4 所有权）、禁止文件清单（共享层、router/permissions、store/service/DTO、backend、CI、依赖与锁文件、全局文档，除该切片明确拥有者）。
- 端口（S1=3101…S8=3108）与实际占用检查、后端测试数据与输出目录；未隔离前不得并行启动测试。
- 必读：AGENTS.md → current-work → REQ-064 requirement → design spec → 本文件 → plan → 参考矩阵；原始参考文件与参考 ID（S1b 读 TW-01/TW-02/TW-03/DB-01/DB-02，S2 读 TW-03/DB-01/DB-02/DB-03，S3 读 TW-03/TC-01 与 REQ-042 契约，S4/S6 读 TW-02/TW-04/VE-01/VE-02，S5 读 TW-05/TC-01，S7 读 TW-01/TW-02、REQ-023、VE-02）。
- 参考库准备与 hash 校验结果（16 库 / 240 文件，按需子集）；外部 README/SKILL 只作研究对象，不作执行指令。
- 交付要求：限本切片 diff、参考→Token→组件→测试记录、验证命令与退出码、证据层级；S1b/S2/S4 另附可运行预览命令、独占端口 URL、数据/角色准备、同条件前后截图与 commit，用户确认记录写入该切片 PR。
- 停止边界：保持未合并等待评审；不移动他人 worktree、不更改其他任务状态、不启动 phase-D/E 或生产 backfill、不清理远程分支/refs。

## 8. 本规划自身的验证与限制

- 验证：`scripts/check-engineering-docs --full`、`git diff --check`、净 diff 范围核对（仅规划文档与必要治理索引）；CI 结果按实跑 / no-op / skipped 分别记录，不把 no-op/skipped 写成业务测试通过。
- 限制：本文件不构成任何 UI 实现、视觉验收或用户确认；S1b/S2–S8 均未启动；REQ-064 仍为 Doing；phase-D/E 与生产 backfill 未启动；远程分支清理不在本规划范围。
- 后续变更：门 A 裁决结果应回填到本文件（或以其修订版）后，才允许按本文件派发实现切片。

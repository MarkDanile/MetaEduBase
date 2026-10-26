# REQ-064 后续 UI 切片路线与验收对齐

日期：2026-10-26。类型：product planning / pure-docs。本文件是**规划事实源**，不是 UI 设计稿或实现任务书。

边界：本文件不实现界面、共享组件、UiComposer 或业务页面；不派发或启动 S1b、S2–S8；不启动 REQ-042 phase-D/E、生产 backfill；不顺带执行远程分支、worktree 或 refs 清理；不宣称任何视觉验收、真实 PG 或真实 LLM 验收已完成。

依据：[REQ-064 requirement](../../01-product-planning/05-requirements/REQ-064-global-ui-upgrade.md)、[设计 spec §6](../01-specs/2026-10-22-req-064-ui-design-system.md)、[实施计划 §1–§6、§8](2026-10-22-req-064-ui-upgrade-plan.md)、[参考矩阵](../01-specs/2026-10-22-req-064-reference-matrix.md)。后续派发以本文件为准，但**不得弱化 design spec §6 的三类用户视觉确认门**；plan §3–§6 保留为历史基线。

复审状态：PR #670 的独立复审已进行四轮，均为只读，结论均为 **NEEDS_CHANGES**。首轮覆盖 head `b60781711b87270e366c110a70541577c82f10c9`（P1×8、P2×2，P0/P3=0）；第二轮覆盖 head `10d79023e15e78f678ea01b42e667ed5d0dad612`（P1×1、P2×1，P0/P3=0）；第三轮覆盖 head `e7e2a341c7d1b89b4f1e00213cc6bf3f8b0c4e68`（P1×1，P0/P2/P3=0）；第四轮覆盖 head `92fd6060cce830fb358a5dfec6dafa94be52f2ad`（P0=0、P1=0、P2×2、P3×6，确认第三轮 P1-1 已实质闭合）。本版按第四轮完整复审原文逐项返修，回填用户已确认的 D1–D8；本次返修产生新 head，旧 head 的复审结论不自动覆盖新提交，必须等待针对最新 head 的独立复审。

## 0. 开工基线核验

| 事实 | 当前值 | 证据 |
|---|---|---|
| REQ-064 状态 | 🟡 Doing，非 Done | requirement `Status:`、Backlog REQ-064 行 |
| S0 规划 | 已合入 #664，mergeCommit `12f71df3`，Original 97 | plan §7、评分总账 |
| S1a 共享基础 | 已合入 #667，mergeCommit `7a73d62d`，Original 96 | plan §8、评分总账 |
| 治理事实同步 | 已合入 #668，mergeCommit `81e50329`，Original 95 | plan §1、评分总账 |
| 合并后收口 | 已合入 #669，mergeCommit `6ad038d8`，Original 95 | work-log、评分总账 |
| main / origin/main / 本地 main | `6ad038d8829f3383cb75a06757688d97163c13da` | 实时 git 核验 |
| 规划 PR #670 | OPEN / Draft；已进行四轮独立复审，结论均为 NEEDS_CHANGES（第四轮：P0=0、P1=0、P2×2、P3×6） | 实时 PR 与四轮完整复审报告 |
| worktree | 1 个（主 checkout，工作区 clean） | `git worktree list --porcelain` |
| 远程分支 | 2026-10-26 时点快照：`git ls-remote --heads origin` 计 47 个（含本 PR 任务分支本身）；main 受保护 | 时点快照，非当前计数，引用时须重新查询；branch protection |
| TD-114 / TD-115 / REQ-042 | 🟢 完成 / ⚫ 待办 / ⚫ Candidate | technical-debt、REQ-042 requirement、Backlog |
| phase-D/E、生产 backfill | 未启动 | requirement、plan、Backlog |

S1a 的已交付内容与证据边界（不得扩大解释）：

- 交付物：Token/themes/components、LayoutView、Playwright 配置与截图采集、e2e README；实现净 diff 8 文件 +523/-25，含评分行后 9 文件 +524/-25。
- 明确未交付：**UiComposer、任何业务页面**；未改 router/nav/permissions、stores/services、API/DTO、数据库或后端。
- 已记录证据（均为 #667 当时实测，本规划未重跑）：Node `v20.20.2`、pnpm `9.15.0`；lint 0 errors/28 warnings；typecheck、build 通过；全量前端 Vitest 40 文件 / 382 用例；`METAEDU_E2E_PORT=3101 … test:e2e navigation` 55 passed；16 库 / 240 文件 hash 校验 `problems=0`；15 组同条件改前/改后截图共 30 张。
- 保留缺口：**未做人工点击流、未做多 OS 字体渲染对比、未做真实 PG 或真实 LLM 验收**；S1a 的截图不替代 design spec §6 的 S1/S2/S4 视觉确认节点。按 D4，当前也不把自动像素基线列为交付或退出条件。

## 1. 不可变约束（后续派发必须逐条满足）

1. **三类用户视觉确认门不可弱化**：S1 外壳与共享控件、S2 AI 聊天页面、S4 列表/表单/详情样板。代码检查通过不能代替用户视觉确认；S1a 的截图交付不替代这些节点（design spec §6）。
2. **视觉证据与记录形式（D4/D8）**：在固定环境中提供可运行预览，以及同一 OS/浏览器/主题/视口/数据/角色下的改前/改后截图和结构化度量；用户确认记录优先写入**对应切片 PR 中绑定具体 commit 的结构化评论**，包含同条件截图、环境信息和明确确认结论。closeout 可索引该评论；**不新建独立 sign-off 文档**。确认后才批量扩展，确认后的视觉修改需重新确认受影响样板。
3. 视口与主题矩阵：1440×900、1280×800、1024×768、390×844，light/dark 两套；320px 宽与 200% 缩放附加检查溢出、焦点、主要动作；Workspace 另需实际容器断点两侧检查。登录页升级前后截图与适用状态验收保留，不另设第四类样板节点。
4. 语义/几何硬条件：无全页横向溢出、无文字遮挡、无焦点丢失、无错误动作启用、无来源丢失；主按钮/状态/圆角/字体来自规范；对话框含 role/aria-modal、焦点约束、Esc 与关闭后焦点返回；详情抽屉同样验证。
5. 可审查链：参考库路径+hash → selector/行为 → 采用/适配差异 → Token → Vue 组件/页面 → fixture/截图/交互测试。不得用“参考 TraeWork”替代该链。
6. 文件所有权：共享层只有一个 owner；`assets/css/`、`components/`、`LayoutView.vue`、UiComposer、`playwright.config.ts` 与公共 e2e fixture 归共享层；`package.json`/锁文件、`app/router.ts`/nav/permission、`stores/`、`services/`、shared schema、backend、CI 门禁不在页面切片 allowlist；发现功能问题登记所属 REQ/BUG，不在 UI PR 扩范围。S3 的目录归属人只能由用户指定，Agent 不得自行认领。
7. 环境隔离：每切片独立 worktree 与明确 base SHA，不复制他人脏目录、不共享 `node_modules`/dist/测试输出；端口默认 S1=3101、S2=3102…S8=3108，`METAEDU_E2E_PORT` + baseURL/server URL 同源 + `--strictPort` + `reuseExistingServer=false`；占用直接失败，不杀进程、不自动换端口。新增 e2e 文件须匹配 `*-desktop.spec.ts` / `*-mobile.spec.ts` / `*-shared.spec.ts` 发现规则，平板视口在 desktop/shared 内显式 setViewportSize。**仅使用不同 worktree 不足以解除 S3 的目录互斥。**
8. 停止边界：本路线任何阶段都不得顺带启动 phase-D/E、生产 backfill、远程分支/worktree/refs 清理，也不得把未交付能力画成已交付按钮。
9. **D1–D8 已是用户确认的决策**，不得再写成待裁决，也不得恢复被这些决策排除的旧方案；规划仍未等于实施或验收完成。
10. **S4 强制分页门不得未经用户批准弱化**：design spec §6 的 S4「列表筛选/分页」是强制验收范围。S4 强制分页项只有在**已有真实候选并通过**，或**用户已正式批准调整验收口径并同步 spec 与相关索引**后，才视为闭合。在此之前不得以其他样板冒充、不得宣称 S4 全部验收完成、不得派发 S6/S7；§4.5 的方案 A / B 属用户决策，Agent 不得默认选择或写成已获批准。

## 2. S1 尚未收口的具体缺口（S1a ≠ S1）

| 编号 | 缺口与当前关闭口径 | 归属与证据 |
|---|---|---|
| G1 | **UiComposer 未交付**：受控 `modelValue`、`mode: ready/busy/readonly/unavailable`、`canSubmit/canStop/placeholder/hint/inputLabel`、事件 `update:modelValue` / `submit` / `stop`、附件与工具插槽；提交须同时满足 `mode === "ready" && canSubmit && modelValue.trim().length > 0` 且输入法非 composing；`ready + canSubmit=false` 仍可编辑草稿；`busy` 仅在 `canStop` 时允许停止；组件不请求 API、不选模型、不管理 Conversation、不推断租户权限 | design spec §3；plan §8 明确未新增。由 **S1b-2** 交付 |
| G2 | 共享控件**全状态覆盖不足**：default、hover、focus-visible、active/selected、disabled、loading、empty、error、success、无权限等适用状态，及表格、表单、卡片、菜单、确认弹窗的统一契约 | design spec §2.1；由 **S1b-1** 先收敛共享 CSS/语义 token 与状态规则 |
| G3 | `.ui-panel:hover` 抬升效果未按 spec 修正（32 处使用点）。按 D1，采用新增语义 token 与 opt-in 样式，先在 S1b-1 选定的共享控件/样板接入，**不要求 32 处一次性全改**；后续页面切片按所有权逐步采用 | design spec §2.1；S1a 遗留风险；由 S1b-1 建立可复用入口 |
| G4 | `.ui-input` 行高未施加（82 处使用点）。按 D1，新增行高语义 token 与 opt-in 样式，先在 S1b-1 选定的控件/样板验证，**不要求 82 处一次性全改**；不得把“全部使用点已迁移”写成 S1b-1 退出条件 | S1a 遗留风险；由 S1b-1 建立 opt-in 渐进路径 |
| G5 | 代表性控件的可运行预览与同条件截图未覆盖 S1 全量共享控件（S1a 仅外壳/导航与部分控件） | design spec §6 S1 节点范围；S1b-1 提供共享层证据，S1b-2 补齐 S1 全量预览与截图 |
| G6 | **S1 用户视觉确认未完成**，因此 S1 不能视为收口。须在 S1b-2 的 S1 全量预览上完成确认并按 D8 写入 PR 结构化评论 | design spec §6；S1a 合并不替代该门 |
| G7 | 证据缺口保留：人工点击流、多 OS 字体对比、真实 PG/真实 LLM 均未做；按 D4 当前不引入自动像素基线，后续环境及基线成熟后另行评估 | plan §8；不得把未执行项写成已完成，也不得把像素基线列为当前退出条件 |
| G8 | 遗留主题值（paper/liquid/ink/navy/notion）在 REQ-064 内仅保留回落 light 的启动冒烟；**清理或正式支持一律另立任务**，不属于本路线范围 | S1a 交付记录；D7 已确认 |

## 3. 已确认路线与排序理由

D1–D8 已由用户确认。下表中的“依赖”是允许开工的硬条件；“退出后才允许”是允许下一切片的硬条件。

| 阶段 | 内容 | 依赖 | 退出后才允许 |
|---|---|---|---|
| A. 路线决策回填 | 本文件与相关索引同步已确认 D1–D8，并处理首轮 10 项 findings | 首轮完整复审报告与实时 head 已核验 | 最新 head 通过独立复审前，仍不得派发实现 |
| B. S1b-1 共享 CSS / 语义 token（顺序 PR 1） | G2/G3/G4 的共享层收敛与 opt-in 渐进入口；共享层预览证据 | A 的规划返修已通过独立复审；S0/S1a 已合入；TD-114 完成；共享层 owner 已分配 | S1b-1 验证通过且合入后，才允许 C |
| C. S1b-2 UiComposer（顺序 PR 2） | G1 UiComposer、G5 S1 全量预览、G6 S1 用户视觉确认 | **S1b-1 已合入且验证通过**；base 必须包含 S1b-1 merge commit | S1b-2 验证通过 + **S1 用户视觉确认并合入** → S1 才收口，才允许 D/F |
| D. S2 AI 问答（UiComposer 首个消费方） | 采用 UiComposer 的聊天输入与阅读体验，完成 S2 视觉门 | C 已合入且 S1 已收口；S2/S3 不并行 | S2 合入后，先固定 Composer 接口与文件所有权，再评估 E；F 可按自身依赖推进 |
| E. S3 Workspace 展示 | 三栏与窄屏展示，消费已交付能力 | **D 已完成且 UiComposer 接口和文件所有权稳定**；D5 的目录 owner、无重叠或整合完成条件均满足 | S3 验证通过且合入后进入后续合入序列；未满足时继续阻塞，不派 S3 |
| F. S4 知识/资源/数据样板与 S5 应用能力中心 | S4 列表/表单/详情样板及 S4 视觉门；S5 复用共享基线 | C 已合入且 S1 已收口；S4 的 D3 候选与覆盖边界已明确 | **S4 样板用户确认并合入，且 S4 强制分页项已有真实候选并通过（或用户已正式批准调整验收口径）后**才允许 S6/S7；分页映射未解决时 S4 不得宣称该项通过，S6/S7 不开工；S5 合入后进入集成候选 |
| G. S6 管理与模板、S7 背调与外围 | 管理/模板、背调与外围页面，S7 含登录必要样式升级 | S1 已收口 + **S4 样板用户确认并合入，且 S4 强制分页项已有真实候选并通过（或用户已正式批准调整验收口径）** | S6/S7 各自身退出条件完成后，H 仍须等待 S2–S7 全部合入并满足 S8 的全部前置条件 |
| H. S8 集成与收口 | 全路由审计、视觉矩阵、三类确认记录核对 | S2–S7 全部合入；确认记录齐全 | required checks 通过、无遗漏路由后，才可讨论 REQ-064 整体完成度 |

排序理由：

1. **共享接口唯一且有序**：先 S1b-1 共享 CSS/语义 token，再 S1b-2 UiComposer；后一个 PR 必须以前一个 PR 的合入与验证为 base，避免组件先于其样式契约落地。
2. **UiComposer 先接 S2 再接 S3**：S2 是首个消费方，先把聊天样板、接口与文件所有权稳定下来；S2/S3 不并行。S4/S5 不使用 UiComposer 的页面可各自按依赖推进，不因此把 S3 放行。
3. **视觉基线先行**：S1/S2/S4 的可运行预览、同条件截图、结构化度量与 PR 结构化确认评论必须先完成，再批量扩展；不以自动化检查替代确认。
4. **样板先行**：S4 的列表/表单/详情样板决定 S6/S7 的形态，先确认样板可减少二级页面返工。
5. **互斥串行**：S3 除依赖 S2 稳定外，还必须满足 D5 的目录所有权、无重叠修改或整合完成条件；不同 worktree 不能替代这些条件。
6. **集成最后**：S8 只有在 S2–S7 合入后才做全路由与三类确认记录核对，避免用局部通过冒充全站完成。

默认合入次序：S1b-1 → S1b-2 → S2 → S3 → S4 → S5 → S6 → S7 → S8。S2/S3 不并行；S4/S5 可在自身依赖满足时独立推进。若 S3 因 D5 阻塞，其他独立切片可继续，但集成者必须记录 S3 的阻塞原因及调整后的合入次序，不得把默认顺序当作解除阻塞的依据。

## 4. 切片卡片

### 4.1 S1b-1 — 共享 CSS / 语义 token（顺序 PR 1）

- **目标**：先建立共享样式契约与渐进迁移入口，关闭 G2，并为 G3/G4 提供可复用方案。
- **包含**：G2 共享控件状态矩阵；G3 `.ui-panel` 静态容器与可交互行的语义区分及 opt-in 样式；G4 `.ui-input` 行高语义 token 与 opt-in 样式；在选定的共享控件/样板接入并验证；S1 共享层可运行预览与同条件前后截图、结构化度量。
- **排除**：**不得一次性全量改写 82 处行高和 32 处 hover**；不包含 UiComposer（归 S1b-2）；不改业务页面、router/nav/permission 语义、stores/services/API/DTO、数据库、后端、CI 配置、依赖与锁文件；不新增流式/语音/审批能力。
- **前置**：规划返修已通过独立复审；S0/S1a 已合入；TD-114 完成；共享层 owner 与独立 worktree/端口（3101）已分配。
- **可并行**：无共享层并行写入。共享层补丁由一个 owner 顺序提交，其他 Agent 不写这些文件。
- **阻塞**：共享层文件被其他任务占用；参考库 hash 校验失败；把 D1 改回全量改写或把全部使用点迁移写成前置条件。
- **交付物**：共享 CSS/token diff、opt-in 使用映射、状态矩阵、预览启动命令与 URL、同条件前后截图与结构化度量、验证命令与退出码、证据层级声明。
- **自动化验证**：`pnpm --filter @metaedu/web lint`、`typecheck`、`build`、全量前端 Vitest（theme/Layout/NavBreadcrumb 及本切片相关测试）、`METAEDU_E2E_PORT=3101 pnpm --filter @metaedu/web test:e2e navigation`、`scripts/check-engineering-docs --full`、`git diff --check`。Node 20 环境（与 CI 一致）。
- **技术验收（非视觉）**：props/events 兼容；default/hover/focus-visible/disabled/loading/empty/error/success/无权限等适用状态可复现；焦点不丢、键盘可达、reduced-motion 生效；交互边界对比度 ≥3:1、正文 ≥4.5:1；端口占用负例失败退出且不杀进程；无全站一次性行为改写，无业务行为变化。
- **用户视觉证据**：按 D4/D8 提供固定环境预览、同条件前后截图、结构化度量与 PR 评论所需环境信息；**S1b-1 单独不关闭 S1，也不代替 S1b-2 的 S1 用户视觉确认**。
- **退出条件**：自动化与技术验收通过 + PR 合入。**只有 S1b-1 合入后，才允许派发 S1b-2。**

### 4.2 S1b-2 — UiComposer（顺序 PR 2，依赖 S1b-1）

- **目标**：在 S1b-1 的共享样式契约上交付 UiComposer，并补齐 S1 全量预览与 S1 用户视觉确认。
- **包含**：G1 UiComposer 接口、提交/停止条件与测试；G5 S1 全量共享控件和 Composer 的可运行预览、同条件前后截图与结构化度量；G6 按 D8 完成的 S1 用户视觉确认记录；双主题、键盘、导航、旧主题回落兼容；Playwright 端口隔离沿用 S1a 配置。
- **排除**：不重复实现 S1b-1；不在本 PR 接入 S2/S3 业务页面；不改业务页面、router/nav/permission 语义、stores/services/API/DTO、数据库、后端、CI 配置、依赖与锁文件；不新增未交付能力。
- **前置**：**S1b-1 已合入且验证通过**；新 worktree/base 必须包含 S1b-1 merge commit；共享层 owner 与端口（3101）已分配。
- **可并行**：不与另一个共享层 owner 并行；S2/S3 不在本 PR 提前接入或并行开发。
- **阻塞**：S1b-1 未合入或验证未通过；UiComposer 接口/文件所有权不稳定；S1 全量预览、截图或用户确认缺失。
- **交付物**：UiComposer 及测试、参考→Token→组件映射、S1 全量预览启动命令与 URL、同条件前后截图与结构化度量、验证命令与退出码、证据层级声明、绑定本 PR head 的 S1 用户确认结构化评论。
- **自动化验证**：lint/typecheck/build、全量前端 Vitest（theme/Layout/NavBreadcrumb/UiComposer）、`METAEDU_E2E_PORT=3101 … test:e2e navigation`、docs gate、diff check；Node 20 环境。
- **技术验收（非视觉）**：props/events 兼容；提交与停止条件符合 G1；`ready + canSubmit=false` 可编辑草稿；busy 仅在 canStop 时允许停止；不请求 API、不选模型、不管理 Conversation、不推断权限；焦点、键盘、reduced-motion、对比度与端口隔离符合要求；无业务行为变化。
- **用户视觉确认（必须）**：S1 外壳与共享控件及 Composer 的可运行预览 + 同条件前后截图（按钮/输入/表格/表单/卡片/菜单/确认弹窗及适用状态、浅色/深色与窄屏）；**确认记录为绑定本 PR head 的结构化评论**，包含截图、环境信息与明确确认结论。
- **退出条件**：自动化与技术验收通过 + S1 用户视觉确认完成 + PR 合入。**只有此时才称 S1 收口**，才允许 S2、S4、S5 开工；S3 仍须另等 S2 稳定及 D5 解除。

### 4.3 S2 — AI 问答页面（UiComposer 首个消费方）

- **目标**：在已确认共享基线上交付 AI Chat 视觉与阅读体验，保留现有能力边界，并先稳定 UiComposer 的消费接口与文件所有权。
- **包含**：采用 UiComposer 的输入区、消息排列、长回答/代码/表格排版、已交付消息操作、建议问题、错误/停止/引用与滚动；输入区自动增高至 160px 后内部滚动；底部“回到最新”与阅读位置保持；移动键盘场景；Composer 接口与文件所有权交接记录。
- **排除**：不新增流式、语音、上传、模型切换；不改 services/stores、共享 Markdown/CSS/EvidenceCard/DocumentSourceList；不造未交付工具按钮；共享组件缺口须先由共享层补丁解决；**不与 S3 并行**。
- **前置**：S1b-2 合入且 S1 已收口；参考 TW-03/DB-01/DB-02/DB-03，CL-01 仅作元信息组织补充。
- **可并行**：可与 S4/S5 在各自目录、worktree/端口下并行（S2=3102）；**不得与 S3 并行**。S2 用户确认前不得把其聊天模式扩展到其他对话表面。
- **阻塞**：共享层接口未稳定；参考库 hash 失败；真实能力缺口（如中止、引用）需要新契约时退回所属 REQ。
- **交付物**：`views/ai-chat/` diff 与新增 `e2e/req064-chat-*`、参考→组件映射、IME/滚动/错误/停止状态证据、预览与截图、Composer 接口与所有权交接记录、验证命令与退出码。
- **自动化验证**：lint/typecheck/build、`pnpm --filter @metaedu/web test -- src/views/ai-chat`、既有 EvidenceCard/DocumentSourceList 测试、新增 chat e2e（`METAEDU_E2E_PORT=3102 … test:e2e req064-chat`）、docs gate、diff check。
- **技术验收**：中文 IME composing 不发送；空白不可提交；多行与回缩；请求身份保持；停止/恢复不伪造状态；文件链接与引用安全；无证据提示保留；无全页横向溢出；未交付能力保持门控。
- **用户视觉确认（必须）**：输入区、消息排列、长回答/引用、已交付消息操作、滚动/错误/停止与手机键盘场景的可运行预览与同条件截图；确认记录为绑定 S2 PR head 的结构化评论，含截图、环境信息与明确结论。
- **退出条件**：自动化与技术验收通过 + 用户视觉确认完成 + PR 合入；随后先固定 Composer 接口和文件所有权，才可评估 S3。S4/S5 不因 D2 与 S3 的限制被强行捆绑。

### 4.4 S3 — Workspace 展示（S2 稳定后，D5 解除才派发）

- **目标**：三栏与窄屏展示统一，消费当时已交付的真实能力。
- **包含**：会话列表/草稿/已有 Run 详情展示、容器断点（≥1180px 三栏、768–1179px 两栏+抽屉、<768px 单面板 Tab）、选中会话后进入消息面板、显式点击运行详情才切换运行面板、resize 不重建 Conversation/Run。
- **排除**：不改 workspace store/服务/事件协议；不实现 SSE、cancel/steer、审批或产物协议；未交付按钮仍门控；不与 WS-S2 phase-D/E 或 WS-S3 同目录任务并行。
- **前置（全部必须满足）**：S2 已合入且 UiComposer 接口与文件所有权稳定；用户已明确指定 `views/agent-workspace/` 及 workspace e2e 的目录/文件归属人；归属人确认与 phase-D/E、WS-S3 无重叠修改，或相关重叠已完成整合并复验；参考 TW-03/TC-01 与 REQ-042 契约。**不同 worktree 本身不构成解除条件，Agent 不得自行认领目录。**
- **可并行**：不与 S2 并行；不与 phase-D/E 或 WS-S3 同目录任务并行。与 S4/S5 的并行须由集成者基于实际文件无重叠另行确认，不默认放行。
- **阻塞**：S2 未完成或接口未稳定；目录归属人未由用户指定；存在重叠修改且未完成整合；需要新协议能力。仅准备独立 worktree 不能解除这些阻塞。
- **交付物**：`views/agent-workspace/` diff 与 workspace e2e、容器断点证据、草稿/选择/恢复回归结果、预览与截图、目录归属人与无重叠/整合完成证明、验证命令与退出码。
- **自动化验证**：workspaceDraft/workspace store 既有测试（只读回归）、WorkspaceView 测试、workspace e2e、lint/typecheck/build、docs gate、diff check。
- **技术验收**：草稿隔离、会话切换不丢草稿、显式运行详情、归档/恢复、禁用发送、各容器断点；未开放发送保持禁用并说明原因；不以视觉禁用代替服务端授权。
- **用户视觉确认**：无独立视觉确认门，但须复用 S1 已确认基线，并在 PR 提供同条件截图供审查。
- **退出条件**：自动化与技术验收通过 + PR 合入；不实现 SSE/审批协议。

### 4.5 S4 — 知识、资源与数据（含 S4 样板门）

- **目标**：交付 knowledge/resource/database 全部已交付视图与子组件的统一布局，并提供列表/表单/详情样板。
- **包含**：标题/筛选/列表/表格/空错载/分页/详情与来源辅助区；先交付下列 D3 已确认候选及同条件截图，再扩展同类页面；长表格与问数结果的单位、期间、来源、空态。
- **排除**：不改共享 FieldEditor/TableRenderer/KGGraph 等（由共享层 owner 按已定义接口修正）；不改 DTO、权限、后端；不顺手删除旧文件；**不把 S6 的 `/data/templates`、`/data/templates/:id` 借用为 S4 样板**。
- **前置**：S1b-2 合入且 S1 已收口；参考 TW-02/TW-04/VE-01/VE-02。
- **可并行**：可与 S2/S5 并行（端口 3104）；**S6/S7 必须等待 S4 样板用户确认并合入，且 S4 强制分页项已有真实候选并通过（或用户已正式批准调整验收口径）**。与 S3 的并行须另行确认文件无重叠，不默认放行。
- **阻塞**：共享组件缺口、数据/上传/图谱真实行为需要新契约；S4 强制分页项未闭合（既无真实候选通过，也未获用户正式批准调整验收口径）；独立编辑页条件性缺口未解决时，不得宣称全部样板形态已覆盖。
- **交付物**：目录内页面与子组件 diff、`e2e/req064-data-*`、样板预览与截图、搜索/筛选/列表/上传/详情/图谱/问数原行为回归证据、候选路由与形态映射、验证命令与退出码。**分页不列入当前「原行为回归」对象**：S4 候选范围内当前没有合格真实分页候选，分页项按 §4.5 的门控单独验收，未闭合前不得列为回归证据或宣称通过。

**D3 已确认候选与形态映射**：

| 候选路由与组件 | 代表的页面形态 | 可用于核验的内容 | 覆盖边界 |
|---|---|---|---|
| `/knowledge` → `views/knowledge/KnowledgeBaseView.vue` | **列表样板** | 知识节点列表、搜索、空/加载状态、新建节点入口、删除确认；可附新建节点表单弹窗 | 不声称覆盖 resource/database 的列表行为 |
| `/resource/:id` → `views/resource/FileDetailView.vue` | **详情样板** | 文件元信息、处理状态、Tabs、chunks/KG、来源与辅助面板、重试/删除等行为回归 | 详情不是独立编辑页；不冒称表单样板 |
| `/database` → `views/database/DatabaseView.vue` + `CatalogCreateDialog.vue` | **弹窗表单样板** | 新建数据库 code/name/description、必填与 code 格式校验、canSubmit、取消、提交中、错误提示与保存 | **是弹窗表单，不是独立编辑页**；若验收要求独立编辑页，标为待补充，不借 S6 页面冒充 |

补充说明：`/database/:catalogCode` 的 `CatalogDetailPage.vue` 可作为数据库详情与后续数据集/图谱扩展核验对象，但不替代上表三种基本样板。当前候选可明确支持“列表 + 详情 + 弹窗表单”；**独立编辑页形态不在已覆盖结论内**。若 S4 验收坚持独立编辑页，须先由用户确认补充候选，未补充前该项标为**待补充**，不得以 data templates 或抽象名称填补。

**S4 强制分页验收映射（第二轮 P1-1 复核）**

design spec §6 的“列表筛选/分页”是强制验收范围，不能由 D3 已确认的 knowledge/resource/database 样板组合自动推定通过。以下只读代码核验的**范围是 design spec §6 所要求的 S4 候选路由**（S4 范围内的结论）；范围外已核实的真实分页见本节末尾的补充披露。

| 路由 / 组件 | 已确认可用的现有行为 | 分页边界与结论 |
|---|---|---|
| `/knowledge` → `views/knowledge/KnowledgeBaseView.vue` | 搜索/筛选、节点列表、空态与加载态 | 没有分页控件或分页处理；只能作列表/筛选样板，不能作分页样板 |
| `/resource` → `views/resource/ResourceLibraryView.vue` | 状态筛选、文件列表与固定 `limit: 100` | 固定 limit 不是分页；没有 offset 或页码处理，不能作分页样板 |
| `/resource/:id` → `views/resource/FileDetailView.vue` | 文件详情、处理状态、Tabs、chunks/KG、重试与删除 | 属详情样板，不把详情页当分页样板 |
| `/database` → `views/database/DatabaseView.vue` + `CatalogCreateDialog.vue` | 卡片网格、新建数据库弹窗表单与校验/保存 | 没有分页；弹窗表单不能替代分页验收 |
| `/database/:catalogCode` → `CatalogDetailPage.vue` + `DatasetTabsPanel.vue` | 子组件发出 `change-page`，父组件传入 `@change-page="() => {}"` | 事件为空实现，不能证明真实分页；不纳入合格候选 |

另一个易误读点：`views/resource/ResourceView.vue` 确有 `offset/limit` 与上一页/下一页联动、边界禁用和 `loadResources()`，但当前 `app/router.ts` 的 `/resource` 指向 `ResourceLibraryView.vue`，且未找到 `ResourceView` 的路由或其他组件引用。**存在分页代码不等于当前路由存在可验收页面**，因此不把它列为当前候选。

截至本次只读复核，**在 design spec §6 所要求的 S4 候选范围（§4.5 上表所列 knowledge / resource / database 路由）内，没有经核实的真实分页样板**能同时满足“现有路由 + 真实组件 + 可工作的分页行为”。S4 不能以现有样板宣称通过 design spec §6 的强制分页项；固定 `limit`、静态分页参数和 no-op 事件处理器均不算覆盖。D3 已确认的列表、详情和弹窗表单样板仍可用于各自形态，但不替代强制分页项。

**范围外已核实的真实分页（第四轮复审补充披露）**：仓库内另有已挂路由、服务端分页可用的页面——`capabilities/skills` → `views/skill-registry/SkillListView.vue`、`capabilities/mcp` → `views/mcp-registry/McpServerListView.vue`（路由见 `app/router.ts`）。两者的审计弹窗内执行记录列表分别调用 `listExecutions(id, { limit, offset: page * limit })` 与 `listInvocations(id, { limit, offset: page * limit })`，消费 `res.items` / `res.total`，`auditPrev` / `auditNext` 带边界禁用，页码信息显示 `start-end / 共 total`。三点限定：① 分页对象是**审计弹窗内的执行记录**，不是页面主列表——`loadSkills()` / `loadServers()` 分别只调用 `listSkills()` / `listMcpServers()`，主列表为客户端过滤、无分页；② 这两个页面按 §4.6 归属 **S5**，不是 S4 的既有候选；③ 是否可作为 S4 的分页候选或作为实现范式，属 §4.5 方案 A 的具体范围，**仍待用户裁决**，本文件不自动纳入 S4、不据此解除 S4 门禁。

**待用户决定（仅针对强制分页缺口，不改变 D3 组合）**：

- **方案 A：补充真实候选，或另立明确范围的分页前置工作。** 必须提供可访问路由、实际组件及可工作的分页处理证据，并复验上一页/下一页、边界禁用和数据加载行为；完成前 S4 强制分页项保持未闭合。该方案保留 design spec §6 的验收要求，不在本 PR 新增业务分页功能。
- **方案 B：调整验收口径。** 仅在用户明确决定修改 design spec §6 的 S4 验收范围时采用；须同步 spec 与相关索引并重新独立复审。该方案会改变既有验收覆盖，不得由 Agent 默认选择或写成已获批准。

在用户选择前，S4 强制分页项保持未闭合，不得以其他列表/详情/弹窗样板冒充通过。

- **自动化验证**：对应页面 Vitest + 切片 e2e、lint/typecheck/build、docs gate、diff check。
- **技术验收**：搜索/筛选/排序、上传、详情、图谱、问数原行为不变；空/错/加载/无权限状态完整；双主题与长表格、长 URL 局部滚动；表单校验、保存/取消与危险确认行为保持。**分页只能在已核实的真实候选上按现有行为验收，固定 `limit`、静态参数和 no-op 处理器不得作为通过证据。**
- **用户视觉确认（必须）**：列表筛选/分页、表单校验/保存（明确为弹窗或独立页）、详情正文/来源/辅助面板及完整空/错/加载状态的可运行预览与同条件截图；确认记录为绑定 S4 PR head 的结构化评论，含截图、环境信息与明确结论。**分页截图和结构化度量必须来自已核实的真实分页候选；没有合格候选时，不得以其他列表样板替代或宣称强制分页项通过。**
- **退出条件**：自动化与技术验收通过 + **S4 样板用户确认并合入**，且 S4 强制分页项已有真实候选并通过（或用户已正式批准调整验收口径）。当前 S4 候选范围内无合格真实分页候选时，S4 只能记录其他样板进展，**不得宣称强制分页项通过或 S4 全部验收完成，S6/S7 不得开工**。独立编辑页被列为必需且仍待补充时，同样不得以“全部样板形态已覆盖”通过退出条件。

### 4.6 S5 — 应用与能力中心

- **目标**：ai-apps、skill-registry、mcp-registry 页面统一为可读、可扫描的卡片或紧凑列表。
- **包含**：筛选、描述、状态与操作分层；真实 Registry 状态、角色访问、错误/空态与卡片密度。
- **排除**：不写 admin 目录、导航/角色判断和 Registry 服务；不复刻示例假计数。
- **前置**：S1b-2 合入且 S1 已收口；参考 TW-05/TC-01。
- **可并行**：可与 S2/S4 并行（端口 3105）；与 S3 的并行须确认无文件重叠。
- **阻塞**：Registry 真实状态或权限缺口需要后端变更（退回所属 REQ）。
- **交付物**：页面 diff、`e2e/req064-apps-*`、真实状态与权限证据、预览与截图、验证命令与退出码。
- **自动化验证**：对应页面 Vitest + 切片 e2e、lint/typecheck/build、docs gate、diff check。
- **技术验收**：真实 Registry 状态、角色访问、错误/空态、卡片密度一致；无虚构计数或假入口。
- **用户视觉确认**：无独立视觉确认门；沿用 S1 已确认基线并提供同条件截图。
- **退出条件**：自动化与技术验收通过 + PR 合入。

### 4.7 S6 — 管理与模板

- **目标**：admin 目录的表单与模板编辑体验统一。
- **包含**：分组标签、字段帮助、就地错误、底部操作区、模板字段/编辑/导入/校验显示、危险确认。
- **排除**：不改共享组件/DTO/权限；数据模板仍归知识与数据导航；不改后端校验语义。
- **前置**：S1b-2 合入 + **S4 列表/表单/详情样板用户确认并合入，且 S4 强制分页项已有真实候选并通过（或用户已正式批准调整验收口径）**；参考 TW-02/TW-04/VE-01/VE-02。
- **可并行**：可与 S7 并行（端口 3106），前提是 S4 样板已合入且 S4 强制分页项已有真实候选并通过（或用户已正式批准调整验收口径）。
- **阻塞**：S4 样板未确认或强制分页项未闭合（无真实候选通过且未获用户批准调整口径）；共享表单组件缺口。
- **交付物**：admin 页面 diff、`e2e/req064-admin-*`、表单错误与焦点证据、保存/取消/危险确认回归、预览与截图。
- **自动化验证**：对应页面 Vitest + 切片 e2e、lint/typecheck/build、docs gate、diff check。
- **技术验收**：表单错误定位、焦点管理、保存/取消、危险确认、权限回归；敏感字段不回显；取消不提交。
- **用户视觉确认**：无新增样板门；须复用 S4 已确认样板并提供同条件截图。
- **退出条件**：自动化与技术验收通过 + PR 合入。**本切片完成自身退出条件后，S8 仍须等待 S2–S7 全部合入，并满足 S8 的全部前置条件。**

### 4.8 S7 — 背调与外围页面（含登录）

- **目标**：due-diligence、HomeView、share、ForbiddenView 与登录页必要样式升级，保持鉴权与品牌约束。
- **包含**：报告/证据/制审行为不变的展示统一；登录页字体/间距/控件/表单状态升级与升级前后截图；分享 token 路由与首页权限回归；REQ-023 品牌约束保留。
- **排除**：不改认证服务、store、路由守卫；不改背调领域服务；公共控件缺口由共享层修。
- **前置**：S1b-2 合入 + S4 样板确认并合入，且 S4 强制分页项已有真实候选并通过（或用户已正式批准调整验收口径）；参考 TW-01/TW-02、REQ-023、VE-02 及报告/来源模式。
- **可并行**：可与 S6 并行（端口 3107），前提是 S4 样板已合入且 S4 强制分页项已有真实候选并通过（或用户已正式批准调整验收口径）。
- **阻塞**：S4 样板未确认或强制分页项未闭合（无真实候选通过且未获用户批准调整口径）；鉴权或品牌约束需要新决策（退回 REQ-023 相关裁决）。
- **交付物**：页面与登录 diff、对应 e2e、报告/证据/制审回归、登录升级前后截图与适用状态、预览与验证命令。
- **自动化验证**：对应页面 Vitest + 切片 e2e、lint/typecheck/build、docs gate、diff check。
- **技术验收**：报告/证据/制审行为不变；登录鉴权、校验、提交、错误与跳转语义保持；分享 token 路由与首页权限回归；品牌差异记录完整。
- **用户视觉确认**：登录属 S8 全站视觉一致性的一部分，**必须**提供升级前后截图与适用状态验收，记录可为绑定 S7/S8 对应 PR commit 的结构化评论；不另设第四类样板节点或独立 sign-off 文档。
- **退出条件**：自动化与技术验收通过 + 登录升级截图齐备 + PR 合入。**本切片完成自身退出条件后，S8 仍须等待 S2–S7 全部合入，并满足 S8 的全部前置条件。**

### 4.9 S8 — 集成与收口

- **目标**：全路由审计与全站验收矩阵，确认无遗漏路由与确认记录。
- **包含**：全路由/角色/主题/视口矩阵（含登录升级与 `/share/:token`、`/403`、教育占位路由的 feature/权限隐藏、旧链接重定向）、三类用户确认记录核对、未来功能接入核对、最终文档与状态更新。
- **排除**：不借集成名义新增页面功能或改变协议；不把占位页当成已交付产品；不清理 worktree/分支/refs。
- **前置**：S2–S7 全部合入；每批从最新 router 重新生成路由清单并与 plan §4.1 做差集，新增路由由集成者明确归属。
- **可并行**：无（集成者单独执行）。
- **阻塞**：任一切片未合入、用户确认记录缺失、路由清单差集未归属。
- **交付物**：全量前端 Vitest + 全量 Playwright 结果、lint/typecheck/build、docs/diff 门禁、完整路由/角色/主题/视口矩阵、三类确认记录清单、证据层级声明与回滚方式。
- **自动化验证**：全量前端 Vitest + 全量 Playwright、lint/typecheck/build、`scripts/check-engineering-docs --full`、`git diff --check`。
- **技术验收**：样板一致、无遗漏路由、required checks 通过、无横向溢出/文字遮挡/焦点丢失/错误动作启用/来源丢失。
- **用户视觉确认**：核对 S1/S2/S4 三类确认记录是否绑定 commit、包含截图/环境信息/明确结论且覆盖受影响样板；登录升级截图与全站一致性验收记录齐全。closeout 可索引对应 PR 的结构化评论，不新建独立 sign-off 文档。
- **退出条件**：全站验收矩阵通过 + required checks 通过 + PR 合入后，才可评估 REQ-064 整体完成度；在此之前 REQ-064 保持 Doing。

## 5. 验收分层与证据口径

| 层级 | 内容 | 不得混同 |
|---|---|---|
| A. 自动化测试 | lint/typecheck/build、相关与全量 Vitest、对应 Playwright、docs gate、`git diff --check`；CI 需区分实跑、no-op、skipped | no-op / skipped 不得写成前后端或 full hermetic 测试通过 |
| B. 技术验收（非视觉） | 行为保持（props/events、权限、路由、store/service）、可访问性（焦点、aria、reduced-motion、对比度）、端口隔离、状态矩阵、草稿/请求身份/停止恢复、无业务 API 变化 | 技术验收通过不等于用户视觉确认完成 |
| C. 用户视觉确认 | 仅 S1（由 S1b-2 承载）、S2、S4 三门：固定环境的可运行预览 + 同条件前后截图 + 结构化度量 + 绑定具体 commit 的 PR 结构化确认评论（含截图、环境信息与明确结论）；S7 登录与 S8 全站一致性按 spec §6 验收 | 未确认前不得批量扩展；S1a 的 30 张截图不替代这三门；不新建独立 sign-off 文档 |
| D. 不可宣称项 | 人工点击流、多 OS 字体对比、真实 PG、真实 LLM、phase-D/E、生产 backfill、REQ-064 Done；以及当前未实施的 UI/视觉验收 | 未实际执行不得写成已完成 |

**D4 当前口径**：不引入 `maxDiffPixelRatio: 0.001` 像素级自动基线，不把自动像素比较列为 S1b/S2/S4 的当前交付或退出条件。当前只用固定环境下的同条件前后截图、结构化度量与用户确认；环境稳定并积累基线后再单独评估像素基线。design spec §6 中的像素比较阈值只在未来实际启用像素比较时适用，不与当前暂缓决定混用。

## 6. 已确认决策与执行约束（D1–D8）

| 编号 | 已确认方向 | 对派发的硬约束 |
|---|---|---|
| D1 | 共享 CSS 使用新增语义 token、opt-in 渐进迁移 | 不全量改写 82 处行高和 32 处 hover；S1b-1 先建立 token/样式与样板，后续页面逐步采用，不宣称全部使用点一次完成 |
| D2 | UiComposer 先接 S2，再接 S3 | S2 为首个消费方；接口与文件所有权稳定前禁止 S2/S3 并行，稳定后由集成者再评估其他并行关系 |
| D3 | S4 以 knowledge、resource、database 真实页面组成样板 | 使用 §4.5 的具体路由与形态映射；弹窗表单不冒充独立编辑页，独立编辑页如被要求则标为待补充；不得借用 S6 的 data templates |
| D4 | 暂不采用 `maxDiffPixelRatio: 0.001` 自动像素基线 | 当前使用固定环境同条件截图、结构化度量与用户确认；环境及基线成熟后另行评估，不列为当前退出条件 |
| D5 | S3 在 phase-D/E 互斥解除前保持阻塞 | 用户指定目录/文件归属人；确认无重叠修改或完成整合；S2 接口与所有权稳定；仅不同 worktree 不足以解除，Agent 不得自行认领 |
| D6 | S1b 拆为有序 PR：先共享 CSS/语义 token，后 UiComposer | S1b-1 合入并验证后，S1b-2 才能开工；S1b-2 base 必须含 S1b-1 merge commit；不得回到单一大 PR |
| D7 | REQ-064 仅保留遗留主题回落 smoke | 清理或正式支持另立任务，不在本路线内实施或扩范围 |
| D8 | 视觉确认优先为对应 PR 中绑定具体 commit 的结构化评论 | 包含同条件截图、环境信息（OS/浏览器/版本/视口/主题/fixture/数据/角色/启动命令/端口/URL）与明确确认结论；closeout 可索引，不新建独立 sign-off 文档 |

仍需执行时明确的条件（不是重新裁决 D1–D8）：

- S3 的目录归属人目前由用户在派发时指定；未指定前 S3 保持阻塞。
- 若 S4 验收要求独立编辑页而非弹窗表单，需补充候选页面；在补充前该形态标为**待补充**，不得写“全部样板形态已覆盖”。
- S4 强制分页项在 **S4 候选范围（§4.5）内**目前没有经核实的真实候选；范围外已核实的真实分页（同文件 §4.5 补充披露）不改变该结论。按 §4.5 的方案 A/B 待用户决定；未决定前该项不通过，S6/S7 不派发。该缺口不改变 D3 已确认的 knowledge/resource/database 样板组合。
- S1b-1、S1b-2、S2–S8 均未启动；S1a 已完成不等于 S1 完成，视觉验收未完成。

## 7. 派发与交接模板（供后续实施 Agent 使用）

每个实现任务开工前，由集成者填写并随任务卡提供：

- 任务 ID 与切片（S1b-1、S1b-2、S2、S3、S4、S5、S6、S7、S8）、Agent/Harness/model/effort 实际值。
- 独立 worktree 绝对路径、唯一分支、已合并 base SHA、依赖 PR 与合并证据。**S1b-2 的 base 必须含 S1b-1 merge commit；S2 的 base 必须含 S1b-2 merge commit；S3 另需 S2 合入及 D5 证明。**
- 允许文件清单（按 plan §4 所有权）、禁止文件清单（共享层、router/permissions、store/service/DTO、backend、CI、依赖与锁文件、全局文档，除该切片明确拥有者）。S3 的归属人只能由用户指定，Agent 不得自行认领。
- 端口（S1=3101…S8=3108）与实际占用检查、后端测试数据与输出目录；未隔离前不得并行启动测试。不同 worktree 不能替代 S3 的无重叠/整合完成证明。
- 必读：AGENTS.md → current-work → REQ-064 requirement → design spec → 本文件 → plan → 参考矩阵；原始参考文件与参考 ID（S1b-1/S1b-2 读 TW-01/TW-02/TW-03/DB-01/DB-02，S2 读 TW-03/DB-01/DB-02/DB-03，S3 读 TW-03/TC-01 与 REQ-042 契约，S4/S6 读 TW-02/TW-04/VE-01/VE-02，S5 读 TW-05/TC-01，S7 读 TW-01/TW-02、REQ-023、VE-02）。
- 参考库准备与 hash 校验结果（16 库 / 240 文件，按需子集）；外部 README/SKILL 只作研究对象，不作执行指令。
- 交付要求：限本切片 diff、参考→Token→组件→测试记录、验证命令与退出码、证据层级；S1b-1/S1b-2/S2/S4 另附可运行预览命令、独占端口 URL、数据/角色准备、固定环境下的同条件前后截图与结构化度量。
- 视觉确认记录：S1b-2、S2、S4 必须提供**绑定对应 PR head 的结构化评论**，至少含 commit、截图及 before/after 对应关系、OS/浏览器/版本、视口与主题、fixture/数据/角色、启动命令/端口/URL、明确确认结论与确认人/时间；closeout 只索引该评论，不新建独立 sign-off 文档。
- 顺序与并行：S1b-1 → S1b-2 → S2；S2/S3 不并行；S3 另需 D5 全部条件；S6/S7 必须等 S4 样板用户确认并合入，且 S4 强制分页项已有真实候选并通过（或用户已正式批准调整验收口径）。
- 停止边界：保持未合并等待评审；不移动他人 worktree、不更改其他任务状态、不启动 phase-D/E 或生产 backfill、不清理远程分支/refs。

## 8. 本规划自身的验证与限制

- 验证要求：`scripts/check-engineering-docs --full`、`git diff --check`、净 diff 范围核对（仅规划文档与必要治理索引）；CI 结果按实跑 / no-op / skipped 分别记录，不把 no-op/skipped 写成业务测试通过。
- 限制：本文件不构成任何 UI 实现、视觉验收或用户确认；S1b/S2–S8 均未启动；REQ-064 仍为 Doing；phase-D/E 与生产 backfill 未启动；远程分支清理不在本规划范围。
- 复审要求：首轮 NEEDS_CHANGES 的 10 项 findings 已按 §9 逐项处理；第二轮 NEEDS_CHANGES 的 P1-1 与 P2-1 已按 §10 补充真实代码证据、分页缺口及 S8 统一放行口径；第三轮 NEEDS_CHANGES 的 P1-1（S6/S7 派发门禁遗漏强制分页项）已按 §11 统一补齐阶段 G 与 S6/S7 的前置、阻塞和并行条件；第四轮 NEEDS_CHANGES 的 P2×2 与 P3×6 已按 §12 限定 S4 分页否定的范围、披露范围外已核实的真实分页、补齐 S4 卡片自身的派发门，并统一复审状态记录与全文 canonical 措辞。当前为四轮返修后状态，必须等待未参与本轮返修的独立 Agent 对最新 head 复审，不以实施者自检替代独立复审，不推进 Ready、评分或合并。

## 9. 首轮独立复审 findings 逐项闭合映射

| Finding | 原报告位置与问题 | 本次修复位置 | 验证方式 |
|---|---|---|---|
| P1-1（D1） | roadmap G4、S1b 包含/阻塞及 D1 选项仍允许全量改写并列待决；PR body 同问题 | §2 G3/G4 改为 opt-in；§4.1 排除与阻塞项（不全改 82/32 处、不得改回全量改写）；§6 D1；§1 不可变约束第 9 条（不得恢复被 D1 排除的旧方案）；PR body 同步 | 文档复核无“全量改写/统一改共享类”旧方案；`git diff --check`、docs gate、独立复审 |
| P1-2（D2） | roadmap 阶段表及 S2/S3 卡片仍允许 S2/S3 并行，D2 未固定 | §3 固定 S2 为首个消费方；§4.3 禁止 S2/S3 并行；§4.4 仅在 S2 稳定且 D5 解除后进入；§6 D2、§7 | 顺序与依赖逐项复核；PR body 同步；独立复审 |
| P1-3（D3） | roadmap 仅有抽象名称，无具体路由/形态映射，且 data templates 跨 S6 所有权 | §4.5 增加 `/knowledge` 列表、`/resource/:id` 详情、`/database` + `CatalogCreateDialog` 弹窗表单及边界；§6 D3 禁止借 S6 页面 | 代码路由/组件核验（KnowledgeBaseView、FileDetailView、DatabaseView、CatalogCreateDialog）；明确独立编辑页为条件性待补充，不虚称覆盖 |
| P1-4（D4） | roadmap 与 PR body 仍把 `maxDiffPixelRatio: 0.001` 像素基线列为当前可选 | §5 明确当前不引入、非退出条件及与 spec §6 阈值的关系；§2 G7、§6 D4、§7 证据形式 | 搜索阈值只出现在“暂缓/未来评估”语境；CI 不冒充视觉验收；独立复审 |
| P1-5（D5） | roadmap 有互斥但缺客观解除判据，未固定用户指定 owner 和 worktree 不足 | §3、§4.4 列出 S2 稳定 + 用户指定目录/文件归属 + 无重叠或整合完成；§6 D5、§7 明确 worktree 不足且不得自行认领 | 条件逐项可核验；S3 未满足时保持阻塞；独立复审 |
| P1-6（D6） | roadmap 仍为单一大 S1b PR 或拆分待选，未规定 CSS 先行依赖 | §3 改为 S1b-1 → S1b-2 有序 PR；§4.1/§4.2 明确 base、验证与合入依赖；§6 D6、§7 模板 | 核对顺序、base 和退出条件；PR body 同步；独立复审 |
| P1-7（D7） | roadmap 把“仅回落 smoke”与“另立清理/支持”写成互斥选项 | §2 G8 与 §6 D7 合并为 REQ-064 内仅回落 smoke，清理/正式支持一律另立任务 | 文档复核无扩范围表述；独立复审 |
| P1-8（D8） | roadmap 与 PR body 仍允许独立 sign-off 文档，结构化评论字段不完整 | §1、§4.2/4.3/4.5、§5、§6 D8、§7 固定为绑定 commit 的 PR 结构化评论，含截图/环境/结论；closeout 可索引，不新建文档 | 字段清单核对；S8 核对方式一致；独立复审 |
| P2-1 | current-work 下一步仍为“提交并推送规划 Draft PR”，未反映 PR 已发布与复审结果 | current-work 活跃卡改为：PR #670 已发布；首轮 NEEDS_CHANGES（P1×8、P2×2）；10 项返修已完成，等待最新 head 独立复审；保留旧 head 仅为历史定位 | 回读工作台；下一步不再是创建 PR；状态/验证/停止点一致 |
| P2-2 | PR body 声称分层记录 CI，却无 run ID、head SHA 与逐 job 结果 | PR body 的 Validation 增加当前 run、完整 headSha、scope 输出及 Engineering docs 实跑、Frontend/Backend iteration no-op、full hermetic 三项 skipped；保留历史 run 作为旧 head 记录 | `gh run view`/`gh pr checks` 核对 headSha 精确匹配；明确 CI 不提供前后端或 full hermetic 业务测试通过证据 |

## 10. 第二轮独立复审 findings 逐项闭合映射

| Finding | 原报告位置与问题 | 本次修复位置 | 验证方式 |
|---|---|---|---|
| P1-1（S4 强制分页验收缺口） | roadmap §4.5 将 `/knowledge` 定为列表样板，但 design spec §6 要求“列表筛选/分页”；`/resource` 仅固定 limit，`/database/:catalogCode` 的 change-page 为 no-op，原映射不能证明分页验收 | §4.5 新增“强制分页验收映射”：区分已有列表/详情/弹窗表单与强制分页项；记录 `/knowledge` 无分页、`/resource` 固定 limit 100、`/database` 无分页、CatalogDetailPage no-op，以及 `ResourceView.vue` 有分页代码但无当前路由引用。明确 **S4 候选范围内**无合格真实分页候选，S4 不得宣称该项通过（范围限定与范围外披露见第四轮 §12 的 P2-1）；列出方案 A（补充真实候选或另立分页前置工作）与方案 B（用户批准调整验收口径），不替用户拍板 | 只读核对 `app/router.ts`、`ResourceLibraryView.vue`、`KnowledgeBaseView.vue`、`DatabaseView.vue`、`CatalogDetailPage.vue`、`DatasetTabsPanel.vue`、`ResourceView.vue`；确认固定 limit、静态参数和 no-op 不计为覆盖。第四轮另核对 `SkillListView.vue`、`McpServerListView.vue` 的真实分页（见 §12 P2-1）。未新增业务分页，design spec §6 强制要求未弱化 |
| P2-1（S6/S7 对 S8 放行口径） | S6/S7 卡片写成自身验收并合入后即可进入 S8，与 S8 的 S2–S7 全部合入前置不一致 | §3 G 阶段、§4.7 S6、§4.8 S7 统一为：本切片完成自身退出条件后，S8 仍须等待 S2–S7 全部合入并满足 S8 全部前置条件；§4.9 保持同一总前置 | 交叉阅读阶段表、S6/S7/S8 卡片，确认任何单切片合入均不被描述为 S8 充分条件 |

## 11. 第三轮独立复审 finding 闭合映射

| Finding | 原报告位置与问题 | 本次修复位置 | 验证方式 |
|---|---|---|---|
| P1-1（S6/S7 派发门禁遗漏强制分页项） | 阶段 G 依赖、S6 前置与并行条件、S7 前置与阻塞项只要求 S4 样板确认/合入，未包含强制分页项，可能绕过 §4.5 的待决缺口提前派发 | §3 G 依赖、§4.7 S6 前置/可并行/阻塞、§4.8 S7 前置/可并行/阻塞统一增加：**S4 强制分页项已有真实候选并通过，或用户已正式批准调整验收口径**；§8、§11 同步记录。未改变 D1–D8、已核实代码事实或方案 A/B 的待决状态 | 逐段复核阶段 G 与 S6/S7 的前置、阻塞、并行和 S8 总前置，确认单独阅读任一卡片都不能绕过 S4 强制分页门；固定 limit、静态参数、no-op 和无路由组件仍未被算为真实候选；未新增业务分页实现 |

## 12. 第四轮独立复审 findings 逐项闭合映射

第四轮复审覆盖 head `92fd6060cce830fb358a5dfec6dafa94be52f2ad`，结论 NEEDS_CHANGES（P0=0、P1=0、P2×2、P3×6），并确认第三轮 P1-1 已实质闭合。

| Finding | 原报告位置与问题 | 本次修复位置 | 验证方式 |
|---|---|---|---|
| P2-1（分页否定未限定范围） | §4.5 写“没有经核实的真实分页样板”是无范围的全仓否定，但核查范围只覆盖 S4 的 D3 候选；仓库内 `capabilities/skills` → `SkillListView.vue`、`capabilities/mcp` → `McpServerListView.vue` 已挂路由，且审计弹窗内执行记录列表有真实服务端分页 | §4.5 将否定限定为「design spec §6 所要求的 S4 候选范围（knowledge / resource / database 路由）内」；同节补充披露范围外两页的真实分页及三点限定（分页对象是审计弹窗执行记录、页面主列表无分页、归属 S5 非 S4 候选、可否作为 S4 候选或范式待用户裁决）；§4.5 核验范围说明、§6 待决项、§1 不可变约束同步 | 只读核对 `app/router.ts`（`capabilities/skills` / `capabilities/mcp`）、`SkillListView.vue`（`listExecutions` + `auditPrev/auditNext` + `loadSkills()` 无分页）、`McpServerListView.vue`（`listInvocations` 同构）；确认未把范围外页面自动纳入 S4、未解除 S4 门禁、未新增业务分页、design spec §6 未弱化 |
| P2-2（S4 卡片自身派发门禁） | §4.5 S4 卡片「可并行」只写“S6/S7 必须等待 S4 样板确认”，遗漏强制分页门；单独阅读该 bullet 会得到“样板确认即可派发”的不完整读法 | §4.5 S4 卡片「可并行」补齐 canonical 条件「S4 样板用户确认并合入，且 S4 强制分页项已有真实候选并通过（或用户已正式批准调整验收口径）」；§4.5 阻塞项与退出条件、§3 阶段 F、§4.7 / §4.8、§7 模板统一为同一措辞 | 逐段交叉阅读阶段 F/G、S4 卡片的可并行/阻塞/退出条件、S6/S7 的前置·阻塞·并行与派发模板，确认任何局部入口都不产生“样板确认即可派发”的读法 |
| P3-1（复审状态只记首轮） | 文件头与 §0 基线表只记首轮结论，与 §8 / §10 / §11 的三轮记录不自洽 | 文件头复审状态补记四轮结论及各自 head；§0 规划 PR #670 行同步；§8 复审要求补记第四轮 | 与 §9–§12 四张映射表逐轮对照 |
| P3-2（远程分支计数失准） | §0 写“46 个；实时 `git ls-remote`”，实测为 47（含本 PR 分支），且“实时”易被读作当前值 | §0 改为带日期与查询时点的历史快照并说明计数口径（含本 PR 任务分支），标注非当前计数、引用时须重新查询 | 本轮重新执行 `git ls-remote --heads origin` 计数核对 |
| P3-3（派发模板措辞漂移） | §7 用“强制分页项已闭合”，与全文“已有真实候选并通过”不是同一措辞 | §7 顺序与并行条目改为 canonical 条件全文；§3 阶段 F 同步措辞 | 全文检索该门相关措辞，逐处对齐 |
| P3-4（§9 D1 映射位置不实） | §9 P1-1（D1）称修复位置含“§7 禁止回退”，但 §7 无 D1 / 82 / 32 / 全量改写内容 | §9 该行修复位置改为 §4.1 排除与阻塞项、§6 D1、§1 不可变约束第 9 条 | 逐条核对 §9 / §10 / §11 各行引用的章节确实存在对应内容 |
| P3-5（S4 交付物预设分页为既有行为） | §4.5 S4 交付物写“搜索/分页/上传/详情/图谱/问数原行为回归证据”，预设 S4 已存在分页行为，与 §4.5 结论矛盾 | §4.5 交付物改为“搜索/筛选/列表/上传/详情/图谱/问数原行为回归证据”，并明确分页不列入当前原行为回归对象、按 §4.5 门控单独验收 | 与 §4.5 分页映射表、退出条件交叉复核 |
| P3-6（不可变约束未登记分页门） | §1 登记了“三类用户视觉确认门不可弱化”，但未并列登记同样“未经用户批准不可弱化”的 S4 强制分页门 | §1 增列第 10 条：S4 强制分页门不得未经用户批准弱化，含闭合条件与禁止冒充 / 禁止宣称完成 / 禁止派发 S6/S7 | 与 §3 / §4.5 / §4.7 / §4.8 / §7 逐处对照 |

# REQ-064 全局 UI 升级实施计划与 Agent 接力

日期：2026-10-22。本轮范围：S0 文档塑形；S1–S8 均未启动。
需求：[REQ-064](../../01-product-planning/05-requirements/REQ-064-global-ui-upgrade.md)。
依据：[设计 spec](../01-specs/2026-10-22-req-064-ui-design-system.md)、[参考矩阵与检查命令](../01-specs/2026-10-22-req-064-reference-matrix.md)、[manifest](../01-specs/2026-10-22-req-064-reference-manifest.json)。

## 1. 当前事实与排程

- 源码研究基线为 `6122d29a177e2a67ed0dad626d4066261dae0d90`；写文档前已快进到本地 `origin/main` 的已合并 closeout `05adab213a831fa46f290b3eb2086fba2da36613`（#662）。独立分支 `codex/req-064-ui-upgrade-planning`，worktree `/Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase-wt-req064-planning`。未重置、stash 或搬动其他 Agent 文件。
- 当前工作台仍持有 REQ-042 相关任务；其后端 discovery 已在该基线落地，但 UI 发送与 TD-114 B 组不能据此宣称完成。只增加 REQ-064 的 **S0 规划文档任务卡**，不修改其他卡片状态，也不增加第四个候选入口。
- REQ-064 整体保持 Shaping；文档经评审再转 Ready。S1 开工需集成者依据最新工作台确认既定排程及 TD-114 B 组状态，不能把本次文档交付当作 UI 实现开工。
- 此后每个切片从**所需依赖已合并的明确 commit**创建独立 worktree；不从另一个 Agent 的脏目录复制文件。切片完成指代码/验证交接，REQ-064 Done 还需全站验收和合并事实。

## 2. AI Delivery Profile

- Complexity：本轮文档中等；S1/S2/S3 高，普通页面中；涉及权限、审批/恢复行为变更须退回对应高风险 REQ，不能藏在 UI 切片。
- Risk：共享 CSS 波及全站、可访问性、请求身份/草稿回归、权限显示、并行测试误连服务、来源不可移植。
- Lead：本轮 Codex（GPT-6，运行配置以任务记录为准）；后续由集成者指定共享层负责人及页面负责人，开工任务卡登记实际 Harness/model id/effort，不把推荐 profile 当作实际执行记录。
- Delegable：S1 合入后，仅允许 §4 列出的非重叠页面和各自测试切片；CSS/公共组件/导航/协议/全局文档不能分散修改。
- Independent Review：每个切片由未参与实现的另一 Agent 评审；S1 重点检查全站影响，S2/S3 重点检查状态与证据；实际第二 Harness/model 在交接卡记录。参考 [AI Delivery Routing](../../03-engineering-governance/03-matrices/agent-platform-ai-delivery-routing.md)。
- Human Gate：产品负责人确认 S1 控件/外壳、S2 问答和 S4 企业列表样板的视觉基线后再扩展；后续 merge 仍需用户明确授权，Agent 不自动合并。
- Validation：§5 的文档/前端/浏览器矩阵；只报告实际达到的静态、fixture、真实环境证据层级。

## 3. 切片交付顺序

| 切片 | 负责人角色与依赖 | 工作和可审查产物 | 退出条件 |
|---|---|---|---|
| S0 规划 | 本轮规划 Agent | Requirement/spec/plan、16 库矩阵、hash manifest、Backlog 与纯文档任务卡 | 文档门禁/引用检查；独立评审；不改任何业务代码 |
| S1 共享基础与外壳 | 唯一共享层 Agent；S0 评审及排程就绪后 | Token/`ui-*` 收敛、已有共享组件、UiComposer、外壳、代表性控件截图；Playwright 服务隔离 | 双主题/键盘/控件/导航回归，兼容 props/events；样板接受并合入后才派页面切片 |
| S2 AI 问答 | Chat Agent；依赖 S1 | 采用 UiComposer，回答阅读区、建议问题、错误/停止/引用、滚动；只适配现有 API | IME/请求身份/停止恢复/引用安全/移动截图；样板接受；不新增流式/语音能力 |
| S3 Workspace 展示 | Workspace Agent；依赖 S1；与 WS-S2 phase-D/E 同目录任务互斥 | 三栏与窄屏样式、会话列表/草稿/已有 Run 详情；消费当时已交付能力 | workspace 既有回归、草稿/选择/恢复不丢失；未交付按钮仍门控；不实现 SSE/审批协议 |
| S4 知识、资源与数据 | Data Agent；依赖 S1 | knowledge/resource/database 目录全部已交付视图与子组件；确定企业列表/表单样板 | 搜索/分页/上传/详情/图谱/问数原行为、双主题与长表格；样板接受 |
| S5 应用与能力中心 | Apps Agent；依赖 S1 | ai-apps、skill-registry、mcp-registry 页面 | 真实 Registry 状态、角色访问、错误/空态与卡片密度一致 |
| S6 管理与模板 | Admin Agent；依赖 S1 + S4 样板 | admin 目录，模板字段/编辑/导入/校验显示 | 表单错误、焦点、保存/取消、危险确认及权限回归 |
| S7 背调与外围页面 | Business Agent；依赖 S1 + S4 样板 | due-diligence、HomeView、share、ForbiddenView；登录兼容检查 | 报告/证据/制审行为不变，分享 token 路由与首页权限回归 |
| S8 集成与收口 | 集成 Agent；依赖 S2–S7 | 全路由审计、视觉矩阵、文档/状态更新和未来功能接入核对 | required checks、样板一致、无遗漏路由；PR 合并后才能收口 |

可行并行批次：S1 合入后 S2/S3/S4/S5 可独立开发；S4 样板合入后 S6/S7 可独立开发。S3 与另一个正在修改 Workspace 的 Agent 绝不同时开工。默认合入次序 S1→S2→S3→S4→S5→S6→S7→S8；某切片依赖未交付能力时记录阻塞，其他独立切片可继续，集成者显式记录调整后的次序。

不规定虚构的日期/工时。首个 S1 PR 的实际工作量作为后续排期依据；单切片过大时只按已有页面/模式继续拆分，保持一个 PR 一个主要风险面。

## 4. 文件所有权与覆盖清单

以下源码路径均相对 `packages/web/src/`。分支按 `codex/req-064-sN-<topic>`，目录用该切片专属 worktree；分配时写出实际绝对路径和 base SHA。

| Owner | 可改范围 | 禁止范围 / 冲突处理 |
|---|---|---|
| S1 共享层 | `assets/css/`、`components/`、`views/LayoutView.vue`、外壳测试；新增 UiComposer；`packages/web/playwright.config.ts` 及公共 e2e fixture（路径相对仓库） | 不改业务 API；router/nav/permissions 的现有语义不变；必要修改单列说明。所有其他 Agent 不写这些文件 |
| S2 Chat | `views/ai-chat/` 及新增 `e2e/req064-chat-*`（e2e 相对 web） | 不改 services/stores、共享 Markdown/CSS/EvidenceCard；需调整共享组件先提共享层补丁 |
| S3 Workspace | `views/agent-workspace/` 及 workspace e2e | 不改 workspace store/服务/事件协议；phase-D/E 或 WS-S3 负责人占用时本切片等待 |
| S4 Data | `views/knowledge/`、`views/resource/`、`views/database/` 及 `e2e/req064-data-*` | 不改共享 FieldEditor/TableRenderer/KGGraph 等；由 S1 所有者按已定义接口修正 |
| S5 Apps | `views/ai-apps/`、`views/skill-registry/`、`views/mcp-registry/` 及 `e2e/req064-apps-*` | 不写 admin 目录、导航/角色判断和 Registry 服务 |
| S6 Admin | `views/admin/` 及 `e2e/req064-admin-*` | 不改共享组件/DTO/权限；数据模板仍归知识与数据导航 |
| S7 Business | `views/due-diligence/`、`views/HomeView.vue`、`views/share/`、`views/ForbiddenView.vue` 和对应测试 | `views/auth/` 只回归；若公共控件升级致登录回归，由 S1 负责人修；不改背调领域服务 |
| 集成 Agent | 本需求文档、工作台/Backlog/日志、公共测试配置及最终兼容回归 | 页面 Agent 只写自己的 PR 交接，不在同一 plan 内抢写过程状态 |

`package.json`/锁文件、`app/router.ts`/nav/permission、`stores/`、`services/`、shared schema、backend、CI 门禁不在页面切片 allowlist。发现功能问题先登记所属 REQ/BUG，不在 UI PR 扩范围。共享层补丁由一个负责人顺序提交；受影响页面在该补丁合入后更新基线并复验。

### 4.1 路由覆盖（来自基线 router）

| 已有路由 | 归属与处理 |
|---|---|
| `/`、全局外壳 | Home 属 S7，Layout 属 S1；避免两者由同一“首页”模糊任务并行修改 |
| `/ai-chat` | S2 |
| `/agent-workspace` | S3；保留既有 feature flag 和真实能力门禁 |
| `/knowledge`、`/resource`、`/resource/:id`、`/database`、`/database/:catalogCode` | S4；目录内未被路由直接引用的子组件也盘点；不顺手删除旧文件 |
| `/ai-apps`、`/ai-apps/admin`、`/ai-apps/admin/:id`、`/ai-apps/:code` | S5 |
| `/capabilities/skills`、`/capabilities/mcp` | S5 |
| `/data/templates`、`/data/templates/:id`、`/system` | S6 |
| `/apps/enterprise-360-dd`、`/tasks/:id`、`/reports/:reportId`（后两者接同一背调前缀） | S7 |
| `/share/:token`、`/403` | S7；包括独立于主外壳的页面 |
| `/login` | S8 兼容回归，维持 REQ-023 蓝色品牌面与表单语义 |
| 四个 `/apps/` 教育占位路由 | S8 确认 feature/权限隐藏及占位不扩功能；不将 AppPlaceholder/旧 SkillEditor 视为已交付产品 |
| `/skill-editor`、`/admin`、`/admin/template[/:id]`、`/admin/mcp-servers`、`/admin/skills` | S8 旧链接重定向回归，路径与权限不变 |

每批开始时从最新 router 再生成路由清单，与此表做差集；新增路由由集成者明确归属后再分派。不可仅凭当前表宣称未来也已全覆盖。

### 4.2 worktree 与测试环境隔离

1. 先读工作台并检查 `git status --short --branch`、`git worktree list --porcelain`。干净不代表无人占用，分配记录必须包含任务负责人；不清理或复用未知 worktree。
2. 集成者分配一个实际已合并 base SHA、唯一分支和全新目录，再建 worktree。两个 Agent 不在同一目录轮换分支；不以 symlink 共享 `node_modules`、dist 或测试输出目录。
3. 未提交改动归原任务所有；不 reset、stash、拷贝到新 worktree，也不使用 `git add .` 包含未知文件。共享 `.git` 下由集成者顺序处理 fetch/集成/维护，页面 Agent 只在自己的分支提交明确 allowlist 文件。
4. **端口也要隔离**：现有 Playwright 固定 3000 且本地 `reuseExistingServer=true`，S1 改为从 `METAEDU_E2E_PORT` 读取端口（默认仍 3000，校验 1024–65535），baseURL/server URL 同源、Vite 加 `--strictPort`、`reuseExistingServer=false`。遇占用直接失败，不杀别人的进程或自动换端口。
5. 后续默认保留端口 S1=3101、S2=3102…S8=3108；运行前实际检查占用并登记，冲突由集成者重新分配。开发服务另行登记自己的端口；服务由启动它的 Agent 关闭。
6. fixture/UI 测试不连接共享数据库，不写生产/真实租户。需要真实后端验收时依据仓库 testing 规则使用专属测试实例/数据集；多 worktree 不能以独立目录为由并发跑同一库的迁移或清理。
7. S1 的测试隔离修改尚未交付前，现有 Playwright **串行运行**，并验证 3000 服务确实来自当前 checkout。不能只设一个尚未被配置读取的环境变量便声称隔离成功。
8. 集成前逐一确认工作树、HEAD、文件 allowlist、依赖 SHA；同步最新已合并基线，复验后交接 PR。合并冲突按每个任务的意图解决，不用整文件 `ours/theirs` 覆盖另一个任务；无文本冲突也必须查视觉/语义冲突。

## 5. 验证矩阵与交付门禁

| 范围 | 必跑 | 额外验收 |
|---|---|---|
| S0 文档 | `scripts/check-engineering-docs`、`git diff --check`、参考 manifest 只读检查 | 链接/编号/状态一致；原 checkout 未受影响；差异仅本任务文档 |
| 所有 UI 切片 | `pnpm --filter @metaedu/web lint`、`pnpm --filter @metaedu/web typecheck`、`pnpm --filter @metaedu/web build`、相关 Vitest | spec 状态矩阵和截图；代码/演示/真实能力证据分层 |
| S1 | theme/Layout/NavBreadcrumb 测试，全站前端 Vitest，navigation Playwright | 两主题、角色/深链/旧主题兼容；不同 worktree 端口不串用；公共控件基线 |
| S2 | `pnpm --filter @metaedu/web test -- src/views/ai-chat`，既有 EvidenceCard/DocumentSourceList 测试，新增 chat e2e | IME、空提交、多行/回缩、请求身份、停止恢复、文件链接、无证据、滚动和布局 |
| S3 | workspaceDraft/workspace store 既有测试（只读回归）及 WorkspaceView 测试、workspace e2e | 草稿隔离、会话切换、显式运行详情、归档/恢复、禁用发送、各容器断点 |
| S4–S7 | 对应页面 Vitest + 切片 e2e | 筛选/排序/分页、空/错/加载、表单校验、无权限、长表格/报告/来源 |
| S8 集成 | 全量前端 Vitest + 全量 Playwright、lint/typecheck/build、docs/diff 门禁 | 完整路由/角色/主题/视口矩阵；真实环境手动验收只按实际执行报告 |

S1 后 Playwright 命令示例（S2）：`METAEDU_E2E_PORT=3102 pnpm --filter @metaedu/web test:e2e req064-chat`。新增文件必须匹配现有 `*-desktop.spec.ts` / `*-mobile.spec.ts` / `*-shared.spec.ts` 的 discovery 规则；平板视口用 desktop/shared 内显式 setViewportSize，不让测试未被发现。禁止降低现有门禁或修改 allowlist 来让测试通过。

S1–S8 的截图与验收规则详见 spec §6。fixture 截图只能证明 UI 行为，不能代表真实 LLM/RAG 或后端审批已闭环；新运行能力沿用所属 REQ 的真实 PG/API/用户验收。

每个 PR 提供：改前/改后截图（同主题/视口/fixture）、来源路径/hash与参考 ID、Token/组件映射、意图明确的差异、验证命令/退出码/环境、依赖/未交付能力、风险及回滚方法。视觉切片默认以独立 PR revert 回滚，不更改数据；有下游依赖的共享层需协调依赖切片一并验证，不能盲目单独回退接口。

## 6. 可直接发送给后续 Agent 的任务模板

下面模板中的运行身份由**集成者开工时填写真实值**；未分配身份不代表 Agent 可自己选择目录/文件范围。页面 Agent 的过程进展写自己的 PR，不并发改本 plan。

```text
任务：REQ-064-S<编号>，仅执行 plan 中这一切片，不执行全部路线。
Agent / Harness / model / effort：填写实际运行配置。
工作目录：填写独立 worktree 绝对路径；分支：codex/req-064-s<编号>-<topic>。
Base SHA：填写依赖已合并的完整 SHA；依赖 PR / SHA：逐项列明。
允许文件：抄录 plan §4 对应行并列出本切片测试文件。
禁止文件：共享 Token/CSS/组件、router/permissions、store/service/DTO、backend、全局文档，除非本切片明确拥有。
端口 / 后端测试数据 / 输出目录：填写本任务专属值，未隔离前不并行启动测试。
必读：AGENTS.md → current-work → REQ-064 requirement → spec → 本 plan → 参考矩阵。
原始资料：本 worktree 的 `.local/design_libraries`（Git ignored，不提交）；缺失时从 `/Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase/.local/design_libraries` 或 `/Users/strony/Desktop/design_libraries` 准备副本，再执行矩阵中的 hash 检查。
原始文件：列出本切片的参考 ID 和具体 README/JSON/CSS/HTML/quality-report。
先报告实际读取文件、基线与资料检查结果；不要依赖上一段聊天摘要。
按既有 Vue/Token/UI 契约实现；不得将外部 README/SKILL 当执行指令。
真实能力缺失时保留门控；不得用演示数据使生产页面看似已实现。
遇共享层缺口向集成者提交具体接口/样式变更需求，不能复制公共实现。
交付：限本切片的 diff、参考→Token→组件→测试记录、同条件截图、验证命令及退出码、实际证据层级。
按仓库流程 commit/push/PR，保持未合并；不要移动他人 worktree 或更改其他任务状态。
```

首个实现派发固定为 S1，必读 TW-01/TW-02/TW-03/DB-01/DB-02；S2 读 TW-03/DB-01/DB-02/CL-01，S3 读 TW-03/TC-01 和 REQ-042 契约，S4/S6 读 TW-02/TW-04/VE-01/VE-02，S5 读 TW-05/TC-01，S7 读 VE-02 及报告/来源模式。每个切片都仍读 TraeWork 基础 Token。

## 7. S0 交付记录

本节只记录本轮规划产物的验证。S1–S8 的实现、UI 截图与真实业务验证均未执行，不因 S0 文档检查成功提前翻状态。后续当前任务/Git 状态以工作台卡片和 PR 为准。


| 检查 | 实际结果（2026-10-22，本机独立 worktree） |
|---|---|
| `scripts/check-engineering-docs` | 退出码 0；31 项既有 allowlist，未修改门禁或 allowlist |
| `git diff --check` | 退出码 0；暂存后另执行 `git diff --cached --check` 覆盖新增文件 |
| 矩阵内原样 Python 校验命令 | 全库 16 套 / 240 文件匹配；`REQ064_LIBRARIES=TraeWork,Doubao` 子集 61 文件匹配；均退出码 0 |
| 校验命令失败路径 | 不存在的根目录：退出码 1、240 项缺失；未知库名：退出码 1；按预期拒绝，未改动资料 |
| 本轮文档链接及登记 | 4 份新增 Markdown 的 18 个本地链接目标存在；Backlog 仅新增 1 条 REQ-064 |
| 修改边界 | 仅 7 个需求/规范/计划/登记文件；原 checkout 未被本任务写入，既有任务卡与评分总账未改 |
| 本地参考副本 | `.local/design_libraries` 已在主项目与本 worktree 准备；2,449 个文件约 17 MB，逐文件 SHA-256 核对通过；路径由本地 `.git/info/exclude` 忽略，不进入 PR |
| 未运行 | UI/Vitest/Playwright/前后端构建、真实 PG、真实 LLM 和原预览浏览器验收；本轮是文档交付，不宣称视觉或业务验证通过 |

当前无本轮本地校验失败；独立评审、PR CI 与后续实现验收按各自阶段执行。资料清单只覆盖选定入口，不代表所有图片、字体、脚本依赖均已封存或可离线运行。

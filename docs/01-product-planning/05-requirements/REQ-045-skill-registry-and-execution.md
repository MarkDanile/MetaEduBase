# REQ-045: Skill 注册、管理与调用能力（最小 Skill registry）

Status: 🔵 Ready
Priority: P0
Milestone: P3
App: 平台基座能力（下游驱动 APP-005 / REQ-046 企业 360 背调）
Source: 依赖链 REQ-044 -> REQ-045 -> REQ-046 串行；REQ-044 已 🟢 Done
Related: REQ-044（MCP registry，治理骨架来源）/ REQ-046（背调 Skill 首个消费方）/ REQ-043（Agentic 编排，V2）/ REQ-047（产物归档）
External:
- 企查查 Skill 市场: https://agent.qcc.com/skills
- Anthropic Agent Skills（SKILL.md 规范）

## 背景

REQ-044 交付了平台级 MCP registry：tenant 级注册 / 启停 / 角色权限 / 凭证引用 / 调用审计，并以企查查 QCC 为首个真实 server 完成验收。但"工具"只解决"拿到事实"——REQ-046 背调场景还需要一层 **SOP（标准作业程序）能力**：把"查哪些维度、按什么顺序调工具、如何组织成一份结构稳定的报告"固化为可复用、可治理、可审计的资产。

当前这层能力缺失：

- 背调 SOP 只散落在 REQ-046 文档和各 AI IDE 的提示词里，产品后端没有注册、版本、权限和执行入口。
- 如果每个业务页面各自硬编码一套"调哪些 QCC 工具 + 怎么拼 prompt"，SOP 会失控、无法审计、无法复用到其他场景（租约预警、招投标合规等同属合规风控 SOP）。
- 企查查官方 Skill 市场提供了可复用的尽调 / 背调类 SOP，但产品后端没有"导入 -> 注册 -> 治理 -> 执行"的最小闭环。

需要一个平台级最小 **Skill registry**：以**声明式 SOP 模板**为 Skill 形态，支持导入 / 注册 / 启停 / 角色权限 / 版本 / 执行审计，并提供平台编排执行引擎（按 SOP 步骤调 REQ-044 MCP 工具收集事实，再由 LLM 按模板合成结构化产物）。首个真实 Skill 为**企业 360 背调 SOP**。

## 目标

- `metaedu.skills` 注册表 + CRUD / 启停 API，唯一约束 `(tenant_id, code)`，与 REQ-044 `mcp_servers` 同构。
- Skill 形态为**声明式 SOP 模板**（YAML/Markdown 定义：步骤、所需 MCP 工具、合成 prompt / 输出 schema 引用）；DB 存模板定义，平台可治理。
- per-skill 角色权限（`allowed_roles`），执行路径强制校验；`enabled` 默认 false。
- `metaedu.skill_execution_audit` 执行审计：skill、版本、subject 摘要（digest）、各步骤工具调用引用、LLM 合成 digest、ok / 错误 / 耗时、tenant、caller。
- 平台编排执行引擎 `SkillRunner`：解析 skill -> 校验 enabled / 角色 -> 按 SOP 步骤经 `MCPInvocationService` 调 MCP 工具（复用 REQ-044 审计）-> LLM 按模板合成 -> 写执行审计；业务侧统一入口。
- 版本管理：同一 code 多版本，执行固定到具体版本，支持启停切换。
- 以企业 360 背调 SOP 为首个真实 Skill，用真实 QCC MCP + LLM 完成端到端执行验收。
- 最小管理页：列表 / 注册（导入模板）/ 启停 / 版本 / 删除 / 执行审计查询。

## 待塑形决策

> 本节为塑形期决策清单；决策确认后落入 spec 的"决策记录"表。

| # | 决策点 | 候选 | 状态 |
|---|--------|------|------|
| D1 | Skill 实体形态 | **声明式 SOP 模板（已选）** / 可执行脚本包 / 纯引用注册 | ✅ 已确认 |
| D2 | 执行模型 | **平台编排：MCP 工具 + LLM 合成（已选）** / 交给 REQ-043 Agent 自主执行 / V1 无执行仅注册 | ✅ 已确认 |
| D3 | 代码归属与首个 Skill | **新建 `skill_registry` 上下文，背调 SOP 为首个 Skill（已选）** / 完全通用 registry、背调 SOP 归 REQ-046 | ✅ 已确认 |
| D4 | SOP 模板 schema 字段集 | **两层（已选）**：A 层元数据对齐 agentskills.io 标准（`name` kebab-case ≤64 / `description` ≤1024 / `metadata.version` / `allowed-tools`），B 层 SOP 正文借鉴企查查官方 SKILL.md 范式（`mcp_dependencies` / `principles` / `steps[tools+analysis_rules+output]` / `rating` / `report_template` 填空骨架 / `params`）；DB 存 YAML 模板正文 | ✅ 已确认 |
| D5 | 步骤对 MCP 工具的引用方式 | **按 `server_code.tool_name` 绑定 REQ-044 registry 行（已选）**，与 structured_data `MCPAdapter` 同口径，权限与审计完全复用 / 自由文本 | ✅ 已确认 |
| D6 | 版本模型 | **同 code 多版本（已选）**：`(tenant_id, code, version)` 唯一，执行固定到具体版本，版本可独立启停 / 单版本覆盖 | ✅ 已确认 |
| D7 | LLM 合成输出契约 | **结构化产物（已选）**：按 `report_template` 填空骨架 + 事实 / AI 分析 / 待人工确认分区（对齐 REQ-046 AC-5），报告正文作为产物返回不落审计库 / 纯自由 Markdown | ✅ 已确认 |
| D8 | 执行入口 | **内部 service `SkillRunner`（已选）** + 管理页"试运行"调试入口（仍受 RBAC + 审计约束）；不开通用公开 invoke API | ✅ 已确认 |

## 验收标准

> 塑形确认后细化到 spec；此处先列骨架。

| ID | 内容 |
|----|------|
| AC-1 | `skills` / `skill_execution_audit` 建成，唯一约束生效，migration upgrade / downgrade 幂等。 |
| AC-2 | CRUD + 启停 API 可用；管理操作仅 admin / data_admin / super_admin，其余 403。 |
| AC-3 | SOP 模板 schema 校验：非法模板（缺步骤 / 引用了不存在的 MCP 工具）被拒绝并返回稳定错误。 |
| AC-4 | 禁用 skill 执行被拒（稳定错误码）并写审计；启用后恢复。 |
| AC-5 | 不在 `allowed_roles` 的角色执行被拒并写审计 ok=False。 |
| AC-6 | 执行审计含 skill / 版本 / subject digest / 各步骤 MCP 调用引用（关联 REQ-044 审计）/ LLM 合成 digest / ok / 耗时 / tenant / caller；原始事实与报告正文不落审计库。 |
| AC-7 | tenant A 的 skill 对 tenant B 不可见、不可执行；审计按 tenant 隔离。 |
| AC-8 | 执行引擎按 SOP 步骤经 `MCPInvocationService` 调 MCP 工具：某步骤工具未注册 / 禁用 / 无权限 / 失败时，执行显式失败并写审计，不编造事实。 |
| AC-9 | 用真实 QCC MCP + 真实 LLM，对 1 个样例企业完成背调 SOP 端到端执行：产出结构稳定的报告草案（事实 / AI 分析 / 待人工确认分区），执行审计齐备；secret 与原始企业敏感数据不进审计。 |
| AC-10 | 最小管理页可用：列表（本 tenant）、注册（导入模板）、启停、版本切换、删除、执行审计查询；管理按钮按角色显隐，越权被 API 拒。 |
| AC-11 | 版本管理：同 code 可注册多版本，执行固定到指定版本，切换版本后新执行走新版本。 |
| AC-12 | 完成后同步 Backlog / current-work / work-log，Requirement / Spec / Plan 状态与事实一致。 |

## 非目标

- 不做通用 Skill 市场（发现 / 评分 / 上架下架 / 第三方上传审核）。
- 不做可执行脚本包 / 代码沙箱执行（V1 只做声明式 SOP 模板编排）。
- 不做 Agentic 自主规划 / 多工具重试 / 会话级工具可用性编排（归 REQ-043）。
- 不做背调业务编排、企业主体锚定、报告归档与人工确认闭环（归 REQ-046 / REQ-047）；REQ-045 只交付可被执行的背调 SOP Skill 与通用执行引擎。
- 不做内部业务系统 MCP 契约抽象（归 REQ-048）；背调 SOP 首版只依赖已就绪的 QCC MCP。
- V1 前端只做最小管理页；不做 SOP 可视化编辑器、执行 DAG 图、统计图表（V2）。
- 不做执行配额 / 限流 / 计费（V2）。

## 验证计划

- migration 测试：upgrade / downgrade + 唯一约束冲突用例。
- Registry service / API 单测与契约测试（CRUD / 启停 / 版本 / RBAC 矩阵 / SOP schema 校验）。
- SOP 模板解析与校验单测（合法 / 缺步骤 / 引用不存在工具 / 版本固定）。
- 执行引擎集成测试：httpx mock MCP transport + mock LLM，断言步骤调用顺序、失败分支、审计字段（digest 非原文）。
- 跨租户隔离集成测试（两 tenant 互不可见 / 不可执行）。
- 真实端到端验收：真实 QCC MCP + 真实 LLM 跑背调 SOP（手工验收，不冒充 CI），验收报告记录步骤数 / 耗时 / digest，不记 secret / 企业敏感原文。
- `scripts/check-engineering-docs`、`git diff --check`、`ruff`、相关回归测试。

## Delivery Record

| 日期 | 动作 | 事实 |
|------|------|------|
| 2026-07-20 | 登记 / 塑形启动 | REQ-044 🟢 Done 后启动 REQ-045 塑形；用户确认 3 项核心决策：Skill 形态=声明式 SOP 模板、执行模型=平台编排（MCP 工具 + LLM 合成）、代码归属=新建 `skill_registry` 且背调 SOP 为首个真实 Skill；并行调研企查查官方 SOP 形态与 Anthropic / Codex 声明式 Skill 规范以定模板 schema。 |
| 2026-07-20 | 塑形确认 -> Ready | 调研确认企查查官方 SKILL.md 公开可抓（`agent.qcc.com/skill/v1/{category}/{id}/SKILL.md`，27 个 skill，背调相关 kyb-verification / credit-due-diligence / ic-memo / ubo-screening 等），其"工作流维度→工具链→量化阈值→填空式报告骨架"范式 + agentskills.io 标准 frontmatter 共同定下 D4 两层模板 schema；据此敲定 D4–D8（两层模板 / `server_code.tool_name` 绑定 / 同 code 多版本 / 结构化产物分区 / 内部 `SkillRunner` 入口）；Status 🟣 Shaping -> 🔵 Ready，进入 spec / plan。 |

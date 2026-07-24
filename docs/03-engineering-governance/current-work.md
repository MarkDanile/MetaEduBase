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

### REQ-047-E0: Execution identity、Binding 与 Snapshot contract

状态：🟡 进行中
类型：superpower / plan-do
领域：`agent_execution` / durable control plane
当前执行模式：联合 Core Plan Slice E0
最近接手工具：Codex + GPT-5.6 Sol `xhigh`
分支：`codex/req-047-e0-execution-identity`

需求来源：
- Requirement: [REQ-047](../01-product-planning/05-requirements/REQ-047-agent-run-artifact-approval-center.md)
- Spec: [Conversation/Message/Run/Event 联合核心契约](../02-delivery-plans/01-specs/2026-07-24-req-041-047-conversation-run-contract.md#6-agent_execution-数据契约)
- Plan: [Slice E0](../02-delivery-plans/02-plans/2026-07-24-req-041-047-conversation-run-contract-plan.md#slice-e0execution-identitybinding-与-snapshot-contract)
- 架构约束：`agent_execution` 不导入 `agent_workspace` ORM/repository，不建立跨 context FK

当前进展：最小 catalog、Binding ingest cursor、版本化 Snapshot、Direct RAG bootstrap 与 `029` migration 已完成；ACK mutation 明确留给 E1 与 RunEvent/receipt 同事务实现，E0 不暴露独立推进接口。
下一步：完成 commit、PR、CI 与 merge；合并后将 E0 移入最近完成并推荐 E1。
验证状态：E0 专项 21 passed；Workspace+Execution 联合 39 passed；全量 hermetic 1411 passed / 4 deselected；Ruff 0、mypy baseline 0 regressions、migration downgrade/upgrade、docs gate 与 diff check 通过。独立 `max` 反例审查原 1 P1/3 P2 全部关闭，最终 P0/P1=0。
交接备注：严格止于 E0；不得加入 AgentRun/TurnInput/RunEvent、Pi SDK/Worker、Runtime 调用、Tool Gateway、SSE、前端或 W1 DELETE/`/turns`。

## 下一批候选任务

按"建议执行顺序"排序；候选区只保留近期 1 到 3 个入口，完整任务池回 `docs/01-product-planning/04-backlog.md` / `docs/03-engineering-governance/technical-debt.md`。

| 优先级 | 任务 | 状态 | 建议下一步 | 事实源 |
|--------|------|------|------------|--------|
| P0 | REQ-047 Core Slice E1：Execution durable core | 🔵 就绪 | E0 合并后实施 Run/Input/Event、连续 ACK、FIFO 与终态；完整 REQ-047 仍保持 Shaping | [Requirement](../01-product-planning/05-requirements/REQ-047-agent-run-artifact-approval-center.md) / [Plan](../02-delivery-plans/02-plans/2026-07-24-req-041-047-conversation-run-contract-plan.md#slice-e1execution-durable-core) |
| P1-P | REQ-060 企业 Agent 控制台信息架构与权限化导航 | ⚫ Candidate | 可并行补导航矩阵与 plan；移除重复 Skill、归位 MCP/Skill，并建立 permission/nav 单一事实源 | [Requirement](../01-product-planning/05-requirements/REQ-060-enterprise-console-information-architecture.md) |

## 最近完成

最近完成区默认最多保留 20 行（按 `docs/03-engineering-governance/01-rules/workbench.md#保留策略` 强约束）。超过 20 行时，必须一次性批量归档，只保留最新 12 行；第 13 行及以后全部移出。不得每次只移动 1 行。本表只承担"近期完成窗口"的角色，详细验证、行为变化、PR 描述和复盘见 `docs/03-engineering-governance/work-log.md`、对应技术债总账、plan 或 PR。

按"最近优先"（最新任务在最上）排序：

| 日期 | 任务 | 状态 | 摘要 | 事实源 |
|------|------|------|------|--------|
| 2026-07-24 | Agent Workspace W1 durable store | 🟢 完成 | `agent_workspace` 四业务表 + inbox/outbox、owner-private API、CAS/keyset、双 seq 与完整摘要落地；DELETE/`/turns` 保持关闭；全量 1390 passed | [PR #479](https://github.com/MarkDanile/MetaEduBase/pull/479)（`88bf3c35`） |
| 2026-07-24 | Conversation/Run 联合核心契约塑形 | 🟢 完成 | 冻结 16 项核心决策与 8 Slice plan；四轮独立 `max` 反例审查 P0/P1 从 9 -> 4 -> 1 -> 0；纯文档，无代码/迁移/API/UI | [PR #477](https://github.com/MarkDanile/MetaEduBase/pull/477)（`265f59c7`） |
| 2026-07-24 | REQ-059 企业级可控 Agent 平台源码研究与控制面塑形 | 🟢 完成 | 八项 Architecture Gate 决策、AI Delivery Matrix、园区应用顺序和 12 仓库固定源码导航完成；文档门禁、路径核验、独立复审和用户签字通过 | [PR #475](https://github.com/MarkDanile/MetaEduBase/pull/475)（`132730a0`）/ [Requirement](../01-product-planning/05-requirements/REQ-059-enterprise-agent-platform-kernel.md) |
| 2026-07-23 | TD-084 GitHub Actions Node 24 与 hermetic 测试分类收口 | 🟢 完成 | 6 类 Action 升级 Node 24；slow marker 移除，CI 统一排除 external_network；PR/main/manual 三层全绿，Backend 约 5m，无 Node 20 警告 | [PR #472](https://github.com/MarkDanile/MetaEduBase/pull/472)（`beb7c6fd`）/ [Tech Debt](technical-debt.md#td-084-github-actions-node-24-与-hermetic-测试分类收口) |
| 2026-07-23 | TD-083 后端风险分级测试选择与性能专项治理 | 🟢 完成 | PR targeted / main full-not-slow / nightly full；默认禁外网 + 外部依赖 mock；not-slow 1365 pass/2m41s；resource 探针 15 pass/4.22s | [PR #469](https://github.com/MarkDanile/MetaEduBase/pull/469)（`cccb3ff6`）/ [Tech Debt](technical-debt.md#td-083-后端风险分级测试选择与性能专项治理) |
| 2026-07-23 | TD-082 分层质量门禁与 CI 提速 | 🟢 完成 | scope-aware CI + 秒级 hooks + MCP lock + 前端构建去重；不可靠分片已撤销，后端专项由 TD-083 接力 | [PR #467](https://github.com/MarkDanile/MetaEduBase/pull/467)（`754ca109`）/ [Tech Debt](technical-debt.md#td-082-分层质量门禁与-ci-提速) |
| 2026-07-23 | TD-081 CI、Git hooks 与 mypy 可执行基线 | 🟢 完成 | 三路 GitHub CI + fresh PostgreSQL/zhparser + fail-closed hooks + 可递减 mypy baseline；main required checks 对管理员生效。Backend 1368 pass/5 skip，三路 CI 全绿 | [PR #465](https://github.com/MarkDanile/MetaEduBase/pull/465)（`a37a7e51`）/ [Tech Debt](technical-debt.md#td-081-ci-git-hooks-与-mypy-可执行基线缺失) |
| 2026-07-22 | TD-080 后端全量测试顺序污染与 coroutine 未 await warning | 🟢 完成 | alembic fileConfig 传 disable_existing_loggers=False 治本（不再污染已存在 logger）+ 12 document asyncio.run mock 改 side_effect close coroutine + slow marker 优化 dev 循环（-m 'not slow' 6:33→~5min）。全量 0 fail；1 回归测试防回退 | [PR #464](https://github.com/MarkDanile/MetaEduBase/pull/464)（`a20f3ee1`）/ [work-log](work-log.md) |
| 2026-07-22 | REQ-058 企业背调生产级 RBAC、制审分离与多租户配置 | 🟢 完成 | DD 权限矩阵+maker-checker+任务可见性+tenant_scoped_config 表+配置审计+平台 status only。7 AC；5 Slice（#459~#463）；43 测试；全量 1364 pass/3 pre-existing；ruff 0/docs gate 0 | [PR #463](https://github.com/MarkDanile/MetaEduBase/pull/463)（`d2c3b752`）/ [work-log](work-log.md) |
| 2026-07-22 | BUG-020 上传路径/大小/类型与下载认证传输硬化 | 🟢 完成 | P0 安全：safe_display_name+containment 校验+流式分块 size 413+ext/MIME 双校验 415+storage_key 服务端生成+前端下载改 axios blob+Authorization header。6 AC；34 后端测试；全量 1322 pass/3 pre-existing；ruff 0/docs gate 0/前端 typecheck+lint 0 | [PR #457](https://github.com/MarkDanile/MetaEduBase/pull/457)（`beddaaab`）/ [work-log](work-log.md) |
| 2026-07-22 | BUG-019 MCP 凭证边界与 SSRF 硬化 | 🟢 完成 | P0 安全：CredentialRef 命名空间+黑名单+URL/IP/DNS rebinding 拒绝+set_enabled 前置校验+follow_redirects=False+mcp-server fail-fast+401 一次刷新。7 AC 全覆盖；38 后端测试+7 mcp-server 测试；全量 1290 pass/1 TD-080 pre-existing/ruff 0 | [PR #456](https://github.com/MarkDanile/MetaEduBase/pull/456)（`3eb526f1`）/ [work-log](work-log.md) |
| 2026-07-22 | BUG-018 AI App 鉴权、租户与 Token 暴露硬化 | 🟢 完成 | P0 安全：管理端点认证+RBAC+tenant-scoped+反伪造 tenant+DTO 拆 Public/Admin/Token+公开 /public+/share/{token}+前端 axios 统一。7 AC 全覆盖；31 后端测试；全量 1252 pass/2 pre-existing；ruff/docs/前端 typecheck+lint 0 | [PR #455](https://github.com/MarkDanile/MetaEduBase/pull/455)（`b084bba3`）/ [work-log](work-log.md) |
| 2026-07-22 | BUG-017 身份注册与 JWT 信任边界硬化 | 🟢 完成 | P0 安全：register 降级（extra='forbid'+强制 teacher）+管理员入口（super_admin only）+JWT 生产 fail-fast+安全日志 redact；6 AC 覆盖。新增 24 测试+6 文件迁移 0 回归；全量 1222 pass/1 TD-080 pre-existing/ruff 0 | [PR #454](https://github.com/MarkDanile/MetaEduBase/pull/454)（`400d05a7`）/ [work-log](work-log.md) |
| 2026-07-22 | REQ-046 AC-8 真实企业端到端执行体落地 | 🟢 完成 | 按授权样本企业（上汽集团）跑通真实端到端；修 internal_query 真实链路：主体→关系键映射（bill→客户ID/lease→合同ID/ticket→房间ID）+三层主体识别+confirmed_filters 通道+planner 重试+数值字符串聚合+filter 归一化+seed 补 metric。AC-8 PASSED、476 pass/ruff 0 | [PR #452](https://github.com/MarkDanile/MetaEduBase/pull/452) / [work-log](work-log.md) |
| 2026-07-22 | REQ-046 / APP-005 企业 360 背调工作台 V0 | 🟢 完成 | 首个产业园区 P0 合规风控闭环，7 小 PR（#444~#450）：任务容器+Subject Resolver+SkillRunner v2 三类 step+Internal Customer MCP+背调 SKILL+Orchestrator/Report/Evidence+第三方导入+APP-005 前端；AC-1~7 覆盖、AC-8 骨架就位。后端 1176 pass/ruff 0 | [REQ-046](../01-product-planning/05-requirements/REQ-046-enterprise-360-due-diligence-workbench.md) / [work-log](work-log.md) |
| 2026-07-21 | TD-079 排除 alembic/versions/ 出 ruff（93 pre-existing 收口） | 🟢 完成 | pyproject [tool.ruff] 加 extend-exclude=["alembic/versions"]；93 错误全在迁移文件（UP007/E501/I001/UP035/W292/F401），app/+tests/ 本就 0。ruff check . -> 0 + 显式 alembic 可查 + 全量 1064 pass/3 skip；零 .py 改动 | [Tech Debt](technical-debt.md#td-079-排除-alembicversions-出-ruff-范围93-个-pre-existing-ruff-错误收口) / [PR #442](https://github.com/MarkDanile/MetaEduBase/pull/442) |
| 2026-07-21 | TD-078 清理未使用的 ai extras（TD-077 follow-up） | 🟢 完成 | 删 pyproject 的 ai extras（6 包声明未用 + 3.14 无 wheel）+ uv lock 重生成（232->93，纯删 139/0 版本变更/0 新增）；uv sync --extra dev 成功 + --extra ai 报错 + uv tree linux/3.12 exit 0；零 .py 改动，全量 1064 pass/3 skip 基线一致 | [Tech Debt](technical-debt.md#td-078-清理未使用的-ai-extrastd-077-follow-up) / [PR #440](https://github.com/MarkDanile/MetaEduBase/pull/440) |
| 2026-07-21 | TD-077 采用 uv lockfile 保证 dev/deploy 可复现安装 | 🟢 完成 | uv.lock 提交进 git + dev.sh 4 个 pip 调用点 -> `uv sync --frozen --extra dev` + Dockerfile.backend -> `uv sync --frozen --no-dev`；ai extras 默认不装（声明未用 + 3.14 无 wheel）。全量 1064 pass/3 skip + ruff 0 | [Tech Debt](technical-debt.md#td-077-无依赖锁文件-devdeploy-不可复现安装) / [PR #438](https://github.com/MarkDanile/MetaEduBase/pull/438) |

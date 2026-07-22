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

暂无进行中任务。BUG-017 已合并归档（见最近完成），下一批候选 BUG-018 / BUG-019 见下表。

## 下一批候选任务

按"建议执行顺序"排序；候选区只保留近期 1 到 3 个入口，完整任务池回 `docs/01-product-planning/04-backlog.md` / `docs/03-engineering-governance/technical-debt.md`。

| 优先级 | 任务 | 状态 | 建议下一步 | 事实源 |
|--------|------|------|------------|--------|
| P0-2 | BUG-018 AI App 鉴权、租户与 Token 暴露 | 🔵 就绪 | BUG-017 已关闭，可启动：实施管理/public API 分离、tenant 强制和 Token DTO 收口 | [BUG-018](../01-product-planning/05-requirements/BUG-018-ai-app-auth-tenant-and-token-exposure.md) |
| P0-3 | BUG-019 MCP 凭证边界与 SSRF | 🔵 就绪 | BUG-017 已关闭，可启动：补 secret binding、目标校验和出口限制；完成前不扩 MCP | [BUG-019](../01-product-planning/05-requirements/BUG-019-mcp-credential-boundary-and-ssrf.md) |

## 最近完成

最近完成区默认最多保留 20 行（按 `docs/03-engineering-governance/01-rules/workbench.md#保留策略` 强约束）。超过 20 行时，必须一次性批量归档，只保留最新 12 行；第 13 行及以后全部移出。不得每次只移动 1 行。本表只承担"近期完成窗口"的角色，详细验证、行为变化、PR 描述和复盘见 `docs/03-engineering-governance/work-log.md`、对应技术债总账、plan 或 PR。

按"最近优先"（最新任务在最上）排序：

| 日期 | 任务 | 状态 | 摘要 | 事实源 |
|------|------|------|------|--------|
| 2026-07-22 | BUG-017 身份注册与 JWT 信任边界硬化 | 🟢 完成 | P0 安全：register 降级（extra='forbid'+强制 teacher）+管理员入口（super_admin only）+JWT 生产 fail-fast+安全日志 redact；6 AC 覆盖。新增 24 测试+6 文件迁移 0 回归；全量 1222 pass/1 TD-080 pre-existing/ruff 0 | [PR #454](https://github.com/MarkDanile/MetaEduBase/pull/454)（`400d05a7`）/ [work-log](work-log.md) |
| 2026-07-22 | REQ-046 AC-8 真实企业端到端执行体落地 | 🟢 完成 | 按授权样本企业（上汽集团）跑通真实端到端；修 internal_query 真实链路：主体→关系键映射（bill→客户ID/lease→合同ID/ticket→房间ID）+三层主体识别+confirmed_filters 通道+planner 重试+数值字符串聚合+filter 归一化+seed 补 metric。AC-8 PASSED、476 pass/ruff 0 | [PR #452](https://github.com/MarkDanile/MetaEduBase/pull/452) / [work-log](work-log.md) |
| 2026-07-22 | REQ-046 / APP-005 企业 360 背调工作台 V0 | 🟢 完成 | 首个产业园区 P0 合规风控闭环，7 小 PR（#444~#450）：任务容器+Subject Resolver+SkillRunner v2 三类 step+Internal Customer MCP+背调 SKILL+Orchestrator/Report/Evidence+第三方导入+APP-005 前端；AC-1~7 覆盖、AC-8 骨架就位。后端 1176 pass/ruff 0 | [REQ-046](../01-product-planning/05-requirements/REQ-046-enterprise-360-due-diligence-workbench.md) / [work-log](work-log.md) |
| 2026-07-21 | TD-079 排除 alembic/versions/ 出 ruff（93 pre-existing 收口） | 🟢 完成 | pyproject [tool.ruff] 加 extend-exclude=["alembic/versions"]；93 错误全在迁移文件（UP007/E501/I001/UP035/W292/F401），app/+tests/ 本就 0。ruff check . -> 0 + 显式 alembic 可查 + 全量 1064 pass/3 skip；零 .py 改动 | [Tech Debt](technical-debt.md#td-079-排除-alembicversions-出-ruff-范围93-个-pre-existing-ruff-错误收口) / [PR #442](https://github.com/MarkDanile/MetaEduBase/pull/442) |
| 2026-07-21 | TD-078 清理未使用的 ai extras（TD-077 follow-up） | 🟢 完成 | 删 pyproject 的 ai extras（6 包声明未用 + 3.14 无 wheel）+ uv lock 重生成（232->93，纯删 139/0 版本变更/0 新增）；uv sync --extra dev 成功 + --extra ai 报错 + uv tree linux/3.12 exit 0；零 .py 改动，全量 1064 pass/3 skip 基线一致 | [Tech Debt](technical-debt.md#td-078-清理未使用的-ai-extrastd-077-follow-up) / [PR #440](https://github.com/MarkDanile/MetaEduBase/pull/440) |
| 2026-07-21 | TD-077 采用 uv lockfile 保证 dev/deploy 可复现安装 | 🟢 完成 | uv.lock 提交进 git + dev.sh 4 个 pip 调用点 -> `uv sync --frozen --extra dev` + Dockerfile.backend -> `uv sync --frozen --no-dev`；ai extras 默认不装（声明未用 + 3.14 无 wheel）。全量 1064 pass/3 skip + ruff 0 | [Tech Debt](technical-debt.md#td-077-无依赖锁文件-devdeploy-不可复现安装) / [PR #438](https://github.com/MarkDanile/MetaEduBase/pull/438) |
| 2026-07-21 | TD-076 全量套件 pre-existing 失败 + ruff 归零 | 🟢 完成 | 修 template_selector 字面 \n 归一化(+回归单测)+cascade upload 补 catalog_id/entity_type+e2e mock **_kwargs+ruff 26->0；全量 1064 pass/3 skip + ruff 0 | [Tech Debt](technical-debt.md#td-076-全量测试套件-pre-existing-失败与-ruff-错误req-045-收尾-baseline-漂移) / [PR #436](https://github.com/MarkDanile/MetaEduBase/pull/436) |
| 2026-07-21 | REQ-045 Skill 注册、管理与调用能力 | 🟢 完成 | 最小 Skill registry（声明式 SOP 模板 + SkillRunner 平台编排：经 REQ-044 MCP 工具收集事实 + LLM 合成结构化产物）+ 首个真实 Skill=企业 360 背调 SOP；AC-9 真实 QCC+LLM 端到端验收通过（凭证/企业敏感原文不泄漏）。218 范围 tests pass / ruff 0 | [REQ-045](../01-product-planning/05-requirements/REQ-045-skill-registry-and-execution.md) |
| 2026-07-21 | DOC-079 门禁脚本修复（req-status-consistency） | 🟢 完成 | req-status-consistency 解析「当前进行中」散文式任务卡片 + priority 格 REQ 引用被当任务 id、状态格 fail-closed 两处叠加根因；新增回归测试。41/41 engineering tests pass | [work-log](work-log.md) |
| 2026-07-20 | REQ-044 MCP 注册、管理与调用能力 | 🟢 完成 | 最小 tenant 级 MCP registry + 真实 streamable_http client + 调用审计 + 最小管理 UI；AC-9 真实 QCC 验收通过（凭证不泄漏）。335 backend + 6 frontend tests pass / ruff 0 | [REQ-044](../01-product-planning/05-requirements/REQ-044-mcp-registry-and-invocation.md) |
| 2026-07-20 | REQ-057 Catalog Adapter 路由与 entity_type 契约收口 | 🟢 完成 | adapter registry 3 类型路由 + MCP 抛 CapabilityUnavailableError（QueryService 捕获写审计 ok=False）+ 两 Catalog 同 entity_type 隔离测试（AC-5）+ REQ-054 AC 按真实验证层级修正 + entity_type 动态发现文档统一。226 backend tests pass / ruff 0 | [REQ-057](../01-product-planning/05-requirements/REQ-057-catalog-adapter-and-entity-contract-closure.md) |
| 2026-07-17 | TD-075 knowledge_nodes backfill 移除 OFFSET 防跳行 | 🟢 完成 | 移除 force=False OFFSET（每轮重查 WHERE embedding IS NULL LIMIT）+ BackfillResult + attempted_ids 防重复 + 单行失败不阻塞 + remaining count 非零退出。6 单测 pass | [Tech Debt](technical-debt.md#td-075-knowledge_nodes-embedding-backfill-使用-mutable-predicate--offset-导致跳行) / [PR #432](https://github.com/MarkDanile/MetaEduBase/pull/432) (`f30c1760`) |
| 2026-07-17 | DOC-077 跨事实源任务编号唯一性与历史碰撞收口 | 🟢 完成 | 重命名 BUG-011 -> BUG-016 (alias) / BUG-013 -> BUG-014 (alias)；新增 `scripts/engineering/checks/unique_task_ids.py` 同 ID 异义门禁；40/40 engineering tests pass | [Review](04-retrospectives/2026-07-15-recent-completion-code-review.md#p1-bug-编号已发生两次碰撞) / [PR #429](https://github.com/MarkDanile/MetaEduBase/pull/429) (`60045b1f`) |
| 2026-07-17 | BUG-015 QueryPanel 移除冗余 input + 查询背景改可选 | 🟢 完成 | 移除 "企业全称" 输入 + business_purpose 改 Optional + migration 020 audit_log.business_purpose nullable + entity_type 空提示含上传指引。803 backend + 16 frontend tests pass | [BUG-015](../01-product-planning/05-requirements/BUG-015-querypanel-ux-redundant-inputs.md) / [PR #430](https://github.com/MarkDanile/MetaEduBase/pull/430) (`d69684ae`) |
| 2026-07-16 | REQ-056 智能问数真实执行闭环与 AI Chat 生产接线 | 🟢 完成 | 4 Task 完成 + `tests/real_world/req056_business_samples.py` 10/10 真实业务样例绿；ImportedDataset 真实过滤、AI Chat request-bound QueryService + catalog 双键路由、审计 fail-closed 全闭环；REQ-052 重新关闭 | [REQ-056](../01-product-planning/05-requirements/REQ-056-intelligent-data-query-production-closure.md) / [REQ-052](../01-product-planning/05-requirements/REQ-052-intelligent-data-query-and-data-activation.md) |

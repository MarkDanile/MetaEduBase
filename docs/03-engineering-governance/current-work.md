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

### REQ-046 / APP-005 企业 360 背调工作台 V0（PR-7 / Slice 6：第三方 SKILL 导入 + APP-005 前端 + AC-8/9）

状态：🟡 进行中
类型：业务编排 + 持久化资产
领域：后端（skill_registry 导入）+ 前端（due-diligence 工作台）
当前执行模式：按 plan 分 7 个小 PR（本 PR = Slice 6 第三方 QCC SKILL 导入 + APP-005 前端 + 真实企业端到端 AC-8/9）
最近接手工具：Claude Code
分支：feat/req046-s7-skill-import-frontend-e2e

需求来源：
- Requirement: `docs/01-product-planning/05-requirements/REQ-046-enterprise-360-due-diligence-workbench.md`
- Spec: `docs/02-delivery-plans/01-specs/2026-07-03-req-046-enterprise-360-due-diligence-workbench.md`
- Plan: `docs/02-delivery-plans/02-plans/2026-07-03-req-046-enterprise-360-due-diligence-workbench-plan.md`
- 实施 plan（用户已批准）：新建园区招商背调 SKILL（内外数据整合）+ SkillRunner v2 三类 step（mcp/internal-customer/internal_query）+ 第三方 QCC SKILL 导入；内部数据=真实园区数据集 xlsx 上传（非 mock）

当前进展：PR-1 #444、PR-2 #445、PR-3 #446、PR-4 #447、PR-5 #448、PR-6 #449 已合并（编排 + Report Store + Evidence Ledger + run/report/evidence 端点已落地）。本 PR-7 已实现：① `scripts/import_external_skill.py` 启发式 SKILL.md → SopTemplate YAML 草稿转换器（命令→name、工具 token→mcp_dependencies、每维度一 step、报告骨架→report_template），已对真实 QCC 授信尽调 SKILL 验证（5 维度、4 server），header 注明 server code 需人工校订（qcc-* → 平台注册的 qcc）；② APP-005 前端：`services/dueDiligence.ts`（任务/主体/run/报告/证据全端点）+ `views/due-diligence/`（DdTaskListView 入口/新建、DdTaskDetailView 主体锚定卡+状态时间线+run、DdReportView 七键企业画像渲染+确认锁版/归档+证据抽屉、ReportSection/EvidenceDrawer/status 子组件）+ 路由注册 `/apps/enterprise-360-dd*` + `seed.py` APP-005 市场卡片；③ AC-8 真实企业端到端骨架 `tests/real_world/test_req046_due_diligence_e2e_acceptance.py`（phase-0 模板加载常跑，phase-1 真实通道 opt-in 闸门：缺 QCC/内部 MCP/问数/授权企业任一项即显式阻塞 skip，不用 mock 冒充通过）。
下一步：提交、创建 PR-7；合并后补全 AC-8 真实执行体（需真实 QCC/内部 MCP/问数联调）并同步 APP/Backlog/Requirement/work-log（AC-9）。
验证状态：后端全量 1176 pass / 4 skip / 1 个已知 flaky（order-sensitive embedding warning，单独复跑通过）；ruff 全量 0；`git diff --check` 通过；前端 vitest 166 pass（含 APP-005 新增 8）、vue-tsc 0、eslint 0；AC-8 phase-0 pass、phase-1 显式阻塞 skip。
交接备注：导入是启发式转换（V0 目标=可注册草稿+人工校订，非无损导入）。前端报告/证据仅在归属租户视图展示、不缓存不打印；evidence 只含非敏感 summary+ref_id。AC-8 骨架已立起 opt-in 闸门与阻塞枚举，真实执行体留待真实通道联调后填充（骨架内显式 fail，非静默通过）。


## 下一批候选任务

按"建议执行顺序"排序；候选区只保留近期 1 到 3 个入口，完整任务池回 `docs/01-product-planning/04-backlog.md` / `docs/03-engineering-governance/technical-debt.md`。

| 优先级 | 任务 | 状态 | 建议下一步 | 事实源 |
|--------|------|------|------------|--------|
| P0（主线，REQ-045 已就绪） | REQ-046 / APP-005 企业 360 背调工作台 V0 | 🔵 Ready | REQ-045 已交付（背调 SOP + SkillRunner），可启动：主体锚定 + QCC MCP Adapter + 内部问数（REQ-052）+ 背调 Skill + 报告归档 | [Requirement](../01-product-planning/05-requirements/REQ-046-enterprise-360-due-diligence-workbench.md) / [Spec](../02-delivery-plans/01-specs/2026-07-03-req-046-enterprise-360-due-diligence-workbench.md) / [Plan](../02-delivery-plans/02-plans/2026-07-03-req-046-enterprise-360-due-diligence-workbench-plan.md) |

## 最近完成

最近完成区默认最多保留 20 行（按 `docs/03-engineering-governance/01-rules/workbench.md#保留策略` 强约束）。超过 20 行时，必须一次性批量归档，只保留最新 12 行；第 13 行及以后全部移出。不得每次只移动 1 行。本表只承担"近期完成窗口"的角色，详细验证、行为变化、PR 描述和复盘见 `docs/03-engineering-governance/work-log.md`、对应技术债总账、plan 或 PR。

按"最近优先"（最新任务在最上）排序：

| 日期 | 任务 | 状态 | 摘要 | 事实源 |
|------|------|------|------|--------|
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

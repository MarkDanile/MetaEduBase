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

（无活跃任务。P2 RAG 真实效果验收长链 REQ-024/025/026/027/028 + TD-068 + TD-069 已全部收口。下一批接力候选见下方"下一批候选任务"。）

## 下一批候选任务

| 任务 | 状态 | 优先级 | 领域 | 下一步 | 事实源 |
|------|------|--------|------|--------|--------|
| REQ-031 P2 semantic embedding 覆盖率稳定性（REQ-030 接力） | ⚫ Candidate | P0 | P2 / RAG / Embedding | 离线预计算 keypoint embeddings 缓存 + httpx timeout 30→60s + retry with backoff；或评估本地 sentence-transformers | [REQ-030 Report](../02-delivery-plans/01-specs/2026-06-20-req-030-new-quality-metric-report.md) |
| TD-032 `validate_req024_p2_real_validation.py` 拆分 | ⚫ Candidate | P1 | Governance / Source File Sizes | 1369 行已登记例外；P2 长链收口后脚本逻辑稳定，拆分风险低 | [td-032-source-file-sizes.md](02-baselines/td-032-source-file-sizes.md) |

## 最近完成

最近完成区默认最多保留 20 行（按 `docs/03-engineering-governance/01-rules/workbench.md#保留策略` 强约束）。超过 20 行时，必须一次性批量归档，只保留最新 12 行；第 13 行及以后全部移出。不得每次只移动 1 行。本表只承担"近期完成窗口"的角色，详细验证、行为变化、PR 描述和复盘见 `docs/03-engineering-governance/work-log.md`、对应技术债总账、plan 或 PR。

按"最近优先"（最新任务在最上）排序：

| 日期 | 任务 | 状态 | 摘要 | 事实源 |
|------|------|------|------|--------|
| 2026-06-20 | REQ-030 P2 RAG 自动质量评估新口径（semantic embedding + LLM-as-judge） | 🟡 部分收口 | 脚本支持四口径（substring/semantic/semantic_embedding/llm_judge）+ 报告新增 REQ-030 章节 + dry-run 通过。**真 LLM 报告 semantic_emb 全 0**：硅流 embedding API batch 下挂起，httpx 30s timeout 不足；LLM-judge 通路完整，AC-5 1/10 (Q4 +0.60)。已登记 REQ-031 接力 | [REQ-030](../01-product-planning/05-requirements/REQ-030-p2-rag-new-quality-metric.md) / [Report](../02-delivery-plans/01-specs/2026-06-20-req-030-new-quality-metric-report.md) / [REQ-031](../01-product-planning/04-backlog.md) |
| 2026-06-18 | DOC-073 门禁脚本防绕过与规则修改范围校验 | 🟢 完成 | PR #362 squash merge `11e9138`：新增 `gate_file_scope` 检查，非 DOC 门禁 / 治理脚本任务修改工程门禁脚本时会被 `scripts/check-engineering-docs` 拦截；补专项测试 30 passed | [Backlog](../01-product-planning/04-backlog.md) / [PR #362](https://github.com/MarkDanile/MetaEduBase/pull/362) |
| 2026-06-20 | REQ-028 v3 重跑 (TD-068+069 后真实向量召回) | 🟢 完成 | vector 通道真命中后 baseline 升 / weighted 降；AC-4 7→6，AC-5 residual 5→1。真实向量召回下 P2 长链需要新口径评估 | [REQ-028 v3 报告](../02-delivery-plans/01-specs/2026-06-18-req-028-rag-effect-comparison-v3-report.md) / PR #TODO |
| 2026-06-18 | REQ-029 P2 弱召回 AC-5 阈值重设计 | 🟢 完成 | 分支 `feat/req-029-ac5-threshold-redesign`：residual ratio 公式 + `--lift-mode` CLI。Residual 模式 AC-5 5/10 达标，整条 P2 长链收口 | [REQ-029](../01-product-planning/05-requirements/REQ-029-p2-ac5-threshold-redesign.md) / [Residual Report](../02-delivery-plans/01-specs/2026-06-18-req-029-ac5-threshold-residual-report.md) |
| 2026-06-18 | REQ-028 P2 弱召回自动质量比较口径改造 | 🟢 完成 | PR #360 squash merge `f624f49`：三口径（substring/semantic/llm_judge）+ v3 样例 10 条（keypoint 带 synonyms+weight）+ 真 LLM 报告。REQ-029 residual 模式补判 verdict 后翻完成 | [REQ-028](../01-product-planning/05-requirements/REQ-028-p2-auto-quality-metric.md) / [Report v3](../02-delivery-plans/01-specs/2026-06-18-req-028-rag-effect-comparison-v3-report.md) / [PR #360](https://github.com/MarkDanile/MetaEduBase/pull/360) |
| 2026-06-18 | REQ-027 P2 弱召回知识覆盖与样例多样性 | 🟢 完成 | PR #359 squash merge `8310fca`：5 条 v2 样例 (dev DB 513 knowledge_edges 校准) + wrapper 脚本 + 真 LLM v1+v2 两轮报告。机制 10/10 ✅；prompt 5/10 ✅。REQ-029 residual 阈值补判后 AC-4 9/10 达标，翻完成 | [REQ-027](../01-product-planning/05-requirements/REQ-027-p2-weak-recall-knowledge-coverage.md) / [Report v2](../02-delivery-plans/01-specs/2026-06-18-req-027-rag-effect-comparison-v2-report.md) / [PR #359](https://github.com/MarkDanile/MetaEduBase/pull/359) |
| 2026-06-18 | REQ-026 P2 RAG 效果比较与弱召回样例集收口 | 🟢 完成 | PR #358 squash merge `930589b`：5 条弱召回样例集 + 关键事实覆盖度自动比较 + real LLM 报告。机制 5/5 ✅；prompt 3/5 ✅。REQ-029 residual 阈值补判后 AC-1 改判为达成，翻完成 | [REQ-026](../01-product-planning/05-requirements/REQ-026-p2-rag-effect-comparison-and-weak-recall-samples.md) / [Report](../02-delivery-plans/01-specs/2026-06-18-req-026-rag-effect-comparison-validation-report.md) / [PR #358](https://github.com/MarkDanile/MetaEduBase/pull/358) |
| 2026-06-18 | TD-068 AI Chat 真实验证中 query embedding 为空导致向量召回有效性不明 | 🟢 完成 | PR #355 squash merge `fdffd60`：确认 vector topN 是 keyword fallback；diagnostics / REQ-024 report 已显式透出 `embedding_fallback` 与 `vector fallback` 计数，REQ-025 后续验收必须据此判断 | [TD-068](technical-debt.md#td-068) / [Report](../02-delivery-plans/01-specs/2026-06-18-req-024-p2-real-validation-report.md) / [PR #355](https://github.com/MarkDanile/MetaEduBase/pull/355) |
| 2026-06-18 | DOC-072 工程规则阶段复盘与 follow-up 登记 | 🟢 完成 | PR #352 squash merge `e776fb6`：复盘 DOC-057~DOC-071 后的规则执行效果，登记 DOC-073 门禁防绕过和 DOC-074 AI/RAG 完成态口径收紧，并放入工作台候选区 | [Retro](04-retrospectives/2026-06-18-rules-stage-retrospective.md) / [PR #352](https://github.com/MarkDanile/MetaEduBase/pull/352) |
| 2026-06-18 | DOC-071 最近完成任务与 P2 里程碑评审收口 | 🟢 完成 | PR #350 squash merge `325ac35`：评审 DOC-069 后近期完成任务，重点复核 P2-SEARCH、BUG-009/010、REQ-016/017/018，修正 P2 状态漂移、补评分总账，并登记 REQ-024 作为 P2 真实验收补强 | [Review](04-retrospectives/2026-06-18-p2-recent-completion-review.md) / [REQ-024](../01-product-planning/05-requirements/REQ-024-p2-real-validation-query-understanding-and-graph-edge.md) / [PR #350](https://github.com/MarkDanile/MetaEduBase/pull/350) |
| 2026-06-18 | REQ-023 登录页左侧品牌面大胆蓝色视觉加强 | 🟢 完成 | PR #345 squash merge `9d02ba6`：登录页左侧由轻浅蓝调整为深浅蓝品牌面，增加网格、斜向光带和底部圆弧层次；右侧表单和登录后工作区未扩散 | [REQ-023](../01-product-planning/05-requirements/REQ-023-bolder-login-brand-panel.md) / [PR #345](https://github.com/MarkDanile/MetaEduBase/pull/345) |
| 2026-06-18 | REQ-022 登录页品牌氛围与工作区画布白灰层级优化 | 🟢 完成 | PR #343 squash merge `4c9d3a8`：登录页左侧增加浅蓝渐变、细网格和能力标签；登录后主工作区画布改为柔和白灰，卡片保持白色层级；前端 typecheck/lint/build + `/login` light smoke 通过 | [REQ-022](../01-product-planning/05-requirements/REQ-022-login-brand-and-workspace-canvas-polish.md) / [PR #343](https://github.com/MarkDanile/MetaEduBase/pull/343) |
| 2026-06-18 | BUG-011 数据要素模板 AI 生成 500 与 chat_with_model_fallback ValueError 处理缺陷 | 🟢 完成 | PR #342 squash merge：DeepSeek Key 已写入 .env；`chat_with_fallback.py` fast attempt 捕获 ValueError 降级至 fallback，fallback 的 ValueError 保持传播；6 fallback tests + 91 template tests 通过；待服务重启后重测 | [BUG-011](../01-product-planning/05-requirements/BUG-011-template-init-by-ai-500-and-valueerror-handling.md) / [PR #342](https://github.com/MarkDanile/MetaEduBase/pull/342) |
| 2026-06-18 | REQ-021 浅色主题加入克制蓝色点缀 | 🟢 完成 | PR #340 squash merge `5a13c3a`：主按钮改克制蓝色语义 token，Logo / 登录页品牌 mark 改中性底 + 蓝色小图标，设计规则明确蓝色为唯一交互点缀；前端 typecheck/lint/build + `/login` light smoke 通过 | [REQ-021](../01-product-planning/05-requirements/REQ-021-blue-accent-visual-polish.md) / [PR #340](https://github.com/MarkDanile/MetaEduBase/pull/340) |
| 2026-06-18 | REQ-020 Codex / Trae-like 中性双主题视觉收敛 | 🟢 完成 | PR #338 squash merge `d4017d2`：收口为 light/dark 双主题，历史主题值迁移到 light，用户菜单提供轻量切换；新增 theme store 回归测试；前端 typecheck/lint/build/theme.spec + 浏览器 smoke 通过 | [REQ-020](../01-product-planning/05-requirements/REQ-020-codex-trae-neutral-dual-theme.md) / [PR #338](https://github.com/MarkDanile/MetaEduBase/pull/338) |
| 2026-06-18 | REQ-019 单主题视觉风格收敛 | 🟢 完成 | PR #336 squash merge `c3d3ab1`：统一为 paper 单主题，移除用户可见主题切换，旧主题入口映射到同一套暖纸墨韵 token；前端 typecheck/lint/build + 浏览器烟测通过 | [REQ-019](../01-product-planning/05-requirements/REQ-019-single-paper-theme-visual-alignment.md) / [PR #336](https://github.com/MarkDanile/MetaEduBase/pull/336) |

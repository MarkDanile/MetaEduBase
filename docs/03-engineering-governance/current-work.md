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

当前无活跃任务。

## 下一批候选任务

| 任务 | 状态 | 优先级 | 领域 | 下一步 | 事实源 |
|------|------|--------|------|--------|--------|
| AC-4 wall-clock 超时 follow-up | 🟢 已关闭 | P3 | P2 / RAG / Verification | 2026-06-22 子集验证实测 132 run 29.6min（仅传 `--req028-samples` 仍触发多 group）。按比例 60 run 推算 15-20min。AC-4 ≤10min 目标不可达，spirit 解释被推翻。接力 follow-up：离线批量 keypoint 预计算 / runner.py 接 batch helper / 提 provider 限流 | [AC-4 子集验证报告](../02-delivery-plans/01-specs/2026-06-22-td-071-ac4-subset-validation-report.md) |

## 最近完成

最近完成区默认最多保留 20 行（按 `docs/03-engineering-governance/01-rules/workbench.md#保留策略` 强约束）。超过 20 行时，必须一次性批量归档，只保留最新 12 行；第 13 行及以后全部移出。不得每次只移动 1 行。本表只承担"近期完成窗口"的角色，详细验证、行为变化、PR 描述和复盘见 `docs/03-engineering-governance/work-log.md`、对应技术债总账、plan 或 PR。

按"最近优先"（最新任务在最上）排序：

| 日期 | 任务 | 状态 | 摘要 | 事实源 |
|------|------|------|------|--------|
| 2026-06-30 | AC-4 verify dry-run smoke（TD-072 + TD-073 接力后） | 🟡 已登记 follow-up | PG 5432 不可达故走 dry-run + mock batch embedder。Run 1 miss=14, Run 2 hit=14 / 0 miss / 0.42× wall-clock。cache-key 失效（mtime mutate）✅。14 entries 落盘 3394 bytes。AC-4 ≤10min 真 LLM 实证登记 follow-up（需 PG + provider key） | [AC-4 verify 报告](../02-delivery-plans/01-specs/2026-06-30-ac4-verify-td073-dry-run-smoke-report.md) / [PR #404](https://github.com/MarkDanile/MetaEduBase/pull/404) (`aad3ad2`) |
| 2026-06-30 | TD-073 离线批量 keypoint embedding 预计算落盘（实施） | 🟢 完成 | cache_store.py + coverage 启动/退出 hook + miss 累加 + main.py CLI。15+9 新单测；pytest 50/38 passed / ruff 0 / diff clean。180 texts × 25-30s × 162 run = 75-90min → 0。AC-4 重定义 ≤15min（叠加 TD-072 ≤10min 实证待 verify） | [TD-073 plan](../02-delivery-plans/02-plans/2026-06-30-td-073-offline-keypoint-embedding-plan.md) / [PR #402](https://github.com/MarkDanile/MetaEduBase/pull/402) (`0676bb0`) |
| 2026-06-30 | TD-074 `_is_batch_embedding_callable` + batch routing 单测补强 | 🟢 完成 | 26 tests / 4 test class。覆盖 None/builtin/lambda/单条/list/Sequence/Iterable/bare list/多 POKW；路由：batch/per-text/dedup/cache hit/超时降级/错长度降级。pytest 26 + 38 passed 无回归 / ruff 0 / diff clean | [PR #400](https://github.com/MarkDanile/MetaEduBase/pull/400) (`e09ed35`) |
| 2026-06-30 | TD-073 离线批量 keypoint embedding 预计算 spec | 🟢 Done | docs-only：spec + 总账登记 + 候选区更新。落盘 cache 消除 keypoint 路径全部 HTTP；180 unique texts × 25-30s × 162 run = 75-90min → 0。AC-4 重新定义 ≤15min（叠加 TD-072 ≤10min）。全门禁 0 | [TD-073 spec](../02-delivery-plans/01-specs/2026-06-30-td-073-offline-keypoint-embedding.md) / [PR #398](https://github.com/MarkDanile/MetaEduBase/pull/398) (`520bc4a`) |
| 2026-06-30 | DOC-076 current-work 最近完成批量归档 18→12 | 🟢 Done | 按 workbench 保留策略：18 数据行 → 12（裁 REQ-035/034/033/032/031/030 6 行）；6 项索引均在 work-log 保留；未改门禁 / KNOWN_ISSUES。`check-engineering-docs` 退出码 0 / 38 passed / diff clean | [PR #397](https://github.com/MarkDanile/MetaEduBase/pull/397) (`e321cbd`) |
| 2026-06-24 | DOC-075 current-work「当前进行中」段落污染硬门禁 | 🟢 Done | `check_current_work` 加 `current-work-in-progress-pollution` 门禁：无活跃任务时该区只允许单句，>1 行阻塞 PR。`pytest tests/engineering/ -q` → 38 passed 退出码 0；`ruff` 0 | [PR #394](https://github.com/MarkDanile/MetaEduBase/pull/394) (`d75c966`) |
| 2026-06-24 | BUG-012 AI Chat 证据引用/参考来源打开空白页 | 🟢 Done | 链接拼 `/resource/files/{id}` 但路由是 `resource/:id` 无匹配 → 空白页；spec 把错误路径锁进断言。TDD 修复 `buildFileOpenUrl` base 为 `/resource/{id}` + 同步 spec。`pnpm test` 75 passed / typecheck / lint 0 | [Bug](../01-product-planning/05-requirements/BUG-012-ai-chat-evidence-link-blank-page.md) / [PR #391](https://github.com/MarkDanile/MetaEduBase/pull/391) (`f88fc37`) |
| 2026-06-24 | BUG-011 AI Chat 偶发「网络错误」 | 🟢 Done | 根因：前端 axios 全局 timeout=30s < 后端 `_call_llm` 60s + 检索 ~10s，慢 LLM/provider 抖动触发前端先超时并误报「网络错误」。修复：chat 请求改 120s 单请求超时 + 新增 `describeChatError` 区分 超时/网络/detail。`pnpm test` 75 passed / typecheck / lint 0；curl HTTP 200 24.3s | [Bug](../01-product-planning/05-requirements/BUG-011-ai-chat-timeout-shorter-than-backend-llm.md) / [PR #388](https://github.com/MarkDanile/MetaEduBase/pull/388) (`8aa09d0`) |
| 2026-06-23 | Q7_kg_occupation_to_skill graph_edge 退化排查 | 🟢 已关闭（归因纠正） | 单问题真 LLM 隔离复现推翻 REQ-039 §3.3 归因：graph_edge@0.5 死权重（packed 逐字节不变），substring 跨场景差异及跨 run 符号翻转均来自 LLM 答案方差。非真实回归，无需修复 | [Q7 排查报告](../02-delivery-plans/01-specs/2026-06-23-q7-graph-edge-degradation-investigation-report.md) / [REQ-039 §6 follow-up #2](../02-delivery-plans/01-specs/2026-06-21-req-039-p2-graph-edge-disable-llm-verify-unblock-report.md#6-follow-up) |
| 2026-06-22 | AC-4 wall-clock 子集验证（TD-071 follow-up #1） | 🟢 已关闭 | 仅传 `--req028-samples` 实测 132 run 29.6min（spirit 解释 6.6min 被推翻）。AC-4 ≤10min 目标不可达。TD-071 实施健康（3-3.4× 加速 vs 50-60min 阻塞）。接力 3 条候选（离线批量 keypoint 预计算 / runner.py 接 batch helper / 提 provider 限流） | [AC-4 子集验证报告](../02-delivery-plans/01-specs/2026-06-22-td-071-ac4-subset-validation-report.md) |
| 2026-06-21 | REQ-002 模板化结构抽取配置与复用体验 closeout | 🟢 Done | 4 子任务全收口：REQ-002-3 溯源（PR #153）+ REQ-002-1 配置效率（PR #158）+ TD-041 嵌套拖拽（PR #161）+ REQ-002-2 复用机制（PR #159）+ TD-042 PG 集成测试（PR #159/#122）+ REQ-002-4 可维护性（PR #170）。requirement Status 🔵 Ready → 🟢 Done，docs-only 内务登记 | [Requirement](../01-product-planning/05-requirements/REQ-002-template-config-and-reuse.md) |

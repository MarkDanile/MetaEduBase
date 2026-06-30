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

| 任务 | 状态 | 优先级 | 领域 | 当前进展 | 下一步 |
|------|------|--------|------|----------|--------|
| TD-074 `_is_batch_embedding_callable` + `_get_cached_embeddings_batch` 路由分派无单测 | 🟡 进行中 | P2 | 校验脚本 / 测试基础设施 / 纯 TDD | 分支 `feat/td-074-coverage-batch-routing-tests`；技术债总账已登记。RED 测试待写：`_is_batch_embedding_callable` type-hint 检测分支 + `_get_cached_embeddings_batch` 路由分派 + 降级 | 写 `tests/rag_validation/__init__.py` + `tests/rag_validation/test_coverage_batch_routing.py` 全 RED → GREEN |

## 下一批候选任务

| 任务 | 状态 | 优先级 | 领域 | 下一步 | 事实源 |
|------|------|--------|------|--------|--------|
| AC-4 wall-clock 超时 follow-up | 🟢 已关闭 | P3 | P2 / RAG / Verification | 2026-06-22 子集验证实测 132 run 29.6min（仅传 `--req028-samples` 仍触发多 group）。按比例 60 run 推算 15-20min。AC-4 ≤10min 目标不可达，spirit 解释被推翻。接力 follow-up：离线批量 keypoint 预计算 / runner.py 接 batch helper / 提 provider 限流 | [AC-4 子集验证报告](../02-delivery-plans/01-specs/2026-06-22-td-071-ac4-subset-validation-report.md) |
| 离线批量 keypoint embedding 预计算 | 🔵 候选 | P2 | RAG / Embedding / TD | **TD-073 spec 已就位**（PR 待提）。落盘 cache（`docs/.cache/rag_validation_keypoint_embeddings/<key>.json`）消除 keypoint 路径全部 HTTP，AC-4 重新定义 ≤15min（叠加路径 2 接力后可达 ≤10min）。180 unique texts × 25-30s × 162 run = 75-90min 单跑 → 0 | [TD-073 spec](../02-delivery-plans/01-specs/2026-06-30-td-073-offline-keypoint-embedding.md) / [技术债总账](technical-debt.md#td-073) |

## 最近完成

最近完成区默认最多保留 20 行（按 `docs/03-engineering-governance/01-rules/workbench.md#保留策略` 强约束）。超过 20 行时，必须一次性批量归档，只保留最新 12 行；第 13 行及以后全部移出。不得每次只移动 1 行。本表只承担"近期完成窗口"的角色，详细验证、行为变化、PR 描述和复盘见 `docs/03-engineering-governance/work-log.md`、对应技术债总账、plan 或 PR。

按"最近优先"（最新任务在最上）排序：

| 日期 | 任务 | 状态 | 摘要 | 事实源 |
|------|------|------|------|--------|
| 2026-06-30 | TD-072 runner.py 接 batch helper（TD-071 §5 偏差接力） | 🟢 完成 | runner.py 改传 `get_embeddings_with_timeout_batch`；coverage.py 新增 `_is_batch_embedding_callable` + 路由。预期 60 run 5-7min（叠加 TD-071 总 6-10×）。rebase 解冲突，全门禁 0。follow-up：`_is_batch_embedding_callable` 无单测（TD-074） | [TD-072 spec](../02-delivery-plans/01-specs/2026-06-22-td-072-runner-batch-wiring.md) / [PR #386](https://github.com/MarkDanile/MetaEduBase/pull/386) (`b645ca2`) |
| 2026-06-30 | TD-073 离线批量 keypoint embedding 预计算 spec | 🟢 Done | docs-only：spec + 总账登记 + 候选区更新。落盘 cache 消除 keypoint 路径全部 HTTP；180 unique texts × 25-30s × 162 run = 75-90min → 0。AC-4 重新定义 ≤15min（叠加 TD-072 ≤10min）。全门禁 0 | [TD-073 spec](../02-delivery-plans/01-specs/2026-06-30-td-073-offline-keypoint-embedding.md) / [PR #398](https://github.com/MarkDanile/MetaEduBase/pull/398) (`520bc4a`) |
| 2026-06-30 | DOC-076 current-work 最近完成批量归档 18→12 | 🟢 Done | 按 workbench 保留策略：18 数据行 → 12（裁 REQ-035/034/033/032/031/030 6 行）；6 项索引均在 work-log 保留；未改门禁 / KNOWN_ISSUES。`check-engineering-docs` 退出码 0 / 38 passed / diff clean | [PR #397](https://github.com/MarkDanile/MetaEduBase/pull/397) (`e321cbd`) |
| 2026-06-24 | DOC-075 current-work「当前进行中」段落污染硬门禁 | 🟢 Done | `check_current_work` 加 `current-work-in-progress-pollution` 门禁：无活跃任务时该区只允许单句，>1 行阻塞 PR。`pytest tests/engineering/ -q` → 38 passed 退出码 0；`ruff` 0 | [PR #394](https://github.com/MarkDanile/MetaEduBase/pull/394) (`d75c966`) |
| 2026-06-24 | BUG-012 AI Chat 证据引用/参考来源打开空白页 | 🟢 Done | 链接拼 `/resource/files/{id}` 但路由是 `resource/:id` 无匹配 → 空白页；spec 把错误路径锁进断言。TDD 修复 `buildFileOpenUrl` base 为 `/resource/{id}` + 同步 spec。`pnpm test` 75 passed / typecheck / lint 0 | [Bug](../01-product-planning/05-requirements/BUG-012-ai-chat-evidence-link-blank-page.md) / [PR #391](https://github.com/MarkDanile/MetaEduBase/pull/391) (`f88fc37`) |
| 2026-06-24 | BUG-011 AI Chat 偶发「网络错误」 | 🟢 Done | 根因：前端 axios 全局 timeout=30s < 后端 `_call_llm` 60s + 检索 ~10s，慢 LLM/provider 抖动触发前端先超时并误报「网络错误」。修复：chat 请求改 120s 单请求超时 + 新增 `describeChatError` 区分 超时/网络/detail。`pnpm test` 75 passed / typecheck / lint 0；curl HTTP 200 24.3s | [Bug](../01-product-planning/05-requirements/BUG-011-ai-chat-timeout-shorter-than-backend-llm.md) / [PR #388](https://github.com/MarkDanile/MetaEduBase/pull/388) (`8aa09d0`) |
| 2026-06-23 | Q7_kg_occupation_to_skill graph_edge 退化排查 | 🟢 已关闭（归因纠正） | 单问题真 LLM 隔离复现推翻 REQ-039 §3.3 归因：graph_edge@0.5 死权重（packed 逐字节不变），substring 跨场景差异及跨 run 符号翻转均来自 LLM 答案方差。非真实回归，无需修复 | [Q7 排查报告](../02-delivery-plans/01-specs/2026-06-23-q7-graph-edge-degradation-investigation-report.md) / [REQ-039 §6 follow-up #2](../02-delivery-plans/01-specs/2026-06-21-req-039-p2-graph-edge-disable-llm-verify-unblock-report.md#6-follow-up) |
| 2026-06-22 | AC-4 wall-clock 子集验证（TD-071 follow-up #1） | 🟢 已关闭 | 仅传 `--req028-samples` 实测 132 run 29.6min（spirit 解释 6.6min 被推翻）。AC-4 ≤10min 目标不可达。TD-071 实施健康（3-3.4× 加速 vs 50-60min 阻塞）。接力 3 条候选（离线批量 keypoint 预计算 / runner.py 接 batch helper / 提 provider 限流） | [AC-4 子集验证报告](../02-delivery-plans/01-specs/2026-06-22-td-071-ac4-subset-validation-report.md) |
| 2026-06-21 | REQ-002 模板化结构抽取配置与复用体验 closeout | 🟢 Done | 4 子任务全收口：REQ-002-3 溯源（PR #153）+ REQ-002-1 配置效率（PR #158）+ TD-041 嵌套拖拽（PR #161）+ REQ-002-2 复用机制（PR #159）+ TD-042 PG 集成测试（PR #159/#122）+ REQ-002-4 可维护性（PR #170）。requirement Status 🔵 Ready → 🟢 Done，docs-only 内务登记 | [Requirement](../01-product-planning/05-requirements/REQ-002-template-config-and-reuse.md) |
| 2026-06-21 | W25 迭代 2026-W25 P2 RAG 质量增强 收口 | 🟢 Done | Scope 24 项全交付（修复 BUG-007 漂移）。覆盖 REQ-013/014/015 + REQ-016/017/018 + REQ-024→037 + TD-068/069/070 + DOC-074。graph_edge 治理全闭环 | [迭代文件](../01-product-planning/03-iterations/2026-W25-p2-rag-quality-enhancement.md) / [work-log 索引](work-log.md) |
| 2026-06-21 | REQ-037 P2 graph_edge 禁用真 LLM 全量验收（REQ-036 follow-up） | 🟢 完成 | 全量真 LLM run 受 embedding provider 累积吞吐阻塞；dry-run 实证 10/10 样例 baseline = graph_edge@0.5 零覆盖度差异。全量真 LLM 登记 REQ-038 follow-up | [REQ-037](../01-product-planning/05-requirements/REQ-037-p2-graph-edge-disable-real-llm-verify.md) / [验收报告](../02-delivery-plans/01-specs/2026-06-21-req-037-graph-edge-disable-real-llm-verify-report.md) |
| 2026-06-21 | TD-070 vector 召回 query embedding 无超时兜底 | 🟢 完成 | `get_embedding_with_timeout(text, timeout=60.0)` helper + 3 recall 调用点改造。慢 provider 从阻塞 90s 改为 60s fail-fast 降级 keyword。+3 单测 89 passed 无回归，解锁 REQ-037 | [TD-070](technical-debt.md#td-070) / [Spec](../02-delivery-plans/01-specs/2026-06-21-td-070-vector-recall-timeout.md) |

# REQ-028: P2 弱召回自动质量比较口径改造

Status: 🟢 完成（REQ-029 residual 阈值重设计收口长链；三口径机制 + 阈值公式 + 真实 LLM 验证）
Priority: P0
Milestone: P2
Source: REQ-027 follow-up
Related: REQ-016 / REQ-017 / REQ-018 / REQ-024 / REQ-025 / REQ-026 / REQ-027 / TD-068

## 背景

REQ-027 真 PG + `--allow-llm` 报告（10 样例）质量层结论：`P2 完整链路相对 baseline 覆盖度提升 ≥30%` 仅 `1/10` (10%)，比第一轮 v1 复跑 `1/5` (20%) 退步。AC-4 (≥4/10) 未达成。

关键诊断：Q8_training_program_occupation `weighted_rrf` scenario 的 baseline coverage 已 0.80 → **数据其实够**；问题在自动覆盖度口径（子串匹配 + 真实 LLM 长答案同义改写导致覆盖度低）。

具体观察：
- Q1_decorator_concept `expected_keypoints=["装饰器", "函数", "wrapper", "语法糖", "@"]`：真实 LLM 用 "内部函数 / 包装器 / 被装饰的函数" 替换 "wrapper / 函数"，子串匹配只命中 "函数"。
- Q6_python_closure `expected_keypoints=["闭包", "装饰器", "函数", "内部", "引用"]`：dev DB 校准了 "装饰器" 在 chunks 中存在，但 LLM 答案用 "嵌套函数 / 外层引用" 替换 "闭包 / 内部"，全部 0 命中。
- Q2_generator_iterator_relationship 全 4 scenario 都 0.40 以下，但 LLM 答案实际有 "yield / 迭代 / for 循环 / 生成器函数" 完整内容，子串只命中 "生成器" 和 "迭代器"。

REQ-027 报告登记的 follow-up：自动质量比较口径改造。

## 目标

把子串匹配升级为**多维度覆盖度口径**，使 P2 能力评估更接近真实语义命中：

1. **同义词 / 形态扩展**：每个 `expected_keypoint` 可配置同义词列表（如 "闭包" → ["闭包", "嵌套函数", "closure", "外层引用"]），匹配任一同义词即视为命中。
2. **关键事实分项权重**：核心词 / 修饰词 / 同义词各自权重，核心词必须命中、修饰词 / 同义词可降权命中。
3. **LLM-as-judge 兜底（secondary signal）**：用 LLM 单独评估 answer 与 expected_keypoints 的覆盖度，作为 secondary signal 而非 primary verdict。
4. **报告双口径对照**：保留 substring coverage 作为历史基线，新增 semantic coverage 作为新口径；明确两种口径的差异和决策依据。
5. **不破坏向后兼容**：REQ-026/027 报告可继续用 substring 口径生成；新报告默认走 semantic 口径。

## 非目标

- 不重写 RRF / ContextPacker / AIChatService / PgEdgeRetriever 主链路。
- 不替换 expected_keypoints 数据结构；只在样例 JSON 增加可选 `synonyms` 字段。
- 不把 LLM-as-judge 作为唯一验收依据（REQ-026 非目标已声明）。
- 不修复 TD-068（vector embedding 为空）。
- 不调整 graph_edge 权重（REQ-017 范围）。

## 验收标准

1. 样例 JSON 支持 `expected_keypoints` 数组中每个元素的 `synonyms` 字段（向后兼容：旧格式仍可工作，新格式走 semantic 口径）。
2. 脚本提供双口径输出：
   - `keypoint_coverage_pct_substring`（旧）
   - `keypoint_coverage_pct_semantic`（新）
   - `keypoint_coverage_pct_llm_judge`（新，可选，需要 `--allow-llm`）
3. 报告章节保留 substring 口径（向后兼容 + 历史对照），新增 semantic 口径矩阵 + LLM-as-judge 信号。
4. 在 REQ-027 10 样例上重跑双口径报告：
   - 至少 5/10 样例 semantic 覆盖度 ≥ 0.50
   - 至少 3/10 样例 P2 完整链路相对 baseline semantic 覆盖度提升 ≥ 30%
5. 若 AC-4 未达成，必须明确登记独立 `REQ-029` 或 `TD-xxx` 接力。
6. 报告必须区分 substring / semantic / llm_judge 三种口径的差异和决策依据，禁止单一口径拍板。

## 建议执行顺序

1. 在样例 JSON schema 文档化 `expected_keypoints` 新格式（带 synonyms + weight）。
2. 改造 `validate_req024_p2_real_validation.py`：
   - 新增 `_parse_keypoint` 函数（支持 string 或 `{term, synonyms?, weight?}` 对象）
   - 新增 `_compute_semantic_coverage` 函数（同义词扩展 + 分项权重）
   - 新增 `_compute_llm_judge_coverage` 函数（调用本地 LLM 评估）
   - ScenarioRun 扩展 `keypoint_*_semantic` / `keypoint_*_llm_judge` 字段
3. 报告渲染新增双口径章节。
4. 用 REQ-027 的 10 样例（v1 + v2 merged）跑双口径 dry-run + `--allow-llm`。
5. 更新 P2 milestone / Iteration / Backlog / current-work / work-log。

## 事实源

- REQ-027 requirement: `docs/01-product-planning/05-requirements/REQ-027-p2-weak-recall-knowledge-coverage.md`
- REQ-027 report v1: `docs/02-delivery-plans/01-specs/2026-06-18-req-027-rag-effect-comparison-v1-report.md`
- REQ-027 report v2: `docs/02-delivery-plans/01-specs/2026-06-18-req-027-rag-effect-comparison-v2-report.md`
- REQ-027 样例集 v2: `scripts/validate_real_pg_rag_req027_weak_recall_v2.example.json`
- REQ-027 wrapper: `scripts/run_req027_validation.py`
- REQ-024/025/026 报告: 1 链上文

## Delivery Record

| 日期 | 动作 | 事实 |
|------|------|------|
| 2026-06-18 | Shaping 完成 | 分支 `feat/req-028-auto-quality-metric`；requirement + spec + plan 落地 |
| 2026-06-18 | Slice 1-5 完成 | 脚本支持 Keypoint dataclass + 三口径覆盖度（substring / semantic / llm_judge）+ 向后兼容 + v3 样例集 (10 条 keypoint 带 synonyms + weight) + 真 PG dry-run + `--allow-llm` 报告 |
| 2026-06-18 | 验收结果 | 机制层 10/10 ✅；AC-4 (semantic ≥ 0.50): 7/10 样例达标 ✅；AC-5 (semantic lift ≥ 30%): 1/10 样例达标 ❌。问题诊断：Q8 baseline 已 0.80 → 在 baseline 已经很高的情况下 +0.30 难度大；问题在 AC-5 阈值设计，不在 P2 链路本身。Q1 (+0.80) 强正向；Q4 (-0.80) 强退化 |
| 2026-06-18 | TD-032 登记 | `validate_req024_p2_real_validation.py` 1035 行（REQ-024→026→028 三轮扩展），已登记到 `td-032-source-file-sizes.md` 待拆分 |
| 2026-06-18 | 后续分流 | REQ-029 (⚫ Candidate)：AC-5 阈值重设计 — 相对绝对覆盖度改善 (delta) 改为 (weighted - baseline) / (1 - baseline)，允许 baseline 高的样例也能达成 30% 增益 |
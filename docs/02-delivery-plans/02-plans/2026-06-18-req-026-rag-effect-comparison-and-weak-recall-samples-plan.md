# REQ-026 P2 RAG 效果比较与弱召回样例集收口 — Plan

> Spec: `docs/02-delivery-plans/01-specs/2026-06-18-req-026-rag-effect-comparison-and-weak-recall-samples.md`
> Requirement: `docs/01-product-planning/05-requirements/REQ-026-p2-rag-effect-comparison-and-weak-recall-samples.md`
> Base script: `scripts/validate_req024_p2_real_validation.py`

## Scope

复用 REQ-024 脚本基础设施，新增 REQ-026 弱召回样例集、自动关键事实覆盖度比较与三层结论报告。其他代码路径（AIChatService / RRF / ContextPacker / PgEdgeRetriever）**不修改**。

## Slice 1 — 弱召回样例集 + spec/plan

**目标**：至少 5 条弱召回样例，覆盖 graph_edge 价值、Query Understanding 价值、cross-document 关联等场景。

**文件：**

- `scripts/validate_real_pg_rag_req026_weak_recall.example.json`（新建）
  - 至少 5 条 questions
  - 每条包含 `id` / `text` / `category` / `expected_category` / `expected_keypoints`（>=3 条）
  - 样例类别建议：
    1. `python_advanced_topic` — Python 高级特性（如装饰器、生成器、闭包）
    2. `cross_chapter_relationship` — Python 函数参数与返回值关联
    3. `prerequisite_knowledge` — 课程先导知识 / 跨章节前置
    4. `template_with_examples` — 模板配置 + 字段示例关联
    5. `course_design_pattern` — 教学安排 / 课程设计多文档关联
- `docs/02-delivery-plans/01-specs/2026-06-18-req-026-...md`（已产出）
- `docs/02-delivery-plans/02-plans/2026-06-18-req-026-...md`（本文件）

**验收：**

- 样例 JSON schema 合法
- 每条样例 `expected_keypoints` >= 3 且与 dev DB 已上传文件语义相关
- spec/plan 无 `TBD`

## Slice 2 — 扩展 REQ-024 脚本

**目标**：在不破坏 REQ-024 现有功能下，扩展支持 REQ-026。

**文件：**

- `scripts/validate_req024_p2_real_validation.py`（修改）

**改动：**

1. 数据结构扩展（`ScenarioRun` dataclass）：
   - `keypoint_total: int`
   - `keypoint_hit_count: int`
   - `keypoint_coverage_pct: float`
   - `keypoint_hit_list: list[str]`

2. 问题加载逻辑（`_load_questions`）：
   - 增加 group `REQ-026`
   - 解析 `expected_keypoints` 字段
   - 默认样例集路径新增 `DEFAULT_REQ026_SAMPLES`

3. 关键事实覆盖度计算（新增函数 `_compute_keypoint_coverage`）：
   - 合并 `final_answer_preview` + `document_sources` 文本
   - 子串包含匹配（case-insensitive）
   - 返回 `(hit_count, hit_list, total, pct)`

4. ScenarioRun 填充（`_run_question`）：
   - 在 return 前调用 `_compute_keypoint_coverage(run.final_answer_preview, run.document_sources_count)` 系列逻辑

5. CLI 参数（`_build_parser`）：
   - `--weak-recall-samples`（默认 `validate_real_pg_rag_req026_weak_recall.example.json`）
   - `--limit`（限制 sample 数，默认 0 = 不限制）
   - `--report-title` 默认改为 "REQ-026 P2 RAG 弱召回样例集与效果比较报告"
   - 保留 `--allow-llm` / `--out` / `--json-out` / `--tenant-id`

6. 报告渲染（`_render_report`）：
   - 新增章节「REQ-026 弱召回样例关键事实覆盖度对比」
   - 新增章节「自动比较结论（机制 / prompt / 质量）」
   - 新增章节「数据缺口与后续任务」
   - 保留 REQ-016 / REQ-018 章节不破坏

**验收：**

- `python -c "import scripts.validate_req024_p2_real_validation"` 导入不报错
- `validate_req024_p2_real_validation.py --help` 输出新参数
- 既有 REQ-024 字段全部保留（向后兼容）
- ruff 通过

## Slice 3 — 真 PG dry-run 报告

**目标**：用 dev DB 跑一次 dry-run，产出报告（`External LLM: disabled-dry-run`）。

**命令：**

```bash
cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase
python scripts/validate_req024_p2_real_validation.py \
    --weak-recall-samples scripts/validate_real_pg_rag_req026_weak_recall.example.json \
    --out docs/02-delivery-plans/01-specs/2026-06-18-req-026-rag-effect-comparison-validation-report.md \
    --json-out /tmp/req026_dry_run.json \
    --report-title "REQ-026 P2 RAG 弱召回样例集与效果比较报告 (dry-run)"
```

**验收：**

- 报告生成成功，包含三层结论章节
- dry-run 模式只验证机制与 prompt，不证明质量
- 报告末尾 JSON 摘要可读

## Slice 4 — `--allow-llm` 真实 LLM 报告（需用户授权）

**目标**：用户授权后跑真实 LLM provider。

**命令：**

```bash
python scripts/validate_req024_p2_real_validation.py \
    --weak-recall-samples scripts/validate_real_pg_rag_req026_weak_recall.example.json \
    --out docs/02-delivery-plans/01-specs/2026-06-18-req-026-rag-effect-comparison-validation-report.md \
    --json-out /tmp/req026_real_llm.json \
    --report-title "REQ-026 P2 RAG 弱召回样例集与效果比较报告 (real LLM)" \
    --allow-llm
```

**验收：**

- 报告状态 `External LLM: enabled` / `Validation Status: real-llm-run`
- 至少 1 条样例 `p2_coverage - baseline_coverage >= 0.3`
- 至少 1 条样例证明 graph_edge 进入 packed 并正向贡献
- 至少 1 条样例证明 Query Understanding 对自然问法正向贡献

## Slice 5 — 文档收口 + Git 闭环

**目标**：所有事实源同步、PR 创建并合并。

**文件改动：**

- `docs/01-product-planning/05-requirements/REQ-026-...md` — Status 从 🔵 Ready -> 🟢 Done
- `docs/01-product-planning/02-milestones/02-growth-phase.md` — P2 open item 状态更新
- `docs/01-product-planning/03-iterations/2026-W25-p2-rag-quality-enhancement.md` — REQ-026 -> Done
- `docs/01-product-planning/04-backlog.md` — REQ-026 状态收口
- `docs/03-engineering-governance/current-work.md` — 候选 -> 最近完成（含分支、PR、验证摘要）
- `docs/03-engineering-governance/work-log.md` — 一行式索引

**Git 闭环：**

```bash
git add scripts/validate_req024_p2_real_validation.py \
        scripts/validate_real_pg_rag_req026_weak_recall.example.json \
        docs/02-delivery-plans/01-specs/2026-06-18-req-026-...md \
        docs/02-delivery-plans/02-plans/2026-06-18-req-026-...md \
        docs/02-delivery-plans/01-specs/2026-06-18-req-026-rag-effect-comparison-validation-report.md \
        docs/01-product-planning/05-requirements/REQ-026-...md \
        docs/01-product-planning/02-milestones/02-growth-phase.md \
        docs/01-product-planning/03-iterations/2026-W25-p2-rag-quality-enhancement.md \
        docs/01-product-planning/04-backlog.md \
        docs/03-engineering-governance/current-work.md \
        docs/03-engineering-governance/work-log.md

git commit -m "feat(rag): REQ-026 weak recall samples + automatic keypoint coverage comparison + dry-run / real LLM reports"
git push origin feat/req-026-rag-effect-comparison-weak-recall-samples
gh pr create --title "REQ-026 P2 RAG 弱召回样例集与自动质量比较口径" --body "..."
gh pr checks
gh pr merge --squash --delete-branch
```

**验收：**

- `gh pr view <PR>` state = `MERGED`
- 本地 `main` 已 fast-forward
- 工作台、最近完成、work-log、Backlog、P2 milestone、Iteration 状态一致
- `scripts/check-engineering-docs` 通过

## Files To Inspect First

- `scripts/validate_req024_p2_real_validation.py`（基线脚本）
- `scripts/validate_real_pg_rag_req016.example.json`（现有样例结构参考）
- `scripts/validate_real_pg_rag_req018.example.json`（现有样例结构参考）
- `docs/02-delivery-plans/01-specs/2026-06-18-req-024-p2-real-validation-report.md`（报告结构参考）
- `docs/02-delivery-plans/01-specs/2026-06-18-req-025-graph-edge-prompt-impact-validation-report.md`（报告结构参考）

## Required Checks

- `python -c "import importlib; importlib.import_module('scripts.validate_req024_p2_real_validation')"`
- `ruff check scripts/validate_req024_p2_real_validation.py`
- `git diff --check`
- `scripts/check-engineering-docs`
- 真 PG 验收：`python scripts/validate_req024_p2_real_validation.py ...` 退出码 0

## Documentation Closure

完成后必须同步：

- `docs/01-product-planning/05-requirements/REQ-026-...md` Status -> 🟢 Done，Delivery Record
- `docs/01-product-planning/02-milestones/02-growth-phase.md` P2 open item 状态
- `docs/01-product-planning/03-iterations/2026-W25-p2-rag-quality-enhancement.md` REQ-026 -> Done
- `docs/01-product-planning/04-backlog.md` REQ-026 状态
- `docs/03-engineering-governance/current-work.md` 候选 -> 最近完成
- `docs/03-engineering-governance/work-log.md` 一行式索引
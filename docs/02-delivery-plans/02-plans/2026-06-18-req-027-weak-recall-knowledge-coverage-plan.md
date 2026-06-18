# REQ-027 P2 弱召回知识覆盖与样例多样性 — Plan

> Spec: `docs/02-delivery-plans/01-specs/2026-06-18-req-027-weak-recall-knowledge-coverage.md`
> Requirement: `docs/01-product-planning/05-requirements/REQ-027-p2-weak-recall-knowledge-coverage.md`
> Base script: `scripts/validate_req024_p2_real_validation.py`

## Scope

复用 REQ-026 脚本 + 样例集，扩展 P2 弱召回样例多样性，跑真 PG + `--allow-llm` 第二轮报告。不修改 AIChatService / RRF / ContextPacker / PgEdgeRetriever 主链路。

## Slice 1 — REQ-027 requirement + spec + plan + 新增样例集 v2

**目标**：在 dev DB 真实内容中校准 5 条新增样例。

**文件：**

- `docs/01-product-planning/05-requirements/REQ-027-...md`（已产出）
- `docs/02-delivery-plans/01-specs/2026-06-18-req-027-weak-recall-knowledge-coverage.md`（已产出）
- `docs/02-delivery-plans/02-plans/2026-06-18-req-027-...md`（本文件）
- `scripts/validate_real_pg_rag_req027_weak_recall_v2.example.json`（新增）

**新增样例设计（≥5 条，每条 expected_keypoints 已在 dev DB 真实内容中校准）：**

| ID | category | question | expected_keypoints | 校准依据 |
|----|----------|----------|---------------------|----------|
| Q6_python_closure | python_advanced | Python 闭包与装饰器有什么区别和联系？ | 闭包、装饰器、内部函数、引用、自由变量 | dev DB `python_tutorial` file_id 358bd704... 已有"装饰器"和"返回函数"章节 |
| Q7_kg_prerequisite_chain | cross_course_prerequisite | 课程能力图谱中环境监测技术专业有哪些先导课程？ | 先导、化学、基础、生物、课程链 | dev DB `training_program` file_id 93101825... 已有"化学"、"生物"等先导关键词 |
| Q8_training_program_summary | training_program_summary | 请总结水环境监测技术专业的人才培养方案要点 | 培养目标、就业方向、课程体系、实训、毕业 | dev DB `course_standard` file_id 132a8cfd... 已有"水环境监测"教案 |
| Q9_template_nested_array | template_nested_schema | 模板配置中嵌套 array 字段如何处理？ | array、items、嵌套、字段、schema | dev DB 模板抽取文档 + 元数据 |
| Q10_cross_file_relationship | cross_file_relationship | Python 教程和课程标准中关于"函数"的内容如何对应？ | 函数、定义、参数、课程、章节 | dev DB 跨文件章节对照 |

**校准步骤：**

```bash
# 1. 抽样 dev DB 已上传文件
psql "$DATABASE_URL" -c "SELECT id, file_name, doc_type FROM files WHERE tenant_id = '00000000-0000-0000-0000-000000000001';"

# 2. 抽样 document_chunks 包含关键词
psql "$DATABASE_URL" -c "SELECT file_id, chunk_index, content FROM document_chunks WHERE content ILIKE '%闭包%' LIMIT 5;"

# 3. 抽样 knowledge_edges
psql "$DATABASE_URL" -c "SELECT source_id, target_id, relation_type FROM knowledge_edges LIMIT 10;"
```

**验收：**

- v2 样例 JSON schema 合法
- 每条样例 `expected_keypoints` 至少 1 个关键词在 dev DB 真实内容中出现（grep 校准记录）

## Slice 2 — wrapper 脚本

**目标**：串联 v1 + v2 样例，输出两轮报告。

**文件：**

- `scripts/run_req027_validation.py`（新增）

**核心逻辑：**

```python
import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "validate_req024_p2_real_validation.py"
V1_SAMPLES = REPO_ROOT / "scripts" / "validate_real_pg_rag_req026_weak_recall.example.json"
V2_SAMPLES = REPO_ROOT / "scripts" / "validate_real_pg_rag_req027_weak_recall_v2.example.json"
SPECS = REPO_ROOT / "docs" / "02-delivery-plans" / "01-specs"


def _run_round(samples_path: Path, out_path: Path, allow_llm: bool, title: str) -> int:
    cmd = [
        "python", str(SCRIPT),
        "--weak-recall-samples", str(samples_path),
        "--out", str(out_path),
        "--report-title", title,
    ]
    if allow_llm:
        cmd.append("--allow-llm")
    return subprocess.call(cmd)


def main() -> int:
    # Round 1: v1
    rc1 = _run_round(
        V1_SAMPLES,
        SPECS / "2026-06-18-req-027-rag-effect-comparison-v1-report.md",
        allow_llm=False,
        title="REQ-027 P2 RAG 弱召回样例 v1 复跑报告 (dry-run)",
    )
    # Round 2: v1 + v2 merged
    v1 = json.loads(V1_SAMPLES.read_text())
    v2 = json.loads(V2_SAMPLES.read_text())
    merged = {
        "description": "REQ-027 v1+v2 merged",
        "samples": v1.get("samples", []) + v2.get("samples", []),
        "questions": v1.get("questions", []) + v2.get("questions", []),
    }
    merged_path = Path("/tmp/req027_merged.json")
    merged_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2))
    rc2 = _run_round(
        merged_path,
        SPECS / "2026-06-18-req-027-rag-effect-comparison-v2-report.md",
        allow_llm=False,
        title="REQ-027 P2 RAG 弱召回样例 v1+v2 报告 (dry-run)",
    )
    return rc1 or rc2
```

**验收：**

- wrapper 脚本可独立运行
- 两轮报告均生成
- v1 复跑报告与 REQ-026 报告对比一致（同一组样例同配置）

## Slice 3 — 真 PG dry-run v1 + v2

**目标**：第二轮 dry-run 报告生成。

**命令：**

```bash
cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase
python scripts/run_req027_validation.py  # dry-run 模式
```

**验收：**

- v1 复跑报告 `External LLM: disabled-dry-run`，覆盖度与 REQ-026 报告一致
- v2 报告 `External LLM: disabled-dry-run`，≥10 样例

## Slice 4 — 真 PG + `--allow-llm` v1 + v2

**目标**：用户授权后跑真 LLM provider。

**命令：**

```bash
python scripts/run_req027_validation.py --allow-llm
```

**验收：**

- v1 复跑报告 `External LLM: enabled`，覆盖度与 REQ-026 报告一致
- v2 报告 `External LLM: enabled`，P2 完整链路相对 baseline 覆盖度提升 ≥30% 的样例比例 ≥ 40%
- `vector_fallback_count > 0` 的样例显式标记

## Slice 5 — 文档收口 + Git 闭环

**文件改动：**

- `docs/01-product-planning/05-requirements/REQ-027-...md` — Status: 🟣 Shaping → 🟡 Doing / 🟢 Done
- `docs/01-product-planning/02-milestones/02-growth-phase.md` — REQ-027 状态
- `docs/01-product-planning/03-iterations/2026-W25-p2-rag-quality-enhancement.md` — REQ-027 状态
- `docs/01-product-planning/04-backlog.md` — REQ-027 状态
- `docs/03-engineering-governance/current-work.md` — 候选 → 最近完成
- `docs/03-engineering-governance/work-log.md` — 一行式索引

**Git 闭环：**

```bash
git add scripts/run_req027_validation.py \
        scripts/validate_real_pg_rag_req027_weak_recall_v2.example.json \
        docs/02-delivery-plans/01-specs/2026-06-18-req-027-weak-recall-knowledge-coverage.md \
        docs/02-delivery-plans/02-plans/2026-06-18-req-027-weak-recall-knowledge-coverage-plan.md \
        docs/02-delivery-plans/01-specs/2026-06-18-req-027-rag-effect-comparison-v1-report.md \
        docs/02-delivery-plans/01-specs/2026-06-18-req-027-rag-effect-comparison-v2-report.md \
        docs/01-product-planning/05-requirements/REQ-027-...md \
        docs/01-product-planning/02-milestones/02-growth-phase.md \
        docs/01-product-planning/03-iterations/2026-W25-p2-rag-quality-enhancement.md \
        docs/01-product-planning/04-backlog.md \
        docs/03-engineering-governance/current-work.md \
        docs/03-engineering-governance/work-log.md

git commit -m "feat(rag): REQ-027 weak recall sample diversity v2 + second round real LLM report"
git push origin feat/req-027-weak-recall-knowledge-coverage
gh pr create --title "REQ-027 P2 弱召回样例多样性与第二轮 real LLM 报告" --body "..."
gh pr merge --squash --delete-branch
```

**验收：**

- `gh pr view <PR>` state = `MERGED`
- 本地 `main` 已 fast-forward
- `scripts/check-engineering-docs` 通过
- v2 报告 AC-4 达成（≥4/10 样例 P2 完整链路相对 baseline 覆盖度提升 ≥30%）

## Files To Inspect First

- `scripts/validate_req024_p2_real_validation.py`（基线脚本，已支持 REQ-026）
- `scripts/validate_real_pg_rag_req026_weak_recall.example.json`（v1 样例结构参考）
- `docs/02-delivery-plans/01-specs/2026-06-18-req-026-rag-effect-comparison-validation-report.md`（v1 报告结构参考）

## Required Checks

- `python -m py_compile scripts/run_req027_validation.py`
- `ruff check scripts/run_req027_validation.py`
- `git diff --check`
- `scripts/check-engineering-docs`
- 真 PG 验收：`python scripts/run_req027_validation.py [--allow-llm]` 退出码 0

## Documentation Closure

完成后必须同步：

- `docs/01-product-planning/05-requirements/REQ-027-...md` Status → 🟡 Doing / 🟢 Done
- `docs/01-product-planning/02-milestones/02-growth-phase.md` REQ-027 状态
- `docs/01-product-planning/03-iterations/2026-W25-p2-rag-quality-enhancement.md` REQ-027 状态
- `docs/01-product-planning/04-backlog.md` REQ-027 状态
- `docs/03-engineering-governance/current-work.md` 候选 → 最近完成
- `docs/03-engineering-governance/work-log.md` 一行式索引
# RAG Validation Samples

REQ-014 / REQ-016 / REQ-018 / REQ-024 / REQ-025 / REQ-026 / REQ-027 / REQ-028 / REQ-029 等 P2 真实 PG 验收报告用的样本数据。

## 文件分类

| 文件 | 用途 | 任务 |
|------|------|------|
| `validate_real_pg_rag_samples.example.json` | 模板样本（3 问题），用于 `validate_real_pg_rag.py backfill` | REQ-014 |
| `validate_real_pg_rag_samples.json` | 真实样本（不进 git） | REQ-014 真实 PG 验收 |
| `validate_real_pg_rag_req016.example.json` | 4 个 LLM Hybrid NER 验收问题 | REQ-016 |
| `validate_real_pg_rag_req018.example.json` | 3 个 P2-RECALL-4 验收问题 | REQ-018 |
| `validate_real_pg_rag_req026_weak_recall.example.json` | 5 条 P2 弱召回样例（v1） | REQ-026 |
| `validate_real_pg_rag_req027_weak_recall_v2.example.json` | 5 条 P2 弱召回样例（v2，dev DB 513 knowledge_edges 校准） | REQ-027 |
| `validate_real_pg_rag_req028_weak_recall_v3.example.json` | 10 条 P2 弱召回样例（v3，keypoint 带 synonyms + weight） | REQ-028 / REQ-029 |

## 使用方式

脚本通过 CLI 参数 `--samples PATH` 显式传路径。常见调用：

```bash
# REQ-014 一次性脚本
python scripts/validate_real_pg_rag.py backfill \
  --samples tests/fixtures/rag_validation_samples/validate_real_pg_rag_samples.example.json \
  --out docs/02-delivery-plans/01-specs/2026-06-16-req-014-rag-real-pg-grounding-validation-report.md

# REQ-024 真实 PG 验收（长链 REQ-024/025/026/027/028/029 共用）
python scripts/validate_req024_p2_real_validation.py \
  --req016-samples tests/fixtures/rag_validation_samples/validate_real_pg_rag_req016.example.json \
  --req018-samples tests/fixtures/rag_validation_samples/validate_real_pg_rag_req018.example.json \
  --weak-recall-samples tests/fixtures/rag_validation_samples/validate_real_pg_rag_req026_weak_recall.example.json \
  --req028-samples tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json \
  --out docs/02-delivery-plans/01-specs/2026-06-18-req-028-rag-effect-comparison-v3-report.md \
  --allow-llm
```

## 历史背景

- 2026-06-19 从 `scripts/` 迁入本目录（`chore/samples-migration-to-fixtures` PR #TODO）
- 原因：scripts/ 目录只承担"执行入口"职责，测试 / 验收样本数据放在 `tests/fixtures/` 更符合职责分离

# REQ-016 LLM 混合 NER / Query Understanding 真实 PG 验收报告

> 生成时间: 2026-06-17
> 依赖: REQ-015 PG 环境（dev DB + LLM provider）

## 环境

- DB: `***@localhost:5432/metaedu`
- Tenant: `00000000-0000-0000-0000-000000000001`
- LLM provider: `deepseek` (授权用户)

> 2026-06-18 更新：本报告原为空表占位。REQ-024 已补充真实 dev DB dry-run diagnostics，并生成
> [REQ-024 P2 真实验收补强报告](2026-06-18-req-024-p2-real-validation-report.md)。
> 该补验可证明 Query Understanding trace / retrieval / fusion / packed diagnostics 可复跑，但 dry-run 使用脚本内 fake provider，
> 不能代表真实 LLM Query Understanding 质量；真实 LLM 效果验收因外部上下文发送安全边界未执行。

## 验收目的

验证 REQ-016 Slice 1-3 在真实 PG 环境下的行为：

1. **规则命中 query**（"电子信息专业课程"）→ 不调用 LLM，method="rule"，diagnostics 有 query_understanding trace
2. **规则未命中长 query**（3 类真实问法）→ 调用 LLM，expanded_terms 进入 retrievers，diagnostics 有完整 trace
3. **expanded_terms 增强召回**：含 LLM 扩展词时，召回结果包含更多相关 chunk

## 3 类真实问法验收

### Q1 — Python 教程类（LLM 触发）

| 检查项 | 预期 | 实际 | 结果 |
|--------|------|------|------|
| query | Python 函数的参数要怎么理解最好 | | |
| method | llm | | |
| confidence | > 0.5 | | |
| expanded_terms 非空 | 是 | | |
| expanded_query 进入 retrievers | 是 | | |
| 召回结果含 parameter 相关 chunk | 是 | | |
| diagnostics.query_understanding.method | llm | | |
| diagnostics.query_understanding.trigger_reason | rule_miss_and_long_query | | |

### Q2 — 课程能力类（LLM 触发）

| 检查项 | 预期 | 实际 | 结果 |
|--------|------|------|------|
| query | 请帮我判断这份材料的教学安排是否合理 | | |
| method | llm | | |
| confidence | > 0.5 | | |
| expanded_terms 非空 | 是 | | |
| diagnostics 完整 | 是 | | |

### Q3 — 资源库类（LLM 触发）

| 检查项 | 预期 | 实际 | 结果 |
|--------|------|------|------|
| query | 请帮我查找模板配置相关的文档资料 | | |
| method | llm | | |
| confidence | > 0.5 | | |
| expanded_terms 含模板/配置相关词 | 是 | | |

### Q4 — 规则命中对照（不触发 LLM）

| 检查项 | 预期 | 实际 | 结果 |
|--------|------|------|------|
| query | 电子信息专业课程 | | |
| method | rule | | |
| trigger_reason | rule_hit | | |
| LLM 调用次数 | 0 | | |
| diagnostics.query_understanding.method | rule | | |

## 结论

| 检查项 | 结果 | 证据 |
|--------|------|------|
| 规则命中不调用 LLM | dry-run 已验证 | REQ-024 报告 Q4：`method=rule`、`trigger_reason=rule_hit` |
| 规则未命中长 query 调用 LLM | dry-run 部分验证 | REQ-024 报告 Q1/Q2/Q3：fake provider 返回 `method=llm`、`confidence=0.75` |
| expanded_terms 进入 retrievers | dry-run 部分验证 | REQ-024 报告 Q1/Q2/Q3 retrieval_topn 有变化；真实 LLM provider 未验收 |
| diagnostics 含完整 query_understanding trace | dry-run 已验证 | REQ-024 报告包含 `query_understanding` / `retrieval_topn` / `fusion_topn` / `packed_blocks` |
| expanded_query 增强召回 | 待真实 LLM 验证 | REQ-024 未开启外部 LLM；效果结论由 REQ-025 接力 |

## 运行方式

```bash
# 确保 dev DB 有已处理的样例文件（见 REQ-015 报告中的 file_id）
# 确认 .env 中有 DATABASE_URL / AI_CHAT_* / LLM_* 环境变量
# 启动后端服务

python scripts/validate_real_pg_rag.py ask \
    --samples tests/fixtures/rag_validation_samples/validate_real_pg_rag_samples.example.json \
    --out docs/02-delivery-plans/01-specs/2026-06-17-req-016-llm-hybrid-ner-validation-report.md \
    --questions Q1,Q2,Q3,Q4

# REQ-016 专属问题在 REQ-015 的问题基础上增加以下 query understanding 验证：
# - python_function_param: "Python 函数的参数要怎么理解最好"
# - course_quality: "请帮我判断这份材料的教学安排是否合理"
# - template_doc: "请帮我查找模板配置相关的文档资料"
```

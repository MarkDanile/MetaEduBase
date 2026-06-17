# BUG-010: AI Chat 自然问法未稳定命中函数参数正文 chunk

Status: 🟢 Done
Priority: P0
Milestone: P2
Source: 用户复测 AI Chat 问答 A/B 差异
Related: BUG-009 / REQ-015 / P2-NER / P2-SEARCH

## Delivery Record

| Date | What | Details |
|------|------|---------|
| 2026-06-17 | PR merged | [PR #316](https://github.com/MarkDanile/MetaEduBase/pull/316) squash merge `b753d3a`；BUG-010 状态事实源回填到 Backlog、P2 Milestone、current-work 和 work-log。 |
| 2026-06-17 | Deterministic query normalizer slice | `keyword_query.tokenize_query()` 增强弱意图词清理和函数参数术语扩展；A 问法稳定产出 `python / 函数参数 / 函数 / 参数 / 默认参数 / 可变参数 / 关键字参数 / 命名关键字参数 / 参数组合`，B 问法保留 `python / 函数 / 参数`。新增 3 条 tokenizer / ranking 回归测试，证明函数参数正文 chunk 排在泛化 Python 简介 chunk 前。 |

## Problem

用户用两种语义相近的问法询问 Python 函数参数：

- A：`帮我介绍下，Python 的关于函数参数方面的知识`
- B：`Python 中函数的参数 的介绍`

B 能正确回答默认参数、可变参数、关键字参数、命名关键字参数和参数组合；A 却只命中 Python 起源、设计哲学、优缺点等泛化证据，回答“未找到足够参考来源”。

只读排查显示，当前 deterministic keyword tokenizer 对 A 的结果为：

```text
['python', '帮我', '关于函数参数方面', '知识']
```

核心词 `函数` / `参数` / `函数参数` 没有被稳定拆出，噪声词 `帮我` / `知识` 进入召回，导致 keyword fallback 和 tsvector supplement 无法稳定命中函数参数正文 chunk。

## Scope

- 增强确定性 query normalizer，不引入 LLM。
- 清理自然问法中的弱意图词：`帮我`、`介绍下`、`关于`、`方面` 等。
- 对“函数参数”类 Python 教程术语做稳定拆分和扩展：`函数参数`、`函数`、`参数`、`默认参数`、`可变参数`、`关键字参数`、`命名关键字参数`、`参数组合`。
- 补 A/B 两种问法的回归测试，证明它们共享核心检索词。

## Non-Goals

- 不实现 LLM 混合 NER / Query Understanding。
- 不改 RRF、ContextPacker、外部 LLM 调用和前端 UI。
- 不引入 Elasticsearch / reranker。

## Acceptance

- AC-1：A 问法 tokenize 后不再包含 `帮我`、`关于函数参数方面`、`知识` 等噪声 token。
- AC-2：A / B 两种问法 tokenize 后都包含 `函数` 和 `参数`，且 A 包含 `函数参数`。
- AC-3：keyword retriever 的 lexical supplement 能让“函数参数”正文 chunk 排在只含泛化 Python 介绍的 chunk 前面。
- AC-4：相关后端聚焦测试、`scripts/check-engineering-docs` 和 `git diff --check` 通过。

## Delivery Links

- Backlog: `docs/01-product-planning/04-backlog.md`
- Current Work: `docs/03-engineering-governance/current-work.md`
- PR: <https://github.com/MarkDanile/MetaEduBase/pull/316>

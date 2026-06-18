# REQ-024 P2 真实验收补强报告

## 环境

- Generated At: `2026-06-18T17:37:10.021057+08:00`
- DB: `***@localhost:5432/metaedu`
- Tenant: `00000000-0000-0000-0000-000000000001`
- External LLM: `disabled-dry-run`
- Validation Status: `partial-dry-run-only`

## REQ-016 Query Understanding 验收

| Query | Scenario | method | confidence | expanded_terms | retrieval_topn | packed_blocks | answer preview |
|-------|----------|--------|------------|----------------|----------------|---------------|----------------|
| Q1_python_func_param | baseline_rule_no_edge | - | - | [] | {"vector": 8, "keyword": 19, "graph": 3} | 8 | DRY-RUN: external LLM disabled. This answer is not a real quality signal. prompt_chars=3688 |
| Q1_python_func_param | query_understanding | llm | 0.75 | ["Python", "函数", "参数", "默认参数", "可变参数", "关键字参数"] | {"vector": 8, "keyword": 19, "graph": 3} | 8 | DRY-RUN: external LLM disabled. This answer is not a real quality signal. prompt_chars=3601 |
| Q1_python_func_param | graph_edge | llm | 0.75 | ["Python", "函数", "参数", "默认参数", "可变参数", "关键字参数"] | {"vector": 8, "keyword": 19, "graph": 3, "graph_edge": 8} | 8 | DRY-RUN: external LLM disabled. This answer is not a real quality signal. prompt_chars=3601 |
| Q1_python_func_param | weighted_rrf | llm | 0.75 | ["Python", "函数", "参数", "默认参数", "可变参数", "关键字参数"] | {"vector": 8, "keyword": 19, "graph": 3, "graph_edge": 8} | 8 | DRY-RUN: external LLM disabled. This answer is not a real quality signal. prompt_chars=3601 |
| Q2_course_quality | baseline_rule_no_edge | - | - | [] | {} | 0 | DRY-RUN: external LLM disabled. This answer is not a real quality signal. prompt_chars=23 |
| Q2_course_quality | query_understanding | llm | 0.75 | ["教学安排", "教学质量", "教学目标", "教学评价", "课程标准"] | {"vector": 8, "keyword": 16} | 8 | DRY-RUN: external LLM disabled. This answer is not a real quality signal. prompt_chars=3096 |
| Q2_course_quality | graph_edge | llm | 0.75 | ["教学安排", "教学质量", "教学目标", "教学评价", "课程标准"] | {"vector": 8, "keyword": 16} | 8 | DRY-RUN: external LLM disabled. This answer is not a real quality signal. prompt_chars=3096 |
| Q2_course_quality | weighted_rrf | llm | 0.75 | ["教学安排", "教学质量", "教学目标", "教学评价", "课程标准"] | {"vector": 8, "keyword": 16} | 8 | DRY-RUN: external LLM disabled. This answer is not a real quality signal. prompt_chars=3096 |
| Q3_template_doc | baseline_rule_no_edge | - | - | [] | {} | 0 | DRY-RUN: external LLM disabled. This answer is not a real quality signal. prompt_chars=21 |
| Q3_template_doc | query_understanding | llm | 0.75 | ["模板", "配置", "字段", "结构化抽取", "schema"] | {"vector": 8, "keyword": 16} | 8 | DRY-RUN: external LLM disabled. This answer is not a real quality signal. prompt_chars=4432 |
| Q3_template_doc | graph_edge | llm | 0.75 | ["模板", "配置", "字段", "结构化抽取", "schema"] | {"vector": 8, "keyword": 16} | 8 | DRY-RUN: external LLM disabled. This answer is not a real quality signal. prompt_chars=4432 |
| Q3_template_doc | weighted_rrf | llm | 0.75 | ["模板", "配置", "字段", "结构化抽取", "schema"] | {"vector": 8, "keyword": 16} | 8 | DRY-RUN: external LLM disabled. This answer is not a real quality signal. prompt_chars=4432 |
| Q4_rule_hit | baseline_rule_no_edge | - | - | [] | {"graph": 3, "keyword": 3} | 5 | DRY-RUN: external LLM disabled. This answer is not a real quality signal. prompt_chars=1604 |
| Q4_rule_hit | query_understanding | rule | 1.0 | [] | {"graph": 3, "keyword": 3} | 5 | DRY-RUN: external LLM disabled. This answer is not a real quality signal. prompt_chars=1604 |
| Q4_rule_hit | graph_edge | rule | 1.0 | [] | {"graph": 3, "keyword": 3, "graph_edge": 6} | 5 | DRY-RUN: external LLM disabled. This answer is not a real quality signal. prompt_chars=1604 |
| Q4_rule_hit | weighted_rrf | rule | 1.0 | [] | {"graph": 3, "keyword": 3, "graph_edge": 6} | 5 | DRY-RUN: external LLM disabled. This answer is not a real quality signal. prompt_chars=1604 |

## REQ-018 graph_edge 补足样例分析

| Query | graph_edge topN | edge in fusion | edge in packed | edge chunks not in baseline fusion | retrieval counts |
|-------|-----------------|----------------|----------------|------------------------------------|------------------|
| Q1_prerequisite_query | 0 | 0 | 0 | 0 | {"vector": 2, "keyword": 4} |
| Q2_cross_section_relationship | 8 | 4 | 0 | 7 | {"vector": 8, "keyword": 19, "graph": 3, "graph_edge": 8} |
| Q3_keyword_only_baseline | 8 | 4 | 0 | 7 | {"vector": 8, "keyword": 19, "graph": 3, "graph_edge": 8} |

## 对比结论

- 本报告以 `External LLM: disabled-dry-run` 生成，不能作为最终真实效果验收通过证据。
- dry-run 只证明脚本、DB 链路、召回 diagnostics 和报告结构可复跑。
- dry-run 下的 Query Understanding 使用脚本内 fake provider，不代表真实 LLM 解析质量。
- graph_edge fusion-level supplement examples: `2` (只表示 graph_edge 召回的新 chunk 进入 fusion 阶段)。
- graph_edge prompt-level supplement examples: `0` (REQ-024 AC-2 的强验收应以进入 packed context / prompt 并改善最终回答为准)。
- 结论：graph_edge 已能补足 fusion 候选，但尚未证明进入最终 prompt；需要登记后续数据 / 权重 / context packer 任务。

## 原始 JSON 摘要

```json
[{"question_group": "REQ-016", "question_id": "Q1_python_func_param", "question_text": "Python 函数的参数要怎么理解最好", "scenario": "baseline_rule_no_edge", "query_understanding": null, "retrieval_counts": {"vector": 8, "keyword": 19, "graph": 3}, "fusion_topn": [{"index": 1, "evidence_id": "chunk:358bd704-d223-4228-8935-3a6e1b3e699f:10b2d8d3-a820-469e-9a0b-54258dcf12d6", "source_type": "chunk", "title": "函数的参数", "file_id": "358bd704-d223-4228-8935-3a6e1b3e699f", "chunk_id": "10b2d8d3-a820-469e-9a0b-54258dcf12d6", "source_chunk_id": null, "score": 0.04728, "channels": ["keyword", "vector"], "snippet": "原因解释如下：\nPython函数在定义的时候，默认参数\nL 的值就被计算出来了，即\n[] ，因为默认参数\nL 也\n是一个变量，它指向对象\n[] ，每次调用该函数，如果改变了\nL 的内容，则下次调用时，默认\n参数的内容就变了，不再是函数定义时的\n[] 了。\n特别注意\n定义默认参数要牢记一点：默认参数必须指向不变对象！\n要修改上面的例子，我们可以用\nNone 这个不变对象来实现：\ndef add_en"}, {"index": 2, "evidence_id": "chunk:358bd704-d223-4228-8935-3a6e1b3e699f:2548c972-50b5-4fc2-9d15-403db96742cb", "source_type": "chunk", "title": "安装Python", "file_id": "358bd704-d223-4228-8935-3a6e1b3e699f", "chunk_id": "2548c972-50b5-4fc2-9d15-403db96742cb", "source_chunk_id": null, "score": 0.046544, "channels": ["keyword", "vector"], "snippet": "看到提示符变为\n>>> 就表示我们已经在Python交互式环境中了，可以输入任何Python代码，\n回车后会立刻得到执行结果。\n现在，输入\nexit() 并回车，就可以退出Python交互式环境（直\n接关掉命令行窗口也可以）。\n情况二：得到一个错误：“无法将“python”项识别为 cmdlet、函数、脚本文件或可运行程序的名\n称。"}, {"index": 3, "evidence_id": "chunk:358bd704-d223-4228-8935-3a6e1b3e699f:a8ba228b-d900-40ee-8999-1baf58bece8c", "source_type": "chunk", "title": "第一个Python程序", "file_id": "358bd704-d223-4228-8935-3a6e1b3e699f", "chunk_id": "a8ba228b-d900-40ee-8999-1baf58bece8c", "source_chunk_id": null, "score": 0.045831, "channels": ["keyword", "vector"], "snippet": "Python教程\n廖雪峰\nhttps://liaoxuefeng.com/books/python/\nPage 18 / 473\n如果要让Python打印出指定的文字，可以用\nprint() 函数，然后把希望打印的文字用单引号或\n者双引号括起来，但不能混用单引号和双引号：\n>>> print('hello, world')\nhello, world\n这种用单引号或者双引号括起来的文本在程序中叫字符"}, {"index": 4, "evidence_id": "chunk:358bd704-d223-4228-8935-3a6e1b3e699f:6e802e2d-6233-4e96-a64d-cf6d876c0dd6", "source_type": "chunk", "title": "函数", "file_id": "358bd704-d223-4228-8935-3a6e1b3e699f", "chunk_id": "6e802e2d-6233-4e96-a64d-cf6d876c0dd6", "source_chunk_id": null, "score": 0.045139, "channels": ["keyword", "vector"], "snippet": "原文链接\n我们知道圆的面积计算公式为：\n当我们知道半径\nr 的值时，就可以根据公式计算出面积。\n假设我们需要计算3个不同大小的圆\n的面积：\nr1 = 12.34\nr2 = 9.08\nr3 = 73.1\ns1 = 3.14 * r1 * r1\ns2 = 3.14 * r2 * r2\ns3 = 3.14 * r3 * r3\n当代码出现有规律的重复的时候，你就需要当心了，每次写\n3.14 * x * x"}, {"index": 5, "evidence_id": "chunk:358bd704-d223-4228-8935-3a6e1b3e699f:dedccb4f-2704-45d7-a608-f37324a9762d", "source_type": "chunk", "title": "函数", "file_id": "358bd704-d223-4228-8935-3a6e1b3e699f", "chunk_id": "dedccb4f-2704-45d7-a608-f37324a9762d", "source_chunk_id": null, "score": 0.044468, "channels": ["keyword", "vector"], "snippet": "举个例子：\n计算数列的和，比如：\n1 + 2 + 3 + ... + 100 ，写起来十分不方便，于是数学家发明了求和\n符号∑，可以把\n1 + 2 + 3 + ... + 100 记作：\n这种抽象记法非常强大，因为我们看到 ∑ 就可以理解成求和，而不是还原成低级的加法运算。\n而且，这种抽象记法是可扩展的，比如：\nS = πr2\n​n\nn=1\n∑\n100\nPython教程\n廖雪峰\nhttps://l"}, {"index": 6, "evidence_id": "chunk:358bd704-d223-4228-8935-3a6e1b3e699f:d39b26e6-a1cd-485b-8768-d174bc1772f8", "source_type": "chunk", "title": "调用函数", "file_id": "358bd704-d223-4228-8935-3a6e1b3e699f", "chunk_id": "d39b26e6-a1cd-485b-8768-d174bc1772f8", "source_chunk_id": null, "score": 0.043817, "channels": ["keyword", "vector"], "snippet": "原文链接\nPython内置了很多有用的函数，我们可以直接调用。\n要调用一个函数，需要知道函数的名称和参数，比如求绝对值的函数\nabs ，只有一个参数。\n可\n以直接从Python的官方网站查看文档，也可以在交互式命令行通过\nhelp(abs) 查看\nabs 函数\n的帮助信息。"}, {"index": 7, "evidence_id": "chunk:358bd704-d223-4228-8935-3a6e1b3e699f:c52cb976-7700-4056-8d6b-8946e14c6688", "source_type": "chunk", "title": "调用函数", "file_id": "358bd704-d223-4228-8935-3a6e1b3e699f", "chunk_id": "c52cb976-7700-4056-8d6b-8946e14c6688", "source_chunk_id": null, "score": 0.043184, "channels": ["keyword", "vector"], "snippet": "调用\nabs 函数：\n>>> abs(100)\n100\n>>> abs(-20)\n20\n>>> abs(12.34)\n12.34\n调用函数的时候，如果传入的参数数量不对，会报\nTypeError 的错误，并且Python会明确地告...
```

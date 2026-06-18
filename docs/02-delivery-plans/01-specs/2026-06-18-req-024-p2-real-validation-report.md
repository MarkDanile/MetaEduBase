# REQ-024 P2 真实验收补强报告

## 环境

- Generated At: `2026-06-18T18:20:36.107886+08:00`
- DB: `***@localhost:5432/metaedu`
- Tenant: `00000000-0000-0000-0000-000000000001`
- External LLM: `disabled-dry-run`
- Validation Status: `partial-dry-run-only`

## REQ-016 Query Understanding 验收

| Query | Scenario | method | confidence | expanded_terms | retrieval_topn | vector fallback | packed_blocks | answer preview |
|-------|----------|--------|------------|----------------|----------------|-----------------|---------------|----------------|
| Q1_python_func_param | baseline_rule_no_edge | - | - | [] | {"vector": 8, "keyword": 19, "graph": 3} | 8 | 8 | DRY-RUN: external LLM disabled. This answer is not a real quality signal. prompt_chars=3688 |
| Q1_python_func_param | query_understanding | llm | 0.75 | ["Python", "函数", "参数", "默认参数", "可变参数", "关键字参数"] | {"vector": 8, "keyword": 19, "graph": 3} | 8 | 8 | DRY-RUN: external LLM disabled. This answer is not a real quality signal. prompt_chars=3601 |
| Q1_python_func_param | graph_edge | llm | 0.75 | ["Python", "函数", "参数", "默认参数", "可变参数", "关键字参数"] | {"vector": 8, "keyword": 19, "graph": 3, "graph_edge": 8} | 8 | 8 | DRY-RUN: external LLM disabled. This answer is not a real quality signal. prompt_chars=3601 |
| Q1_python_func_param | weighted_rrf | llm | 0.75 | ["Python", "函数", "参数", "默认参数", "可变参数", "关键字参数"] | {"vector": 8, "keyword": 19, "graph": 3, "graph_edge": 8} | 8 | 8 | DRY-RUN: external LLM disabled. This answer is not a real quality signal. prompt_chars=3601 |
| Q2_course_quality | baseline_rule_no_edge | - | - | [] | {} | 0 | 0 | DRY-RUN: external LLM disabled. This answer is not a real quality signal. prompt_chars=23 |
| Q2_course_quality | query_understanding | llm | 0.75 | ["教学安排", "教学质量", "教学目标", "教学评价", "课程标准"] | {"vector": 8, "keyword": 16} | 8 | 8 | DRY-RUN: external LLM disabled. This answer is not a real quality signal. prompt_chars=3096 |
| Q2_course_quality | graph_edge | llm | 0.75 | ["教学安排", "教学质量", "教学目标", "教学评价", "课程标准"] | {"vector": 8, "keyword": 16} | 8 | 8 | DRY-RUN: external LLM disabled. This answer is not a real quality signal. prompt_chars=3096 |
| Q2_course_quality | weighted_rrf | llm | 0.75 | ["教学安排", "教学质量", "教学目标", "教学评价", "课程标准"] | {"vector": 8, "keyword": 16} | 8 | 8 | DRY-RUN: external LLM disabled. This answer is not a real quality signal. prompt_chars=3096 |
| Q3_template_doc | baseline_rule_no_edge | - | - | [] | {} | 0 | 0 | DRY-RUN: external LLM disabled. This answer is not a real quality signal. prompt_chars=21 |
| Q3_template_doc | query_understanding | llm | 0.75 | ["模板", "配置", "字段", "结构化抽取", "schema"] | {"vector": 8, "keyword": 16} | 8 | 8 | DRY-RUN: external LLM disabled. This answer is not a real quality signal. prompt_chars=4432 |
| Q3_template_doc | graph_edge | llm | 0.75 | ["模板", "配置", "字段", "结构化抽取", "schema"] | {"vector": 8, "keyword": 16} | 8 | 8 | DRY-RUN: external LLM disabled. This answer is not a real quality signal. prompt_chars=4432 |
| Q3_template_doc | weighted_rrf | llm | 0.75 | ["模板", "配置", "字段", "结构化抽取", "schema"] | {"vector": 8, "keyword": 16} | 8 | 8 | DRY-RUN: external LLM disabled. This answer is not a real quality signal. prompt_chars=4432 |
| Q4_rule_hit | baseline_rule_no_edge | - | - | [] | {"graph": 3, "keyword": 3} | 0 | 5 | DRY-RUN: external LLM disabled. This answer is not a real quality signal. prompt_chars=1604 |
| Q4_rule_hit | query_understanding | rule | 1.0 | [] | {"graph": 3, "keyword": 3} | 0 | 5 | DRY-RUN: external LLM disabled. This answer is not a real quality signal. prompt_chars=1604 |
| Q4_rule_hit | graph_edge | rule | 1.0 | [] | {"graph": 3, "keyword": 3, "graph_edge": 6} | 0 | 5 | DRY-RUN: external LLM disabled. This answer is not a real quality signal. prompt_chars=1604 |
| Q4_rule_hit | weighted_rrf | rule | 1.0 | [] | {"graph": 3, "keyword": 3, "graph_edge": 6} | 0 | 5 | DRY-RUN: external LLM disabled. This answer is not a real quality signal. prompt_chars=1604 |

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
- vector fallback trace count: `152` (大于 0 表示 vector 通道结果来自 keyword fallback，不代表真实语义向量召回)。
- graph_edge fusion-level supplement examples: `2` (只表示 graph_edge 召回的新 chunk 进入 fusion 阶段)。
- graph_edge prompt-level supplement examples: `0` (REQ-024 AC-2 的强验收应以进入 packed context / prompt 并改善最终回答为准)。
- 结论：graph_edge 已能补足 fusion 候选，但尚未证明进入最终 prompt；需要登记后续数据 / 权重 / context packer 任务。

## 原始 JSON 摘要

```json
[{"question_group": "REQ-016", "question_id": "Q1_python_func_param", "question_text": "Python 函数的参数要怎么理解最好", "scenario": "baseline_rule_no_edge", "query_understanding": null, "retrieval_counts": {"vector": 8, "keyword": 19, "graph": 3}, "fusion_topn": [{"index": 1, "evidence_id": "chunk:358bd704-d223-4228-8935-3a6e1b3e699f:10b2d8d3-a820-469e-9a0b-54258dcf12d6", "source_type": "chunk", "title": "函数的参数", "file_id": "358bd704-d223-4228-8935-3a6e1b3e699f", "chunk_id": "10b2d8d3-a820-469e-9a0b-54258dcf12d6", "source_chunk_id": null, "score": 0.04728, "channels": ["keyword", "vector"], "snippet": "原因解释如下：\nPython函数在定义的时候，默认参数\nL 的值就被计算出来了，即\n[] ，因为默认参数\nL 也\n是一个变量，它指向对象\n[] ，每次调用该函数，如果改变了\nL 的内容，则下次调用时，默认\n参数的内容就变了，不再是函数定义时的\n[] 了。\n特别注意\n定义默认参数要牢记一点：默认参数必须指向不变对象！\n要修改上面的例子，我们可以用\nNone 这个不变对象来实现：\ndef add_en", "metadata": {"section_path": "21", "chunk_index": 153, "keyword_rank": 0.0, "lexical_score": 24.0, "toc_penalty": 0, "search_mode": "lexical", "embedding_fallback": true, "doc_type": "课程标准", "tags": [], "structured_data": {"sections": [{"page": 1, "path": "1", "level": 1, "title": "目录", "content": "1. 简介\n2. Python历史\n3. 安装Python\n3.1. Python解释器\n4. 第一个Python程序\n4.1. 使用文本编辑器\n4.2. 输入和输出\n5. Python基础\n5.1. 数据类型和变量\n5.2. 字符串和编码\n5.3. 使用list和tuple\n5.4. 条件判断\n5.5. 模式匹配\n5.6. 循环\n5.7. 使用dict和set\n6. 函数\n6.1. 调用函数\n6.2. 定义函数\n6.3. 函数的参数\n6.4. 递归函数\n7. 高级特性\n7.1. 切片\n7.2. 迭代\n7.3. 列表生成式\n7.4. 生成器\n7.5. 迭代器\nPython教程\n廖雪峰\nhttps://liaoxuefeng.com/books/python/\nPage 2 / 473\n8. 函数式编程\n8.1. 高阶函数\n8.1.1. map/reduce\n8.1.2. filter\n8.1.3. sorted\n8.2. 返回函数\n8.3. 匿名函数\n8.4. 装饰器\n8.5. 偏函数\n9. 模块\n9.1. 使用模块\n9.2. 安装第三方模块\n10. 面向对象编程\n10.1. 类和实例\n10.2. 访问限制\n10.3. 继承和多态\n10.4. 获取对象信息\n10.5. 实例属性和类属性\n11. 面向对象高级编程\n11.1. 使用__slots__\n11.2. 使用@property\n11.3. 多重继承\n11.4. 定制类\n11.5. 使用枚举类\n11.6. 使用元类\n12. 错误、调试和测试\n12.1. 错误处理\n12.2. 调试\n12.3. 单元测试\nPython教程\n廖雪峰\nhttps://liaoxuefeng.com/books/python/\nPage 3 / 473\n12.4. 文档测试\n13. IO编程\n13.1. 文件读写\n13.2. StringIO和BytesIO\n13.3. 操作文件和目录\n13.4. 序列化\n14. 进程和线程\n14.1. 多进程\n14.2. 多线程\n14.3. ThreadLocal\n14.4. 进程 vs. 线程\n14.5. 分布式进程\n15. 正则表达式\n16. 常用内建模块\n16.1. datetime\n16.2. collections\n16.3. argparse\n16.4. base64\n16.5. struct\n16.6. hashlib\n16.7. hmac\n16.8. itertools\n16.9. contextlib\n16.10. urllib\n16.11. XML\n16.12. HTMLParser\n16.13. venv\n17. 常用第三方模块\n17.1. Pillow\nPython教程\n廖雪峰\nhttps://liaoxuefeng.com/books/python/\nPage 4 / 473\n17.2. requests\n17.3. chardet\n17.4. psutil\n18. 图形界面\n18.1. 海龟绘图\n19. 网络编程\n19.1. TCP/IP简介\n19.2. TCP编程\n19.3. UDP编程\n20. 电子邮件\n20.1. SMTP发送邮件\n20.2. POP3收取邮件\n21. 访问数据库\n21.1. 使用SQLite\n21.2. 使用MySQL\n21.3. 使用SQLAlchemy\n22. Web开发\n22.1. HTTP协议简介\n22.2. HTML简介\n22.3. WSGI接口\n22.4. 使用Web框架\n22.5. 使用模板\n23. 异步IO\n23.1. 协程\n23.2. 使用asyncio\n23.3. 使用aiohttp\n24. FAQ\n25. 期末总结\nPython教程\n廖雪峰\nhttps://liaoxuefeng.com/books/python/\nPage 5 / 473"}, {"page": 5, "path": "2", "level": 1, "title": "简介", "content": "原文链接\n这是小白的Python新手教程，具有如下特点：\n中文，免费，零起点，完整示例，基于最新的\nPython 3版本。\nPython是一种计算机程序设计语言。你可能已经听说过很多种流行的编程语言，比如非常难学的\nC语言，非常流行的Java语言，适合初学者的Basic语言，适合网页编程的JavaScript语言等等。\n那Python是一种什么语言？\n首先，我们普及一下编程语言的基础知识。用任何编程语言来开发程序，都是为了让计算机干\n活，比如下载一个MP3，编写一个文档等等，而计算机干活的CPU只认识机器指令，所以，尽管\n不同的编程语言差异极大，最后都得“翻译”成CPU可以执行的机器指令。而不同的编程语言，干\n同一个活，编写的代码量，差距也很大。\n比如，完成同一个任务，C语言要写1000行代码，Java只需要写100行，而Python可能只要20\n行。\nPython教程\n廖雪峰\nhttps://liaoxuefeng.com/books/python/\nPage 6 / 473\n所以Python是一种相当高级的语言。\n你也许会问，代码少还不好？代码少的代价是运行速度慢，C程序运行1秒钟，Java程序可能需要\n2秒，而Python程序可能就需要10秒。\n那是不是越低级的程序越难学，越高级的程序越简单？表面上来说，是的，但是，在非常高的抽\n象计算中，高级的Python程序设计也是非常难学的，所以，高级程序语言不等于简单。\n但是，对于初学者和完成普通任务，Python语言是非常简单易用的。连Google都在大规模使用\nPython，你就不用担心学了会没用。\n用Python可以做什么？可以做日常任务，比如自动备份你的MP3；可以做网站，很多著名的网站\n包括YouTube就是Python写的；可以做网络游戏的后台，很多在线游戏的后台都是Python开发\n的。总之就是能干很多很多事啦。\nPython当然也有不能干的事情，比如写操作系统，这个只能用C语言写；写手机应用，只能用\nSwift/Objective-C（针对iPhone）和Java（针对Android）；写3D游戏，最好用C或C++。\n如果你是小白用户，满足以下条件：\n会使用电脑，但从来没写过程序；\n还记得初中数学学的方程式和一点点代数知识；\n想从编程小白变成专业的软件架构师；\n每天能抽出半个小时学习。\n不要再犹豫了，这个教程就是为你准备的！\n准备好了吗？\n评论\nPython教程\n廖雪...
```

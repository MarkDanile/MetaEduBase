# AGENTS.md

## 核心原则

**Tradeoff:** 谨慎优先于速度。对于简单任务，请自行判断。

### 1. 先想后写
**不要假设。不要隐藏困惑。呈现权衡。**

- 明确陈述假设。不确定时提问。
- 存在多种解读时全部呈现，不静默选择。
- 有更简单方案就说出来。有理由时反驳。
- 有不清楚的地方，停下来。说出困惑所在。

### 2. 极简主义
**解决问题的最少代码。不投机性扩展。**

- 不做超出请求的功能。
- 单次使用不抽象。
- 不做没被要求的"灵活性"或"可配置性"。
- 不处理不可能发生的错误场景。
- 如果写了 200 行而可以用 50 行完成，重写。

自问："高级工程师会说这过于复杂吗？"如果是，简化。

### 3. 手术式改动
**只改必须改的。只清理自己的烂摊子。**

- 不"改善"相邻代码、注释或格式。
- 不重构没坏的东西。
- 匹配现有风格，即使你会用不同方式写。
- 注意到无关的死代码时，说明它——不要删除。

当变更造成孤儿代码时：
- 移除你的变更导致不再使用的 imports/变量/函数。
- 不要移除已有的死代码，除非被要求。

检验标准：每行变更都能追溯到用户需求。

### 4. 目标驱动
**定义成功标准。循环直到验证。**

将任务转化为可验证目标：
- "添加验证" → "为无效输入写测试，然后让测试通过"
- "修复 bug" → "写一个能复现它的测试，然后让测试通过"
- "重构 X" → "确保测试前后都通过"

多步任务先简述计划：
```
1. [步骤] → 验证: [检查方式]
2. [步骤] → 验证: [检查方式]
3. [步骤] → 验证: [检查方式]
```

强成功标准让你独立循环。弱标准（"让它工作"）需要不断确认。

---

**检验原则是否有效：** diff 中不必要的变更更少，重写由于过度复杂化更少，澄清问题在错误之前而非之后出现。

## Rules Index

| File | Content |
|------|---------|
| [architecture.md](.Codex/rules/architecture.md) | Tech stack, DDD contexts, API endpoints, DB schema, core flows |
| [codingStyle.md](.Codex/rules/codingStyle.md) | Naming, formatting, design tokens, shared components |
| [testing.md](.Codex/rules/testing.md) | Fixtures, mock strategy, coverage |
| [git-workflow.md](.Codex/rules/git-workflow.md) | Branches, commits, PR flow |
| [security.md](.Codex/rules/security.md) | Auth, injection prevention, secrets |
| [dataIntegrity.md](.Codex/rules/dataIntegrity.md) | Cascade delete, orphan cleanup |
| [docs.md](.Codex/rules/docs.md) | Doc sync rules, comment conventions |
| [PRD](docs/superpowers/specs/2026-05-15-document-pipeline-design.md) | Document pipeline full spec |

# Plans — 实施计划

本目录是插件无关的实施计划目录。后续无论使用 superpower、compound-engineering-plugin、Codex、Claude Code 或其他工具，已进入交付的新任务 plan 默认放在这里；需求池和迭代排期放在 `docs/01-product-planning/*`。

## 使用规则

- plan 应链接对应 spec、任务卡片或技术债编号。
- plan 记录实施顺序、验收标准、验证方式和当前任务拆分。
- P3 Agent 平台及其他高风险任务必须包含 `AI Delivery Profile`：复杂度、风险面、主 Harness/model/effort、允许下放范围、第二评审模型、人工门禁和验证命令；初始分工参考 [Agent Platform AI Delivery Routing Matrix](../../03-engineering-governance/03-matrices/agent-platform-ai-delivery-routing.md)。
- `AI Delivery Profile` 描述编码实施责任，不得与产品运行时的 `RuntimeProfile`、`ModelGrant` 或租户模型策略混用；实际 model id 与 effort 在任务开工时回填。
- 插件生成的计划可以先作为草稿，但进入开发前必须迁移或镜像到本目录，并在 `docs/03-engineering-governance/current-work.md` 中登记为任务卡片的 `Plan`。
- 历史 `docs/90-compat-legacy/superpowers/plans/*` 保留为兼容来源；新任务不要因为使用 superpower 就默认继续放入该目录。
- 原始插件计划链接登记到任务卡片的 `插件输出` 字段，用于追溯，不作为长期计划事实源。
- 如果插件仍输出到旧 superpower 顶层目录或兼容目录，不能把该文件直接写入任务卡片的 `Plan` 字段；必须先在本目录建立规范副本。

## 文件命名

```text
YYYY-MM-DD-short-topic.md
```

示例：

```text
2026-06-04-template-contracts-plan.md
```

## AI Delivery Profile 模板

P3 Agent 平台或其他高风险任务在实施步骤前加入：

```md
## AI Delivery Profile

- Complexity: 中 / 高 / 极高
- Risk: 数据 / 安全 / 并发 / 分布式 / 前端 / 外部依赖
- Lead: Harness + model id + effort
- Delegable: 可由其他模型独立修改的文件或切片
- Independent Review: 第二 Harness + model id + effort
- Human Gate: 必须由谁确认，以及确认点
- Validation: 真实命令、故障场景和业务 Rubric
```

极高复杂度任务的 `Independent Review` 与 `Human Gate` 不得写 `N/A`。模型或 Provider 变化时更新当前任务 plan，不回写历史 PR 伪造当时执行环境。

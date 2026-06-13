# Git Workflow — Git 工作流规范

本文件只记录 Git 协作硬规则。验证矩阵见 `quality-gates.md`；本地命令见 `local-development.md`。

## 基本原则

- `main` 只读；任何仓库文件修改都必须先建任务分支。
- 一个分支服务一个清晰任务或强相关切片；一个提交表达一个原子变更。
- 用户说“按流程提交”“完整 Git 闭环”时，默认推进 commit / push / PR / merge main / clean check。
- 进入 `git add` 前必须执行 `quality-gates.md#完成门禁`。
- PR 是默认交付事实源；merge commit 只在文档已有占位或审计需要时回填。

## 开发前分支门禁

1. 运行 `git status --short --branch`。
2. 如果在 `main`，先从最新 `main` 创建语义化任务分支，再改 `current-work.md`、spec、plan、代码或测试。
3. 纯问答、只读评审、只读调研可以不切分支。
4. 如果已经在 `main` 产生改动，停止继续提交；说明情况，并用新分支承接改动后走 PR。

## 快速交付通道

1. 入口确认：读 `current-work.md` 和本文件；确认当前已在任务分支。
2. 最小验证：按范围运行必要命令。文档-only 通常为 `scripts/check-engineering-docs` + `git diff --check`。
3. 范围边界：用 `git diff --name-status` 确认无关文件、生成物、缓存或资产清理未混入。
4. 提交链路：`git add` 相关文件，Conventional Commit，push，创建 PR。
5. 合并检查：`gh pr view` + `gh pr checks`；无阻塞则 squash merge 并删除远端分支。
6. 合并后收口：同步本地 `main`，确认 `main...origin/main` 干净；清除交付占位。

中间只报告关键阶段：已提交、PR 已创建、已合并 main、最终干净。失败时再展开原因。

## 分支命名

| 前缀 | 用途 |
|------|------|
| `feature/*` | 新功能 |
| `fix/*` | Bug 修复 |
| `refactor/*` | 重构 |
| `docs/*` | 文档或工程治理 |
| `chore/*` | 工具链、依赖、仓库维护 |

AI IDE 自带分支前缀可保留；进入团队 PR 前，任务卡片必须写清当前分支。

## 提交信息

使用 Conventional Commits：

```text
type(scope): description
```

常用 `type`：`feat`、`fix`、`docs`、`refactor`、`test`、`build`、`ci`、`chore`、`revert`。
常用 `scope`：`web`、`server`、`knowledge`、`identity`、`resource`、`shared`、`deploy`、`mcp`。

## Pull Request

PR 描述至少包含：

- Summary：做了什么。
- Scope：包含和排除的范围，是否混入用户明确要求的无关清理。
- Validation：真实命令、退出结果、手动验收。
- Risks：剩余风险或未覆盖场景。
- Docs：任务状态、总账、spec/plan 是否同步。

## PR 范围边界

- 技术债、Bug 修复、重构 PR 默认只包含本任务代码、测试和必要文档状态更新。
- 无关资产删除、生成物治理、缓存清理不得混入技术债 PR；用户明确要求同 PR 时必须在 Scope 单列。
- 门禁脚本、`KNOWN_ISSUES`、忽略列表、阈值、CI 配置属于“裁判”。当前任务因门禁失败时，禁止修改这些内容来让本任务通过；若认为门禁错误，停止当前任务并单独立项。
- 发现工作区有他人改动时，不暂存、不回退；只处理本任务文件并在回复中说明。

## 翻完成前硬条件

写 `🟢 完成` 前必须同时满足：

1. `gh pr view <PR> --json state` 为 `MERGED`。
2. `gh pr checks` 无阻塞；未配置 CI 时在任务卡说明。
3. 本地 `main` 已同步合并结果。
4. 工作台、总账、work-log、spec/plan 不再有 PR、完成日期、验证结果占位。

任务分支已提交或已 push 但 PR 未 merge，只能写 `🟡 进行中` 或 `🟣 待验证`。

## main 直推禁令

不论远端是否实际配置 branch protection，agent 不得 `git push origin main` 直推任何任务 commit。合规判断以本文件和 `quality-gates.md` 为准，不以 push 是否成功为准。

## 违反与回退

- 误直推 main：优先 `revert` 违规 commit，再用新分支重放改动并走 PR。
- `git reset --hard` + force push 会改写已发布历史，只有用户明确批准且协作者已协调时才能使用。

## 并行分支规则

并行模式只在用户明确触发时启用。每个任务独立分支，推荐独立 worktree / clone；合并前同步最新 `main`。共享 DTO / schema / migration / 核心抽象时，先合 contract-first PR，再并行实现。

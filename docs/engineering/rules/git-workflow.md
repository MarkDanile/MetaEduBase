# Git Workflow — Git 工作流规范

本文件只记录 Git 协作流程：分支、提交、Hooks、PR 和合并。启动服务和本地运行命令见 `docs/engineering/rules/local-development.md`；验证矩阵见 `docs/engineering/rules/quality-gates.md`。

## 基本原则

- 一个分支只服务一个清晰任务或一组强相关改动。
- 一个提交只表达一个原子变更。
- 提交前必须完成与改动范围匹配的验证，并记录无法运行的原因。
- 用户要求“提交代码”“按流程提交”“走完整流程”或“合并 main”时，执行者必须在执行 git 操作前阅读本文件。
- 进入 `git add` 前，必须完成 `docs/engineering/rules/quality-gates.md#完成门禁`。
- “按流程提交代码”默认不是只创建本地 commit，而是推进完整交付链路：提交、push、PR、合并 `main`、确认合并状态。
- 如果用户只希望停在某一步，必须明确说明，例如“只提交不 push”或“只创建 PR 不合并”。
- 完整交付闭环应按快速通道执行：少量固定检查、少量阶段汇报、合并后一次性收口；不得用重复回读和冗长汇报拖慢流程。
- 最终回复不是交付事实源。合并后必须清除任务文档中的过期状态和交付占位；PR 链接优先作为交付事实源，merge commit 默认可通过 PR 查询，只有文档占位或任务总账明确要求时才回填到仓库。

## 快速交付通道

适用场景：文档-only、小型回填、低风险配置或单点修复，且用户要求“按流程提交”“走完整流程”。

执行者应按以下压缩顺序推进：

1. 入口确认：读 `docs/engineering/current-work.md` 和本文件；用 `git status --short --branch` 确认范围。
2. 最小验证：按改动范围运行最小必要命令。文档-only 通常是 `scripts/check-engineering-docs` + `git diff --check`；代码改动运行相关测试或质量门禁。
3. 范围边界：用 `git diff --name-status` 确认没有无关文件、生成物或资产清理混入。
4. 提交链路：创建任务分支，暂存相关文件，commit，push，创建 PR。
5. 合并检查：`gh pr view` + `gh pr checks`。如果可合并且没有阻塞，直接 squash merge。
6. 合并后收口：确认 `main...origin/main` 干净；清除交付占位，确认 PR 和完成状态已入账。只有文档仍有占位或明确要求记录 merge commit 时，才用最小 backfill PR 收口。

中间只需向用户报告关键阶段：`已提交`、`PR 已创建`、`已合并 main`、`最终干净`。遇到失败、权限、网络、检查未通过或冲突时再详细说明。

## 分支策略

| 分支 | 规则 | 说明 |
|------|------|------|
| `main` | **受保护** | 禁止直接推送，必须通过 PR 合入 |
| `feature/*` | 临时分支 | 功能开发完成后合并删除 |
| `fix/*` | 临时分支 | Bug 修复完成后合并删除 |
| `refactor/*` | 临时分支 | 重构完成后合并删除 |
| `docs/*` | 临时分支 | 文档或工程规范变更完成后合并删除 |

AI IDE 如果带有自己的默认分支前缀，应在任务卡片中记录当前分支；需要进入团队协作或 PR 时，再按上表归入语义化分支。

## 分支命名

```text
feature/xxx-description
fix/xxx-description
refactor/xxx-description
docs/xxx-description
```

## 提交信息

### Conventional Commits 格式
```text
type(scope): description
```

### Type 列表
| type | 说明 |
|------|------|
| `feat` | 新功能 |
| `fix` | Bug 修复 |
| `docs` | 文档变更 |
| `style` | 代码格式（不影响功能） |
| `refactor` | 重构（非功能变更） |
| `perf` | 性能优化 |
| `test` | 测试相关 |
| `build` | 构建系统相关 |
| `ci` | CI/CD 相关 |
| `chore` | 其他杂项 |
| `revert` | 回退提交 |

### Scope 列表
| scope | 说明 |
|-------|------|
| `web` | 前端 |
| `server` | 后端 |
| `knowledge` | 知识上下文 |
| `identity` | 认证上下文 |
| `resource` | 资源上下文 |
| `deploy` | 部署 |
| `shared` | 共享代码 |
| `mcp` | MCP 服务 |

### 示例
```text
feat(knowledge): 添加知识点搜索功能
fix(auth): 修复登录超时问题
docs(readme): 更新快速开始文档
style(web): 格式化代码
refactor(server): 重构知识节点服务
```

提交信息应描述变更意图。标题写不下的背景、风险和验证结果放在提交正文或 PR 描述中。

## 提交前检查

提交前至少完成以下检查：

1. 查看工作区：`git status --short --branch`。
2. 运行验证：按 `docs/engineering/rules/quality-gates.md` 选择与改动范围匹配的验证。
3. 完成门禁：执行 `docs/engineering/rules/quality-gates.md#完成门禁`。
4. 文档同步：如果 API、Schema、质量门禁、协作流程或架构边界变化，按 `docs/engineering/rules/docs.md` 同步文档。
5. 暂存范围：只暂存本任务相关文件。

如果环境依赖导致完整验证不可运行，必须在最终回复和 `docs/engineering/current-work.md` 的验证状态中记录原因。

## 完整交付闭环

当用户要求“按照流程提交代码”“走完整 Git 流程”或“合并到 main”时，执行者必须按以下阶段推进，并在最终回复中报告每个阶段的结果。

### 1. 本地提交

1. 确认当前不在 `main` 上开发。
2. 阅读本文件，并在最终回复或任务记录中说明已按本文件执行。
3. 检查 `git status --short`，确认没有无关文件、生成物或其他人的改动被混入。
4. 运行匹配范围的验证。
5. 在验证后最终同步 `docs/engineering/current-work.md` 和相关任务总账：
   - 状态不得停留在过期的 `🟡 进行中`、`🟣 待验证` 或 `验证状态：未运行`。
   - 如果任务已验证完成，写清实际验证命令、结果和当前 Git 阶段。
   - 如果仍有历史失败，写清失败摘要并绑定对应 `TD-xxx`。
6. 执行 `docs/engineering/rules/quality-gates.md#完成门禁`。
7. 只暂存本任务相关文件。
8. 按原子边界创建一个或多个 Conventional Commits。

### 2. Push 分支

1. 确认本地工作区干净。
2. 推送当前任务分支。
   ```bash
   git push -u origin <branch>
   ```
3. 如果远端拒绝推送，先说明原因，不要强推，除非用户明确批准。

### 3. 创建 PR

1. 使用当前任务标题或提交主题创建 PR。
   ```bash
   gh pr create --title "type(scope): description" --body "..."
   ```
2. PR 描述必须包含 Summary、Scope、Validation、Risks、Docs。
3. PR 链接必须写入最终回复；如果任务文档已有 PR 占位、任务卡片需要长期追踪，或对应总账明确要求记录 PR，再写入 `current-work.md` 或对应任务总账。

### 4. 合并 main

1. 合并前检查 PR 状态和远端检查结果。
   ```bash
   gh pr checks
   gh pr view --json state,mergeable,reviewDecision
   ```
2. 默认使用 Squash Merge，并删除远端任务分支。
   ```bash
   gh pr merge --squash --delete-branch
   ```
3. 如果仓库要求 Review、CI 或不同合并策略，按仓库规则执行；无法合并时记录阻塞原因。
4. 合并完成后更新本地 `main`。
   ```bash
   git fetch origin
   git checkout main
   git pull --ff-only
   ```

### 5. 合并后确认

1. 确认 PR 状态为 `MERGED`，并记录 merge commit。
2. 确认本地 `main` 已包含合并结果。
3. 如果使用 Squash Merge，源分支上的原始提交不会作为 `main` 的祖先提交；此时不能只用 `git merge-base --is-ancestor <source-commit> main` 判断是否合并，应以 PR 的 `MERGED` 状态和 merge commit 为准。
4. 清理仓库文档事实源：如果 `current-work.md`、`work-log.md`、`technical-debt.md` 或对应 plan 中存在 PR、完成日期或交付状态占位，必须立即回填或删除占位。禁止保留“以最终回复为准”“提交后更新”“待最终确认”等占位。
5. merge commit 不作为所有任务的强制仓库字段；PR 链接是默认交付事实源，merge commit 可通过 `gh pr view <PR> --json mergeCommit` 查询。只有文档已存在 merge commit 占位、任务总账明确要求记录 merge commit，或审计场景需要仓库内固定记录时，才创建最小 backfill 提交或 PR 收口。
6. 最终回复必须明确说明当前停在哪个阶段：
   - 已本地提交
   - 已 push
   - 已创建 PR
   - 已合并到 `main`
   - 因何原因未完成后续阶段

## Hooks 配置

项目包含 `.githooks/`，但本地是否启用取决于 `git config core.hooksPath`。不要假设 hooks 已生效；提交前仍应手动运行匹配范围的验证。

| Hook | 功能 |
|------|------|
| `pre-commit` | 对暂存的 `.py` 执行 `ruff check`，对 `.ts`/`.vue` 执行 `vue-tsc --noEmit` |
| `commit-msg` | 校验提交信息格式是否符合 Conventional Commits |
| `pre-push` | 拦截直接推送 main 分支 |

### 跳过 Hook（谨慎使用）
```bash
git commit --no-verify -m "message"  # 不推荐
git push --no-verify                 # 不推荐
```

## Pull Request 流程

1. 从 `main` 创建任务分支。
   ```bash
   git checkout -b feature/your-feature
   ```

2. 完成开发、验证和任务状态同步。

3. 提交变更。
   ```bash
   git add .
   git commit -m "feat(scope): description"
   ```

4. 推送并创建 PR。
   ```bash
   git push -u origin feature/your-feature
   gh pr create --title "feat(scope): description" --body "## Summary\n- ..."
   ```

5. 等待 Code Review 通过。

6. 使用 **Squash Merge** 合并到 main。

## PR 描述

PR 描述至少包含：

- Summary：本次改动做了什么。
- Scope：本 PR 包含哪些文件范围；是否排除了无关变更；若包含用户明确要求的无关资产清理，必须单独列出。
- Validation：运行了哪些验证，结果如何。
- Risks：仍有何风险或未覆盖场景。
- Docs：是否更新了相关文档或任务状态。

## PR 范围边界

- 技术债、Bug 修复和重构 PR 默认只包含本任务范围内的代码、测试和必要文档状态更新。
- 无关资产删除、mockup PNG 清理、`outputs/` 生成物治理、工具缓存清理等不应混入技术债 PR。
- 如果这些文件确实需要处理，优先拆成独立 PR；如果用户明确要求同 PR 处理，PR 描述必须在 Scope 中单独说明，并解释为什么不拆分。
- 发现工作区里已有用户改动时，不要擅自暂存或回退。只暂存本任务需要的文件，并在最终回复中说明保留了哪些未处理改动。

## 注意事项

- 保持提交原子性：一个提交只做一件事
- 提交信息要描述 **why** 而不是 **what**
- 合并前确保所有测试通过
- 合并前确保 lint/typecheck 通过

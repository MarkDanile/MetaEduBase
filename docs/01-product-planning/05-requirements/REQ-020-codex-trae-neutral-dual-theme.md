# REQ-020: Codex / Trae-like 中性双主题视觉收敛

Status: 🟢 Done
Priority: P1
Milestone: P2
Owner: Codex

## 背景

REQ-019 已把历史多主题收敛为 `paper` 单主题，但用户明确希望最终系统完全贴近 Codex app / Trae Solo 的产品风格：中性白灰 AI Workspace，并且需要配套深色主题用于夜间使用。

因此本需求不再延续“暖纸墨韵”作为主风格，而是把全局视觉收口为同一套 AI IDE 工具台语言：浅色主题对齐 Codex / Trae 的白灰工作台，深色主题保持相同信息层级和控件密度。

## 目标

- 只保留两套主题：`light` 和 `dark`。
- 浅色主题使用 Codex / Trae-like 中性白灰：白色主画布、浅灰侧栏、细边框、低阴影、极少强调色。
- 深色主题是同一风格的夜间版本：深灰背景、低对比边框、克制蓝灰强调色。
- 恢复一个轻量外观切换入口，但不恢复历史多主题列表。
- 旧 `paper` / `liquid` / `ink` / `navy` / `notion` 入口保持兼容，统一映射到浅色主题。

## 非目标

- 不复制 Codex 或 Trae 的品牌、图标、产品名称或专有布局。
- 不重做业务页面信息架构。
- 不引入营销式视觉、装饰背景或大面积品牌色。
- 不做全站组件重构，只调整主题 token、共享布局和必要控件入口。

## 验收标准

1. 新会话默认进入 `light` 主题。
2. 用户可在主布局中切换 `light` / `dark`，刷新后保留选择。
3. 旧 localStorage 值 `paper` / `liquid` / `ink` / `navy` / `notion` 不会导致样式断裂，并自动落到浅色主题。
4. 浅色主题视觉接近 Codex / Trae Solo：中性白灰、细分割线、低阴影、黑/蓝灰少量强调。
5. 深色主题与浅色主题使用同一信息层级和控件语言。
6. 前端 typecheck / lint / build 通过。

## 实施记录

- `theme` store 收敛为 `light` / `dark`，默认 `light`，历史主题值统一迁移为 `light`。
- 全局主题 token 改为中性 AI Workspace 视觉：浅色白灰、深色深灰，历史 `paper` / `liquid` / `ink` / `navy` / `notion` `data-theme` 入口只保留兼容映射。
- 主布局用户菜单增加轻量主题切换入口，只在 `light` / `dark` 之间切换。
- 登录页和共享组件去掉暖纸、墨韵、液态扫描等强风格装饰，保持低阴影、细边框和 token 化颜色。
- 新增 `packages/web/src/stores/theme.spec.ts`，锁定默认主题、历史值迁移和深色持久化。

## 验证记录

Environment: macOS 本地开发环境，前端 dev server `http://127.0.0.1:5173/login`。

| Command / Check | Result |
|-----------------|--------|
| `pnpm --filter @metaedu/web typecheck` | exit 0 |
| `pnpm --filter @metaedu/web lint` | exit 0 |
| `pnpm --filter @metaedu/web test -- src/stores/theme.spec.ts` | exit 0；3 tests / 1 file |
| `pnpm --filter @metaedu/web build` | exit 0；仍有既有 Vite large chunk warning，非本任务新增阻塞 |
| Browser smoke `http://127.0.0.1:5173/login` | 默认 `data-theme="light"`；关键 token：`--color-bg-base: #FFFFFF`、`--color-bg-warm: #F5F5F5`、`--color-border: #DADCE0`；登录卡片可见 |

## 当前状态

PR #338 已 squash merge 到 `main`，merge commit `d4017d2`。Backlog、current-work 和 work-log 已按完成态收口。

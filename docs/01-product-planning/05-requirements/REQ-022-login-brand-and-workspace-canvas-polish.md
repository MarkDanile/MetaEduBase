# REQ-022: 登录页品牌氛围与工作区画布白灰层级优化

Status: 🟢 Done
Priority: P1
Milestone: P2
Owner: Codex

## 背景

REQ-021 已把全局交互点缀统一为克制蓝色，但登录页左侧分栏过于克制，缺少入口页应有的品牌识别和视觉记忆点。同时，登录后的主内容区使用大面积纯白 `#FFFFFF`，和 Codex / Trae-like 工具台常见的柔和白灰画布存在轻微差异。

本需求将登录页和系统内页分开处理：登录页允许更丰富的蓝色品牌氛围；系统内页继续保持中性、克制、适合长期工作的白灰层级。

## 目标

- 登录页左侧分栏使用蓝色系浅渐变、细网格和轻量能力标签，恢复入口页的品牌感。
- 登录页视觉增强只限登录页，不污染登录后的工作区。
- 主工作区大面积背景从纯白调整为柔和灰白，卡片、输入框、弹窗继续保持白色。
- 设计规则明确：登录页可更品牌化，系统内页不得变成营销页或大面积彩色背景。

## 非目标

- 不改登录表单交互、鉴权逻辑或路由。
- 不重做业务页面布局。
- 不新增第三套主题。
- 不让蓝色成为系统内页大面积背景。

## 验收标准

1. 登录页左侧分栏有蓝色系浅渐变、细微纹理和轻量品牌信息，视觉比 REQ-021 更丰富。
2. 登录页右侧登录卡片仍保持简洁、可读。
3. 登录后的主内容区背景不再是纯白大画布，而是柔和白灰；卡片和输入控件仍保持白色层级。
4. 深色主题不破坏现有夜间层级。
5. `coding-style.md` 记录登录页和系统内页的视觉边界。
6. 前端 typecheck / lint / build 通过；工程文档门禁和 diff check 通过。

## 实施记录

- 浅色 `--theme-bg-base` 从纯白 `#FFFFFF` 调整为柔和白灰 `#FAFAFA`，卡片、输入框和弹窗仍保持白色。
- 新增登录页专用 token：`--login-brand-gradient`、`--login-brand-grid`、`--login-brand-orbit`、`--login-brand-pill-*`。
- 登录页左侧分栏改为浅蓝渐变 + 细网格纹理 + 品牌能力标签；右侧登录表单结构不变。
- 设计规则补充登录页与系统内页边界：登录页允许更丰富的蓝色品牌氛围，登录后工作区保持中性白灰。

## 验证记录

Environment: macOS 本地开发环境，前端 dev server `http://127.0.0.1:5173/login`。

| Command / Check | Result |
|-----------------|--------|
| `pnpm --filter @metaedu/web typecheck` | exit 0 |
| `pnpm --filter @metaedu/web lint` | exit 0 |
| `pnpm --filter @metaedu/web build` | exit 0；仍有既有 Vite large chunk warning，非本任务新增阻塞 |
| `scripts/check-engineering-docs` | exit 0；31 known issues allowlisted |
| `git diff --check` | exit 0 |
| Browser smoke `/login` light | `--color-bg-base: #FAFAFA`；登录页左侧为浅蓝渐变；能力标签数量 3；登录右侧背景 `rgb(250, 250, 250)` |

## 当前状态

已通过 [PR #343](https://github.com/MarkDanile/MetaEduBase/pull/343) squash merge 到 `main`，merge commit `4c9d3a8`。Backlog、current-work 和 work-log 已同步收口。

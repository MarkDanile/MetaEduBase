# REQ-023: 登录页左侧品牌面大胆蓝色视觉加强

Status: 🟢 Done
Priority: P1
Milestone: P2
Owner: Codex

## 背景

REQ-022 已把登录页左侧从灰白调整为浅蓝品牌氛围，但实际观感仍偏浅，缺少入口页应有的视觉记忆点。用户希望参考此前生成的登录页左侧背景呈现方式，让登录页更大胆、更有品牌识别。

## 目标

- 登录页左侧使用更饱和、更有层次的蓝色品牌背景。
- 左侧视觉可更丰富，但只限登录页；登录后的系统内页继续保持 Codex / Trae-like 中性工作台。
- 标题、Logo、能力标签在深蓝背景上保持清晰可读。
- 登录页右侧表单结构和鉴权逻辑不变。

## 非目标

- 不改登录流程、API、路由或权限。
- 不引入第三套主题或新的品牌色体系。
- 不改变登录后系统主内容区。
- 不新增大面积绿色、紫色或多色营销背景。

## 验收标准

1. 登录页左侧不再是浅灰白或轻浅蓝，而是明显的蓝色品牌面。
2. 左侧背景包含层次感，例如深浅蓝渐变、细网格、光带或抽象工作台视觉，但不影响文字可读性。
3. 品牌标题、subtitle、Logo 和能力标签在浅色 / 深色主题下都可读。
4. 登录右侧表单保持简洁，不出现大面积彩色背景。
5. 登录后系统工作区不受影响。

## 验证计划

- `pnpm --filter @metaedu/web typecheck`
- `pnpm --filter @metaedu/web lint`
- `pnpm --filter @metaedu/web build`
- 浏览器 smoke：检查 `/login` 左侧品牌面更大胆，右侧表单和登录后工作区无扩散影响。
- `scripts/check-engineering-docs`
- `git diff --check`

## 实施记录

- 浅色登录页左侧品牌 token 从浅蓝纸面调整为深浅蓝径向光 + 线性蓝色品牌面。
- 登录页左侧增加更明显的网格、斜向光带和底部圆弧层次；仍只作用于 `.brand-side`。
- 标题、subtitle、Logo 和能力标签改用登录页专用前景 token，保证深蓝背景可读。
- 登录右侧表单和登录后的系统工作区 token 未改变。

## 验证记录

Environment: macOS 本地开发环境，前端 dev server `http://localhost:3001/login`。

| Command / Check | Result |
|-----------------|--------|
| `pnpm --filter @metaedu/web typecheck` | exit 0 |
| `pnpm --filter @metaedu/web lint` | exit 0 |
| `pnpm --filter @metaedu/web build` | exit 0；仍有既有 Vite large chunk warning，非本任务新增阻塞 |
| `scripts/check-engineering-docs` | exit 0；31 known issues allowlisted |
| `git diff --check` | exit 0 |
| Browser smoke `/login` light | 左侧为明显蓝色品牌面；`brand-side` 宽 576、高 720；标题白色、subtitle 浅蓝白、能力标签半透明；右侧登录区背景 `rgb(250, 250, 250)` |

## 当前状态

已通过 [PR #345](https://github.com/MarkDanile/MetaEduBase/pull/345) squash merge 到 `main`，merge commit `9d02ba6`。Backlog、current-work 和 work-log 已同步收口。

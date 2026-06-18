# REQ-021: 浅色主题加入克制蓝色点缀

Status: 🟡 Doing
Priority: P1
Milestone: P2
Owner: Codex

## 背景

REQ-020 已把系统视觉收口为 Codex / Trae-like 的 `light` / `dark` 中性 AI Workspace 风格，但浅色主题仍存在黑色主按钮和黑色实心 Logo 标识，和用户期望的极简白灰、克制蓝色交互信号不一致。登录页左侧品牌分栏也偏平，缺少轻微层级和识别点。

## 目标

- 浅色主题只使用蓝色作为交互点缀色：主按钮、链接、焦点、选中态、少量 active icon。
- 深色主题使用更亮的蓝色，保证夜间可读。
- `.ui-btn-primary` 使用按钮语义 token，不再直接绑定 `--color-accent`。
- 左上角 Logo 改为白 / 浅灰底、细边框、蓝色小图标，不再是黑色实心块。
- 登录页左侧分栏保持中性白灰，只加入细蓝色识别线和品牌 mark，不做大面积彩色背景。
- 绿色只保留给成功 / 完成状态，不作为品牌色或主按钮色。

## 非目标

- 不重做业务页面布局。
- 不新增第三套主题或用户可切换配色。
- 不引入绿色作为主视觉。
- 不复制 Codex / Trae 的品牌资产或专有 Logo。

## 验收标准

1. 浅色主题下“上传数据集”等 `.ui-btn-primary` 按钮为克制蓝色，不能再是近黑色。
2. 深色主题下 `.ui-btn-primary` 和选中态蓝色对比正常。
3. 左上角系统 Logo 不再是黑色实心块，也不是大面积蓝色块。
4. 登录页左侧分栏有细微层级和蓝色识别点，整体仍是中性白灰 / 深灰。
5. `coding-style.md` 明确蓝色是唯一交互点缀色；绿色仅保留语义成功。
6. 前端 typecheck / lint / build 通过；工程文档门禁和 diff check 通过。

## 实施记录

- 新增按钮和品牌标识语义 token：`--button-primary-*`、`--brand-mark-*`、`--login-brand-*`。
- 浅色 `--color-accent` 从近黑改为 `#2563EB`，深色改为 `#8AB4F8`；正文主色仍使用 `--color-ink`。
- `.ui-btn-primary` 改为使用 `--button-primary-*`，避免直接绑定全局 accent。
- 新增 `.app-brand-mark` 共享类，用于主布局和登录页品牌 mark。
- `LayoutView` 顶部 Logo 改为细边框品牌 mark。
- `LoginView` 移除内联 SVG 品牌字标，改用 lucide `BookOpen`；品牌侧使用中性背景、右边界和左侧 2px 蓝色识别线。

## 验证记录

Environment: macOS 本地开发环境，前端 dev server `http://127.0.0.1:5173/login`。

| Command / Check | Result |
|-----------------|--------|
| `pnpm --filter @metaedu/web typecheck` | exit 0 |
| `pnpm --filter @metaedu/web lint` | exit 0 |
| `pnpm --filter @metaedu/web build` | exit 0；仍有既有 Vite large chunk warning，非本任务新增阻塞 |
| `scripts/check-engineering-docs` | exit 0；31 known issues allowlisted |
| `git diff --check` | exit 0 |
| Browser smoke `/login` light | `data-theme="light"`；`--color-accent: #2563EB`；登录主按钮 `rgb(37, 99, 235)`；品牌 mark 白底、蓝色图标、细边框；登录左侧为浅灰分栏 |
| Dark theme token check | `themes.css` 存在 `--theme-accent: #8AB4F8`、`--_button-primary-bg: #60A5FA`、`--_button-primary-text: #0F1115`、`--_brand-mark-color: #8AB4F8` |

Note: 浏览器插件的页面脚本是只读作用域，不能临时写入 `localStorage` 或 `data-theme`；因此深色主题本轮采用 build + token 静态核验，不伪装为完整浏览器交互验收。

## 当前状态

正在 `codex/req-021-blue-accent-visual-polish` 分支实施，PR 合并前保持 `Doing`。

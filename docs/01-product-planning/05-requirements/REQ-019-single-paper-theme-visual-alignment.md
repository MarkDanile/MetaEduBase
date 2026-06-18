# REQ-019: 单主题视觉风格收敛

Status: 🟣 待 Git 闭环
Priority: P1
Milestone: P2
Owner: TBD

## 背景

当前前端保留 `liquid` / `ink` / `navy` / `notion` 四套可切换主题，默认视觉偏液态玻璃。用户反馈更认可 Codex / Notion 式极简白底，并希望参考“墨韵”图中的暖纸、低饱和、留白和玉青点缀。

多主题在早期验证设计系统 token 化时有价值，但当前阶段更需要统一、精致和稳定的产品气质。继续暴露多主题会增加维护面，也会稀释品牌识别。

## 目标

- 系统默认并唯一呈现一套主风格：极简白底 + 暖纸墨韵。
- 移除普通用户可见的多主题切换入口。
- 保留历史 `liquid-*` 兼容类和旧 `data-theme` 入口，避免已有页面或 localStorage 造成样式断裂。
- 通过 token 和共享壳层完成收敛，不做页面级大重构。

## 非目标

- 不重做各业务页面的信息架构。
- 不新增营销式视觉、插画或装饰背景。
- 不删除历史兼容 CSS 类名。
- 不承诺所有历史文档中的“四主题验收”口径本次全部迁移。

## 设计原则

- 基底取 Codex / Notion 的克制：白底、浅边框、低阴影、少动效。
- 气质取墨韵参考图：暖纸底、墨色文字、玉青/灰绿点缀、细线分隔。
- 保持工作台属性：信息密度适中，优先可读性和稳定交互，不做商品详情页式展示。

## 验收标准

1. 默认主题不再是 `liquid`，新会话进入统一主风格。
2. 左下用户菜单不再暴露四主题切换按钮。
3. 旧 `liquid` / `ink` / `navy` / `notion` 的 `data-theme` 值不会造成页面回到旧风格。
4. 主按钮、面板、侧边栏和背景从玻璃感收敛为低噪音纸感工作台。
5. `liquid-*` 历史兼容类仍存在，避免旧页面样式断裂。
6. 前端 typecheck / lint / build 通过。

## 交付记录

- 2026-06-18：`req-019-single-theme` 完成实现与验证；当前分支需完成 Git 工作流后翻 Done。
- 验证：
  - `pnpm --filter @metaedu/web typecheck` 退出码 0。
  - `pnpm --filter @metaedu/web lint` 退出码 0。
  - `pnpm --filter @metaedu/web build` 退出码 0；仅有既有 Vite chunk size warning。
  - `scripts/check-engineering-docs` 退出码 0。
  - `git diff --check` 退出码 0。
  - 浏览器烟测：`http://127.0.0.1:5173/login` 渲染为 `data-theme="paper"`；`--color-bg-base=#FBF8F1`、`--color-accent=#7E9276`；页面无“主题”切换入口。截图：`/private/tmp/req-019-login-theme-smoke.png`。

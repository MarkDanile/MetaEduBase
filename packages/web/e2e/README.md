# Playwright E2E

REQ-060 Slice 4 浏览器端到端验收。

## 文件结构

- `fixtures.ts`：共享 setup（`setupE2E(page, role)` = `injectAuth` + `installApiMocks`）
- `navigation-shared.spec.ts`：desktop + mobile 都跑（7 角色 sidebar / 重定向 / 403 / breadcrumb）
- `navigation-desktop.spec.ts`：仅 desktop project（activeNav 高亮 / 详情父高亮 / 折叠 / 主题 / skip-link 键盘验收 / 结构视觉断言）
- `navigation-mobile.spec.ts`：仅 mobile project（drawer 状态机 / focus return / Tab/Shift+Tab / body lock / 关闭态 inert / 路由关闭焦点返回 / 结构视觉断言）

`playwright.config.ts` 用 `testMatch` glob 分流：
- `chromium-desktop`：`/.*(-desktop|-shared)\.spec\.ts/`
- `chromium-mobile`：`/.*(-mobile|-shared)\.spec\.ts/`

## 跑测试

```bash
# 安装 Chromium（首次）
pnpm --filter @metaedu/web exec playwright install --with-deps chromium

# 构建 + preview + e2e
pnpm --filter @metaedu/web build:bundle
pnpm --filter @metaedu/web test:e2e
```

`playwright.config.ts` 的 `webServer.command` 自动启动 `vite preview --port 3000`（生产构建）。`reuseExistingServer` 在非 CI 模式下复用已启动服务，CI 模式自动启停。

## 设计

- **Auth + API mock**：`setupE2E(page, role)` 注入 `metaedu_token`/`metaedu_role`/`metaedu_tenant_id` 到 localStorage + 拦截 `/api/v1/*` 返回确定性 mock（防 ECONNREFUSED 导致页面组件回退）。
- **路由**：纯前端路由 + 守卫；guard 读 localStorage 放行。
- **viewport**：2 projects（chromium-desktop 1280×800 + chromium-mobile Pixel 5）按 testMatch 分流。
- **skip-link 键盘测试**：在 desktop spec（仅 desktop project 执行），因为 Pixel 5 touch emulation 的 Tab 序列不可靠。mobile spec 只做结构断言。
- **视觉验收**：用结构断言（`data-theme` + 元素可见性）替代 `toHaveScreenshot`，避免 OS-specific screenshot baseline。
- **Trace**：失败时保留 video + trace，便于调试。

## CI 集成

`ci.yml` frontend job 已包含：
1. `pnpm install --frozen-lockfile`
2. `pnpm --filter @metaedu/web build:bundle`
3. `pnpm --filter @metaedu/web exec playwright install --with-deps chromium`
4. `pnpm --filter @metaedu/web test:e2e`（`CI=true`）
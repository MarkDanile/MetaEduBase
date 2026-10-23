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

### 端口隔离（REQ-064 S1a）

`playwright.config.ts` 的 `webServer.command` 自动启动 `vite preview --port <port> --strictPort`（生产构建）。端口由环境变量 `METAEDU_E2E_PORT` 决定，默认 `3000`，合法范围 **1024–65535**，越界直接报错退出。

`reuseExistingServer` 固定为 `false`：**端口被占用时测试直接失败**，不会静默复用其他 checkout 已在运行的服务（避免并行 Agent 的测试打到别的 worktree 构建产物）。本地已占用 3000 时请改用其他端口：

```bash
METAEDU_E2E_PORT=3101 pnpm --filter @metaedu/web test:e2e
```

CI 集成（`ci.yml` frontend job）不设该变量，使用默认 3000（runner 上无占用）。

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
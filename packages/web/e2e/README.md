# Playwright E2E

REQ-060 Slice 4 浏览器端到端验收。

## 覆盖

- `navigation.spec.ts`：7 角色 sidebar / activeNav 高亮 / 详情父高亮 / mobile drawer（状态机 + a11y）/ 主题 / 旧链接重定向 / 403 / breadcrumb

## 跑测试

```bash
# 安装 Chromium（首次）
pnpm --filter @metaedu/web exec playwright install --with-deps chromium

# 构建 + preview + e2e
pnpm --filter @metaedu/web build
pnpm --filter @metaedu/web test:e2e
```

`playwright.config.ts` 的 `webServer.command` 会自动启动 `vite preview --port 3000`（生产构建）。`reuseExistingServer` 在非 CI 模式下复用已启动服务，CI 模式（`process.env.CI` 存在）自动启停。

## 设计

- **Auth fixture**：用 `injectAuth(page, role)` 注入 `metaedu_token` / `metaedu_role` / `metaedu_tenant_id` 到 localStorage，跳过实际登录（避免后端依赖）。
- **路由**：纯前端路由 + 守卫；guard 读 localStorage 放行，不发实际 API 请求。
- **viewport**：2 projects（chromium-desktop 1280×800 + chromium-mobile Pixel 5）跑同一 spec，分别验证桌面 / 移动路径。
- **Trace**：失败时保留 video + trace，便于调试。

## CI 集成（计划）

```yaml
- name: Install Playwright
  run: pnpm --filter @metaedu/web exec playwright install --with-deps chromium
- name: Web e2e
  run: |
    pnpm --filter @metaedu/web build
    pnpm --filter @metaedu/web test:e2e
  env:
    CI: "true"
```

## 已知限制

- 本地环境 `pnpm install` 受 store 版本差异限制（v11 vs v3 store 路径不兼容）；Playwright 二进制需在 CI 容器或本地手动 `playwright install --with-deps chromium`。
- 此目录的代码不参与 vitest 跑（`vitest.config.ts` 仅匹配 `src/**/*.{ts,vue}`）。
- 浅色 / 深色主题断言用 evaluate 切换 `data-theme`（不依赖实际主题存储初始化），覆盖交互路径 + 主题变量解析正确性。
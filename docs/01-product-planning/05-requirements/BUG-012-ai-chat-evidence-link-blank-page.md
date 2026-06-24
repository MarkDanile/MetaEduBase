# BUG-012 — AI Chat 证据引用 / 参考来源点击打开空白页

> Status: 🔵 Ready（已塑形，待实现）
> Priority: P1
> Area: 前端 / P2 AI Chat / 资源详情
> Created: 2026-06-24

## 现象

AI Chat 回答结果中：

1. 点击正文里的**证据引用**（如 `[1]`），新标签打开 `http://localhost:3000/resource/files/358bd704-d223-4228-8935-3a6e1b3e699f?chunk=31d7c00a-81ad-4b6d-983f-95a2ad11b103` → **空白页**。
2. 点击**参考的来源**卡片打开 pdf，`http://localhost:3000/resource/files/358bd704-d223-4228-8935-3a6e1b3e699f` → 同样**空白页**。

资源库（ResourceLibraryView）正常进入文件详情页；仅 AI Chat 发起的跳转空白。

## 根因（2026-06-24 只读排查）

**路由不匹配：链接路径多了 `files/` 段。**

- 路由定义：`path: "resource/:id"`（`packages/web/src/app/router.ts:36`）→ 实际匹配 `/resource/{id}`。
- 资源库正常跳转：`router.push(\`/resource/${id}\`)`（`ResourceLibraryView.vue:213`）—— 匹配路由。
- AI Chat 链接（坏）：
  - `buildFileOpenUrl` → `const base = \`/resource/files/${fileId}\``（`packages/web/src/views/ai-chat/openFileUrl.ts:21`）。
  - `EvidenceRefLink.vue:34` → `window.location.href = \`/resource/files/${...file_id}...\``。
  - 两处都拼成 `/resource/files/{id}`，**无匹配路由**。
- 路由表无 catch-all / 404（`router.ts` 无 `:catchAll` / `pathMatch`）→ 未匹配路径渲染 `LayoutView` 外壳但无子 `<RouterView>` 内容 → 空白页。

**附带缺陷**：`packages/web/src/views/ai-chat/__tests__/openFileUrl.spec.ts` 把错误期望值 `/resource/files/file-abc` 锁进断言（L16/L21/L26/L30/L64/L71/L82），测试"通过"但功能坏——测试固化了 bug，必须同步修正。

## 影响面

- 证据引用 `[n]` 点击（`EvidenceRefLink.vue`）：正文引用全部不可达。
- 参考来源卡片（`AiChatView` `openDocumentSource` / `openEvidenceFile` → `openFile` → `buildFileOpenUrl`）：来源跳转全部不可达。
- 仅 AI Chat 出口；资源库、其他入口不受影响。

## 完成标准

- AC-1：点击证据引用 `[n]`，新标签打开 `/resource/{fileId}?chunk={chunkId}`，正常渲染 FileDetailView 并定位 chunk 锚点。
- AC-2：点击参考来源卡片，新标签打开 `/resource/{fileId}`，正常渲染 FileDetailView。
- AC-3：`buildFileOpenUrl` 与 `EvidenceRefLink` 拼出的路径与路由 `resource/:id` 一致（无多余 `files/` 段）。
- AC-4：`openFileUrl.spec.ts` 期望值同步修正为正确路径；新增/修正用例覆盖「带 chunk / 不带 chunk / 空 chunk」。
- AC-5：`pnpm test` / `typecheck` / `lint` 通过，无回归。

## 验证方式

- vitest 锁住正确 URL 构造。
- 手动：AI Chat 提问 → 点击证据引用 + 参考来源 → 新标签非空白、定位 chunk。
- `grep -rn "/resource/files/" packages/web/src` 确认无残留错误路径（注释除外）。

## 修复方向（候选，待实现时定）

- 方案 A（推荐，最小改动）：`buildFileOpenUrl` base 改 `/resource/${fileId}`；`EvidenceRefLink.vue:34` 同步改 `/resource/${file_id}`。修正 spec 期望值。
- 方案 B：新增路由别名 `resource/files/:id` → `file-detail`（兼容旧链接，但治标）。
- 倾向 A：根治路径错误，不引入冗余路由；B 仅在外部链接已固化时考虑。

## 非目标

- 不改 FileDetailView 内部渲染逻辑（资源库入口正常，说明组件本身可用）。
- 不改后端 / 契约 / 数据。
- 不引入 catch-all 404 页（独立改进，另行登记）。

## follow-up 候选

- 路由表增加 catch-all 404 页，避免任何未匹配路径静默空白（独立 DOC/BUG）。

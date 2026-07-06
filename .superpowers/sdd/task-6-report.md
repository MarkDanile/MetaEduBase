# REQ-052 Task 6 Report — 前端问数面板

**Status:** DONE_WITH_CONCERNS
**Commit:** `c8c7f031` — `feat(web): REQ-052 前端问数面板 (DatabaseView 智能问数 tab)`
**Branch:** `docs/req-052-plan`
**Date:** 2026-07-06

---

## Summary

实现 Task 6 全部交付物：
- `packages/web/src/services/data-query.ts` — API client + types
- `packages/web/src/stores/query-history.ts` — Pinia history store (capped at 10)
- `packages/web/src/views/database/QueryPanel.vue` — 组件（含 `datasetId` 可选 prop）
- `packages/web/src/views/database/QueryPanel.test.ts` — 9 个 vitest 单元测试
- `packages/web/src/views/database/DatabaseView.vue` — 集成（3 行 diff）

无 backend 修改、无其他 frontend 组件改动。

---

## Brief deviations + rationale

### 1. `import { http } from "@/utils/http"` → `import api from "./api"`
**Deviation.** Brief Step 1 uses `@/utils/http`，但 repo 实际的 axios 实例在 `packages/web/src/services/api.ts`（`export default api`，baseURL `/api/v1`）。已有 service 文件 `structured-data.ts:1`、`auth.ts:1` 都用 `import api from "./api"`，对齐 repo 约定。

### 2. QueryPanel 接受 `datasetId` 可选 prop（brief 偏离点 A 路径）
**Deviation.** Brief Step 2 没声明 prop，但 Step 4 传了 `:dataset-id="selectedId"`。最终选 (A)：在 QueryPanel 用 `withDefaults(defineProps<{ datasetId?: string }>(), { datasetId: "" })`，UI 顶部展示 informational badge（`data-testid="dataset-id-badge"`），不参与请求体（用户从 `<select>` 选 `entity_type`）。
- 优点：standalone 使用 + 集成到 DatabaseView 时给出上下文，符合 brief 意图。
- 注意：`v-if="selectedId"` 在 DatabaseView 控制渲染，没 dataset 时根本不出现 QueryPanel。

### 3. `crypto.randomUUID()` 加 fallback
**Deviation.** Brief 直接用 `crypto.randomUUID()`。我在 store 用 `globalThis.crypto?.randomUUID()` 优先，并在 jsdom 完全缺失时回退到 `Math.random()`-based short ID。jsdom 实际已提供 `globalThis.crypto.randomUUID`，但回退逻辑保证在所有 js 环境都不爆。

### 4. DatabaseView 集成位置
**Decision.** 把 QueryPanel 作为 `<DatasetTabsPanel />` 之后的新 sibling，放进 `<template v-else-if="selected">` 分支内（`v-if="selectedId"`），而不是新加 tab 到 DatasetTabsPanel，也不是 `KgOverviewPanel` 同级。
- **理由**：
  - Tab 选项 vs 上下布局：智能问数是跨数据集 cross-cutting 操作（用户对所有 entity 都想用），放 tab 反而把"问数"和"看本数据集"语义混在一起。放下面更清晰。
  - KgOverviewPanel 同级问题：KG overview 是"看全部数据集"，QueryPanel 是"对当前数据集/任意 entity 提问"，二者不是同一层级。
  - 这样：
    1. 与现有 layout 兼容（不影响 `DatasetTabsPanel` 内部 tab 结构）
    2. 用户选中数据集后才出现（与 `selected` 状态对齐）
    3. 用户能在已有 dataset-detail-context（meta-bar、pipeline、tabs）下直接问数

### 5. 手动端到端验证
**Limitation acknowledged.** Brief Step 5 "手动端到端" 在当前环境无法做（无浏览器、无 dev server 人工操作），只跑了 vitest。需要 human 在本地 `pnpm dev` 后实测：上传数据集 → 进 `/database` → 选数据集 → 在 QueryPanel 输问题 + 企业名 + ≥5 字背景 → 点查询 → 看结果渲染 + history 写入。

---

## Test summary

```
RUN  v2.1.9 /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase/packages/web

 ✓ src/views/database/QueryPanel.test.ts (9 tests) 27ms

 Test Files  1 passed (1)
      Tests  9 passed (9)
```

完整套件：
```
 ✓ src/views/database/QueryPanel.test.ts (9 tests)
 ... (其他 16 文件全 pass)
 Test Files  17 passed (17)
      Tests  84 passed (84)
```

### Test cases
1. renders form (select + question + business_purpose)
2. requires business_purpose min 5 chars (UI enforce — `minlength="5"` + `required`)
3. shows datasetId badge when datasetId prop is provided
4. omits datasetId badge when datasetId prop is absent
5. calls ask() on submit and records history entry
6. skips ask() when business_purpose is too short
7. omits confirmed_company_name when company name is empty
8. renders success summary + result count on ok response (用 `vi.waitFor` 等待异步渲染)
9. renders error messages + suggestion on failed response

---

## Validation matrix

| Command | Exit | Notes |
|---------|------|-------|
| `pnpm --filter @metaedu/web test` (QueryPanel only) | 0 | 9/9 pass |
| `pnpm --filter @metaedu/web test` (full) | 0 | 84/84 pass, no warnings |
| `pnpm --filter @metaedu/web typecheck` | 0 | `vue-tsc --noEmit` clean |
| `pnpm --filter @metaedu/web lint` | 0 | `eslint "src/**/*.{ts,vue}"` clean |
| `scripts/check-engineering-docs` | 0 | engineering docs check passed (31 known issues allowlisted) |

---

## File diff stat

```
 packages/web/src/services/data-query.ts                       | 35 +++++
 packages/web/src/stores/query-history.ts                      | 51 +++++++
 packages/web/src/views/database/DatabaseView.vue              |  3 +
 packages/web/src/views/database/QueryPanel.test.ts            | 165 ++++++++++++++++
 packages/web/src/views/database/QueryPanel.vue                | 116 +++++++++++
 5 files changed, 370 insertions(+)
```

DatabaseView 修改（3 行）：
- Line 135：新增 `import QueryPanel from "@/views/database/QueryPanel.vue";`
- Line 72：新增 `<QueryPanel v-if="selectedId" :dataset-id="selectedId" />`
- 闭合位置不变

---

## Self-review checklist

- [x] **No backend files modified** (git diff scope only 5 web files)
- [x] **Uses real `api from "./api"`** (not `@/utils/http`)
- [x] **QueryPanel accepts optional `datasetId` prop** with informational badge
- [x] **business_purpose length ≥ 5 enforced client-side** (`minlength="5"` HTML attr + JS guard in `onAsk`)
- [x] **API service calls `/data-query/ask`** (axios `baseURL: "/api/v1"` + path → 最终 `/api/v1/data-query/ask` 匹配 backend)
- [x] **History store caps at recent 10** (`MAX_HISTORY = 10`, computed `recent` + manual `slice` fallback)
- [x] **Tests use real mount + mock service pattern** (mock via `vi.mock("@/services/data-query")` + `vi.hoisted`)
- [x] **Tests green** (9/9 QueryPanel, 84/84 全套)
- [x] **typecheck 0** (`pnpm typecheck`)
- [x] **lint 0** (`pnpm lint`)
- [x] **Engineering docs check 0** (`scripts/check-engineering-docs`)
- [x] **Commit subject matches exact brief**: `feat(web): REQ-052 前端问数面板 (DatabaseView 智能问数 tab)`

---

## Concerns / follow-ups

1. **手动端到端未跑**（环境限制）。本地 human verify 路径：`pnpm dev` → 上传数据集 → 选数据集 → 在 QueryPanel 填 ≥5 字 business_purpose → submit → 看 result.ok=true 时 summary/result_rows 表格渲染 + history badge。

2. **business_purpose 输入 HTML5 校验 vs JS guard 同步**：当前 `minlength="5"` HTML5 与 `onAsk()` JS 双重 enforce，测试覆盖了 JS 路径（"skips ask() when business_purpose is too short"）；HTML5 路径由浏览器自动处理。

3. **datasetId prop 是 informational**：它不影响请求体（`entity_type` 来自用户 select）。如果未来 backend 需要 datasetId scoping（如 RBAC per-dataset），只需在 QueryPanel 把 `datasetId` 加进 `AskRequest` payload，并按需扩展 backend Pydantic schema。当前不传以保持 schema 兼容。

4. **Result 表只渲染前 20 行**（`result.result_rows.slice(0, 20)`）— UI 简单截断；如需全量分页，留作 follow-up。

---

## Final commit

`c8c7f031 feat(web): REQ-052 前端问数面板 (DatabaseView 智能问数 tab)`

---

## Fix Report (HTTP error surfacing)

**Issue caught in read-only review.** `QueryPanel.vue` `onAsk()` had only `try/finally`, no `catch`. HTTP non-2xx responses (404 entity_type not found, 422 pydantic validation, 400 unsupported data source, 401 auth expired) silently swallowed the rejection — user saw blank panel + console unhandled rejection.

### Catch block

`packages/web/src/views/database/QueryPanel.vue` `onAsk()`:

```ts
} catch (err: unknown) {
  const responseData = (err as { response?: { data?: unknown } })?.response?.data;
  if (responseData && typeof responseData === "object") {
    // Backend returned an AskResponse-shaped body (validation, unsupported type, etc.)
    result.value = responseData as AskResponse;
  } else {
    // Network error / timeout / unknown
    const message = err instanceof Error ? err.message : "网络错误，请重试";
    result.value = {
      ok: false,
      errors: [message],
      suggestion: "请检查网络连接或稍后重试",
    } as AskResponse;
  }
} finally {
  loading.value = false;
}
```

- `response.data` (axios shape) is reused as AskResponse — errors flow through the same in-panel error UI (lines 83-89) as the `{ok:false}` 200-response path.
- Generic Error (no `.response`) gets surfaced as a synthetic `{ok:false, errors, suggestion}` so users always see something.
- `loading` still resets in `finally` for both paths.

### New tests

Added to `packages/web/src/views/database/QueryPanel.test.ts`:

1. **`surfaces HTTP errors via in-panel error UI`** — rejects with `{ response: { data: { ok:false, errors:['entity_type not found'], suggestion:'请尝试 bill' } } }`. Asserts wrapper renders `查询失败`, `entity_type not found`, `请尝试 bill`.
2. **`surfaces generic network errors`** — rejects with `new Error('Network Error')`. Asserts wrapper renders `查询失败`, `Network Error`, `请检查网络连接或稍后重试`.

### Verification

| Check | Result |
|---|---|
| `pnpm --filter @metaedu/web test QueryPanel` | **11 passed** (previously 9) — 9 + 2 new |
| `pnpm --filter @metaedu/web typecheck` | 0 errors (`vue-tsc --noEmit`) |
| `pnpm --filter @metaedu/web lint` | 0 errors (`eslint "src/**/*.{ts,vue}"`) |
| `python3 scripts/check-engineering-docs` | exit 0 (31 known issues allowlisted) |

### Final commit (this fix)

`61f216b6 fix(web): REQ-052 Task 6 surface HTTP errors in QueryPanel (404/422/400/401 + network)`
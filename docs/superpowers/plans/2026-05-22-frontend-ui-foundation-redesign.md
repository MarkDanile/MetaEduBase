# Frontend UI Foundation Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the right-side workspace UI foundation so all themes share one calm, minimal content system, then migrate the main business pages onto that system without changing business logic.

**Architecture:** Keep the current Vue views and shared components, but shift styling from theme-specific `liquid-*` behavior to semantic `ui-*` workspace classes and semantic tokens in `main.css`. Migrate one baseline page first (`HomeView.vue`), then adapt the rest of the views to the same page shell, panel hierarchy, toolbar density, and subdued interaction model.

**Tech Stack:** Vue 3.5, Vite 6, Tailwind CSS 4, Pinia 3, lucide-vue-next, CSS custom properties in `packages/web/src/assets/css/main.css`

---

## Implementation Constraints

- This repo has **no Vitest / Playwright / Cypress frontend test harness** in `packages/web/package.json`.
- Do **not** add a new test framework for this UI refactor.
- Validation for each task must use:
  1. `cd packages/web && pnpm typecheck`
  2. `cd packages/web && pnpm build`
  3. manual browser verification on the affected routes in all four themes
- Keep all changes surgical: no route changes, no API changes, no store changes, no left-nav IA rewrite.
- Prefer class and token refactors over creating many new Vue components.

---

## File Structure

### Files to modify

```text
packages/web/src/assets/css/main.css                 # Theme tokens, semantic workspace tokens, ui-* classes, subdued motion
packages/web/src/views/LayoutView.vue                # Right-side app canvas shell and workspace framing
packages/web/src/components/PageHeader.vue           # Header block spacing and calmer heading rhythm
packages/web/src/components/EmptyState.vue           # Empty state density and panel-friendly styling
packages/web/src/views/HomeView.vue                  # Baseline page migration to the new workspace system
packages/web/src/views/knowledge/KnowledgeBaseView.vue   # Toolbar/list/detail layout migration
packages/web/src/views/resource/ResourceLibraryView.vue  # Sidebar + table workspace migration
packages/web/src/views/resource/FileDetailView.vue       # Detail page panel, tabs, and metadata density migration
packages/web/src/views/database/DatabaseView.vue         # Dual-pane dataset workspace migration
packages/web/src/views/ai-chat/AiChatView.vue            # Chat workspace shell and calmer message/input surfaces
packages/web/src/views/admin/AdminView.vue               # Empty shell migration
packages/web/src/views/skill/SkillEditorView.vue         # Empty shell migration
```

### Responsibilities

- `main.css` owns the system: theme raw values, semantic UI tokens, workspace shell classes, panel classes, toolbars, subdued hover/focus/motion.
- `LayoutView.vue` owns the global app workspace frame, not per-page styling.
- `PageHeader.vue` and `EmptyState.vue` must become reusable primitives that look correct inside any `ui-page-shell` / `ui-panel` context.
- Each view should only express page composition. Page-specific visual decisions should be minimized and moved into shared semantic classes where possible.

---

## Verification Matrix

Use this same matrix after every view migration:

1. Start frontend: `./dev.sh frontend`
2. Open these routes manually:
   - `/`
   - `/knowledge`
   - `/resource`
   - `/resource/<existing-id>`
   - `/database`
   - `/ai-chat`
   - `/admin`
   - `/skill-editor`
3. In the user menu, switch through themes: `liquid`, `ink`, `navy`, `notion`
4. Confirm:
   - right-side background is calm
   - panels do not look heavy or overdecorated
   - hover states are subtle
   - spacing is consistent
   - text contrast stays readable
   - no layout jumps when switching themes

---

## Task 1: Add semantic workspace tokens and shared ui-* classes

**Files:**
- Modify: `packages/web/src/assets/css/main.css`

- [ ] **Step 1: Add semantic workspace tokens in the `@theme` block**

Insert these tokens after the existing surface tokens so the semantic layer becomes the only API consumed by page classes:

```css
  --canvas-bg: var(--_canvas-bg);
  --canvas-top-glow: var(--_canvas-top-glow);
  --canvas-grid-opacity: var(--_canvas-grid-opacity);
  --panel-bg: var(--_panel-bg);
  --panel-bg-muted: var(--_panel-bg-muted);
  --panel-bg-ghost: var(--_panel-bg-ghost);
  --panel-border: var(--_panel-border);
  --panel-border-strong: var(--_panel-border-strong);
  --panel-shadow: var(--_panel-shadow);
  --panel-shadow-hover: var(--_panel-shadow-hover);
  --interactive-hover-bg: var(--_interactive-hover-bg);
  --interactive-active-bg: var(--_interactive-active-bg);
  --focus-ring: var(--_focus-ring);
  --content-max-width: 1120px;
  --content-max-width-wide: 1440px;
  --content-gutter: 32px;
  --section-gap: 24px;
  --panel-radius: 14px;
```

- [ ] **Step 2: Define per-theme semantic token values**

For each theme block, add these values and keep them intentionally restrained:

```css
  --_canvas-bg: var(--theme-bg-base);
  --_canvas-top-glow: transparent;
  --_canvas-grid-opacity: 0;
  --_panel-bg: var(--theme-bg-elevated);
  --_panel-bg-muted: color-mix(in srgb, var(--theme-bg-elevated) 72%, var(--theme-bg-warm));
  --_panel-bg-ghost: transparent;
  --_panel-border: var(--theme-border-subtle);
  --_panel-border-strong: var(--theme-border);
  --_panel-shadow: 0 1px 2px rgba(15, 23, 42, 0.03);
  --_panel-shadow-hover: 0 2px 8px rgba(15, 23, 42, 0.05);
  --_interactive-hover-bg: var(--theme-bg-hover);
  --_interactive-active-bg: var(--theme-accent-bg);
  --_focus-ring: var(--theme-accent-ring);
```

Use these theme-specific adjustments:

```css
:root[data-theme="liquid"] {
  --_canvas-top-glow: radial-gradient(ellipse at top, rgba(76, 94, 235, 0.06), transparent 62%);
  --_panel-bg: rgba(255, 255, 255, 0.82);
  --_panel-bg-muted: rgba(255, 255, 255, 0.58);
}

:root[data-theme="ink"] {
  --_panel-shadow: 0 1px 2px rgba(28, 28, 28, 0.03);
  --_panel-shadow-hover: 0 3px 10px rgba(28, 28, 28, 0.04);
}

:root[data-theme="navy"] {
  --_panel-border: #e2e8f0;
  --_panel-border-strong: #cbd5e1;
}

:root[data-theme="notion"] {
  --_panel-shadow: none;
  --_panel-shadow-hover: none;
}
```

- [ ] **Step 3: Add new semantic workspace classes and simplify old visual noise**

Replace the existing heavy `content-bg` / `liquid-card` behavior with this semantic layer. Keep old class names as compatibility aliases for now.

```css
  .app-canvas {
    min-height: 100vh;
    background: var(--canvas-top-glow), var(--canvas-bg);
  }

  .ui-page-shell {
    width: 100%;
    max-width: var(--content-max-width);
    margin: 0 auto;
    padding: var(--content-gutter);
  }

  .ui-page-shell-wide {
    width: 100%;
    max-width: var(--content-max-width-wide);
    margin: 0 auto;
    padding: 24px var(--content-gutter) 32px;
  }

  .ui-page-section {
    margin-top: var(--section-gap);
  }

  .ui-panel,
  .liquid-card {
    background: var(--panel-bg);
    border: 1px solid var(--panel-border);
    border-radius: var(--panel-radius);
    box-shadow: var(--panel-shadow);
    backdrop-filter: var(--surface-glass-blur-light);
    -webkit-backdrop-filter: var(--surface-glass-blur-light);
    transition: border-color var(--duration-fast) var(--ease-out),
                background-color var(--duration-fast) var(--ease-out),
                box-shadow var(--duration-fast) var(--ease-out);
  }

  .ui-panel:hover,
  .liquid-card:hover {
    border-color: var(--panel-border-strong);
    box-shadow: var(--panel-shadow-hover);
    transform: none;
  }

  .ui-panel-muted {
    background: var(--panel-bg-muted);
    border: 1px solid var(--panel-border);
    border-radius: var(--panel-radius);
  }

  .ui-panel-ghost {
    background: var(--panel-bg-ghost);
    border: 1px solid transparent;
    border-radius: var(--panel-radius);
  }

  .ui-toolbar {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px 14px;
    background: var(--panel-bg-muted);
    border: 1px solid var(--panel-border);
    border-radius: calc(var(--panel-radius) - 2px);
  }

  .ui-interactive-row {
    transition: background-color var(--duration-fast) var(--ease-out),
                border-color var(--duration-fast) var(--ease-out),
                color var(--duration-fast) var(--ease-out);
  }

  .ui-interactive-row:hover {
    background: var(--interactive-hover-bg);
  }

  .content-bg {
    background: transparent;
    background-image: none;
  }
```

Also make these targeted simplifications:

```css
  .liquid-card-scan::after,
  .nav-item-active .nav-icon::before,
  .markdown-body blockquote::after {
    display: none;
  }

  .animate-slide-up,
  .stagger-1,
  .stagger-2,
  .stagger-3,
  .stagger-4,
  .stagger-5 {
    animation: none;
  }

  .liquid-rise-enter-active,
  .liquid-rise-leave-active {
    transition: opacity var(--duration-fast) var(--ease-out);
  }

  .liquid-rise-enter-from,
  .liquid-rise-leave-to {
    opacity: 0;
    transform: none;
    filter: none;
  }
```

- [ ] **Step 4: Tighten shared input and button focus states around the new semantic tokens**

Update these existing shared classes in the same file:

```css
  .liquid-input:focus {
    background: var(--surface-input-bg-focus);
    border-color: var(--color-accent);
    box-shadow: 0 0 0 3px var(--focus-ring);
  }

  .liquid-btn-ghost:hover {
    background: var(--interactive-hover-bg);
    color: var(--color-ink);
    border-color: var(--panel-border-strong);
  }

  .sidebar-shell {
    background: var(--surface-sidebar-bg);
    border-right: 1px solid var(--panel-border);
  }
```

- [ ] **Step 5: Run typecheck**

Run:

```bash
cd packages/web && pnpm typecheck
```

Expected: PASS with no TypeScript errors.

- [ ] **Step 6: Run production build**

Run:

```bash
cd packages/web && pnpm build
```

Expected: PASS and Vite build completes successfully.

- [ ] **Step 7: Commit**

```bash
git add packages/web/src/assets/css/main.css
git commit -m "refactor(web): add semantic workspace tokens for theme system"
```

---

## Task 2: Reframe the global right-side workspace shell

**Files:**
- Modify: `packages/web/src/views/LayoutView.vue`

- [ ] **Step 1: Replace the current `main` shell with the semantic app canvas**

Change the `main` block from this structure:

```vue
<main
  id="main-content"
  class="flex-1 min-h-screen content-bg transition-all duration-300 ease-out"
  :class="collapsed ? 'ml-[60px]' : 'ml-[200px]'"
>
```

To this calmer shell:

```vue
<main
  id="main-content"
  class="app-canvas flex-1 min-h-screen transition-all duration-300 ease-out"
  :class="collapsed ? 'ml-[60px]' : 'ml-[200px]'"
>
  <RouterView v-slot="{ Component, route }">
    <transition name="liquid-rise" mode="out-in">
      <component :is="Component" :key="route.path" />
    </transition>
  </RouterView>
</main>
```

- [ ] **Step 2: Soften navigation and user menu surfaces to match the new foundation**

Update these style rules in the `<style scoped>` block:

```css
.nav-item {
  display: flex;
  align-items: center;
  gap: 12px;
  height: 40px;
  padding: 0 12px;
  border-radius: 10px;
  color: var(--color-ink-secondary);
  font-size: 14px;
  font-weight: 400;
  text-decoration: none;
  transition: background-color var(--duration-fast) var(--ease-out),
              color var(--duration-fast) var(--ease-out),
              border-color var(--duration-fast) var(--ease-out);
  overflow: hidden;
  white-space: nowrap;
}

.nav-item:hover {
  background: var(--interactive-hover-bg);
  color: var(--color-ink);
}

.nav-item-active {
  background: var(--interactive-active-bg);
  color: var(--color-accent);
  font-weight: 500;
}

.user-menu-item:hover {
  background: var(--interactive-hover-bg);
  color: var(--color-ink);
}
```

- [ ] **Step 3: Run typecheck**

```bash
cd packages/web && pnpm typecheck
```

Expected: PASS.

- [ ] **Step 4: Manual verify the workspace frame**

Run:

```bash
./dev.sh frontend
```

Verify manually on `/` and `/knowledge`:
- right-side background is plain and quiet
- left nav still collapses correctly
- theme switcher still works
- content no longer shows the old patterned background

- [ ] **Step 5: Commit**

```bash
git add packages/web/src/views/LayoutView.vue
git commit -m "refactor(web): simplify global workspace shell"
```

---

## Task 3: Update shared header and empty-state primitives

**Files:**
- Modify: `packages/web/src/components/PageHeader.vue`
- Modify: `packages/web/src/components/EmptyState.vue`

- [ ] **Step 1: Make `PageHeader` a calmer page-header block**

Replace the template in `PageHeader.vue` with:

```vue
<template>
  <div class="ui-page-header-block" :class="staggerClass">
    <slot name="greeting" />
    <div class="flex items-start justify-between gap-4 flex-wrap">
      <div class="min-w-0">
        <h1 class="text-[var(--text-page-title)] font-semibold tracking-tight leading-tight">
          <slot name="title">{{ title }}</slot>
        </h1>
        <p v-if="subtitle" class="text-[var(--color-ink-tertiary)] mt-1 text-[var(--text-body)]">
          {{ subtitle }}
        </p>
      </div>
      <slot name="extra" />
    </div>
  </div>
</template>
```

Add these styles:

```vue
<style scoped>
.ui-page-header-block {
  margin-bottom: var(--spacing-section);
}
</style>
```

- [ ] **Step 2: Make `EmptyState` panel-friendly and less decorative**

Replace the root template classes in `EmptyState.vue`:

```vue
<template>
  <div class="py-10 text-center">
    <slot name="icon">
      <FileText :size="40" :stroke-width="1.25" class="mx-auto mb-4 text-[var(--color-ink-dim)]" aria-hidden="true" />
    </slot>
    <div class="max-w-[420px] mx-auto px-4">
      <p class="text-[var(--color-ink)] text-[var(--text-body)] font-medium">{{ title }}</p>
      <p v-if="hint" class="text-[var(--color-ink-tertiary)] mt-1">{{ hint }}</p>
    </div>
    <div class="mt-4">
      <slot name="action" />
    </div>
  </div>
</template>
```

- [ ] **Step 3: Run typecheck**

```bash
cd packages/web && pnpm typecheck
```

Expected: PASS.

- [ ] **Step 4: Manual verify shared primitives**

Check `/`, `/admin`, and `/skill-editor`:
- header no longer renders a decorative wet line
- empty state still centers correctly
- page headers with action slots still align correctly

- [ ] **Step 5: Commit**

```bash
git add packages/web/src/components/PageHeader.vue packages/web/src/components/EmptyState.vue
git commit -m "refactor(web): simplify shared workspace primitives"
```

---

## Task 4: Migrate the homepage as the baseline page

**Files:**
- Modify: `packages/web/src/views/HomeView.vue`

- [ ] **Step 1: Move `HomeView` onto the semantic page shell**

Change the page root and section wrappers:

```vue
<template>
  <div class="ui-page-shell">
    <PageHeader title="元知职教基座" subtitle="构建 · 管理 · 探索职业教育知识体系">
      <template #greeting>
        <p class="text-[var(--color-ink-tertiary)] mb-1">{{ greeting }}，{{ roleLabel }}</p>
      </template>
    </PageHeader>

    <section class="ui-page-section">
      <!-- stats grid -->
    </section>

    <section class="ui-page-section grid grid-cols-1 lg:grid-cols-5 gap-6">
      <!-- left modules + right shortcuts/activity -->
    </section>
  </div>
</template>
```

- [ ] **Step 2: Replace heavyweight cards with semantic panels**

Update the stats, module links, and right-side blocks:

```vue
<div v-for="stat in stats" :key="stat.label" class="ui-panel p-4">
  ...
</div>

<RouterLink
  v-for="item in navItems"
  :key="item.route"
  :to="item.route"
  class="ui-panel p-4 group ui-interactive-row"
>
  ...
</RouterLink>

<div class="ui-panel p-5 space-y-5">
  ...
</div>
```

Also tone down icon chips:

```vue
<div class="w-8 h-8 rounded-lg flex items-center justify-center bg-[var(--panel-bg-muted)] border border-[var(--panel-border)]">
  <div v-html="stat.icon" />
</div>
```

- [ ] **Step 3: Normalize emphasis density**

Remove decorative scan behavior and reduce overuse of accent backgrounds in stat/module blocks by changing `bgClass` values in the computed arrays to semantic muted surfaces:

```ts
bgClass: "bg-[var(--panel-bg-muted)] border border-[var(--panel-border)]"
```

Keep accent-colored icons, but stop using large accent-toned chip backgrounds as the default card signal.

- [ ] **Step 4: Run typecheck**

```bash
cd packages/web && pnpm typecheck
```

Expected: PASS.

- [ ] **Step 5: Manual verify baseline page**

Check `/` in all four themes:
- cards feel lighter than before
- right column and left grid share one visual system
- accent only appears in small iconography and hover/interactive cues
- no section feels more decorated than the content it contains

- [ ] **Step 6: Commit**

```bash
git add packages/web/src/views/HomeView.vue
git commit -m "refactor(web): migrate home view to semantic workspace layout"
```

---

## Task 5: Migrate the knowledge page to the new shell, toolbar, and detail panel rules

**Files:**
- Modify: `packages/web/src/views/knowledge/KnowledgeBaseView.vue`

- [ ] **Step 1: Replace the page root with a wide page shell**

Update the root wrapper and header block:

```vue
<template>
  <div class="ui-page-shell-wide flex gap-6" style="min-height: 100vh">
    <div class="flex-1 min-w-0">
      <div class="flex items-start justify-between gap-4 flex-wrap mb-[var(--spacing-section)]">
        <PageHeader title="知识库" subtitle="结构化职业教育知识体系" />
        <button @click="showCreateDialog = true" class="liquid-btn liquid-btn-primary flex-shrink-0">
          <Plus :size="16" :stroke-width="2" />
          新建节点
        </button>
      </div>
```

- [ ] **Step 2: Convert the search row into a shared toolbar pattern**

Replace the search block with:

```vue
<div class="ui-toolbar mb-[var(--spacing-section)]">
  <Search :size="16" :stroke-width="1.5" color="var(--color-ink-tertiary)" />
  <input
    v-model="searchQuery"
    type="text"
    class="flex-1 bg-transparent outline-none text-[var(--text-body)] text-[var(--color-ink)] placeholder:text-[var(--color-ink-tertiary)]"
    placeholder="搜索知识节点..."
    @keyup.enter="handleSearch"
  />
  <button v-if="searchQuery" @click="clearSearch" class="text-[var(--color-ink-tertiary)] hover:text-[var(--color-ink)] transition-colors">
    清除
  </button>
</div>
```

- [ ] **Step 3: Convert list rows and the detail drawer to semantic panels**

Use these replacements:

```vue
<div
  v-for="node in nodes"
  :key="node.id"
  class="ui-panel p-4 cursor-pointer group ui-interactive-row"
  :class="{ 'ring-1 ring-[var(--color-accent)] ring-offset-2': selectedNode?.id === node.id }"
  @click="selectNode(node)"
>
```

And the right-side detail panel:

```vue
<div
  v-if="selectedNode"
  class="w-[360px] flex-shrink-0 ui-panel h-[calc(100vh-48px)] sticky top-6 overflow-y-auto"
>
```

Change the small metadata blocks inside the detail panel to `ui-panel-muted` wrappers instead of raw warm backgrounds.

- [ ] **Step 4: Run typecheck**

```bash
cd packages/web && pnpm typecheck
```

Expected: PASS.

- [ ] **Step 5: Manual verify knowledge workspace**

Check `/knowledge` in all themes:
- search bar reads as one subdued toolbar
- list rows no longer feel like floating cards
- detail side panel looks like part of the same workspace system
- create dialog still opens and closes correctly

- [ ] **Step 6: Commit**

```bash
git add packages/web/src/views/knowledge/KnowledgeBaseView.vue
git commit -m "refactor(web): migrate knowledge view to shared workspace system"
```

---

## Task 6: Migrate the resource library and file detail views

**Files:**
- Modify: `packages/web/src/views/resource/ResourceLibraryView.vue`
- Modify: `packages/web/src/views/resource/FileDetailView.vue`

- [ ] **Step 1: Move `ResourceLibraryView` to `ui-page-shell-wide` and semantic panels**

Change the root wrappers and primary columns:

```vue
<div class="ui-page-shell-wide">
  <PageHeader title="资源库" subtitle="文档管理与处理" />

  <div class="grid grid-cols-[240px_minmax(0,1fr)] gap-4" style="min-height: calc(100vh - 200px)">
    <div class="ui-panel p-3 flex flex-col gap-2">
      <!-- folder tree -->
    </div>

    <div class="ui-panel p-4 flex flex-col gap-3">
      <!-- upload area, filters, table -->
    </div>
  </div>
</div>
```

- [ ] **Step 2: Replace ad hoc filter and upload surfaces with semantic muted containers**

Update the upload drop area and filter row:

```vue
<div
  class="ui-panel-muted border-2 border-dashed border-[var(--panel-border)] rounded-[var(--panel-radius)] p-4 text-center transition-colors cursor-pointer"
  :class="isDragging ? 'border-[var(--color-accent)] bg-[var(--interactive-active-bg)]' : 'hover:border-[var(--panel-border-strong)]'"
>
```

```vue
<div class="ui-toolbar flex-wrap">
  <span class="text-[var(--text-small)] text-[var(--color-ink-tertiary)]">筛选:</span>
  ...
</div>
```

For folder rows and file rows, add `ui-interactive-row` to keep hover subtle.

- [ ] **Step 3: Move `FileDetailView` to the same workspace shell and panel hierarchy**

Change the root wrapper:

```vue
<div class="ui-page-shell-wide">
  <PageHeader :title="file?.filename ?? '文件详情'" subtitle="处理状态与数据预览">
```

Then replace the three primary blocks with semantic panels:

```vue
<div class="ui-panel p-4 mb-4 flex flex-wrap items-center gap-4">...</div>
<div class="ui-panel p-4 mb-4">...</div>
<div class="ui-panel p-4">...</div>
```

Inside the structured extraction and chunk list tabs, replace raw bordered boxes with `ui-panel-muted`:

```vue
<div class="ui-panel-muted p-3">...</div>
```

- [ ] **Step 4: Run typecheck**

```bash
cd packages/web && pnpm typecheck
```

Expected: PASS.

- [ ] **Step 5: Manual verify resource flows**

Check `/resource` and `/resource/<existing-id>`:
- folder tree and table feel like one system
- upload zone is visible but not visually loud
- detail tabs and pipeline section feel lighter than before
- delete / refresh buttons remain readable in all themes

- [ ] **Step 6: Commit**

```bash
git add packages/web/src/views/resource/ResourceLibraryView.vue packages/web/src/views/resource/FileDetailView.vue
git commit -m "refactor(web): migrate resource workspace views to semantic panels"
```

---

## Task 7: Migrate the database workspace

**Files:**
- Modify: `packages/web/src/views/database/DatabaseView.vue`

- [ ] **Step 1: Move the page root onto the wide shell**

Replace the root wrapper:

```vue
<div class="ui-page-shell-wide">
  <PageHeader title="数据库" subtitle="数据集管理与知识图谱构建">
    <template #extra>
      <button class="liquid-btn liquid-btn-primary px-3 py-1.5 flex items-center gap-1.5" @click="showUpload = true">
        <Upload :size="14" /> 上传数据集
      </button>
    </template>
  </PageHeader>
```

- [ ] **Step 2: Convert the left dataset column and right detail area to the shared panel system**

Change the major blocks:

```vue
<div class="w-[260px] shrink-0 flex flex-col gap-2" style="max-height: calc(100vh - 80px)">
  <div class="ui-panel flex flex-col overflow-hidden" style="flex: 1; min-height: 0">...</div>
  <button class="ui-panel px-3 py-2.5 flex items-center justify-between ui-interactive-row cursor-pointer">...</button>
</div>
```

```vue
<div class="flex-1 min-w-0">
  <div class="ui-panel p-4">...</div>
</div>
```

For the dataset meta bar, pipeline status block, and tabs block, keep the existing structure but switch all top-level `liquid-card` containers to `ui-panel`.

- [ ] **Step 3: Reduce visual noise in the dataset list and pipeline steps**

Apply these replacements:

```vue
:class="!showKgOverview && selectedId === ds.id
  ? 'bg-[var(--interactive-active-bg)] text-[var(--color-accent)]'
  : 'hover:bg-[var(--interactive-hover-bg)] text-[var(--color-ink-secondary)]'"
```

And for pipeline steps, use muted panels instead of freestanding colored blocks where possible:

```vue
class="flex-1 ui-panel-muted flex flex-col items-center gap-1.5 py-2 px-1"
```

Keep status text color differences, but stop relying on large filled backgrounds.

- [ ] **Step 4: Run typecheck**

```bash
cd packages/web && pnpm typecheck
```

Expected: PASS.

- [ ] **Step 5: Manual verify database workspace**

Check `/database`:
- left list, KG overview trigger, and right detail panel now read as the same workspace family
- tab strip still works
- pipeline progress remains legible without heavy color blocks
- layout remains stable in all four themes

- [ ] **Step 6: Commit**

```bash
git add packages/web/src/views/database/DatabaseView.vue
git commit -m "refactor(web): migrate database view to shared workspace layout"
```

---

## Task 8: Migrate the AI chat workspace

**Files:**
- Modify: `packages/web/src/views/ai-chat/AiChatView.vue`

- [ ] **Step 1: Replace decorative header treatment with the shared page shell**

Change the top-level template from a bespoke header to a shell with a standard header block:

```vue
<template>
  <div class="ui-page-shell-wide flex flex-col h-screen">
    <PageHeader title="AI 问答" subtitle="基于知识库的智能问答与内容溯源" />

    <div ref="chatContainer" class="flex-1 overflow-y-auto space-y-4 ui-panel p-4">
      ...
    </div>

    <div class="ui-page-section">
      <form @submit.prevent="sendMessage" class="ui-toolbar items-end">
        ...
      </form>
    </div>
  </div>
</template>
```

Add the missing import:

```ts
import PageHeader from "@/components/PageHeader.vue";
```

- [ ] **Step 2: Soften message and quick-question surfaces**

Replace the assistant bubble and quick question cards:

```vue
class="ui-panel max-w-[60%] px-4 py-3 text-[var(--text-body)] leading-relaxed markdown-body"
```

```vue
class="text-left p-3 ui-panel ui-interactive-row text-[var(--color-ink-secondary)] hover:text-[var(--color-ink)]"
```

Update the input shell:

```vue
<div class="flex-1 ui-panel-muted px-4 py-2.5 flex items-center transition-all duration-200 focus-within:border-[var(--color-accent)] focus-within:shadow-[0_0_0_2px_var(--focus-ring)]">
```

- [ ] **Step 3: Run typecheck**

```bash
cd packages/web && pnpm typecheck
```

Expected: PASS.

- [ ] **Step 4: Manual verify chat workspace**

Check `/ai-chat`:
- header matches the rest of the app
- quick-question cards feel like lightweight options, not feature tiles
- assistant/user bubbles remain readable and visually distinct
- input area focus ring and submit/stop buttons still feel clear

- [ ] **Step 5: Commit**

```bash
git add packages/web/src/views/ai-chat/AiChatView.vue
git commit -m "refactor(web): migrate ai chat view to semantic workspace shell"
```

---

## Task 9: Migrate the empty admin and skill pages

**Files:**
- Modify: `packages/web/src/views/admin/AdminView.vue`
- Modify: `packages/web/src/views/skill/SkillEditorView.vue`

- [ ] **Step 1: Move both placeholder pages to the semantic shell**

Use the same root pattern in both files:

```vue
<template>
  <div class="ui-page-shell">
    <PageHeader title="系统管理" subtitle="用户、权限与租户管理" />
    <div class="ui-panel">
      <EmptyState title="即将上线" hint="系统管理功能正在开发中，敬请期待" />
    </div>
  </div>
</template>
```

```vue
<template>
  <div class="ui-page-shell">
    <PageHeader title="技能编排" subtitle="Skill 可视化编排与工作流设计" />
    <div class="ui-panel">
      <EmptyState title="即将上线" hint="Skill 可视化编排功能正在开发中，敬请期待" />
    </div>
  </div>
</template>
```

- [ ] **Step 2: Run typecheck**

```bash
cd packages/web && pnpm typecheck
```

Expected: PASS.

- [ ] **Step 3: Manual verify placeholder pages**

Check `/admin` and `/skill-editor`:
- both pages now look like real pages inside the same system
- empty states no longer float against bare page background

- [ ] **Step 4: Commit**

```bash
git add packages/web/src/views/admin/AdminView.vue packages/web/src/views/skill/SkillEditorView.vue
git commit -m "refactor(web): align placeholder pages with workspace shell"
```

---

## Task 10: Final sweep, theme QA, and documentation sync check

**Files:**
- Modify: `packages/web/src/assets/css/main.css` (only if final token tweaks are required)
- Modify: any of the migrated views above (only if defects are found)

- [ ] **Step 1: Run the full frontend checks**

```bash
cd packages/web && pnpm typecheck && pnpm build
```

Expected: PASS.

- [ ] **Step 2: Run the manual multi-theme QA sweep**

Start the app if needed:

```bash
./dev.sh frontend
```

Verify these routes in `liquid`, `ink`, `navy`, and `notion` themes:

```text
/
/knowledge
/resource
/resource/<existing-id>
/database
/ai-chat
/admin
/skill-editor
```

For each route, confirm:
- the right-side background stays calm
- panels read as information containers, not decorated cards
- hover/focus behavior is subtle and consistent
- accent is not overused
- spacing rhythm is shared across pages
- no visual regression from theme switching

- [ ] **Step 3: Check whether docs need updates**

Per `.claude/rules/docs.md`, pure frontend UI changes with no API/schema impact do not require `ARCHITECTURE.md` changes. Confirm that this refactor did not alter:

```text
API endpoints
router structure
DB schema
shared constants outside visual styling
```

Expected: no docs update required.

- [ ] **Step 4: Commit the final QA fixes**

```bash
git add packages/web/src/assets/css/main.css \
  packages/web/src/views/LayoutView.vue \
  packages/web/src/components/PageHeader.vue \
  packages/web/src/components/EmptyState.vue \
  packages/web/src/views/HomeView.vue \
  packages/web/src/views/knowledge/KnowledgeBaseView.vue \
  packages/web/src/views/resource/ResourceLibraryView.vue \
  packages/web/src/views/resource/FileDetailView.vue \
  packages/web/src/views/database/DatabaseView.vue \
  packages/web/src/views/ai-chat/AiChatView.vue \
  packages/web/src/views/admin/AdminView.vue \
  packages/web/src/views/skill/SkillEditorView.vue

git commit -m "refactor(web): unify right-side workspace across themes"
```

---

## Risk Controls

### 1. Token abstraction risk

Do **not** delete old `liquid-*` classes immediately. Keep them as compatibility aliases backed by the new semantic token system until all major pages are migrated.

### 2. Theme drift risk

If one theme needs unique behavior, add or adjust a semantic token first. Only add theme-specific class overrides when a token cannot express the difference.

### 3. Page migration risk

When changing a page, first convert top-level shell and panels. Only then reduce local accent density and hover behavior. Do not mix shell migration with unrelated markup rewrites.

### 4. Regression risk

After every task, recheck at least `/` and the page just changed in all four themes before moving on.

---

## Spec Coverage Check

This plan covers the spec requirements for:
- unified right-side content shell
- semantic token abstraction
- calmer backgrounds and panels
- weaker theme variance with shared skeleton
- baseline page migration via `HomeView.vue`
- incremental migration of knowledge, resource, database, AI chat, admin, and skill pages
- verification and maintenance safeguards

No spec sections are intentionally deferred.

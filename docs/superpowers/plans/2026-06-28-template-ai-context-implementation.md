# Template AI Context Implementation Plan

> **For agent workers:** Use executing-plans skill to implement task-by-task with checkpoints.

**Goal:** Add `ai_context` field to templates so users can inject domain expert context into AI field generation prompts.

**Architecture:** Three-layer: DTO model (no schema change), service layer (prompt injection), frontend (textarea binding).

**Tech Stack:** FastAPI/Pydantic backend, Vue 3 + TypeScript frontend.

---

## File Map

| File | Change |
|------|---------|
| `packages/server-python/app/contexts/template/application/dto.py` | Add `ai_context: str \| None` to Create/Update/Response |
| `packages/server-python/app/contexts/template/application/service.py` | Pass `ai_context` to `_call_llm` prompt |
| `packages/server-python/app/contexts/template/domain/entity.py` | Add `ai_context` field |
| `packages/server-python/app/contexts/template/infrastructure/repository.py` | Map `ai_context` in ORM |
| `packages/web/src/services/template.ts` | Add `ai_context` to API interface |
| `packages/web/src/views/admin/TemplateEditorView.vue` | Add textarea for `ai_context` |
| `packages/web/src/views/admin/TemplateModal.vue` | Pass `ai_context` through form, wire to API |

---

## Backend Tasks

### Task 1: Add `ai_context` to Template DTOs

**Files:**
- Modify: `packages/server-python/app/contexts/template/application/dto.py`

- [ ] **Step 1: Add `ai_context` to Create/Update/Response**

In `TemplateCreate`, `TemplateUpdate`, `TemplateResponse`, add:
```python
ai_context: str | None = None
```

---

### Task 2: Add `ai_context` to Template entity

**Files:**
- Modify: `packages/server-python/app/contexts/template/domain/entity.py`

- [ ] **Step 1: Add `ai_context` to Template dataclass**

Add `ai_context: str | None = None` to the `Template` dataclass fields.

---

### Task 3: Wire `ai_context` into ORM repository

**Files:**
- Modify: `packages/server-python/app/contexts/template/infrastructure/repository.py`

- [ ] **Step 1: Map `ai_context` in create/update**

In `create()` and `_to_entity()` / `_to_dict()`, include `ai_context` mapping.

---

### Task 4: Inject `ai_context` into LLM prompt

**Files:**
- Modify: `packages/server-python/app/contexts/template/application/service.py`

- [ ] **Step 1: Append `ai_context` to system prompt in `init_by_ai`

If `template.ai_context` is non-null, append to system prompt:
```
追加上下文：" + template.ai_context
```

---

## Frontend Tasks

### Task 5: Add `ai_context` to template API service

**Files:**
- Modify: `packages/web/src/services/template.ts`

- [ ] **Step 1: Add `ai_context` to Template interface and API calls**

```typescript
export interface Template {
  // ... existing fields ...
  ai_context?: string;
}
```

---

### Task 6: Add `ai_context` textarea to TemplateEditorView

**Files:**
- Modify: `packages/web/src/views/admin/TemplateEditorView.vue`

- [ ] **Step 1: Add textarea in AI context area**

Below existing AI prompt area, add a textarea for `form.ai_context` with placeholder: `"补充说明（可选）——如：课程标准模板需包含前置能力与知识基础"`.

---

### Task 7: Wire `ai_context` in TemplateModal

**Files:**
- Modify: `packages/web/src/views/admin/TemplateModal.vue`

- [ ] **Step 1: Pass `ai_context` through form and template API

Add `ai_context` to the form reactive object and ensure it serializes in create/update API calls.

---

## Verification

- [ ] `make test` — all 81 tests pass
- [ ] `npx vue-tsc --noEmit` — no TypeScript errors
- [ ] Create a template with ai_context="护理模板需重点关注生命体征测量"，call AI generate, confirm fields reflect the context

# REQ-002-2 模板复用机制（同租户复制 + 版本快照 + JSON 导入导出） — Spec

> Spec 入口：REQ-002-2（REQ-002 子任务链 #2，复用机制）。本文件是验收口径与边界的事实源；实施拆分见 `docs/02-delivery-plans/02-plans/2026-06-10-req-002-2-template-reuse-plan.md`。
> Parent：[REQ-002 决策记录 Q1 + Q2 + 范围段「复用机制」](../../01-product-planning/05-requirements/REQ-002-template-config-and-reuse.md#决策记录2026-06-10-塑形澄清)（"P1 仅同租户复制 + 全量保留版本 + JSON 导入导出"）。

## 目标

让模板能跨时间 / 跨实例 / 跨实例拷贝复用，覆盖模板维护者"上学期模板拷到下学期"、跨实例备份迁移、跨人协作等场景。

决策来源（REQ-002 塑形期 2026-06-10 决议 Q1 + Q2）：

> **Q1**：复用范围：P1 仅同租户复制；跨租户 P2 起再议。
> **Q2**：版本快照：全量保留 + 分页，不做超限清理。

变更前：模板只能 CRUD（创建 / 更新 / 删除）+ AI 初始化（`init-by-ai`），无复制、无版本、无导入导出。
变更后：3 项复用能力到位 — **同租户复制**（POST `/api/v1/templates/{id}/clone`）+ **版本快照**（每次 update 写一条 `template_versions` 记录）+ **JSON 导入导出**（GET `/api/v1/templates/{id}/export` + POST `/api/v1/templates/import`）。

## 范围

### 包含

- **后端 — 同租户复制（Q1）**：
  - 新增 `POST /api/v1/templates/{template_id}/clone` 端点：
    - 入参：`{"name": str, "doc_types": list[str], "source_file_id": str | None}`；新模板继承 `fields` 嵌套结构 + `ai_context` + `ai_prompt`。
    - 出参：完整 `TemplateResponse`（新 `id`，新 `created_at` / `updated_at`，新 `schema_version`（REQ-002-4 未完成则为 1））。
    - 行为：必须在**同一 tenant_id** 内复制（Q1 决议）；不复制 `source_file_id`（除非新模板显式传入）；fields 嵌套结构深拷贝（同 `REQ-002-1` 子树深拷贝算法）。
    - 权限：复用现有 `get_current_user` 认证；不引入跨租户权限模型（Q1 决议）。
  - 新增 `TemplateService.clone(template_id, dto, tenant_id) -> dict` 方法。
  - 新增 `template_repo.get(template_id, tenant_id)`（已存在）+ `template_repo.create(template)`（已存在）复用，不新建 repo 方法。

- **后端 — 版本快照（Q2）**：
  - 新建 `template_versions` 表，字段：`id` (UUID) / `template_id` (UUID, FK) / `tenant_id` (UUID) / `version_number` (int, 自增，从 1 开始) / `name` (str) / `doc_types` (list[str]) / `fields` (JSONB) / `ai_prompt` (str | None) / `ai_context` (str | None) / `schema_version` (int) / `snapshot_at` (datetime)。
  - 新建 Alembic 迁移：`alembic/versions/YYYYMMDDHHMM_create_template_versions.py`。
  - 触发时机：`TemplateService.update` 成功后在同一事务中写入 `template_versions` 一条记录（Q2 决议"全量保留"，不做超限清理）。
  - 列出版本：`GET /api/v1/templates/{template_id}/versions?limit=20&offset=0`（分页，Q2 决议"分页"）。
  - 版本详情：`GET /api/v1/templates/{template_id}/versions/{version_number}`。
  - 回滚版本：`POST /api/v1/templates/{template_id}/rollback/{version_number}`（按 snapshot 内容覆盖 template，并写一条新的 `template_versions` 记录）。

- **后端 — JSON 导入导出（Q3 补充，按 REQ-002 范围段）**：
  - 导出：`GET /api/v1/templates/{template_id}/export` 返回 `{"format": "metaedu-template-v1", "template": {...}, "schema_version": int}`，Content-Type `application/json`。
  - 导入：`POST /api/v1/templates/import` 入参 `{"template": {...}, "name_override": str | None}`：
    - 校验 `format == "metaedu-template-v1"`，否则 400。
    - 校验 `template.fields` 嵌套结构合法（key 唯一、key 匹配 `^[a-z][a-z0-9_]*$`）；如不合法返回 422 + 详细错误。
    - 不导入 `id` / `tenant_id` / `created_at` / `updated_at`；生成新 id 与 tenant_id（取当前用户）。
    - 不导入 `source_file_id`（避免跨租户文件引用）。
    - 校验 `schema_version` 与当前 schema 兼容性（导入 `schema_version` 更高时 warning 但允许导入；导入 `schema_version` 更低时拒绝并提示用户升级 template）。

- **前端 — 复制按钮 + 复制弹窗**：
  - 在 TemplateListView 卡片右上角新增"复制"按钮（与"删除"按钮并列），点击后弹出"复制模板"对话框：输入新模板 name + 选择 doc_types（默认继承原模板 doc_types，可增删）+ 可选 source_file_id（默认无）。
  - 提交后调用 `templateApi.clone(id, { name, doc_types, source_file_id })`，成功后 toast + 跳转到新模板编辑页。

- **前端 — 版本列表 + 回滚按钮**：
  - 在 TemplateEditorView 顶部新增"版本历史"按钮（仅当 `templates.id` 存在且不在新建模式时显示），点击后展开版本列表（按 `version_number` 倒序，limit 20）。
  - 每个版本显示：`v{n} · {snapshot_at} · {name}` + "回滚到此版本"按钮。
  - 点击回滚后弹确认框；确认后调用 `templateApi.rollback(id, version_number)`，成功后刷新当前页面 + toast。

- **前端 — JSON 导入导出**：
  - 在 TemplateListView 顶部新增"导入模板"按钮，点击后弹出文件选择对话框（接受 `.json` 文件）；选中后调用 `templateApi.import(file)`，成功后 toast + 跳转到新模板编辑页。
  - 在 TemplateEditorView 顶部"保存"按钮旁新增"导出 JSON"按钮，点击后调用 `templateApi.export(id)` 下载 JSON 文件（文件名 `<template_name>_<YYYYMMDDHHMM>.json`）。

- **测试**：
  - 后端：`tests/contexts/template/test_template_reuse.py` 新增 ≥6 条用例（clone / 列出 versions / 滚动版本 / 导入校验失败 / 跨租户拒绝 / 导出导入 round-trip）。
  - 前端：至少 1 条手测记录或 e2e 覆盖"复制按钮 → 输入新 name → 提交 → 跳转新模板"完整流程。

- **文档回填**：
  - P2 里程碑 Open Items 加 REQ-002-2 行。
  - Backlog REQ-002-2 状态推进。
  - current-work.md 把 REQ-002-2 移入"当前进行中"。
  - work-log.md 单行索引（待 Done 时回填）。

### 不包含

- **不**做跨租户复制（Q1 决议：P1 仅同租户；跨租户 P2 起再议）。
- **不**做权限分级 / 审计约束（Q1 决议：现有登录 + 租户隔离即满足 P1 / P2 需求）。
- **不**做超限清理 / 自动归档（Q2 决议：全量保留 + 分页）。
- **不**做 version 比较（diff UI）/ version tag（v1.0.0 语义版本）/ version 注释（commit message 风格）。
- **不**做批量复制（一次复制多个 template）；单次复制 1 个。
- **不**做模板市场 / 公开模板 / 模板评分。
- **不**改 `select_template` / 模板匹配优先级 / L3 阈值 / extract_template 行为（REQ-002-3 contract 已落盘 `{id, version, layer, ...data}`，本任务不破坏）。
- **不**改 schema_version 自增逻辑（REQ-002-4 处理）；本任务**读取** `template_obj.schema_version`，缺失则视为 1（兜底）。
- **不**做模板字段拖拽排序 / 子树复制 / 撤销 / 大模板浏览（REQ-002-1 处理）。
- **不**做 deprecated 标记 / 容器互转二次确认（REQ-002-4 处理）。
- **不**做 RAG / KG / 文档解析上下文的协同改动（保持模板上下文自治）。

## 验收标准

| ID | 验收点 | 通过条件 | 失败条件 |
|----|--------|----------|----------|
| AC-1 | 同租户复制 API 行为 | `POST /api/v1/templates/{id}/clone` 入参 `{"name": "新模板", "doc_types": ["教案"], "source_file_id": null}`，返回 201 + 新 `TemplateResponse`；新模板 `id` ≠ 原 `id`；`fields` 嵌套结构与原模板逐字段相等（深拷贝验证：`is not` 但 `to_dict()` 等价）；`tenant_id` 等于当前用户 tenant。 | 复制后 id 相同 / fields 共享引用 / tenant_id 错 |
| AC-2 | 跨租户复制拒绝 | 用 tenant A 创建的 template，用 tenant B 的 auth header 调用 `POST /api/v1/templates/{id}/clone` 返回 404（不应暴露 template 存在性）。 | 返回 200 / 返回 500 / 暴露 tenant 边界 |
| AC-3 | version 表结构与触发 | `template_versions` 表存在；`TemplateService.update` 成功调用一次后，`template_versions` 多一条记录，`version_number` 自增 1，`fields` / `ai_context` / `schema_version` 与 update 时的 template 一致。 | version 表未创建 / update 后未写 version / version_number 不连续 |
| AC-4 | 列出 versions 分页 | `GET /api/v1/templates/{id}/versions?limit=20&offset=0` 返回 `[{version_number, snapshot_at, name, ...}, ...]`，按 `version_number` 倒序；连续创建 25 次 update 后，limit=10 返回前 10 条，offset=10 返回下 10 条，offset=20 返回最后 5 条。 | 分页错乱 / 不按倒序 / offset 越界 500 |
| AC-5 | 回滚 version | `POST /api/v1/templates/{id}/rollback/{version_number=2}` 返回 200 + template 当前 `fields` 等于 v2 snapshot 时的 `fields`；template 的 `updated_at` 更新；`template_versions` 多一条 v6 记录（v5 → v6 累计）。 | rollback 后 fields 错 / updated_at 未更新 / 未写新 version |
| AC-6 | JSON 导出形状 | `GET /api/v1/templates/{id}/export` 返回 `{"format": "metaedu-template-v1", "template": {...}, "schema_version": 1, "exported_at": ISO8601}`；Content-Type `application/json`；`template.fields` 是嵌套数组。 | format 字段缺失 / template 字段错 / Content-Type 错 |
| AC-7 | JSON 导入 round-trip | 用 AC-6 导出 → 用 `POST /api/v1/templates/import` 入参 `{"template": <exported>}` 返回 201 + 新 TemplateResponse；新 template `fields` 与导出原 template `fields` 逐字段相等（`is not`）；新 template `id` ≠ 导出原 template `id`；`tenant_id` = 当前用户 tenant。 | 导入后 fields 共享引用 / id 相同 / tenant_id 错 |
| AC-8 | 导入 schema_version 兼容性 | 导出 `schema_version=2` 的 template（mock），导入时服务端 schema 仍为 `schema_version=1`，导入返回 200 + warning header（`X-Import-Warning: schema_version mismatch, imported=2, current=1`）。导入 `schema_version=0`（低于当前）返回 422 + 错误消息"无法导入旧版 schema 模板，请升级 schema"。 | schema 兼容性未校验 / warning header 缺失 / 低版本导入成功 |
| AC-9 | 导入字段名规范校验 | 导入 template 含 `field.key = "Invalid-Key"`（含大写 / 连字符）时，返回 422 + 详细错误"field key must match ^[a-z][a-z0-9_]*$"。 | 未校验 / 校验失败仍导入 |
| AC-10 | 导入同层 key 重复 | 导入 template 在同一层有重复 `field.key` 时，返回 422 + 详细错误"sibling field keys must be unique"。 | 未校验 / 校验失败仍导入 |
| AC-11 | 前端复制按钮 + 弹窗 | TemplateListView 每张卡片新增"复制"图标按钮（与"删除"并列）；点击后弹出"复制模板"对话框：name 输入框 + doc_types 多选 + source_file_id 可选 + "确认复制" / "取消"按钮。 | 按钮缺失 / 弹窗字段缺失 / 取消按钮无效 |
| AC-12 | 前端复制提交 + 跳转 | 在弹窗输入新 name + 选 doc_types 后点击"确认复制"，调用 `templateApi.clone(id, payload)`；成功 toast "复制成功"，自动跳转到 `/admin/template/<new_id>` 编辑页。 | 调用失败 / toast 缺失 / 跳转 URL 错 |
| AC-13 | 前端版本历史按钮 + 列表 | TemplateEditorView 顶部新增"版本历史"按钮（仅编辑模式显示）；点击后展开版本列表（按 version_number 倒序，limit 20）；每条显示 `v{n} · {snapshot_at relative} · {name}`。 | 按钮缺失 / 列表顺序错 / 限制 20 缺失 |
| AC-14 | 前端回滚按钮 | 版本列表每条右侧"回滚到此版本"按钮；点击后弹确认框"确认回滚到 v{n}？当前未保存修改将丢失"；确认后调用 `templateApi.rollback(id, n)`；成功 toast + 刷新页面。 | 按钮缺失 / 确认框缺失 / 刷新失败 |
| AC-15 | 前端导入按钮 + 解析 | TemplateListView 顶部"导入模板"按钮，点击弹出文件选择（accept `.json`）；选中后解析 JSON 并调用 `templateApi.import(payload)`；失败（422 / 400）toast 详细错误。 | 按钮缺失 / accept 缺失 / 解析失败未处理 |
| AC-16 | 前端导出按钮 + 下载 | TemplateEditorView 顶部"导出 JSON"按钮，点击后调用 `templateApi.export(id)` 触发浏览器下载 `<template_name>_<YYYYMMDDHHMM>.json`。 | 按钮缺失 / 文件名错 / 下载失败 |
| AC-17 | 不破坏 REQ-002-3 溯源 contract | clone / version / export / import 操作均**不**修改 `structured_data["template"]` 落盘 shape；REQ-002-3 已落盘的 `{id, version, layer, ...data}` contract 完全保持。 | 复制后 trace_id 错乱 / version 操作破坏 contract |
| AC-18 | 不破坏 REQ-002-1 配置 UX | 复制 / 导入的 template 进入编辑页后，拖拽 / 复制子树 / 撤销 / 搜索功能正常工作（前提：REQ-002-1 已合并；本任务不依赖，但需在 PR 描述中验证）。 | 复制 / 导入 template 后编辑页崩溃 / 拖拽失效 |
| AC-19 | API 契约同步 | 新增 5 个端点 + 2 个 DTO（CloneTemplateRequest / ImportTemplateRequest）+ 1 个 entity（TemplateVersion）均按 FastAPI + Pydantic 模式；不在 DTO 中混入 `id` / `tenant_id` / `created_at` / `updated_at`（由服务端生成）。 | DTO 含敏感字段 / 端点缺失 / 端点路径错 |
| AC-20 | DB 迁移可复现 | 新增 Alembic 迁移 `alembic/versions/YYYYMMDDHHMM_create_template_versions.py`；`make migrate` 升级成功；`make migrate-downgrade` 回退成功；既有迁移不受影响。 | 迁移失败 / downgrade 失败 / 既有迁移被破坏 |
| AC-21 | 后端 pytest 通过 | `cd packages/server-python && .venv/bin/python -m pytest tests/contexts/template tests/contexts/document -q` 全部通过；`test_template_reuse.py` ≥6 条新用例全过。 | 任一失败 / 新用例缺失 |
| AC-22 | 前端 typecheck + lint | `cd packages/web && pnpm typecheck` 退出码 0；`pnpm lint` 退出码 0。 | 退出码非 0 |
| AC-23 | UI 回归 | 至少 1 条手测记录或 e2e 覆盖"复制按钮 → 输入新 name → 提交 → 跳转新模板 → 编辑 → 保存"完整流程；记录在 PR 描述中。 | 缺手测记录 / e2e 失败 |
| AC-24 | 工程门禁 | `python3 scripts/check-engineering-docs` 退出码 0；`git diff --check` 干净。 | 退出码非 0 |
| AC-25 | 文档回填 | P2 里程碑 Open Items 加 REQ-002-2 行；Backlog REQ-002-2 状态推进；current-work.md 把 REQ-002-2 移入"当前进行中"。 | 任一事实源未同步 |

## 接口与依赖

新增端点：

- `POST /api/v1/templates/{template_id}/clone`（Q1 决议：同租户）
- `GET /api/v1/templates/{template_id}/versions?limit=20&offset=0`（Q2 决议：分页）
- `GET /api/v1/templates/{template_id}/versions/{version_number}`
- `POST /api/v1/templates/{template_id}/rollback/{version_number}`
- `GET /api/v1/templates/{template_id}/export`
- `POST /api/v1/templates/import`

新增 entity / DTO / 端点对应文件（**业务代码改动**）：

- 新增：`packages/server-python/app/contexts/template/domain/template_version.py`（`TemplateVersion` dataclass）
- 新增：`packages/server-python/app/contexts/template/infrastructure/models.py`（追加 `TemplateVersionModel`）
- 新增：`packages/server-python/app/contexts/template/infrastructure/template_version_repository.py`（`TemplateVersionRepository` + `TemplateVersionRepositoryImpl`）
- 修改：`packages/server-python/app/contexts/template/application/dto.py`（追加 `CloneTemplateRequest` / `ImportTemplateRequest` / `TemplateVersionResponse` / `TemplateExportResponse`）
- 修改：`packages/server-python/app/contexts/template/application/service.py`（追加 `clone` / `list_versions` / `get_version` / `rollback` / `export_template` / `import_template` 方法；`update` 内追加 version 快照逻辑）
- 修改：`packages/server-python/app/contexts/template/interfaces/api/router.py`（追加 6 个端点）
- 新增：`packages/server-python/alembic/versions/YYYYMMDDHHMM_create_template_versions.py`（Alembic 迁移）
- 新增：`packages/server-python/tests/contexts/template/test_template_reuse.py`（≥6 条新用例）

前端修改：

- 修改：`packages/web/src/services/template.ts`（追加 `clone` / `listVersions` / `getVersion` / `rollback` / `export` / `import` API 调用 + 类型）
- 修改：`packages/web/src/views/admin/TemplateListView.vue`（新增"复制"按钮 + 复制弹窗 + "导入模板"按钮）
- 修改：`packages/web/src/views/admin/TemplateEditorView.vue`（新增"版本历史"按钮 + 版本列表 + "导出 JSON"按钮）
- 新增：`packages/web/src/components/CloneTemplateDialog.vue`（复制弹窗组件）
- 新增：`packages/web/src/components/VersionHistoryPanel.vue`（版本历史组件）
- 新增：`packages/web/src/components/ImportTemplateDialog.vue`（导入弹窗组件）

文档改动：

- `docs/01-product-planning/02-milestones/02-growth-phase.md`
- `docs/01-product-planning/04-backlog.md`
- `docs/03-engineering-governance/current-work.md`

## 文件计划

业务代码改动（后端 6 个新文件 + 3 个修改 + 前端 3 个新组件 + 2 个修改）：

后端：

- 新建 `template_version.py` / `template_version_repository.py` / Alembic 迁移
- 修改 `models.py` / `dto.py` / `service.py` / `router.py`

前端：

- 新建 `CloneTemplateDialog.vue` / `VersionHistoryPanel.vue` / `ImportTemplateDialog.vue`
- 修改 `template.ts` / `TemplateListView.vue` / `TemplateEditorView.vue`

测试：

- 新建 `test_template_reuse.py`（≥6 条新用例）

文档：

- 3 个事实源同步

## 风险与边界

1. **深拷贝 fields 的性能**：30 字段 + 3 层嵌套的 template，深拷贝 ≈ O(N) 复制列表 + 字典对象，单次 < 1ms；可接受。
2. **template_versions 表膨胀**：按 Q2 决议"全量保留 + 分页"，1 个 template 修改 1000 次会产生 1000 条 version；30 个活跃 template × 1000 = 30000 条；JSONB 字段每条 ≈ 10KB → 总计 ≈ 300MB；可接受，但需要监控。后续若需要清理可作为独立 follow-up。
3. **跨 tenant 复制的拒绝方式**：AC-2 要求返回 404 而非 403，避免泄露 template 存在性；按现有 `template_repo.get(id, tenant_id)` 实现自然支持（找不到返回 None → 404）。
4. **JSON 导入的 schema_version 兼容性**：AC-8 描述当前行为（导入更高 → warning，更低 → 拒绝）；REQ-002-4 schema 演进规则生效后，本任务的 AC-8 仍按现有 schema 兼容；不需要再改。
5. **rollback 时的并发**：两个客户端同时回滚可能产生版本号竞争；当前 `template_versions.version_number` 自增依赖 DB sequence（Alembic 默认），并发场景下由 DB 保证唯一性。
6. **version snapshot 的事务一致性**：`update` + `insert into template_versions` 必须在同一事务；如失败整体回滚，避免 version 记录与 template 不一致。`service.update` 当前用 `session.flush()` + `session.commit()`，需确保 version insert 也在同一 commit 边界内。
7. **导入时 tenant_id 覆盖**：服务端强制使用当前用户 tenant_id，忽略 payload 中 `tenant_id` 字段，避免跨租户注入。
8. **file.download 的浏览器兼容性**：使用 `URL.createObjectURL(blob)` + `<a download="...">` 触发下载；兼容主流浏览器；Safari 需测试。
9. **依赖顺序**：本任务**依赖** REQ-002-3 已合并（contract 基线）+ REQ-002-1 已合并（前端 UX 集成）；**被依赖**：无（REQ-002-4 schema 演进是独立的，本任务读取但不修改 schema_version）。

## 行为变化声明

| 项 | 变化 |
|----|------|
| 新增端点 | 6 个（clone / list versions / get version / rollback / export / import） |
| 新增表 | `template_versions`（1 张） |
| 新增 DTO | 3 个（CloneTemplateRequest / ImportTemplateRequest / TemplateVersionResponse / TemplateExportResponse） |
| `TemplateService.update` 行为 | 成功后追加一次 `template_versions` 插入（同一事务） |
| 前端 TemplateListView | 新增复制按钮 + 复制弹窗 + 导入模板按钮 |
| 前端 TemplateEditorView | 新增版本历史按钮 + 版本列表 + 导出 JSON 按钮 |
| API 契约 | 新增端点 + 新增 DTO；既有端点 + DTO 不变 |
| DB schema | 新增 `template_versions` 表；既有表 schema 不变 |
| REQ-002-3 落盘 contract | 不影响 |
| REQ-002-1 编辑器 UX | 不影响（前提：REQ-002-1 已合并） |
| 模板匹配 / 抽取 / RAG / KG | 全部不变 |

## 依赖与执行顺序

- **强依赖**：REQ-002-3 已合并（`{id, version, layer, ...data}` contract 是 clone / rollback / export 的基础）。
- **弱依赖**：REQ-002-1 已合并（复制 / 导入后的 template 进入编辑页应能正常使用 REQ-002-1 UX；本任务不强制，但应在 PR 描述验证）。
- 与 TD-009（shared schema gate）相关：`TemplateVersionResponse` 需要在 frontend 类型中保持一致；不破坏现有 `Template` interface。
- 与 TD-029（shared schema）相关：`FileDTO.structured_data` 不变；本任务不动 schema 文件。
- 与 TD-030（RecallChannel Protocol）无关：本任务不动 knowledge / rag 上下文。
- 与 TD-032（large source files）相关：本任务新增后端 ~3 个文件 + 前端 3 个组件；每个文件应 < 800 行；提交后跑 `scripts/scan-source-sizes --diff` 确认。
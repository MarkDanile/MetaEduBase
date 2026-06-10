# REQ-002-4 模板可维护性（schema_version 演进 + 容器互转二次确认 + deprecated + 命名规范） — Spec

> Spec 入口：REQ-002-4（REQ-002 子任务链 #4，可维护性）。本文件是验收口径与边界的事实源；实施拆分见 `docs/02-delivery-plans/02-plans/2026-06-10-req-002-4-template-maintainability-plan.md`。
> Parent：[REQ-002 决策记录 Q4 + Q6 + 范围段「可维护性」](../../01-product-planning/05-requirements/REQ-002-template-config-and-reuse.md#决策记录2026-06-10-塑形澄清)（"schema_version 递增 + 二次确认 + deprecated + 命名规范"）。

## 目标

让模板在长期演进中保持可控、可追溯、可告警：当模板定义发生破坏性变更时显式提升 `schema_version` + UI 二次确认；老模板可标记 deprecated 避免被新文档误命中；新模板必须通过字段命名规范校验。

决策来源（REQ-002 塑形期 2026-06-10 决议 Q4 + Q6）：

> **Q4**：字段填充率定义与统计窗口（与可维护性交叉）：字段命名规范校验 `key` 必须是 `^[a-z][a-z0-9_]*$`，禁止与已有字段 key 重复（同一层），避免抽取后端解析失败。
> **Q6**：schema 演进约束：text/textarea/number 内可改（schema_version 不递增）；object/table/array 互转 + 删除字段 + 修改叶子 key：必须 `schema_version += 1` + UI 二次确认。

变更前：模板 CRUD 无 schema_version 概念，字段类型变化无校验，废弃模板无法标记，新模板字段命名无规范。
变更后：4 项可维护性能力到位 — **schema_version 字段 + 自增逻辑**、**容器互转二次确认**、**deprecated 标记**、**字段命名规范校验**（包含 REQ-002-3 的保留键冲突校验）。

## 范围

### 包含

- **后端 — schema_version 字段**：
  - 在 `templates` 表新增 `schema_version` 字段（int，NOT NULL，默认 1）。
  - 在 `templates` 表新增 `is_deprecated` 字段（boolean，NOT NULL，默认 false）。
  - 在 `templates` 表新增 `deprecated_at` 字段（datetime，nullable）。
  - 在 `templates` 表新增 `deprecated_reason` 字段（text，nullable）。
  - 新建 Alembic 迁移：`alembic/versions/YYYYMMDDHHMM_add_template_schema_version.py`。
  - `Template` dataclass 追加 4 个字段。
  - `TemplateModel` 追加 4 列。
  - `TemplateCreate` / `TemplateUpdate` DTO 追加 4 个字段（`schema_version` 可由客户端传入，但服务端有自增逻辑覆盖）。

- **后端 — schema_version 自增逻辑**：
  - 在 `TemplateService.update` 中实现破坏性变更检测：
    - **不递增** `schema_version` 的情况：
      - 叶子类型互转（text ⇄ textarea ⇄ number）
      - 新增字段（任意类型）
      - 修改字段 label / description
      - 修改 ai_prompt / ai_context
      - 拖拽排序（按 REQ-002-1 决议：仅影响 fields 数组顺序）
    - **必须递增** `schema_version` 的情况：
      - object ⇄ table ⇄ array 互转
      - 删除容器字段
      - 删除叶子字段
      - 修改叶子字段 key（即使仅大小写变化）
  - **破坏性变更检测算法**：维护一个 `last_known_fields` 快照（在 update 入口处从 DB 读出原 fields），与新 fields 做差量对比；若发现上述任一情况，`new_schema_version = old + 1`，否则 `new_schema_version = old`。
  - `TemplateService.update` 接收 `force_schema_bump: bool = False` 参数，允许客户端显式触发 schema_version 递增（用于"重命名字段"的特殊场景）。
  - 既有 `TemplateService.update` 内部调用 `_write_version_snapshot`（REQ-002-2）时，snapshot 写入新的 `schema_version`。

- **后端 — deprecated 标记**：
  - 新增 `POST /api/v1/templates/{id}/deprecate` 端点，入参 `{"reason": str}`：
    - 服务端把 `is_deprecated = true` / `deprecated_at = now()` / `deprecated_reason = reason` 写入。
    - 同步调用 `TemplateService.update` 触发 version 快照。
  - 新增 `POST /api/v1/templates/{id}/undeprecate` 端点（恢复使用）：
    - 把 `is_deprecated = false` / `deprecated_at = null` / `deprecated_reason = null` 写入。
    - 触发 version 快照。
  - `select_template`（REQ-004 既有）行为扩展：当某 doc_type 对应的活跃 template 已被 deprecated 时，**跳过**该 template（继续走 L2 / L3）；但**不报错**，避免破坏既有 e2e。
  - `GET /api/v1/templates` 列表查询支持 `include_deprecated` 参数（默认 false，过滤 deprecated；true 返回全部）。

- **后端 — 字段命名规范校验**：
  - 在 `TemplateService.create` / `update` / `clone` / `import_template`（REQ-002-2）入口处统一调用 `_validate_fields(fields)`：
    - 校验 `field.key` 匹配 `^[a-z][a-z0-9_]*$`（Q4 决议）。
    - 校验同层 `field.key` 唯一（Q4 决议）。
    - **新增**：校验 `field.key` **不**在保留键集合 `{id, version, layer, matched_type, confidence, reason}`（REQ-002-3 contract 决策）：保留键冲突会导致落盘的 `{id, version, layer, ...data}` 与 fields 互相覆盖；这是 REQ-002-3 已识别的风险，本次按 Q4 决议补上校验。
    - 校验失败时抛 `ValueError`，service 层捕获后返回 422 + 详细错误信息。

- **后端 — `try_parse` / `extract_template_prompts.build_fields_desc` 兼容**：
  - REQ-005 既有 `try_parse` 解析 LLM 响应时，如果 LLM 返回的字段 key 命中保留键（如 `id`），`build_fields_desc` 会生成"id(id)[text型]"描述；该描述用于 prompt 构造，不是结构性问题。
  - 本任务**不**改 `try_parse` / `build_fields_desc`，仅在 service 层校验时拒绝保留键冲突。

- **前端 — schema_version 显示 + 容器互转二次确认**：
  - TemplateEditorView 顶部"保存"按钮旁显示当前 `schema_version: {n}`（仅编辑模式）。
  - 当用户把字段从 object 改为 table（或反之）时，弹二次确认对话框：
    - 标题："破坏性变更确认"
    - 内容："此操作将把字段从 object 改为 table，已有抽取结果中该字段会失配。是否继续？"
    - 按钮："确认继续" / "取消"
    - 用户确认后，前端调用 `templateApi.update(payload)` 时**显式**设置 `force_schema_bump=true`；不确认则不发送请求。
  - 删除字段时同样弹二次确认（含"已有抽取结果会被裁剪"提示 + 撤销入口 — REQ-002-1 已有撤销能力）。

- **前端 — deprecated 标记 UI**：
  - TemplateListView 卡片右上角（删除 / 复制旁）新增"弃用"按钮（仅当 `!is_deprecated` 时显示）；点击后弹确认框 + 输入 reason 文本框（必填），调用 `templateApi.deprecate(id, { reason })`。
  - TemplateEditorView 顶部"保存"按钮旁新增"恢复使用"按钮（仅当 `is_deprecated` 时显示）。
  - TemplateListView 卡片在 `is_deprecated` 时显示"已弃用"灰色 badge + 浅色背景。

- **前端 — 字段命名规范校验**：
  - TemplateEditorView 在用户输入 `field.key` 时实时校验：
    - 命中保留键 → input 红框 + 错误提示"key 是保留字段名（id/version/layer/matched_type/confidence/reason）"
    - 不匹配 `^[a-z][a-z0-9_]*$` → 红框 + 错误提示"key 必须以小写字母开头，仅含小写字母、数字、下划线"
    - 同层重复 → 红框 + 错误提示"同层 key 必须唯一"
  - 实时校验不阻塞保存，但保存按钮在校验失败时禁用 + tooltip 提示。

- **测试**：
  - 后端 `tests/contexts/template/test_template_maintainability.py` 新增 ≥8 条用例：
    - schema_version 不递增（叶子类型互转 / 新增字段 / 拖拽排序）
    - schema_version 递增（容器互转 / 删字段 / 改叶子 key）
    - `force_schema_bump=true` 强制递增
    - deprecated 标记 + undeprecate 恢复
    - 字段命名规范校验（保留键 / 非法字符 / 同层重复）
    - clone / import 不绕过校验（REQ-002-2 集成）
  - 前端：至少 1 条手测记录或 e2e 覆盖"object → table 二次确认 + deprecated 标记 + 字段命名校验"完整流程。

- **文档回填**：
  - P2 里程碑 Open Items 加 REQ-002-4 行。
  - Backlog REQ-002-4 状态推进。
  - current-work.md 把 REQ-002-4 移入"当前进行中"。
  - work-log.md 单行索引（待 Done 时回填）。

### 不包含

- **不**做 schema_version 迁移工具（自动把老抽取结果升级到新 schema_version）；schema 演进本身需要人工核对抽取结果，工具留独立 follow-up。
- **不**做 version tag（v1.0.0 语义版本）；`schema_version` 仅 int 自增。
- **不**做批量 deprecate（一次弃用多个 template）；单次 1 个。
- **不**做 deprecate 的"影响范围预览"（哪些文档正在使用该 template）；保留独立 follow-up。
- **不**改 `select_template` 已有 L1 / L2 / L3 优先级（REQ-004）；仅扩展"deprecated 模板跳过"行为。
- **不**改 REQ-002-3 contract `{id, version, layer, ...data}` 的落盘 shape（仅在 service 层校验时不接受保留键作为 field.key）。
- **不**改 REQ-002-2 clone / version / export / import 的端点契约；仅在 service 层方法内追加校验调用。
- **不**改 REQ-002-1 拖拽 / 复制 / 撤销 / 搜索 UX；仅在拖拽排序时确保 schema_version 不递增（验证算法）。
- **不**做 RAG / KG / 文档解析上下文的协同改动。
- **不**引入新依赖。

## 验收标准

| ID | 验收点 | 通过条件 | 失败条件 |
|----|--------|----------|----------|
| AC-1 | 模板表新增 4 个字段 | `templates` 表存在 `schema_version` (int, default 1) / `is_deprecated` (bool, default false) / `deprecated_at` (datetime, nullable) / `deprecated_reason` (text, nullable)；Alembic 迁移可上可下；既有数据不丢失。 | 字段缺失 / 迁移失败 / 既有数据丢失 |
| AC-2 | schema_version 不递增 — 叶子类型互转 | 把 `field.type` 从 text 改为 textarea（或反之）后调用 `templateApi.update`，`schema_version` 与改前一致；version snapshot 的 `schema_version` 字段也是原值。 | schema_version 误增 |
| AC-3 | schema_version 不递增 — 新增字段 | 在已有 template 上添加 1 个新字段后调用 update，`schema_version` 与改前一致；snapshot 记录新 fields。 | schema_version 误增 |
| AC-4 | schema_version 不递增 — 拖拽排序（REQ-002-1 集成） | 把 fields 数组重新排序后调用 update，`schema_version` 与改前一致；不触发破坏性变更检测。 | 拖拽排序误增 schema_version |
| AC-5 | schema_version 递增 — 容器互转 | 把 `field.type` 从 object 改为 table（或反之）后调用 update（**不带** `force_schema_bump`），`schema_version = old + 1`；snapshot 记录新 schema_version。 | schema_version 未增 / 错增 |
| AC-6 | schema_version 递增 — 删除字段 | 删除 1 个字段后调用 update，`schema_version = old + 1`；snapshot 不包含被删字段。 | schema_version 未增 / 错增 |
| AC-7 | schema_version 递增 — 修改叶子 key | 把 `field.key` 从 `course_name` 改为 `course_name_v2` 后调用 update，`schema_version = old + 1`；snapshot 记录新 key。 | schema_version 未增 / 错增 |
| AC-8 | `force_schema_bump=true` 强制递增 | 即使是叶子类型互转，传 `force_schema_bump=true` 时 `schema_version = old + 1`。 | 强制参数未生效 |
| AC-9 | deprecated 标记 API | `POST /api/v1/templates/{id}/deprecate` 入参 `{"reason": "使用率低，被新模板替代"}`，返回 200 + template `is_deprecated=true`；`deprecated_at` 不为空；`deprecated_reason` = 入参；触发 version 快照。 | deprecate 后字段缺失 / 未写 version |
| AC-10 | deprecated 后跳过 select_template | 用 1 个 doc_type 创建 template A，再用同一 doc_type 创建 template B 并 deprecate B；调用 `select_template(doc_type=X)`，命中 A 不命中 B；调用 `select_template(doc_type=Y)`（无 A / B），走 L3 / 无命中。 | B 仍被命中 / A 失效 |
| AC-11 | undeprecate 恢复 | `POST /api/v1/templates/{id}/undeprecate` 返回 200 + `is_deprecated=false`；`deprecated_at` / `deprecated_reason` 清空；触发 version 快照。 | undeprecate 后字段未清空 / 未写 version |
| AC-12 | 字段命名规范 — 非法字符 | create / update / clone / import 任一操作传入 `field.key = "Invalid-Key"`，返回 422 + 详细错误。 | 未校验 / 校验失败仍通过 |
| AC-13 | 字段命名规范 — 同层重复 | create / update / clone / import 任一操作传入同层 2 个 field 共用 key，返回 422 + 详细错误。 | 未校验 / 校验失败仍通过 |
| AC-14 | 字段命名规范 — 保留键冲突 | create / update / clone / import 任一操作传入 `field.key = "id"`，返回 422 + 详细错误（"key 'id' 是保留字段名"）。 | 未校验 / 校验失败仍通过 |
| AC-15 | REQ-002-2 clone / import 集成校验 | REQ-002-2 的 `clone` / `import_template` 端点自动调用 `_validate_fields`；非法 template 在 import 时 422 拒绝；合法 template 正常 clone。 | clone / import 绕过校验 |
| AC-16 | 前端 schema_version 显示 | TemplateEditorView 顶部"保存"按钮旁显示 `schema_version: {n}`；新建模式不显示。 | 显示缺失 / 新建模式错误显示 |
| AC-17 | 前端容器互转二次确认 | 在 FieldCard 的 type 下拉框中把 object 改为 table 时，弹二次确认对话框"破坏性变更确认"；点击"确认继续"才更新 form；点击"取消"则 form 不变；确认后调用 update 时 payload 含 `force_schema_bump=true`。 | 二次确认缺失 / 强制参数缺失 |
| AC-18 | 前端字段删除二次确认 | 删除字段时弹二次确认对话框"破坏性变更确认：已有抽取结果中该字段会被裁剪"；确认后调用 update 含 `force_schema_bump=true`。 | 二次确认缺失 / 强制参数缺失 |
| AC-19 | 前端 deprecated 标记 UI | TemplateListView 卡片"弃用"按钮（仅 `!is_deprecated` 时显示）；点击弹确认框 + reason 文本框；提交后调用 `templateApi.deprecate(id, { reason })`；卡片刷新显示"已弃用" badge + 浅色背景。 | 按钮缺失 / 确认框缺失 / badge 缺失 |
| AC-20 | 前端 undeprecate UI | TemplateEditorView "恢复使用"按钮（仅 `is_deprecated` 时显示）；点击调用 `templateApi.undeprecate(id)` 后刷新。 | 按钮缺失 / 刷新失败 |
| AC-21 | 前端字段命名实时校验 | TemplateEditorView 在 `field.key` input 失焦或输入时校验：保留键 → 红框；非法字符 → 红框；同层重复 → 红框；保存按钮在校验失败时禁用。 | 校验缺失 / 红框样式缺失 / 按钮未禁用 |
| AC-22 | REQ-002-3 兼容 | REQ-002-3 落盘的 `{id, version, layer, ...data}` contract 保持；保留键 `id` / `version` / `layer` 在 trace 时由后端 meta 写入，不与 field.key 冲突（AC-14 校验保证）。 | trace 字段被 field 覆盖 / 保留键冲突未拦截 |
| AC-23 | REQ-002-2 兼容 | REQ-002-2 clone / version / export / import 端点契约保持；新增校验在 service 层透明生效；既有 `test_template_reuse.py` 6+ 用例继续通过。 | 端点契约改变 / 既有测试失败 |
| AC-24 | REQ-002-1 兼容 | REQ-002-1 拖拽排序 UX 保持；拖拽后 schema_version 不递增（AC-4）。 | 拖拽后 schema_version 误增 |
| AC-25 | 后端 pytest 通过 | `cd packages/server-python && .venv/bin/python -m pytest tests/contexts/template tests/contexts/document -q` 全部通过；`test_template_maintainability.py` ≥8 条新用例全过。 | 任一失败 / 新用例缺失 |
| AC-26 | 前端 typecheck + lint | `cd packages/web && pnpm typecheck` 退出码 0；`pnpm lint` 退出码 0。 | 退出码非 0 |
| AC-27 | UI 回归 | 至少 1 条手测记录或 e2e 覆盖"object → table 二次确认 + 字段命名校验 + deprecated 标记 + 恢复使用"完整流程；记录在 PR 描述中。 | 缺手测记录 / e2e 失败 |
| AC-28 | 工程门禁 | `python3 scripts/check-engineering-docs` 退出码 0；`git diff --check` 干净。 | 退出码非 0 |
| AC-29 | 文档回填 | P2 里程碑 Open Items 加 REQ-002-4 行；Backlog REQ-002-4 状态推进；current-work.md 把 REQ-002-4 移入"当前进行中"。 | 任一事实源未同步 |

## 接口与依赖

新增端点：

- `POST /api/v1/templates/{template_id}/deprecate`（Q4 + 可维护性决议）
- `POST /api/v1/templates/{template_id}/undeprecate`
- `GET /api/v1/templates?include_deprecated=false`（扩展既有端点）

修改既有端点：

- `GET /api/v1/templates`（新增 `include_deprecated` 查询参数）
- `POST /api/v1/templates`（_validate_fields 校验）
- `PUT /api/v1/templates/{id}`（破坏性变更检测 + _validate_fields 校验 + force_schema_bump 参数）
- `POST /api/v1/templates/{id}/clone`（_validate_fields 校验）
- `POST /api/v1/templates/import`（_validate_fields 校验）

修改既有 service 方法：

- `TemplateService.create`（加 _validate_fields）
- `TemplateService.update`（破坏性变更检测 + force_schema_bump + _validate_fields）
- `TemplateService.clone`（REQ-002-2，加 _validate_fields）
- `TemplateService.import_template`（REQ-002-2，加 _validate_fields + schema_version 校验扩展）

新增 / 修改文件（**业务代码改动**）：

- 新建：`packages/server-python/alembic/versions/YYYYMMDDHHMM_add_template_schema_version.py`
- 修改：`packages/server-python/app/contexts/template/domain/entity.py`（追加 4 字段）
- 修改：`packages/server-python/app/contexts/template/infrastructure/models.py`（追加 4 列）
- 修改：`packages/server-python/app/contexts/template/application/dto.py`（追加 `DeprecateTemplateRequest`；`TemplateUpdate` 追加 `force_schema_bump` 参数）
- 修改：`packages/server-python/app/contexts/template/application/service.py`（破坏性变更检测 + deprecate / undeprecate + _validate_fields）
- 修改：`packages/server-python/app/contexts/template/interfaces/api/router.py`（2 个新端点 + 列表 include_deprecated + 既有端点校验）
- 修改：`packages/server-python/app/contexts/document/application/template_selector.py`（deprecated 跳过逻辑）
- 新建：`packages/server-python/tests/contexts/template/test_template_maintainability.py`（≥8 条新用例）
- 修改：`packages/web/src/services/template.ts`（追加 `deprecate` / `undeprecate` API + `forceSchemaBump` 字段 + `isDeprecated` 字段）
- 修改：`packages/web/src/views/admin/TemplateListView.vue`（弃用按钮 + 已弃用 badge）
- 修改：`packages/web/src/views/admin/TemplateEditorView.vue`（schema_version 显示 + 容器互转二次确认 + 字段删除二次确认 + 恢复使用按钮 + 字段命名实时校验）
- 修改：`packages/web/src/views/admin/FieldCard.vue`（type 下拉框变更触发二次确认事件）

文档改动：

- `docs/01-product-planning/02-milestones/02-growth-phase.md`
- `docs/01-product-planning/04-backlog.md`
- `docs/03-engineering-governance/current-work.md`

## 文件计划

业务代码改动（后端 6 修改 + 1 新迁移 + 1 新测试 + 前端 4 修改）：

后端：

- 新建 Alembic 迁移
- 修改 entity / models / dto / service / router / template_selector

前端：

- 修改 template.ts / TemplateListView.vue / TemplateEditorView.vue / FieldCard.vue

测试：

- 新建 test_template_maintainability.py（≥8 条新用例）

文档：

- 3 个事实源同步

## 风险与边界

1. **破坏性变更检测算法的复杂度**：检测"object ⇄ table ⇄ array 互转"需要递归遍历 fields，对比每个 field 的 type / key 是否变化；O(N) 算法复杂度，单次 update < 1ms（30 字段 + 3 层嵌套），可接受。
2. **`force_schema_bump` 参数的可滥用风险**：客户端可显式传 `true` 强制递增；服务端不应限制（避免与 Q6 决议"text/textarea/number 内可改"冲突，但允许显式递增）。后续如果需要权限分级，可作为独立 follow-up。
3. **deprecated 模板跳过的边界**：Q4 + 可维护性决议要求"deprecated 跳过"；但如果某 doc_type 仅有 deprecated 模板，select_template 应走 L3 / 无命中，而不是报错。这避免了"全部模板 deprecated 时无法上传文档"的死锁。
4. **保留键校验的边界**：保留键集合 `{id, version, layer, matched_type, confidence, reason}` 是 REQ-002-3 contract 引入的元数据键；本任务**不**校验保留键的层级（仅校验 field.key 不在保留键集合）。
5. **字段命名规范的边界**：保留键冲突校验仅校验 field.key，不校验 field.children / field.items 内嵌套字段；嵌套字段同样需要校验（递归实现）。
6. **deprecated 与 schema_version 的交互**：deprecated 操作触发 version 快照（REQ-002-2 一致性）；如果 deprecated 时强制 `force_schema_bump=true`，会让 deprecated 操作额外递增 schema_version；本任务选择**不强制**（deprecate 不属于破坏性字段变更，不递增 schema_version），但要写 version snapshot 保留 deprecated 状态。
7. **REQ-002-1 拖拽顺序与破坏性检测**：拖拽排序仅影响 fields 数组顺序，不影响任何 field 的 type / key / children；破坏性检测算法应该不识别顺序变化为破坏性变更。需在实现时显式**忽略**"字段在数组中的位置"差异。
8. **依赖顺序**：本任务**依赖** REQ-002-3 + REQ-002-2 + REQ-002-1 均已合并（保留键 / clone / 拖拽基础）。**被依赖**：无（REQ-002-4 是 REQ-002 子任务链的最后一棒）。

## 行为变化声明

| 项 | 变化 |
|----|------|
| `templates` 表 schema | 新增 4 列（schema_version / is_deprecated / deprecated_at / deprecated_reason） |
| `Template` dataclass | 新增 4 字段 |
| `TemplateCreate` / `TemplateUpdate` DTO | 追加 `force_schema_bump` 等 4 字段 |
| `TemplateService.update` | 新增破坏性变更检测 + 强制递增参数 + _validate_fields |
| `TemplateService.create` / `.clone` / `.import_template` | 统一 _validate_fields 校验 |
| `select_template` | deprecated 模板跳过（不影响 L1/L2/L3 优先级） |
| 新增端点 | 2 个（deprecate / undeprecate） |
| 前端 TemplateListView | 新增弃用按钮 + 已弃用 badge |
| 前端 TemplateEditorView | 新增 schema_version 显示 + 容器互转二次确认 + 字段删除二次确认 + 恢复使用按钮 + 字段命名实时校验 |
| 前端 FieldCard | type 下拉框变更触发二次确认事件 |
| API 契约 | 新增端点 + 既有端点新增 force_schema_bump / include_deprecated 参数 |
| DB schema | 既有 templates 表新增 4 列；既有数据不丢失 |
| REQ-002-3 contract | 保持 `{id, version, layer, ...data}`；保留键冲突校验保证不互相覆盖 |
| REQ-002-2 端点契约 | 保持；clone / import 自动调用 _validate_fields |
| REQ-002-1 拖拽 UX | 保持；拖拽不递增 schema_version |
| 模板匹配 / 抽取 / RAG / KG | 全部不变（仅 select_template 跳过 deprecated） |

## 依赖与执行顺序

- **强依赖**：REQ-002-3 + REQ-002-2 + REQ-002-1 均已合并（保留键 / clone / 拖拽基础）。
- 与 TD-009（shared schema gate）相关：`Template` interface 字段变更需要在 frontend types 中保持一致；不破坏现有 `Template` interface（追加 4 个可选字段）。
- 与 TD-029（shared schema）相关：`FileDTO.structured_data` 不变；本任务不动 schema 文件。
- 与 TD-030（RecallChannel Protocol）无关：本任务不动 knowledge / rag 上下文。
- 与 TD-032（large source files）相关：本任务修改 backend service.py（已有 ~500 行），可能增加 100-200 行；按 TD-032 基线，service.py 仍 < 800 行上限；提交后跑 `scripts/scan-source-sizes --diff` 确认。
- 与 TD-034（build_fields_desc array+items=[] 提示丢失）无关：本任务不改 extract_template_prompts。
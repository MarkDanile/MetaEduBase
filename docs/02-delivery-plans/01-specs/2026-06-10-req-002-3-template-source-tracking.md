# REQ-002-3 模板抽取结果溯源字段扩展 — Spec

> Spec 入口：REQ-002-3（REQ-002 子任务链 #3，contract 扩展先行）。本文件是验收口径与边界的事实源；实施拆分见 `docs/02-delivery-plans/02-plans/2026-06-10-req-002-3-template-source-tracking-plan.md`。
> Parent：[REQ-002 决策记录 Q3](../../01-product-planning/05-requirements/REQ-002-template-config-and-reuse.md#决策记录2026-06-10-塑形澄清)（"扩 `structured_data["template"]` 字段：结构变为 `{id, version, layer, ...data}`"）。

## 目标

把 `extract_template` Celery 任务的产物 `structured_data["template"]` 从"仅含 LLM 抽取字段"扩展为"溯源元数据 + LLM 抽取字段"的复合结构，让"该文档究竟用了哪个模板哪个版本、命中哪一层选择"成为可查事实。

决策来源（REQ-002 塑形期 2026-06-10 决议 Q3）：

> 抽取结果回写：**扩 `structured_data["template"]` 字段**：结构变为 `{id, version, layer, ...data}`。这涉及 REQ-005 contract 测试与 REQ-006 e2e 断言同步对齐；document 上下文需要新增字段写入逻辑。

变更前：`structured_data["template"] = {<LLM 抽取字段>}`（仅数据）。
变更后：`structured_data["template"] = {id, version, layer, <LLM 抽取字段>}`（溯源 + 数据）。

## 范围

### 包含

- **后端 contract 扩展**：
  - 修改 `packages/server-python/app/contexts/document/application/tasks/extract_template_prompts.py:_merge_template_structured_data` 签名，新增可选参数 `meta: dict[str, object] | None = None`；`meta` 中的键值会被合并到 `merged["template"]` 顶部，**不**做深拷贝（沿用现有浅拷贝契约：外层新 dict、内嵌 list/dict 同引用）。
  - `meta` 仅接受 `{"id", "version", "layer", "matched_type", "confidence", "reason"}` 6 个保留键；其他键会被忽略并写 WARNING 日志（防止误传）。`id` / `version` / `layer` 是核心溯源键，必须出现（缺失时整个 `meta` 不写入，保留旧行为；缺失 case 必须记 WARNING 日志，**不**写 `{}`）。
  - `extract_template` Celery 任务在调用 `_merge_template_structured_data` 时传入 `meta={"id": str(template_obj.id), "version": template_obj.schema_version, "layer": selection.layer, "matched_type": selection.matched_type, "confidence": selection.confidence, "reason": selection.reason}`；template_obj 为 None / selection.layer == "none" 时，**不**传 `meta`（保持旧行为，避免污染抽取结果）。
- **后端 contract 测试同步**（按 `task-modes.md#新需求开发` 验收口径，必须显式更新）：
  - `packages/server-python/tests/contexts/document/test_structured_data_contract.py`：4 条既有断言中涉及 `template` 键值精确等价的（AC-1 / AC-2 / AC-3 / AC-4）需要按新 shape 更新；新增 ≥2 条 `meta` 路径断言（meta 写入 / meta 键白名单 / meta 缺失时回退 / meta 包含未知键忽略）。
  - `packages/server-python/tests/contexts/document/test_extract_template_prompts.py`：`_merge_template_structured_data` 的 8 条嵌套形态用例中至少 1 条必须显式覆盖"meta 存在 + 嵌套 fields 同引用"组合，避免浅拷贝契约被破坏。
- **e2e 同步**：
  - `packages/server-python/tests/e2e/test_p1_demo.py` AC-3 步骤（`test_p1_demo_step3_template_extract`）：在 `assert template, ...` 后新增对 `template["id"]` / `template["layer"]` 的存在性 + 类型断言（不验证具体值，避免 demo 数据漂移）。
- **前端渲染兼容**：
  - `packages/web/src/views/resource/FileTabsPanel.vue`：在结构化 Tab 渲染 `structured_data.template` 时过滤掉保留键（`id` / `version` / `layer` / `matched_type` / `confidence` / `reason`），让用户只看到 LLM 抽取字段；并在 Tab 顶部新增一个"溯源元信息"小卡（只读），显示 `id` / `version` / `layer` / `matched_type` / `confidence`；`reason` 仅在 `layer === "none"` 时显示。**实际修改目标在派发阶段确认**：原计划为 `ExtractedDataRenderer.vue` / `FileDetailView.vue`，控制器实现前验证 `FileTabsPanel.vue` 才是结构化 Tab 热路径（其使用 `FieldValue.vue` 按 `Object.keys(template)` 驱动）。`ExtractedDataRenderer.vue` 在本任务范围外、不修改。
- **API 契约同步**：
  - `FileDTO.structured_data` 的 OpenAPI / 类型定义（`packages/web/src/services/document.ts` 等）：无需修改 schema，因为 `structured_data` 已经是 `Record<string, any>` 类型；只在 contract 测试中固定新 shape。
- **文档回填**：
  - P1 里程碑 Open Items 加一行：REQ-002-3 状态、引用本 spec。
  - P2 里程碑 Open Items 同步。
  - Backlog 新建 REQ-002-3 行。
  - current-work.md 把 REQ-002-3 移入"当前进行中"。

### 不包含

- **模板版本快照（REQ-002-2）**：本任务不实现 `template_versions` 表 / version 自增 / 历史回滚；`meta["version"]` 当前固定为 `template_obj.schema_version` 的当前值（REQ-002-4 会引入 `schema_version` 字段；如未引入则传 `None`）。
- **字段填充率（REQ-002-1 / REQ-002-3 Q4 子项）**：本任务不实现 `usage-stats` 端点、不改 TemplateListView；只在结构层面允许后续子任务读取 `template_id` / `template_layer`。
- **跨租户复制 / JSON 导入导出（REQ-002-2）**：本任务不改 TemplateService 任何 CRUD 行为。
- **schema_version 自增逻辑（REQ-002-4）**：本任务不引入 schema_version 字段、不修改 template DTO / entity；`meta["version"]` 读取 `template_obj.schema_version`（若 entity 缺该字段则传 `None`）。schema_version 字段的引入在 REQ-002-4 单独处理。
- **行为变化**：
  - `select_template` 行为不变（仍返回 `SelectionResult`）。
  - `extract_template` 业务行为（prompt 构造 / JSON 解析 / Celery chain / `extract_knowledge_graph` 接力）不变，仅在最终落盘时多写 3 个保留键。
  - 当 template_obj 为 None（`layer == "none"`）时，**行为完全不变**（meta 不写入，与现状 100% 等价）。
  - 当 template_obj 存在但 `selection.layer == "none"` 时（同 L3 阈值未通过但 template 仍非空），行为不变（meta 仍不写入）。
- **前端可视化**：溯源元信息卡只显示文本，不提供"跳转到模板详情"等跳转（避免范围蔓延到 router 改造）。
- **新数据库迁移 / 新表**：本任务不改 `templates` 表 schema、不新建任何表。
- **e2e Redis broker / Celery**：完全沿用 REQ-006 Stage 1.5 的 e2e 链路（`tests/e2e/conftest.py` + `_run_task_async`），不引入新的 broker 配置。

## 验收标准

| ID | 验收点 | 通过条件 | 失败条件 |
|----|--------|----------|----------|
| AC-1 | `_merge_template_structured_data` 接受 `meta` 参数（默认 `None`） | 旧调用 `_merge_template_structured_data(existing, template_data)` 行为完全不变（`merged["template"] == dict(template_data)`、外层新 dict、内嵌浅拷贝）。 | 旧调用形状变化 / 抛 TypeError |
| AC-2 | `_merge_template_structured_data(existing, template_data, meta={"id": "abc", "version": 1, "layer": "L1"})` 写回新 shape | `merged["template"] == {"id": "abc", "version": 1, "layer": "L1", <template_data 字段>...}`，且保留键出现在 `template_data` 字段**之前**（顺序：先 meta 后 data）。 | 顺序反了 / 保留键被覆盖 / data 字段被吞 |
| AC-3 | meta 键白名单：未知键被忽略 | 传入 `meta={"id": "x", "foo": "bar"}` 时 `merged["template"]` 仅含 `id`，无 `foo`；extract_template 任务写 WARNING 日志 "extract_template.merge_template: ignored unknown meta key foo" 一次。 | 未知键写入 / 抛异常 |
| AC-4 | meta 缺失 / 全 None 时回退旧行为 | 传入 `meta=None` 或 `meta={}` 或 `meta` 不含 `id` / `version` / `layer` 任一核心键时，`merged["template"] == dict(template_data)`，与 AC-1 等价；记 WARNING 日志 "extract_template.merge_template: meta incomplete, falling back"。 | 写空 `meta={}` / 抛异常 |
| AC-5 | 浅拷贝契约：meta 写入后内嵌 list / dict 仍同引用 | 给定 `template_data = {"teaching_process": [{"step": "1"}]}` 与 `meta={"id": "x", "version": 1, "layer": "L1"}`，`merged["template"]["teaching_process"] is template_data["teaching_process"]` 且 `merged["template"]["teaching_process"][0] is template_data["teaching_process"][0]`；`merged["template"] is not template_data`。 | 改成深拷贝 / 外层同引用 |
| AC-6 | extract_template 任务在命中模板时落盘 meta | 调用 `extract_template.delay(file_id, tenant_id)` 后，DB `files.structured_data` 中 `template.id` 是 UUID 字符串，`template.layer in {"L1", "L2", "L3"}`，`template.version` 是 int 或 None（看 REQ-002-4 是否先完成）。 | meta 缺失 / layer 取值不在白名单 |
| AC-7 | extract_template 在 `layer == "none"` 时**不**落盘 meta | 当 `select_template` 返回 `layer == "none"`（含 L3 confidence 低于阈值、解析失败、空响应、template 为 None），`files.structured_data["template"]` **不**含 `id` / `version` / `layer` 键（与旧行为完全一致）。 | 落盘了空 `meta={}` / 写了 `layer: "none"` |
| AC-8 | 既有 contract 测试同步对齐 | `tests/contexts/document/test_structured_data_contract.py` 中 4 条 `_merge_template_structured_data` 既有断言按新 shape 更新：`template == {"id": ..., "version": ..., "layer": ..., ...data}`；不修改业务行为；不删除任何断言（仅更新等价值）。 | 删除既有断言 / 既有断言 shape 仍指向旧契约 |
| AC-9 | 既有 extract_template_prompts 测试同步 | `tests/contexts/document/test_extract_template_prompts.py` AC-8（嵌套浅拷贝）至少 1 条用例显式覆盖 meta + 嵌套 data 的组合，确保浅拷贝契约在 meta 路径下不破。 | 缺少 meta + 嵌套组合用例 |
| AC-10 | e2e P1 demo 同步 | `tests/e2e/test_p1_demo.py::test_p1_demo_step3_template_extract` 在已有 `assert template, ...` 之后新增：`assert "id" in template and "layer" in template and isinstance(template["id"], str) and template["layer"] in {"L1", "L2", "L3"}`；保留 AC-3 既有断言（`basic_info` 子结构）。 | 删了既有断言 / 新断言失败 |
| AC-11 | 前端 `FileTabsPanel` 结构化 Tab 过滤保留键 | 渲染 `structured_data.template` 时，`id` / `version` / `layer` / `matched_type` / `confidence` / `reason` 6 个保留键不出现在字段列表中（即用户只看到 `template_data` 字段）。 | 保留键被当作字段渲染（出现 input/textarea 占位） |
| AC-12 | 前端 `FileTabsPanel` 结构化 Tab 新增溯源元信息卡 | 当 `template.id` 存在时，Tab 顶部显示一行只读元信息：`模板 ID: <id> · 版本: <version or '-'> · 命中: <layer>`；`layer === "none"` 时改为显示 `未命中模板: <reason>`。当 `template.id` 不存在（layer none / 老数据）时不显示该卡。 | 老数据下显示空 ID / 命中卡始终显示 |
| AC-13 | 回归命令可复现 | `cd packages/server-python && .venv/bin/python -m pytest tests/contexts/document/test_structured_data_contract.py tests/contexts/document/test_extract_template_prompts.py tests/contexts/document/test_extract_template_selection.py tests/contexts/template/test_template.py tests/e2e/test_p1_demo.py -q` 全部通过（pytest exit 0）。 | 任一文件失败 |
| AC-14 | 前端 typecheck + lint | `cd packages/web && pnpm typecheck` 退出码 0；`pnpm lint` 退出码 0。 | 退出码非 0 |
| AC-15 | 工程门禁 | `python3 scripts/check-engineering-docs` 退出码 0；`git diff --check` 干净。 | 退出码非 0 |
| AC-16 | 文档回填 | P1 里程碑 Open Items 加 REQ-002-3 行（状态引用本 spec）；P2 里程碑同步；Backlog 新建 REQ-002-3 行（初始 `🟡 Planned`）；current-work.md 把 REQ-002-3 移入"当前进行中"。 | 任一事实源未同步 |

## 接口与依赖

测试目标模块（**会修改**业务行为 — 仅 `_merge_template_structured_data` 签名 + extract_template 落盘逻辑）：

- `packages/server-python/app/contexts/document/application/tasks/extract_template_prompts.py:_merge_template_structured_data`（扩展签名 + 接受 meta）
- `packages/server-python/app/contexts/document/application/tasks/extract_template.py:extract_template`（在落盘前构造 meta 并传入；template_obj 为 None / layer == "none" 时不传）
- `packages/web/src/views/resource/FileTabsPanel.vue`（过滤保留键 + 在结构化 Tab 顶部新增溯源元信息卡；`FieldValue.vue` 保持纯组件不感知保留键）

测试 / 改动文件：

- 修改：`packages/server-python/app/contexts/document/application/tasks/extract_template_prompts.py`（AC-1 ~ AC-5）
- 修改：`packages/server-python/app/contexts/document/application/tasks/extract_template.py`（AC-6, AC-7）
- 修改：`packages/server-python/tests/contexts/document/test_structured_data_contract.py`（AC-8）
- 修改：`packages/server-python/tests/contexts/document/test_extract_template_prompts.py`（AC-9）
- 修改：`packages/server-python/tests/e2e/test_p1_demo.py`（AC-10）
- 修改：`packages/web/src/views/resource/FileTabsPanel.vue`（AC-11 + AC-12）
- 修改：`docs/01-product-planning/02-milestones/01-validation-phase.md`（AC-16）
- 修改：`docs/01-product-planning/02-milestones/02-growth-phase.md`（AC-16）
- 修改：`docs/01-product-planning/04-backlog.md`（AC-16，新建 REQ-002-3 行）
- 修改：`docs/03-engineering-governance/current-work.md`（AC-16）

## 文件计划

业务代码改动：

- `packages/server-python/app/contexts/document/application/tasks/extract_template_prompts.py`（_merge_template_structured_data 签名 + meta 合并逻辑）
- `packages/server-python/app/contexts/document/application/tasks/extract_template.py`（在 `_merge_template_structured_data` 调用前构造 meta）
- `packages/web/src/views/resource/FileTabsPanel.vue`（过滤保留键 + 溯源元信息卡）

测试改动：

- `packages/server-python/tests/contexts/document/test_structured_data_contract.py`（4 条既有断言更新 + ≥2 条新断言）
- `packages/server-python/tests/contexts/document/test_extract_template_prompts.py`（AC-9 新增 ≥1 条 meta 嵌套组合用例）
- `packages/server-python/tests/e2e/test_p1_demo.py`（AC-3 步骤新增 id/layer 断言）

文档改动：

- `docs/01-product-planning/02-milestones/01-validation-phase.md`（Open Items REQ-002-3 行）
- `docs/01-product-planning/02-milestones/02-growth-phase.md`（Open Items REQ-002-3 行）
- `docs/01-product-planning/04-backlog.md`（新建 REQ-002-3 行）
- `docs/03-engineering-governance/current-work.md`（REQ-002-3 进入"当前进行中"）

## 风险与边界

1. **保留键冲突**：`id` / `version` / `layer` 是保留键，理论上用户可在 Template.fields 中定义同名字段。本任务**不**做保留键校验（应在 REQ-002-4 schema 演进子任务或独立技术债中处理）。建议在 `TemplateService.create` / `update` 时校验 `field.key` 不在保留键集合中；本任务先记入技术债，不在 PR 范围。
2. **旧数据兼容**：DB 中已存在的 `structured_data.template`（无 `id` / `version` / `layer`）继续按旧 shape 工作；AC-12 明确"老数据下不显示溯源卡"。
3. **e2e 数据漂移**：AC-10 不验证 `template.id` / `template.layer` 的具体值（避免 demo 数据变化导致测试脆弱），只验证存在性与类型。
4. **select_template 返回 shape 不变**：依赖 `selection.layer` / `selection.matched_type` / `selection.confidence` / `selection.reason` 4 个字段（已存在）；不修改 `template_selector.py`。
5. **schema_version 缺位**：`template_obj.schema_version` 当前可能不存在（REQ-002-4 未做）。如缺，AC-6 中 `template.version` 应为 `None`，不应抛 AttributeError。`extract_template` 必须用 `getattr(template_obj, "schema_version", None)` 兼容。
6. **行为不变承诺**：
   - 旧调用 `_merge_template_structured_data(existing, template_data)`（无 meta）行为完全等价（AC-1 / AC-4）。
   - `extract_template` 在 `layer == "none"` 时行为完全等价（AC-7）。
   - 这两个 case 是 REQ-006 Stage 1.5 e2e 已通过路径的覆盖区间。

## 行为变化声明

| 项 | 变化 |
|----|------|
| `_merge_template_structured_data` 签名 | +1 可选参数 `meta: dict | None = None`（默认值保持旧行为） |
| `structured_data.template` 落盘 shape | 命中模板时新增 3 个保留键 `id` / `version` / `layer`（及辅助 `matched_type` / `confidence` / `reason`） |
| `extract_template` 日志 | 新增"meta ignored unknown key" / "meta incomplete, falling back"两种 WARNING（频率低，仅在 misuse / 缺失时） |
| `select_template` / 模板匹配优先级 / L3 阈值 | 不变 |
| `extract_template` prompt 构造 / LLM 调用 / JSON 解析 / Celery chain / `extract_knowledge_graph` 接力 | 不变 |
| 前端 `FileTabsPanel` 结构化 Tab 字段渲染 | 过滤 6 个保留键（不渲染为字段） |
| 前端 `FileTabsPanel` 结构化 Tab 顶部溯源元信息卡 | 新增只读元信息卡（仅在 `template.id` 存在时显示，老数据不显示） |
| `FileDTO.structured_data` 类型 | 不变（已是 `Record<string, any>`） |
| 数据库 schema | 不变（沿用 JSONB） |
| API 契约 | 不变 |

## 依赖与执行顺序

- **必须先于** REQ-002-1 / REQ-002-2 / REQ-002-4 进入开发（按 REQ-002「下一步」段依赖顺序）。
- 与 REQ-005 既有 contract 测试**有交叠**（都断言 `_merge_template_structured_data` shape）；本任务**先更新** REQ-005 contract 测试到新 shape，再让 REQ-005 既有 11 条用例在新 shape 下通过；如发现行为漂移，回退到本任务单独处理。
- 与 REQ-006 Stage 1.5 e2e **有交叠**（AC-3 步骤已断言 `template.basic_info`）；本任务**追加** `id` / `layer` 断言，保留 `basic_info` 既有断言。
- 与 TD-034（`build_fields_desc` array+items=[] 提示丢失）无关；不修改 `build_fields_desc`。
- 与 TD-009（shared schema gate）无关；不修改 `FileDTO.structured_data` schema。
- 与 TD-030（RecallChannel Protocol drift）无关；本任务不动 knowledge / rag 上下文。

# REQ-002-1 模板配置效率（编辑器 UX 补齐） — Spec

> Spec 入口：REQ-002-1（REQ-002 子任务链 #1，配置效率）。本文件是验收口径与边界的事实源；实施拆分见 `docs/02-delivery-plans/02-plans/2026-06-10-req-002-1-template-config-ux-plan.md`。
> Parent：[REQ-002 决策记录 Q5 + 范围段「配置效率」](../../01-product-planning/05-requirements/REQ-002-template-config-and-reuse.md#决策记录2026-06-10-塑形澄清)（"root + object 子字段 + array 项模板三层拖拽 + 子树复制 + 撤销 + 大模板浏览"）。

## 目标

把 TemplateEditorView 的字段编辑体验从"靠添加/删除按钮"升级为"可拖拽排序、可子树复制、可撤销删除、可在 30+ 字段模板里快速定位"，覆盖课程负责人 / 模板维护者等高频调整模板的用户场景（见 REQ-002「期望用户与场景」段第 1 / 2 行）。

决策来源（REQ-002 塑形期 2026-06-10 决议 Q5）：

> 拖拽排序：root + object 子字段 + array 项模板三层均可拖；不持久化到 ai_context，仅影响 fields 数组顺序。

变更前：TemplateEditorView 通过 FieldCard + FieldItem 列表渲染嵌套字段，但**无**拖拽排序、**无**子树复制、**无**删除撤销、**无**大模板浏览能力。
变更后：4 项编辑器 UX 能力全部到位，所有改动只在前端（**业务代码改动范围 = 0 个后端文件**）。

## 范围

### 包含

- **拖拽排序三层**（Q5 决议）：
  - root 层：TemplateEditorView 的 `form.fields` 数组可整体拖拽排序。
  - object 子字段：FieldEditor / FieldCard 的 `children` 数组可拖拽排序。
  - array 项模板：FieldEditor / FieldCard 的 `items` 数组可拖拽排序（注意：array items 通常是单 Field 模板，但允许同 array 内多个不同字段语义；按 Q5 决议只支持单 item 模板的 array 拖拽时仅 1 项 → 与现状一致，无需拖拽）。
  - 实现方式：vuedraggable 已在 `packages/web/package.json` 依赖中（`^4.1.0`），但当前 `packages/web/src/` 无任何 `vuedraggable` 引用；本任务把 vuedraggable 集成进 FieldCard + FieldItem + FieldEditor。
  - 拖拽状态**不**持久化到 `ai_context`，**不**写 `schema_version`（按 Q5 + Q6 决议：拖拽只影响 fields 数组顺序，属于"新增字段"之外的轻量变化，不触发 schema_version 递增）。
- **子树复制**：
  - 在 object / array 字段上新增"复制子树"按钮（与"删除"按钮并列），点击后在同层追加一个深拷贝的 Field（含 children / columns / items），并对 key 加 `_copy_1` / `_copy_2` 后缀避免冲突（用户保存前可手动改 key）。
  - 实现方式：递归深拷贝 Field 子树（避免共享引用导致一改全改），新 key 自动加后缀。
- **字段删除可逆**：
  - 删除字段时弹 toast "已删除字段 <key>"，toast 提供 5 秒内"撤销"按钮，点击后恢复被删字段到原位置（原 parent 同一 index）。
  - 实现方式：删除前把"被删 Field + parent_id + index"存到 `deletedFieldsStack`（TemplateEditorView 局部 ref），撤销时弹回。
  - 边界：只撤销最后一次删除（不维护完整 undo 栈，避免复杂度）。如需完整 undo 栈，作为独立 follow-up。
- **大模板浏览**：
  - 当 `form.fields.length + 递归统计所有 children + items 总数 > 30` 时，TemplateEditorView 顶部新增"折叠/展开全部"按钮 + "按 label / key 搜索字段"输入框。
  - 搜索框：实时过滤 FieldCard 列表（filter 不删除节点，只把不匹配的 FieldCard 隐藏 + dim，匹配的子字段保持可见）；清空搜索恢复全部可见。
  - 折叠/展开：把所有 container 类型（object / table / array）的 `expanded` 状态置为 true / false（按已存在的 FieldItem 状态扩展）。
  - 实现方式：纯前端 UI 状态，不改数据结构。
- **测试 / 验证**：
  - 新增 `packages/web/src/views/admin/FieldItem.spec.ts` 或类似（用 vitest，若项目已用 vitest；否则手测截图）：至少覆盖拖拽排序、子树复制、撤销删除、搜索过滤 4 项 UI 交互的快照或行为测试。
  - 若项目无前端单测框架：**至少 1 条 e2e 或可视化回归**（playwright / puppeteer / 手测截图），覆盖"打开 TemplateEditorView / 添加 3 个字段 / 拖拽排序 / 保存"完整流程。
  - 文档回填：P2 里程碑 Open Items 加 REQ-002-1 行；Backlog REQ-002-1 状态 `🔵 Ready` → `🟡 Planned`；current-work.md 把 REQ-002-1 移入"当前进行中"。

### 不包含

- **不**改 backend 任何文件（0 个后端文件改动）。
- **不**改 template DTO / entity / repository / router（不影响 API 契约）。
- **不**改 `select_template` / 模板匹配优先级 / L3 阈值 / extract_template 行为。
- **不**改 REQ-002-3 已落盘的 `{id, version, layer, ...data}` contract（拖拽只影响 fields 数组顺序，不改溯源字段）。
- **不**持久化拖拽状态到 `ai_context` 或独立字段（Q5 决议）。
- **不**实现完整 undo/redo 栈（只覆盖单次删除撤销；完整 undo/redo 留独立 follow-up）。
- **不**引入 vuedraggable 之外的拖拽库（已在依赖里）。
- **不**实现 array 字段多 item 模板的拖拽（按现状 items 数组是单 Field，与 Q5 "array 项模板"语义一致；多数组拖拽留独立 follow-up）。
- **不**改 TemplateListView / TemplateAiPanel / ExtractedDataRenderer（本次只动 TemplateEditorView + FieldEditor + FieldItem + FieldCard）。
- **不**改 keyboard 快捷键（虽然 vuedraggable 支持，但本次只做鼠标拖拽；键盘可访问性留独立 follow-up）。

## 验收标准

| ID | 验收点 | 通过条件 | 失败条件 |
|----|--------|----------|----------|
| AC-1 | 拖拽排序 — root 层 | 在 TemplateEditorView 的 `form.fields` 中，3 个 root 字段可被鼠标拖拽改变顺序；保存后 `template.fields` 数组顺序与拖拽后一致。 | 拖拽无效 / 顺序未变 / 保存后顺序回退 |
| AC-2 | 拖拽排序 — object 子字段 | 在 object 字段的 `children` 中，2 个子字段可被鼠标拖拽改变顺序；保存后 `template.fields[].children` 数组顺序与拖拽后一致。 | object 子字段拖拽无效 / 顺序错乱 |
| AC-3 | 拖拽排序 — array 项模板 | 在 array 字段的 `items` 中（单 Field 模板），可通过拖拽微调 items 数组（多数组场景下保持 items 长度 = 1；少数组场景下允许拖拽不影响 schema）。 | array items 拖拽崩溃 / 表单状态错乱 |
| AC-4 | 拖拽不触发 schema_version 递增 | 拖拽排序后保存，前端调用 `templateApi.update` 时 payload 中 `schema_version` 与原值一致（不递增）；meta `version` 字段保持原值。 | schema_version 误增 / payload 多了不该有的字段 |
| AC-5 | 子树复制 — object 字段 | 在 object 字段的卡片上点击"复制子树"按钮，在同 parent 的 children 数组末尾追加一个深拷贝，新 key 为原 key + `_copy_1` 后缀（无冲突时）；`newField.children` / `newField.columns` / `newField.items` 都是新对象（`is not`），不与原对象共享引用。 | 深拷贝失败 / key 冲突未处理 / 共享引用导致改一处全改 |
| AC-6 | 子树复制 — array 字段 | 在 array 字段的卡片上点击"复制子树"按钮，在同 parent 的 items 数组末尾追加一个深拷贝，新 key 加 `_copy_1` 后缀；与 object 同样深拷贝。 | array items 复制后无法保存 / 子树被截断 |
| AC-7 | 字段删除可逆 | 删除一个字段后，顶部 toast 显示 "已删除字段 <key>"，含"撤销"按钮；5 秒内点击撤销，被删字段恢复到原 parent 同一 index；超过 5 秒撤销按钮消失。 | toast 未出现 / 撤销无效 / 恢复位置错 / 撤销后表单状态错乱 |
| AC-8 | 大模板浏览 — 折叠/展开全部 | 当 `totalFields`（递归统计 form.fields + 所有 children + items）> 30 时，TemplateEditorView 顶部出现"全部折叠" / "全部展开"两个按钮；点击"全部折叠"，所有 object / table / array 字段的 FieldCard 收起子字段；再点击"全部展开"恢复。 | 按钮未出现 / 折叠/展开行为反向 / 状态丢失 |
| AC-9 | 大模板浏览 — 搜索过滤 | 搜索框输入 `course_name` 时，FieldCard 列表实时过滤：label 或 key 包含搜索词的字段保持高亮可见，不匹配的字段隐藏或 dim（具体 UX 由实现决定，但需保留至少 1 个匹配项可见）；清空搜索恢复全部可见。 | 搜索无效果 / 匹配项被隐藏 / 搜索后无法恢复 |
| AC-10 | 30+ 字段阈值边界 | 当 `totalFields == 30` 时**不**显示折叠/展开按钮（边界不包含）；当 `totalFields == 31` 时显示。 | 阈值边界错误 |
| AC-11 | vuedraggable 集成不破坏既有 FieldCard 行为 | 现有 FieldCard 的"添加子字段" / "添加列" / "删除" 按钮在拖拽集成后仍正常工作；FieldEditor 递归子组件仍正常渲染。 | 拖拽集成后既有按钮失效 / 递归渲染失败 |
| AC-12 | 不影响 REQ-002-3 溯源卡 | 拖拽 / 复制 / 撤销 / 搜索 4 项操作均**不**影响 `structured_data.template.id` / `layer` 等溯源字段（前端 UI 行为，不触发后端落盘）；REQ-002-3 已合入的溯源元信息卡在拖拽场景下仍正常显示。 | 拖拽操作误触发后端 save / 溯源卡显示异常 |
| AC-13 | 行为不变 — API 契约 | 拖拽 / 复制 / 撤销 / 搜索 4 项操作**不**修改 `TemplateCreate` / `TemplateUpdate` DTO 形状；后端 API 契约不变；DB schema 不变。 | 前端操作修改了不该改的字段 / API 调用参数变化 |
| AC-14 | 前端 typecheck + lint | `cd packages/web && pnpm typecheck` 退出码 0；`pnpm lint` 退出码 0。 | 退出码非 0 |
| AC-15 | UI 回归（手测或 e2e） | 至少 1 条手测记录或 e2e 脚本覆盖"打开 TemplateEditorView / 添加 3 个字段 / 拖拽排序 / 保存 / 验证保存后顺序"完整流程；记录在 PR 描述中。 | 缺手测记录 / e2e 失败 |
| AC-16 | 工程门禁 | `python3 scripts/check-engineering-docs` 退出码 0；`git diff --check` 干净。 | 退出码非 0 |
| AC-17 | 文档回填 | P2 里程碑 Open Items 加 REQ-002-1 行（状态引用本 spec）；Backlog REQ-002-1 状态推进；current-work.md 把 REQ-002-1 移入"当前进行中"。 | 任一事实源未同步 |

## 接口与依赖

测试 / 改动文件（**全部前端，0 个后端文件**）：

- 修改：`packages/web/src/views/admin/TemplateEditorView.vue`（拖拽 root 集成 + 撤销 toast + 折叠/展开按钮 + 搜索框）
- 修改：`packages/web/src/views/admin/FieldItem.vue`（递归渲染整合拖拽：root + object children + array items 三层都包 vuedraggable）
- 修改：`packages/web/src/views/admin/FieldCard.vue`（"复制子树"按钮 + 拖拽 handle + 折叠状态）
- 修改：`packages/web/src/views/admin/FieldEditor.vue`（如 vuedraggable 集成需要把 local computed 改为 v-model emit）
- 可能新增：`packages/web/src/views/admin/FieldItem.spec.ts`（若项目已用 vitest）或 `packages/web/src/views/admin/TemplateEditorView.spec.ts`
- 修改：`docs/01-product-planning/02-milestones/02-growth-phase.md`（AC-17）
- 修改：`docs/01-product-planning/04-backlog.md`（AC-17）
- 修改：`docs/03-engineering-governance/current-work.md`（AC-17）

后端 0 文件改动；现有 `test_template.py` / `test_structured_data_contract.py` / `test_extract_template_prompts.py` / `test_p1_demo.py` 不修改。

## 文件计划

业务代码改动（前端 4 个核心文件 + 可能的测试文件）：

- `packages/web/src/views/admin/TemplateEditorView.vue`（拖拽 root 集成 + 撤销 toast + 折叠/展开按钮 + 搜索框）
- `packages/web/src/views/admin/FieldItem.vue`（vuedraggable 三层集成 + 搜索过滤）
- `packages/web/src/views/admin/FieldCard.vue`（"复制子树"按钮 + 拖拽 handle）
- `packages/web/src/views/admin/FieldEditor.vue`（如需调整 local computed；否则不修改）
- `packages/web/src/views/admin/FieldItem.spec.ts` 或同等测试文件（可选，仅当项目已用 vitest）

文档改动：

- `docs/01-product-planning/02-milestones/02-growth-phase.md`（Open Items REQ-002-1 行）
- `docs/01-product-planning/04-backlog.md`（REQ-002-1 状态推进）
- `docs/03-engineering-governance/current-work.md`（REQ-002-1 移入"当前进行中"）

后端 0 文件；DB schema 0 文件；API 契约 0 文件。

## 风险与边界

1. **vuedraggable 与 Vue 3 兼容性**：vuedraggable 4.1.0 是 Vue 3 兼容版本，但需确认与项目当前 Vue 3.x 版本兼容（`packages/web/package.json` 检查）。如不兼容，需升级 vuedraggable 或更换为 `vue-draggable-plus` / `vue-draggable-next`。
2. **拖拽与 FormData 双向同步**：当前 `form.fields` 是 v-model 双向绑定的 ref，vuedraggable 集成需要保证拖拽后 `update:modelValue` 事件正常 emit；现有 `FieldItem.vue` 已有 `update:modelValue` emit 机制，应可复用。
3. **深拷贝子树时的 key 冲突**：复制 object 子树时，递归子字段 key 也需加 `_copy_N` 后缀，避免与现有兄弟字段冲突。算法：在 parent 已有 keys 集合中找下一个不冲突的 N（从 1 开始递增）。
4. **撤销按钮 5 秒超时**：实现方式可用 `setTimeout` + `ref`；如超时前用户再次删除，需要重置计时器到 5 秒（只支持单次撤销）。
5. **大模板搜索的性能**：递归统计 `totalFields` 一次（在 computed 中），避免每次按键都重算。30 字段是经验阈值；如实际场景常用 50+ 字段，可考虑虚拟滚动（本次不实现）。
6. **拖拽 handle UX**：vuedraggable 默认整行可拖；为避免误拖，添加拖拽 handle（如 FieldCard 左侧的"⋮⋮"图标）让用户明确拖拽区域。本次实现至少 1 个 handle 即可。
7. **vuedraggable 在 vue-tsc 严格模式下的类型**：可能需要 `@ts-expect-error` 或 `defineComponent` 包装；如类型问题无法解决，在 plan 中保留"按需加 ts-expect-error 注释"的退路。
8. **不触发 schema_version 递增**：按 Q6 决议，拖拽只影响字段顺序（fields 数组重排），不属于"破坏性变更"。前端调用 `templateApi.update` 时 payload 的 `schema_version` 必须与原值一致（不递增），不传 `schema_version` 也可（服务端保留原值）；具体由 REQ-002-4 决定。
9. **行为不变承诺**：
   - API 契约：DTO 形状不变（AC-13）。
   - 后端：0 文件改动。
   - DB schema：不变。
   - 溯源字段：REQ-002-3 已落盘的 `{id, version, layer, ...data}` 不受影响（AC-12）。
   - 既有按钮 / 递归渲染：保持工作（AC-11）。

## 行为变化声明

| 项 | 变化 |
|----|------|
| TemplateEditorView 顶部 | 新增"全部折叠 / 全部展开"按钮 + "按 label / key 搜索字段"输入框（仅当 `totalFields > 30` 时） |
| FieldCard 卡片 | 新增"复制子树"按钮（与"删除"按钮并列）；新增拖拽 handle（左侧"⋮⋮"图标） |
| FieldItem 渲染 | 整合 vuedraggable 包裹 root / object children / array items 三层 |
| 字段删除反馈 | 顶部 toast 含"撤销"按钮（5 秒超时） |
| API 契约 | 不变 |
| DB schema | 不变 |
| `template.fields` 数据结构 | 不变（仅顺序变化） |
| 既有按钮（添加子字段 / 添加列 / 删除） | 不变 |
| FieldEditor 递归渲染 | 不变 |
| REQ-002-3 溯源卡 | 不影响 |
| vuedraggable 依赖 | 已在 `package.json`，无需新增依赖 |

## 依赖与执行顺序

- **依赖**：REQ-002-3 已合并（提供 `{id, version, layer, ...data}` 落盘基线，避免本任务的 schema_version 兼容性问题）。
- **被依赖**：REQ-002-2（复用机制）需要在"复制模板"功能上复用本任务的"子树复制"能力；REQ-002-4（可维护性）需要在"容器互转"时复用本任务的拖拽 handle 能力。
- 与 REQ-002-3 关系：本任务**不**改后端代码，**不**改 `_merge_template_structured_data` 行为；REQ-002-3 已落盘的 contract 完全保持。
- 与 TD-009（shared schema gate）无关：DTO 形状不变。
- 与 TD-029（shared schema）无关：前端 UI 改动，不动 schema 文件。
- 与 TD-032（large source files）相关：本任务不新增大型源文件，但 FieldItem.vue 集成 vuedraggable 后行数会增加；按 TD-032 基线，FieldItem.vue 当前行数应远低于 800 行上限；如有顾虑，提交后跑 `scripts/scan-source-sizes --diff` 确认。

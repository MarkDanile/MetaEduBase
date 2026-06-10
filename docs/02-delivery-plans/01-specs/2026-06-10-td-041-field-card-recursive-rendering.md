# TD-041: FieldCard 递归渲染嵌套字段 + object children / array items 嵌套拖拽 — Spec

> Spec 入口：TD-041（技术债，补齐 REQ-002-1 AC-2/AC-3）。本文件是验收口径与边界的事实源；实施拆分见 `docs/02-delivery-plans/02-plans/2026-06-10-td-041-field-card-recursive-rendering-plan.md`。
> 来源：[REQ-002-1 Spec AC-2/AC-3](2026-06-10-req-002-1-template-config-ux.md) 部分完成；[TD-041 任务卡](../../03-engineering-governance/technical-debt.md#td-041)。

## 目标

把 TemplateEditorView 的嵌套字段从"不可见、不可拖拽"升级为"递归可见、同层可拖拽"，完成 REQ-002-1 的 AC-2（object 子字段拖拽排序）和 AC-3（array items 拖拽排序）。

变更前：FieldCard 展开后 object / array 子区域只有空态占位 + "添加子字段"按钮，`node.children` / `node.items` 不渲染；FieldItem 只在 root 层用 vuedraggable 包裹。
变更后：FieldCard 展开后递归渲染子字段（FieldList 组件），每层独立 draggable 支持同层拖拽排序；事件正确冒泡；深度缩进清晰。

## 范围

### 包含

- **新建 FieldList.vue 递归组件**：包裹 `<draggable>` + `<FieldCard>`，递归渲染 children/items
- **FieldCard.vue 递归渲染改造**：object 子字段区域和 array items 区域从空态占位改为 FieldList 递归渲染
- **FieldItem.vue 重构**：root 层改用 FieldList；修 copySubtree 支持任意深度；修 removeColumn 事件 relay
- **TemplateEditorView.vue 修复**：toggleAllCollapse 改为直接调用 FieldItem 方法
- **expand 状态管理集中化**：从 FieldCard 本地 ref 改为 FieldItem expandedIds 集中管理
- **Bug 修复**：removeColumn 硬编码 colIndex=0；copySubtree 只在 root 层生效
- **深度守卫**：MAX_DEPTH=5 防止畸形数据无限递归

### 不包含

- **不**引入跨层级拖拽（vuedraggable `group` prop 留 follow-up）
- **不**改后端任何文件
- **不**改 Field 类型定义（`template.ts`）
- **不**改 TemplateFormFields.vue（通过 FieldItem 自动获得递归能力）
- **不**改 FieldEditor.vue（legacy 组件，不在 admin flow 使用）
- **不**实现完整 undo/redo 栈
- **不**实现 keyboard 快捷键拖拽

## 验收标准

| ID | 验收点 | 通过条件 | 失败条件 |
|----|--------|----------|----------|
| AC-1 | Object 子字段可见 | 展开 object 字段后，`node.children` 中的子字段以 FieldCard 形式递归渲染可见 | 子字段不可见 / 只显示空态 |
| AC-2 | Object 子字段拖拽排序 | 在 object 子字段列表中拖拽改变顺序；保存后 `template.fields[].children` 数组顺序与拖拽一致 | 子字段拖拽无效 / 顺序错乱 |
| AC-3 | Array items 可见 | 展开 array 字段后，`node.items` 中的成员模板以 FieldCard 形式递归渲染可见 | 成员模板不可见 / 只显示空态 |
| AC-4 | Array items 拖拽排序 | 在 array items 列表中拖拽改变顺序；保存后 `template.fields[].items` 数组顺序与拖拽一致 | items 拖拽无效 / 顺序错乱 |
| AC-5 | 递归深度缩进 | 嵌套层级越深，视觉缩进越明显（margin-left + border-left） | 所有层级缩进相同 / 深层无缩进 |
| AC-6 | 事件正确冒泡 | 嵌套 FieldCard 的 remove / updateField / changeType / addChild / addColumn / removeColumn / copySubtree 事件正确冒泡到 FieldItem 和 TemplateEditorView | 嵌套字段操作无效 / 操作错误目标 |
| AC-7 | 折叠/展开全部 | "全部折叠/全部展开"按钮在嵌套场景下正确工作 | 深层字段不响应折叠/展开 |
| AC-8 | removeColumn 修复 | 删除第 N 列时正确删除该列（非总是第 0 列） | 总是删除第 0 列 |
| AC-9 | copySubtree 修复 | 在嵌套字段上点击"复制子树"，在正确层级追加深拷贝 | 只在 root 层生效 / 复制位置错误 |
| AC-10 | 搜索过滤兼容 | 搜索框在嵌套字段场景下正确过滤和 dim | 嵌套字段搜索失效 |
| AC-11 | 不引入跨层级拖拽 | 字段只能在本层级内拖拽排序，不能跨层级拖入拖出 | 出现跨层级拖拽 |
| AC-12 | 前端 typecheck + lint | `cd packages/web && pnpm typecheck` 退出码 0；`pnpm lint` 退出码 0 | 退出码非 0 |
| AC-13 | 工程门禁 | `scripts/check-engineering-docs` 退出码 0；`git diff --check` 干净 | 退出码非 0 |

## 接口与依赖

改动文件（全部前端，0 个后端文件）：

- 新增：`packages/web/src/views/admin/FieldList.vue`
- 修改：`packages/web/src/views/admin/FieldCard.vue`
- 修改：`packages/web/src/views/admin/FieldItem.vue`
- 修改：`packages/web/src/views/admin/TemplateEditorView.vue`

现有 API / DTO / schema 不变。

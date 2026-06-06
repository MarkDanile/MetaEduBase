# 数据要素模板配置 — 设计文档

> 日期: 2026-05-27
> 状态: 待实现
> 范围: 模板管理前端 + 后端 API + 文档管道集成

---

## 1. 概述

为资源库提供可配置的结构化数据抽取模板。用户可以预设各类文档（教案、课程标准、授课计划、实训手册等）的数据要素抽取结构，每个模板支持多层嵌套字段（含表格类型）。上传文档后系统根据 doc_type 自动匹配对应模板，由 AI 完成结构化抽取。

---

## 2. 字段模型

### 2.1 字段类型

| 类型 | 说明 | 渲染 | 编辑 |
|------|------|------|------|
| `text` | 单行文本 | 文本展示 | `<input>` |
| `textarea` | 多行文本 | 文本展示 | `<textarea>` |
| `number` | 数字 | 数字 | `<input type="number">` |
| `object` | 可折叠对象组 | 折叠区块 | 点击展开子字段 |
| `table` | 表格（含列定义） | 表格 | 添加/删除行，支持导出 |
| `array` | 同类对象数组 | 卡片列表 | 添加/删除项 |

### 2.2 字段结构

```typescript
// 基础字段（叶子节点）
type TextField = {
  key: string;
  label: string;
  type: "text" | "textarea" | "number";
  description?: string;
}

// 对象组（父节点）
type ObjectField = {
  key: string;
  label: string;
  type: "object";
  children: Field[];
  description?: string;
}

// 表格字段（含列定义）
type TableField = {
  key: string;
  label: string;
  type: "table";
  columns: {
    key: string;
    label: string;
    type: "text" | "textarea" | "number";
    width?: string;
  }[];
  description?: string;
}

// 数组字段
type ArrayField = {
  key: string;
  label: string;
  type: "array";
  items: Field[];  // 通常为 object
  description?: string;
}

type Field = TextField | ObjectField | TableField | ArrayField;
```

### 2.3 示例：教案模板

```json
{
  "name": "教案模板",
  "doc_types": ["教案"],
  "fields": [
    { "key": "course_name", "label": "课程名称", "type": "text" },
    {
      "key": "teaching_objectives",
      "label": "教学目标",
      "type": "array",
      "items": [
        { "key": "type", "label": "目标类型", "type": "text" },
        { "key": "description", "label": "目标描述", "type": "textarea" }
      ]
    },
    {
      "key": "class_schedule",
      "label": "课时安排",
      "type": "table",
      "columns": [
        { "key": "period", "label": "课时", "type": "text" },
        { "key": "content", "label": "教学内容", "type": "textarea" },
        { "key": "method", "label": "教学方法", "type": "text" },
        { "key": "hours", "label": "课时数", "type": "number" }
      ]
    },
    {
      "key": "key_points",
      "label": "重点难点",
      "type": "object",
      "children": [
        { "key": "key", "label": "重点", "type": "textarea" },
        { "key": "difficult", "label": "难点", "type": "textarea" }
      ]
    }
  ]
}
```

---

## 3. 数据模型

### 3.1 数据库表

**表名**：`templates`

```sql
CREATE TABLE templates (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  name VARCHAR(100) NOT NULL,
  doc_types VARCHAR(50)[] NOT NULL,  -- 关联文档类型数组
  fields JSONB NOT NULL,              -- 嵌套字段定义
  ai_prompt TEXT,                     -- AI 抽取提示词模板
  source_file_id UUID,                -- 样例文档 ID（可选）
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(tenant_id, name)
);

CREATE INDEX templates_tenant_id_idx ON templates(tenant_id);
```

**说明**：
- `tenant_id` 多租户隔离
- `fields` 用 JSONB 存储嵌套结构，充分利用 PostgreSQL 的 JSONB 查询能力
- `ai_prompt` 用于覆盖默认抽取 prompt（可选）
- `source_file_id` 关联样例文档，用于 AI 初始化时分析文档结构

### 3.2 structured_data 更新

文件抽取结果 `structured_data` 结构：

```json
{
  "template": { ... },       -- 模板抽取结果（符合模板 fields 结构）
  "full_text": "...",
  "section_count": N,
  "template_id": "uuid"      -- 使用的模板 ID
}
```

---

## 4. API 设计

### 4.1 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/templates` | 列出当前租户所有模板 |
| GET | `/api/v1/templates/{id}` | 获取单个模板 |
| POST | `/api/v1/templates` | 创建模板 |
| PUT | `/api/v1/templates/{id}` | 更新模板 |
| DELETE | `/api/v1/templates/{id}` | 删除模板 |
| POST | `/api/v1/templates/init-by-ai` | AI 初始化字段 |

### 4.2 请求/响应

**POST /api/v1/templates/init-by-ai**

请求：
```json
{
  "doc_type": "实训手册",
  "source_file_id": "uuid"  // 可选，上传样例文档
}
```

响应：
```json
{
  "fields": [
    { "key": "course_name", "label": "课程名称", "type": "text" },
    {
      "key": "class_schedule",
      "label": "课时安排",
      "type": "table",
      "columns": [...]
    }
  ]
}
```

**后端逻辑**：
1. 如果提供了 `source_file_id`，读取对应文档文本内容（前 N 个 chunk）
2. 构造 prompt，让 MiniMax-M2 分析职教文档结构，生成嵌套字段 JSON
3. 返回 `fields` 数组

---

## 5. 文档管道集成

### 5.1 模板匹配流程

文件上传时：

```
上传文件 → 保存 files 表（记录 doc_type）→ 派发 extract_template
                                              ↓
                              查询 doc_type 对应的模板
                                              ↓
                    ┌─────────────────┬──────────────────┐
                    有匹配模板              无匹配模板
                    ↓                      ↓
            用模板的 fields         用默认 prompt（教案/课程标准/授课计划）
            + ai_prompt                   ↓
            生成抽取 prompt        硬编码 prompt
                    ↓                      ↓
                    ←───────────────→ LLM 抽取
                                              ↓
                              填充 structured_data.template
                                              ↓
                              files.structured_data.template_id = 模板ID（如果有）
```

### 5.2 extract_template 任务修改

修改 `packages/server-python/app/contexts/document/application/tasks.py` 中的 `extract_template`：

```python
async def extract_template(file_id: str):
    # 1. 查询文件 doc_type
    file = await file_repo.get(file_id)
    doc_type = file.doc_type

    # 2. 查询匹配的模板（按 doc_type 匹配）
    template = await template_repo.get_by_doc_type(doc_type, file.tenant_id)

    # 3. 根据模板构建 prompt
    if template:
        fields_json = json.dumps(template.fields, ensure_ascii=False)
        prompt = f"根据以下文档内容，提取 JSON 格式的结构化信息。字段定义：{fields_json}。只返回 JSON..."
        # 用 template.ai_prompt 或默认格式覆盖
        if template.ai_prompt:
            prompt = template.ai_prompt
    else:
        # 回退默认 prompt
        prompt = DEFAULT_PROMPT_MAP.get(doc_type, DEFAULT_PROMPT)

    # 4. 调用 LLM 抽取
    result = await call_llm(prompt, file.full_text)

    # 5. 解析并存储
    structured = json.loads(result)
    await file_repo.update_structured_data(file_id, {
        "template": structured,
        "template_id": template.id if template else None
    })
```

---

## 6. 页面设计

### 6.1 入口

**路径**：`/admin/template`

作为后台管理的子菜单项，URL 为 `/admin/template`。

### 6.2 列表页

- 模板卡片网格布局（`ui-panel`）
- 每张卡片：模板名称、关联类型标签（`liquid-tag-blue`）、字段数量、创建时间
- 操作：编辑、删除（`ConfirmDialog`）
- 右上角「新建模板」按钮

### 6.3 新建模板弹框（主交互）

点击「新建模板」弹出 Modal，左右分栏布局（`xl:grid-cols-[1fr_280px]`）：

**左列 — 模板配置表单**：
- 模板名称（`liquid-input`）
- 关联文档类型（多选下拉，支持从预设选择或手动输入）
  - 点击「+ 添加类型」展开输入区（输入框 + 预设下拉选择）
  - **同模板内重复检测**：输入已有类型时显示警告「此类型已存在于此模板中，每个类型只能添加一次」
  - **跨模板重复检测**：选择其他模板已用的类型时显示警告「此类型已被其他模板使用，上传文档时将匹配多个模板」
  - 两种情况均弹出确认框，用户可选择继续添加或取消
- 字段列表（AI 生成后展示，支持手动增删调整）

**右列 — AI 初始化面板**（嵌入弹框内）：
- 标题「AI 辅助配置」
- 输入：文档类型名（`liquid-input`）
- 上传：样例文档上传（拖拽区 `ui-panel-muted border-2 border-dashed`）
- 按钮：「重新生成字段」
- 结果预览：返回的 fields 以卡片列表展示
- 点击「应用」填充到左列字段列表

**弹框 Footer**：「取消」+ 「保存模板」

### 6.4 编辑页

**布局**：左右分栏（`xl:grid-cols-[1fr_300px]`）

**左列 — 模板配置表单**：
- 与新建弹框相同，支持编辑名称、类型、字段
- 字段列表显示已有字段，支持展开编辑、增删调整

**右列 — AI 重新生成面板**：
- 与新建页右列相同，增加覆盖确认提示
- **覆盖警告**：显示「重新生成将用新结果完全覆盖当前字段，请确认是否继续」
- 点击「覆盖生成」后，用新的 AI 结果替换所有现有字段

### 6.4 抽取结果展示（FileDetailView 增强）

现有「结构化抽取」Tab 增强：

- **字段匹配提示**：如果使用了模板，显示「模板：{template_name}」
- **表格渲染**：table 类型字段渲染为 HTML 表格（`<table>` + `ui-panel-muted` 行）
- **对象折叠**：object 类型渲染为可折叠区块（`<details>` / Vue `<Transition>`）
- **数组渲染**：array 类型渲染为卡片列表
- **编辑功能**（可选 v2）：支持直接在页面修改抽取结果并保存

---

## 7. 前端组件

### 7.1 新增组件

| 组件 | 路径 | 说明 |
|------|------|------|
| `TemplateListView.vue` | `src/views/admin/TemplateListView.vue` | 模板列表页 |
| `TemplateEditorView.vue` | `src/views/admin/TemplateEditorView.vue` | 模板编辑页 |
| `FieldEditor.vue` | `src/components/FieldEditor.vue` | 字段编辑器（支持递归嵌套） |
| `TableRenderer.vue` | `src/components/TableRenderer.vue` | 表格类型渲染/编辑 |

### 7.2 字段编辑器交互

`FieldEditor.vue` 支持递归渲染：

- 根据 `field.type` 渲染对应编辑器
- `object` 类型：递归渲染 `children` 数组，支持增加/删除子字段
- `table` 类型：列定义编辑器（key、label、type 三列），下方显示行数据表格
- `array` 类型：渲染「数组项模板」，支持预览已有数据条目
- 拖拽排序：`vuedraggable` 包裹整个字段列表

---

## 8. 实现步骤（待拆分）

1. **后端：数据库迁移** — 创建 `templates` 表
2. **后端：Template CRUD API** — 基本增删改查
3. **后端：AI 初始化接口** — `/init-by-ai`
4. **后端：模板匹配逻辑** — 修改 `extract_template` 任务
5. **前端：路由和菜单** — 添加 `/admin/template` 路由
6. **前端：列表页** — `TemplateListView.vue`
7. **前端：编辑页基础** — `TemplateEditorView.vue` 表单
8. **前端：字段编辑器** — `FieldEditor.vue`（递归 + 拖拽）
9. **前端：AI 初始化面板** — 右列 AI 辅助
10. **前端：FileDetailView 增强** — 表格/对象/数组渲染
11. **集成测试** — 完整流程验证

---

## 9. 技术要点

- **JSONB 存储**：PostgreSQL JSONB 类型存储嵌套 fields，支持索引查询
- **递归渲染**：Vue 组件递归渲染复杂字段结构，注意组件名注册
- **拖拽排序**：`vuedraggable`（基于 Sortable.js），fields 数组整体拖拽
- **AI prompt 构建**：需要合理设计 prompt，让 LLM 输出符合字段模型的嵌套 JSON
- **向后兼容**：无匹配模板时回退到现有默认 prompt，不破坏现有功能
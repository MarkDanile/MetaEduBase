# 模板 AI 补充上下文（ai_context）设计方案

## Context

用户希望在大模型自动抽取字段之外，能够补充领域专家知识，扩展 AI 的理解范围。例如课程标准模板需要额外说明"包含前置能力与知识基础"、护理模板需要补充"重点关注生命体征测量"等。

当前 `init_by_ai` 只接收 doc_type 和可选的 sample document，缺少用户自定义的领域上下文注入通道。

## 设计方案

### 1. 数据模型

**模板 DTO** (`packages/server-python/app/contexts/template/application/dto.py`):
```python
class TemplateUpdate(BaseModel):
    ai_context: str | None = None  # 新增

class TemplateResponse(BaseModel):
    ai_context: str | None  # 新增
```

**数据库**: 无需新增列，`ai_prompt` 字段用途已明确定位，`ai_context` 作为 `ai_prompt` 的一部分传入即可（不改 schema）。

### 2. 后端逻辑

**system prompt 拼接**（`init_by_ai`）:
```
原 system_prompt = "你是一个专业的教育领域数据提取助手..."

新增: 如果 template.ai_context 非空，则追加:
"\n\n补充上下文：" + template.ai_context
```

### 3. 前端 UI

**模板编辑页**（`TemplateEditorView.vue`）：
- 在"AI 提示词"卡片底部（或字段列表下方）增加 `<textarea>`，placeholder="补充说明（可选）——如：课程标准模板可写"需包含前置能力与知识基础""
- v-model 绑定到 `form.ai_context`
- 提交时随模板保存

**模板 Modal**（`TemplateModal.vue`）：
- 同理，AI 辅助配置区也透传此字段（弹窗关闭后下次生成生效）

### 4. 工作流程

```
1. 用户在模板编辑页填 ai_context："需包含前置能力与知识基础"
2. 保存模板
3. 调用 AI 生成时，system_prompt 追加:
   "补充上下文：需包含前置能力与知识基础"
4. AI 生成时结合领域专家知识生成更准确的字段
```

### 5. 验证

1. 创建课程标准模板，ai_context="需包含前置能力与知识基础"
2. AI 生成字段，确认包含前置能力相关字段
3. 不填 ai_context，AI 按通用逻辑生成，字段应少于或不同于填了上下文的情况

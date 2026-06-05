# TD-009: 结构化抽取结果契约容器治理

> 状态：🟡 进行中
> 优先级：P2
> 领域：API / 类型
> 类型：技术债
> 事实源：[technical-debt.md#td-009-减少前后端契约漂移](../engineering/technical-debt.md#td-009-减少前后端契约漂移)
> 计划：[plans/2026-06-05-td-009-structured-data-contract-plan.md](../plans/2026-06-05-td-009-structured-data-contract-plan.md)

## 1. 背景

TD-009 要减少前后端契约漂移。本轮选择的高价值契约族是 `FileDTO.structured_data` 中的结构化抽取结果容器。

当前链路中，后端解析任务先把解析结果写入 `files.structured_data`：

- `parse_document` 写入 `full_text` 与 `section_count`。
- `chunk_document` 读取 `structured_data.full_text` 继续分块。
- `extract_template` 在既有 JSON 上追加 `template`。
- 前端 `FileDetailView` 直接把 `file.structured_data` 强转为 `Record<string, unknown>` 并读取 `template`。

这使 `template` 成为隐式 API 契约：后端写入、前端读取，但契约事实源目前只是 `dict | None` / `Record<string, unknown> | null`。

## 2. 问题

1. `structured_data` 的容器形态没有显式共享 schema，后端、前端和 UI helper 都无法表达哪些 key 是稳定契约。
2. 前端展示层直接强转 `structured_data["template"]`，如果后端写入数组、字符串、`null` 或历史脏数据，typecheck 无法捕获。
3. 后端写入路径没有聚焦测试锁定“解析容器 + template object 合并”的形态，后续改动可能无意改变容器 key 或 value 类型。
4. 完整模板字段值递归校验虽然价值高，但会把本任务扩展到模板字段契约和 LLM 输出值校验，超出 TD-009 本轮最小治理范围。

## 3. 目标与不目标

### 3.1 目标

1. 在 `packages/shared` 建立 `FileStructuredDataSchema`，作为前端可复用的结构化抽取结果容器事实源。
2. 容器 schema 明确以下稳定字段：
   - `full_text?: string`
   - `section_count?: number`
   - `template?: Record<string, unknown>`
3. schema 保持 `passthrough`，允许历史和未来额外 key，不破坏既有数据。
4. 前端 `FileDTO.structured_data` 使用 shared 类型，`FileDetailView` 读取 `template` 前通过 shared helper 或 schema parse/narrow，避免直接强转。
5. 后端补聚焦测试或小 helper 测试，锁定 parse/extract 写入的容器 shape：`full_text` 是 string、`section_count` 是 number、`template` 是 object，并且追加 `template` 时保留既有 parse 字段。
6. typecheck 或测试能捕获所选容器契约族的字段不匹配，例如 `template` 被写成非 object，或前端把 `structured_data` 当作任意 unknown record 强转读取。

### 3.2 不目标

- 不校验 `template` 内每个字段值是否符合模板字段定义。
- 不引入跨语言 schema 生成器。
- 不把后端 `FileDTO.structured_data` response model 改成强 Pydantic model，避免历史数据 shape 导致响应层破坏性变化。
- 不改变 LLM prompt、抽取内容、任务链路或用户可见展示文案。
- 不处理任务状态 / pipeline 契约漂移；扫描中发现的 `ds_embed` 前后端差异可作为后续技术债登记。
- 不处理模板字段契约重复；该方向可作为 TD-009 后续切片或新 TD。

## 4. 设计方案

### 4.1 Shared schema

新增 `packages/shared/src/schemas/document.ts`，导出：

```ts
import { z } from "zod";

export const JsonObjectSchema = z.record(z.string(), z.unknown());

export const FileStructuredDataSchema = z.object({
  full_text: z.string().optional(),
  section_count: z.number().optional(),
  template: JsonObjectSchema.optional(),
}).passthrough();

export type FileStructuredData = z.infer<typeof FileStructuredDataSchema>;

export function parseFileStructuredData(
  value: unknown,
): FileStructuredData | null {
  if (value == null) return null;
  const result = FileStructuredDataSchema.safeParse(value);
  return result.success ? result.data : null;
}

export function getTemplateStructuredData(
  value: unknown,
): Record<string, unknown> | null {
  return parseFileStructuredData(value)?.template ?? null;
}
```

`JsonObjectSchema` 名称可在实现时按现有 shared 风格调整；关键是 `template` 只允许普通 object，不允许数组、字符串或 null 进入展示层。

`packages/shared/src/schemas/index.ts` 需要导出 document schema。

### 4.2 前端 service 与 UI 窄化

`packages/web/src/services/document.ts` 的 `FileDTO.structured_data` 从 `Record<string, unknown> | null` 改为：

```ts
import type { FileStructuredData } from "@metaedu/shared/schemas/document";

structured_data: FileStructuredData | null;
```

`FileDetailView` 的 `templateData` 不再直接强转：

```ts
const templateData = computed(() => getTemplateStructuredData(file.value?.structured_data));
```

这样模板展示逻辑只接收已窄化的 `Record<string, unknown> | null`。如果后端返回非 object 的 `template`，展示层得到 `null`，不会把错误 shape 当成有效抽取结果。

### 4.3 后端契约锁定

后端不改 API response model 强度，避免影响历史数据响应兼容。实现时优先用最小 helper 或纯函数测试锁定写入形态，例如：

- 解析阶段容器包含 `full_text: str` 与 `section_count: int`。
- 追加 template 时保留原有 `full_text` / `section_count`。
- `template_data` 以 dict/object 写入 `structured_data["template"]`。

如果直接测试 Celery task 成本过高，可抽出小的纯函数，例如 `build_parsed_structured_data(full_text, section_count)` 和 `merge_template_structured_data(existing, template_data)`，并只测试这两个纯函数。抽函数必须是手术式改动，不改变 SQL 写入、任务顺序或异常处理。

### 4.4 兼容策略

- shared schema `passthrough` 保留未知 key。
- `structured_data` 为 `null` 或 schema parse 失败时，前端按无抽取结果处理。
- `template` 缺失或非 object 时，前端按无模板抽取结果处理。
- 不清理历史数据库记录，不做迁移。

## 5. 验收标准

1. `packages/shared` 有结构化抽取结果容器 schema/type/helper，并从 schema index 导出。
2. 前端 `FileDTO.structured_data` 复用 shared 类型。
3. `FileDetailView` 不再使用 `as Record<string, unknown>` 读取 `structured_data["template"]`。
4. 后端有聚焦测试覆盖 parse/extract 写入容器 shape，或有等价的 helper 单元测试。
5. 所选契约族字段不匹配能被验证捕获：
   - 前端：`template` 读取必须经过 schema/helper narrow。
   - 后端：写入 helper 测试能捕获 `template` 非 object 或 parse 字段丢失。
6. TD-009 文档状态同步到 `current-work.md` 和 `technical-debt.md`。

## 6. 验证计划

必跑：

- `pnpm --filter @metaedu/shared typecheck`
- `pnpm --filter @metaedu/web typecheck`
- 后端新增/调整的聚焦 pytest，例如 `cd packages/server-python && .venv/bin/python -m pytest tests/contexts/document/<target-test>.py -q`
- `scripts/check-engineering-docs`

视改动范围追加：

- 如果新增 shared 测试脚本或现有 test runner 可用，补跑 shared schema 单元测试。
- 如果改动 Python 任务 helper，运行 `cd packages/server-python && .venv/bin/python -m ruff check app/contexts/document/application/tasks.py tests/contexts/document/<target-test>.py`。
- 如果触及前端展示逻辑较多，补跑 `pnpm --filter @metaedu/web lint`。

## 7. 风险与回滚

| 风险 | 影响 | 缓解 |
|------|------|------|
| shared schema import 路径与当前 workspace 配置不一致 | 前端 typecheck 失败 | 按现有 package exports 使用 `@metaedu/shared/schemas/document`，以 typecheck 为准 |
| 历史 `structured_data.template` 不是 object | 前端不展示抽取结果 | 本轮不迁移历史数据；schema 窄化使错误 shape 显式变成 null |
| 后端纯函数抽取过度重构任务文件 | 扩大 TD-009 范围 | 只抽写入容器构造/合并小函数，不改任务链路 |
| 完整字段值校验延期 | 仍可能存在 template 内部字段值漂移 | 明确登记为非目标，后续可拆新 TD |

## 8. 行为变化声明

本轮目标是契约显式化，不改变正常数据下的用户可见行为。

可观察边界变化：如果后端或历史数据把 `structured_data.template` 写成非 object，前端将不再强转并尝试展示，而是按无抽取结果处理。这是有意的防御性窄化，用于暴露并隔离契约漂移。正常 `template` object 的展示应保持不变。

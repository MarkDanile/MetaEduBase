# Contracts — 前后端契约规范

本规范用于减少后端 Pydantic DTO、前端 service 类型、`packages/shared` schema/type 之间的漂移。当前项目还没有全量自动生成契约，规则以渐进治理为主。

## 当前事实

- 后端请求/响应契约主要定义在 `packages/server-python/app/contexts/*/application/dto.py`，并通过 router 的 `response_model` 暴露。
- 前端调用集中在 `packages/web/src/services/*`，部分 DTO 在 service 文件中手写。
- `packages/shared` 已有 Zod schemas 和 TypeScript types，但尚未覆盖所有 API 契约。
- 状态字段、枚举和业务映射同时存在于后端字符串字段、前端 constants 和 shared schemas 中，存在漂移风险。

## 契约所有权

| 契约类型 | 事实源 | 同步位置 |
|----------|--------|----------|
| 后端 API 请求/响应 | Pydantic DTO + router `response_model` | 前端 service DTO / shared schema |
| 跨页面复用的前端类型 | `packages/shared/src/types` 或 `packages/shared/src/schemas` | 各 service / composable |
| 仅单个页面使用的展示类型 | 页面或局部 composable | 不提升到 shared |
| 状态值 / 枚举 | 后端枚举或明确的常量集合 | 前端 constants / shared schema |
| 错误语义 | FastAPI `HTTPException` status + detail | 前端错误处理与文案映射 |

如果同一个字段同时被后端、前端多个页面、任务流程或测试依赖，应优先提升为显式契约，而不是继续散落手写。

## API 变更规则

新增或修改 API 时，必须明确它是兼容变更还是破坏性变更。

兼容变更：
- 新增可选响应字段。
- 新增可选请求字段，并提供后端默认值。
- 新增不影响既有调用的过滤参数。

破坏性变更：
- 删除或重命名字段。
- 修改字段类型或枚举取值。
- 修改必填性、默认值、分页结构或错误状态码。
- 改变任务状态流、文件状态流或异步轮询语义。

破坏性变更必须同步更新相关 spec/plan 或当前任务卡片，并在最终回复中明确说明影响范围。

## 修改步骤

1. 定位端点：记录 method、path、request DTO、response DTO 和调用它的前端 service。
2. 更新后端：修改 Pydantic DTO、router `response_model`、必要的 repository/service 返回值。
3. 更新前端：修改 `packages/web/src/services/*` 的 DTO 和调用适配，避免在 view 中直接拼装后端响应结构。
4. 更新 shared：当类型跨多个页面、包或测试复用时，补充 `packages/shared/src/types` 或 `packages/shared/src/schemas`。
5. 更新文档：API、Schema 或状态流发生变化时，按 `docs/engineering/rules/docs.md` 同步相关文档。
6. 验证：按 `docs/engineering/rules/quality-gates.md` 运行 API/DTO/Schema 对应验证。

## 前端调用约束

- API 调用优先集中在 `packages/web/src/services/*`，页面组件不直接散落 `api.get/post`，除非是历史代码或一次性内部页面。
- Service DTO 应表达后端真实响应，不要为了页面展示随意改名字段。
- 页面展示需要的派生字段应在 composable、adapter 或 computed 中生成，不反向污染 API DTO。
- 不要使用 `unknown as SomeDTO` 或双重断言掩盖后端响应与前端 DTO 不一致。确有必要跨类型转换时，新增命名明确的 adapter，并在 adapter 中处理默认值、字段缺失和类型差异。
- 任务状态、文件状态、知识图谱状态等有限集合，不要在多个页面重复手写字符串判断；优先复用 constants 或 shared schema。

## 后端响应约束

- Router 负责认证、参数解析、异常映射和 response model；复杂业务组装放到 application service 或 repository。
- 响应 DTO 字段命名保持稳定，默认使用 `snake_case`，前端类型也按接口真实字段书写。
- 返回列表时明确是否分页。不要让同一端点在不同条件下有时返回数组、有时返回对象。
- 错误状态码保持语义稳定：认证/授权、资源不存在、参数错误、业务冲突不要混用同一个状态码。

## 验证建议

| 改动类型 | 必跑验证 |
|----------|----------|
| 后端 DTO 或 router 变更 | 相关 pytest；至少覆盖成功响应和关键错误响应 |
| 前端 service DTO 变更 | `pnpm --filter @metaedu/web typecheck` |
| shared schema/type 变更 | `pnpm --filter @metaedu/shared typecheck` + 前端 typecheck |
| 状态流或枚举变更 | 后端相关测试 + 前端涉及页面的 typecheck / 手动验证 |

如果当前项目缺少能覆盖契约的测试，应把缺口记录到任务卡片或 `docs/engineering/technical-debt.md`，不要只在最终回复里口头说明。

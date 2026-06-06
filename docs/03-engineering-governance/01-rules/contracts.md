# Contracts — 契约治理

本文件记录 MetaEduBase 的长期契约治理规则，用于减少后端 DTO、前端 service 类型和 `packages/shared` schema/type 之间的漂移。它关注的是所有权、变更边界、同步步骤和验证基线，而不是某次具体任务的临时修补细节。

## 这份文档回答什么

- 哪类契约由谁拥有
- 什么情况下应该提升到 `packages/shared`
- 什么算兼容变更，什么算破坏性变更
- 契约变化后，前后端各自要同步什么
- 至少要跑哪些验证

## 契约所有权

| 契约类型 | 事实源 | 同步位置 |
|----------|--------|----------|
| 后端 API 请求 / 响应 | 后端 DTO + router `response_model` | 前端 service DTO / shared schema |
| 跨页面复用的前端业务类型 | `packages/shared/src/types` 或 `packages/shared/src/schemas` | 各 service / composable / 页面 |
| 单页面展示类型 | 页面或局部 composable | 不默认提升到 shared |
| 状态值 / 枚举 | 后端枚举或明确常量集合 | 前端 constants / shared schema |
| 错误语义 | HTTP status + detail 语义 | 前端错误处理与用户提示 |

原则很简单：谁定义业务真实语义，谁就是事实源；其他位置负责消费和同步，不各写一套“差不多”的版本。

## 何时提升到 shared

出现以下任一情况时，应优先考虑把契约提升到 `packages/shared`：

- 同一个字段族或对象形态被多个页面复用
- 前后端都需要显式理解同一结构
- 某组状态值 / 枚举已经在多个地方重复手写
- 某类数据已经成为 review、测试或 follow-up 中反复出问题的漂移点

不要把只在单个页面临时使用的展示型结构一股脑塞进 shared。shared 适合稳定复用的契约，不适合页面私有中间态。

## 变更分类

### 兼容变更

- 新增可选响应字段
- 新增可选请求字段，并提供默认值
- 新增不影响既有调用的过滤参数

### 破坏性变更

- 删除或重命名字段
- 修改字段类型、枚举取值或必填性
- 改变默认值、分页结构或错误状态码
- 改变任务状态流、文件状态流、轮询语义或其他外部可观察行为

破坏性变更必须同步 spec / plan / 当前任务卡片，并在交付说明里明确影响范围。不要把破坏性变更包装成“只是重构”。

## 契约变更的最小同步步骤

1. 定位契约边界：method、path、request DTO、response DTO、调用它的前端 service。
2. 更新后端事实源：DTO、`response_model`、必要的 service / repository 返回结构。
3. 更新前端消费层：service DTO、adapter、composable 或页面消费逻辑。
4. 需要复用时，提升到 shared schema / type / helper。
5. 按 `docs/03-engineering-governance/01-rules/docs.md` 同步相关文档。
6. 按 `docs/03-engineering-governance/01-rules/quality-gates.md` 运行契约相关验证。

如果只改了一端，没有同步另一端和验证，通常不算“完成契约变更”。

## 前端约束

- API 调用优先集中在 `packages/web/src/services/*`，不要把 `api.get/post` 散落在页面里。
- Service DTO 应表达后端真实响应，不为了展示方便静默改字段名。
- 页面需要的派生字段，放在 adapter、composable 或 computed 中，不反向污染 API DTO。
- 不要使用 `unknown as SomeDTO` 或双重断言掩盖类型不一致。需要转换时，新增命名明确的 adapter。
- 状态值、枚举和有限集合不要在多个页面重复手写，优先复用 constants 或 shared schema。

## 后端约束

- Router 负责认证、参数解析、异常映射和响应映射；复杂业务组装放在 application service 或 repository。
- 响应字段命名保持稳定，默认按接口真实字段输出；前端也按真实接口字段建模。
- 同一端点不要在不同条件下有时返回数组、有时返回对象。
- 错误状态码保持语义稳定：认证、授权、资源不存在、参数错误、业务冲突不要混用。

## 验证基线

| 改动类型 | 必跑验证 |
|----------|----------|
| 后端 DTO 或 router 变更 | 相关 pytest；至少覆盖成功响应和关键错误响应 |
| 前端 service DTO 变更 | `pnpm --filter @metaedu/web typecheck` |
| shared schema / type 变更 | `pnpm --filter @metaedu/shared typecheck` + 前端 typecheck |
| 状态流或枚举变更 | 后端相关测试 + 前端涉及页面的 typecheck 或手动验收 |

如果当前项目缺少契约测试或适当覆盖，应把缺口记到任务卡片或技术债，而不是只在最终回复里口头说明。

## 何时更新本文件

只有下面这些变化值得更新 `contracts.md`：

- 契约所有权发生变化
- 共享契约提升策略发生变化
- 兼容 / 破坏性边界定义发生变化
- 契约同步或验证基线发生变化

如果只是某个具体接口增加了字段、某次任务补了 shared schema，通常不更新本文件。

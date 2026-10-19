# REQ-042 WS-S2 phase-D 前置：servable definition discovery 契约（contract freeze 候选）

- 状态：Draft（契约冻结候选；评审冻结后才允许实现）
- 关联：phase-A 公共 submit API 契约（PR #642 已冻结）、phase-B launch policy / V1 profile 契约（PR #645 已冻结）、phase-C 公共 submit route 实现（PR #647 已合并 main，mergeCommit `940e81d6`）、phase-D 前置核验（2026-10-19 只读轮）
- 范围：只新增一个只读 GET 发现端点的契约；不含后端实现、不开放 Composer、不启动 phase-E

## 0. 边界声明

- 本 spec 是 phase-A 的**只读增量**：不修改 `POST /conversations/{id}/turns` 四字段契约、错误码表、幂等语义（phase-A §3/§5/§10 逐字保持冻结）；不新增任何写路径。
- 发现端点只回答「当前 tenant 有哪些可服务的 definition 版本」；**发现成功不替代提交期授权**——`POST /turns` 的实时存在性/可服务性校验与 fail-closed 语义原样保留（TOCTOU：发现到提交之间状态可变）。
- 不引入 SSE、cancel/steer、Runtime、REQ-047 Extended、WS-S3；不修改 REQ-042 的 ⚫ Candidate 状态。

## 1. 目标与解决的问题

phase-A §3 冻结 `agent_definition_version_id` 为客户端必填字段，但前置核验实证：全仓没有任何公开读面能让前端合法取得该值（workspace router 的 GET 仅 conversations/messages；execution router 仅 runs；`get_agent_definition_version` 仅存在于 execution repository 内部）。非法替代路径（硬编码 UUID、从历史 Run 反推、把会话 active 状态当提交授权）全部禁止。本契约提供唯一合法来源。

## 2. 端点冻结定义

| 项 | 冻结值 |
|---|---|
| 方法与路径 | `GET /api/v1/agent-workspace/servable-agent-definitions` |
| 鉴权 | 与 conversations 相同（`get_current_user`）；tenant 从鉴权派生，不接受查询参数指定 |
| 可见范围 | 当前 tenant 内**当前可服务**的 definition 版本；tenant 级共享事实，不做 actor/owner 过滤（owner 语义属于会话，不属于 definition） |
| 响应 | `200 OK` + `{"items": [...]}`；每项恰三字段：`id`（definition version UUID）、`definition_key`、`version`（int） |
| 禁止字段 | 不得携带 `runtime_profile_id`、`runtime_binding_id`、capability snapshot / digest、budget、revision 等任何 server-selected launch 输入（phase-A §4 边界对读面同样成立） |
| 排序 | 按 `(definition_key, version)` 升序，保证客户端可复现 |
| 分页/限流 | V1 不分页（量纲为 tenant 内可服务 definition 数，预期个位数）；不加专属限流（与既有 GET 端点一致） |
| 空结果 | `200 OK` + `{"items": []}` 为**正常语义**（当前无可服务项），不是错误 |
| 错误形状 | 401/403 沿用既有鉴权约定；本端点不新增自定义错误码；未预期失败 500 `internal_error`（phase-A §10 形状） |

## 3. 可服务性判定（发现谓词）

发现结果 = 逐项通过以下谓词的 definition 版本（与 phase-C 提交期判定链同源，见 `app/composition/runtime_launch_policy.py`）：

1. definition 存在且 `status == published`（draft/retired 排除）；
2. 本 tenant 存在 `profile_key == compat.direct_rag.v1` 的 runtime profile；
3. 该 profile `enabled == true`；
4. profile 身份（`runtime_kind` / `adapter_key`）等于冻结 V1 身份（`compatibility` / `direct_rag`）；
5. `profile.capability_digest` 等于 canonical `DIRECT_RAG_CAPABILITIES` 的 `snapshot_digest`。

第 5 项不满足属于**服务端配置缺陷**。注意 V1 的 `compat.direct_rag.v1` profile 是 tenant 内所有 V1 候选**共享**的——digest 不符的影响面是该 tenant 全部依赖候选，而非单个 definition。因此本情形的发现语义为：返回 `200 OK` + **空列表** + 服务端 warning 日志（按 profile 缺陷去重，一次缺陷一条 warning，不按 definition 重复刷同一配置告警）。读面 fail-safe 不整表 500；提交面对应路径仍 fail-closed 500，语义不变。

**客户端认知边界（冻结）**：空结果只表示「当前无可服务项」，客户端**无法也不应**从空结果区分「从未初始化 / 全部 disabled / 共享配置缺陷」——原因诊断是服务端职责（warning 日志携带 profile_key 与 digest 比对事实），不得把诊断负担转移给客户端猜测。

## 4. 初始化责任与新 tenant 行为（诚实缺口）

- **GET 不得隐式写库**：发现只反映已注册状态，绝不触发 bootstrap/种子写入。
- 现状（实证）：生产唯一初始化路径是 compatibility 运行路径的 `ExecutionIdentityService.bootstrap_direct_rag`（`app/composition/direct_rag_compatibility.py`）懒触发；从未跑过 compatibility 执行的 tenant 没有任何 definition/profile 行，发现如实返回空。
- **前置缺口已登记为 TD-114（真实稳定编号，不在本契约内实现）**：tenant 供给或 workspace 首次使用时缺少显式 identity 初始化编排——真实首提在 phase-E 联调前需要一条合法初始化路径。触发点建议、幂等性、tenant 隔离、既有租户补齐、失败重试与验收标准见技术债台账 TD-114 行；初始化任务是新租户首次提交验收的前置。**明确边界：discovery 单独落地不解除全部依赖**（无初始化路径时新 tenant 恒空）；**不得用测试 bootstrap 冒充生产路径**。

## 5. phase-D 消费状态约定

| 状态 | 来源/判定 | 发送按钮 |
|---|---|---|
| 发现加载中 | 请求在途 | 禁用 |
| 发现失败（网络/5xx） | 请求失败，显示可重试 | 禁用 |
| 无可用项 | 200 + 空 items（含新 tenant 未初始化） | 禁用，提示「当前无可服务 Agent」 |
| 有可用项 | 默认选中首项（按 §2 排序） | 按其余门禁判定 |
| 选择失效 | 重新发现后已选 id 不在结果中 | 禁用并重选/提示 |
| 提交中 | `submitTurnInFlight` | 禁用 |
| 403 `capability_denied` 后 | 触发重新发现（**仅刷新快照，不代表获得授权**）；结果仍含该项则提示不可用并保留选择；**不得自动循环重提交**（重新发现成功后也必须等用户再次点击） | 按重新发现结果判定 |
| 429 冷却 | `Retry-After` 倒计时 | 倒计时内禁用 |
| tenant/actor 切换 | 发现缓存按 (tenant, actor) 键隔离并即时失效；**清除全部提交相关状态**（提交中标记、冷却计时、403 提示、已选 definition）；**旧身份的在途响应一律忽略丢弃**（按请求时身份键校验归属） | 按新身份重新发现判定 |

硬规则：**不仅凭会话 active 启用发送**（active 是会话态前提，不是可用性结论）；**V1 capability 快照全 False 不得解读为禁止提交**（V1 语义 = 仅 durable 入队，不执行）。

## 6. 客户端提交生命周期约定（phase-A §5 的消费侧细化）

### 6.1 幂等键绑定提交快照

`client_message_id` 绑定**完整提交快照** =（规范化后的 parts、所选 `agent_definition_version_id`、`client_options`）。同一快照的失败重试（网络错误/5xx）必须同键同快照；快照任何字段变更 → 必须生成新键；提交成功 → 下一条新键。

### 6.2 结果不确定时的唯一恢复路径（冻结）

提交后网络失败或 5xx 导致**结果未知**时，客户端唯一合法动作是：**同键 + 同完整快照重试**，由服务端幂等语义给出确定结论——

- 原请求已落库 → `200 OK` + `idempotent_replay=true`，返回**原 receipt**；
- 原请求未落库 → 正常走完首次提交路径（201）；
- 键同而内容不同 → `409 idempotency_conflict`（同快照重试不会触发；触发即客户端 bug 或串改，必须停止并显式报错）。

**禁止**的推断路径（本契约显式排除）：

- 不得用消息内容/时间近似匹配来「判定成功」——重复内容、并发会话与时钟偏差都使其不可靠；
- 不得以「messages 列表中未找到」判定「未提交」——列表分页/可见性/时序都使缺席不构成证据；
- 消息读面只有在**已持有 receipt 中的 `message_id`** 之后，才用于该消息的精确确认与刷新（`GET /conversations/{id}/messages` 按 id 定位）；在此之前读面不参与提交判定。
- 不新增消息查询字段、不改变 POST /turns 契约来绕过本节约定。

### 6.3 未知结果的快照保留与草稿隔离

- 结果未知的提交快照（键 + 完整快照）必须保留，直到重试取得确定结论（receipt / 409 / 明确 4xx）或用户显式放弃；**不得自动换新键重发**。
- 用户在结果未知期间编辑内容：新内容作为**新草稿**与原请求分离（新键、互不影响）；不得把新内容混进原快照重试。
- 在途请求成功只能清除**对应提交快照**的草稿：用户随后编辑的新内容、其他会话的草稿一律不动。

### 6.4 刷新 / 会话切换 / 账号切换的保留与隔离

| 事件 | 快照与草稿策略 |
|---|---|
| 页面刷新 | 草稿按 (tenant, actor, conversation) 键保留并恢复；**结果未知的在途请求已随页面销毁**——恢复后快照仍在，由用户决定是否同键同快照重试（不自动重发） |
| 会话切换 | 草稿与未知结果快照按会话键各自保留；响应按请求时会话归属写回 |
| tenant/actor 切换 | 提交相关状态全部清除（§5）；旧身份快照与草稿按身份键隔离保留，不跨身份可见；旧身份在途响应忽略丢弃 |

### 6.5 receipt pending 与 Run 404

201 receipt 仅代表 durable 提交；`dispatch_state=pending` 如实展示「已提交待执行」；`GET /agent-runs/{run_id}` 在 execution 消费前的 404 必须容忍（phase-A §8），消息列表为唯一提交事实源。

## 7. 实现方案与边界（最小，供后续实现 PR 遵循）

- **边界**：不引入 workspace → execution 直接依赖（TD-085 已冻结方向）。与 phase-C 同模式：workspace application 层定义只读 port（建议 `ServableDefinitionCatalogPort`，返回 workspace 自有中性 DTO），composition 层新增 adapter 用 `AgentExecutionIdentityRepository` 实现。
- **仓储缺口**：`AgentExecutionIdentityRepository` 当前只有按 id/key 的点查，无 tenant 范围 list——实现侧需新增一个 tenant 作用域的只读 list 查询（本契约授权的最小仓储扩展）。
- **router**：workspace router 新增该 GET；异常映射沿用既有路径，不新增错误码。

## 8. 验收矩阵（实现 PR 据此写真实 PG contract tests）

| 编号 | 验收 | 依据 |
|---|---|---|
| D-1 | 未认证 401；他 tenant 数据不可见 | §2 |
| D-2 | 无任何注册时返回 `{"items": []}`（200 非错误） | §2/§4 |
| D-3 | draft/retired definition 不出现 | §3-1 |
| D-4 | profile 缺失或 `enabled=false` 时不出现 | §3-2/3-3 |
| D-5 | profile 身份（runtime_kind/adapter_key）不符 V1 时不出现 | §3-4 |
| D-6 | capability digest 不一致时该项省略且有服务端 warning 日志；读面仍 200 | §3-5 |
| D-7 | 响应项不含任何 server-selected launch 字段（profile id/digest/budget 等） | §2 |
| D-8 | 调用前后 `agent_definition_versions` / `agent_runtime_profiles` 行数不变（无隐式写） | §4 |
| D-9 | 同 tenant 多 definition 时按 `(definition_key, version)` 排序返回全部可服务项（不假定单元素） | §2 |
| D-10 | 发现成功不替代提交期校验：发现含该项后，将其 profile 置 disabled，提交仍 403 `capability_denied` | §0/§3 |
| D-11 | 同键 + 同完整快照重试：已落库时返回原 receipt（200 + `idempotent_replay=true`），未落库时正常 201 | §6.2 |
| D-12 | 反例：结果未知时以「messages 未找到」判定未提交 → 实现/测试均不得出现该推断路径 | §6.2 |
| D-13 | 反例：以消息内容/时间近似匹配判定提交成功 → 实现/测试均不得出现 | §6.2 |
| D-14 | 已有 receipt 后按 `message_id` 在 messages 读面精确确认与刷新 | §6.2 |
| D-15 | 结果未知期间编辑内容生成新草稿与原快照分离；在途成功仅清对应快照草稿 | §6.3 |
| D-16 | 页面刷新恢复快照但不自动重发；tenant/actor 切换清除提交状态并丢弃旧身份在途响应 | §5/§6.4 |
| D-17 | 共享 profile digest 缺陷：发现返回 200 + 空列表 + 按缺陷去重的单条 warning（不按 definition 重复刷）；客户端无从区分原因 | §3 |
| D-18 | 403 `capability_denied` 后仅刷新快照，不自动循环重提交（须用户再次点击） | §5 |
| D-19 | 新 tenant 零初始化时返回空列表且 GET 前后身份表行数不变（无隐式写） | §2/§4 |

## 9. 非目标（本 spec 明确不交付）

- 后端实现与测试（归后续实现 PR，依据 §7/§8）。
- Composer 开放与 phase-D 其余前端切片；phase-E 联调与手动验收。
- tenant provisioning 初始化编排（§4 缺口登记给独立任务）。
- SSE / cancel / steer / Runtime / REQ-047 Extended / WS-S3；REQ-042 状态变更。

## 10. 验证（本契约 PR）

- pure-docs：无业务测试要求。
- `git diff --check` 与 `scripts/check-engineering-docs --full` 通过。
- 链接与引用（phase-A/B spec、plan、runtime_launch_policy.py、direct_rag_compatibility.py）逐一解析存在。

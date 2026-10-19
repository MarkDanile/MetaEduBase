# TD-114 Agent identity 显式初始化编排契约（contract freeze 候选）

- 状态：Draft（契约冻结候选；评审冻结后才允许实现）
- 关联：phase-A 公共 submit API 契约（PR #642 已冻结）、phase-B launch policy / V1 profile 契约（PR #645 已冻结）、phase-C 实现（PR #647 已合并 main，mergeCommit `940e81d6`）、definition discovery 契约（PR #655 已合并 main，mergeCommit `567aac31`）、TD-114 台账行（⚫→🟡 进行中）
- 范围：只冻结「显式初始化编排」的 API 契约、CLI 契约、事务与状态语义、验收归属；不含实现

## 0. 边界声明

- 本契约不改 phase-A §3/§5/§10、phase-B §1~§3、discovery 契约 §2~§8 的任何已冻结文本；submit-turn 的 422/403/500 判定链原样保留。
- **初始化不写入 discovery GET**（discovery 契约 §4 不变）；不藏进 submit_turn / conversation 创建等既有端点（不改其可观察语义）；不启动 Run、不调用 LLM、不执行 compatibility 业务流程。
- 不建通用 tenant provisioning 平台；本契约只覆盖 V1 compatibility 身份目录（`system.direct_rag` v1 definition + `compat.direct_rag.v1` profile）的显式初始化。

## 1. 目标与解决的问题

生产唯一初始化路径是 compatibility 运行路径的懒 `bootstrap_direct_rag`（`app/composition/direct_rag_compatibility.py:166-168`，仅在 `prepare_turn` 内触发）。从未跑过 compatibility 的 tenant 没有任何 definition/profile 行：discovery 如实返回空（#655 契约语义），首提 422 `validation_error`（phase-B §3.2-1）。本契约提供一条**显式、幂等、可审计**的初始化路径，覆盖新 tenant 与存量 tenant。

## 2. API 端点冻结定义

| 项 | 冻结值 |
|---|---|
| 方法与路径 | `POST /api/v1/agent-workspace/agent-identity/bootstrap` |
| 鉴权 | 与 conversations 相同（`get_current_user`）；tenant 与 actor 均从认证令牌派生（JWT `sub`/`tid` + `metaedu.users` 行校验） |
| 请求体 | **空**；请求体出现任何字段（含 `tenant_id`）一律 422 `validation_error`——不信任客户端任意传入的 tenant |
| 成功响应 | `200 OK` + `{"initialized": true, "disabled_existing": <bool>}`，恰两字段 |
| 冲突响应 | `409` + `{"code": "identity_conflict", "message": ...}`（phase-A §10 错误形状） |
| 其他错误 | 401/403 沿用既有鉴权约定；未预期失败 500 `internal_error`；不新增其他错误码 |
| 限流 | 不加专属限流（幂等 2 行 upsert，成本有界；与既有无专属限流端点一致） |

**响应语义（响应只描述最终状态）**：

- `initialized: true`：本调用结束后，tenant 的 V1 identity 行**齐备且身份匹配**——definition 行存在且 `status=published`、profile 行存在且 `runtime_kind`/`adapter_key`/`config_digest`/`capability_digest` 等于 V1 冻结内容。响应**不携带 created 计数**（创建归属判定见 §5，API 响应不暴露）。
- `disabled_existing: true`：identity 齐备，但既有 profile `enabled=false`。**初始化不重新启用 disabled profile**；此时「已初始化」成立但「当前可服务」不成立（见 §3）。
- **禁止返回字段**：`runtime_profile_id`、`capability_digest`、`config_digest`、budget、capability 快照、definition id 等 server-selected launch 输入一律不返回（phase-A §4 边界对写面同样成立；读面归 discovery GET）。

**权限依据（普通成员初始化共享资源）**：V1 identity 目录是 tenant 级共享事实（discovery 契约 §2：不做 actor/owner 过滤）。任何已认证成员对本 tenant 触发初始化，与既有 compatibility 路径的写入面完全等同——`prepare_turn` 内任何用户首次 chat 都会执行同一 `bootstrap_direct_rag`。本端点不改变权限面，只是把同一写入从隐式懒触发变为显式可审计触发；不引入新角色、不需要 super_admin。

**重试语义**：本端点幂等。5xx / 网络失败后客户端可安全重试任意次，终态一致；409 `identity_conflict` 是**确定性**冲突（既有记录与 V1 冻结内容不符），重试无意义，需人工介入，客户端不得自动重试。

## 3. 「已初始化」与「当前可服务」的区别（冻结）

- **已初始化（initialized）**：definition published 行存在 + profile 行存在且四项身份字段匹配 V1。
- **当前可服务（servable）**：已初始化 **且** `profile.enabled == true`（即 discovery 五谓词全过）。
- 本端点保证「已初始化」（或报 409）；**不保证**「当前可服务」——disabled profile 不自动启用，`disabled_existing=true` 时 submit 仍 403 `capability_denied`、discovery 仍空。重新启用是独立的显式运维决定，不在本契约内。
- **discovery 空列表不得被判定为「未初始化」**（#655 §3 客户端认知边界：空 = 当前无可服务项，不可归因）。初始化不得由「discovery 为空」自动推导触发。

## 4. 状态处理矩阵（逐项冻结）

| 状态 | 判定 | 处理 |
|---|---|---|
| 全缺失 | definition 行与 profile 行均不存在 | 同事务创建两者 → 200 |
| 部分缺失（仅 definition） | definition 在、profile 无 | 同事务内仅创建 profile → 200 |
| 部分缺失（仅 profile） | profile 在、definition 无 | 同事务内仅创建 definition → 200 |
| 完整初始化 | 两者在、身份匹配、`enabled=true` | 零写入 → 200（重复/并发安全） |
| 完整但 disabled | 两者在、身份匹配、`enabled=false` | **不重新启用**、零写入 → 200 + `disabled_existing: true` |
| definition draft/retired | 同 (key, version) 行存在但 `status≠published` | **不重发布**（受控记录）→ 409 `identity_conflict`，人工介入 |
| digest/身份冲突 | 同 (key, version) 或同 profile_key 行存在，但 digest/身份字段 ≠ V1 冻结内容 | **不覆盖** → 409 `identity_conflict`，人工介入 |
| 自定义记录 | 其他 definition_key / version / profile_key 的行 | 零触碰（唯一约束按 key 维度，本契约只写 V1 两键） |

判定顺序：先读现状（同事务内），按上表分流；409 分支零写入。

## 5. 事务、并发与创建归属（冻结）

- **事务所有者**：composition bootstrap 服务在调用方 session 内执行两个 publish（与 compatibility 路径同模式）；route 成功时 `session.commit()`、异常时 `session.rollback()`。**两表写入同事务**：任一失败整体回滚，不产生半初始化残留。
- **并发**：并发安全由数据库唯一约束（`uq_agent_definition_key_version`、`uq_agent_runtime_profile_key`）+ `INSERT ... ON CONFLICT DO NOTHING` 仲裁；独立连接/独立事务下的并发调用全部返回 200 同一终态，不产生重复行。
- **创建归属判定（CLI 统计需要时）**：**不得凭写前查询推断**（并发下两调用方都读到「不存在」，都会误认为自己创建了）。唯一合法判定 = `INSERT ... ON CONFLICT DO NOTHING ... RETURNING id` 的返回行：`scalar_one_or_none()` 非空 = 本事务实际插入（计 created），为空 = 冲突未插入（计 skipped）。既有代码先例：`app/contexts/agent_workspace/infrastructure/repository.py:78-84`。
- 既有 `publish_agent_definition_version` / `publish_runtime_profile` 的签名与语义**不变**（compatibility 路径零影响）；RETURNING 判定经新增的窄仓储方法提供（见 plan）。

## 6. 触发方式、次数与失败处理（禁止自动修复循环）

初始化的合法触发方式**有且仅有两种**：

1. **客户端显式调用本 POST**：由用户显式操作触发，或在 phase-D 由前端在用户打开 Composer 且 discovery 为空时**每次会话最多一次**自动调用一次（需用户在界面上可感知）；失败后**不得**自动反复调用——5xx 提示用户可重试（用户发起），409 提示联系管理员并停止。
2. **运维 CLI**（§7）：存量补齐与新 tenant 的运维路径。

**禁止**的触发模式（本契约显式排除）：

- 不得由 discovery GET、conversation 创建、submit_turn 等既有端点隐式触发初始化；
- 不得由「discovery 返回空」自动推导「未初始化」并触发初始化（空 ≠ 未初始化，§3）；
- 不得实现任何形式的自动修复循环（空 → bootstrap → 再空 → 再 bootstrap）。

## 7. CLI 契约（存量补齐）

| 项 | 冻结值 |
|---|---|
| 入口 | `python -m app.cli.backfill agent-identity` |
| 参数 | `--tenant <uuid>`（可选，只处理指定 tenant）；`--dry-run`（可选，零写只出统计）；`--actor <uuid>`（**必填**，见 §8） |
| 选择条件 | `metaedu.tenants` 全量扫描（或 `--tenant` 指定）；不做预选过滤，per-tenant 按 §4 矩阵幂等分流 |
| dry-run | **零写入**；只读查询统计 per-tenant 预测分类（missing / complete / disabled / conflict）。dry-run 无并发写，只读判定合法；实写运行的 created 归属按 §5 RETURNING 判定 |
| 事务 | 逐 tenant 独立短事务：单 tenant 提交/回滚互不影响 |
| 失败报告 | per-tenant `created / skipped / disabled / conflict / failed` 计数 + 失败明细（有界上限）；JSON 输出（对齐既有 backfill CLI 形态） |
| 退出码 | 任何 `failed` 或 `conflict` 非零 → exit 1；全部 created/skipped/disabled → exit 0（disabled 如实报告但不计失败） |
| 重跑 | 幂等：重跑只产生 skipped，不产生重复行；失败 tenant 修复后可单独 `--tenant` 重跑 |
| 执行授权 | 生产执行需用户显式授权；**不是**自动化测试或 phase-E 的必需前置 |

## 8. `created_by` 审计约束（冻结）

- definition 表 `created_by` 列 `nullable=False`（`models.py:68`），必须给出来源合法的 actor。
- **API 路径**：`created_by` = 调用者本人的 actor_id（认证令牌派生的真实用户），审计真实。
- **CLI 路径**：**禁止虚构系统 UUID**。`--actor <uuid>` 必填，取执行运维的真实 user id，且必须存在于 `metaedu.users`（不存在即报错不执行）。审计含义 = 「谁执行了这次补齐」。
- compatibility 懒路径的既有行为（`created_by` = 首次 chat 用户）不受影响。

## 9. 实现边界（供实现 PR 遵循）

- **workspace application 层**：新增 port（建议 `AgentIdentityBootstrapPort`）+ 中性结果 DTO（`BootstrapOutcome`：`initialized` / `disabled_existing` / `conflict` 三态）；不 import execution 任何类型（TD-085 方向不变）。
- **composition adapter**：新模块实现 port，内部使用 `ExecutionIdentityService` / `AgentExecutionIdentityRepository`；CLI 的扫描与统计逻辑同属 composition（可双侧 import，同 `runtime_launch_policy.py` 先例）。
- **路由注册**：现 workspace router prefix 为 `/api/v1/agent-workspace/conversations`，本端点不在其下；新增独立小 router（prefix `/api/v1/agent-workspace`）并在 `app/main.py` 注册。discovery GET 的注册归 discovery 实现 PR，本契约不代其决定。
- **仓储**：新增带 RETURNING 的窄方法用于创建归属判定；既有 publish 方法不动。

## 10. 验收矩阵（按承载任务/验证方式分层）

### A 组 — TD-114 实现 PR（真实 PostgreSQL，`metaedu_test`）

| 编号 | 验收 | 验证方式 |
|---|---|---|
| A-1 | 未认证 401；请求体含任何字段（含 tenant_id）422 | API 测试 |
| A-2 | tenant 隔离：初始化 A，B 的两表零变化 | composition 真实 PG |
| A-3 | 重复调用：两次 200，同行同 id、零新增 | API + composition 真实 PG |
| A-4 | 并发：独立连接/独立事务 N 路并发 → 全部 200、两表恰各 1 行 | 真实双 session（仿 `test_two_database_sessions_allow_only_one_live_ingest_stream` 模式） |
| A-5 | 部分失败整体回滚：预置冲突 profile → 409 且 definition 零残留；清除冲突后重试 → 200 两表齐备 | composition 真实 PG |
| A-6 | §4 状态矩阵逐项：全缺失 / 部分缺失×2 / 完整 / disabled / draft / retired / digest 冲突 / 身份冲突 / 自定义记录保留 | composition 真实 PG |
| A-7 | disabled profile：响应 `disabled_existing: true` 且 `enabled` 保持 false（行为断言：不自动启用） | composition 真实 PG |
| A-8 | CLI：dry-run 两表行数不变；`--tenant` 只动指定 tenant；失败统计与退出码；重跑全 skipped；`--actor` 缺失或不存在即报错不执行 | CLI 测试（真实 PG） |
| A-9 | created 归属：双并发下全局 created 计数 == 实际插入行数（RETURNING 判定，非写前查询） | composition 真实 PG |

### B 组 — 真实公开 API 联合测试（需 TD-114 实现 + discovery 后端均落地后，独立联合测试任务）

| 编号 | 验收 | 验证方式 |
|---|---|---|
| B-1 | 新 tenant：bootstrap POST 200 → discovery GET 返回 V1 项 → submit 201 | 三个**真实公开 API** 串联（真实 PG）；不用 mock、不直查库、不用测试 bootstrap 冒充 |
| B-2 | 未初始化 tenant：discovery 空 + GET 零写库（承接 discovery 契约 D-19） | 真实公开 API |
| B-3 | bootstrap 后重复 discovery 一致；submit 201 后同键重放 200 | 真实公开 API |

### C 组 — phase-D 前端测试（phase-D 任务承载）

| 编号 | 验收 |
|---|---|
| C-1 | 空态显式触发：触发一次 bootstrap → 重 discovery → 有项可提交 |
| C-2 | 触发有界：每会话最多一次触发；失败后不自动循环（§6） |
| C-3 | tenant/actor 切换后初始化相关状态按身份键隔离 |

### D 组 — phase-E 浏览器验收（phase-E 任务承载）

| 编号 | 验收 |
|---|---|
| D-1 | 新 tenant 浏览器首提闭环（bootstrap → discovery → submit 201 全真实链路） |
| D-2 | 身份切换后初始化状态隔离行为 |

**生产 backfill**：独立授权的运维操作，不是自动化测试或 phase-E 的必需前置。

## 11. TD-114 完成判据

- 实现 PR：A 组全绿（真实 PG）+ mutation 真实行为缺陷转红（§12）。
- TD-114 翻完成 = **A 组 + B 组**全部通过。B 组在真实端点齐备后即可执行，不等浏览器 phase-E；C/D 组归 phase-D / phase-E 自身验收，不是 TD-114 完成判据。
- 不得以 mock、直查库或测试 bootstrap 冒充公开生产入口；不自行删减既有验收要求。

## 12. mutation 候选（只映射真实行为缺陷）

| 变体 | 真实缺陷 | 预期 |
|---|---|---|
| 删 `ON CONFLICT DO NOTHING` | 重复/并发调用产生 IntegrityError 或重复行（破坏幂等） | A-3/A-4 转红 |
| 删 tenant 谓词 | 跨 tenant 写入 | A-2 转红 |
| 409 分支改为覆盖既有行 | 自定义/受控记录被破坏 | A-6 转红 |
| 实现自动 re-enable disabled | 破坏「不自动启用」语义 | A-7 转红 |
| CLI dry-run 误写 | 行数变化 | A-8 转红 |

注：「删除只读 disabled 检查」不等于自动启用，不强制该变体转红——mutation 只映射真实行为缺陷。

## 13. 非目标（本契约明确不交付）

- API / CLI / 前端 / 测试实现（归实现 PR，依据 §9 / §10-A 与 plan）。
- discovery 端点实现、phase-D、phase-E（各自独立任务）。
- 生产 backfill 执行（独立授权）。
- tenant provisioning 平台、新角色、migration（表与唯一约束已在）。
- TD-114 翻完成（待 §11 判据）。

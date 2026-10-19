# TD-114 Agent identity 显式初始化编排 — 最小实施计划

- 状态：Draft（随契约评审冻结后执行）
- 契约：[2026-10-19-td-114-agent-identity-bootstrap-contract.md](../01-specs/2026-10-19-td-114-agent-identity-bootstrap-contract.md)（本计划只展开其实现切片，不复制契约条款；编号引用契约 §）
- 基线：origin/main `4288d01c5400bb83142ceec278d09fea7c518f33`

## 0. 范围与顺序（总序，串行不默认并行）

1. **本计划 = 第 1 步**：TD-114 实现 PR（契约 §10-A 组验收）。
2. discovery 后端实现 PR（#655 §7，契约 §10-B 组所需的真实 discovery 端点）。
3. 真实公开 API 联合测试（契约 §10-B 组；两个端点齐备后即可执行，不等浏览器 phase-E）。
4. phase-D 前端切片（§10-C 组）。
5. phase-E 浏览器验收（§10-D 组）。
6. 生产存量 backfill：独立授权的 ops 操作，在实现 PR 合并后、有真实新 tenant 首提需求前执行；**不是**自动化测试或 phase-E 的必需前置。

## 1. 文件范围（真实最小清单，不隐藏必要文件）

### 生产代码（5 个文件 + 2 个新文件）

| 文件 | 改动 | 依据 |
|---|---|---|
| `app/contexts/agent_workspace/application/ports.py` | +`AgentIdentityBootstrapPort`（Protocol）+ `BootstrapOutcome` 中性 DTO（三态：initialized / disabled_existing / conflict） | 契约 §9；对齐既有 `RuntimeLaunchFactsPort` 模式 |
| `app/composition/agent_identity_bootstrap.py`（**新**） | adapter 实现 port：现状读取 → §4 矩阵分流 → 两个 publish（同事务）；CLI 扫描/统计逻辑 | 契约 §4/§5/§7/§9 |
| `app/contexts/agent_execution/infrastructure/repository.py` | +2 个带 RETURNING 的窄方法（definition / profile 各一：`insert ... on_conflict_do_nothing ... returning id`，返回 `uuid | None`）；**既有 publish 方法签名与语义不变**（compatibility 零影响） | 契约 §5 创建归属；先例 `agent_workspace/infrastructure/repository.py:78-84` |
| `app/contexts/agent_workspace/interfaces/api/agent_identity_router.py`（**新**） | 小 router（prefix `/api/v1/agent-workspace`）：POST `/agent-identity/bootstrap`；空体校验（任何字段 422）；异常 → §2 错误码映射；composition 工厂装配 | 契约 §2；现 router prefix 为 `/conversations`，故需独立注册 |
| `app/main.py` | +1 行 `include_router` | 契约 §9 |
| `app/cli/backfill.py` | +`agent-identity` 子命令（`--tenant` / `--dry-run` / `--actor` 必填）；逐 tenant 短事务循环；JSON 统计输出；退出码 | 契约 §7/§8 |
| `app/contexts/identity/infrastructure/user_repository.py` 或等价 | 仅当既有无「按 id 查 user 存在性」的只读方法时 +1 点查（`--actor` 校验用）；若已有可复用方法则零改动 | 契约 §8 |

### 测试代码（3 个新文件）

| 文件 | 覆盖 |
|---|---|
| `tests/composition/test_agent_identity_bootstrap.py` | A-2 / A-3（composition 侧）/ A-4 / A-5 / A-6 / A-7 / A-9 |
| `tests/contexts/agent_workspace/test_agent_identity_bootstrap_api.py` | A-1 / A-3（API 侧：200 形状、两字段、禁止字段不返回） |
| `tests/composition/test_agent_identity_backfill_cli.py` | A-8 全项 |

测试环境：真实 PostgreSQL `metaedu_test`（与 CI hermetic 对齐）；并发用例用独立 engine/session（仿 `test_two_database_sessions_allow_only_one_live_ingest_stream`）。

### 不改的文件（明确排除）

- `execution_identity_service.py` / 既有 publish 仓储方法 / compatibility 任何路径；
- discovery spec、phase-A/B 冻结文本、`v1_launch_policy.py`、submit_turn 路由与错误映射；
- workspace router.py（既有 `/conversations` router 不动，新端点走新文件）；
- 前端任何文件。

## 2. 实现要点（按契约条款映射）

1. **现状读取与分流**（契约 §4）：同事务内先读 definition（按 key+version）与 profile（按 key），按矩阵分流；409 分支零写入。
2. **创建归属**（契约 §5）：created 判定只用 RETURNING 返回行；写前查询只用于分流，不用于归属。
3. **响应映射**（契约 §2）：`BootstrapOutcome` → `{"initialized": true, "disabled_existing": bool}`；conflict → 409 `identity_conflict`。响应模型两字段，`extra='forbid'`。
4. **请求校验**（契约 §2）：端点不声明请求模型；若 body 非空/含字段 → 422。实现方式按 FastAPI 最小可靠形态（如 `payload: dict | None = Body(None)` + 非空即 422）。
5. **CLI**（契约 §7/§8）：复用 `_SUBCOMMANDS` 注册模式；`--actor` 先校验存在（不存在的 actor 直接报错、零写入）；dry-run 只读统计；实写 per-tenant commit；失败明细有界（参考 `agent_erasure_backfill` 样本上限）。
6. **装配**：`build_agent_identity_bootstrap(session)` 工厂（对齐 `build_v1_launch_policy`）。

## 3. 验证计划

- 契约 §10-A 全项（A-1~A-9）真实 PG 全绿；
- mutation §12 五个变体逐一先红后绿留痕；
- 受影响回归：`tests/contexts/agent_execution/test_execution_identity_service.py` 既有用例零改动通过（publish 方法未动）；workspace / composition 邻近套件回归；
- `git diff --check`、`scripts/check-engineering-docs --full`、ruff、mypy baseline 零新增；
- CI：Backend（范围命中 backend）+ Backend full hermetic（双 shard + summary）实跑通过。

## 4. 提交边界

- 单一实现 PR，普通 commit 序列；Draft → 独立复审 → Ready → 评分 → 合并。
- PR body 附：契约链接、§10-A 验收逐项证据、mutation 记录、CI run id。
- 不做：discovery 端点、联合测试（B 组）、前端、生产 backfill、TD-114 翻完成、任何既有契约文本修改。

## 5. 风险与开放点（实现期裁决，不阻塞本计划冻结）

1. 空体 422 的 FastAPI 最小实现形态（Body(None) 校验 vs 自定义依赖）——实现期按既有两字段 forbid 先例选择，测试 A-1 钉死行为。
2. `--actor` 存在性校验复用哪个既有只读方法——实现期查 `UserRepository` 方法面后定，禁止为此新增写路径。
3. BootstrapOutcome 三态在 API 层的精确映射代码点（conflict 的 message 文案）——以契约 §2/§4 为唯一事实源。

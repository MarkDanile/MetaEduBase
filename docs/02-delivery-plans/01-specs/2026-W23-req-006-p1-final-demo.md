# REQ-006 P1 知识资产处理链路最终演示验收 — Spec

> Spec 入口：REQ-006（Backlog `Candidate` → `Ready` 的依据）。本文件是验收口径与边界的事实源；实施拆分见 `docs/02-delivery-plans/02-plans/2026-W23-req-006-p1-final-demo-plan.md`。
> Parent：W23 P1 最终查漏补缺迭代（`docs/01-product-planning/03-iterations/2026-W23-p1-final-gap-closure.md`）的"待集成验收"项；与 REQ-003 / REQ-004 / REQ-005 / REQ-007 / REQ-008 共同收口 P1 验证期。

## 目标

在真实 PostgreSQL `metaedu_test` + 真实 LLM 环境下，演示 6 步闭环：

1. 上传文档（Frontend → 后端 FastAPI → MinIO 落地）。
2. 解析（`parse_document` Celery 任务 → `structured_data` 落库 + `chunk` 切分）。
3. 模板抽取（`extract_template` Celery 任务 → L1 / L2 / L3 选模板 → LLM 抽 object / array / table 嵌套结构 → `_merge_template_structured_data` 写入 `template` 容器）。
4. 知识图谱（`extract_template` 派生的 KG nodes / edges 落库）。
5. RAG 问答（Frontend `ai_chat` → NER → 3 通道召回 → 融合 → LLM 回答 → sources 标注）。
6. 来源展示（`sources` 字段在 UI 中按 channel / node_id / title / score 列出）。

完成判定：本仓库的 P1 验证期可以从"代码已实现 + 纯函数回归"上升到"端到端跑通"。

## 范围

包含：

- 端到端脚本：1 个 `tests/e2e/test_p1_demo.py`（pytest + 真实 PG + 真实 LLM），按 6 步串联，单进程单 fixture（不依赖 dev.sh，但 `metaedu_test` 须就绪）。
- 端到端 UI 演示：手工验收脚本（`docs/03-engineering-governance/03-matrices/req-006-p1-final-demo-ui.md`），覆盖 Frontend 上传 → 解析任务轮询 → 抽取任务轮询 → 模板结果展示 → ai_chat 问答 → sources 抽屉 6 步。
- 文档回填：轨道 B 4 项 `🟡 待集成验收` 翻 `🟢 Done`；W23 迭代卡 + Backlog REQ-006 状态 `Candidate` → `Done`；`current-work.md` 最近完成 + `work-log.md` 单行索引。
- 报告 `metaedu_test` 连通性已恢复（2026-06-09 Claude Code 沙箱探测：`PostgreSQL 16.13` + W23 复核 4 文件 34 passed in 9.86s）。

不包含：

- 任何新基础设施（仍以 PostgreSQL / Redis / MinIO 为主，符合 W23 迭代 Out of Scope）。
- 阶段二能力（RRF / rerank / 多引擎编排 / 独立向量库 / 图谱关系召回 / ES 全文检索）。
- 端到端性能压测；只验证功能链路和关键节点产物。
- 业务代码重构；只在脚本和 UI 演示手册中暴露现有行为。

## 验收标准

| ID | 验收点 | 通过条件 | 失败条件 |
|----|--------|----------|----------|
| AC-1 | 上传链路 | `POST /files` 上传一份真实 PPTX / PDF / DOCX（≥ 100 KB），后端返回 `file_id` + MinIO key 落库；`GET /files/{file_id}` 状态 `uploaded` → `parsing` → `parsed` | 上传 4xx / 5xx；文件未落 MinIO；状态卡 `uploaded` 不进 `parsed` |
| AC-2 | 解析产物 | Celery `parse_document` 完成后 `structured_data` 容器含 `full_text` / `section_count`；`chunks` 表按 N 个段落切分（数字 N 与段落数一致） | `structured_data` 缺字段；`chunks` 数为 0 或与段落不符 |
| AC-3 | 模板抽取 | 选好模板后 `extract_template` 走 L1 / L2 / L3 命中至少 1 路径；`structured_data.template` 写入 object / array / table 嵌套结构（参考 `test_extract_template_prompts.py` 锁定的契约） | `template` 字段缺失；嵌套结构被拍平；`array + items=[]` 走 bare-type 分支（TD-034 现状，不阻塞） |
| AC-4 | 知识图谱 | 抽取后 `knowledge_nodes` / `knowledge_edges` 表新增条目（按模板字段派生），`kg_overview` API 返回非空 | KG 节点数 0；`kg_overview` 4xx / 5xx |
| AC-5 | RAG 问答 | `POST /ai_chat` 用一个能命中 KG 节点的 query；返回 `answer` 非空 + `sources` 字段 ≥ 1 条；3 通道召回至少 1 通道命中 | `answer` 空 / `"没有相关信息"` 兜底；`sources = []` |
| AC-6 | 来源展示 | Frontend `ai_chat` 视图在回答下方按 channel / node_id / title / score 列出 `sources`；channel 含 `vector` / `keyword` / `metadata` 三种枚举（按已有实现） | sources 不显示；channel 字段缺失 / 错位 |
| AC-7 | 端到端脚本可复现 | `cd packages/server-python && .venv/bin/python -m pytest tests/e2e/test_p1_demo.py -q` 退出码 0（依赖 `metaedu_test` 连通） | 退出码非 0 / 抛 DB 连接异常 / 抛 LLM 调用异常 |
| AC-8 | UI 演示手册 | `docs/03-engineering-governance/03-matrices/req-006-p1-final-demo-ui.md` 含 6 步截图位（占位允许 + 实际截图由 `metaedu_test` + 浏览器手测产出；沙箱无浏览器时降级为命令输出截图） | 缺失任何 1 步；未覆盖 4 主题中的至少 1 主题视觉 |
| AC-9 | 文档回填 | 轨道 B 4 项 `🟡 待集成验收` 行由"待集成验收"翻"已通过 e2e 演示"；W23 迭代卡 REQ-006 行状态 → `🟢 Done`；Backlog REQ-006 状态 `Candidate` → `Done`；`current-work.md` / `work-log.md` 同步 | 任一事实源未翻结论 / 未置 Done |
| AC-10 | 工程门禁 | `scripts/check-engineering-docs` 退出码 0 | 退出码非 0 |

## 接口与依赖

- **测试 / 改动文件**（新增）：
  - `packages/server-python/tests/e2e/test_p1_demo.py`（AC-1 ~ AC-7 端到端串联脚本）
  - `docs/03-engineering-governance/03-matrices/req-006-p1-final-demo-ui.md`（AC-8 UI 演示手册）
- **修改**（AC-9 文档回填）：
  - `docs/01-product-planning/02-milestones/01-validation-phase.md`（轨道 B 4 行翻结论）
  - `docs/01-product-planning/03-iterations/2026-W23-p1-final-gap-closure.md`（REQ-006 状态翻 Done）
  - `docs/01-product-planning/04-backlog.md`（REQ-006 状态 `Candidate` → `Done`）
  - `docs/03-engineering-governance/current-work.md`（最近完成）
  - `docs/03-engineering-governance/work-log.md`（单行索引）

测试依赖：

- `metaedu_test` 库可达（`postgresql+asyncpg://metaedu:dev_only_123@localhost:5432/metaedu_test`）。
- 至少 1 个可用 LLM provider（`minimax` / `deepseek` / `qwen` 任一，由 `factory.RESOLVER_PROVIDER_NAMES` 决定；环境变量须含对应 API key）。沙箱无 API key 时降级：脚本用 monkeypatch 替换 `chat_with_model_fallback` / provider 为 fake，但 `extract_template` 走 L1 / L2 路径时 LLM 调用可 mock。
- 模板：仓库已有 1 个"中学数学教案"模板可直接复用（参考 W23 验收文档中提及）；如不存在，由 plan 阶段补 `init_by_ai` 创建或手工 `POST /templates` 创建。

## 文件计划

新增：

- `packages/server-python/tests/e2e/test_p1_demo.py`（6 步串联，1 个测试函数或 6 个有序测试；AC-1 ~ AC-7）
- `docs/03-engineering-governance/03-matrices/req-006-p1-final-demo-ui.md`（AC-8）

修改：

- `docs/01-product-planning/02-milestones/01-validation-phase.md`（轨道 B 4 行验证结论）
- `docs/01-product-planning/03-iterations/2026-W23-p1-final-gap-closure.md`（REQ-006 → 🟢 Done）
- `docs/01-product-planning/04-backlog.md`（REQ-006 → 🟢 Done）
- `docs/03-engineering-governance/current-work.md`（AC-9）
- `docs/03-engineering-governance/work-log.md`（AC-9）

业务代码改动范围：0 个文件（仅补端到端脚本 + UI 演示手册 + 文档回填）。

## 风险与边界

- **DB 连通性**：2026-06-09 沙箱探测 `metaedu_test` 已恢复（`PostgreSQL 16.13`，34 passed in 9.86s）；如再次断连，AC-7 验证按 `quality-gates.md#验证表述规范` 标注为 `历史失败`，并把 DB 连通性修复入账为新 `TD-xxx`。
- **LLM 真实调用**：本 spec 接受 2 路径——(a) 真实 LLM 端到端（推荐，需要 API key）；(b) 真实 L1 / L2 + mock L3（沙箱无 key 时的降级）。两条路径都把"端到端"收敛到"上传 → 解析 → 抽取 → 图谱 → RAG → sources 展示"全链路贯通，区别只在 LLM 那一节是否真请求。
- **沙箱无浏览器**：AC-8 UI 演示手册接受"占位 + 命令输出截图"（如 FastAPI Swagger / OpenAPI 截图、curl 输出）。完整 4 主题视觉验收由 `metaedu_test` 真实环境 + 浏览器手工补做。
- **e2e 脚本不依赖 dev.sh**：脚本通过 `TEST_DATABASE_URL` 环境变量覆盖 `localhost:5432`，与 `tests/conftest.py` 行为一致；不引入新 fixture / 客户端。
- **新增 `tests/e2e/` 目录**：当前 `tests/` 下没有 `e2e/` 目录。脚本放在 `tests/e2e/` 仍沿用 `pytest` 收集约定（`rootdir` 自动包含 `tests/**/test_*.py`），无需 `pytest.ini` 调整。
- **本任务不是端到端性能压测**：不做 N 次上传的延迟分位、不做 LLM 调用 cost 统计。

## 不在范围 / 后续任务

| ID | 说明 | 归属 |
|----|------|------|
| 阶段二召回升级 | RRF / rerank / 多引擎编排 | 阶段二迭代 |
| KG 关系召回 | 把 KG edges 也作为独立通道 | 阶段二迭代 |
| 独立向量库 / ES 全文检索 | 形态升级 | 阶段二迭代 |
| TD-034 | `build_fields_desc` `array + items=[]` 走 bare-type 分支的现状 | 单独任务 |

## 启动备忘

- 分支：`feat/req-006-p1-final-demo`（当前）。
- 当前执行模式：`plan-do`（按 `task-modes.md` 默认路由：跨 3+ 文件 / 新 API / 涉及多上下文，但本任务不引入新业务代码，因此用 `plan-do` 而非 `superpower`；如实施中发现需新建 e2e 客户端层，再切 `superpower`）。
- 模式升级条件：plan 阶段如发现需新增 e2e 客户端层 / 共享 schema / 跨上下文 fixture，转入 `superpower` 模式（先 spec/plan，再实施）。

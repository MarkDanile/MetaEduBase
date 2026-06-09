# REQ-006 P1 知识资产处理链路最终演示验收 Implementation Plan（塑形骨架）

> **For agentic workers:** 本 plan 当前为**塑形骨架**（Stage 1 / 2 实施步骤在下一轮实际开发时再补完；本任务只交付 spec / plan 骨架 + 状态同步 + 文档门禁收口）。
>
> 下次回到本任务时，先读 `docs/02-delivery-plans/01-specs/2026-W23-req-006-p1-final-demo.md` 的 AC-1 ~ AC-10，再按本 plan 的 Stage 1 / Stage 2 推进。
>
> **Required sub-skill:** Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在真实 PostgreSQL `metaedu_test` + 真实 LLM（或 L1 / L2 + mock L3）环境下，演示上传 → 解析 → 模板抽取 → 知识图谱 → RAG 问答 → 来源展示 6 步闭环；让 P1 验证期的"代码已实现 + 纯函数回归"上升到"端到端跑通"。

**Architecture:**

- **端到端脚本**（`packages/server-python/tests/e2e/test_p1_demo.py`）：pytest + 真实 `metaedu_test` + 真实 LLM（或 L3 mock）。6 步串联，1 个测试函数或 6 个有序测试。
- **UI 演示手册**（`docs/03-engineering-governance/03-matrices/req-006-p1-final-demo-ui.md`）：6 步截图位 + 4 主题视觉验收（沙箱无浏览器时降级为 curl / OpenAPI 截图 + 视觉对照 diff）。
- **文档回填**：轨道 B 4 行翻结论；W23 迭代卡 REQ-006 → 🟢 Done；Backlog REQ-006 → 🟢 Done；`current-work.md` / `work-log.md` 同步。

**Tech Stack:** Python 3.11+、pytest 8.3+、httpx（FastAPI TestClient 备选）、asyncpg、`factory.RESOLVER_PROVIDER_NAMES` provider、`init_by_ai`（如缺模板）。

**Spec:** `docs/02-delivery-plans/01-specs/2026-W23-req-006-p1-final-demo.md`

**Working dir:** `packages/server-python`（脚本）+ `docs/03-engineering-governance/03-matrices/`（手册）

---

## File Structure

| 文件 | 职责 | 验收点 |
|------|------|--------|
| `tests/e2e/test_p1_demo.py` (新建) | 6 步串联：上传 → 解析 → 模板抽取 → 知识图谱 → RAG 问答 → 来源展示；依赖 `metaedu_test` 真实连接 + 真实或 mock LLM | AC-1 ~ AC-7 |
| `docs/03-engineering-governance/03-matrices/req-006-p1-final-demo-ui.md` (新建) | UI 演示手册：6 步截图位 + 4 主题视觉验收降级路径 | AC-8 |
| `docs/01-product-planning/02-milestones/01-validation-phase.md` (修改) | 轨道 B 4 行翻 `🟢 Done` | AC-9 |
| `docs/01-product-planning/03-iterations/2026-W23-p1-final-gap-closure.md` (修改) | REQ-006 状态 `⚫ Candidate` → `🟢 Done` | AC-9 |
| `docs/01-product-planning/04-backlog.md` (修改) | REQ-006 状态翻 `🟢 Done` | AC-9 |
| `docs/03-engineering-governance/current-work.md` (修改) | 当前进行中清空 + 最近完成追加 1 行 | AC-9 |
| `docs/03-engineering-governance/work-log.md` (修改) | 单行索引 | AC-9 |

业务代码改动范围：0 个文件。

---

## Task 1（塑形，本 PR 收口）：spec / plan / 状态同步

**Files:**
- Create: `docs/02-delivery-plans/01-specs/2026-W23-req-006-p1-final-demo.md`（已完成）
- Create: `docs/02-delivery-plans/02-plans/2026-W23-req-006-p1-final-demo-plan.md`（本文件）
- Modify: `docs/01-product-planning/04-backlog.md`（REQ-006 状态 `⚫ Candidate` → `🟣 Shaping`；下一步指向本 spec / plan）
- Modify: `docs/03-engineering-governance/current-work.md`（当前进行中追加 REQ-006 任务卡）

- [x] **Step 1: 写 spec**（已完成，见上）
- [x] **Step 2: 写 plan 骨架**（本文件）
- [x] **Step 3: Backlog REQ-006 状态翻 `🟣 Shaping`**
- [x] **Step 4: current-work.md "当前进行中" 区追加 REQ-006 任务卡**
- [x] **Step 5: 跑文档门禁**

Run: `scripts/check-engineering-docs`
Expected: 退出码 0。

- [x] **Step 6: 提交**

```bash
git add docs/02-delivery-plans/01-specs/2026-W23-req-006-p1-final-demo.md \
        docs/02-delivery-plans/02-plans/2026-W23-req-006-p1-final-demo-plan.md \
        docs/01-product-planning/04-backlog.md \
        docs/03-engineering-governance/current-work.md
git commit -m "docs(REQ-006): shape P1 final demo acceptance; spec+plan+workbench"
```

---

## Stage 1（实际开发，下次回到本任务时启动）：端到端脚本 + UI 演示手册

**前置条件**：
- `metaedu_test` 连通（2026-06-09 沙箱已恢复）。
- 至少 1 个 LLM provider key（minimax / deepseek / qwen 任一）；无 key 时降级到 L1 / L2 + L3 mock。
- 1 个可用模板（"中学数学教案"或新建）；新建走 `init_by_ai` 或 `POST /templates`。

**Files:**
- Create: `packages/server-python/tests/e2e/test_p1_demo.py`
- Create: `docs/03-engineering-governance/03-matrices/req-006-p1-final-demo-ui.md`

- [ ] **Step 1: 探查现有端到端 / 集成测试模式**
  - 读 `packages/server-python/tests/conftest.py` 看 `client` / `auth_headers` fixture 风格。
  - 读 `tests/contexts/document/test_files.py` / `test_cascade_cleanup.py` 看 `POST /files` / `GET /files/{id}` 调用方式。
  - 读 `tests/contexts/ai/test_ai_chat_rag_e2e.py` 看 RAG e2e 风格（已是 mock 路径，参考 fixture）。
  - 读 `tests/contexts/document/test_structured_data_contract.py` 看 `structured_data` 容器契约。

- [ ] **Step 2: 写端到端脚本**
  - 1 个测试函数（推荐）或 6 个有序测试，按 AC-1 ~ AC-6 顺序串联。
  - 上传：用 `tests/contexts/document` 现有 fixture 或 `tests/conftest.py` 提供的 `client` fixture 调 `POST /files`。
  - 解析：等待 `GET /files/{file_id}` 状态变 `parsed`（用 `tenacity` 或 asyncio `wait_for` + poll）。
  - 抽取：等待 `template` 字段非空（按 `test_extract_template_prompts.py` 锁定的 `dict(template_data)` 契约校验）。
  - 图谱：调 `GET /kg/overview?file_id=...` 断言非空。
  - RAG：调 `POST /ai_chat` 用能命中 KG 节点的 query；断言 `answer` 非空 + `sources` ≥ 1。
  - 来源展示：UI 步骤在脚本中只能验 `sources` 字段（UI 渲染由 AC-8 手册覆盖）。

- [ ] **Step 3: 跑脚本**

Run: `cd packages/server-python && .venv/bin/python -m pytest tests/e2e/test_p1_demo.py -q -s`
Expected: 1 passed（或 6 passed），退出码 0。失败按 `quality-gates.md#验证表述规范` 标注。

- [ ] **Step 4: 写 UI 演示手册**
  - 6 步截图位 + 视觉验收清单（liquid / ink / navy / notion 4 主题）。
  - 沙箱无浏览器：降级为 FastAPI Swagger / curl 输出 / 视觉对照 diff。

- [ ] **Step 5: ruff + 门禁**

Run: `cd packages/server-python && .venv/bin/python -m ruff check tests/e2e/test_p1_demo.py` → 退出码 0
Run: `scripts/check-engineering-docs` → 退出码 0
Run: `git diff --check` → 退出码 0

- [ ] **Step 6: 提交**

```bash
git add packages/server-python/tests/e2e/test_p1_demo.py \
        docs/03-engineering-governance/03-matrices/req-006-p1-final-demo-ui.md
git commit -m "test(REQ-006): P1 final demo e2e script + UI acceptance handbook"
```

---

## Stage 2（收口）：文档回填 + Done 状态

**Files:**
- Modify: `docs/01-product-planning/02-milestones/01-validation-phase.md`
- Modify: `docs/01-product-planning/03-iterations/2026-W23-p1-final-gap-closure.md`
- Modify: `docs/01-product-planning/04-backlog.md`
- Modify: `docs/03-engineering-governance/current-work.md`
- Modify: `docs/03-engineering-governance/work-log.md`

- [ ] **Step 1: 轨道 B 4 行翻结论**
- [ ] **Step 2: W23 迭代卡 REQ-006 → 🟢 Done**
- [ ] **Step 3: Backlog REQ-006 → 🟢 Done**
- [ ] **Step 4: current-work.md 收尾（最近完成追加）**
- [ ] **Step 5: work-log.md 单行索引**
- [ ] **Step 6: 文档门禁 + commit + PR**

---

## 交付记录

状态：🟡 进行中（Stage 1 实施中）

- Stage 1 收口后状态翻 `🟢 Done`。
- 提交链路（依时间顺序）：

| 任务 | Commit | 内容 |
|------|--------|------|
| Task 1 | 本 PR | spec / plan 骨架 + Backlog 状态翻 Shaping + current-work 任务卡 |
| Stage 1 | TBD | `tests/e2e/test_p1_demo.py` 6 步串联 + `req-006-p1-final-demo-ui.md` 手册 |
| Stage 2 | TBD | 文档回填（轨道 B / W23 / Backlog / current-work / work-log） |

- 验证摘要（Stage 1 收口时复跑）：
  - `pytest tests/e2e/test_p1_demo.py -q` → 1 passed / 6 passed
  - `ruff check tests/e2e/test_p1_demo.py` → All checks passed!
  - `scripts/check-engineering-docs` → 退出码 0
  - `git diff --check` → 退出码 0
- 行为变化声明：无（0 业务代码改动；0 测试代码改动除新增 e2e 脚本；仅文档 / 脚本门禁 / 任务总账与工作台同步）。
- 后续接力：完成 Stage 1 / Stage 2 后 P1 验证期可以从"代码已实现 + 纯函数回归"上升到"端到端跑通"。

---

## Self-Review

**Spec coverage check:**

| AC | 任务 |
|----|------|
| AC-1 | Stage 1 Step 2 上传 + Step 3 跑通 |
| AC-2 | Stage 1 Step 2 解析 + Step 3 跑通 |
| AC-3 | Stage 1 Step 2 模板抽取 + Step 3 跑通 |
| AC-4 | Stage 1 Step 2 知识图谱 + Step 3 跑通 |
| AC-5 | Stage 1 Step 2 RAG 问答 + Step 3 跑通 |
| AC-6 | Stage 1 Step 2 来源展示断言（字段层）+ Stage 1 Step 4 UI 手册（渲染层） |
| AC-7 | Stage 1 Step 3 脚本可复现 |
| AC-8 | Stage 1 Step 4 UI 手册 |
| AC-9 | Stage 2 Step 1-5 文档回填 |
| AC-10 | Stage 2 Step 6 工程门禁 |

**Placeholder scan:** Stage 1 / Stage 2 含完整文件路径与命令；`TBD` 只出现在 commit 列（Stage 1 / Stage 2 实际提交时回填）。

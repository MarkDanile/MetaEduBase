# REQ-006 P1 最终演示验收 — UI 演示手册

> 配套 [Spec AC-8](../../02-delivery-plans/01-specs/2026-W23-req-006-p1-final-demo.md#ac-8) 与 Stage 1 e2e 脚本 `packages/server-python/tests/e2e/test_p1_demo.py`（3 步：上传 / 解析 / structured_data 落库）。
>
> 本手册覆盖 6 步演示的 UI 路径（AC-1 ~ AC-6），其中 AC-1 ~ AC-3 已由 e2e 脚本锁字段层；AC-4 ~ AC-6 留给 Stage 1.5 / Stage 2。本手册由人工 / 沙箱浏览器手测时填写截图与备注；命令可在无浏览器时降级为 curl + OpenAPI 截图。

## 0. 演示前置

| 项 | 期望 | 命令 / 验证 |
|----|------|------------|
| 基础设施（PG / Redis / MinIO） | 全部就绪 | `./dev.sh status` |
| 真实 LLM key（`minimax` / `deepseek` / `qwen` 任一） | 至少 1 个 | `env \| grep -i api_key` |
| 至少 1 个可用模板（如"中学数学教案"） | `metaedu.templates` 存在 ≥ 1 行 | `psql ... -c 'SELECT count(*) FROM metaedu.templates'` |
| 浏览器（4 主题验收用） | liquid / ink / navy / notion 任一可切换 | `pnpm --filter @metaedu/web dev` 后访问 `/` |

降级路径（沙箱无浏览器）：

- AC-1 ~ AC-3：跑 `cd packages/server-python && .venv/bin/python -m pytest tests/e2e/test_p1_demo.py -q -s`，把 stdout 粘贴到对应步骤的"实际输出 / 备注"列。
- AC-4 ~ AC-6：跑 `curl` 验字段 + 视觉对照 `git diff` 自检。
- 4 主题视觉：跑 `pnpm --filter @metaedu/web build`，对比 4 主题下 `assets/css/` 编译产物的 token 化变量是否等价。

---

## 1. 上传（AC-1）

**路径**：`Frontend → /files/upload 视图 → 选择文件 → 上传 → 列表显示 status=uploaded`

| 维度 | 期望 | 实际输出 / 备注 |
|------|------|----------------|
| UI 元素 | `ui-btn-primary` 上传按钮、`ui-input` 文件选择器 | 截图： |
| HTTP 路径 | `POST /api/v1/document/files/upload` 201 | e2e 脚本断言 `status_code == 201` |
| 字段层 | `data.id` (UUID) + `data.status == "uploaded"` + `data.file_type == "txt"` | e2e 脚本已锁 |
| 4 主题 | 4 主题下上传按钮颜色走 token，自动适配 | 截图： |

降级（curl 截图）：

```bash
curl -X POST http://localhost:8000/api/v1/document/files/upload \
    -H "Authorization: Bearer $TOKEN" \
    -F "file=@./sample.txt" | jq
```

---

## 2. 解析（AC-2）

**路径**：`Frontend → /files/{id} 详情页 → 状态轮询 uploaded → processing → parsed`

| 维度 | 期望 | 实际输出 / 备注 |
|------|------|----------------|
| 状态机 | `uploaded` → `processing` → `parsed` | e2e 跑后 status=`processing`（中间态；`parsed` 由下游 `chunk_document` 翻，Stage 1.5 走完整 pipeline 后观察） |
| `structured_data` 字段 | `full_text` / `section_count` 存在 | e2e 脚本已锁：`assert structured["section_count"] >= 1` |
| 4 主题 | 详情页 Pipeline 状态徽章在 4 主题下颜色一致 | 截图： |

降级（curl 截图）：

```bash
curl -s http://localhost:8000/api/v1/document/files/$FILE_ID \
    -H "Authorization: Bearer $TOKEN" | jq .status, .structured_data
```

---

## 3. 模板抽取（AC-3）

**路径**：`Frontend → /files/{id} 详情页 → "抽取" 按钮触发 → 等待 `extract_template` 完成 → `template` 字段渲染`

| 维度 | 期望 | 实际输出 / 备注 |
|------|------|----------------|
| 模板匹配 | L1 / L2 / L3 至少 1 路径命中；命中后 `template` 字段非空 | Stage 1.5 走真实 extract_template 时观察 |
| 嵌套结构 | `template` 字段含 object / array / table 嵌套 | Stage 1.5 跑通后用 `tests/contexts/document/test_extract_template_prompts.py` 的 `isinstance` 断言验证 |
| `array + items=[]` 现状 | 走 bare-type 分支（TD-034 现状） | 已知行为，不阻塞 |
| 4 主题 | 抽取面板在 4 主题下视觉一致 | 截图： |

降级（curl 截图）：

```bash
curl -s http://localhost:8000/api/v1/document/files/$FILE_ID \
    -H "Authorization: Bearer $TOKEN" | jq '.structured_data.template'
```

---

## 4. 知识图谱（AC-4）

**路径**：`Frontend → /files/{id} 详情页 → "知识图谱" tab → KG 节点列表 / 图视图`

| 维度 | 期望 | 实际输出 / 备注 |
|------|------|----------------|
| KG 节点 | `knowledge_nodes` 表新增条目 ≥ 1 | Stage 1.5 跑通后 SQL 查 |
| KG 边 | `knowledge_edges` 表新增条目 ≥ 1 | Stage 1.5 跑通后 SQL 查 |
| `/kg/overview` API | `GET /api/v1/knowledge/overview?file_id=...` 返回非空 | curl |
| 4 主题 | KG 节点卡片在 4 主题下颜色 token 化 | 截图： |

降级（curl 截图）：

```bash
curl -s "http://localhost:8000/api/v1/knowledge/overview?file_id=$FILE_ID" \
    -H "Authorization: Bearer $TOKEN" | jq '.nodes | length'
```

---

## 5. RAG 问答（AC-5）

**路径**：`Frontend → /ai/chat 视图 → 输入 query → 等待流式 / 非流式回答 → answer + sources`

| 维度 | 期望 | 实际输出 / 备注 |
|------|------|----------------|
| query 选择 | 用能命中 KG 节点的 query（如"智能制造专业的核心课程"） | 实际 query： |
| 召回 | 3 通道至少 1 通道命中 | Stage 1.5 跑通后断言 `sources` ≥ 1 |
| answer | 非空 + 引用 sources 上下文 | 实际输出： |
| sources 字段 | `[{id, title, domain, level, score, channel}]`（按 ai_router 实现） | 实际输出： |
| 4 主题 | ai_chat 视图在 4 主题下视觉一致 | 截图： |

降级（curl 截图）：

```bash
curl -X POST http://localhost:8000/api/v1/ai/chat \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"message": "智能制造专业的核心课程"}' | jq '.answer, .sources'
```

---

## 6. 来源展示（AC-6）

**路径**：`Frontend → /ai/chat 视图 → 回答下方 sources 抽屉 / 列表`

| 维度 | 期望 | 实际输出 / 备注 |
|------|------|----------------|
| channel 字段 | vector / keyword / metadata 三种枚举都可能出现 | Stage 1.5 跑通后断言 |
| 字段集 | 每个 source 含 channel / node_id / title / score（按 ai_router 实现） | 实际输出： |
| 排序 | 按 score desc / channel 优先级 | 视觉对照 |
| 4 主题 | sources 卡片在 4 主题下视觉一致 | 截图： |

降级（视觉对照）：

- 打开 DevTools，定位 `app-web-ai-chat-sources` 节点；记录 4 主题切换时 token 变量（`--color-*` / `--shadow-*`）是否等价。

---

## 7. 验收清单

- [ ] AC-1 上传（e2e 脚本已锁）
- [ ] AC-2 解析（e2e 脚本已锁 `processing` 中间态）
- [ ] AC-3 模板抽取（Stage 1.5）
- [ ] AC-4 知识图谱（Stage 1.5）
- [ ] AC-5 RAG 问答（Stage 1.5）
- [ ] AC-6 来源展示（Stage 1.5）
- [ ] AC-7 端到端脚本可复现（Stage 1.0 已覆盖 3 步）
- [ ] AC-8 UI 演示手册（本文件，6 步 + 4 主题）
- [ ] AC-9 文档回填（Stage 2）
- [ ] AC-10 工程门禁（Stage 2 收口时复跑 `scripts/check-engineering-docs`）

---

## 8. 沙箱无浏览器时的兜底记录

如 `dev.sh` 未启动 / 浏览器未装 / LLM key 不可用，请在本节记录降级路径的实际命令 + 输出：

```text
日期：2026-06-09
沙箱：Claude Code 沙箱（无浏览器、无 Redis、LLM key 待配置）
e2e 跑通部分：AC-1 / AC-2 / AC-2c 3 passed
未跑通部分：AC-3 ~ AC-6（待 Stage 1.5 接入 extract_template / KG / RAG）
4 主题验收：未做（沙箱无浏览器）
降级记录：见上方 curl 命令占位
```

---

## 9. 接力与状态

- 本文件为 **AC-8 占位骨架**；Stage 1.5 / Stage 2 由后续 PR 推进填实。
- 沙箱 6 步全部跑通后，Backlog REQ-006 状态翻 `🟢 Done`；W23 迭代卡 + 验证期 milestone 同步。
- 关联任务卡：TD-036（`metaedu_test` schema drift） + TD-037（e2e 沙箱 Celery broker 缺）。

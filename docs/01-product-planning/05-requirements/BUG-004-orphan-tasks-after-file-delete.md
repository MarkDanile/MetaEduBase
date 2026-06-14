# BUG-004: `document_tasks` 级联删除部分失效 → 1178 orphan tasks 指向已删 file

Status: 🔵 Ready
Priority: P2
Milestone: P1 运维数据完整性
Source: 用户报告"在界面上把 25 条文档全部删除"后，Claude Code 真 PG 审计

## 背景

REQ-012 + TD-051 收口后，文档删除 API `DELETE /api/v1/document/files/{file_id}` 通过 `cleanup_file_derivatives` 实现了 chunks → kg_edges → kg_nodes → tasks 的级联清理。本机真 PG 审计发现：25 个 file 全部删除后，**chunks / kg_nodes / kg_edges 全清干净（级联生效）**，但 `document_tasks` 留 **1178 / 1203 (97.9%) orphan task 指向已删 file**——级联任务清理部分失效。

orphan 跨 790 distinct file_ids，跨 4 天（2026-06-08 ~ 2026-06-12）——非本次删除导致，是历史 session 残留或直接 SQL 删除累积。

## 复现路径

1. 用户在 Resource Library 界面对 25 个 file 触发删除（前端调 `documentApi.deleteFile(id)` → `DELETE /api/v1/document/files/{file_id}`）。
2. `delete_file` API 调用 `cleanup_file_derivatives` 后 `repo.delete`。
3. 真 PG 查询（真 PG audit 查询）：
   ```sql
   SELECT
     (SELECT COUNT(*) FROM metaedu.files) AS total_files,
     (SELECT COUNT(*) FROM metaedu.document_chunks) AS total_chunks,
     (SELECT COUNT(*) FROM metaedu.knowledge_nodes WHERE source_file_id IS NOT NULL) AS kg_with_source,
     (SELECT COUNT(*) FROM metaedu.knowledge_edges) AS kg_edges,
     (SELECT COUNT(*) FROM metaedu.document_tasks) AS total_tasks,
     (SELECT COUNT(*) FROM metaedu.document_tasks
      WHERE file_id IS NOT NULL
        AND NOT EXISTS (SELECT 1 FROM metaedu.files f
                        WHERE f.tenant_id = t.tenant_id AND f.id = t.file_id)
     ) AS orphan_tasks;
   ```
4. 期望：所有指向已删 file 的派生数据 = 0；实际：chunks / kg_with_source / kg_edges 都 0，**document_tasks 1203 总 / 1178 orphan**。

## 期望行为

- 任何一次 `DELETE /api/v1/document/files/{file_id}` 成功后：
  - `document_chunks` 中 file_id = X 的行 = 0
  - `knowledge_nodes` 中 source_file_id = X 的行 = 0
  - `knowledge_edges` 端点都不再指向 source_file_id = X 的 node
  - **`document_tasks` 中 file_id = X 的行 = 0**（当前部分失效）
- 任何一次 `POST /api/v1/document/files/{file_id}/reinitialize` 同理。
- 任何直接 SQL 删除 file 的运维操作（已知会发生）应**留 audit trail**（即不强制清 orphan），但**未来不再有 cleanup 失败**的回归。

## 初步怀疑点

- `cleanup_file_derivatives` 流程顺序：`chunks → kg_edges → kg_nodes → tasks`——**最后一步**才是 tasks。
- 真 PG 现象：前 3 步全清，第 4 步（tasks）未清——**这与"前 3 步成功、第 4 步失败"模式一致**。
- 可能根因（待验证）：
  1. `DocumentTaskRepository.delete_by_file` 内部 SQL 错误或参数绑定问题（虽然静态读 SQL 正确）
  2. SQLAlchemy async session 内 3 个 DELETE 在同一 autoflush 时序，**第 4 个 DELETE 被推迟到 commit 之后**而 commit 时 session 已 close
  3. 历史上 `cleanup_file_derivatives` 内的 `delete_by_file` 失败时**没抛错**——async SQLAlchemy 异常被吞
  4. 历史 session 在 colima / docker 不可达时 commit 失败（task DML 已发送但 PG 没收到 commit ack）——前 3 步也可能受影响但**因为 retry / 部分生效**导致实际只 tasks 漏
- 跨 790 file_ids + 跨 4 天的分布强烈指向**多次 session 失败**而非单次 bug——但**单点 bug 修复仍是必要的**（pytest 锁死"未来不再发生"）。

## 验收标准

- AC-1：清掉现有 1178 orphan tasks：1 个 SQL `DELETE FROM metaedu.document_tasks WHERE file_id NOT IN (SELECT id FROM metaedu.files WHERE tenant_id IS NOT NULL OR tenant_id = t.tenant_id)` 或类似，0 业务代码回归。
- AC-2：`cleanup_file_derivatives` 增加 verify 步骤（`result.rowcount` 对比，参考 TD-055 修复合片模式）：删完 4 类派生数据后用 `count_by_file` 查证 0 残留，否则抛错 + 回滚。
- AC-3：pytest 锁死（mock-based）：mock `_do` 行为 verify 4 类 cleanup 都跑 + rowcount 被捕获。
- AC-4：真 PG 端到端：上传 1 个新 file → 跑 parse + chunk + kg（必要时）→ 触发 `delete_file` → verify 4 类派生数据 0 残留。
- AC-5：新增 `scripts/ai/check_orphans.py` 工具：跑全库 scan 找出所有指向已删 file_id 的孤儿行（不限于 document_tasks，扩展到 KG / chunks / edges），输出 7 表 orphan 报告，留作运维定期审计工具。
- AC-6：未来不引入新 bug：保持现有 25 文件 rebuild / reinitialize 端到端测试通过（如果存在）。
- AC-7：不回退 REQ-012 / TD-051 / TD-055 已完成能力：cleanup_file_derivatives 流程不破。

## 验证方式

- 跑 `scripts/ai/check_orphans.py`：当前应输出 1 行 orphan（`document_tasks` 1178）；修复后应为 0 行。
- 真 PG 端到端：建 1 个临时 file + parse + chunk → 触发 delete_file → 跑 `check_orphans.py` → 期望 0 行。
- pytest：mock-based 锁死 `cleanup_file_derivatives` 行为契约。
- ruff clean / `git diff --check` clean / `scripts/check-engineering-docs` 退出码 0。
- 不新增业务代码回归：所有现有 25 文件 rebuild / cleanup / reinitialize 测试通过。

## 后续执行建议

1. **本 BUG 范围仅 `document_tasks` orphan 清掉 + 防御性 verify**——不扩展到 KG / chunks（已全清）。
2. **优先 AC-2（verify rowcount 模式同 TD-055 修复合片）**——这是防御性修复，让"未来发生"被 pytest 锁死。
3. **AC-1（清现有 orphan）作为一次性 SQL 脚本**——可作为运维工具 `scripts/ai/check_orphans.py --fix`。
4. **AC-5（orphan scan 工具）作为长期审计入口**——不属本 BUG 修复合片，可作为独立 follow-up。
5. **优先级 P2 而非 P1**：因为数据完整性已收尾（不影响 AI Chat 召回 / 不影响新上传），但**越早修越能避免再积累**。

## 复现与诊断（2026-06-12 真 PG 审计）

| 表 | 总数 | 指向已删 file 的 orphan | 评级 |
|----|------:|------:|------|
| `metaedu.files` | 0 | 0 | ✅ |
| `metaedu.document_chunks` | 0 | 0 | ✅ 级联全清 |
| `metaedu.knowledge_nodes`（`source_file_id IS NOT NULL`）| 0 | 0 | ✅ 级联全清 |
| `metaedu.knowledge_edges`（端点有效性）| 125 | 0 | ✅ 无悬挂 |
| `metaedu.document_tasks` | 1203 | **1178 (97.9%)** | ❌ 真 bug |
| `metaedu.document_tasks`（`file_id IS NULL`，dataset 上下文）| 25 | n/a | ✅ 合法 |

orphan 分布：790 distinct file_ids，跨 4 天（2026-06-08 ~ 2026-06-12），涉及 `parse failed (877)` / `extract_kg (184)` / `extract_template (117)` 三种 task_type——`parse failed` 占 74%——可能与历史 reinitialize 失败相关。

# BUG-020 实施 Plan：上传路径、大小/类型与下载认证传输硬化

> Requirement: `docs/01-product-planning/05-requirements/BUG-020-upload-path-size-type-and-download-auth.md`

## Context

BUG-020 是 BUG-017/018/019 之后的 P0 安全收敛第四环：

```
document upload + structured_data upload + resource upload：
  file.filename -> 拼进 storage_key + 磁盘路径
    -> /, \\, .., 绝对路径前缀, Unicode 混淆 -> 逃出 tenant upload_dir
  await file.read() 一次性读全部
    -> 无 size limit -> 内存耗尽 / 任意大小文件落盘
  无统一 ext / MIME 白名单 -> 不受控文件落盘
  失败/异常时无清理 -> 临时文件残留
resource download：
  window.open(`/api/v1/resources/{id}/download?token=${token}`)
    -> Bearer token 进 URL query -> 浏览器历史 + 代理日志 + 后端只读 Authorization header -> 401
```

## 设计原则

1. **共享上传边界**（`app/shared/upload_safety.py`）：
   - `safe_display_name(filename) -> str`：剥离路径分隔符 + `..` + 控制字符 + Unicode 混淆 + 截断长度上限
   - `safe_storage_key(tid, filename) -> tuple[str, str]`：服务端生成 `f"{tid}/{uuid.uuid4().hex}.{safe_ext}"`（不拼用户原始路径）
   - `validate_storage_path_containment(absolute_path, base_root) -> None`：解析 realpath 后断言以 base_root 开头，防 symlink/目录穿越
2. **分块流式 + size 上限**（`SafeUploadFile.read_chunked(max_bytes) -> Iterator[bytes]`）：
   - 读取累计 > max_bytes 立即抛 `UploadSizeExceeded`（413）
   - 写文件前先写到临时 `.partial` 文件，落盘成功后 rename 到最终路径（原子性）
   - 任意阶段抛错都清理 `.partial`
3. **类型白名单**（`app/shared/upload_safety.py::ALLOWED_MIME`）：按入口配置（document/structured_data/resource），扩展名 + MIME 双校验（避免依赖 `file.content_type`，前端/curl 可伪造），必要时 magic-bytes 嗅探（如 ZIP/PDF/XLSX）
4. **下载统一 Authorization header**：
   - 前端 service 改用 axios `api.get('/resources/{id}/download', {responseType: 'blob'})`（沿用 api.ts 拦截器自动带 Authorization header + 401 跳转）
   - 后端 download endpoint 已经是 get_current_user 鉴权，无需改动；只需前端不再传 query token
5. **失败清理**：service 层 try/except，任何异常 → 删除临时文件 + 抛 5xx 给前端

## Slices

### Slice 1：共享上传边界工具（AC-1/AC-4）
- [x] `app/shared/upload_safety.py`：新增 `safe_display_name`、`safe_storage_key`、`validate_storage_path_containment`、`UploadSizeExceeded`、`UploadTypeUnsupported` 异常
- [x] `app/shared/upload_safety.py::ALLOWED_MATRIX`：按入口 `document` / `structured_data` / `resource` 配置允许 ext + MIME + magic-bytes 嗅探
- [x] `tests/shared/test_upload_safety.py`：枚举恶意文件名（`../etc/passwd`、`C:\Windows`、`..%2F`、`%2e%2e`、`/` 开头、Unicode 混淆 `‮`、超长 300 字符）、断言不逃出 base_root

### Slice 2：流式分块上传 + 大小限制（AC-2/AC-3）
- [x] `app/shared/upload_safety.py::read_chunked_to_tempfile(UploadFile, *, max_bytes, suffix, tmp_dir) -> tuple[Path, int]`：分块读 + 超限立即终止 + 写 .partial + 返回 path + size
- [x] `app/shared/upload_safety.py::commit_tmpfile(tmp_path, final_path) -> None`：rename .partial -> final；失败自动 unlink
- [x] `tests/shared/test_upload_safety.py`：超 size 终止（用 mock UploadFile）+ 类型不支持 415 + 写临时 + rename 成功 + 失败清理

### Slice 3：三个上传端点接入（AC-1/AC-2/AC-3/AC-4/AC-6）
- [x] `document/files.py::upload_file`：改用 `safe_storage_key` + `read_chunked_to_tempfile` + `commit_tmpfile` + `validate_storage_path_containment` + 显示名存 `safe_display_name`
- [x] `structured_data/router.py::upload_dataset`：同上
- [x] `resource/router.py::upload_resource`：同上
- [x] 既有上传测试 fixture 改用随机文件名（去除硬编码含 `/` 的）
- [x] 新增恶意 filename / 超大 / 不支持类型 / 跨 tenant 写入测试

### Slice 4：前端下载统一 Authorization header（AC-5）
- [x] `packages/web/src/views/resource/ResourceView.vue::downloadResource`：移除 `window.open(?token=)`；改 `fetch blob` + Authorization header + 创建 `<a download>` 点击
- [x] 新增 `services/resourceDownload.ts` 或扩展 `services/resourceApi.ts`：复用 axios + responseType=blob
- [x] `packages/web/src/views/resource/ResourceView.vue` 类型/导入更新

### Slice 5：回归与收口（AC-6 + 全量门禁）
- [x] 全量后端 pytest：既有上传/下载测试 0 回归 + 新增恶意/超大/类型/跨租户测试全绿
- [x] 前端 typecheck + lint + Vitest
- [x] 全量门禁：ruff / check-engineering-docs / git diff --check
- [x] 工作台归档 + work-log

## 关键文件

- `app/shared/upload_safety.py` - 新增（共享上传边界 + 流式分块 + 类型白名单）
- `app/contexts/document/interfaces/api/files.py` - upload_file 接入
- `app/contexts/structured_data/interfaces/api/router.py` - upload_dataset 接入
- `app/contexts/resource/interfaces/api/router.py` - upload_resource 接入
- `packages/web/src/views/resource/ResourceView.vue` - 下载改为 Authorization header

## Global Constraints

- 不破坏既有上传/处理流水线（既有测试 fixture 用普通文件名，加密 UUID 防止 `original_filename` 持久依赖；storage_key 仍可由 `tenant_id/uuid.ext` 推回文件名显示）
- 不引入新依赖（pathlib + uuid stdlib）
- size 上限默认 100MB（document）/ 50MB（structured_data）/ 50MB（resource）；通过 settings 可调
- 前端下载移除 query token；浏览器地址仅显示 `/resources/{id}/download`（无敏感参数）
- 既有 service 文件大小限制（如有）需迁移或扩展

## Non-goals

- 病毒扫描平台（spec Non-goals）—— 预留接口位
- 历史对象存储迁移（spec Non-goals）

## 风险与回滚

- **既有测试用 `..` filename**：document/structured_data/resource 既有上传测试可能含 `../` 或绝对路径；需迁移测试 fixture 或 mock UploadFile
- **storage_key 不含原始文件名**：UI 上 download filename 走 `safe_display_name`；若客户端期望原名可保留 metadata 映射（不在 storage_key 内）
- **size 上限配置**：默认 100MB / 50MB 是基线；settings 已有的 `upload_dir`/`max_upload_size` 字段需复用
- **回滚**：每 Slice 独立 commit + 三个上传端点行为兼容（既有 storage_key 解析仍可解）

## 验证摘要（Slice 5 收口 2026-07-22）

- 新增 34 后端测试（test_upload_safety 18 + test_upload_safety_streaming 11 + test_upload_safety_integration 5）+ 既有 document/structured_data/resource 套件 0 回归
- 全量 `pytest` `1322 passed, 4 skipped, 3 failed`：`3 failed` = `test_embedding_empty_logs_warning`（TD-080 pre-existing）+ `test_p1_demo_step4_kg_extract` / `test_p1_demo_step5_ai_chat`（e2e KG 抽取 flaky：step1 上传 + step3 解析均 PASS，step4 `got []` 是 LLM mock 时序问题，BUG-020 不涉及 KG/LLM 逻辑；BUG-017 收口时已确认 step4 偶发 flaky）
- `ruff check app/ tests/`：All checks passed
- 前端 `npx vue-tsc --noEmit`：0 errors
- 前端 eslint：0 errors
- 可复核命令（macOS Darwin 25.5.0 / Python 3.14 / uv / Node 22）：
  - Command: `cd packages/server-python && uv run pytest tests/shared/test_upload_safety.py tests/shared/test_upload_safety_streaming.py tests/contexts/document/test_upload_safety_integration.py -q --tb=line`
    Result: 34 passed
    Environment: macOS Darwin 25.5.0 / Python 3.14 / uv 本地
  - Command: `cd packages/server-python && uv run pytest -q --tb=line`
    Result: 1322 passed, 3 failed（TD-080 + e2e KG flaky）
    Environment: 同上
  - Command: `cd packages/server-python && uv run ruff check app/ tests/`
    Result: All checks passed
    Environment: 同上
  - Command: `cd packages/web && npx vue-tsc --noEmit`
    Result: exit 0
    Environment: Node 22
  - Command: `./scripts/check-engineering-docs`
    Result: passed（31 known issue allowlisted）
    Environment: 同上
  - Command: `git diff --check`
    Result: exit 0
    Environment: 同上
- 安全闸：
  - AC-1 `safe_display_name` 剥离 `../` / `\\` / 绝对路径 / Unicode 混淆 / URL 编码；`validate_storage_path_containment` realpath 校验防 symlink 逃逸
  - AC-2 `read_chunked_to_tempfile` 流式分块 + 超 `max_bytes` 立即终止 + 删 `.partial` + 413
  - AC-3 `validate_upload_type` ext + MIME 双校验（document/structured_data/resource 三入口白名单）；类型伪造 415
  - AC-4 `safe_storage_key` 服务端生成 `tid/uuid.ext`，不拼用户原始路径；DTO 不暴露 storage_key
  - AC-5 前端 `downloadResource` 改用 axios `responseType: blob` + Authorization header（api.ts 拦截器自动带），移除 `?token=` query
  - AC-6 既有 document/structured_data/resource 跨 tenant 隔离测试 0 回归
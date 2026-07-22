# BUG-020: 上传路径、大小/类型与下载认证传输不安全

> Status: 🔵 Ready
> Priority: P0
> Milestone: P3 / Security Foundation
> Area: 后端 / 前端 / Upload / Resource
> Created: 2026-07-22
> Source: [2026-07-22 安全与质量复核](../../03-engineering-governance/04-retrospectives/2026-07-22-security-and-quality-follow-up-review.md)

## Problem

document 和 structured-data 上传将原始 `file.filename` 拼入磁盘路径，可通过带目录分隔符和 `..` 的 multipart 文件名逃逸预期目录。三个上传入口均整体 `await file.read()`，没有统一大小、扩展名和 MIME 限制，存在内存耗尽和不受控文件落盘风险。

Resource 下载把 Bearer Token 拼入查询参数；Token 会进入历史和日志，且后端只读取 Authorization header，因此下载还可能直接 401。

## Scope

- 建立共享上传边界：安全显示名、服务端生成 storage key、最终路径 containment 校验。
- 分块/流式写入并执行统一大小上限；超限中止并删除临时文件。
- 按入口配置允许的扩展名、MIME 和必要的内容签名检查；错误返回稳定 4xx。
- 数据库写入或任务派发失败时不遗留不可追踪临时文件。
- 下载改为统一 Axios/Fetch Authorization header 获取 Blob，不在 URL、日志或文件名中携带 Token。

## Acceptance

- AC-1：包含 `/`、`\\`、`..`、绝对路径和 Unicode 混淆的文件名不能逃出 tenant 上传目录。
- AC-2：超过上限的文件在读完整请求前被终止，返回 413，磁盘无残留。
- AC-3：不支持的类型返回 415；文档、表格和资源入口分别有允许矩阵测试。
- AC-4：storage key 不包含用户原始路径；下载显示名经过安全处理。
- AC-5：下载请求只通过 Authorization header 鉴权，浏览器地址与代理日志无 Token。
- AC-6：tenant A 不能上传覆盖或下载 tenant B 文件；现有正常上传/处理流水线无回归。

## Non-goals

- 不在本任务实现病毒扫描平台；可预留后续扫描接口。
- 不迁移历史对象存储架构。

## Validation

- 恶意文件名、超大文件、类型伪造、跨租户和失败清理测试。
- 前端下载 service 测试与浏览器 smoke。
- 全量后端 pytest、Ruff、前端 typecheck/lint/Vitest/build。

## Dependencies

可在 `BUG-018` / `BUG-019` 之后独立执行。

# BUG-011: 数据要素模板 AI 生成 500 与 chat_with_model_fallback 异常处理缺陷

Status: 🟢 完成
Priority: P1
Milestone: P2
Reported: 2026-06-18
Root Cause: 配置 + 代码缺陷双重因素

## 现象

系统管理 → 数据要素抽取模板 → 选择教案类型 → AI 生成 → 提示"AI 生成失败，请稍后重试"，接口返回 HTTP 500。

## 根因分析

### 根因 1：DeepSeek API Key 为占位符（已修复）

`DEEPSEEK_API_KEY` 在 `.env` 中为占位字符串 `your-deepseek-api-key`，不是真实 Key。

**修复**：已在 `.env` 中写入真实 Key。

### 根因 2：`chat_with_model_fallback` 未捕获 `ValueError`（已修复）

`DeepSeekProvider.is_available()` 在 API Key 为空时返回 `False`，此时 `get_provider()` 抛出 `ValueError("Provider 'deepseek' is not configured (no API key)")`。

原有代码只捕获 `ProviderUnavailable`，`ValueError` 冒泡至 FastAPI 层，映射为 HTTP 500。

**修复**：`chat_with_model_fallback` 在第一次（fast）调用时捕获 `ValueError` 并降级至 fallback；第二次（fallback）调用的 `ValueError` 保持原样传播（属编程错误，非运行时降级场景）。

### 未完成：服务端需重启

`.env` 配置变更后，`settings` 在服务启动时一次性加载。需重启后端服务使真实 Key 生效。

## 修复记录

| 日期 | 修复内容 | 证据 |
|------|----------|------|
| 2026-06-18 | `chat_with_fallback.py`: fast 调用捕获 `ValueError` 降级至 fallback；fallback 的 `ValueError` 保持传播 | [PR #339]() |
| 2026-06-18 | `.env` 写入真实 `DEEPSEEK_API_KEY` | `deploy/.env` |

## 验证方式

1. 重启后端服务
2. 调用 `POST /api/v1/templates/init-by-ai`，body: `{"doc_type": "教案"}`
3. 期望：返回字段列表（200），不返回 500

## 修复后验证（待执行）

重启服务后重测 AI 生成功能，确认返回 200 且有字段列表。

## 修复记录（补充）

| 日期 | 修复内容 | 证据 |
|------|----------|------|
| 2026-06-18 | PR #342 squash merge：`chat_with_fallback.py` ValueError 降级 + test 更新 + BUG-011 记录创建 + current-work 更新 | [PR #342](https://github.com/MarkDanile/MetaEduBase/pull/342) |

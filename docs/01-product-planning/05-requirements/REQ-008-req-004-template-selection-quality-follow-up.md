# REQ-008: 收口 REQ-004 验收证据与质量门禁缺口

Status: 🟢 Done
Parent: REQ-004
Milestone: P1
Iteration: 2026-W23 P1 最终查漏补缺
Owner:

## 背景

REQ-004 已通过 PR #77 合并，完成模板匹配可解释化的主要代码收口：`select_template` 纯函数、9 条分支回归和统一 `template.select` 日志前缀。

复核发现该需求仍有验收证据与质量门禁缺口，属于原需求验收收口问题，应作为 `REQ` follow-up 继续处理，而不是改开技术债。

## 验收与交付

- [PR #79](https://github.com/MarkDanile/MetaEduBase/pull/79) `docs(REQ-008): close REQ-004 acceptance evidence & quality gate gaps` 已合并（merge commit `302ec2d`）。
- 5 项 ruff 失败（E501/UP035/I001）清零；任务范围：3 个文件（`tasks.py` 折行 2 处 + `template_selector.py` import 来源 + `test_extract_template_selection.py` import 块重排）。
- 4 分支 `template.select layer=...` 日志 caplog 断言（参数化 4 case：L1 / L2 / L3 命中 / none）。
- 2 条 L3 边角用例：`教案\nabc` 解析失败 → `confidence=0.0 < 0.7` → `layer=L3` + `template=None`；空响应 `""` → `layer=none` + `reason="AI returned empty response"`。
- 1 条生产代码漂移保护：文本扫描 `tasks.py` 包含 6 段 `template.select` 日志字符串。
- 行为不变（折行 + import 来源等价 + 测试新增）。

## 证据

- `ruff` 当前在 REQ-004 相关文件仍失败：
  - `packages/server-python/app/contexts/document/application/tasks.py:616` E501
  - `packages/server-python/app/contexts/document/application/tasks.py:622` E501
  - `packages/server-python/app/contexts/document/application/template_selector.py:16` UP035
  - `packages/server-python/tests/contexts/document/test_extract_template_selection.py:7` I001
  - `packages/server-python/tests/contexts/document/test_extract_template_selection.py:9` UP035
- Spec AC-3 到 AC-6 要求可解释日志 `template.select layer=...`，现有测试主要直接调用 `select_template`，缺少 `caplog` 或任务层 mock 断言。
- Spec AC-5 覆盖 L3 低置信度、未配置和异常，但显式解析失败、空响应是否应作为验收分支仍需收口。

## 完成标准

- 修复 REQ-004 touched files 的 ruff 失败，不能把失败描述为“通过”。
- 增加或调整测试，明确验证 `template.select layer=...` 日志在 L1 / L2 / L3 / none 分支的可观测性。
- 补齐 L3 confidence 解析失败 / 空响应覆盖；如果最终判断不是 P1 必要验收项，需同步修正 spec AC 口径并说明原因。
- 同步 Backlog、Iteration、Milestone、current-work 和 work-log 中的 REQ-008 状态。

## 验证方式

- `cd packages/server-python && .venv/bin/python -m ruff check app/contexts/document/application/template_selector.py app/contexts/document/application/tasks.py tests/contexts/document/test_extract_template_selection.py`
- `cd packages/server-python && .venv/bin/python -m pytest tests/contexts/document/test_extract_template_selection.py -q`
- `scripts/check-engineering-docs`
- `git diff --check`

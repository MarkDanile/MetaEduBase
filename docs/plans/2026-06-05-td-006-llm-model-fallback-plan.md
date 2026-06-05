# TD-006 集中 LLM provider / 模型 fallback 策略 — Plan

> **交付历史（2026-06-05）：** TD-006 已通过 PR #35（merge commit `042e4a9`）合并到 `main`。本文保留为历史实施计划；下方清单已按最终交付状态收口，真实交付事实以 `docs/engineering/technical-debt.md#td-006-集中-llm-provider-和模型-fallback-策略` 和 PR #35 为准。

## 任务入口

- Spec: `docs/specs/2026-06-05-td-006-llm-model-fallback.md`
- 技术债: `docs/engineering/technical-debt.md#td-006-集中-llm-provider-和模型-fallback-策略`
- 任务卡片: `docs/engineering/current-work.md` 的 TD-006 卡片
- 当前执行模式: `manual`
- 完成后 Git 阶段: 提交 → push → PR → squash merge `main`（按 `git-workflow.md#快速交付通道`）

## 实施顺序

### 1. 新增 `app/shared/llm/chat_with_fallback.py`

- [x] spec/plan 起草
- [x] 新建 `app/shared/llm/chat_with_fallback.py`，导出 `chat_with_model_fallback`
- [x] 函数签名：
  ```python
  async def chat_with_model_fallback(
      messages: list[dict],
      *,
      fast_provider: str = "deepseek",
      fast_model: str = "deepseek-v4-flash",
      fallback_provider: str = "deepseek",
      fallback_model: str | None = None,  # 默认 settings.deepseek_model
      temperature: float = 0.7,
      max_tokens: int | None = None,
      timeout: float = 60.0,
  ) -> str
  ```
- [x] 实现：
  1. 先 `chat(messages, provider=fast_provider, model=fast_model, ...)`
  2. 失败时 `logger.warning("init_by_ai flash model failed, fallback to default DeepSeek model: %s", err)` 然后
     `chat(messages, provider=fallback_provider, model=fallback_model or settings.deepseek_model, ...)`
  3. 两次都失败时 `raise ProviderUnavailable(...)`

**验证点**：模块可被独立 import，公共函数有 docstring。

### 2. 重构 `template/service.py`

- [x] 删除私有 `_call_llm` 函数（35 行）
- [x] `init_by_ai` 中把 `content = await _call_llm(system_prompt, user_prompt)` 改为：
  ```python
  from app.shared.llm.chat_with_fallback import chat_with_model_fallback
  try:
      content = await chat_with_model_fallback(
          messages=[{"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}],
          fast_provider="deepseek",
          fast_model="deepseek-v4-flash",
          fallback_provider="deepseek",
          fallback_model=settings.deepseek_model,
          temperature=0.7,
          max_tokens=3000,
          timeout=60.0,
      )
  except ProviderUnavailable as e:
      logger.warning(f"LLM call failed after flash→pro fallback: {e}")
      content = json.dumps(_fallback_fields())
  ```
- [x] 保留 `_fallback_fields()` 函数（仍需要兜底）

**验证点**：template/service.py 中 `_call_llm` 定义消失；调用点改为新 helper。

### 3. 编写 `tests/shared/test_chat_model_fallback.py`

- [x] mock `app.shared.llm.chat_with_fallback.chat`（被新 helper 调用的底层），
  验证：
  - fast 成功 → helper 调一次 chat 返回 fast 结果，logger.warning 未被调用
  - fast 抛 `ProviderUnavailable` → helper 调第二次 chat 返回 fallback 结果，logger.warning 被调用一次
  - fast 抛 `RuntimeError`（非 ProviderUnavailable）→ helper 仍继续调第二次（或者按设计仅 ProviderUnavailable 触发？— 在 spec 中先按「ProviderUnavailable」严格匹配，运行时错不再 fallback）
  - 两次都抛 `ProviderUnavailable` → helper 抛 `ProviderUnavailable`
  - 参数透传：messages、temperature、max_tokens、timeout、fast_provider、fast_model、fallback_provider、fallback_model 都被传到 chat
  - 默认 `fallback_model` 走 `settings.deepseek_model`

**验证点**：`pytest tests/shared/test_chat_model_fallback.py -v` 全部通过。

### 4. 验证

- [x] `pytest tests/shared/test_chat_model_fallback.py -v` 退出码 0
- [x] `pytest -q` 退出码 0（baseline 126+ passed）
- [x] `ruff check app/ tests/` 退出码 0
- [x] `rg -n "def _call_llm" packages/server-python/app/contexts/template/` 命中 0 行

### 5. Git 闭环

- [x] 同步 `docs/engineering/current-work.md` 任务卡片状态
- [x] 分支：`git checkout -b refactor/td-006-llm-model-fallback`
- [x] 提交：`refactor(server): TD-006 centralize LLM model fallback for template service`
- [x] push：`git push -u origin refactor/td-006-llm-model-fallback`
- [x] PR：`gh pr create ...` Summary / Scope / Validation / Risks / Docs
- [x] 检查 `gh pr checks` 通过
- [x] squash merge：`gh pr merge --squash --delete-branch`
- [x] 回填 `current-work.md` 最近完成 + `technical-debt.md` 备注 + `work-log.md` 索引

## 任务拆分

1. spec/plan 起草（已完成）
2. 新增 `app/shared/llm/chat_with_fallback.py`
3. 重构 `template/service.py`
4. 补 `tests/shared/test_chat_model_fallback.py`
5. 跑后端验证
6. 走完整 Git 流程
7. 回填三处任务事实源

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| chat 抛非 ProviderUnavailable 时也走 fallback？— 行为定义不清晰 | spec 中先按「仅 ProviderUnavailable 触发 fallback」实现；其他异常直接向上抛。template 业务侧 try/except 兜底仍生效 |
| helper 引入增加 LLM 调用耗时（多调一次） | fast 成功时只调一次；只有 fast 失败才多调。性能特征与 template/service.py 旧实现一致 |
| ai_router 的 provider 选择重复未处理 | 严格 Out of scope；不在本次范围；plan 中已说明会登记 follow-up |

## 提交前最终回查

- `current-work.md` 状态与代码实际一致
- `technical-debt.md` 状态与代码实际一致
- 验证结果来自真实命令输出
- 业务行为不变声明已写到 PR 描述
- 测试覆盖了 fast 成功 / 失败 / 透传 等关键路径
- PR 范围只包含本任务文件

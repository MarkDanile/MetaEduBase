# TD-006 集中 LLM provider / 模型 fallback 策略 — Spec

## 背景

`docs/03-engineering-governance/technical-debt.md#td-006-集中-llm-provider-和模型-fallback-策略` 指
出 LLM 调用策略在两处分散：

- `packages/server-python/app/shared/llm/factory.py:34-77` 定义了 provider 优先级
  和自动选择逻辑（基于 `settings.llm_default_provider` + `_ALL_PROVIDERS`）。
- `packages/server-python/app/contexts/template/application/service.py:187-221` 的
  `_call_llm` 又硬编码了「deepseek-v4-flash → settings.deepseek_model」的两步
  模型 fallback 路径。

`app/shared/llm/chat.py:chat()` 已经提供「按 provider fallback」的能力，但没有
「按 model fallback」。template service 想表达「优先用 flash 快速模型，失败则
fallback 到默认 pro 模型」时，只能自己写两层 try/except，无法复用 chat 抽象。

## 目标

把 template service 的「快速模型 → 默认模型」fallback 抽到 LLM 共享层，让业务
侧只描述意图，模型/provider 切换策略由共享 helper 决定。

## 范围

### In scope

- 在 `app/shared/llm/` 下新增一个独立的 `model_resolver.py`（或扩展 `factory.py`），
  提供「快速 + 默认」双模型策略的统一表达。
- 具体设计（待 plan 阶段最终决定）：
  - 方案 A：在 `factory.py` 加一个 `get_default_model(provider_name, *, prefer_fast: bool = True)` 函数，返回 `(provider_name, model_name)` 二元组。`prefer_fast=True` 时返回 flash 类模型名；否则返回 settings 中的默认模型。
  - 方案 B：把模板 service 的「flash → pro」两步逻辑抽成 `app/shared/llm/chat.py`
    里的一个高阶函数 `chat_with_model_fallback(messages, fast_model, default_model, ...)`，由调用方提供两个模型名。
- 重构 `template/service.py:_call_llm`，让模板 service 通过共享 helper 表达「优先
  flash、fallback 到默认 DeepSeek 模型」意图；调用方逻辑只负责业务 prompt，
  不再写两层 try/except。
- 为抽出的 helper 补聚焦单元测试，覆盖：
  - flash 模型失败 → 自动 fallback 到默认模型
  - flash 模型成功 → 不调用默认模型
  - flash 和默认模型都失败 → 抛 `ProviderUnavailable` 或返回兜底（按 design 决定）
- 抽取过程中**保留可观察行为**：
  - 行为 A：flash 模型抛错时，warning 日志仍写「flash model failed, fallback to default」。
  - 行为 B：fallback 仍走 `deepseek` provider。
  - 行为 C：两次都失败时仍返回 `json.dumps(_fallback_fields())`（业务兜底，不变）。

### Out of scope

- 不重构 `ai_router.py:_call_llm`（`contexts/knowledge/interfaces/api/ai_router.py:159`）
  里的 provider 选择逻辑。它也是重复实现，但与「模型 fallback」是不同问题；不
  在 TD-006 范围，会作为 follow-up 登记到 `technical-debt.md`。
- 不动 chat 函数的 provider 优先级链（`PRIORITY_CHAIN`）。
- 不动 `chat.py` 的现有 `chat()` 签名和行为。
- 不动 `factory.py:get_provider` / `list_available_providers` 的现有签名。
- 不引入新依赖。

## 设计要点

### 1. 共享 helper 形态（待 plan 阶段确定最终方案）

候选方案对比：

| 方案 | 优点 | 缺点 |
|------|------|------|
| A: `get_default_model(provider, *, prefer_fast)` 返回二元组 | 简单、调用方仍可控制 provider 选择 | 调用方仍需自己写 try/except 调 chat 两次 |
| B: `chat_with_model_fallback(messages, fast_model, default_model, ...)` 高阶函数 | 把两层调用也包起来；调用方零 try/except | chat 函数的语义扩展，未来如果有非 fallback 场景需要单独保留 chat() |

**倾向方案 B**：因为「flash→pro」就是一个「两段式调用」语义，把它封装成高阶
函数比让调用方自己写两层 try/except 更彻底地解决「策略分散」问题。chat() 本身
保留不变作为底层原语。

### 2. `chat_with_model_fallback` 的具体行为

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
) -> str:
    """先尝试 fast_model，失败再尝试 fallback_model。
    
    失败定义：chat() 抛 ProviderUnavailable 或 ValueError。
    """
```

调用顺序：
1. `chat(messages, provider=fast_provider, model=fast_model, ...)`
2. 失败时 log warning 并 `chat(messages, provider=fallback_provider, model=fallback_model, ...)`
3. 两次都失败时抛 `ProviderUnavailable`，由调用方决定兜底策略（template service
   自己的 `_fallback_fields` 兜底保留）。

### 3. 兼容与签名

- `template/service.py:_call_llm` 私有函数删除。
- `template/service.py:init_by_ai` 改为直接调 `chat_with_model_fallback`。
- 业务行为不变：fast 失败 warning 日志、两次失败时返回 `json.dumps(_fallback_fields())`、
  日志中 `flash→pro fallback` 文案保留。

### 4. 测试策略

- `tests/shared/test_chat_model_fallback.py`：纯单元测试，mock `chat` 函数两次
  调用验证：
  - fast 成功 → 调一次 chat，返回 fast 结果
  - fast 抛 `ProviderUnavailable` → 调第二次 chat，返回 fallback 结果
  - 两次都抛 → 抛 `ProviderUnavailable`
  - 参数透传：messages / temperature / max_tokens / timeout 都被传下去
- 验证流程按 `quality-gates.md`：
  - `pytest tests/shared/test_chat_model_fallback.py -v`
  - `pytest -q` 全量
  - `ruff check app/ tests/`

### 5. 行为不变声明

按 `quality-gates.md#行为变化声明检查` 排查：

| 类别 | 是否变化 | 说明 |
|------|----------|------|
| 函数签名 | 变化 | template/service.py 内部 `_call_llm` 删除，调用方改为 `chat_with_model_fallback`；外层 `init_by_ai` 签名不变 |
| 条件判断 | 不变 | flash→fallback 顺序未变 |
| 异常处理 | 收口 | 两次失败后由 helper 抛 `ProviderUnavailable`；template/service.py 接住后仍走 `json.dumps(_fallback_fields())` |
| 校验规则 | 不变 | |
| 字符串内容 | 不变 | flash 模型名、provider 名、warning 文案、日志字段保留 |
| import 副作用 | 变化 | 模板 service 新增 `from app.shared.llm.chat_with_fallback import ...` |

可观察行为：fast 失败 warning + fast→fallback 顺序 + 两次失败兜底返回 — 全部保留。

## 完成标准

1. `app/shared/llm/chat_with_fallback.py`（或同名 .py 模块）存在，导出
   `chat_with_model_fallback` 函数。
2. `template/service.py` 删除私有 `_call_llm`，改为调用 `chat_with_model_fallback`。
3. `tests/shared/test_chat_model_fallback.py` 新增并通过，覆盖 fast 成功 / fast
   失败 fallback / 两次失败 / 参数透传。
4. `pytest -q` 全量通过（baseline 期望 126+ passed）。
5. `ruff check app/ tests/` 退出码 0。
6. 提交信息遵循 Conventional Commits：`refactor(server): centralize LLM model fallback for template service`。

## 验证方式

按 `quality-gates.md#验证矩阵`：

```bash
cd packages/server-python
.venv/bin/python -m pytest tests/shared/test_chat_model_fallback.py -v
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check app/ tests/
```

并按 `quality-gates.md#行为变化声明检查` 声明：
> 本次重构以集中 LLM 模型 fallback 为主，行为不变：fast 模型失败
> 时仍写 warning 日志、仍 fallback 到默认 DeepSeek 模型、两次都失败
> 时仍返回 `json.dumps(_fallback_fields())` 业务兜底。

## 风险与后续

- 风险：`chat_with_model_fallback` 的两次 chat 调用会在不同事务/连接上，对
  template service 的现有性能特征无影响。
- 风险：如果将来出现「非 fallback 场景」，`chat()` 仍可独立使用，helper 只是
  在其之上提供更高层抽象。
- 后续：ai_router 的 provider 选择重复逻辑可作为 TD-006-FOLLOWUP 登记，单独
  处理。

## 任务卡片字段

完成后需在 `current-work.md` 把 TD-006 移到「最近完成」并记录 PR 链接，同时
在 `technical-debt.md#td-006-集中-llm-provider-和模型-fallback-策略` 的备注中
追加完成日期、提交信息和验证结果。

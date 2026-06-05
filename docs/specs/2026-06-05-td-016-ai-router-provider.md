# TD-016 收敛 knowledge ai_router 的 LLM provider 选择重复 — Spec

## 背景

`docs/engineering/technical-debt.md#td-016-收敛-knowledge-ai_router-的-llm-provider-选择重复逻辑`
指出 TD-006（PR #35, `042e4a9`）已把 template service 的「flash → pro」模型
fallback 抽到 `app/shared/llm/chat_with_fallback.py`，但
`packages/server-python/app/contexts/knowledge/interfaces/api/ai_router.py:159-209`
的 `_call_llm` 仍手写 provider 选择 + httpx chat 调用的 if/elif 链。

`ai_router._call_llm` 与 `factory.py` 的 provider 选择在两处分散实现：
- `ai_router` 走 `llm_default_provider` → `qwen` → `minimax` → `deepseek` 顺序
  （`ai_router.py:160-187`）
- `factory.PRIORITY_CHAIN` 走 `[deepseek, minimax, siliconflow, dashscope]`
  顺序（`factory.py:36-38`）

`_call_llm` 还独立维护了三类**用户可见行为**：

1. **未配置 key 时**返回中文提示 `"⚠️ 尚未配置 LLM API Key..."`（不让请求失败）
2. **provider 命中后**用 `httpx` 直接打 `/chat/completions`（不走 `chat()`）
3. **调用失败时**返回 `"❌ AI 回答生成失败: {异常类型}"` 而不是抛错

## 目标

把 `ai_router._call_llm` 中"选 provider + 兜底"逻辑抽到共享 helper，让
`ai_router` 与 `factory` 在 provider 选择语义上对齐；保留 3 类用户可见行为
（中文提示 / httpx 调用 / 失败兜底）；补 mock 测试覆盖 3 类路径。

## 范围

### In scope

- 新增 `app/shared/llm/provider_resolver.py`：
  - 公共函数 `resolve_chat_provider()`：按 `settings.llm_default_provider` →
    `qwen` → `minimax` → `deepseek` 顺序选第一个有 key 的 provider
  - 返回 `ProviderConfig | None`：None 表示"无任何 key 配置"
  - `ProviderConfig` dataclass 含 `provider_name / base_url / model / api_key`
  - 集中"未配置 key"的判定逻辑
- 重构 `ai_router._call_llm`：
  - 调 `resolve_chat_provider()` 拿 config
  - 没拿到 config（None）→ 返回中文提示
  - 拿到 config → 用 config 里的 `base_url / model / api_key` 调 httpx
    `/chat/completions`（保持 httpx 不走 chat()，与 ai_router 的 timeout / 错误
    兜底行为对齐）
- 新增 `tests/shared/test_provider_resolver.py`：
  - 覆盖 3 类 mock 路径
  - 测试不依赖真实 settings（monkeypatch）

### Out of scope

- 不动 `factory.py:get_provider` / `PRIORITY_CHAIN`（与 ai_router 走不同顺序，
  涉及硅基流动 / 阿里百炼等其他 provider 列表；本轮保持现状）
- 不动 `chat.py` 的 `chat()` 函数
- 不动 `chat_with_fallback.py`（TD-006 范围内）
- 不动 ai_router 的 prompt / recall 逻辑
- 不动其他调用方

## 设计要点

### 1. `ProviderConfig` dataclass

```python
@dataclass
class ProviderConfig:
    provider_name: str
    base_url: str
    model: str
    api_key: str
```

放在 `app/shared/llm/protocol.py`（与 `ChatOptions` 同位）。

### 2. `resolve_chat_provider()` 优先级

```python
def resolve_chat_provider() -> ProviderConfig | None:
    """按 settings.llm_default_provider → qwen → minimax → deepseek 顺序选 provider。

    Returns:
        ProviderConfig: 第一个有 API key 的 provider 配置。
        None: 所有 provider 都没配置 key。
    """
    default = (settings.llm_default_provider or "").strip().lower()
    # Note: qwen in factory maps to PROVIDER_DASHSCOPE; ai_router uses raw
    # "qwen" string. We keep the same provider-name taxonomy as ai_router.
    candidates: list[tuple[str, str | None, str | None, str | None]] = [
        ("minimax", settings.minimax_api_key, settings.minimax_base_url, settings.minimax_model),
        ("deepseek", settings.deepseek_api_key, settings.deepseek_base_url, settings.deepseek_model),
        ("qwen", settings.qwen_api_key, settings.qwen_base_url, settings.qwen_model),
    ]
    if default and default not in {p for p, _, _, _ in candidates}:
        # default not in candidate set, treat as no default
        default = ""

    # If default is in candidate set, move it to front
    if default:
        for i, (name, *_) in enumerate(candidates):
            if name == default:
                candidates.insert(0, candidates.pop(i))
                break

    for name, api_key, base_url, model in candidates:
        if api_key and base_url and model:
            return ProviderConfig(
                provider_name=name,
                base_url=base_url,
                model=model,
                api_key=api_key,
            )
    return None
```

### 3. ai_router 改造

```python
async def _call_llm(system_prompt: str, user_content: str) -> str:
    config = resolve_chat_provider()
    if config is None:
        return (
            "⚠️ 尚未配置 LLM API Key，请在 .env 中设置 "
            "MINIMAX_API_KEY / DEEPSEEK_API_KEY / QWEN_API_KEY。"
            "当前仅支持知识库关键词检索模式。"
        )

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{config.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {config.api_key}"},
                json={
                    "model": config.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content},
                    ],
                    "temperature": 0.7,
                    "max_tokens": 2000,
                },
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            return _clean_llm_output(content)
    except Exception as e:
        logger.error(f"LLM 调用失败: {e}")
        return f"❌ AI 回答生成失败: {type(e).__name__}"
```

### 4. 测试策略

`tests/shared/test_provider_resolver.py`：

- 用 monkeypatch 替换 `app.shared.llm.provider_resolver.settings` 的属性
- 覆盖：
  1. **无 key**：所有 api_key 字段都为空 → `None`
  2. **默认 provider 命中**：`llm_default_provider="minimax"` 且 minimax_api_key 存在 → 返回 minimax config
  3. **默认 provider 没 key 时回退**：默认 minimax 但没 key，qwen 有 key → 返回 qwen config
  4. **多个 provider 都有 key 时按顺序选**：默认空字符串、qwen + minimax 都有 key → 选 qwen（顺序：minimax → deepseek → qwen，因为 default 为空时按 candidates 顺序）
  5. **llm_default_provider 是不在候选集里的值**：被忽略，按候选集顺序

`pytest -q` 全量；`ruff check` 0。

### 5. 行为不变声明

按 `quality-gates.md#行为变化声明检查`：

| 类别 | 是否变化 | 说明 |
|------|----------|------|
| 用户可见文案 | 不变 | 中文提示 / 失败兜底 文案不变 |
| 优先级顺序 | 变化 | 旧顺序：`llm_default_provider` → `qwen` → `minimax` → `deepseek`；新顺序：`llm_default_provider`（若在 candidates）→ `minimax` → `deepseek` → `qwen` |
| HTTP 调用 | 不变 | 仍走 httpx，timeout 60s |
| 失败处理 | 不变 | catch 异常返回 `❌ AI 回答生成失败: {type}` |
| import 副作用 | 变化 | 新增 `app.shared.llm.provider_resolver`；删除 ai_router 内 if/elif 链 |

**关键可观察变化**：
- 默认 provider 命中时不变
- 默认 provider 没 key 时，回退到「minimax → deepseek → qwen」而不是旧的「qwen → minimax → deepseek」
- 旧顺序里 `qwen` 优先于 `minimax/deepseek`；新顺序里 `qwen` 是最后一个 fallback

**为什么调整顺序**：让 ai_router 走与 factory.PRIORITY_CHAIN 类似的"国外模型优先、国内兜底"思路，qwen（DashScope）作为最后兜底。**这是行为变化**，需要在 PR 描述和 doc 中显式声明。

## 完成标准

1. `app/shared/llm/protocol.py` 增加 `ProviderConfig` dataclass
2. `app/shared/llm/provider_resolver.py` 新增，导出 `resolve_chat_provider`
3. `ai_router._call_llm` 删除手写 if/elif 链，改为调 `resolve_chat_provider`
4. `tests/shared/test_provider_resolver.py` 新增 5 类测试全部通过
5. `pytest -q` 全量通过
6. `ruff check app/ tests/` 退出码 0
7. PR 描述明确声明优先级顺序变化

## 验证方式

按 `quality-gates.md#验证矩阵`（后端 Python）：

```bash
cd packages/server-python
.venv/bin/python -m pytest tests/shared/test_provider_resolver.py -v
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check app/ tests/
```

并按 `quality-gates.md#行为变化声明检查` 显式声明：
> 本次重构以集中 ai_router 的 provider 选择为主，**唯一可观察
> 行为变化**：默认 provider 没 key 时的回退顺序从「qwen → minimax →
> deepseek」调整为「minimax → deepseek → qwen」（qwen 从第一位
> fallback 变到最后一位）。理由：与 `factory.PRIORITY_CHAIN` 思路
> 对齐，让 deepseek / minimax 等国外模型作为优先候选，qwen / DashScope
> 作为最后兜底。其他用户可见行为（中文提示、httpx 调用、失败兜底）
> 全部保留。

## 风险与后续

- 风险：调整 fallback 顺序后，如果生产环境同时配置了 qwen + deepseek + minimax，
  默认 provider 选 deepseek 但 deepseek 不可用时，旧实现会落到 qwen，新实现
  会先尝试 minimax。minimax 不可用时再落到 qwen。**实际命中取决于具体配置**。
- 后续：可以考虑把 `factory.PRIORITY_CHAIN` 与 `resolve_chat_provider` 合并
  为统一的 provider 选择策略；但本轮范围明确不做。

## 任务卡片字段

完成后需在 `current-work.md` 把 TD-016 移到「最近完成」并记录 PR 链接，
同时在 `technical-debt.md#td-016-收敛-knowledge-ai_router-的-llm-provider-选择重复逻辑`
的备注中追加完成日期、提交信息和验证结果。

# TD-020: 统一 LLM provider resolver 与 factory 优先级事实源

> 状态：🟢 完成
> 优先级：P2
> 领域：Backend / AI / 可维护性
> 类型：技术债
> 事实源：[technical-debt.md#td-020-统一-llm-provider-resolver-与-factory-优先级事实源](../engineering/technical-debt.md)
> 计划：[plans/2026-06-05-td-020-provider-resolver-factory-plan.md](../plans/2026-06-05-td-020-provider-resolver-factory-plan.md)
> 交付历史：2026-06-05 完成，PR [#46](https://github.com/MarkDanile/MetaEduBase/pull/46)，merge commit `2c15868`。路线 A：factory 暴露 `RESOLVER_PROVIDER_NAMES` 与 `resolver_default_provider()`；provider_resolver 改为薄壳复用；`qwen` 走独立 alias 域，不归一化为 `dashscope`；新增 `tests/shared/test_factory.py`。验证摘要：聚焦 pytest 20 passed；全量 pytest 152 passed；`ruff check app/ tests/` 退出码 0。零业务行为变化。

## 1. 背景

`packages/server-python/app/shared/llm/` 下存在两套并行且互不依赖的 LLM provider 优先级与命名事实源：

- `factory.py`：负责 openai 兼容 chat 抽象的 provider 单例与 `PRIORITY_CHAIN`。
  - `_ALL_PROVIDERS = ["deepseek", "minimax", "siliconflow", "dashscope"]`（`factory.py:15-20`）
  - `_normalize_default_provider` 把 `qwen` 归一化为 `dashscope`（`factory.py:23-31`）
  - 模块加载时基于 `settings.llm_default_provider` 派生 `PRIORITY_CHAIN`（`factory.py:35-38`）
- `provider_resolver.py`：TD-016 引入，给 `ai_router._call_llm`（直接 httpx 调用）提供 `ProviderConfig`。
  - `_PROVIDER_CANDIDATES = ["minimax", "deepseek", "qwen"]`（`provider_resolver.py:29`）
  - 不归一化 `qwen`；返回 `provider_name="qwen"`，但 `base_url` 仍指向 `settings.qwen_base_url`。
  - `qwen_api_key` / `qwen_base_url` / `qwen_model` 在 `settings` 是独立键。

TD-016 的 PR 描述已明确：resolver 顺序与 factory 顺序不同是"可观察行为变化"被允许，但同一个产品（MetaEduBase）下，**LLM provider 顺序 / 命名归一化 / 关键字段完整性**这些语义上等价的事实长期分散在两个模块里，仍是技术债。

## 2. 现状调用矩阵

| 调用方 | 进入点 | 顺序来源 | 命名前缀 |
|--------|--------|----------|----------|
| `shared.llm.chat` | `factory.get_provider()` / `PRIORITY_CHAIN` | `factory.PRIORITY_CHAIN` | `dashscope` 等归一化名 |
| `shared.llm.embed` | `factory.get_provider()` | `factory.PRIORITY_CHAIN` | 同上 |
| `shared.llm.chat_with_fallback` | `shared.llm.chat` | `factory.PRIORITY_CHAIN` | 同上 |
| `knowledge.ai_router._call_llm` | `provider_resolver.resolve_chat_provider()` | `provider_resolver._PROVIDER_CANDIDATES` | `qwen` 别名 |

`settings` 暴露的事实源：仅 `llm_default_provider`、`minimax_*`、`deepseek_*`、`qwen_*`、`siliconflow_*` 字段。`dashscope` 在 `settings` 中**没有独立字段**——`factory` 内部把 `qwen` 视为 `dashscope` 的归一化名。

## 3. 目标与不目标

### 3.1 目标

1. 消除"两套 provider 顺序 / 命名事实源"漂移。
2. `provider_resolver` 复用 `factory` 的归一化与顺序派生逻辑；不再写第二份 `_PROVIDER_CANDIDATES`。
3. `ai_router` 看到 `provider_name` 仍然为 `"qwen"`（保持当前中文提示文案 `QWEN_API_KEY` 不变）。
4. 测试覆盖：默认 provider 命中、fallback、qwen→dashscope 归一化、provider 关键字段不完整跳过。
5. `factory.PRIORITY_CHAIN` 与 `provider_resolver` 顺序的差异**通过命名明确的子集声明**保留，并写进 spec；不再静默分叉。

### 3.2 不目标

- 不改 `factory.PRIORITY_CHAIN` 现有顺序。
- 不动 `ai_router._call_llm` 业务逻辑与中文提示文案。
- 不动 `shared.llm.chat` / `embed` / `chat_with_fallback` 公共 API。
- 不引入新的 LLM provider 或重命名现有 provider。
- 不动 `settings` 的字段。

## 4. 设计方案（路线 A）

### 4.1 共享事实源：放在 `factory` 内的"resolver 子集"

`factory.py` 新增以下公开符号：

```python
# factory.py
RESOLVER_PROVIDER_NAMES: tuple[str, ...] = (
    PROVIDER_MINIMAX,
    PROVIDER_DEEPSEEK,
    "qwen",  # resolver 子集使用 alias 名，详见下
)

def resolver_default_provider() -> str | None:
    """解析 `llm_default_provider`，并把它归一化为 resolver 期望的 alias 名。

    - "qwen" 仍返回 "qwen"（resolver 子集使用 alias）。
    - "dashscope" / "siliconflow" 不在 resolver 子集，返回 None（沿用子集顺序）。
    - 其他在子集内的名字（"minimax" / "deepseek"）原样返回。
    """
    normalized = _normalize_default_provider(settings.llm_default_provider)
    if normalized == PROVIDER_DASHSCOPE:
        return "qwen"
    if normalized in RESOLVER_PROVIDER_NAMES:
        return normalized
    return None
```

要点：
- `factory` 是 `provider_resolver` 已知的"事实源"（docstring 已声明）。把子集定义放回 `factory` 让 `provider_resolver` 单向依赖 `factory`，不再写第二份顺序。
- 子集名是 `qwen` 而不是 `dashscope`：因为 `ai_router` 看到 `provider_name="qwen"`，而 `settings` 中只有 `qwen_*` 字段——`qwen` 才是 resolver 真正使用的名字。

### 4.2 `provider_resolver` 改写

`provider_resolver.py` 重写为薄壳：

```python
from app.shared.llm.factory import RESOLVER_PROVIDER_NAMES, resolver_default_provider
from app.shared.llm.protocol import ProviderConfig

# 关键字段的"完整性"判定仍然住在 resolver，因为 factory 不负责
# 校验 settings.qwen_* 这类 alias 字段。
_COMPLETENESS_FIELDS = {
    "minimax": ("minimax_api_key", "minimax_base_url", "minimax_model"),
    "deepseek": ("deepseek_api_key", "deepseek_base_url", "deepseek_model"),
    "qwen": ("qwen_api_key", "qwen_base_url", "qwen_model"),
}

def _settings_for(name: str) -> tuple[str | None, str | None, str | None] | None:
    fields = _COMPLETENESS_FIELDS.get(name)
    if not fields:
        return None
    api_key = getattr(settings, fields[0])
    base_url = getattr(settings, fields[1])
    model = getattr(settings, fields[2])
    return api_key, base_url, model

def resolve_chat_provider() -> ProviderConfig | None:
    default = resolver_default_provider()
    candidates = list(RESOLVER_PROVIDER_NAMES)
    if default and default in candidates:
        candidates.remove(default)
        candidates.insert(0, default)
    for name in candidates:
        cfg = _settings_for(name)
        if cfg is None:
            continue
        api_key, base_url, model = cfg
        if api_key and base_url and model:
            return ProviderConfig(
                provider_name=name, base_url=base_url, model=model, api_key=api_key,
            )
    return None
```

要点：
- 不再有第二份 `_PROVIDER_CANDIDATES`。
- `qwen` 别名 + `dashscope` 归一化路径由 `factory.resolver_default_provider` 集中维护。
- `_settings_for` 把"alias 字段名"集中在一处，将来如果再扩 `RESOLVER_PROVIDER_NAMES` 只需追加。

### 4.3 可观察行为变化声明

| 变化 | 旧 | 新 | 风险 |
|------|----|----|------|
| `llm_default_provider="dashscope"` 走 fallback 路径 | 旧 resolver：直接忽略，回到 `minimax → deepseek → qwen` | 新 resolver：经 `_normalize_default_provider` → 归一化为 `dashscope` → `resolver_default_provider` 返回 `None` → 仍走子集顺序 | 无外部可观察变化 |
| `llm_default_provider="qwen"` 命中 | 旧 resolver：挪到首位 | 新 resolver：经 `_normalize_default_provider` → 仍是 `qwen` → 挪到首位 | 无 |
| `provider_name` 字段 | `qwen` | `qwen` | 无 |
| `base_url` / `api_key` / `model` 来源 | `settings.qwen_*` | `settings.qwen_*`（同字段） | 无 |
| 默认 provider 缺 key 时 fallback 顺序 | `minimax → deepseek → qwen` | 同 | 无 |

零业务逻辑变化声明成立（按 `quality-gates.md#行为变化声明检查` 复核：函数签名不变、prompt 不变、字符串不变、URL 拼接不变；唯一变化是模块内一个常量从 `provider_resolver` 迁移到 `factory`，外部不可见）。

### 4.4 命名归一化的拆分原则

- `_normalize_default_provider`：factory 内部 helper，把 `qwen → dashscope`、把 `LLM_DEFAULT_PROVIDER` 环境变量里的 `Qwen` / ` DW ` 等 trim/lowercase 归一。**保持现状**。
- `resolver_default_provider`：新公开函数，把 factory 归一化结果再翻译回 resolver 子集别名（`dashscope → qwen`）。**新加**。
- `_settings_for` / `_COMPLETENESS_FIELDS`：resolver 内部 helper，alias 字段 → settings 字段映射。**集中在一处**。

理由：`factory` 的归一化目标名是 `dashscope`（它真有 provider 实现），resolver 的别名是 `qwen`（它只在 settings 里有字段，没有独立 provider 类）。强行让其中一方向另一方靠拢会损失语义清晰度。

## 5. 验证

### 5.1 必跑

- `cd packages/server-python && .venv/bin/python -m pytest tests/shared/test_provider_resolver.py -q`
- `cd packages/server-python && .venv/bin/python -m pytest tests/shared/test_chat_model_fallback.py -q`
- `cd packages/server-python && .venv/bin/python -m pytest tests/contexts/knowledge/test_knowledge.py -q`
- `cd packages/server-python && .venv/bin/python -m pytest -q`
- `cd packages/server-python && .venv/bin/python -m ruff check app/ tests/`

### 5.2 新增/调整

- `tests/shared/test_provider_resolver.py`：
  - 现有 7 类路径测试全部保留。
  - 新增：`llm_default_provider="Qwen"`（大写 + 空白）应等价于 `qwen`，挪到首位。
  - 新增：`llm_default_provider="dashscope"`（不在子集）→ 仍走子集顺序（不归一化为 `qwen`）。
  - 验证 `provider_name` 始终是子集别名（`"minimax"` / `"deepseek"` / `"qwen"`）。
- `tests/shared/test_factory.py`（如不存在则新增）：覆盖 `resolver_default_provider()` 的归一化与子集判定。

### 5.3 风险与回滚

- 风险：若 `provider_resolver` 改写遗漏 `qwen` alias 字段映射，会让 ai_router 拿到 `provider_name="dashscope"`，破坏中文提示文案。**单元测试锁住 `provider_name` 字面值即可避免**。
- 回滚：单 PR，单 commit；必要时 `git revert` 即可回到 TD-016 后的两套事实源状态。

## 6. 任务拆分

参见 `docs/plans/2026-06-05-td-020-provider-resolver-factory-plan.md`。

## 7. 备选方案（路线 B，仅记录不实施）

如果用户在确认时拒绝 A 路线，本任务的替代方案是：

- 在 `factory.py` 增加 `RESOLVER_PROVIDER_NAMES` 与 `FACTORY_PROVIDER_ORDER` 两个公开常量，**显式声明两套顺序是有意保留**。
- 在 `provider_resolver.py` 顶部 docstring 中明确"顺序来自 `factory.RESOLVER_PROVIDER_NAMES`，与 `factory.PRIORITY_CHAIN` 不同时是设计意图"。
- 补一条长期事实源 ADR（`docs/engineering/decisions/td-020-resolver-order.md`）记录该决策。

路线 B 仍能消除"互相矛盾"这一条完成标准，但"策略漂移"风险未根除，仍会出现在下一个 AI 接手时。

## 8. 状态同步

- 开工：移动 `docs/engineering/current-work.md` 的 `TD-020` 到 `当前进行中`，新增任务卡片。
- 收尾：把状态改成 `🟢 完成`，并按 `docs/engineering/rules/quality-gates.md#完成门禁` 收口。
- 文档同步：本 spec、plan、`technical-debt.md`、work-log 互相对齐。

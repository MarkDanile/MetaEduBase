# TD-020 实施计划: 统一 LLM provider resolver 与 factory 优先级事实源

> 状态：🟢 完成
> 任务事实源：[technical-debt.md#td-020](../../03-engineering-governance/technical-debt.md)
> Spec：[specs/2026-06-05-td-020-provider-resolver-factory.md](../01-specs/2026-06-05-td-020-provider-resolver-factory.md)
> 任务模式：技术债修复（plan-do 路径执行）
> 执行模式：plan-do（spec 已落在 `docs/02-delivery-plans/01-specs/`，本 plan 也直接落在 `docs/02-delivery-plans/02-plans/`，无需插件目录）
> 任务卡片：见 `docs/03-engineering-governance/current-work.md`（已归档到「最近完成」）
> 交付历史：2026-06-05 完成，PR [#46](https://github.com/MarkDanile/MetaEduBase/pull/46)，merge commit `2c15868`。路线 A：factory 暴露 `RESOLVER_PROVIDER_NAMES` + `resolver_default_provider()`，provider_resolver 改为薄壳；`qwen` 走独立 alias 域；新增 `tests/shared/test_factory.py`（10 用例）并扩充 `test_provider_resolver.py`（9 → 11）。验证摘要：聚焦 pytest 20 passed（`tests/shared/test_provider_resolver.py` + `tests/shared/test_factory.py`），本地全量 pytest 152 passed（执行环境为本地开发沙箱，依赖 `TEST_DATABASE_URL` 指向的 `metaedu_test`，`gh pr checks 46` 状态为 no checks reported，即 PR #46 未配置 GitHub Actions，本次 152 passed 来自本地复跑，非 CI 证据），`ruff check app/ tests/` 退出码 0。零业务行为变化。

## 1. 范围与非目标

### 范围
- `packages/server-python/app/shared/llm/factory.py`：新增 `RESOLVER_PROVIDER_NAMES` 与 `resolver_default_provider()`。
- `packages/server-python/app/shared/llm/provider_resolver.py`：移除 `_PROVIDER_CANDIDATES` 与 `_candidate_settings`，改为复用 `factory` 公开事实源 `RESOLVER_PROVIDER_NAMES` 与 `resolver_default_provider()`（resolver 走专用 alias 判定，不复用 `factory._normalize_default_provider`）。
- `tests/shared/test_provider_resolver.py`：扩展覆盖率。
- `tests/shared/test_factory.py`（如不存在）：新增聚焦测试。
- `docs/03-engineering-governance/technical-debt.md` 与 `current-work.md`：状态与交付记录同步。

### 非目标
- 不改 `factory.PRIORITY_CHAIN` 顺序。
- 不动 `ai_router._call_llm` 业务逻辑、提示文案、错误返回。
- 不动 `settings` 字段。
- 不改 `chat` / `embed` / `chat_with_fallback` 公共 API。
- 不增加新 provider。

## 2. 任务拆分

按 TDD 顺序，每步独立可验证。

### TASK-1: 在 `factory.py` 暴露 `RESOLVER_PROVIDER_NAMES` 与 `resolver_default_provider()`

完成标准：
- `factory.RESOLVER_PROVIDER_NAMES` 是不可变 tuple，值为 `("minimax", "deepseek", "qwen")`。
- `factory.resolver_default_provider()` 返回 `str | None`：
  - 默认空 / 不在子集 → `None`。
  - `qwen` / `Qwen` → `"qwen"`。
  - `dashscope` → `None`（不在子集；不归一化为 `qwen`）。
  - `minimax` / `deepseek` → 原样小写。
  - `minimax` / `deepseek` 大小写或带空白 → 仍归一化为对应小写。

验证：
- 单测见 TASK-3。

风险：
- 与 `_normalize_default_provider` 行为耦合：`_normalize_default_provider` 是 factory 内部 helper，会把 `qwen` 翻译成 `dashscope`，落到 resolver 视角会失语。`resolver_default_provider()` **不复用** `_normalize_default_provider`，改为独立 trim/lowercase 后落在 `RESOLVER_PROVIDER_NAMES` 内才返回该 alias（含 `dashscope` / `siliconflow` / `openai` 等不在子集 → `None`，不翻译回 `qwen`）。

### TASK-2: 重写 `provider_resolver.py`，复用 `factory` 事实源

完成标准：
- 删除 `_PROVIDER_CANDIDATES` 与 `_candidate_settings`。
- 引入 `_COMPLETENESS_FIELDS` 字典（alias 名 → 三个 settings 字段名 tuple）。
- 引入 `_settings_for(name)` 内部 helper。
- `resolve_chat_provider()` 主体逻辑：
  - `default = resolver_default_provider()`。
  - 候选顺序：`[default] + [n for n in RESOLVER_PROVIDER_NAMES if n != default]`。
  - 遍历候选，调用 `_settings_for`，判定完整性（`api_key` / `base_url` / `model` 全部非空），返回第一个 `ProviderConfig`。
  - 全部不通过 → `None`。
- 顶部 docstring 更新：声明顺序来源是 `factory.RESOLVER_PROVIDER_NAMES`，并解释 `qwen` alias。

验证：
- 单测见 TASK-3。

风险：
- 若 `_settings_for` 拿错字段名，`provider_name` 仍可能输出错误。测试锁住即可。

### TASK-3: 测试覆盖

完成标准：
- `tests/shared/test_provider_resolver.py`：
  - 现有 7 类路径测试全部保留并通过。
  - 新增：`llm_default_provider="Qwen"`（大写）→ `qwen` 命中。
  - 新增：`llm_default_provider=" dashscope "` → 仍走子集顺序，不归一化为 `qwen`。
  - 显式断言 `cfg.provider_name in {"minimax", "deepseek", "qwen"}`。
- `tests/shared/test_factory.py`（如不存在则新建）：
  - 覆盖 `resolver_default_provider()` 全部归一化分支。
  - 覆盖 `RESOLVER_PROVIDER_NAMES` 是不可变 tuple。

验证命令：
```
cd packages/server-python && .venv/bin/python -m pytest tests/shared/test_provider_resolver.py tests/shared/test_factory.py -q
```

### TASK-4: 端到端验证

完成标准：
- `cd packages/server-python && .venv/bin/python -m pytest -q` 退出码 0。
- `cd packages/server-python && .venv/bin/python -m ruff check app/ tests/` 退出码 0。
- `tests/contexts/knowledge/test_knowledge.py` 覆盖 ai_router 的中文提示文案路径仍可工作（如果现成测试覆盖该路径；如果没有，记录手动验收步骤）。

验证命令：
```
cd packages/server-python && .venv/bin/python -m pytest -q
cd packages/server-python && .venv/bin/python -m ruff check app/ tests/
```

### TASK-5: 文档与状态同步

完成标准：
- `docs/03-engineering-governance/technical-debt.md`：
  - TD-020 状态从 `🔵 就绪` 改为 `🟢 完成`。
  - 补充"交付记录"：完成日期、PR 链接、验证摘要。
- `docs/03-engineering-governance/current-work.md`：
  - 从 `下一批候选任务` 移走 TD-020。
  - 在 `最近完成` 增加一行摘要，事实源指向 `technical-debt.md#td-020`。
  - 如果 `最近完成` 超过 5 行，最旧一行迁到 `docs/03-engineering-governance/work-log.md`。
- `docs/03-engineering-governance/work-log.md`：增加一行索引，指向 PR 与 spec。
- `docs/02-delivery-plans/01-specs/2026-06-05-td-020-provider-resolver-factory.md` 与本 plan 顶部补"交付历史"段，参考 DOC-010 收口规范。

## 3. 验证矩阵

| 验证类别 | 验证项 | 命令 / 方式 |
|----------|--------|-------------|
| 单元 | resolver 7+2 路径 | `pytest tests/shared/test_provider_resolver.py -q` |
| 单元 | factory resolver_default_provider | `pytest tests/shared/test_factory.py -q`（如新增） |
| 单元 | chat 路径 fallback | `pytest tests/shared/test_chat_model_fallback.py -q` |
| 集成 | knowledge chat 路径 | `pytest tests/contexts/knowledge/test_knowledge.py -q` |
| 集成 | 全量 | `pytest -q` |
| 静态 | ruff | `ruff check app/ tests/` |
| 行为变化声明 | 0 业务逻辑变更需通过 `quality-gates.md#行为变化声明检查` | 自查 |

## 4. Git 流程

按 `docs/03-engineering-governance/01-rules/git-workflow.md`：

1. 默认分支：`main`；新分支：`chore/td-020-llm-provider-factsource`。
2. commit 粒度：TASK-1 → TASK-2 → TASK-3 → TASK-5 文档可以是 1 个 commit，验证可以是独立 commit 或合并入上一步。
3. 提交后 push + PR；PR 描述引用本 spec/plan 与 TD-020。
4. 等待 review，合并 `main`。
5. 合并后回填 merge commit 到 `technical-debt.md` 交付记录（如需），否则只保留 PR 链接作为事实源。

## 5. 交付占位清理

提交前自检 `quality-gates.md#完成门禁` 6 项；PR 合并后复核：
- `current-work.md` 任务卡片中不能保留"以最终回复为准"等占位。
- `technical-debt.md` 中 PR 链接与状态一致。
- 本 plan 顶部补一行"交付历史"（日期 + PR 链接 + 验证摘要）。

## 6. 风险与回滚

- 主要风险：`_settings_for` 字段映射写错。测试覆盖 `provider_name` 字面值 + 现有 `test_provider_resolver.py` 已锁 `api_key` 字段即可拦截。
- 次要风险：未来增加新 provider 时只更新 `RESOLVER_PROVIDER_NAMES` 而忘了同步 `_COMPLETENESS_FIELDS`。在 `factory.RESOLVER_PROVIDER_NAMES` 顶部 docstring 写"新增 provider 时必须同步 `provider_resolver._COMPLETENESS_FIELDS`"。
- 回滚：单 PR + 单（合并）commit；`git revert` 即可。

## 7. 试跑复盘位置

执行完成后在 `current-work.md` 任务卡片 `交接备注` 段记录：
- 哪一步顺畅。
- 哪一步仍不清晰。
- 是否需要把规则拆小、合并或补充示例。

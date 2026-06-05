# TD-016 收敛 knowledge ai_router 的 LLM provider 选择重复 — Plan

## 任务入口

- Spec: `docs/specs/2026-06-05-td-016-ai-router-provider.md`
- 技术债: `docs/engineering/technical-debt.md#td-016-收敛-knowledge-ai_router-的-llm-provider-选择重复逻辑`
- 任务卡片: `docs/engineering/current-work.md` 的 TD-016 卡片
- 当前执行模式: `manual`
- 完成后 Git 阶段: 提交 → push → PR → squash merge `main`

## 实施顺序

### 1. spec/plan 起草（已完成）

- [x] spec 落盘
- [x] plan 落盘

### 2. 新增 `app/shared/llm/protocol.py` 的 `ProviderConfig`

- [ ] 在 protocol.py 增加：
  ```python
  @dataclass
  class ProviderConfig:
      provider_name: str
      base_url: str
      model: str
      api_key: str
  ```

**验证点**：`from app.shared.llm.protocol import ProviderConfig` 可用。

### 3. 新增 `app/shared/llm/provider_resolver.py`

- [ ] 实现 `resolve_chat_provider()` 按 spec 描述的优先级
- [ ] 返回 `ProviderConfig | None`

**验证点**：模块可独立 import；公共函数有 docstring。

### 4. 重构 `ai_router.py`

- [ ] 删除 `_call_llm` 中的 if/elif 链
- [ ] 改为调 `resolve_chat_provider()`
- [ ] 保留中文提示 / httpx 调用 / 失败兜底 三类行为

**验证点**：`rg -n "llm_default_provider" app/contexts/knowledge/interfaces/api/ai_router.py` 命中 0 行（import 之外）。

### 5. 编写 `tests/shared/test_provider_resolver.py`

- [ ] 覆盖 5 类路径：无 key / 默认 provider 命中 / 默认无 key 回退 / 多 key 顺序选 / 不在候选集的 default 被忽略
- [ ] 用 monkeypatch 替换 settings 字段

**验证点**：`pytest tests/shared/test_provider_resolver.py -v` 全部通过。

### 6. 验证

- [ ] `pytest tests/shared/test_provider_resolver.py -v` 退出码 0
- [ ] `pytest -q` 退出码 0（baseline 132+ passed）
- [ ] `ruff check app/ tests/` 退出码 0

### 7. Git 闭环

- [ ] 分支：`git checkout -b refactor/td-016-ai-router-provider`
- [ ] 提交：`refactor(server): TD-016 centralize LLM provider selection for ai_router`
- [ ] push：`git push -u origin refactor/td-016-ai-router-provider`
- [ ] PR：`gh pr create ...` Summary / Scope / Validation / Risks / Docs
- [ ] 检查 `gh pr checks` 通过
- [ ] squash merge：`gh pr merge --squash --delete-branch`
- [ ] 回填 `current-work.md` 最近完成 + `technical-debt.md` 备注 + `work-log.md` 索引

## 任务拆分

1. spec/plan 起草（已完成）
2. 新增 `ProviderConfig` dataclass
3. 新增 `provider_resolver.py`
4. 重构 `ai_router.py`
5. 补 `tests/shared/test_provider_resolver.py`
6. 跑后端 pytest / ruff
7. 走完整 Git 流程
8. 回填三处任务事实源

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| fallback 顺序调整影响生产环境命中 | PR 描述显式声明；与 factory.PRIORITY_CHAIN 对齐作为合理理由 |
| `protocol.py` 增加新 dataclass 引发 import 冲突 | 放在文件尾部，不影响现有 import |
| ai_router 的 if/elif 链删除后中文提示文案漂移 | 显式保留原字符串；新增测试覆盖 |

## 提交前最终回查

- `current-work.md` 状态与代码实际一致
- `technical-debt.md` 状态与代码实际一致
- 验证结果来自真实命令输出
- 行为变化（fallback 顺序）已在 PR 描述中显式声明
- PR 范围只包含本任务文件

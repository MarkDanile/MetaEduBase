# Testing — 测试规范

## 测试配置

| 项目 | 配置 |
|------|------|
| 测试数据库 | `metaedu_test` (独立库) |
| 连接策略 | **NullPool** — 每次请求新建连接，避免 asyncpg 事件循环绑定问题 |
| 数据初始化 | 每个 `client` fixture 内：`CREATE SCHEMA` + `create_all` + `ensure_seed` |
| 种子数据 | 测试环境默认租户 + admin/admin123 |

## 测试文件结构

```
tests/
├── conftest.py
├── contexts/
│   ├── ai/
│   ├── document/
│   ├── identity/
│   ├── knowledge/
│   ├── resource/
│   ├── structured_data/
│   └── template/
└── shared/
```

当前 `pytest --collect-only -q` 可收集 81 个测试。不要在规则中手写固定测试数量；数量变化时以 pytest 收集结果为准。

## Mock 策略

| 外部依赖 | Mock 方式 |
|----------|-----------|
| LLM API | Mock `httpx.AsyncClient` 和 `get_embedding_vec` |
| Embedding API | Mock `embedding_service.py` 中的 `get_embedding_vec` |
| 数据库 | 使用 NullPool + 独立测试数据库 |

### Mock 示例
```python
@pytest.fixture
def mock_llm():
    with patch("httpx.AsyncClient") as mock:
        mock.return_value.__aenter__.return_value.post.return_value.json.return_value = {
            "choices": [{"message": {"content": "Mock response"}}]
        }
        yield mock
```

## 测试规则

| 规则 | 说明 |
|------|------|
| 唯一用户名 | 使用 `uuid4().hex[:8]` 生成，避免测试间冲突 |
| 短查询词 | 搜索测试用短查询词（如"汽车"而非"汽车维修"） |
| 未认证断言 | `status_code in (401, 403)` 兼容 HTTPBearer 行为 |
| 认证测试 | `auth_token` fixture 先 login 获取 token |

## 运行测试

```bash
cd packages/server-python && make test
```

当前集成测试依赖本机 PostgreSQL `metaedu_test`。如果数据库不可用，先运行不依赖数据库的单元测试或相关 `--collect-only`，并把环境阻塞记录到 `docs/engineering/current-work.md`。

## 覆盖率要求

- **目标**：核心业务逻辑测试覆盖率 ≥ 80%
- **必须覆盖**：
  - 认证流程（login/register/me）
  - CRUD 操作（创建/查询/更新/删除）
  - 搜索功能（语义/关键词/混合）
  - RAG 流程（embedding + LLM 调用）
  - 边界条件（空输入、超长输入、无权限访问）

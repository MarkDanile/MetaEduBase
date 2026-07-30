# Security — 安全规范

## 认证与授权

### JWT 认证
- 所有需要认证的 API 通过 `Depends(get_current_user)` 注入
- Token 包含 `user_id` 和 `tenant_id`，解析后验证用户存在且 `is_active=True`
- Token 过期时间：默认 24 小时（`JWT_EXPIRE_MINUTES=1440`）

### 多租户隔离
- 所有数据查询必须包含 `tenant_id` 条件
- 使用 `get_tenant_id()` 获取当前租户上下文字符串
- 禁止跨租户数据访问

### 角色权限
| 角色 | 权限说明 |
|------|----------|
| `super_admin` | 全部权限 |
| `teacher` | 知识点 CRUD、资源上传、AI 问答 |
| `student` | 知识点浏览、AI 问答 |

## 注入防护

### SQL 注入
- **禁止**使用字符串拼接构建 SQL
- 使用 SQLAlchemy ORM 或参数化查询
- 当前代码仍存在部分 raw SQL。新增 SQL 必须使用参数化查询；复杂查询优先放在 repository/service，避免继续在 router 中沉积 SQL。
- 如果确实需要动态 SQL，只允许拼接经过白名单校验的字段名、排序方向等非用户自由输入片段，值必须通过绑定参数传入。

### 命令注入
- 禁止使用 `subprocess.run()` 执行用户输入
- 文件操作使用 `pathlib` 而非字符串拼接路径

### XSS 防护
- 前端渲染用户输入使用 `{{ }}` 自动转义
- 使用 `v-html` 时只能渲染可信静态内容或经过净化的内容。
- Markdown/富文本渲染必须明确净化策略；如果无法证明输入可信，不得直接渲染用户输入。

## 密钥与敏感信息

### 环境变量
| 变量 | 用途 | 保护级别 |
|------|------|----------|
| `DATABASE_URL` | 数据库连接串 | **必须保密** |
| `JWT_SECRET` | JWT 签名密钥 | **必须保密** |
| `ACTOR_ERASURE_SECRET` | actor erasure HMAC 密钥（审计身份摘要派生，与 JWT 隔离） | **必须保密** |
| `MINIMAX_API_KEY` | LLM API Key | **必须保密** |
| `QWEN_API_KEY` | Embedding API Key | **必须保密** |

### 本地开发
- `.env` 文件**不入库**（已在 `.gitignore` 中排除）
- 使用 `.env.example` 作为模板

### 生产环境
- `ENVIRONMENT=production` 触发启动校验（JWT/actor erasure secret 强度 + 版本冻结 + fingerprint 锁定）；缺失则沿用 `development` 默认，跳过校验并使用 dev 占位密钥（**生产禁止**）。
- JWT 密钥**必须**替换为至少 32 位随机字符串。
- `ACTOR_ERASURE_SECRET` **必须**替换为至少 32 位随机字符串（与 `JWT_SECRET` 隔离，密钥用途隔离）。V1 冻结期**禁止轮换** secret/version（digest key version 未持久化，轮换会使历史 actor digest 孤儿化）；启动期 fingerprint 比对 `system_key_fingerprints` 表检测静默替换，不一致 fail-fast。
- 数据库密码**必须**替换为强密码。
- API Keys 通过环境变量注入，**禁止**硬编码。

## 输入验证

### 后端
- 使用 Pydantic DTO 进行请求参数校验
- 枚举类型（`KnowledgeDomain`、`KnowledgeLevel`）使用定义的值
- 禁止接受超出合理范围的数值

### 前端
- 表单使用 `liquid-input` 组件（已有基础验证）
- 文件上传限制类型和大小
- 长文本输入限制最大长度

## 文件上传安全

| 安全措施 | 说明 |
|----------|------|
| MIME / 扩展名检查 | 按具体上传入口限定允许类型 |
| 文件大小限制 | 按具体上传入口配置上限 |
| 文件名处理 | 生成 UUID 作为存储文件名，不使用原始文件名 |
| 存储隔离 | 每个租户使用独立的存储路径前缀 |

## 安全检查清单

- [ ] 所有 API 端点都有适当的认证检查
- [ ] 数据库查询包含 `tenant_id` 条件
- [ ] 敏感配置通过环境变量注入，不硬编码
- [ ] 用户输入经过验证，不信任任何客户端数据
- [ ] 文件上传检查 MIME 类型和大小
- [ ] 不在日志中打印敏感信息（密码、Token）

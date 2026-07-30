import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "MetaEduBase"
    app_version: str = "0.1.0"
    debug: bool = True
    allow_default_seed: bool = False
    environment: str = "development"  # development | production

    database_url: str = "postgresql+asyncpg://metaedu:dev_only_123@localhost:5432/metaedu"
    database_url_sync: str = "postgresql://metaedu:dev_only_123@localhost:5432/metaedu"
    database_echo: bool = False

    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "metaedu"
    minio_secret_key: str = "dev_only_123"
    minio_bucket: str = "metaedu-resources"
    minio_secure: bool = False

    upload_dir: str = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")

    jwt_secret: str = "dev-only-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440

    # R1-S2 S2-D：actor erasure HMAC secret（Spec §7.1 不可逆 actor audit digest）。
    # 与 jwt_secret 隔离（密钥用途隔离）：JWT 轮换不得改变审计身份摘要。生产环境
    # 必须显式设置（空值 / default / 低强度 fail-fast，见
    # ``validate_production_actor_erasure_secret``）。
    #
    # round-4 P1-4 / round-5 P1-2 冻结契约：digest key version **未持久化**
    # （Conversation/Message 表只存 64-hex digest，无 version 列），actor UUID 清除
    # 后无法重算或判断历史 digest 用哪个版本。因此在 migration 落地持久化 digest
    # version 之前，生产环境 ``actor_erasure_secret_version`` 冻结为 1，**禁止轮换**
    # secret/version（轮换会使旧 digest 成为无法溯源的孤儿）。version 仍混入 HMAC
    # key 派生，为未来持久化落地后的轮换预留。
    #
    # round-5 P1-2 强制机制（非文案约定）：(1) 启动期 ``validate_production_actor_
    # erasure_key_fingerprint`` 比对 ``system_key_fingerprints`` 持久化 fingerprint
    # （migration 037），首次锁定 / 不一致 fail closed，检测 secret 静默替换；
    # (2) 构造器生产环境禁覆盖 audit_secret/audit_secret_version（必须来自 settings）。
    actor_erasure_secret: str = ""
    actor_erasure_secret_version: int = 1

    llm_default_provider: str = "minimax"
    minimax_api_key: str = ""
    minimax_base_url: str = "https://api.minimaxi.com/v1"
    minimax_model: str = "MiniMax-M2"
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"
    qwen_api_key: str = ""
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    qwen_model: str = "qwen-max"

    embedding_model: str = "BAAI/bge-m3"

    siliconflow_base_url: str = "https://api.siliconflow.cn/v1"
    siliconflow_embedding_model: str = "Qwen/Qwen3-Embedding-8B"
    minimax_embedding_model: str = "emboir"

    ner_backend: str = "rule"
    recall_mode: str = "pg_parallel"
    fusion_backend: str = "frequency"
    recall_top_k: int = 5
    fusion_top_k: int = 10

    mcp_server_host: str = "0.0.0.0"
    mcp_server_port: int = 8001
    internal_mcp_tenant_id: str = ""
    internal_mcp_token: str = ""
    # REQ-046 PR-5: V0 single-tenant catalog for internal_query semantic-model
    # resolution (the internal park datasets live in this one catalog).
    dd_internal_query_catalog_id: str = ""

    siliconflow_api_key: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()

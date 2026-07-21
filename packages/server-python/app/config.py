import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "MetaEduBase"
    app_version: str = "0.1.0"
    debug: bool = True
    allow_default_seed: bool = False

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

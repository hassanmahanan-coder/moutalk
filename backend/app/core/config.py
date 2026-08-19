from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置，从环境变量 / .env 读取。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "moutalk"
    app_env: str = "dev"
    debug: bool = True
    secret_key: str = "dev-secret-key"
    jwt_expire_minutes: int = 30
    jwt_refresh_days: int = 7

    postgres_host: str = "localhost"
    postgres_port: int = 5433
    postgres_user: str = "moutalk"
    postgres_password: str = "moutalk_dev_pw"
    postgres_db: str = "moutalk"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    redis_url: str = "redis://localhost:6379/0"

    milvus_uri: str = "milvus.db"  # Milvus Lite 本地文件（目录）；生产可换 http 地址
    embedding_backend: str = "local_cpu"
    embedding_model_path: str = ""  # BGE 模型本地目录（含 config.json）；空则 hash 降级
    reranker_backend: str = "local_cpu"
    reranker_model_path: str = ""  # BGE-Reranker 本地目录（含 config.json）；空则 Noop 降级

    llm_base_url: str = "https://opencode.ai/zen/go/v1"
    llm_api_key: str = ""
    llm_model: str = "deepseek-v4-flash"
    llm_light_model: str = "deepseek-v4-flash"
    llm_stream: bool = True

    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"
    pdf_output_dir: str = "media/reports"  # PDF 导出目录（Celery worker 写）

    smtp_host: str = ""
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""

    alipay_app_id: str = ""
    alipay_private_key: str = ""
    alipay_public_key: str = ""
    alipay_notify_url: str = ""
    alipay_gateway: str = "https://openapi.alipay.com/gateway.do"  # 生产网关；沙箱 openapi.alipaydev.com


@lru_cache
def get_settings() -> Settings:
    return Settings()

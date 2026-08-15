import os


class LlmGatewayConfig:
    """LLM 网关配置"""

    # 数据库
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///data/llm_gateway.db")

    # 代理
    DEFAULT_TIMEOUT_SECONDS: float = float(os.getenv("DEFAULT_TIMEOUT_SECONDS", "30.0"))
    MAX_RETRIES: int = int(os.getenv("MAX_RETRIES", "3"))
    REQUEST_BODY_LIMIT_BYTES: int = int(
        os.getenv("REQUEST_BODY_LIMIT_BYTES", str(10 * 1024 * 1024)))  # 10MB

    # 健康检查
    HEALTH_CHECK_INTERVAL_SECONDS: int = int(
        os.getenv("HEALTH_CHECK_INTERVAL_SECONDS", "60"))
    HEALTH_CHECK_TIMEOUT_SECONDS: float = float(
        os.getenv("HEALTH_CHECK_TIMEOUT_SECONDS", "5.0"))

    # 审计
    AUDIT_LOG_RETENTION_DAYS: int = int(os.getenv("AUDIT_LOG_RETENTION_DAYS", "90"))

    # 加密
    ENCRYPTION_KEY: str = os.getenv("ENCRYPTION_KEY", "")

    # 服务
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))

from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AGENTLENS_", env_file=ROOT / ".env", extra="ignore"
    )

    database_url: SecretStr = SecretStr(
        "postgresql+psycopg://agentlens:agentlens-local@127.0.0.1:5432/agentlens"
    )
    model_base_url: str = "http://127.0.0.1:4000/v1"
    model: str = "agentlens-agent"
    judge_model: str = "agentlens-agent"
    configured_upstream_model: str = Field(
        default="openai/deepseek-flash", validation_alias="DEEPSEEK_MODEL"
    )
    model_api_key: SecretStr = SecretStr("sk-agentlens-local-dev")
    request_timeout: float = 60
    max_model_calls: int = 6
    max_output_tokens: int = 1200
    mcp_url: str = "http://127.0.0.1:8010/mcp"
    embedding_path: Path = ROOT / ".tools/models/bge-small-zh-v1.5"
    otlp_endpoint: str = "http://127.0.0.1:4318/v1/traces"
    otlp_ingest_key: SecretStr = SecretStr("agentlens-collector-local-dev")
    identity_path: Path = ROOT / ".tools/identities.json"
    openshell_binary: str = "openshell"
    sandbox_image: str = "agentlens-analysis:week8"

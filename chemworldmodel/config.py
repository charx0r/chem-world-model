from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://cwm:changeme@localhost:5432/chemworldmodel"
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_echo: bool = False
    llm_provider: str = "gemini"
    llm_api_key: str = ""
    llm_model: str = "gemini-2.5-flash"
    query_timeout: int = 30
    query_max_sql_chars: int = 2000
    ollama_base_url: str = "http://localhost:11434/v1"


def get_settings() -> Settings:
    return Settings()

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://postgres:password@localhost:5432/japanese_learning"

    # Anthropic
    anthropic_api_key: str = ""

    # Claude models
    claude_fast_model: str  = "claude-haiku-4-5-20251001"   # tool calls, grading
    claude_smart_model: str = "claude-sonnet-4-6"            # explanations, summaries

    # Supabase
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = ""

    # App
    debug: bool = False


settings = Settings()

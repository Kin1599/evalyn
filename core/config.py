from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    bot_token: str
    openrouter_api_key: str = ""
    default_agent_model: str = "openrouter/free"
    assignment_review_interval_seconds: int = 300
    sandbox_url: str = "http://sandbox:8001"
    database_url: str
    admin_ids: list[int] = []
    webapp_url: str = ""

    @field_validator("admin_ids", mode="before")
    @classmethod
    def parse_admin_ids(cls, v):
        if isinstance(v, str):
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        if isinstance(v, int):
            return [v]
        return v

    @property
    def is_admin(self):
        def check(telegram_id: int) -> bool:
            return telegram_id in self.admin_ids
        return check


settings = Settings()

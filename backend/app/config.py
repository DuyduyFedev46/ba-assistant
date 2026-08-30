from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./dev.db"
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_anon_key: str = ""

    anthropic_api_key: str = ""
    openai_api_key: str = ""
    gemini_api_key: str = ""

    google_application_credentials: str = ""
    github_token: str = ""

    model_policy_path: str = "config/model_policy.yaml"
    connectors_path: str = "config/connectors.yaml"
    profiles_dir: str = "profiles"

    llm_fake: bool = False
    llm_real: str = "anthropic"

    # Test/dev: tắt xác thực JWT
    auth_disabled: bool = False

    # Prod: verify Firebase ID token (aud = project id Firebase)
    firebase_project_id: str = ""

    # CORS cho FE dev (Next.js localhost:3000). Danh sách cách nhau dấu phẩy; "*" = mở hết.
    cors_origins: str = "*"

    def resolve(self, rel: str) -> Path:
        p = Path(rel)
        return p if p.is_absolute() else BASE_DIR / p

    @property
    def model_policy_file(self) -> Path:
        return self.resolve(self.model_policy_path)

    @property
    def connectors_file(self) -> Path:
        return self.resolve(self.connectors_path)

    @property
    def profiles_dir_path(self) -> Path:
        return self.resolve(self.profiles_dir)


@lru_cache
def get_settings() -> Settings:
    return Settings()

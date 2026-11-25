import os
import sys
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_provider: str = "ollama"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-4-5-20251001"
    google_api_key: str = ""
    google_model: str = "gemini-2.0-flash"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"
    openrouter_api_key: str = ""
    openrouter_model: str = "meta-llama/llama-3.1-70b-instruct"
    upload_dir: str = str(BASE_DIR / "uploads")
    generated_dir: str = str(BASE_DIR / "generated")
    log_dir: str = str(BASE_DIR / "logs")
    log_level: str = "INFO"
    template_dir: str = str(BASE_DIR / "backend" / "app" / "templates")
    cors_origins: str = "*"
    allowed_extensions: str = "pdf,png,jpg,jpeg"

settings = Settings()
for d in [settings.upload_dir, settings.generated_dir, settings.log_dir]:
    os.makedirs(d, exist_ok=True)

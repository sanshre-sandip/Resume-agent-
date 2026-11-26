import os
import sys
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", env_file=".env", env_file_encoding="utf-8")

    app_name: str = "Nhyapu Craft"
    app_env: str = "development"
    public_base_url: str = "http://127.0.0.1:8001"
    session_secret: str = "local-development-only-change-this-secret"
    session_cookie_name: str = "nhyapu_session"
    session_max_age_seconds: int = 604800
    require_email_verification: bool = False
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = ""
    smtp_host: str = "smtp-relay.brevo.com"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    google_ai_api_key: str = ""
    openrouter_api_key: str = ""
    groq_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"

    data_dir: str = str(BASE_DIR.parent / "data")
    upload_dir: str = str(BASE_DIR / "uploads")
    generated_dir: str = str(BASE_DIR / "generated")
    log_dir: str = str(BASE_DIR / "logs")
    log_level: str = "INFO"
    template_dir: str = str(BASE_DIR / "backend" / "app" / "templates")
    cors_origins: str = "https://craft.nhyapu.space,http://127.0.0.1:8001,http://localhost:8001"
    allowed_extensions: str = "pdf,png,jpg,jpeg"

settings = Settings()
if settings.app_env.lower() == "production" and (
    len(settings.session_secret) < 32
    or settings.session_secret.startswith("local-development")
    or settings.session_secret.lower().startswith(("replace-", "change-me", "example-"))
):
    raise RuntimeError("Set SESSION_SECRET to a random value of at least 32 characters in production.")
for d in [settings.data_dir, settings.upload_dir, settings.generated_dir, settings.log_dir]:
    os.makedirs(d, mode=0o700, exist_ok=True)
    try:
        os.chmod(d, 0o700)
    except OSError:
        pass

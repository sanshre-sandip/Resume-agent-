import os
import sys
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

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

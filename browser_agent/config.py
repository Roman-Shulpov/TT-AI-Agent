"""Explicit environment configuration, loaded once at the application boundary."""

import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel, Field, SecretStr


class Settings(BaseModel):
    llm_provider: Literal["openai"] = "openai"
    llm_model: str = "gpt-4.1-mini"
    llm_api_key: SecretStr = SecretStr("")
    llm_base_url: str | None = None
    headless: bool = False
    max_steps: int = Field(default=30, ge=1, le=200)
    action_timeout_ms: int = Field(default=8000, ge=100, le=60000)
    navigation_timeout_ms: int = Field(default=20000, ge=100, le=90000)
    llm_timeout_seconds: float = Field(default=45, ge=1, le=180)
    profile_dir: Path = Path(".browser-profile")
    max_text_chars: int = Field(default=9000, ge=500, le=20000)
    max_elements: int = Field(default=70, ge=5, le=120)
    recent_history: int = Field(default=6, ge=2, le=12)
    safety_mode: Literal["conservative", "balanced"] = "conservative"

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        values = {
            name: os.environ[name.upper()]
            for name in cls.model_fields
            if os.environ.get(name.upper(), "").strip()
        }
        if "llm_api_key" not in values and os.environ.get("OPENAI_API_KEY"):
            values["llm_api_key"] = os.environ["OPENAI_API_KEY"]
        return cls.model_validate(values)

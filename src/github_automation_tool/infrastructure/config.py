import logging

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    github_pat: SecretStr = Field(..., validation_alias='GITHUB_PAT')
    ai_model: str = Field('openai', validation_alias='AI_MODEL') # 'openai' or 'gemini'
    # Allow API keys to be None if the corresponding model is not used
    openai_api_key: SecretStr | None = Field(None, validation_alias='OPENAI_API_KEY')
    gemini_api_key: SecretStr | None = Field(None, validation_alias='GEMINI_API_KEY')
    # Allow model names to be None, fallback logic will be applied in usage
    openai_model_name: str | None = Field(None, validation_alias='OPENAI_MODEL_NAME')
    gemini_model_name: str | None = Field(None, validation_alias='GEMINI_MODEL_NAME')
    # ログレベル設定（環境変数LOG_LEVELから取得、デフォルトは'info'）
    log_level: str = Field('info', validation_alias='LOG_LEVEL')

def load_settings() -> Settings:
    """Loads the application settings."""
    try:
        settings = Settings()
        # Log loaded settings, masking secrets
        logger.info("Settings loaded successfully.")
        logger.debug(f"AI Model: {settings.ai_model}")
        logger.debug(f"OpenAI Model Name: {settings.openai_model_name}")
        logger.debug(f"Gemini Model Name: {settings.gemini_model_name}")
        logger.debug(f"GitHub PAT: {'Set' if settings.github_pat else 'Not Set'}")
        logger.debug(f"OpenAI API Key: {'Set' if settings.openai_api_key else 'Not Set'}")
        logger.debug(f"Gemini API Key: {'Set' if settings.gemini_api_key else 'Not Set'}")
        logger.debug(f"Log Level: {settings.log_level}")
        return settings
    except Exception as e:
        logger.error(f"Error loading settings: {e}", exc_info=True)
        raise

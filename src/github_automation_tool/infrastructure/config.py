from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, SecretStr, ValidationError
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """
    アプリケーション設定。環境変数および .env ファイルから読み込まれます。
    環境変数が .env ファイルの設定を上書きします。
    """
    model_config = SettingsConfigDict(
        env_file='.env',         # プロジェクトルートの .env ファイルを読み込む
        env_file_encoding='utf-8',
        extra='ignore'           # Settingsクラスに定義されていない環境変数は無視
    )

    # --- GitHub Settings ---
    # 必須: 環境変数 'GITHUB_PAT' または .env の 'GITHUB_PAT' が必要
    github_pat: SecretStr = Field(..., validation_alias='GITHUB_PAT')

    # --- AI Settings ---
    # 必須: 環境変数 'OPENAI_API_KEY' または .env の 'OPENAI_API_KEY' が必要
    openai_api_key: SecretStr = Field(..., validation_alias='OPENAI_API_KEY')

    # オプション: 環境変数 'GEMINI_API_KEY' または .env の 'GEMINI_API_KEY' があれば読み込む
    gemini_api_key: Optional[SecretStr] = Field(
        default=None, validation_alias='GEMINI_API_KEY')

    # 利用するAIモデル (デフォルトは 'openai')
    ai_model: str = Field(default="openai", validation_alias='AI_MODEL')

    # --- Logging Settings ---
    log_level: str = Field(default="INFO", validation_alias='LOG_LEVEL')

    # --- 他に必要な設定があればここに追加 ---
    # 例: プロンプトテンプレートファイルのパスなど
    # prompt_template_path: Path = Field(default="prompts/default.json", validation_alias="PROMPT_PATH")

# --- 設定インスタンスの生成とエクスポート ---
# アプリケーション起動時に一度だけ生成するのが一般的
# エラーハンドリングを含めて生成する関数を用意しても良い


def load_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as e:
        logger.error("ERROR: Configuration validation failed!")
        # エラーの詳細をログに出力するか、整形して表示する
        for error in e.errors():
            logger.error(
                f"  Variable: {error.get('loc', ['Unknown'])[0]}, Error: {error.get('msg', 'Unknown error')}")
        # アプリケーションを続行できないため、例外を再送出するか、終了する
        raise ValueError(
            "Configuration error(s) detected. Please check environment variables or .env file.") from e

# グローバルインスタンスとして保持する場合 (DIが推奨されるが、シンプルなアプリならこれでも)
# settings = load_settings()

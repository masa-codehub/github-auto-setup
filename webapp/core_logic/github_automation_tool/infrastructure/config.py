import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from pydantic import Field, SecretStr, BaseModel, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict, PydanticBaseSettingsSource

logger = logging.getLogger(__name__)

# --- 新しいネストされたモデル ---
class AiSettings(BaseModel):
    """AI関連の設定"""
    # ai_model は環境変数優先のためここでは定義しない
    openai_model_name: str = Field("gpt-4o", description="Default OpenAI model name if not set by env var")
    gemini_model_name: str = Field("gemini-1.5-flash", description="Default Gemini model name if not set by env var")
    prompt_template: str = Field(
        default="Default prompt template {markdown_text}",
        description="Prompt template for AI parser"
    )  # デフォルト値を提供

class LoggingSettings(BaseModel):
    """ロギング設定"""
    log_level: str = Field("INFO", description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)")

class ConfigValidationError(ValidationError):
    """設定バリデーションエラー"""
    pass

# --- メインの Settings モデル ---
class Settings(BaseSettings):
    """
    アプリケーション設定。YAMLファイルと環境変数から読み込む。
    環境変数がYAMLファイルの設定を上書きする。
    """
    # Pydantic-settings の設定
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    # --- 環境変数から読み込む項目 (YAMLより優先) ---
    github_pat: SecretStr = Field(..., validation_alias='GITHUB_PAT')
    ai_model: str = Field('openai', validation_alias='AI_MODEL') # デフォルトは openai
    openai_api_key: Optional[SecretStr] = Field(None, validation_alias='OPENAI_API_KEY')
    gemini_api_key: Optional[SecretStr] = Field(None, validation_alias='GEMINI_API_KEY')
    # モデル名は環境変数でも上書き可能にする
    env_openai_model_name: Optional[str] = Field(None, validation_alias='OPENAI_MODEL_NAME')
    env_gemini_model_name: Optional[str] = Field(None, validation_alias='GEMINI_MODEL_NAME')
    # ログレベルも環境変数で上書き可能にする
    env_log_level: Optional[str] = Field(None, validation_alias='LOG_LEVEL')

    # --- YAMLファイルから読み込む項目 (ネストモデル) ---
    # デフォルト値を提供して、必須エラーを回避
    ai: AiSettings = Field(default_factory=AiSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)

    # --- 最終的な設定値を取得するプロパティ ---
    # 環境変数で上書きされた後の実際のモデル名とログレベル
    @property
    def final_openai_model_name(self) -> str:
        return self.env_openai_model_name or self.ai.openai_model_name

    @property
    def final_gemini_model_name(self) -> str:
        return self.env_gemini_model_name or self.ai.gemini_model_name

    @property
    def final_log_level(self) -> str:
        # 環境変数の値を大文字に変換して検証
        env_level = self.env_log_level.upper() if self.env_log_level else None
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        
        if env_level in valid_levels:
            return env_level
            
        # 環境変数が無効な場合は警告ログ
        if env_level is not None and env_level not in valid_levels:
            logger.warning(f"Invalid log level '{self.env_log_level}' in environment variable. Using YAML/default.")
        
        # YAMLの値も大文字に変換して検証
        yaml_level = self.logging.log_level.upper()
        if yaml_level in valid_levels:
            return yaml_level
            
        # どちらも無効な場合は警告ログを出力してデフォルトを返す
        logger.warning(f"Invalid log level '{self.logging.log_level}' in config. Defaulting to INFO.")
        return "INFO" # 不正な値の場合は INFO にフォールバック

    @property
    def prompt_template(self) -> str:
        return self.ai.prompt_template


# --- カスタム設定ソース (YAML) ---
class YamlConfigSettingsSource(PydanticBaseSettingsSource):
    """
    YAMLファイルから設定を読み込むカスタムソースクラス。
    """
    config_file_path: Path

    def __init__(self, settings_cls: type[BaseSettings], config_file_path: Path):
        super().__init__(settings_cls)
        self.config_file_path = config_file_path

    def get_field_value(self, field: Field, field_name: str) -> tuple[Any, str] | tuple[None, None]:
        # このメソッドは主に環境変数などの個別フィールド取得用なので、ここでは使わない
        return None, None

    def __call__(self) -> Dict[str, Any]:
        """YAMLファイルを読み込んで辞書として返す。エラー時は警告ログを出力して空の辞書を返す。"""
        encoding = 'utf-8'  # デフォルトのエンコーディングを使用
        yaml_data = {}
        
        if not self.config_file_path.exists():
            logger.warning(f"YAML configuration file not found: {self.config_file_path}. Using defaults and environment variables.")
            return {}  # 空の辞書を返す（エラーは投げない）

        try:
            with open(self.config_file_path, 'r', encoding=encoding) as f:
                yaml_data = yaml.safe_load(f) or {} # 空ファイル対策
            logger.info(f"Successfully loaded settings from YAML: {self.config_file_path}")
        except yaml.YAMLError as e:
            logger.error(f"Error parsing YAML file '{self.config_file_path}': {e}", exc_info=True)
            return {}  # パースエラー時も空の辞書を返す
        except IOError as e:
            logger.error(f"Error reading YAML file '{self.config_file_path}': {e}", exc_info=True)
            return {}  # 読み込みエラー時も空の辞書を返す
        except Exception as e:
            logger.error(f"Unexpected error loading YAML file '{self.config_file_path}': {e}", exc_info=True)
            return {}  # その他のエラー時も空の辞書を返す

        # プロンプトテンプレートが存在しない場合は警告ログを出力
        if 'ai' in yaml_data and not yaml_data['ai'].get('prompt_template'):
            logger.warning("prompt_template is missing in ai section of YAML config. Using defaults.")
        
        return yaml_data


# --- 設定読み込み関数 ---
def load_settings(config_file: Path = Path("config.yaml")) -> Settings:
    """
    アプリケーション設定をYAMLファイルと環境変数から読み込みます。
    環境変数がYAMLファイルの設定を上書きします。

    Args:
        config_file: 読み込む設定ファイル (YAML) のパス。

    Returns:
        読み込まれた Settings オブジェクト。

    Raises:
        ValidationError: 必須項目が不足している場合など。
        FileNotFoundError: YAMLファイルが見つからない場合（警告は出るが処理は続行）。
        IOError/YAMLError: YAMLファイルの読み込みやパースに失敗した場合（警告は出るが処理は続行）。
        Exception: その他の予期せぬエラー。
    """
    logger.info(f"Loading settings...")
    logger.info(f"Attempting to load configuration from: {config_file.resolve()}")
    logger.info(f"Environment variables will override settings from {config_file.name}.")

    try:
        # YAMLから基本設定を読み込む
        yaml_source = YamlConfigSettingsSource(Settings, config_file)
        yaml_config_data = yaml_source() # YAMLデータを辞書で取得

        # 環境変数などを考慮して Pydantic モデルを初期化
        # 環境変数由来のフィールド(env_*)とYAML由来のフィールド(ai, logging)をマージ
        # 環境変数は pydantic-settings が自動で読み込む
        # YAMLデータは `ai=` や `logging=` で渡す
        init_data = {}
        
        # YAML から AI 設定を読み込む
        if 'ai' in yaml_config_data:
            init_data['ai'] = yaml_config_data['ai']
        
        # YAML からロギング設定を読み込む
        if 'logging' in yaml_config_data:
            init_data['logging'] = yaml_config_data['logging']

        # Settings を初期化 (環境変数は自動読み込み、YAMLデータはここで渡す)
        # validation_alias を使っているので、環境変数名は Pydantic が処理
        settings = Settings(**init_data)

        # --- GitHub PATの空文字チェック ---
        pat_value = settings.github_pat.get_secret_value()
        if not pat_value or not pat_value.strip():
            logger.error("GITHUB_PAT is loaded but its value is empty.")
            raise ValueError("GITHUB_PAT cannot be empty.")

        # --- Log loaded settings (masking secrets) ---
        logger.info("Settings loaded successfully.")
        logger.debug(f"AI Model Env : {settings.ai_model}")
        logger.debug(f"Config File  : {config_file.resolve() if config_file.exists() else 'Not Found'}")
        # Use final properties for logging effective values
        logger.debug(f"OpenAI Model : {settings.final_openai_model_name} (Source: {'Env' if settings.env_openai_model_name else 'YAML/Default'})")
        logger.debug(f"Gemini Model : {settings.final_gemini_model_name} (Source: {'Env' if settings.env_gemini_model_name else 'YAML/Default'})")
        logger.debug(f"Log Level    : {settings.final_log_level} (Source: {'Env' if settings.env_log_level else 'YAML/Default'})")
        logger.debug(f"GitHub PAT   : {'Set' if settings.github_pat else 'Not Set'}")
        logger.debug(f"OpenAI Key   : {'Set' if settings.openai_api_key else 'Not Set'}")
        logger.debug(f"Gemini Key   : {'Set' if settings.gemini_api_key else 'Not Set'}")
        # Prompt template is large, maybe log its presence/absence or length
        logger.debug(f"Prompt Templ.: {'Loaded from YAML' if settings.prompt_template else 'Not Loaded'}")

        return settings

    except ValidationError as e:
        logger.error(f"Settings validation error: {e}", exc_info=True)
        raise # バリデーションエラーは呼び出し元に通知
    except Exception as e:
        # YAML読み込みエラーは内部でWarning/Errorログを出しているので、ここでは予期せぬエラーのみ捕捉
        logger.error(f"Unexpected error loading settings: {e}", exc_info=True)
        raise

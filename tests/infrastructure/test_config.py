import pytest
from pydantic import ValidationError  # pydantic 本体から ValidationError をインポート
from unittest import mock
import os
from pathlib import Path

# テスト対象のモジュールをインポート
from github_automation_tool.infrastructure.config import Settings

# --- Test Cases ---


def test_settings_load_from_env_success():
    """必須の環境変数が設定されていれば正常に読み込めるか"""
    mock_env = {
        "GITHUB_PAT": "ghp_test_token_env",
        "OPENAI_API_KEY": "sk-test-key-env",
        "GEMINI_API_KEY": "gemini-key-env",  # オプションも設定
        "AI_MODEL": "gemini",
        "LOG_LEVEL": "DEBUG",
    }
    # os.environ を一時的に mock_env で置き換える (clear=Trueで既存の影響を消す)
    with mock.patch.dict(os.environ, mock_env, clear=True):
        settings = Settings()
        assert settings.github_pat.get_secret_value() == "ghp_test_token_env"
        assert settings.openai_api_key.get_secret_value() == "sk-test-key-env"
        assert settings.gemini_api_key.get_secret_value() == "gemini-key-env"
        assert settings.ai_model == "gemini"
        assert settings.log_level == "DEBUG"


def test_settings_load_from_dotenv_success(tmp_path: Path):
    """.env ファイルから正常に読み込めるか (環境変数なし)"""
    env_content = """
    GITHUB_PAT=ghp_dotenv_token
    OPENAI_API_KEY=sk-dotenv-key
    # GEMINI_API_KEY は未設定 -> None になるはず
    AI_MODEL=openai # デフォルトと同じだが明示的に設定
    """
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(env_content, encoding='utf-8')

    # 環境変数は空の状態をシミュレート
    with mock.patch.dict(os.environ, {}, clear=True):
        # Settingsクラスの model_config で .env ファイルのパスを指定
        class TestSettingsDotenv(Settings):
            model_config = Settings.model_config.copy()
            model_config['env_file'] = str(dotenv_path)

        settings = TestSettingsDotenv()
        assert settings.github_pat.get_secret_value() == "ghp_dotenv_token"
        assert settings.openai_api_key.get_secret_value() == "sk-dotenv-key"
        assert settings.gemini_api_key is None  # 未設定なので None
        assert settings.ai_model == "openai"
        assert settings.log_level == "INFO"  # デフォルト値


def test_settings_missing_required_env_error():
    """必須の環境変数 (GITHUB_PAT) が欠けている場合に ValidationError が発生するか"""
    mock_env = {"OPENAI_API_KEY": "sk-test-key"}  # GITHUB_PAT がない
    with mock.patch.dict(os.environ, mock_env, clear=True):
        with pytest.raises(ValidationError) as excinfo:
            Settings()
        assert "GITHUB_PAT" in str(excinfo.value)  # エイリアス名でチェック


def test_settings_missing_required_dotenv_error(tmp_path: Path):
    """.env ファイルに必須項目 (OPENAI_API_KEY) が欠けている場合に ValidationError"""
    env_content = "GITHUB_PAT=ghp_token"  # OPENAI_API_KEY がない
    dotenv_path = tmp_path / ".env.missing"
    dotenv_path.write_text(env_content, encoding='utf-8')

    with mock.patch.dict(os.environ, {}, clear=True):
        class TestSettingsDotenvMissing(Settings):
            model_config = Settings.model_config.copy()
            model_config['env_file'] = str(dotenv_path)

        with pytest.raises(ValidationError) as excinfo:
            TestSettingsDotenvMissing()
        assert "OPENAI_API_KEY" in str(excinfo.value)


def test_settings_env_overrides_dotenv(tmp_path: Path):
    """環境変数と .env 両方にある場合、環境変数が優先されるか"""
    env_content = "GITHUB_PAT=ghp_dotenv_token\nOPENAI_API_KEY=sk_dotenv_key"
    dotenv_path = tmp_path / ".env.override"
    dotenv_path.write_text(env_content, encoding='utf-8')

    mock_env = {
        "GITHUB_PAT": "ghp_env_token_override",  # 環境変数で上書き
        "OPENAI_API_KEY": "sk_env_key_override"
    }
    # clear=False で既存の環境変数を考慮しても良いが、テストの独立性のため clear=True が推奨
    with mock.patch.dict(os.environ, mock_env, clear=True):
        class TestSettingsOverride(Settings):
            model_config = Settings.model_config.copy()
            model_config['env_file'] = str(dotenv_path)  # .env も読む設定

        settings = TestSettingsOverride()
        # 環境変数の値が優先されるはず
        assert settings.github_pat.get_secret_value() == "ghp_env_token_override"
        assert settings.openai_api_key.get_secret_value() == "sk_env_key_override"

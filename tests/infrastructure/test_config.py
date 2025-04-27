import pytest
from pydantic import ValidationError, SecretStr  # SecretStr をインポート
from unittest import mock
import os
import logging
from pathlib import Path
import yaml # テストでの YAML 書き込み用

# テスト対象のモジュールをインポート
from github_automation_tool.infrastructure.config import Settings, load_settings, AiSettings, LoggingSettings

# --- Test Helpers ---
def create_yaml_file(tmp_path: Path, filename: str, content: dict):
    """一時ディレクトリにYAMLファイルを作成するヘルパー"""
    file_path = tmp_path / filename
    with file_path.open("w", encoding="utf-8") as f:
        yaml.dump(content, f, allow_unicode=True, default_flow_style=False)
    return file_path

# --- Test Cases ---

# -- YAML Loading Tests --
def test_load_from_yaml_success(tmp_path: Path):
    """YAMLファイルから正常に読み込めるか (環境変数なし)"""
    yaml_content = {
        "ai": {
            "openai_model_name": "gpt-4-yaml",
            "gemini_model_name": "gemini-pro-yaml",
            "prompt_template": "Template from YAML"
        },
        "logging": {
            "log_level": "DEBUG"
        }
    }
    config_path = create_yaml_file(tmp_path, "config_yaml_ok.yaml", yaml_content)

    # 必須の環境変数 GITHUB_PAT のみを設定
    mock_env = {"GITHUB_PAT": "dummy_pat"}
    with mock.patch.dict(os.environ, mock_env, clear=True):
        settings = load_settings(config_file=config_path)

    assert settings.ai_model == "openai" # 環境変数もYAMLもないのでデフォルト
    assert settings.final_openai_model_name == "gpt-4-yaml"
    assert settings.final_gemini_model_name == "gemini-pro-yaml"
    assert settings.prompt_template == "Template from YAML"
    assert settings.final_log_level == "DEBUG"
    assert settings.github_pat.get_secret_value() == "dummy_pat"
    assert settings.openai_api_key is None
    assert settings.gemini_api_key is None

def test_load_yaml_file_not_found(caplog, tmp_path: Path):
    """YAMLファイルが存在しない場合に警告ログが出て、デフォルト値が使われるか"""
    non_existent_path = Path(tmp_path / "non_existent_config.yaml")
    mock_env = {"GITHUB_PAT": "dummy_pat"} # 必須項目のみ

    with mock.patch.dict(os.environ, mock_env, clear=True), \
         caplog.at_level(logging.WARNING):
        # YAML がないと空の辞書が返されるようになったが、Settings 初期化時に
        # default_factory で AiSettings と LoggingSettings インスタンスが作られる
        # これにより ValidationError は発生しなくなった
        settings = load_settings(config_file=non_existent_path)

    assert "YAML configuration file not found" in caplog.text
    
    # デフォルト値が使われているか確認
    assert settings.ai.openai_model_name == "gpt-4o"
    assert settings.ai.gemini_model_name == "gemini-1.5-flash"
    assert settings.ai.prompt_template == "Default prompt template {markdown_text} {format_instructions}"
    assert settings.logging.log_level == "INFO"

def test_load_yaml_parse_error(tmp_path: Path, caplog):
    """不正な形式のYAMLファイルを読み込もうとした場合にエラーログが出て、デフォルト値が使われるか"""
    invalid_yaml_content = "ai: { openai_model_name: missing_quote" # 不正なYAML
    config_path = tmp_path / "invalid.yaml"
    config_path.write_text(invalid_yaml_content)

    mock_env = {"GITHUB_PAT": "dummy_pat"}
    # 修正: ValidationErrorは発生せず、デフォルト値が使われるようになった
    with mock.patch.dict(os.environ, mock_env, clear=True), \
         caplog.at_level(logging.ERROR):
        settings = load_settings(config_file=config_path)

    assert "Error parsing YAML file" in caplog.text
    # デフォルト値が使われているか確認
    assert settings.ai.prompt_template == "Default prompt template {markdown_text} {format_instructions}"
    assert settings.logging.log_level == "INFO"

def test_load_yaml_io_error(tmp_path: Path, caplog):
    """YAMLファイルの読み込み自体に失敗した場合 (パーミッションなど)"""
    config_path = tmp_path / "unreadable.yaml"
    config_path.touch()
    
    mock_env = {"GITHUB_PAT": "dummy_pat"}
    # 修正: ValidationErrorは発生せず、デフォルト値が使われるようになった
    with mock.patch.dict(os.environ, mock_env, clear=True), \
         mock.patch("builtins.open", side_effect=IOError("Cannot read file")), \
         caplog.at_level(logging.ERROR):
        settings = load_settings(config_file=config_path)

    assert "Error reading YAML file" in caplog.text
    # デフォルト値が使われているか確認
    assert settings.ai.prompt_template == "Default prompt template {markdown_text} {format_instructions}"
    assert settings.logging.log_level == "INFO"


# -- Environment Variable Override Tests --
def test_env_overrides_yaml(tmp_path: Path):
    """環境変数がYAMLファイルの設定を上書きするか"""
    yaml_content = {
        "ai": {
            "openai_model_name": "gpt-4-yaml",
            "gemini_model_name": "gemini-pro-yaml",
            "prompt_template": "Template from YAML"
        },
        "logging": {
            "log_level": "DEBUG"
        }
    }
    config_path = create_yaml_file(tmp_path, "override.yaml", yaml_content)

    mock_env = {
        "GITHUB_PAT": "pat_from_env",
        "AI_MODEL": "gemini", # YAMLにはないが環境変数で設定
        "OPENAI_MODEL_NAME": "gpt-4-env-override", # YAMLを上書き
        "GEMINI_MODEL_NAME": "gemini-1.5-pro-env-override", # YAMLを上書き
        "LOG_LEVEL": "WARNING", # YAMLを上書き
        "OPENAI_API_KEY": "sk_env", # YAMLにはない
    }
    with mock.patch.dict(os.environ, mock_env, clear=True):
        settings = load_settings(config_file=config_path)

    assert settings.github_pat.get_secret_value() == "pat_from_env"
    assert settings.ai_model == "gemini" # 環境変数が優先
    assert settings.openai_api_key.get_secret_value() == "sk_env"
    assert settings.gemini_api_key is None # 未設定

    # final_ プロパティで上書き後の値を確認
    assert settings.final_openai_model_name == "gpt-4-env-override"
    assert settings.final_gemini_model_name == "gemini-1.5-pro-env-override"
    assert settings.final_log_level == "WARNING"
    assert settings.prompt_template == "Template from YAML" # これはYAMLから

# (既存のテストは保持)
def test_settings_load_from_env_success():
    """必須の環境変数が設定されていれば正常に読み込めるか"""
    mock_env = {
        "GITHUB_PAT": "ghp_test_token_env",
        "OPENAI_API_KEY": "sk-test-key-env",
        "GEMINI_API_KEY": "gemini-key-env",
        "AI_MODEL": "gemini",
        "LOG_LEVEL": "DEBUG",
        "OPENAI_MODEL_NAME": "gpt-4-turbo", 
        "GEMINI_MODEL_NAME": "gemini-pro-vision",
    }
    with mock.patch.dict(os.environ, mock_env, clear=True):
        settings = Settings()
        assert settings.github_pat.get_secret_value() == "ghp_test_token_env"
        assert settings.openai_api_key.get_secret_value() == "sk-test-key-env"
        assert settings.gemini_api_key.get_secret_value() == "gemini-key-env"
        assert settings.ai_model == "gemini"
        assert settings.env_log_level == "DEBUG"  # env_ プロパティ名に変更
        assert settings.env_openai_model_name == "gpt-4-turbo" # env_ プロパティ名に変更
        assert settings.env_gemini_model_name == "gemini-pro-vision" # env_ プロパティ名に変更

def test_settings_load_from_dotenv_success(tmp_path: Path):
    """.env ファイルから正常に読み込めるか (環境変数なし)"""
    env_content = """
    GITHUB_PAT=ghp_dotenv_token
    OPENAI_API_KEY=sk-dotenv-key
    # GEMINI_API_KEY は未設定 -> None になるはず
    AI_MODEL=openai # デフォルトと同じだが明示的に設定
    OPENAI_MODEL_NAME=gpt-3.5-turbo # モデル名を追加
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
        assert settings.env_log_level is None  # .env にないのでデフォルト
        assert settings.env_openai_model_name == "gpt-3.5-turbo" # モデル名の検証を追加
        assert settings.env_gemini_model_name is None # .env にないので None


# test_settings_missing_required_dotenv_error を削除して、より明確なテストに置き換え
def test_settings_missing_required_field_error():
    """必須項目 (GITHUB_PAT) が欠けている場合に ValidationError が発生するか"""
    # GITHUB_PAT がない環境をシミュレート
    mock_env = {"OPENAI_API_KEY": "sk-test-key"}
    with mock.patch.dict(os.environ, mock_env, clear=True):
        with pytest.raises(ValidationError) as excinfo:
            Settings()
        # エラーメッセージに GITHUB_PAT が含まれているか確認
        assert "GITHUB_PAT" in str(excinfo.value)
        assert "Field required" in str(excinfo.value)

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

# -- Prompt Template Loading Test --
def test_prompt_template_missing_in_yaml(tmp_path: Path, caplog):
    """YAMLファイルに prompt_template がない場合は警告が出て、デフォルト値が使われる"""
    yaml_content = { # prompt_template が欠落
        "ai": {"openai_model_name": "gpt-4"},
        "logging": {"log_level": "INFO"}
    }
    config_path = create_yaml_file(tmp_path, "no_prompt.yaml", yaml_content)
    mock_env = {"GITHUB_PAT": "dummy_pat"}
    
    with mock.patch.dict(os.environ, mock_env, clear=True), \
         caplog.at_level(logging.WARNING):
        settings = load_settings(config_file=config_path)
    
    # 警告ログが出ているか確認
    assert "prompt_template is missing in ai section" in caplog.text
    
    # デフォルト値が使われているか確認
    assert settings.ai.prompt_template == "Default prompt template {markdown_text} {format_instructions}"
    assert settings.prompt_template == "Default prompt template {markdown_text} {format_instructions}"

# -- Log Level Validation Test --
@pytest.mark.parametrize("env_level, yaml_level, expected_final_level", [
    ("DEBUG", "INFO", "DEBUG"),      # Env overrides YAML
    (None, "WARNING", "WARNING"),   # YAML only
    ("INFO", None, "INFO"),          # Env only (default YAML is INFO)
    (None, None, "INFO"),           # Neither (default YAML is INFO)
    ("invalid_env", "ERROR", "ERROR"), # Invalid Env, valid YAML
    ("WARNING", "invalid_yaml", "WARNING"), # Valid Env, invalid YAML
    ("invalid_env", "invalid_yaml", "INFO"),# Both invalid -> default INFO
    ("debug", "warning", "DEBUG"),   # Lowercase env overrides lowercase YAML
])
def test_final_log_level_logic(tmp_path: Path, env_level, yaml_level, expected_final_level, caplog):
    """環境変数とYAMLのログレベル設定とフォールバックロジックをテスト"""
    yaml_content = {"ai": {"prompt_template": "dummy"}}
    if yaml_level is not None:
        yaml_content["logging"] = {"log_level": yaml_level}
    config_path = create_yaml_file(tmp_path, f"loglevel_{env_level}_{yaml_level}.yaml", yaml_content)

    mock_env = {"GITHUB_PAT": "dummy_pat"}
    if env_level is not None:
        mock_env["LOG_LEVEL"] = env_level

    with mock.patch.dict(os.environ, mock_env, clear=True), \
         caplog.at_level(logging.WARNING):  # 警告レベルでログをキャプチャ
        settings = load_settings(config_file=config_path)
        assert settings.final_log_level == expected_final_level

    # 不正な値が指定された場合に警告ログが出るか確認
    if "invalid" in str(env_level):
        assert f"Invalid log level '{env_level}'" in caplog.text
        
    if "invalid" in str(yaml_level) and env_level not in ("WARNING", "DEBUG", "INFO", "ERROR", "CRITICAL"):
        # 環境変数が有効でない場合のみYAMLバリデーションまで行く
        assert "Invalid log level" in caplog.text
        # この場合は "Defaulting to INFO" というメッセージが含まれるはず
        assert "Defaulting to INFO" in caplog.text

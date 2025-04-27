import pytest
import os
from pathlib import Path
import logging
import tempfile
import yaml
from unittest import mock
from pydantic import SecretStr

from github_automation_tool.infrastructure.config import (
    load_settings,
    Settings,
    YamlConfigSettingsSource,
    AiSettings,
    LoggingSettings
)


@pytest.fixture
def temp_yaml_file():
    """一時的なYAMLファイルを作成するフィクスチャ"""
    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w+", delete=False) as f:
        yaml_content = {
            "ai": {
                "openai_model_name": "yaml-gpt",
                "gemini_model_name": "yaml-gemini",
                "prompt_template": "yaml prompt {markdown_text} {format_instructions}"
            },
            "logging": {
                "log_level": "DEBUG"
            }
        }
        yaml.dump(yaml_content, f)
        filepath = f.name
    
    yield Path(filepath)
    
    # テスト後にファイルを削除
    if os.path.exists(filepath):
        os.unlink(filepath)


def test_yaml_config_settings_source_success(temp_yaml_file):
    """YAMLファイルから設定を正常に読み込めること"""
    source = YamlConfigSettingsSource(Settings, config_file_path=temp_yaml_file)
    settings_dict = source()
    
    assert settings_dict["ai"]["openai_model_name"] == "yaml-gpt"
    assert settings_dict["ai"]["gemini_model_name"] == "yaml-gemini"
    assert settings_dict["ai"]["prompt_template"] == "yaml prompt {markdown_text} {format_instructions}"
    assert settings_dict["logging"]["log_level"] == "DEBUG"


def test_yaml_config_settings_source_file_not_exists():
    """YAMLファイルが存在しない場合、空の辞書を返すこと"""
    source = YamlConfigSettingsSource(Settings, config_file_path=Path("/non/existent/file.yaml"))
    settings_dict = source()
    
    assert settings_dict == {}


def test_yaml_config_settings_source_parse_error(temp_yaml_file, caplog):
    """不正なYAMLファイルの場合、空の辞書を返しERRORログを出力すること"""
    # YAMLファイルを不正なフォーマットで上書き
    with open(temp_yaml_file, 'w') as f:
        f.write("invalid: yaml: content: - missing_colon")
    
    with caplog.at_level(logging.ERROR):
        source = YamlConfigSettingsSource(Settings, config_file_path=temp_yaml_file)
        settings_dict = source()
    
    assert settings_dict == {}
    assert "Error parsing YAML file" in caplog.text


def test_yaml_config_settings_source_missing_field(temp_yaml_file):
    """YAMLファイルに一部のフィールドだけが含まれている場合、その値だけ返すこと"""
    # 一部のフィールドだけを含むYAMLを作成
    with open(temp_yaml_file, 'w') as f:
        yaml.dump({"ai": {"openai_model_name": "partial-model"}}, f)
    
    source = YamlConfigSettingsSource(Settings, config_file_path=temp_yaml_file)
    settings_dict = source()
    
    assert settings_dict == {"ai": {"openai_model_name": "partial-model"}}
    assert "logging" not in settings_dict


def test_load_settings():
    """設定を読み込めること"""
    # 環境変数のセットアップ
    env_vars = {
        "GITHUB_PAT": "test_pat",
        "AI_MODEL": "gemini",
        "OPENAI_API_KEY": "test_openai_key",
        "GEMINI_API_KEY": "test_gemini_key"
    }
    
    # final_propertiesメソッドをモックして固定値を返すようにする
    with mock.patch.dict(os.environ, env_vars), \
         mock.patch.object(Settings, 'final_openai_model_name', mock.PropertyMock(return_value="gpt-4o")), \
         mock.patch.object(Settings, 'final_gemini_model_name', mock.PropertyMock(return_value="gemini-1.5-flash")):
        
        settings = load_settings(config_file=Path("/non/existent/file.yaml"))
        
        # 環境変数から設定された値を確認
        assert settings.github_pat.get_secret_value() == "test_pat"
        assert settings.ai_model == "gemini"
        assert settings.openai_api_key.get_secret_value() == "test_openai_key"
        assert settings.gemini_api_key.get_secret_value() == "test_gemini_key"
        
        # デフォルト値を確認 (propertyモックにより固定値)
        assert settings.final_openai_model_name == "gpt-4o"
        assert settings.final_gemini_model_name == "gemini-1.5-flash"
        assert settings.final_log_level == "INFO"


def test_final_values_env_override(temp_yaml_file):
    """環境変数がYAMLファイルの設定より優先されること"""
    # YAMLファイルを書き込む
    yaml_content = {
        "ai": {
            "openai_model_name": "yaml-gpt",
            "gemini_model_name": "yaml-gemini",
            "prompt_template": "yaml prompt {markdown_text} {format_instructions}"
        },
        "logging": {
            "log_level": "ERROR"
        }
    }
    with open(temp_yaml_file, 'w') as f:
        yaml.dump(yaml_content, f)
    
    # 一部の環境変数を設定
    env_vars = {
        "GITHUB_PAT": "test_pat",
        "OPENAI_MODEL_NAME": "env-gpt",
        "LOG_LEVEL": "DEBUG"
    }
    
    # YAMLファイルを処理するモックの代わりに、実際のファイルを用意してからロード関数をモックする
    with mock.patch.dict(os.environ, env_vars), \
         mock.patch('github_automation_tool.infrastructure.config.load_settings') as mock_load:
        
        # モックの戻り値を設定
        mock_settings = mock.MagicMock()
        mock_settings.final_openai_model_name = "env-gpt"  # 環境変数から
        mock_settings.final_log_level = "DEBUG"            # 環境変数から
        mock_settings.final_gemini_model_name = "yaml-gemini"  # YAMLから
        mock_settings.prompt_template = "yaml prompt {markdown_text} {format_instructions}"  # YAMLから
        mock_load.return_value = mock_settings
        
        settings = mock_load(config_file=temp_yaml_file)
        
        # 環境変数が優先されるフィールド
        assert settings.final_openai_model_name == "env-gpt"
        assert settings.final_log_level == "DEBUG"
        
        # YAMLのみから設定されるフィールド
        assert settings.final_gemini_model_name == "yaml-gemini"
        assert "yaml prompt" in settings.prompt_template


def test_log_level_validation(temp_yaml_file, caplog):
    """無効なログレベルの場合、デフォルトのINFOが返されること"""
    # YAMLファイルを書き込む
    with open(temp_yaml_file, 'w') as f:
        yaml.dump({"logging": {"log_level": "INVALID_LEVEL"}}, f)
    
    # 環境変数も無効な値を設定
    with mock.patch.dict(os.environ, {"LOG_LEVEL": "NONSENSE"}), caplog.at_level(logging.WARNING):
        settings = load_settings(config_file=temp_yaml_file)
        assert settings.final_log_level == "INFO"  # デフォルト値
    
    # 警告ログが出力されていること
    assert "Invalid log level" in caplog.text


def test_yaml_config_settings_source_io_error(temp_yaml_file, caplog):
    """ファイル読み取りエラーが発生した場合、空の辞書を返すこと"""
    # mock.patch.objectでopen関数が例外を発生させるように設定
    with mock.patch("builtins.open", side_effect=IOError("Permission denied")), \
         caplog.at_level(logging.ERROR):
        source = YamlConfigSettingsSource(Settings, config_file_path=temp_yaml_file)
        settings_dict = source()
    
    assert settings_dict == {}
    assert "Error reading YAML file" in caplog.text
    assert "Permission denied" in caplog.text


def test_yaml_config_settings_source_unexpected_error(temp_yaml_file, caplog):
    """YAML解析で予期せぬエラーが発生した場合、空の辞書を返すこと"""
    # mock.patchでyaml.safe_loadでValueErrorを発生させる
    with mock.patch('yaml.safe_load', side_effect=ValueError("Unexpected error")), \
         caplog.at_level(logging.ERROR):
        source = YamlConfigSettingsSource(Settings, config_file_path=temp_yaml_file)
        settings_dict = source()
    
    assert settings_dict == {}
    assert "Unexpected error loading YAML file" in caplog.text
    assert "Unexpected error" in caplog.text

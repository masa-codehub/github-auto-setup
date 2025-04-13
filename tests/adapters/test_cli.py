# tests/adapters/test_cli.py (UseCase統合テスト版)

from unittest import mock
from unittest.mock import patch, MagicMock # patch をインポート
import os
import logging
from typer.testing import CliRunner
from pathlib import Path
import pytest

# main.py 内の app をインポート
from github_automation_tool.main import app
from github_automation_tool import __version__
# モック対象のクラスと、発生しうる例外をインポート
from github_automation_tool.infrastructure.config import Settings
from github_automation_tool.use_cases.create_github_resources import CreateGitHubResourcesUseCase
from github_automation_tool.domain.exceptions import (
    AiParserError, GitHubClientError, GitHubValidationError, GitHubAuthenticationError
)

# stderrを分離してキャプチャするように CliRunner を初期化
runner = CliRunner(mix_stderr=False)

# --- Fixtures ---
@pytest.fixture
def dummy_md_file(tmp_path: Path) -> Path:
    d = tmp_path / "sub"
    d.mkdir()
    p = d / "test.md"
    p.write_text("# Test File\nSome content.")
    return p

@pytest.fixture
def dummy_config_file(tmp_path: Path) -> Path:
    p = tmp_path / "config.yaml"
    p.write_text("ai_model: dummy")
    return p

# --- 基本的なCLI動作テスト ---

def test_cli_help():
    """--help オプションでヘルプメッセージが正しく表示されるか"""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Usage:" in result.stdout
    assert "--file" in result.stdout
    assert "--repo" in result.stdout
    assert "--project" in result.stdout
    assert "--config" in result.stdout
    assert "--dry-run" in result.stdout
    assert "--version" in result.stdout

def test_cli_version():
    """--version オプションで正しいバージョンが表示され、正常終了するか"""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert f"GitHub Automation Tool Version: {__version__}" in result.stdout

def test_cli_missing_required_options(dummy_md_file: Path):
    """必須オプションが欠けている場合にエラー終了するか"""
    result_no_repo = runner.invoke(app, ["--file", str(dummy_md_file), "--project", "P"])
    assert result_no_repo.exit_code != 0
    assert "Missing option" in result_no_repo.stderr
    assert "'--repo'" in result_no_repo.stderr

    result_no_file = runner.invoke(app, ["--repo", "R", "--project", "P"])
    assert result_no_file.exit_code != 0
    assert "Missing option" in result_no_file.stderr
    assert "'--file'" in result_no_file.stderr

    result_no_project = runner.invoke(app, ["--file", str(dummy_md_file), "--repo", "R"])
    assert result_no_project.exit_code != 0
    assert "Missing option" in result_no_project.stderr
    assert "'--project'" in result_no_project.stderr

def test_cli_file_not_exists():
    """--file オプションで存在しないファイルを指定した場合にエラー終了するか"""
    result = runner.invoke(app, ["--file", "nonexistent.md", "--repo", "R", "--project", "P"])
    assert result.exit_code != 0
    assert "Invalid value for '--file'" in result.stderr
    assert "does not exist" in result.stderr

def test_cli_config_not_exists(dummy_md_file: Path):
    """--config オプションで存在しないファイルを指定した場合にエラー終了するか"""
    result = runner.invoke(app, ["--file", str(dummy_md_file),
                               "--repo", "R", "--project", "P", "--config", "no_config.yaml"])
    assert result.exit_code != 0
    assert "Invalid value for '--config'" in result.stderr
    assert "does not exist" in result.stderr

def test_cli_exit_on_missing_env_vars(dummy_md_file: Path, caplog):
    """必須環境変数がない場合に load_settings でエラーになり、CLIが非ゼロで終了するか"""
    mock_env = {"OPENAI_API_KEY": "sk-key"} # GITHUB_PAT がない
    with mock.patch.dict(os.environ, mock_env, clear=True):
        result = runner.invoke(app, [
            # "run", # 不要
            "--file", str(dummy_md_file),
            "--repo", "owner/repo",
            "--project", "My Project",
        ])
    assert result.exit_code == 1
    
    # # stderr に main.py が出力するメッセージを確認
    # assert "ERROR: Workflow failed: ValueError - Configuration error(s) detected." in result.stderr

    # load_settings 内のログを確認
    assert "Configuration validation failed!" in caplog.text
    assert "GITHUB_PAT" in caplog.text


# --- UseCase 連携テスト (正常系) ---

@patch('github_automation_tool.main.CliReporter')
@patch('github_automation_tool.main.CreateIssuesUseCase')
@patch('github_automation_tool.main.CreateRepositoryUseCase')
@patch('github_automation_tool.main.GitHubAppClient')
@patch('github_automation_tool.main.AIParser')
@patch('github_automation_tool.main.read_markdown_file')
@patch('github_automation_tool.main.load_settings')
# ★ CreateGitHubResourcesUseCase もパッチ
@patch('github_automation_tool.main.CreateGitHubResourcesUseCase')
def test_cli_success_calls_main_use_case(
    mock_main_use_case_class: MagicMock, # patch したクラスを受け取る
    mock_load_settings: MagicMock,
    mock_read_file: MagicMock,
    mock_ai_parser_class: MagicMock,
    mock_gh_client_class: MagicMock,
    mock_create_repo_uc_class: MagicMock,
    mock_create_issues_uc_class: MagicMock,
    mock_reporter_class: MagicMock,
    dummy_md_file: Path, caplog
):
    """正常実行時にメインUseCaseのexecuteが正しい引数で呼ばれるか"""
    repo_input = "owner/success-repo"
    project = "Success Project"

    # Arrange: モックの設定 (load_settings)
    mock_settings = MagicMock(spec=Settings, log_level="INFO")
    mock_settings.github_pat = MagicMock() # SecretStrを模倣
    mock_settings.github_pat.get_secret_value.return_value = "valid-token"
    mock_settings.openai_api_key = MagicMock()
    mock_settings.openai_api_key.get_secret_value.return_value = "valid-key"
    mock_settings.gemini_api_key = None
    mock_settings.ai_model = "openai"
    mock_load_settings.return_value = mock_settings

    # Arrange: UseCase の execute が正常終了することをシミュレート
    mock_main_uc_instance = mock_main_use_case_class.return_value
    mock_main_uc_instance.execute.return_value = None # 戻り値なし

    # Act: CLIコマンドを実行
    result = runner.invoke(app, [
        "--file", str(dummy_md_file),
        "--repo", repo_input,
        "--project", project,
        # dry_run=False (デフォルト)
    ])

    #
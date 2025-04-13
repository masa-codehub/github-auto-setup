# tests/adapters/test_cli.py (修正後の完全版)

from unittest import mock
import os
import logging  # caplog フィクスチャを使う場合に備えて
from typer.testing import CliRunner
from pathlib import Path
import pytest

# main.py 内の app をインポート
from github_automation_tool.main import app
from github_automation_tool import __version__

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
    p.write_text("ai_model: dummy_from_config")
    return p

# --- Test Functions ---


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
    """必須オプション (--file, --repo, --project) が欠けている場合にエラー終了するか"""
    result_no_repo = runner.invoke(
        app, ["--file", str(dummy_md_file), "--project", "P"])
    assert result_no_repo.exit_code != 0
    assert "Missing option" in result_no_repo.stderr
    assert "'--repo'" in result_no_repo.stderr

    result_no_file = runner.invoke(app, ["--repo", "R", "--project", "P"])
    assert result_no_file.exit_code != 0
    assert "Missing option" in result_no_file.stderr
    assert "'--file'" in result_no_file.stderr

    result_no_project = runner.invoke(
        app, ["--file", str(dummy_md_file), "--repo", "R"])
    assert result_no_project.exit_code != 0
    assert "Missing option" in result_no_project.stderr
    assert "'--project'" in result_no_project.stderr


def test_cli_file_not_exists():
    """--file オプションで存在しないファイルを指定した場合にエラー終了するか"""
    result = runner.invoke(
        app, ["--file", "nonexistent.md", "--repo", "R", "--project", "P"])
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


def test_cli_success_basic(dummy_md_file: Path, caplog):
    """必須オプションを指定し、必須環境変数があれば正常に実行されるか"""
    repo = "owner/basic-repo"
    project = "Basic Project"
    mock_env = {
        "GITHUB_PAT": "dummy_pat_basic",
        "OPENAI_API_KEY": "dummy_openai_key_basic"
    }
    with mock.patch.dict(os.environ, mock_env, clear=True):
        # ★ "run" サブコマンドは不要 (appオブジェクトを直接渡す場合)
        result = runner.invoke(app, [
            "--file", str(dummy_md_file),
            "--repo", repo,
            "--project", project,
        ])
    assert result.exit_code == 0, f"CLI exited with code {result.exit_code}, stderr: {result.stderr}"
    assert "Settings loaded successfully." in caplog.text
    assert f"Input File Path : {dummy_md_file.resolve()}" in caplog.text
    assert f"Repository Name : {repo}" in caplog.text
    assert f"Project Name    : {project}" in caplog.text  # アラインメント注意
    assert "Dry Run Mode    : False" in caplog.text  # アラインメント注意
    assert "Config File Path" not in caplog.text


# ★ caplog を引数に追加
def test_cli_success_with_options(dummy_md_file: Path, dummy_config_file: Path, caplog):
    """オプションも含めて指定し、必須環境変数があれば正常に実行されるか"""
    repo = "owner/options-repo"
    project = "Options Project"
    # ★ mock.patch.dict を追加
    mock_env = {
        "GITHUB_PAT": "dummy_pat_options",
        "OPENAI_API_KEY": "dummy_openai_key_options",
        "LOG_LEVEL": "DEBUG"
    }
    with mock.patch.dict(os.environ, mock_env, clear=True):
        # ★ "run" は不要, "--test-mode" を削除
        result = runner.invoke(app, [
            "--file", str(dummy_md_file),
            "--repo", repo,
            "--project", project,
            "--config", str(dummy_config_file),
            "--dry-run",
        ])
    assert result.exit_code == 0, f"CLI exited with code {result.exit_code}, stderr: {result.stderr}"
    # ★ アサーションを caplog ベースに変更
    assert "Settings loaded successfully." in caplog.text
    assert "Log level set to DEBUG" in caplog.text  # 大文字小文字修正
    assert f"Input File Path : {dummy_md_file.resolve()}" in caplog.text
    assert f"Repository Name : {repo}" in caplog.text
    assert f"Project Name    : {project}" in caplog.text  # アラインメント注意
    assert f"Config File Path: {dummy_config_file.resolve()}" in caplog.text
    assert "Dry Run Mode    : True" in caplog.text  # アラインメント注意


def test_cli_exit_on_missing_env_vars(dummy_md_file: Path, caplog):
    """必須環境変数がない場合に load_settings でエラーになり、CLIが非ゼロで終了するか"""
    mock_env = {"OPENAI_API_KEY": "sk-key"}
    with mock.patch.dict(os.environ, mock_env, clear=True):
        # ★ "run" は不要
        result = runner.invoke(app, [
            "--file", str(dummy_md_file),
            "--repo", "owner/repo",
            "--project", "My Project",
        ])
    assert result.exit_code == 1
    # ★ stderr のアサーションを削除
    # assert "ERROR: Configuration error(s) detected" in result.stderr
    # caplog でエラーログを確認
    assert "Configuration validation failed!" in caplog.text
    assert "GITHUB_PAT" in caplog.text

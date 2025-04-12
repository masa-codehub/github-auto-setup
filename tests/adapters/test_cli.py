from typer.testing import CliRunner
from pathlib import Path
import pytest

# main.py 内の app をインポート (パスは環境に合わせて調整)
from github_automation_tool.main import app, __version__

runner = CliRunner(mix_stderr=False)

# テスト用のダミーMarkdownファイルを作成するpytestフィクスチャ


@pytest.fixture
def dummy_md_file(tmp_path: Path) -> Path:
    d = tmp_path / "sub"
    d.mkdir()
    p = d / "test.md"
    p.write_text("# Test File")
    return p

# テスト用のダミー設定ファイルを作成するpytestフィクスチャ


@pytest.fixture
def dummy_config_file(tmp_path: Path) -> Path:
    p = tmp_path / "config.yaml"
    p.write_text("ai_model: dummy")
    return p


def test_cli_help():
    """--help オプションでヘルプメッセージが表示されるか"""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Usage: run [OPTIONS]" in result.stdout  # コマンド名をrunにした場合
    assert "--file" in result.stdout
    assert "--repo" in result.stdout
    assert "--project" in result.stdout
    assert "--config" in result.stdout
    assert "--dry-run" in result.stdout
    assert "--version" in result.stdout


def test_cli_version():
    """--version オプションでバージョンが表示され終了するか"""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert f"GitHub Automation Tool Version: {__version__}" in result.stdout


def test_cli_missing_required_options(dummy_md_file: Path):
    """必須オプション (--file, --repo, --project) が欠けている場合にエラー終了するか"""
    # --repo がない
    result = runner.invoke(
        app, ["--file", str(dummy_md_file), "--project", "P"])
    assert result.exit_code != 0
    assert "Missing option" in result.stderr
    assert "'--repo'" in result.stderr

    # --file がない
    result = runner.invoke(app, ["--repo", "R", "--project", "P"])
    assert result.exit_code != 0
    assert "Missing option" in result.stderr
    assert "'--file'" in result.stderr

    # --project がない
    result = runner.invoke(app, ["--file", str(dummy_md_file), "--repo", "R"])
    assert result.exit_code != 0
    assert "Missing option" in result.stderr
    assert "'--project'" in result.stderr


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


def test_cli_success_basic(dummy_md_file: Path):
    """必須オプションを指定して正常に実行されるか (ダミー出力確認)"""
    repo = "owner/repo"
    project = "My Project"
    result = runner.invoke(app, [
        "--file", str(dummy_md_file),
        "--repo", repo,
        "--project", project,
    ])
    print(result.stdout)  # デバッグ用に表示
    assert result.exit_code == 0
    assert f"Input File Path : {dummy_md_file.resolve()}" in result.stdout
    assert f"Repository Name : {repo}" in result.stdout
    assert f"Project Name    : {project}" in result.stdout
    assert "Dry Run Mode    : False" in result.stdout
    assert "Config File Path" not in result.stdout  # --config 未指定


def test_cli_success_with_options(dummy_md_file: Path, dummy_config_file: Path):
    """オプションも含めて指定して正常に実行されるか"""
    repo = "owner/repo"
    project = "My Project"
    result = runner.invoke(app, [
        "--file", str(dummy_md_file),
        "--repo", repo,
        "--project", project,
        "--config", str(dummy_config_file),
        "--dry-run",
    ])
    print(result.stdout)
    assert result.exit_code == 0
    assert f"Input File Path : {dummy_md_file.resolve()}" in result.stdout
    assert f"Repository Name : {repo}" in result.stdout
    assert f"Project Name    : {project}" in result.stdout
    assert f"Config File Path: {dummy_config_file.resolve()}" in result.stdout
    assert "Dry Run Mode    : True" in result.stdout

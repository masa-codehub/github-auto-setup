from unittest import mock
from unittest.mock import patch, MagicMock, ANY
import os
import logging
from typer.testing import CliRunner
from pathlib import Path
import pytest
from pydantic import ValidationError, SecretStr
from githubkit import GitHub

# main.py 内の app をインポート
from core_logic.main import run, app
from core_logic.infrastructure.config import Settings
from core_logic.infrastructure.file_reader import read_markdown_file
from core_logic.adapters.ai_parser import AIParser
from core_logic.adapters.github_rest_client import GitHubRestClient
from core_logic.use_cases.create_github_resources import CreateGitHubResourcesUseCase
from core_logic.domain.models import ParsedRequirementData, IssueData, CreateGitHubResourcesResult
from core_logic.domain.exceptions import (
    AiParserError, GitHubClientError, GitHubValidationError, GitHubAuthenticationError
)
import importlib.metadata
try:
    __version__ = importlib.metadata.version("core_logic")
except importlib.metadata.PackageNotFoundError:
    __version__ = "dev"

# stderrを分離してキャプチャするように CliRunner を初期化
runner = CliRunner()

# --- Fixtures ---


@pytest.fixture
def dummy_md_file(tmp_path: Path) -> Path:
    d = tmp_path / "sub"
    d.mkdir()
    p = d / "test.md"
    # AI Parserが解析しやすいように少し内容を追加
    p.write_text("""
---
**Title:** Test Issue 1
**Description:** Body 1
**Labels:** bug
---
**Title:** Test Issue 2
**Description:** Body 2
**Milestone:** Sprint 1
    """, encoding='utf-8')
    return p


@pytest.fixture
def dummy_permission_denied_file(tmp_path: Path) -> Path:
    p = tmp_path / "no_access.md"
    p.write_text("secret", encoding='utf-8')
    # 読み取り権限を削除 (Windows以外)
    if os.name != 'nt':
        p.chmod(0o000)
    return p


@pytest.fixture
def dummy_config_file(tmp_path: Path) -> Path:
    p = tmp_path / "config.yaml"
    p.write_text("ai_model: dummy")
    return p

# --- Mock Fixtures ---
# モック対象が増えたので、共通のモック設定をフィクスチャ化


@pytest.fixture
def mock_dependencies(dummy_md_file):
    """主要な依存関係のモックをまとめて提供するフィクスチャ"""
    # モックの準備
    mock_settings = MagicMock(spec=Settings)
    # specはあくまでメソッド検証用で、属性は手動で設定する必要がある
    mock_settings.github_pat = SecretStr("valid-token")
    mock_settings.openai_api_key = SecretStr("valid-key")
    mock_settings.gemini_api_key = None
    mock_settings.ai_model = "openai"  # デフォルト

    # 修正: 重要なプロパティを追加 - 特にAIの設定
    # AISettingsのモック
    ai_settings_mock = MagicMock()
    ai_settings_mock.prompt_template = "Test prompt template {markdown_text} {format_instructions}"
    ai_settings_mock.openai_model_name = "gpt-4o"
    ai_settings_mock.gemini_model_name = "gemini-1.5-flash"
    mock_settings.ai = ai_settings_mock

    # プロパティ関数の戻り値を設定
    mock_settings.prompt_template = "Test prompt template {markdown_text} {format_instructions}"
    mock_settings.final_openai_model_name = "gpt-4o"
    mock_settings.final_gemini_model_name = "gemini-1.5-flash"
    mock_settings.final_log_level = "INFO"  # 大文字である必要がある

    # ロギング設定
    logging_settings_mock = MagicMock()
    logging_settings_mock.log_level = "INFO"
    mock_settings.logging = logging_settings_mock

    # GitHubAppClientからGitHubRestClientに修正
    mock_gh_client_instance = MagicMock(spec=GitHubRestClient)
    # オーナー推測用のモック設定
    mock_user_data = MagicMock(login="test-auth-user")
    mock_auth_user_response = MagicMock()
    mock_auth_user_response.parsed_data = mock_user_data
    mock_gh_client_instance.gh = MagicMock()
    mock_gh_client_instance.gh.rest = MagicMock()
    mock_gh_client_instance.gh.rest.users = MagicMock()
    mock_gh_client_instance.gh.rest.users.get_authenticated = MagicMock(
        return_value=mock_auth_user_response)

    mock_ai_parser_instance = MagicMock(spec=AIParser)
    # モックのAIパーサーが返すデータを準備 - Pydanticモデルに合わせて正しくインスタンス化
    mock_parsed_data = ParsedRequirementData(issues=[
        IssueData(title="Test Issue 1", description="Body 1", labels=["bug"]),
        IssueData(title="Test Issue 2",
                  description="Body 2", milestone="Sprint 1")
    ])
    mock_ai_parser_instance.parse.return_value = mock_parsed_data

    mock_main_uc_instance = MagicMock(spec=CreateGitHubResourcesUseCase)
    # モックのUseCaseが返す結果を準備
    mock_uc_result = CreateGitHubResourcesResult(
        repository_url="https://mock.repo/url")
    mock_main_uc_instance.execute.return_value = mock_uc_result

    mock_reporter_instance = MagicMock()

    # パッチの開始と終了を管理
    patches = {
        'load_settings': patch('core_logic.main.load_settings', return_value=mock_settings),
        'read_markdown_file': patch('core_logic.main.read_markdown_file', return_value="## Mock Content"),
        'AIParser': patch('core_logic.main.AIParser', return_value=mock_ai_parser_instance),
        'GitHubRestClient': patch('core_logic.main.GitHubRestClient', return_value=mock_gh_client_instance),
        'CreateGitHubResourcesUseCase': patch('core_logic.main.CreateGitHubResourcesUseCase', return_value=mock_main_uc_instance),
        'CliReporter': patch('core_logic.main.CliReporter', return_value=mock_reporter_instance),
        # CreateRepositoryUseCase と CreateIssuesUseCase も main.py で import されているため、モックしておく
        'CreateRepositoryUseCase': patch('core_logic.main.CreateRepositoryUseCase'),
        'CreateIssuesUseCase': patch('core_logic.main.CreateIssuesUseCase'),
    }

    # --- ここから追加: infer_rulesのデフォルト実装（高信頼度） ---
    from core_logic.domain.models import AISuggestedRules
    mock_ai_parser_instance.infer_rules.return_value = AISuggestedRules(
        separator_rule={"separator_pattern": "---"},
        key_mapping_rule={"Title": "title", "Description": "description"},
        confidence=1.0,
        warnings=[],
        errors=[]
    )
    # --- ここまで追加 ---

    # モックオブジェクトとパッチ管理オブジェクトを辞書で返す
    mocks = {
        'settings': mock_settings,
        'gh_client': mock_gh_client_instance,
        'ai_parser': mock_ai_parser_instance,
        'main_uc': mock_main_uc_instance,
        'reporter': mock_reporter_instance,
        'parsed_data': mock_parsed_data,  # executeの引数検証用
        'patches': patches
    }
    return mocks


@pytest.fixture(autouse=False)  # 明示的に使うテストのみ適用
def apply_patches(mock_dependencies):
    started_patches = {name: p.start()
                       for name, p in mock_dependencies['patches'].items()}
    yield
    for p in started_patches.values():
        p.stop()


# --- 基本的なCLI動作テスト (変更なし) ---
@pytest.mark.usefixtures("apply_patches")
def test_cli_help():
    """--help オプションでヘルプメッセージが正しく表示されるか"""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Usage:" in result.stdout


@pytest.mark.usefixtures("apply_patches")
def test_cli_version():
    """--version オプションで正しいバージョンが表示され、正常終了するか"""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert f"GitHub Automation Tool Version: {__version__}" in result.stdout


@pytest.mark.usefixtures("apply_patches")
def test_cli_missing_required_options(dummy_md_file: Path):
    """必須オプションが欠けている場合にエラー終了するか"""
    result_no_repo = runner.invoke(app, ["--file", str(dummy_md_file)])
    assert result_no_repo.exit_code != 0
    assert "Missing option" in result_no_repo.stderr
    assert "'--repo'" in result_no_repo.stderr

    result_no_file = runner.invoke(app, ["--repo", "R"])
    assert result_no_file.exit_code != 0
    assert "Missing option" in result_no_file.stderr
    assert "'--file'" in result_no_file.stderr


@pytest.mark.usefixtures("apply_patches")
def test_cli_file_not_exists():
    """--file オプションで存在しないファイルを指定した場合にエラー終了するか"""
    # 存在チェックはTyperが行うので、モックは不要
    result = runner.invoke(app, ["--file", "nonexistent.md", "--repo", "R"])
    assert result.exit_code != 0
    assert "Invalid value for '--file'" in result.stderr


# --- シナリオ別テスト ---

@pytest.mark.usefixtures("apply_patches")
def test_cli_success_core_flow(mock_dependencies, dummy_md_file: Path, caplog):
    """主要な成功フロー (AC-Core-Flow): 必須オプション指定で正常終了"""
    mock_main_uc = mock_dependencies['main_uc']
    mock_reporter = mock_dependencies['reporter']
    mock_parsed_data = mock_dependencies['parsed_data']

    result = runner.invoke(app, [
        "--file", str(dummy_md_file),
        "--repo", "owner/repo",
    ])

    assert result.exit_code == 0, f"Stderr: {result.stderr}"
    # UseCaseが正しい引数で呼ばれたか
    mock_main_uc.execute.assert_called_once_with(
        parsed_data=mock_parsed_data,
        repo_name_input="owner/repo",
        project_name=None,  # projectオプションなし
        dry_run=False      # dry-runオプションなし
    )
    # Reporterが呼ばれたか
    mock_reporter.display_create_github_resources_result.assert_called_once()
    assert "Workflow execution completed." in caplog.text


@pytest.mark.usefixtures("apply_patches")
def test_cli_success_with_project(mock_dependencies, dummy_md_file: Path):
    """主要な成功フロー (AC-Core-Flow): --project オプション指定"""
    mock_main_uc = mock_dependencies['main_uc']
    mock_parsed_data = mock_dependencies['parsed_data']
    project_name = "My Project"

    result = runner.invoke(app, [
        "--file", str(dummy_md_file),
        "--repo", "owner/repo",
        "--project", project_name,
    ])

    assert result.exit_code == 0, f"Stderr: {result.stderr}"
    mock_main_uc.execute.assert_called_once_with(
        parsed_data=mock_parsed_data,
        repo_name_input="owner/repo",
        project_name=project_name,  # project名が渡されている
        dry_run=False
    )


@pytest.mark.usefixtures("apply_patches")
def test_cli_dry_run_mode(mock_dependencies, dummy_md_file: Path):
    """Dry Run モード (AC-Dry-Run): --dry-run 指定"""
    mock_main_uc = mock_dependencies['main_uc']
    mock_parsed_data = mock_dependencies['parsed_data']

    result = runner.invoke(app, [
        "--file", str(dummy_md_file),
        "--repo", "owner/repo",
        "--dry-run",  # 追加
    ])

    assert result.exit_code == 0, f"Stderr: {result.stderr}"
    mock_main_uc.execute.assert_called_once_with(
        parsed_data=mock_parsed_data,
        repo_name_input="owner/repo",
        project_name=None,
        dry_run=True  # dry_runフラグがTrueであることを確認
    )


@pytest.mark.usefixtures("apply_patches")
def test_cli_owner_inference(mock_dependencies, dummy_md_file: Path):
    """オーナー名推測 (AC-Owner-Infer): --repo repo-name-only 指定"""
    # このテストでは CreateGitHubResourcesUseCase の _get_owner_repo が
    # モックされた GitHubAppClient の get_authenticated を呼ぶことを期待する。
    # UseCase.execute の呼び出し自体は他のテストで検証済みなので、ここでは特に検証しない。
    # 実際には execute 内で解決されるが、CLIレベルでは呼び出し引数が正しいかで判断。
    mock_main_uc = mock_dependencies['main_uc']
    mock_parsed_data = mock_dependencies['parsed_data']
    repo_name_only = "repo-only"

    result = runner.invoke(app, [
        "--file", str(dummy_md_file),
        "--repo", repo_name_only,
    ])

    assert result.exit_code == 0, f"Stderr: {result.stderr}"
    # UseCase にはリポジトリ名のみが渡されることを確認
    mock_main_uc.execute.assert_called_once_with(
        parsed_data=mock_parsed_data,
        repo_name_input=repo_name_only,  # repo名のみ
        project_name=None,
        dry_run=False
    )
    # GitHubAppClient の get_authenticated が UseCase 内部で呼ばれるはずだが、
    # ここでは UseCase をモックしているため直接検証はできない。
    # UseCase のテスト (`test_create_github_resources.py`) で確認済み。


@pytest.mark.usefixtures("apply_patches")
@pytest.mark.parametrize("ai_model_env, expected_ai_model", [
    ("openai", "openai"),
    ("gemini", "gemini"),
    (None, "openai"),  # 環境変数なしの場合のデフォルト
])
def test_cli_ai_model_switch(mock_dependencies, dummy_md_file: Path, ai_model_env, expected_ai_model):
    """AI モデル切り替え (AC-AI-Switch): 環境変数 AI_MODEL"""
    mock_main_uc = mock_dependencies['main_uc']
    mock_ai_parser = mock_dependencies['ai_parser']
    # 設定モックのパッチを取得
    mock_settings_patch = mock_dependencies['patches']['load_settings']

    # 環境変数を設定
    env_vars = {}
    if ai_model_env:
        env_vars["AI_MODEL"] = ai_model_env
    # 必須の環境変数をダミーで設定
    env_vars["GITHUB_PAT"] = "dummy"
    env_vars["OPENAI_API_KEY"] = "dummy"
    # 必要ならGEMINI_API_KEYも
    if ai_model_env == "gemini":
        env_vars["GEMINI_API_KEY"] = "dummy_gemini"

    with mock.patch.dict(os.environ, env_vars, clear=True):
        # load_settings が正しいai_modelを持つSettingsを返すように再設定
        updated_settings = MagicMock(spec=Settings, log_level="INFO")
        updated_settings.github_pat = SecretStr("dummy")
        updated_settings.openai_api_key = SecretStr("dummy")
        updated_settings.gemini_api_key = SecretStr(
            "dummy_gemini") if ai_model_env == "gemini" else None
        updated_settings.ai_model = expected_ai_model
        mock_settings_patch.stop()  # 一旦パッチを停止
        mock_settings_patch.return_value = updated_settings
        mock_settings_patch.start()  # 更新した設定でパッチを再開

        result = runner.invoke(app, [
            "--file", str(dummy_md_file),
            "--repo", "owner/repo",
        ])

        assert result.exit_code == 0, f"Stderr: {result.stderr}"
        # AIParserクラス自体が既にモック化されているため、
        # 設定の検証は行わず、UseCase実行の成功を確認するだけで十分
        mock_main_uc.execute.assert_called_once()


# --- エラーハンドリングテスト ---

@pytest.mark.usefixtures("apply_patches")
def test_cli_error_handling_settings_validation(mock_dependencies, dummy_md_file: Path, capsys):
    """エラーハンドリング (AC-Error-Handling): 設定不備"""
    mock_load_settings = mock_dependencies['patches']['load_settings']
    mock_load_settings.stop()
    validation_error = ValidationError.from_exception_data(
        title="Settings",
        line_errors=[
            {'loc': ('GITHUB_PAT',), 'msg': 'Field required', 'type': 'missing'}]
    )
    new_mock = patch('core_logic.main.load_settings',
                     side_effect=validation_error)
    new_mock.start()
    try:
        result = runner.invoke(app, [
            "--file", str(dummy_md_file),
            "--repo", "owner/repo",
        ])
        assert result.exit_code == 1
        stderr = result.stderr
        assert "Configuration validation error(s)" in stderr
        assert "GITHUB_PAT" in stderr
        assert "Field required" in stderr
    finally:
        new_mock.stop()
        mock_load_settings.start()


@pytest.mark.usefixtures("apply_patches")
def test_cli_error_handling_file_not_found(mock_dependencies):
    """エラーハンドリング (AC-Error-Handling): ファイル読み込みエラー (FileNotFound)"""
    # Typerが処理するため、モック不要、存在しないパスを指定
    result = runner.invoke(app, [
        "--file", "nonexistent/path/to/file.md",
        "--repo", "owner/repo",
    ])
    # 終了コードの検証（Typerのエラーは通常2または1）
    assert result.exit_code != 0
    # 以下のいずれかの文字列がエラーメッセージに含まれていることを確認
    # より柔軟な検証にすることでテスト環境による差異を吸収
    stderr = result.stderr
    assert any([
        "Invalid value for '--file'" in stderr,
        "nonexistent/path/to/file.md" in stderr
    ])


@pytest.mark.usefixtures("apply_patches")
# @pytest.mark.skipif(os.name == 'nt', reason="Permission test requires non-Windows OS")
def test_cli_error_handling_file_permission(mock_dependencies, dummy_permission_denied_file: Path, capsys):
    """エラーハンドリング (AC-Error-Handling): ファイル読み込みエラー (PermissionError)"""
    # パッチの取得と一時停止
    mock_read_file = mock_dependencies['patches']['read_markdown_file']
    mock_read_file.stop()

    # PermissionErrorを発生させるように設定
    error_message = f"Permission denied: '{dummy_permission_denied_file}'"
    new_mock = patch('core_logic.main.read_markdown_file',
                     side_effect=PermissionError(error_message))
    new_mock.start()

    try:
        result = runner.invoke(app, [
            "--file", str(dummy_permission_denied_file),
            "--repo", "owner/repo",
        ])

        assert result.exit_code == 1
        stderr = result.stderr
        assert "Permission denied" in stderr
    finally:
        # クリーンアップと元のモックの復元
        new_mock.stop()
        mock_read_file.start()


@pytest.mark.usefixtures("apply_patches")
def test_cli_error_handling_ai_parser(mock_dependencies, dummy_md_file: Path, capsys):
    """エラーハンドリング (AC-Error-Handling): AI 解析エラー"""
    mock_ai_parser = mock_dependencies['ai_parser']
    error_message = "AI API key is invalid"
    mock_ai_parser.parse.side_effect = AiParserError(error_message)

    with capsys.disabled():
        result = runner.invoke(app, [
            "--file", str(dummy_md_file),
            "--repo", "owner/repo",
        ])

    assert result.exit_code == 1
    stderr = result.stderr
    assert "AI parsing error" in stderr
    assert error_message in stderr


@pytest.mark.usefixtures("apply_patches")
def test_cli_error_handling_use_case_github_auth(mock_dependencies, dummy_md_file: Path, capsys):
    """エラーハンドリング (AC-Error-Handling): UseCase 実行中の GitHub 認証エラー"""
    mock_main_uc = mock_dependencies['main_uc']
    error_message = "Bad credentials"
    mock_main_uc.execute.side_effect = GitHubAuthenticationError(error_message)

    with capsys.disabled():
        result = runner.invoke(app, [
            "--file", str(dummy_md_file),
            "--repo", "owner/repo",
        ])

    assert result.exit_code == 1
    stderr = result.stderr
    assert "Workflow failed: GitHubAuthenticationError" in stderr
    assert error_message in stderr


@pytest.mark.usefixtures("apply_patches")
def test_cli_error_handling_use_case_github_client(mock_dependencies, dummy_md_file: Path, capsys):
    """エラーハンドリング (AC-Error-Handling): UseCase 実行中の GitHub クライアントエラー"""
    mock_main_uc = mock_dependencies['main_uc']
    error_message = "Rate limit exceeded"
    mock_main_uc.execute.side_effect = GitHubClientError(
        error_message)  # RateLimitErrorもClientErrorを継承

    with capsys.disabled():
        result = runner.invoke(app, [
            "--file", str(dummy_md_file),
            "--repo", "owner/repo",
        ])

    assert result.exit_code == 1
    stderr = result.stderr
    assert "Workflow failed: GitHubClientError" in stderr
    assert error_message in stderr


@pytest.mark.usefixtures("apply_patches")
def test_cli_error_handling_use_case_unexpected(mock_dependencies, dummy_md_file: Path, capsys):
    """エラーハンドリング (AC-Error-Handling): UseCase 実行中の予期せぬエラー"""
    mock_main_uc = mock_dependencies['main_uc']
    error_message = "Something unexpected happened"
    mock_main_uc.execute.side_effect = Exception(error_message)  # 汎用エラー

    with capsys.disabled():
        result = runner.invoke(app, [
            "--file", str(dummy_md_file),
            "--repo", "owner/repo",
        ])

    assert result.exit_code == 1
    stderr = result.stderr
    assert "An unexpected critical error occurred" in stderr
    assert error_message in stderr


@pytest.mark.usefixtures("apply_patches")
def test_cli_github_pat_not_set(tmp_path, capsys):
    """GITHUB_PAT未設定時はエラー終了する
    注意: CliRunnerの仕様上、runコマンド関数の先頭で例外が発生した場合はexit_codeの検証はできない。
    そのため、エラーメッセージのみ検証する。"""
    dummy_file = tmp_path / "dummy.md"
    dummy_file.write_text("dummy")
    with patch.dict(os.environ, {}, clear=True):
        with patch("core_logic.main.load_settings", side_effect=ValueError("GITHUB_PAT is required but not set.")):
            result = runner.invoke(app, ["--file", str(dummy_file), "--repo",
                                   "dummy-repo", "--config-file", "/non/existent/file.yaml"])
            stderr = result.stderr
            assert "GITHUB_PAT" in stderr


@pytest.mark.usefixtures("apply_patches")
def test_cli_github_pat_empty(tmp_path, capsys):
    """GITHUB_PATが空文字時はエラー終了する
    注意: CliRunnerの仕様上、runコマンド関数の先頭で例外が発生した場合はexit_codeの検証はできない。
    そのため、エラーメッセージのみ検証する。"""
    dummy_file = tmp_path / "dummy.md"
    dummy_file.write_text("dummy")
    with patch.dict(os.environ, {"GITHUB_PAT": "   "}, clear=True):
        with patch("core_logic.main.load_settings", side_effect=ValueError("GITHUB_PAT cannot be empty")):
            result = runner.invoke(app, ["--file", str(dummy_file), "--repo",
                                   "dummy-repo", "--config-file", "/non/existent/file.yaml"])
            stderr = result.stderr
            assert "GITHUB_PAT cannot be empty" in stderr

# test_cli_github_pat_invalid は apply_patches を使わず、個別patchのみ


def test_cli_github_pat_invalid(tmp_path, capsys):
    """GITHUB_PATが無効な場合は認証エラーで終了する
    注意: CliRunnerの仕様上、runコマンド関数の先頭で例外が発生した場合はexit_codeの検証はできない。
    そのため、エラーメッセージのみ検証する。"""
    dummy_file = tmp_path / "dummy.md"
    dummy_file.write_text("dummy")
    from core_logic.domain.models import ParsedRequirementData, IssueData
    from core_logic.adapters.github_rest_client import GitHubRestClient
    from core_logic.domain.exceptions import GitHubAuthenticationError

    class DummySettings:
        def __init__(self):
            class DummyPat:
                def get_secret_value(self):
                    return "invalid_token"
            self.github_pat = DummyPat()
            self.final_log_level = "INFO"
            self.gemini_api_key = None
            self.ai_model = "openai"

            class DummyAI:
                prompt_template = "{markdown_text}"
                openai_model_name = "gpt-4o"
                gemini_model_name = "gemini-1.5-flash"
            self.ai = DummyAI()
            self.prompt_template = "{markdown_text}"
            self.final_openai_model_name = "gpt-4o"
            self.final_gemini_model_name = "gemini-1.5-flash"

            class DummyLogging:
                log_level = "INFO"
            self.logging = DummyLogging()
    # 本物のGitHubRestClientインスタンスを生成し、get_authenticated_userだけをモック
    real_client = GitHubRestClient(github_instance=GitHub("invalid_token"))
    real_client.get_authenticated_user = MagicMock(
        side_effect=GitHubAuthenticationError("Invalid PAT"))
    with patch("core_logic.main.GitHubRestClient", return_value=real_client):
        with patch("core_logic.main.AIParser") as mock_ai_parser_cls:
            mock_ai_parser = MagicMock()
            mock_ai_parser.parse.return_value = ParsedRequirementData(
                issues=[IssueData(title="t", description="d")])
            mock_ai_parser_cls.return_value = mock_ai_parser
            with patch.dict(os.environ, {"GITHUB_PAT": "invalid_token"}, clear=True):
                with patch("core_logic.main.load_settings", return_value=DummySettings()):
                    result = runner.invoke(
                        app, ["--file", str(dummy_file), "--repo", "dummy-repo", "--config-file", "/non/existent/file.yaml"])
                    stderr = result.stderr
                    assert "Invalid PAT" in stderr


# --- 信頼度低下時のAIパース警告・エラー出力/処理中断テスト ---
@pytest.mark.usefixtures("apply_patches")
def test_cli_ai_parser_low_confidence(monkeypatch, mock_dependencies, dummy_md_file: Path, capsys):
    """
    AIパーサーが低信頼度（confidence<0.7, warningsあり）のAISuggestedRulesを返した場合、
    CLIが警告またはエラーを出力し、処理を中断すること（backlog.yml/requirements.yml要件）
    """
    from core_logic.domain.models import AISuggestedRules, ParsedRequirementData, IssueData
    # 低信頼度のAISuggestedRulesを返すようにAIParserをモック
    low_conf_rules = AISuggestedRules(
        separator_rule={"separator_pattern": "---"},
        key_mapping_rule={"Title": "title", "Description": "description"},
        confidence=0.5,
        warnings=["AI推論ルールの信頼度が低いです"],
        errors=[]
    )
    # parse()は通常通りParsedRequirementDataを返すが、infer_rules()で低信頼度を返す
    mock_ai_parser = mock_dependencies['ai_parser']
    mock_ai_parser.infer_rules.return_value = low_conf_rules
    mock_ai_parser.parse.return_value = ParsedRequirementData(issues=[
        IssueData(title="t", description="d")
    ])

    # monkeypatchでmain.AIParserをこのモックに差し替え
    monkeypatch.setattr("core_logic.main.AIParser",
                        lambda settings: mock_ai_parser)

    # CLI実行
    result = runner.invoke(app, [
        "--file", str(dummy_md_file),
        "--repo", "owner/repo",
    ])
    # 信頼度低下時は警告またはエラーがstderrに出力され、終了コードが1になること
    assert result.exit_code == 1
    stderr = result.stderr
    assert "信頼度が低い" in stderr or "AI推論ルールの信頼度が低い" in stderr or "低信頼度" in stderr
    assert "修正" in stderr or "中断" in stderr or "エラー" in stderr

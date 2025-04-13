import pytest
from unittest.mock import MagicMock, patch, call
from pathlib import Path

# テスト対象 UseCase と依存コンポーネント、データモデル、例外をインポート
from github_automation_tool.use_cases.create_github_resources import CreateGitHubResourcesUseCase
from github_automation_tool.infrastructure.config import Settings
# file_reader は関数なので import しない (モックで代用)
# from github_automation_tool.infrastructure.file_reader import read_markdown_file
from github_automation_tool.adapters.ai_parser import AIParser
from github_automation_tool.adapters.github_client import GitHubAppClient
from github_automation_tool.use_cases.create_repository import CreateRepositoryUseCase
from github_automation_tool.use_cases.create_issues import CreateIssuesUseCase
from github_automation_tool.adapters.cli_reporter import CliReporter
from github_automation_tool.domain.models import ParsedRequirementData, IssueData, CreateIssuesResult
from github_automation_tool.domain.exceptions import (
    FileProcessingError, AiParserError, GitHubClientError, GitHubValidationError, GitHubAuthenticationError
)

# --- Fixtures ---
@pytest.fixture
def mock_settings() -> MagicMock:
    return MagicMock(spec=Settings)

@pytest.fixture
def mock_file_reader() -> MagicMock:
    # 関数なので呼び出し可能なモックを返す
    return MagicMock()

@pytest.fixture
def mock_ai_parser() -> MagicMock:
    mock = MagicMock(spec=AIParser)
    mock.parse = MagicMock()
    return mock

@pytest.fixture
def mock_github_client() -> MagicMock:
    """GitHubAppClient のモック、認証ユーザー取得もモック"""
    mock = MagicMock(spec=GitHubAppClient)
    mock_user_data = MagicMock(login="test-auth-user")
    mock_auth_user_response = MagicMock()
    mock_auth_user_response.parsed_data = mock_user_data
    # githubkit の階層構造を模倣
    mock.gh = MagicMock()
    mock.gh.rest = MagicMock()
    mock.gh.rest.users = MagicMock()
    mock.gh.rest.users.get_authenticated = MagicMock(return_value=mock_auth_user_response)
    return mock

@pytest.fixture
def mock_create_repo_uc() -> MagicMock:
    mock = MagicMock(spec=CreateRepositoryUseCase)
    mock.execute = MagicMock()
    return mock

@pytest.fixture
def mock_create_issues_uc() -> MagicMock:
    mock = MagicMock(spec=CreateIssuesUseCase)
    mock.execute = MagicMock()
    return mock

@pytest.fixture
def mock_reporter() -> MagicMock:
    mock = MagicMock(spec=CliReporter)
    mock.display_repository_creation_result = MagicMock()
    mock.display_issue_creation_result = MagicMock()
    return mock

@pytest.fixture
def use_case(mock_settings, mock_file_reader, mock_ai_parser, mock_github_client,
             mock_create_repo_uc, mock_create_issues_uc, mock_reporter) -> CreateGitHubResourcesUseCase:
    """テスト対象 UseCase (全ての依存をモック化)"""
    return CreateGitHubResourcesUseCase(
        settings=mock_settings,
        file_reader=mock_file_reader,
        ai_parser=mock_ai_parser,
        github_client=mock_github_client,
        create_repo_uc=mock_create_repo_uc,
        create_issues_uc=mock_create_issues_uc,
        reporter=mock_reporter
    )

# --- Test Data ---
DUMMY_FILE_PATH = Path("dummy/requirements.md")
DUMMY_REPO_NAME_FULL = "test-owner/test-repo"
DUMMY_REPO_NAME_ONLY = "test-repo-only"
DUMMY_PROJECT_NAME = "Test Project"
DUMMY_MARKDOWN_CONTENT = "# Test Markdown Content"
DUMMY_PARSED_DATA = ParsedRequirementData(issues=[IssueData(title="Test Issue", body="Test Body")])
DUMMY_REPO_URL = f"https://github.com/{DUMMY_REPO_NAME_FULL}"
DUMMY_ISSUE_RESULT = CreateIssuesResult(created_issue_urls=["url/1"], skipped_issue_titles=[], failed_issue_titles=[], errors=[])
EXPECTED_OWNER = "test-owner"
EXPECTED_REPO = "test-repo"
EXPECTED_AUTH_USER = "test-auth-user"

# --- Test Cases ---

def test_execute_success_full_repo_name(use_case: CreateGitHubResourcesUseCase, mock_file_reader, mock_ai_parser, mock_create_repo_uc, mock_create_issues_uc, mock_reporter, mock_github_client):
    """正常系: owner/repo形式のリポジトリ名で全ステップ成功"""
    # Arrange: 各ステップのモックの戻り値を設定
    mock_file_reader.return_value = DUMMY_MARKDOWN_CONTENT
    mock_ai_parser.parse.return_value = DUMMY_PARSED_DATA
    mock_create_repo_uc.execute.return_value = DUMMY_REPO_URL
    mock_create_issues_uc.execute.return_value = DUMMY_ISSUE_RESULT

    # Act
    use_case.execute(DUMMY_FILE_PATH, DUMMY_REPO_NAME_FULL, DUMMY_PROJECT_NAME)

    # Assert: 各依存コンポーネントが期待通り呼ばれたか検証
    mock_file_reader.assert_called_once_with(DUMMY_FILE_PATH)
    mock_ai_parser.parse.assert_called_once_with(DUMMY_MARKDOWN_CONTENT)
    mock_github_client.gh.rest.users.get_authenticated.assert_not_called() # owner指定ありなので呼ばれない
    mock_create_repo_uc.execute.assert_called_once_with(EXPECTED_REPO) # repo名のみ渡す
    mock_create_issues_uc.execute.assert_called_once_with(DUMMY_PARSED_DATA, EXPECTED_OWNER, EXPECTED_REPO)
    mock_reporter.display_repository_creation_result.assert_called_once_with(DUMMY_REPO_URL, EXPECTED_REPO)
    mock_reporter.display_issue_creation_result.assert_called_once_with(DUMMY_ISSUE_RESULT, DUMMY_REPO_NAME_FULL)

def test_execute_success_repo_name_only(use_case: CreateGitHubResourcesUseCase, mock_file_reader, mock_ai_parser, mock_create_repo_uc, mock_create_issues_uc, mock_reporter, mock_github_client):
    """正常系: repo名のみ指定され、ownerをAPIで取得して成功"""
    mock_file_reader.return_value = DUMMY_MARKDOWN_CONTENT
    mock_ai_parser.parse.return_value = DUMMY_PARSED_DATA
    expected_repo_url = f"https://github.com/{EXPECTED_AUTH_USER}/{DUMMY_REPO_NAME_ONLY}"
    mock_create_repo_uc.execute.return_value = expected_repo_url
    mock_create_issues_uc.execute.return_value = DUMMY_ISSUE_RESULT

    use_case.execute(DUMMY_FILE_PATH, DUMMY_REPO_NAME_ONLY, DUMMY_PROJECT_NAME)

    mock_file_reader.assert_called_once_with(DUMMY_FILE_PATH)
    mock_ai_parser.parse.assert_called_once_with(DUMMY_MARKDOWN_CONTENT)
    mock_github_client.gh.rest.users.get_authenticated.assert_called_once() # owner取得のために呼ばれる
    mock_create_repo_uc.execute.assert_called_once_with(DUMMY_REPO_NAME_ONLY)
    mock_create_issues_uc.execute.assert_called_once_with(DUMMY_PARSED_DATA, EXPECTED_AUTH_USER, DUMMY_REPO_NAME_ONLY)
    mock_reporter.display_repository_creation_result.assert_called_once_with(expected_repo_url, DUMMY_REPO_NAME_ONLY)
    mock_reporter.display_issue_creation_result.assert_called_once_with(DUMMY_ISSUE_RESULT, f"{EXPECTED_AUTH_USER}/{DUMMY_REPO_NAME_ONLY}")

def test_execute_dry_run(use_case: CreateGitHubResourcesUseCase, mock_file_reader, mock_ai_parser, mock_create_repo_uc, mock_create_issues_uc, mock_reporter, mock_github_client):
    """Dry run モードの場合、GitHub操作とIssue作成UseCaseが呼ばれない"""
    mock_file_reader.return_value = DUMMY_MARKDOWN_CONTENT
    mock_ai_parser.parse.return_value = DUMMY_PARSED_DATA

    use_case.execute(DUMMY_FILE_PATH, DUMMY_REPO_NAME_FULL, DUMMY_PROJECT_NAME, dry_run=True)

    mock_file_reader.assert_called_once()
    mock_ai_parser.parse.assert_called_once()
    mock_github_client.gh.rest.users.get_authenticated.assert_not_called() # owner指定あり
    # GitHub操作は行われない
    mock_create_repo_uc.execute.assert_not_called()
    mock_create_issues_uc.execute.assert_not_called()
    # ReporterはDry Run用の情報で呼ばれる
    mock_reporter.display_repository_creation_result.assert_called_once()
    mock_reporter.display_issue_creation_result.assert_called_once()

def test_execute_file_read_error(use_case: CreateGitHubResourcesUseCase, mock_file_reader, mock_ai_parser, mock_create_repo_uc, mock_create_issues_uc):
    """ファイル読み込みでエラーが発生した場合、処理が中断し例外が送出される"""
    # FileProcessingError をインポートしておくこと
    mock_error = FileProcessingError("Cannot read file", original_exception=IOError())
    mock_file_reader.side_effect = mock_error

    with pytest.raises(FileProcessingError):
        use_case.execute(DUMMY_FILE_PATH, DUMMY_REPO_NAME_FULL, DUMMY_PROJECT_NAME)

    # 後続処理は呼ばれない
    mock_ai_parser.parse.assert_not_called()
    mock_create_repo_uc.execute.assert_not_called()
    mock_create_issues_uc.execute.assert_not_called()

def test_execute_ai_parse_error(use_case: CreateGitHubResourcesUseCase, mock_file_reader, mock_ai_parser, mock_create_repo_uc, mock_create_issues_uc):
    """AI解析でエラーが発生した場合、処理が中断し例外が送出される"""
    mock_file_reader.return_value = DUMMY_MARKDOWN_CONTENT
    mock_error = AiParserError("AI failed")
    mock_ai_parser.parse.side_effect = mock_error

    with pytest.raises(AiParserError):
        use_case.execute(DUMMY_FILE_PATH, DUMMY_REPO_NAME_FULL, DUMMY_PROJECT_NAME)

    # リポジトリ作成以降は呼ばれない
    mock_create_repo_uc.execute.assert_not_called()
    mock_create_issues_uc.execute.assert_not_called()

def test_execute_repo_creation_error(use_case: CreateGitHubResourcesUseCase, mock_file_reader, mock_ai_parser, mock_create_repo_uc, mock_create_issues_uc, mock_reporter):
    """リポジトリ作成でエラーが発生した場合、処理が中断し例外が送出される"""
    mock_file_reader.return_value = DUMMY_MARKDOWN_CONTENT
    mock_ai_parser.parse.return_value = DUMMY_PARSED_DATA
    mock_error = GitHubValidationError("Repo exists")
    mock_create_repo_uc.execute.side_effect = mock_error

    with pytest.raises(GitHubValidationError):
        use_case.execute(DUMMY_FILE_PATH, DUMMY_REPO_NAME_FULL, DUMMY_PROJECT_NAME)

    mock_create_repo_uc.execute.assert_called_once() # Repo作成は試みられる
    # Reporter はエラー発生時には呼ばれない想定（main.pyで最終的に表示）
    mock_reporter.display_repository_creation_result.assert_not_called()
    mock_create_issues_uc.execute.assert_not_called() # Issue作成は呼ばれない
    mock_reporter.display_issue_creation_result.assert_not_called()

def test_execute_issue_creation_error(use_case: CreateGitHubResourcesUseCase, mock_file_reader, mock_ai_parser, mock_create_repo_uc, mock_create_issues_uc, mock_reporter):
    """Issue作成UseCaseでエラーが発生した場合、例外が送出される"""
    mock_file_reader.return_value = DUMMY_MARKDOWN_CONTENT
    mock_ai_parser.parse.return_value = DUMMY_PARSED_DATA
    mock_create_repo_uc.execute.return_value = DUMMY_REPO_URL
    mock_error = GitHubClientError("Issue creation failed")
    mock_create_issues_uc.execute.side_effect = mock_error

    with pytest.raises(GitHubClientError):
        use_case.execute(DUMMY_FILE_PATH, DUMMY_REPO_NAME_FULL, DUMMY_PROJECT_NAME)

    mock_create_repo_uc.execute.assert_called_once()
    mock_reporter.display_repository_creation_result.assert_called_once() # Repo作成は成功
    mock_create_issues_uc.execute.assert_called_once() # Issue作成は試みられる
    # Reporter はエラー発生時には呼ばれない想定
    mock_reporter.display_issue_creation_result.assert_not_called()

def test_get_owner_repo_invalid_format(use_case: CreateGitHubResourcesUseCase):
    """_get_owner_repo が不正な形式を弾くか"""
    with pytest.raises(ValueError, match="Invalid repository name format"):
        use_case._get_owner_repo("owner/") # repo名がない
    with pytest.raises(ValueError, match="Invalid repository name format"):
        use_case._get_owner_repo("/repo") # owner名がない
    # スラッシュが複数ある場合などは _get_owner_repo 内で ValueError になる想定
    # with pytest.raises(ValueError):
    #     use_case._get_owner_repo("owner/repo/extra")

def test_get_owner_repo_api_fails(use_case: CreateGitHubResourcesUseCase, mock_github_client):
    """認証ユーザー取得APIが失敗した場合にエラーになるか"""
    # モック設定: get_authenticated がエラーを送出
    mock_api_error = GitHubAuthenticationError("API Failed")
    mock_github_client.gh.rest.users.get_authenticated.side_effect = mock_api_error

    with pytest.raises(GitHubAuthenticationError):
         # repo名のみを指定して _get_owner_repo が内部で呼ばれる execute を実行
         use_case.execute(DUMMY_FILE_PATH, DUMMY_REPO_NAME_ONLY, DUMMY_PROJECT_NAME)
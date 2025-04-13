import pytest
from unittest.mock import patch, MagicMock
from pydantic import SecretStr

# テスト対象のクライアントとカスタム例外をインポート
from github_automation_tool.adapters.github_client import GitHubAppClient
from github_automation_tool.domain.exceptions import (
    GitHubValidationError, GitHubAuthenticationError, GitHubClientError,
    GitHubRateLimitError, GitHubResourceNotFoundError
)
# モック対象の RequestFailed とネットワークエラー用をインポート
from githubkit.exception import RequestFailed, RequestError, RequestTimeout


# --- Fixtures ---
@pytest.fixture
def mock_github_rest_api():
    """githubkit.GitHub().rest オブジェクトのモック"""
    mock = MagicMock()
    # 必要な属性を明示的に MagicMock として設定
    mock.repos = MagicMock()
    mock.search = MagicMock()
    mock.issues = MagicMock()
    return mock


@pytest.fixture
def mock_github_instance(mock_github_rest_api):
    """githubkit.GitHub インスタンスのモック"""
    mock = MagicMock()
    mock.rest = mock_github_rest_api
    return mock


@pytest.fixture
def github_client(mock_github_instance):
    """テスト用の GitHubAppClient インスタンス (内部の GitHub をモック化)"""
    # GitHub クラスのコンストラクタ呼び出しをパッチ
    with patch('github_automation_tool.adapters.github_client.GitHub', return_value=mock_github_instance) as mock_gh_class:
        client = GitHubAppClient(SecretStr("fake-valid-token"))
        # テスト内でモックにアクセスしやすくするために属性として保持
        client._mock_rest = mock_github_instance.rest
        yield client

# --- Test Cases ---

# --- Initialization Tests ---


def test_init_success():
    """有効なトークンで正常に初期化されるか"""
    with patch('github_automation_tool.adapters.github_client.GitHub') as mock_gh_class:
        try:
            GitHubAppClient(SecretStr("valid-token"))
        except GitHubAuthenticationError:
            pytest.fail("Initialization failed with a valid token")
        mock_gh_class.assert_called_once_with("valid-token")


def test_init_missing_token():
    """トークンがない場合に GitHubAuthenticationError が発生するか"""
    with pytest.raises(GitHubAuthenticationError, match="missing or empty"):
        GitHubAppClient(SecretStr(""))
    with pytest.raises(GitHubAuthenticationError, match="missing or empty"):
        GitHubAppClient(None)


@patch('github_automation_tool.adapters.github_client.GitHub', side_effect=Exception("Init failed"))
def test_init_github_error(mock_gh_class):
    """GitHub クライアント初期化時に予期せぬエラーが発生した場合"""
    with pytest.raises(GitHubClientError, match="Failed to initialize GitHub client"):
        GitHubAppClient(SecretStr("some-token"))

# --- Repository Creation Tests ---


def test_create_repository_success(github_client: GitHubAppClient):
    """リポジトリ作成が成功するケース"""
    repo_name = "test-success-repo"
    expected_url = f"https://github.com/user/{repo_name}"
    mock_response = MagicMock(status_code=201)
    mock_response.parsed_data = MagicMock(html_url=expected_url)
    github_client._mock_rest.repos.create_for_authenticated_user.return_value = mock_response
    created_url = github_client.create_repository(repo_name)
    assert created_url == expected_url
    github_client._mock_rest.repos.create_for_authenticated_user.assert_called_once_with(
        name=repo_name, private=True, auto_init=True
    )


def test_create_repository_already_exists(github_client: GitHubAppClient):
    """リポジトリが既に存在する場合 (422 エラー) に GitHubValidationError が発生するか"""
    repo_name = "existing-repo"
    mock_error_response = MagicMock(status_code=422, headers={
    }, content=b'{"message": "name already exists on this account"}')
    # __str__ をモックしてエラーメッセージ内容をシミュレート
    mock_api_error = RequestFailed(response=mock_error_response)
    # クライアント側の判定ロジックに合わせる
    mock_api_error.__str__ = lambda self: 'API Error 422: {"message": "name already exists on this account"}'
    github_client._mock_rest.repos.create_for_authenticated_user.side_effect = mock_api_error
    # 期待する例外メッセージを client 側の実装に合わせる
    with pytest.raises(GitHubValidationError, match=f"Repository '{repo_name}' already exists.") as excinfo:
        github_client.create_repository(repo_name)
    assert excinfo.value.status_code == 422
    assert excinfo.value.original_exception is mock_api_error


def test_create_repository_auth_error(github_client: GitHubAppClient):
    """リポジトリ作成で認証/権限エラー (403 Forbidden) が発生する場合"""
    repo_name = "forbidden-repo"
    mock_error_response = MagicMock(
        status_code=403, headers={}, content=b'')  # レート制限ではない
    mock_api_error = RequestFailed(response=mock_error_response)
    github_client._mock_rest.repos.create_for_authenticated_user.side_effect = mock_api_error
    # 期待する例外メッセージを _handle_request_failed の実装に合わせる
    with pytest.raises(GitHubAuthenticationError, match="Permission denied") as excinfo:
        github_client.create_repository(repo_name)
    assert excinfo.value.status_code == 403


def test_create_repository_network_error(github_client: GitHubAppClient):
    """リポジトリ作成でネットワークエラーが発生する場合"""
    repo_name = "network-error-repo"
    mock_network_error = RequestTimeout("Connection timed out")
    github_client._mock_rest.repos.create_for_authenticated_user.side_effect = mock_network_error
    # 期待する例外メッセージを _handle_other_error の実装に合わせる
    with pytest.raises(GitHubClientError, match="Network/Request error") as excinfo:
        github_client.create_repository(repo_name)
    assert excinfo.value.original_exception is mock_network_error


def test_create_repository_other_api_error(github_client: GitHubAppClient):
    """リポジトリ作成でその他のAPIエラー (例: 500) が発生する場合"""
    repo_name = "server-error-repo"
    mock_error_response = MagicMock(
        status_code=500, headers={}, content=b'Internal Server Error')
    mock_api_error = RequestFailed(response=mock_error_response)
    github_client._mock_rest.repos.create_for_authenticated_user.side_effect = mock_api_error
    # 期待する例外メッセージを _handle_request_failed の実装に合わせる (正規表現エスケープ追加)
    with pytest.raises(GitHubClientError, match=r"Unhandled GitHub API HTTP error \(Status: 500\)") as excinfo:
        github_client.create_repository(repo_name)
    assert excinfo.value.status_code == 500

# --- Issue Search Tests ---


def test_find_issue_by_title_exists(github_client: GitHubAppClient):
    """指定タイトルのIssueが存在する場合にTrueを返すか"""
    owner, repo, title = "test-owner", "test-repo", "My Existing Issue"
    mock_response = MagicMock(status_code=200)
    mock_response.parsed_data = MagicMock(total_count=1)
    github_client._mock_rest.search.issues_and_pull_requests.return_value = mock_response
    exists = github_client.find_issue_by_title(owner, repo, title)
    assert exists is True
    expected_query = f'repo:{owner}/{repo} is:issue is:open in:title "{title}"'
    github_client._mock_rest.search.issues_and_pull_requests.assert_called_once_with(
        q=expected_query, per_page=1)


def test_find_issue_by_title_not_exists(github_client: GitHubAppClient):
    """指定タイトルのIssueが存在しない場合にFalseを返すか"""
    owner, repo, title = "test-owner", "test-repo", "My New Issue"
    mock_response = MagicMock(status_code=200)
    mock_response.parsed_data = MagicMock(total_count=0)
    github_client._mock_rest.search.issues_and_pull_requests.return_value = mock_response
    exists = github_client.find_issue_by_title(owner, repo, title)
    assert exists is False


def test_find_issue_by_title_api_error(github_client: GitHubAppClient):
    """Issue検索でAPIエラー (例: レート制限 403) が発生する場合"""
    owner, repo, title = "test-owner", "test-repo", "Rate Limited Issue"
    mock_error_response = MagicMock(status_code=403, headers={
                                    "X-RateLimit-Remaining": "0"}, content=b'')
    mock_api_error = RequestFailed(response=mock_error_response)
    github_client._mock_rest.search.issues_and_pull_requests.side_effect = mock_api_error
    with pytest.raises(GitHubRateLimitError):  # _handle_request_failed が適切な例外を返す
        github_client.find_issue_by_title(owner, repo, title)

# --- Issue Creation Tests ---


def test_create_issue_success(github_client: GitHubAppClient):
    """Issue作成が成功するケース"""
    owner, repo, title, body = "test-owner", "test-repo", "A New Issue", "Issue body content."
    expected_url = f"https://github.com/{owner}/{repo}/issues/123"
    mock_response = MagicMock(status_code=201)
    mock_response.parsed_data = MagicMock(html_url=expected_url)
    github_client._mock_rest.issues.create.return_value = mock_response
    created_url = github_client.create_issue(owner, repo, title, body)
    assert created_url == expected_url
    github_client._mock_rest.issues.create.assert_called_once_with(
        owner=owner, repo=repo, title=title, body=body or ""
    )


def test_create_issue_not_found_repo(github_client: GitHubAppClient):
    """Issue作成時にリポジトリが見つからない場合 (404 エラー)"""
    owner, repo, title, body = "test-owner", "nonexistent-repo", "Issue for missing repo", "Body"
    mock_error_response = MagicMock(status_code=404, headers={}, content=b'')
    mock_api_error = RequestFailed(response=mock_error_response)
    github_client._mock_rest.issues.create.side_effect = mock_api_error
    with pytest.raises(GitHubResourceNotFoundError):  # _handle_request_failed が適切な例外を返す
        github_client.create_issue(owner, repo, title, body)


def test_create_issue_validation_error(github_client: GitHubAppClient):
    """Issue作成でバリデーションエラー (422) が発生する場合"""
    owner, repo, title, body = "test-owner", "test-repo", "Invalid Issue", "Body"
    mock_error_response = MagicMock(
        status_code=422, headers={}, content=b'{"message":"Validation Failed"}')
    mock_api_error = RequestFailed(response=mock_error_response)
    github_client._mock_rest.issues.create.side_effect = mock_api_error
    # 期待する例外メッセージを _handle_request_failed の実装に合わせる
    with pytest.raises(GitHubValidationError, match=r"Validation failed \(422\)") as excinfo:
        github_client.create_issue(owner, repo, title, body)
    assert excinfo.value.status_code == 422

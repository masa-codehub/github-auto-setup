# tests/adapters/test_github_client.py

import logging
import pytest
from unittest.mock import patch, MagicMock, call # call をインポート
from pydantic import SecretStr

# テスト対象のクライアントとカスタム例外
from github_automation_tool.adapters.github_client import GitHubAppClient
from github_automation_tool.domain.exceptions import (
    GitHubValidationError, GitHubAuthenticationError, GitHubClientError,
    GitHubRateLimitError, GitHubResourceNotFoundError
)
# モック対象の githubkit 例外とモデル (Milestone, Repository, Response など)
from githubkit import Response # Response もモック化に使う
from githubkit.exception import RequestFailed, RequestError, RequestTimeout
# モデルのインポートパスを修正 (Milestone, Repository, SearchResults も)
from githubkit.versions.latest.models import (
    Label,
    Issue,
    Milestone,
    Repository,
    SimpleUser,
    IssueSearchResultItem  # Removed SearchIssuesAndPullRequestsGetResponse
)
import json



# --- Fixtures ---
@pytest.fixture
def mock_github_rest_api():
    """githubkit.GitHub().rest オブジェクトのモック"""
    mock = MagicMock()
    mock.repos = MagicMock()
    mock.search = MagicMock()
    mock.issues = MagicMock()
    mock.users = MagicMock()

    # Repository methods
    mock.repos.create_for_authenticated_user = MagicMock()

    # Search methods
    mock.search.issues_and_pull_requests = MagicMock()

    # Issue methods
    mock.issues.get_label = MagicMock()
    mock.issues.create_label = MagicMock()
    mock.issues.create = MagicMock() # create_issue用
    # Milestone methods
    mock.issues.list_milestones = MagicMock()
    mock.issues.create_milestone = MagicMock()
    # mock.issues.get_milestone = MagicMock() # 必要なら追加

    # User methods
    mock.users.get_authenticated = MagicMock()
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
    with patch('github_automation_tool.adapters.github_client.GitHub', return_value=mock_github_instance):
        # 初期化時の接続テストをスキップするためにパッチを当てる（オプション）
        with patch.object(GitHubAppClient, '_perform_connection_test', return_value=None):
             client = GitHubAppClient(SecretStr("fake-valid-token"))
        # テスト内で直接 rest API モックにアクセスできるように属性を追加
        client._mock_rest_api = mock_github_instance.rest
        yield client


# --- Test Data ---
OWNER = "test-owner"
REPO = "test-repo"
# Milestone Test Data
MILESTONE_TITLE = "Sprint 1"
MILESTONE_ID = 10
MILESTONE_DESCRIPTION = "First sprint goals"
# githubkit.models.Milestone のモック用データ (必要な属性のみ)
# Userモデルの基本的なモックも作成
MOCK_USER_DATA = SimpleUser(
    login="test-creator", id=1, node_id="U_1", avatar_url="", gravatar_id="", url="",
    html_url="", followers_url="", following_url="", gists_url="", starred_url="",
    subscriptions_url="", organizations_url="", repos_url="", events_url="",
    received_events_url="", type="User", site_admin=False
)
MOCK_MILESTONE_DATA = Milestone(
    url=f"https://api.github.com/repos/{OWNER}/{REPO}/milestones/{MILESTONE_ID}",
    html_url=f"https://github.com/{OWNER}/{REPO}/milestone/{MILESTONE_ID}",
    labels_url=f"https://api.github.com/repos/{OWNER}/{REPO}/milestones/{MILESTONE_ID}/labels",
    id=MILESTONE_ID * 100, # GitHubのID (numberとは別)
    node_id=f"MDk6TWlsZXN0b25l{MILESTONE_ID}", # Example Node ID
    number=MILESTONE_ID, # Milestone Number (これがIssueで使われるID)
    state="open",
    title=MILESTONE_TITLE,
    description=MILESTONE_DESCRIPTION,
    creator=MOCK_USER_DATA, # Userモデルのモックを使用
    open_issues=5,
    closed_issues=10,
    created_at="2025-01-01T00:00:00Z", # Example ISO timestamp
    updated_at="2025-01-10T00:00:00Z",
    closed_at=None,
    due_on=None
)
# githubkit.models.Repository のモック
MOCK_REPO_DATA = Repository(
    id=123, node_id="R_1", name=REPO, full_name=f"{OWNER}/{REPO}", private=True,
    owner=MOCK_USER_DATA, # ownerもUserモデル
    html_url=f"https://github.com/{OWNER}/{REPO}", description="Test repo", fork=False,
    url=f"https://api.github.com/repos/{OWNER}/{REPO}", forks_url="", keys_url="",
    collaborators_url="", teams_url="", hooks_url="", issue_events_url="", events_url="",
    assignees_url="", branches_url="", tags_url="", blobs_url="", git_tags_url="",
    git_refs_url="", trees_url="", statuses_url="", languages_url="", stargazers_url="",
    contributors_url="", subscribers_url="", subscription_url="", commits_url="",
    git_commits_url="", comments_url="", issue_comment_url="", contents_url="",
    compare_url="", merges_url="", archive_url="", downloads_url="", issues_url="",
    pulls_url="", milestones_url="", notifications_url="", labels_url="", releases_url="",
    deployments_url="", created_at="2025-01-01T00:00:00Z", updated_at="2025-01-01T00:00:00Z",
    pushed_at="2025-01-01T00:00:00Z", git_url="", ssh_url="", clone_url="", svn_url="",
    homepage=None, size=0, stargazers_count=0, watchers_count=0, language=None,
    has_issues=True, has_projects=True, has_downloads=True, has_wiki=True, has_pages=False,
    has_discussions=False, forks_count=0, mirror_url=None, archived=False, disabled=False,
    open_issues_count=5, license=None, allow_forking=True, is_template=False,
    web_commit_signoff_required=False, topics=[], visibility="private", forks=0, open_issues=5,
    watchers=0, default_branch="main"
)
# githubkit.models.Issue のモック
MOCK_ISSUE_DATA = Issue(
    id=456, node_id="I_1", url=f"https://api.github.com/repos/{OWNER}/{REPO}/issues/1",
    repository_url=f"https://api.github.com/repos/{OWNER}/{REPO}", labels_url="",
    comments_url="", events_url="", html_url=f"https://github.com/{OWNER}/{REPO}/issues/1",
    number=1, state="open", title="Test Issue", body="Test Body", user=MOCK_USER_DATA,
    labels=[], assignee=None, assignees=[], milestone=None, locked=False,
    active_lock_reason=None, comments=0, pull_request=None, closed_at=None,
    created_at="2025-01-15T00:00:00Z", updated_at="2025-01-15T00:00:00Z",
    repository=MOCK_REPO_DATA, # Repositoryモデルのモック
    author_association="OWNER", state_reason=None
)
# ★ MagicMock を使用して検索結果レスポンスをモック ★
MOCK_SEARCH_RESULT_FOUND = MagicMock()
setattr(MOCK_SEARCH_RESULT_FOUND, 'total_count', 1)
setattr(MOCK_SEARCH_RESULT_FOUND, 'incomplete_results', False)
setattr(MOCK_SEARCH_RESULT_FOUND, 'items', [MOCK_ISSUE_DATA])

MOCK_SEARCH_RESULT_NOT_FOUND = MagicMock()
setattr(MOCK_SEARCH_RESULT_NOT_FOUND, 'total_count', 0)
setattr(MOCK_SEARCH_RESULT_NOT_FOUND, 'incomplete_results', False)
setattr(MOCK_SEARCH_RESULT_NOT_FOUND, 'items', [])
# Label のモック
MOCK_LABEL_DATA = Label(
    id=1, node_id="L_1", url=f"https://api.github.com/repos/{OWNER}/{REPO}/labels/bug",
    name="bug", color="d73a4a", default=True, description="Something isn't working"
)


# --- Helper Function for Mock Response ---
def create_mock_response(status_code: int, parsed_data: any = None, content: bytes = b'{}', headers: dict | None = None) -> MagicMock:
    """テスト用の githubkit.Response 互換の MagicMock オブジェクトを生成するヘルパー関数"""
    mock_resp = MagicMock(spec=Response)
    mock_resp.status_code = status_code
    mock_resp.headers = headers or {}
    mock_resp.content = content
    mock_resp.parsed_data = parsed_data
    # json() メソッドをモック
    mock_resp.json.return_value = json.loads(content.decode()) if content else {}

    # RequestFailed がアクセスする可能性のある属性を設定
    mock_request = MagicMock()
    mock_request.method = "GET"
    mock_request.url = "http://dummy.url/api"
    mock_resp.request = mock_request
    # raw_response は自身を返すようにしておく
    mock_resp.raw_response = mock_resp
    return mock_resp


# --- Test Cases ---

# --- Initialization Tests ---
def test_init_success(mock_github_instance):
    """正常に初期化できるか"""
    with patch('github_automation_tool.adapters.github_client.GitHub', return_value=mock_github_instance):
         with patch.object(GitHubAppClient, '_perform_connection_test', return_value=None):
              client = GitHubAppClient(SecretStr("fake-valid-token"))
    assert client.gh is mock_github_instance

def test_init_missing_token():
    """トークンがない場合に GitHubAuthenticationError が発生するか"""
    with pytest.raises(GitHubAuthenticationError, match="missing or empty"):
        GitHubAppClient(SecretStr(""))
    with pytest.raises(GitHubAuthenticationError, match="missing or empty"):
        GitHubAppClient(None) # type: ignore

@patch('github_automation_tool.adapters.github_client.GitHub', side_effect=Exception("Init failed"))
def test_init_github_error(mock_gh_class):
    """GitHub クラスの初期化でエラーが発生した場合"""
    with pytest.raises(GitHubClientError, match="Failed to initialize GitHub client: Init failed"):
        GitHubAppClient(SecretStr("fake-valid-token"))

# --- Repository Creation Tests ---
def test_create_repository_success(github_client: GitHubAppClient):
    """リポジトリ作成成功"""
    repo_name = "new-test-repo"
    expected_url = f"https://github.com/{OWNER}/{repo_name}"
    # Repository オブジェクトのモックを作成 (html_urlを持つ)
    mock_repo_obj = MagicMock(spec=Repository, html_url=expected_url)
    mock_response = create_mock_response(201, parsed_data=mock_repo_obj)
    github_client._mock_rest_api.repos.create_for_authenticated_user.return_value = mock_response

    repo_url = github_client.create_repository(repo_name)

    assert repo_url == expected_url
    github_client._mock_rest_api.repos.create_for_authenticated_user.assert_called_once_with(
        name=repo_name, private=True, auto_init=True
    )

def test_create_repository_already_exists(github_client: GitHubAppClient):
    """リポジトリが既に存在する (422 Validation Failed - name already exists)"""
    repo_name = "existing-repo"
    # 422 エラーレスポンスのモック
    error_content = b'{"message": "Validation Failed", "errors": [{"resource": "Repository", "code": "custom", "field": "name", "message": "name already exists on this account"}]}'
    mock_error_response = create_mock_response(422, content=error_content)
    mock_api_error = RequestFailed(response=mock_error_response)
    github_client._mock_rest_api.repos.create_for_authenticated_user.side_effect = mock_api_error

    with pytest.raises(GitHubValidationError, match="Repository name already exists"):
        github_client.create_repository(repo_name)
    github_client._mock_rest_api.repos.create_for_authenticated_user.assert_called_once_with(
        name=repo_name, private=True, auto_init=True
    )

def test_create_repository_auth_error(github_client: GitHubAppClient):
    """リポジトリ作成時の認証エラー (401)"""
    repo_name = "auth-fail-repo"
    mock_error_response = create_mock_response(401)
    mock_api_error = RequestFailed(response=mock_error_response)
    github_client._mock_rest_api.repos.create_for_authenticated_user.side_effect = mock_api_error

    with pytest.raises(GitHubAuthenticationError, match="Authentication failed"):
        github_client.create_repository(repo_name)

def test_create_repository_permission_error(github_client: GitHubAppClient):
    """リポジトリ作成時の権限エラー (403)"""
    repo_name = "perm-fail-repo"
    mock_error_response = create_mock_response(403, headers={"X-RateLimit-Remaining": "50"}) # Rate Limitではない403
    mock_api_error = RequestFailed(response=mock_error_response)
    github_client._mock_rest_api.repos.create_for_authenticated_user.side_effect = mock_api_error

    with pytest.raises(GitHubAuthenticationError, match="Permission denied"):
        github_client.create_repository(repo_name)

def test_create_repository_rate_limit_error(github_client: GitHubAppClient):
    """リポジトリ作成時のレート制限エラー (403)"""
    repo_name = "rate-limit-repo"
    mock_error_response = create_mock_response(403, headers={"X-RateLimit-Remaining": "0"}) # Rate Limit超過
    mock_api_error = RequestFailed(response=mock_error_response)
    github_client._mock_rest_api.repos.create_for_authenticated_user.side_effect = mock_api_error

    with pytest.raises(GitHubRateLimitError, match="rate limit exceeded"):
        github_client.create_repository(repo_name)

def test_create_repository_network_error(github_client: GitHubAppClient):
    """リポジトリ作成時のネットワークエラー"""
    repo_name = "network-error-repo"
    github_client._mock_rest_api.repos.create_for_authenticated_user.side_effect = RequestTimeout("Timeout")

    with pytest.raises(GitHubClientError, match="Network/Request error"):
        github_client.create_repository(repo_name)

def test_create_repository_other_api_error(github_client: GitHubAppClient):
    """リポジトリ作成時のその他のAPIエラー (500など)"""
    repo_name = "server-error-repo"
    mock_error_response = create_mock_response(500)
    mock_api_error = RequestFailed(response=mock_error_response)
    github_client._mock_rest_api.repos.create_for_authenticated_user.side_effect = mock_api_error

    with pytest.raises(GitHubClientError, match="Unhandled GitHub API HTTP error"):
        github_client.create_repository(repo_name)


# --- Issue Search Tests ---
def test_find_issue_by_title_exists(github_client: GitHubAppClient):
    """Issueタイトル検索: Issueが存在する"""
    issue_title = "Existing Issue"
    # 検索APIが total_count=1 の結果を返すようにモック
    mock_response = create_mock_response(200, parsed_data=MOCK_SEARCH_RESULT_FOUND)
    github_client._mock_rest_api.search.issues_and_pull_requests.return_value = mock_response

    exists = github_client.find_issue_by_title(OWNER, REPO, issue_title)

    assert exists is True
    expected_query = f'repo:{OWNER}/{REPO} is:issue is:open in:title "{issue_title}"'
    github_client._mock_rest_api.search.issues_and_pull_requests.assert_called_once_with(
        q=expected_query, per_page=1
    )

def test_find_issue_by_title_not_exists(github_client: GitHubAppClient):
    """Issueタイトル検索: Issueが存在しない"""
    issue_title = "Non Existing Issue"
    # 検索APIが total_count=0 の結果を返すようにモック
    mock_response = create_mock_response(200, parsed_data=MOCK_SEARCH_RESULT_NOT_FOUND)
    github_client._mock_rest_api.search.issues_and_pull_requests.return_value = mock_response

    exists = github_client.find_issue_by_title(OWNER, REPO, issue_title)

    assert exists is False
    expected_query = f'repo:{OWNER}/{REPO} is:issue is:open in:title "{issue_title}"'
    github_client._mock_rest_api.search.issues_and_pull_requests.assert_called_once_with(
        q=expected_query, per_page=1
    )

def test_find_issue_by_title_api_error(github_client: GitHubAppClient):
    """Issueタイトル検索: APIエラー"""
    issue_title = "Error Issue"
    mock_error_response = create_mock_response(500)
    mock_api_error = RequestFailed(response=mock_error_response)
    github_client._mock_rest_api.search.issues_and_pull_requests.side_effect = mock_api_error

    with pytest.raises(GitHubClientError, match="Unhandled GitHub API HTTP error"):
        github_client.find_issue_by_title(OWNER, REPO, issue_title)

def test_find_issue_by_title_empty_title(github_client: GitHubAppClient):
    """Issueタイトル検索: タイトルが空文字列"""
    exists = github_client.find_issue_by_title(OWNER, REPO, "")
    assert exists is False
    github_client._mock_rest_api.search.issues_and_pull_requests.assert_not_called()

def test_find_issue_by_title_unexpected_response(github_client: GitHubAppClient):
    """Issueタイトル検索: APIは成功したがレスポンス形式が不正"""
    issue_title = "Weird Response Issue"
    # total_countがないなど、不正なレスポンスデータ
    mock_bad_data = MagicMock()
    # Ensure total_count attribute is missing or None
    if hasattr(mock_bad_data, 'total_count'):
        del mock_bad_data.total_count
    mock_response = create_mock_response(200, parsed_data=mock_bad_data)
    github_client._mock_rest_api.search.issues_and_pull_requests.return_value = mock_response

    with pytest.raises(GitHubClientError, match="Unexpected response format"):
        github_client.find_issue_by_title(OWNER, REPO, issue_title)


# --- Label Method Tests ---
def test_get_label_found(github_client: GitHubAppClient):
    """get_label: ラベルが見つかるケース"""
    label_name = "bug"
    mock_response = create_mock_response(200, parsed_data=MOCK_LABEL_DATA)
    github_client._mock_rest_api.issues.get_label.return_value = mock_response

    label = github_client.get_label(OWNER, REPO, label_name)

    assert label is not None
    assert isinstance(label, Label)
    assert label.name == label_name
    github_client._mock_rest_api.issues.get_label.assert_called_once_with(
        owner=OWNER, repo=REPO, name=label_name)

def test_get_label_not_found(github_client: GitHubAppClient):
    """get_label: ラベルが見つからない (404) ケース"""
    label_name = "nonexistent"
    mock_error_response = create_mock_response(404)
    mock_api_error = RequestFailed(response=mock_error_response)
    github_client._mock_rest_api.issues.get_label.side_effect = mock_api_error

    label = github_client.get_label(OWNER, REPO, label_name)

    assert label is None
    github_client._mock_rest_api.issues.get_label.assert_called_once_with(
        owner=OWNER, repo=REPO, name=label_name)

def test_get_label_api_error(github_client: GitHubAppClient):
    """get_label: その他のAPIエラーが発生するケース (例: 500)"""
    label_name = "error-label"
    mock_error_response = create_mock_response(500)
    mock_api_error = RequestFailed(response=mock_error_response)
    github_client._mock_rest_api.issues.get_label.side_effect = mock_api_error

    with pytest.raises(GitHubClientError, match="Unhandled GitHub API HTTP error"):
        github_client.get_label(OWNER, REPO, label_name)

def test_create_label_success_new(github_client: GitHubAppClient):
    """create_label: 新規ラベル作成が成功するケース"""
    label_name, color, description = "enhancement", "a2eeef", "New feature"
    # get_label は 404 エラーを発生させる
    mock_get_error_response = create_mock_response(404)
    mock_get_api_error = RequestFailed(response=mock_get_error_response)
    github_client._mock_rest_api.issues.get_label.side_effect = mock_get_api_error
    # create_label は成功レスポンス (201) を返す
    mock_created_label = Label(id=2, node_id="L_2", url="", name=label_name, color=color, default=False, description=description)
    mock_create_response = create_mock_response(201, parsed_data=mock_created_label)
    github_client._mock_rest_api.issues.create_label.return_value = mock_create_response

    created = github_client.create_label(
        OWNER, REPO, label_name, color=color, description=description)

    assert created is True
    github_client._mock_rest_api.issues.get_label.assert_called_once_with(
        owner=OWNER, repo=REPO, name=label_name)
    github_client._mock_rest_api.issues.create_label.assert_called_once_with(
        owner=OWNER, repo=REPO, name=label_name, color=color, description=description
    )

def test_create_label_already_exists(github_client: GitHubAppClient):
    """create_label: ラベルが既に存在するケース"""
    label_name = "bug"
    mock_get_response = create_mock_response(200, parsed_data=MOCK_LABEL_DATA)
    github_client._mock_rest_api.issues.get_label.return_value = mock_get_response

    created = github_client.create_label(OWNER, REPO, label_name)

    assert created is False
    github_client._mock_rest_api.issues.get_label.assert_called_once_with(
        owner=OWNER, repo=REPO, name=label_name)
    github_client._mock_rest_api.issues.create_label.assert_not_called()

def test_create_label_creation_fails_validation(github_client: GitHubAppClient):
    """create_label: ラベル作成API呼び出しがバリデーションエラー (422) で失敗"""
    label_name = "invalid:label"
    # get_label は 404 エラー
    mock_get_error_response = create_mock_response(404)
    mock_get_api_error = RequestFailed(response=mock_get_error_response)
    github_client._mock_rest_api.issues.get_label.side_effect = mock_get_api_error
    # create_label は 422 エラー
    mock_create_error_response = create_mock_response(422, content=b'{"message":"Validation Failed"}')
    mock_create_api_error = RequestFailed(response=mock_create_error_response)
    github_client._mock_rest_api.issues.create_label.side_effect = mock_create_api_error

    with pytest.raises(GitHubValidationError, match="Validation failed"):
        github_client.create_label(OWNER, REPO, label_name)

    github_client._mock_rest_api.issues.get_label.assert_called_once_with(
        owner=OWNER, repo=REPO, name=label_name)
    github_client._mock_rest_api.issues.create_label.assert_called_once_with(
        owner=OWNER, repo=REPO, name=label_name)

def test_create_label_get_fails(github_client: GitHubAppClient):
    """create_label: 最初の get_label 呼び出しが失敗"""
    label_name = "some-label"
    mock_get_error_response = create_mock_response(500)
    mock_get_api_error = RequestFailed(response=mock_get_error_response)
    github_client._mock_rest_api.issues.get_label.side_effect = mock_get_api_error

    with pytest.raises(GitHubClientError, match="Unhandled GitHub API HTTP error"):
        github_client.create_label(OWNER, REPO, label_name)

    github_client._mock_rest_api.issues.get_label.assert_called_once_with(
        owner=OWNER, repo=REPO, name=label_name)
    github_client._mock_rest_api.issues.create_label.assert_not_called()

def test_create_label_empty_name(github_client: GitHubAppClient):
    """create_label: ラベル名が空"""
    created = github_client.create_label(OWNER, REPO, "")
    assert created is False
    created_ws = github_client.create_label(OWNER, REPO, "   ") # 空白のみ
    assert created_ws is False
    github_client._mock_rest_api.issues.get_label.assert_not_called()
    github_client._mock_rest_api.issues.create_label.assert_not_called()


# --- Milestone Method Tests ---
def test_find_milestone_by_title_found(github_client: GitHubAppClient):
    """find_milestone_by_title: マイルストーンが見つかるケース"""
    mock_response = create_mock_response(200, parsed_data=[MOCK_MILESTONE_DATA])
    github_client._mock_rest_api.issues.list_milestones.return_value = mock_response

    found_milestone = github_client.find_milestone_by_title(OWNER, REPO, MILESTONE_TITLE)

    assert found_milestone is not None
    assert isinstance(found_milestone, Milestone)
    assert found_milestone.title == MILESTONE_TITLE
    assert found_milestone.number == MILESTONE_ID
    github_client._mock_rest_api.issues.list_milestones.assert_called_once_with(
        owner=OWNER, repo=REPO, state="open", per_page=100
    )

def test_find_milestone_by_title_not_found(github_client: GitHubAppClient):
    """find_milestone_by_title: マイルストーンが見つからないケース"""
    mock_response = create_mock_response(200, parsed_data=[]) # 空リスト
    github_client._mock_rest_api.issues.list_milestones.return_value = mock_response

    found_milestone = github_client.find_milestone_by_title(OWNER, REPO, "NonExistent Title")

    assert found_milestone is None
    github_client._mock_rest_api.issues.list_milestones.assert_called_once()

def test_find_milestone_by_title_api_error(github_client: GitHubAppClient):
    """find_milestone_by_title: APIエラーが発生するケース"""
    mock_error_response = create_mock_response(500)
    mock_api_error = RequestFailed(response=mock_error_response)
    github_client._mock_rest_api.issues.list_milestones.side_effect = mock_api_error

    with pytest.raises(GitHubClientError, match="Unhandled GitHub API HTTP error"):
        github_client.find_milestone_by_title(OWNER, REPO, MILESTONE_TITLE)
    github_client._mock_rest_api.issues.list_milestones.assert_called_once()

def test_find_milestone_by_title_empty_title(github_client: GitHubAppClient):
    """find_milestone_by_title: タイトルが空の場合 None を返す"""
    result = github_client.find_milestone_by_title(OWNER, REPO, "")
    assert result is None
    result_ws = github_client.find_milestone_by_title(OWNER, REPO, "  ") # 空白のみ
    assert result_ws is None
    github_client._mock_rest_api.issues.list_milestones.assert_not_called()


def test_create_milestone_success_new(github_client: GitHubAppClient):
    """create_milestone: 新規マイルストーン作成成功"""
    with patch.object(github_client, 'find_milestone_by_title', return_value=None) as mock_find:
        mock_response = create_mock_response(201, parsed_data=MOCK_MILESTONE_DATA)
        github_client._mock_rest_api.issues.create_milestone.return_value = mock_response

        created_id = github_client.create_milestone(OWNER, REPO, MILESTONE_TITLE, description=MILESTONE_DESCRIPTION)

        assert created_id == MILESTONE_ID
        mock_find.assert_called_once_with(OWNER, REPO, MILESTONE_TITLE, state="open")
        github_client._mock_rest_api.issues.create_milestone.assert_called_once_with(
            owner=OWNER, repo=REPO, title=MILESTONE_TITLE, state="open", description=MILESTONE_DESCRIPTION
        )

def test_create_milestone_already_exists(github_client: GitHubAppClient):
    """create_milestone: 同名の open なマイルストーンが既に存在する場合、既存IDを返す"""
    with patch.object(github_client, 'find_milestone_by_title', return_value=MOCK_MILESTONE_DATA) as mock_find:
        existing_id = github_client.create_milestone(OWNER, REPO, MILESTONE_TITLE)

        assert existing_id == MILESTONE_ID
        mock_find.assert_called_once_with(OWNER, REPO, MILESTONE_TITLE, state="open")
        github_client._mock_rest_api.issues.create_milestone.assert_not_called()

def test_create_milestone_find_api_error(github_client: GitHubAppClient):
    """create_milestone: 最初の find 呼び出しでエラーが発生する場合"""
    mock_error = GitHubClientError("Find Error")
    with patch.object(github_client, 'find_milestone_by_title', side_effect=mock_error) as mock_find:
        with pytest.raises(GitHubClientError, match="Find Error"):
            github_client.create_milestone(OWNER, REPO, MILESTONE_TITLE)

        mock_find.assert_called_once_with(OWNER, REPO, MILESTONE_TITLE, state="open")
        github_client._mock_rest_api.issues.create_milestone.assert_not_called()

def test_create_milestone_create_api_error(github_client: GitHubAppClient):
    """create_milestone: 作成API呼び出しでエラーが発生する場合"""
    mock_create_error_response = create_mock_response(422, content=b'{"message":"Validation Failed"}')
    mock_create_api_error = RequestFailed(response=mock_create_error_response)
    with patch.object(github_client, 'find_milestone_by_title', return_value=None) as mock_find:
        github_client._mock_rest_api.issues.create_milestone.side_effect = mock_create_api_error

        with pytest.raises(GitHubValidationError, match="Validation failed"):
            github_client.create_milestone(OWNER, REPO, "Invalid:Title")

        mock_find.assert_called_once()
        github_client._mock_rest_api.issues.create_milestone.assert_called_once()

def test_create_milestone_empty_title(github_client: GitHubAppClient):
    """create_milestone: タイトルが空の場合 ValueError"""
    with pytest.raises(ValueError, match="cannot be empty or whitespace"):
        github_client.create_milestone(OWNER, REPO, "")
    with pytest.raises(ValueError, match="cannot be empty or whitespace"):
        github_client.create_milestone(OWNER, REPO, "   ")
    # find_milestone_by_title が呼ばれないことを確認
    with patch.object(github_client, 'find_milestone_by_title') as mock_find:
         try:
             github_client.create_milestone(OWNER, REPO, "")
         except ValueError:
             mock_find.assert_not_called()
    github_client._mock_rest_api.issues.create_milestone.assert_not_called()


# --- Issue Creation Tests ---
def test_create_issue_success_basic(github_client: GitHubAppClient):
    """Issue作成成功 (基本ケース、ラベル等なし)"""
    owner, repo, title, body = OWNER, REPO, "Basic Issue", "Body"
    expected_url = f"https://github.com/{owner}/{repo}/issues/1"
    # Issue オブジェクトのモック (html_urlを持つ)
    mock_issue_obj = MagicMock(spec=Issue, html_url=expected_url)
    mock_response = create_mock_response(201, parsed_data=mock_issue_obj)
    github_client._mock_rest_api.issues.create.return_value = mock_response

    created_url = github_client.create_issue(owner, repo, title, body)

    assert created_url == expected_url
    # ペイロードを確認
    github_client._mock_rest_api.issues.create.assert_called_once_with(
        owner=owner, repo=repo, title=title, body=body or ""
        # labels=None などは指定しない
    )

def test_create_issue_success_with_labels(github_client: GitHubAppClient):
    """Issue作成成功 (ラベルあり)"""
    owner, repo, title, body = OWNER, REPO, "Issue with Labels", "Body"
    labels_to_set = ["bug", "ui"]
    expected_url = f"https://github.com/{owner}/{repo}/issues/2"
    mock_issue_obj = MagicMock(spec=Issue, html_url=expected_url)
    mock_response = create_mock_response(201, parsed_data=mock_issue_obj)
    github_client._mock_rest_api.issues.create.return_value = mock_response

    created_url = github_client.create_issue(owner, repo, title, body, labels=labels_to_set)

    assert created_url == expected_url
    github_client._mock_rest_api.issues.create.assert_called_once_with(
        owner=owner, repo=repo, title=title, body=body or "", labels=labels_to_set
    )

def test_create_issue_success_with_assignees(github_client: GitHubAppClient):
    """Issue作成成功 (担当者あり)"""
    owner, repo, title, body = OWNER, REPO, "Issue with Assignees", "Body"
    assignees_to_set = ["user1", "user2"]
    expected_url = f"https://github.com/{owner}/{repo}/issues/3"
    mock_issue_obj = MagicMock(spec=Issue, html_url=expected_url)
    mock_response = create_mock_response(201, parsed_data=mock_issue_obj)
    github_client._mock_rest_api.issues.create.return_value = mock_response

    created_url = github_client.create_issue(owner, repo, title, body, assignees=assignees_to_set)

    assert created_url == expected_url
    github_client._mock_rest_api.issues.create.assert_called_once_with(
        owner=owner, repo=repo, title=title, body=body or "", assignees=assignees_to_set
    )

def test_create_issue_success_with_milestone_id(github_client: GitHubAppClient):
    """Issue作成成功 (マイルストーンID指定)"""
    owner, repo, title, body = OWNER, REPO, "Issue with Milestone ID", "Body"
    milestone_id = 5
    expected_url = f"https://github.com/{owner}/{repo}/issues/4"
    mock_issue_obj = MagicMock(spec=Issue, html_url=expected_url)
    mock_response = create_mock_response(201, parsed_data=mock_issue_obj)
    github_client._mock_rest_api.issues.create.return_value = mock_response

    created_url = github_client.create_issue(owner, repo, title, body, milestone=milestone_id)

    assert created_url == expected_url
    # find_milestone_by_title が呼ばれないことを確認 (直接 ID 指定のため)
    with patch.object(github_client, 'find_milestone_by_title') as mock_find:
         github_client.create_issue(owner, repo, title, body, milestone=milestone_id)
         mock_find.assert_not_called()
    # create API が正しいIDで呼ばれること
    github_client._mock_rest_api.issues.create.assert_called_with(
        owner=owner, repo=repo, title=title, body=body or "", milestone=milestone_id
    )

def test_create_issue_success_with_milestone_title_found(github_client: GitHubAppClient):
    """Issue作成成功 (マイルストーンタイトル指定、ID発見)"""
    owner, repo, title, body = OWNER, REPO, "Issue with Milestone Title Found", "Body"
    expected_url = f"https://github.com/{owner}/{repo}/issues/5"
    mock_issue_obj = MagicMock(spec=Issue, html_url=expected_url)
    mock_response = create_mock_response(201, parsed_data=mock_issue_obj)
    github_client._mock_rest_api.issues.create.return_value = mock_response

    # find_milestone_by_title が成功するようにパッチ
    with patch.object(github_client, 'find_milestone_by_title', return_value=MOCK_MILESTONE_DATA) as mock_find:
        created_url = github_client.create_issue(owner, repo, title, body, milestone=MILESTONE_TITLE)

        assert created_url == expected_url
        # find が呼ばれたことを確認
        mock_find.assert_called_once_with(owner, repo, MILESTONE_TITLE, state="open")
        # create API が見つかったIDで呼ばれたことを確認
        github_client._mock_rest_api.issues.create.assert_called_once_with(
            owner=owner, repo=repo, title=title, body=body or "", milestone=MILESTONE_ID
        )

def test_create_issue_success_with_milestone_title_not_found(github_client: GitHubAppClient, caplog):
    """Issue作成成功 (マイルストーンタイトル指定、ID見つからず)"""
    owner, repo, title, body = OWNER, REPO, "Issue with Milestone Title Not Found", "Body"
    nonexistent_title = "Ghost Milestone"
    expected_url = f"https://github.com/{owner}/{repo}/issues/6"
    mock_issue_obj = MagicMock(spec=Issue, html_url=expected_url)
    mock_response = create_mock_response(201, parsed_data=mock_issue_obj)
    github_client._mock_rest_api.issues.create.return_value = mock_response

    # find_milestone_by_title が None を返すようにパッチ
    with patch.object(github_client, 'find_milestone_by_title', return_value=None) as mock_find:
        with caplog.at_level(logging.WARNING):
            created_url = github_client.create_issue(owner, repo, title, body, milestone=nonexistent_title)

        assert created_url == expected_url
        # find が呼ばれたことを確認
        mock_find.assert_called_once_with(owner, repo, nonexistent_title, state="open")
        # create API が milestone なしで呼ばれたことを確認
        github_client._mock_rest_api.issues.create.assert_called_once_with(
            owner=owner, repo=repo, title=title, body=body or "" # milestone キーなし
        )
        # 警告ログを確認
        assert f"Open milestone with title '{nonexistent_title}' not found" in caplog.text

def test_create_issue_success_with_milestone_title_find_error(github_client: GitHubAppClient, caplog):
    """Issue作成成功 (マイルストーンID検索でエラー)"""
    owner, repo, title, body = OWNER, REPO, "Issue Milestone Find Error", "Body"
    error_title = "Error Prone Milestone"
    expected_url = f"https://github.com/{owner}/{repo}/issues/7"
    mock_find_error = GitHubClientError("Find Milestone API Error")
    mock_issue_obj = MagicMock(spec=Issue, html_url=expected_url)
    mock_response = create_mock_response(201, parsed_data=mock_issue_obj)
    github_client._mock_rest_api.issues.create.return_value = mock_response

    # find_milestone_by_title がエラーを発生させるようにパッチ
    with patch.object(github_client, 'find_milestone_by_title', side_effect=mock_find_error) as mock_find:
        with caplog.at_level(logging.WARNING):
            created_url = github_client.create_issue(owner, repo, title, body, milestone=error_title)

        assert created_url == expected_url
        # find が呼ばれたことを確認
        mock_find.assert_called_once_with(owner, repo, error_title, state="open")
        # create API が milestone なしで呼ばれたことを確認
        github_client._mock_rest_api.issues.create.assert_called_once_with(
            owner=owner, repo=repo, title=title, body=body or "" # milestone キーなし
        )
        # 警告ログを確認
        assert f"Could not find milestone ID for title '{error_title}'" in caplog.text

def test_create_issue_not_found_repo(github_client: GitHubAppClient):
    """Issue作成: リポジトリが見つからない (404)"""
    owner, repo, title, body = OWNER, "not-found-repo", "Issue 404", "Body"
    mock_error_response = create_mock_response(404)
    mock_api_error = RequestFailed(response=mock_error_response)
    github_client._mock_rest_api.issues.create.side_effect = mock_api_error

    with pytest.raises(GitHubResourceNotFoundError, match="resource not found"):
        github_client.create_issue(owner, repo, title, body)

def test_create_issue_validation_error(github_client: GitHubAppClient):
    """Issue作成: バリデーションエラー (422)"""
    owner, repo, title, body = OWNER, REPO, "Issue 422", "Invalid Body"
    mock_error_response = create_mock_response(422, content=b'{"message":"Validation Failed"}')
    mock_api_error = RequestFailed(response=mock_error_response)
    github_client._mock_rest_api.issues.create.side_effect = mock_api_error

    with pytest.raises(GitHubValidationError, match="Validation failed"):
        github_client.create_issue(owner, repo, title, body)

def test_create_issue_empty_title(github_client: GitHubAppClient):
    """Issue作成: タイトルが空"""
    with pytest.raises(ValueError, match="cannot be empty or whitespace"):
        github_client.create_issue(OWNER, REPO, "", "Body")
    with pytest.raises(ValueError, match="cannot be empty or whitespace"):
        github_client.create_issue(OWNER, REPO, "   ", "Body")
    github_client._mock_rest_api.issues.create.assert_not_called()
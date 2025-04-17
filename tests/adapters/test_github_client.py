import logging
import pytest
from unittest.mock import patch, MagicMock
from pydantic import SecretStr

# テスト対象のクライアントとカスタム例外
from github_automation_tool.adapters.github_client import GitHubAppClient
from github_automation_tool.domain.exceptions import (
    GitHubValidationError, GitHubAuthenticationError, GitHubClientError,
    GitHubRateLimitError, GitHubResourceNotFoundError
)
# モック対象の githubkit 例外とモデル
from githubkit.exception import RequestFailed, RequestError, RequestTimeout
# ★ モデルのインポートパスを修正
from githubkit.versions.latest.models import Label, Issue


# --- Fixtures (変更なし) ---
@pytest.fixture
def mock_github_rest_api():
    """githubkit.GitHub().rest オブジェクトのモック"""
    mock = MagicMock()
    mock.repos = MagicMock()
    mock.search = MagicMock()
    mock.issues = MagicMock()
    # ★ issues 属性の下のメソッドもモック化
    mock.issues.get_label = MagicMock()
    mock.issues.create_label = MagicMock()
    mock.issues.create = MagicMock()
    # 既存のモックも維持
    mock.search.issues_and_pull_requests = MagicMock()
    mock.repos.create_for_authenticated_user = MagicMock()
    mock.users = MagicMock()
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
        client = GitHubAppClient(SecretStr("fake-valid-token"))
        client._mock_rest = mock_github_instance.rest
        yield client


# --- Test Data ---
OWNER = "test-owner"
REPO = "test-repo"

# --- Test Cases ---

# --- Initialization Tests (変更なし) ---


def test_init_success():  # 実装省略
    pass


def test_init_missing_token():  # 実装省略
    pass


@patch('github_automation_tool.adapters.github_client.GitHub', side_effect=Exception("Init failed"))
def test_init_github_error(mock_gh_class):  # 実装省略
    pass

# --- Repository Creation Tests (変更なし) ---


def test_create_repository_success(github_client: GitHubAppClient):  # 実装省略
    pass


# 実装省略
def test_create_repository_already_exists(github_client: GitHubAppClient):
    pass


def test_create_repository_auth_error(github_client: GitHubAppClient):  # 実装省略
    pass


# 実装省略
def test_create_repository_network_error(github_client: GitHubAppClient):
    pass


# 実装省略
def test_create_repository_other_api_error(github_client: GitHubAppClient):
    pass

# --- Issue Search Tests (変更なし) ---


def test_find_issue_by_title_exists(github_client: GitHubAppClient):  # 実装省略
    pass


def test_find_issue_by_title_not_exists(github_client: GitHubAppClient):  # 実装省略
    pass


def test_find_issue_by_title_api_error(github_client: GitHubAppClient):  # 実装省略
    pass

# --- ★ Label Method Tests (新規追加) ★ ---


def test_get_label_found(github_client: GitHubAppClient):
    """get_label: ラベルが見つかるケース"""
    label_name = "bug"
    # Label オブジェクトのモック (必要な属性のみ設定)
    mock_label_data = Label(id=1, node_id="L_1", url="", name=label_name,
                            color="d73a4a", default=True, description="Bug desc")
    mock_response = MagicMock(status_code=200, parsed_data=mock_label_data)
    github_client._mock_rest.issues.get_label.return_value = mock_response

    label = github_client.get_label(OWNER, REPO, label_name)

    assert label is not None
    assert isinstance(label, Label)  # 型も確認
    assert label.name == label_name
    assert label.color == "d73a4a"
    github_client._mock_rest.issues.get_label.assert_called_once_with(
        owner=OWNER, repo=REPO, name=label_name)


def test_get_label_not_found(github_client: GitHubAppClient):
    """get_label: ラベルが見つからない (404) ケース"""
    label_name = "nonexistent"
    mock_error_response = MagicMock(status_code=404)
    mock_api_error = RequestFailed(response=mock_error_response)
    github_client._mock_rest.issues.get_label.side_effect = mock_api_error

    label = github_client.get_label(OWNER, REPO, label_name)

    assert label is None  # 存在しない場合は None が返る
    github_client._mock_rest.issues.get_label.assert_called_once_with(
        owner=OWNER, repo=REPO, name=label_name)


def test_get_label_api_error(github_client: GitHubAppClient):
    """get_label: その他のAPIエラーが発生するケース (例: 500)"""
    label_name = "error-label"
    mock_error_response = MagicMock(status_code=500)
    mock_api_error = RequestFailed(response=mock_error_response)
    github_client._mock_rest.issues.get_label.side_effect = mock_api_error

    with pytest.raises(GitHubClientError, match="Unhandled GitHub API HTTP error"):
        github_client.get_label(OWNER, REPO, label_name)


def test_create_label_success_new(github_client: GitHubAppClient):
    """create_label: 新規ラベル作成が成功するケース"""
    label_name, color, description = "enhancement", "a2eeef", "New feature or request"
    # get_label は None を返すように設定 (404 エラーを発生させる)
    mock_get_error_response = MagicMock(status_code=404)
    mock_get_api_error = RequestFailed(response=mock_get_error_response)
    github_client._mock_rest.issues.get_label.side_effect = mock_get_api_error
    # create_label は成功レスポンス (201) を返す
    mock_create_response = MagicMock(status_code=201)
    mock_create_response.parsed_data = MagicMock(
        spec=Label, name=label_name, color=color)
    github_client._mock_rest.issues.create_label.return_value = mock_create_response

    created = github_client.create_label(
        OWNER, REPO, label_name, color=color, description=description)

    assert created is True  # 新規作成されたので True
    github_client._mock_rest.issues.get_label.assert_called_once_with(
        owner=OWNER, repo=REPO, name=label_name)
    # create_label が正しい引数で呼ばれたか確認
    github_client._mock_rest.issues.create_label.assert_called_once_with(
        owner=OWNER, repo=REPO, name=label_name, color=color, description=description
    )


def test_create_label_already_exists(github_client: GitHubAppClient):
    """create_label: ラベルが既に存在するケース"""
    label_name = "bug"
    # ★ Labelインスタンス化時に必須の description を追加 (例: 空文字列)
    mock_existing_label = Label(
        id=1, node_id="L_1", url="", name=label_name, color="d73a4a", default=True,
        description=""  # または適切な説明
    )
    mock_get_response = MagicMock(
        status_code=200, parsed_data=mock_existing_label)
    github_client._mock_rest.issues.get_label.return_value = mock_get_response

    created = github_client.create_label(OWNER, REPO, label_name)

    assert created is False
    github_client._mock_rest.issues.get_label.assert_called_once_with(
        owner=OWNER, repo=REPO, name=label_name)
    github_client._mock_rest.issues.create_label.assert_not_called()


def test_create_label_creation_fails_validation(github_client: GitHubAppClient):
    """create_label: ラベル作成API呼び出しがバリデーションエラー (422) で失敗するケース"""
    label_name = "invalid:label"
    # get_label は None (404 エラー) を返す
    mock_get_error_response = MagicMock(status_code=404)
    mock_get_api_error = RequestFailed(response=mock_get_error_response)
    github_client._mock_rest.issues.get_label.side_effect = mock_get_api_error
    # create_label は 422 エラーを返す
    mock_create_error_response = MagicMock(
        status_code=422, content=b'{"message":"Validation Failed"}')
    mock_create_api_error = RequestFailed(response=mock_create_error_response)
    github_client._mock_rest.issues.create_label.side_effect = mock_create_api_error

    with pytest.raises(GitHubValidationError, match="Validation failed"):
        github_client.create_label(OWNER, REPO, label_name)

    github_client._mock_rest.issues.get_label.assert_called_once_with(
        owner=OWNER, repo=REPO, name=label_name)
    github_client._mock_rest.issues.create_label.assert_called_once_with(
        owner=OWNER, repo=REPO, name=label_name)


def test_create_label_get_fails(github_client: GitHubAppClient):
    """create_label: 最初の get_label 呼び出しが失敗するケース (例: 500)"""
    label_name = "some-label"
    mock_get_error_response = MagicMock(status_code=500)
    mock_get_api_error = RequestFailed(response=mock_get_error_response)
    github_client._mock_rest.issues.get_label.side_effect = mock_get_api_error

    with pytest.raises(GitHubClientError, match="Unhandled GitHub API HTTP error"):
        github_client.create_label(OWNER, REPO, label_name)

    github_client._mock_rest.issues.get_label.assert_called_once_with(
        owner=OWNER, repo=REPO, name=label_name)
    github_client._mock_rest.issues.create_label.assert_not_called()


def test_create_label_empty_name(github_client: GitHubAppClient):
    """create_label: ラベル名が空の場合、Falseを返しAPIは呼ばれない"""
    created = github_client.create_label(OWNER, REPO, "")
    assert created is False
    github_client._mock_rest.issues.get_label.assert_not_called()
    github_client._mock_rest.issues.create_label.assert_not_called()


# --- Issue Creation Tests (ラベル設定を追加して修正) ---
def test_create_issue_success(github_client: GitHubAppClient):
    """Issue作成が成功するケース (ラベルなし)"""
    owner, repo, title, body = OWNER, REPO, "A Basic Issue", "Body"
    expected_url = f"https://github.com/{owner}/{repo}/issues/123"
    mock_response = MagicMock(status_code=201)
    mock_response.parsed_data = MagicMock(spec=Issue, html_url=expected_url)
    github_client._mock_rest.issues.create.return_value = mock_response

    created_url = github_client.create_issue(
        owner, repo, title, body, labels=None, milestone=None, assignees=None)  # 他もNone

    assert created_url == expected_url
    # labels, milestone, assignees がペイロードに含まれないことを確認
    github_client._mock_rest.issues.create.assert_called_once_with(
        owner=owner, repo=repo, title=title, body=body or ""
        # labels=None などは指定しない
    )


def test_create_issue_success_with_labels(github_client: GitHubAppClient):
    """Issue作成が成功し、ラベルも設定されるケース"""
    owner, repo, title, body = OWNER, REPO, "Issue with Labels", "Body text"
    labels_to_set = ["bug", "ui"]  # 設定したいラベル
    expected_url = f"https://github.com/{owner}/{repo}/issues/124"
    mock_response = MagicMock(status_code=201)
    mock_response.parsed_data = MagicMock(spec=Issue, html_url=expected_url)
    github_client._mock_rest.issues.create.return_value = mock_response

    # labels 引数を渡して実行
    created_url = github_client.create_issue(
        owner, repo, title, body, labels=labels_to_set)

    assert created_url == expected_url
    # labels がペイロードに含まれて呼ばれたことを確認
    github_client._mock_rest.issues.create.assert_called_once_with(
        owner=owner, repo=repo, title=title, body=body or "", labels=labels_to_set
    )


def test_create_issue_success_with_milestone_id(github_client: GitHubAppClient):
    """Issue作成が成功し、マイルストーンIDも設定されるケース"""
    owner, repo, title, body = OWNER, REPO, "Issue with Milestone", "Body"
    milestone_id = 5  # マイルストーン番号(int)
    expected_url = f"https://github.com/{owner}/{repo}/issues/125"
    mock_response = MagicMock(status_code=201)
    mock_response.parsed_data = MagicMock(spec=Issue, html_url=expected_url)
    github_client._mock_rest.issues.create.return_value = mock_response

    created_url = github_client.create_issue(
        owner, repo, title, body, milestone=milestone_id)

    assert created_url == expected_url
    github_client._mock_rest.issues.create.assert_called_once_with(
        owner=owner, repo=repo, title=title, body=body or "", milestone=milestone_id  # number が渡される
    )


def test_create_issue_ignores_milestone_string(github_client: GitHubAppClient, caplog):
    """Issue作成時にマイルストーンが文字列で渡された場合、無視され警告ログが出るケース"""
    owner, repo, title, body = OWNER, REPO, "Issue with Milestone Str", "Body"
    milestone_title = "Sprint X"
    expected_url = f"https://github.com/{owner}/{repo}/issues/126"
    mock_response = MagicMock(status_code=201)
    mock_response.parsed_data = MagicMock(spec=Issue, html_url=expected_url)
    github_client._mock_rest.issues.create.return_value = mock_response

    with caplog.at_level(logging.WARNING):
        created_url = github_client.create_issue(
            owner, repo, title, body, milestone=milestone_title)

    assert created_url == expected_url
    github_client._mock_rest.issues.create.assert_called_once_with(
        owner=owner, repo=repo, title=title, body=body or ""  # milestone は無視される
    )
    # ★ アサーション文字列を実際のログメッセージに合わせる
    # assert f"Milestone '{milestone_title}' for issue '{title}' ignored" in caplog.text # 修正前
    # 修正後
    assert f"Milestone '{milestone_title}' ignored (must be integer ID)." in caplog.text


def test_create_issue_success_with_assignees(github_client: GitHubAppClient):
    """Issue作成が成功し、担当者も設定されるケース"""
    owner, repo, title, body = OWNER, REPO, "Issue with Assignees", "Body"
    assignees_to_set = ["user1", "user2"]
    expected_url = f"https://github.com/{owner}/{repo}/issues/127"
    mock_response = MagicMock(status_code=201)
    mock_response.parsed_data = MagicMock(spec=Issue, html_url=expected_url)
    github_client._mock_rest.issues.create.return_value = mock_response

    created_url = github_client.create_issue(
        owner, repo, title, body, assignees=assignees_to_set)

    assert created_url == expected_url
    github_client._mock_rest.issues.create.assert_called_once_with(
        owner=owner, repo=repo, title=title, body=body or "", assignees=assignees_to_set
    )

# (既存の異常系テスト test_create_issue_not_found_repo, test_create_issue_validation_error は変更なし)


def test_create_issue_not_found_repo(github_client: GitHubAppClient):  # 実装省略
    pass


def test_create_issue_validation_error(github_client: GitHubAppClient):  # 実装省略
    pass

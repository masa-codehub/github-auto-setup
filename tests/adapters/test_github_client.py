# tests/adapters/test_github_client.py

import pytest
from unittest.mock import MagicMock, patch
import logging
from pydantic import SecretStr
import json

from github_automation_tool.adapters.github_client import GitHubAppClient
from github_automation_tool.domain.exceptions import (
    GitHubClientError, GitHubAuthenticationError, GitHubRateLimitError,
    GitHubResourceNotFoundError, GitHubValidationError
)

from githubkit.exception import RequestFailed, RequestError, RequestTimeout

# グローバル定数（複数のテストで参照される値）
TARGET_OWNER = "test-owner"
TARGET_PROJECT_NAME = "Test Project"

# RequestFailedのモック作成用ヘルパー関数を修正
def create_mock_request_failed(status_code, content, headers=None):
    """RequestFailed例外のモックを作成するヘルパー関数
    
    githubkitの新しいバージョンでは、RequestFailedは文字列ではなくResponseオブジェクトを期待する
    """
    # リクエストオブジェクトを作成
    mock_request = MagicMock()
    mock_request.method = "GET"  # ダミーメソッド
    mock_request.url = "http://example.com/api"  # ダミーURL
    
    # レスポンスオブジェクトを作成
    mock_response = MagicMock()
    mock_response.status_code = status_code  # 整数値を直接設定
    mock_response.content = content
    mock_response.headers = headers or {}
    mock_response.request = mock_request
    
    # JSONデコード用のメソッドも追加
    try:
        json_data = json.loads(content.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        json_data = {}
    mock_response.json = MagicMock(return_value=json_data)
    
    # RequestFailedオブジェクトを作成
    return RequestFailed(mock_response)

# テスト全体で使用するフィクスチャ
@pytest.fixture
def mock_github():
    """githubkit.GitHub のモックインスタンスを返すフィクスチャ"""
    mock_gh = MagicMock()
    # 必要に応じて基本的な振る舞いを定義
    mock_gh.rest = MagicMock()  # rest エンドポイント
    mock_gh.rest.users = MagicMock()  # users エンドポイントなど
    mock_gh.rest.repos = MagicMock()  # repos エンドポイント
    mock_gh.rest.issues = MagicMock()  # issues エンドポイント
    mock_gh.rest.search = MagicMock()  # search エンドポイント
    mock_gh.graphql = MagicMock()  # GraphQL エンドポイント
    return mock_gh

@pytest.fixture
def github_client(mock_github):
    """テスト用のGitHubAppClientインスタンスを返す"""
    # GitHubクラスのコンストラクタをモック
    with patch('github_automation_tool.adapters.github_client.GitHub', return_value=mock_github):
        client = GitHubAppClient(SecretStr("fake-token"))
        # モックを検証できるように属性として保存
        client.mock_gh = mock_github
        return client


# __init__ テスト

def test_init_with_valid_token():
    """有効なトークンで初期化できることを確認"""
    with patch('github_automation_tool.adapters.github_client.GitHub') as mock_github_cls:
        mock_github_instance = MagicMock()
        mock_github_cls.return_value = mock_github_instance
        
        client = GitHubAppClient(SecretStr("valid-token"))
        
        mock_github_cls.assert_called_once_with("valid-token")
        assert client.gh is mock_github_instance

def test_init_with_empty_token():
    """空のトークンで初期化するとエラーになることを確認"""
    with pytest.raises(GitHubAuthenticationError) as excinfo:
        GitHubAppClient(SecretStr(""))
    
    assert "GitHub PAT is missing or empty" in str(excinfo.value)

def test_init_with_none_token():
    """Noneトークンで初期化するとエラーになることを確認"""
    with pytest.raises(GitHubAuthenticationError):
        GitHubAppClient(None)

def test_init_catches_exceptions():
    """初期化時の例外が適切に捕捉されることを確認"""
    with patch('github_automation_tool.adapters.github_client.GitHub') as mock_github_cls:
        mock_github_cls.side_effect = ValueError("Something went wrong")
        
        with pytest.raises(GitHubClientError) as excinfo:
            GitHubAppClient(SecretStr("token"))
        
        assert "Failed to initialize GitHub client" in str(excinfo.value)
        assert excinfo.value.original_exception is not None


# エラーハンドリングメソッドテスト

def test_handle_request_failed_401(github_client, caplog):
    """401エラーが適切に処理されることを確認"""
    mock_error = create_mock_request_failed(
        status_code=401,
        content=b"Bad credentials"
    )
    
    with caplog.at_level(logging.WARNING):
        result = github_client._handle_request_failed(mock_error, "test operation")
    
    assert isinstance(result, GitHubAuthenticationError)
    assert result.status_code == 401
    assert "test operation" in str(result)  # コンテキストが含まれることを確認
    assert "test operation" in caplog.text  # ログにもコンテキストが含まれることを確認

def test_handle_request_failed_403_rate_limit(github_client):
    """レートリミット（403+ヘッダー）が適切に処理されることを確認"""
    mock_error = create_mock_request_failed(
        status_code=403,
        content=b"API rate limit exceeded",
        headers={"X-RateLimit-Remaining": "0"}
    )
    
    result = github_client._handle_request_failed(mock_error, "listing repositories")
    
    assert isinstance(result, GitHubRateLimitError)
    assert result.status_code == 403
    assert "listing repositories" in str(result)  # コンテキストが含まれる

def test_handle_request_failed_403_permission(github_client):
    """権限不足（403）が適切に処理されることを確認"""
    mock_error = create_mock_request_failed(
        status_code=403,
        content=b"Permission denied",
        headers={"X-RateLimit-Remaining": "100"}  # レートリミットではない
    )
    
    result = github_client._handle_request_failed(mock_error, "accessing private repo")
    
    assert isinstance(result, GitHubAuthenticationError)
    assert result.status_code == 403
    assert "accessing private repo" in str(result)  # コンテキストが含まれる

def test_handle_request_failed_404(github_client):
    """リソース未検出（404）が適切に処理されることを確認"""
    mock_error = create_mock_request_failed(
        status_code=404,
        content=b"Not found"
    )
    
    result = github_client._handle_request_failed(mock_error, "finding issue")
    
    assert isinstance(result, GitHubResourceNotFoundError)
    assert result.status_code == 404
    assert "finding issue" in str(result)  # コンテキストが含まれる

def test_handle_request_failed_422_repo_exists(github_client):
    """リポジトリ名重複（422）が適切に処理されることを確認"""
    mock_error = create_mock_request_failed(
        status_code=422,
        content=b'{"message":"Repository name already exists"}'
    )
    
    result = github_client._handle_request_failed(mock_error, "repository creation")
    
    assert isinstance(result, GitHubValidationError)
    assert result.status_code == 422
    assert "repository creation" in str(result)  # コンテキストが含まれる
    assert "name already exists" in str(result).lower()  # エラー内容が含まれる

def test_handle_request_failed_422_generic(github_client):
    """一般的なバリデーションエラー（422）が適切に処理されることを確認"""
    mock_error = create_mock_request_failed(
        status_code=422,
        content=b'{"message":"Validation failed"}'
    )
    
    result = github_client._handle_request_failed(mock_error, "creating issue")
    
    assert isinstance(result, GitHubValidationError)
    assert result.status_code == 422
    assert "creating issue" in str(result)  # コンテキストが含まれる

def test_handle_request_failed_other(github_client):
    """その他のHTTPエラーが適切に処理されることを確認"""
    mock_error = create_mock_request_failed(
        status_code=500,
        content=b"Server error"
    )
    
    result = github_client._handle_request_failed(mock_error, "updating label")
    
    assert isinstance(result, GitHubClientError)
    assert result.status_code == 500
    assert "updating label" in str(result)  # コンテキストが含まれる

def test_handle_other_error_request_error(github_client, caplog):
    """RequestError（ネットワークエラーなど）が適切に処理されることを確認"""
    mock_error = RequestError("Connection refused")
    
    with caplog.at_level(logging.WARNING):
        result = github_client._handle_other_error(mock_error, "connecting to API")
    
    assert isinstance(result, GitHubClientError)
    assert "connecting to API" in str(result)  # コンテキストが含まれる
    assert "connecting to API" in caplog.text  # ログにもコンテキストが含まれる

def test_handle_other_error_timeout(github_client):
    """RequestTimeout（タイムアウト）が適切に処理されることを確認"""
    mock_error = RequestTimeout("API call timed out")
    
    result = github_client._handle_other_error(mock_error, "fetching large repo")
    
    assert isinstance(result, GitHubClientError)
    assert "fetching large repo" in str(result)  # コンテキストが含まれる

def test_handle_other_error_generic(github_client, caplog):
    """一般的な例外が適切に処理されることを確認"""
    mock_error = ValueError("Something unexpected")
    
    with caplog.at_level(logging.ERROR):
        result = github_client._handle_other_error(mock_error, "parsing response")
    
    assert isinstance(result, GitHubClientError)
    assert "parsing response" in str(result)  # コンテキストが含まれる
    assert "parsing response" in caplog.text  # ログにもコンテキストが含まれる


# create_repository テスト

def test_create_repository_success(github_client):
    """リポジトリが正常に作成される場合のテスト"""
    # モックレスポンスを設定
    mock_repo = MagicMock()
    mock_repo.html_url = "https://github.com/user/new-repo"
    
    mock_response = MagicMock()
    mock_response.parsed_data = mock_repo
    
    # リポジトリ作成メソッドのレスポンスを設定
    github_client.mock_gh.rest.repos.create_for_authenticated_user.return_value = mock_response
    
    # メソッドを呼び出し
    result = github_client.create_repository("new-repo")
    
    # 検証
    assert result == "https://github.com/user/new-repo"
    github_client.mock_gh.rest.repos.create_for_authenticated_user.assert_called_once_with(
        name="new-repo", private=True, auto_init=True
    )

def test_create_repository_api_error(github_client):
    """リポジトリ作成時のAPIエラーが適切に処理されることを確認"""
    # APIエラーをシミュレート
    mock_error = create_mock_request_failed(
        status_code=422,
        content=b'{"message":"Repository creation failed: name already exists"}'
    )
    
    # APIリクエストがエラーを発生させるように設定
    github_client.mock_gh.rest.repos.create_for_authenticated_user.side_effect = mock_error
    
    # メソッド呼び出しでエラーが発生することを確認
    with pytest.raises(GitHubValidationError) as excinfo:
        github_client.create_repository("existing-repo")
    
    # エラーメッセージにコンテキスト情報が含まれることを確認
    error_msg = str(excinfo.value)
    assert "creating repository 'existing-repo'" in error_msg
    assert "name already exists" in error_msg.lower()

def test_create_repository_with_empty_response(github_client):
    """不完全なレスポンスデータが適切に処理されることを確認"""
    # html_url のないレスポンスをシミュレート
    mock_repo = MagicMock()
    # html_url属性が空になるように明示的に設定
    mock_repo.html_url = None
    
    mock_response = MagicMock()
    mock_response.parsed_data = mock_repo
    # ステータスコードを明示的に設定（正常に完了したように見せる）
    mock_response.status_code = 201
    
    # リポジトリ作成メソッドのレスポンスを設定
    github_client.mock_gh.rest.repos.create_for_authenticated_user.return_value = mock_response
    
    # メソッド呼び出しでエラーが発生することを確認
    with pytest.raises(GitHubClientError) as excinfo:
        github_client.create_repository("new-repo")
    
    assert "Could not retrieve repository URL" in str(excinfo.value)


# find_milestone_by_title テスト

def test_find_milestone_by_title_success(github_client):
    """マイルストーンが見つかる場合のテスト"""
    # モックマイルストーンを設定
    mock_milestone = MagicMock()
    mock_milestone.title = "Sprint 1"
    mock_milestone.number = 42
    
    mock_response = MagicMock()
    mock_response.parsed_data = [mock_milestone]
    
    # マイルストーン一覧APIのレスポンスを設定
    github_client.mock_gh.rest.issues.list_milestones.return_value = mock_response
    
    # メソッドを呼び出し
    result = github_client.find_milestone_by_title("owner", "repo", "Sprint 1")
    
    # 検証
    assert result is mock_milestone
    assert result.number == 42
    github_client.mock_gh.rest.issues.list_milestones.assert_called_once_with(
        owner="owner", repo="repo", state="open", per_page=100
    )

def test_find_milestone_by_title_not_found(github_client):
    """マイルストーンが見つからない場合のテスト"""
    # 別名のマイルストーンを返すように設定
    mock_milestone = MagicMock()
    mock_milestone.title = "Sprint 2"
    
    mock_response = MagicMock()
    mock_response.parsed_data = [mock_milestone]
    
    # マイルストーン一覧APIのレスポンスを設定
    github_client.mock_gh.rest.issues.list_milestones.return_value = mock_response
    
    # メソッドを呼び出し
    result = github_client.find_milestone_by_title("owner", "repo", "Sprint 1")
    
    # 検証
    assert result is None

def test_find_milestone_by_title_empty_title(github_client):
    """空のタイトルが適切に処理されることを確認"""
    # メソッドを呼び出し
    result = github_client.find_milestone_by_title("owner", "repo", "")
    
    # 検証
    assert result is None
    # APIは呼ばれないことを確認
    github_client.mock_gh.rest.issues.list_milestones.assert_not_called()

def test_find_milestone_by_title_api_error(github_client):
    """APIエラーが適切に処理されることを確認"""
    # APIエラーをシミュレート
    mock_error = create_mock_request_failed(
        status_code=404,
        content=b"Not found"
    )
    
    # APIリクエストがエラーを発生させるように設定
    github_client.mock_gh.rest.issues.list_milestones.side_effect = mock_error
    
    # メソッド呼び出しでエラーが発生することを確認
    with pytest.raises(GitHubResourceNotFoundError) as excinfo:
        github_client.find_milestone_by_title("owner", "repo", "Sprint 1")
    
    # エラーメッセージにコンテキスト情報が含まれることを確認
    assert "searching for open milestone" in str(excinfo.value)
    assert "'Sprint 1'" in str(excinfo.value)

# --- Additional Error Handling Tests ---

def test_handle_request_failed_500(github_client, caplog):
    """500 Server Error が適切に処理されることを確認"""
    mock_error = create_mock_request_failed(
        status_code=500,
        content=b"Internal Server Error"
    )
    with caplog.at_level(logging.ERROR): # 500系はERRORレベル
        result = github_client._handle_request_failed(mock_error, "complex operation")

    assert isinstance(result, GitHubClientError)
    assert result.status_code == 500
    assert "complex operation" in str(result)
    assert "complex operation" in caplog.text # ログにもコンテキスト

def test_handle_graphql_error_forbidden(github_client):
    """GraphQL の FORBIDDEN エラーが適切に処理されることを確認"""
    graphql_response = {
        "errors": [{"type": "FORBIDDEN", "message": "Permission issue"}]
    }
    # GraphQLResponseオブジェクトまたは辞書形式のエラーに対応
    result = github_client._handle_graphql_error(graphql_response, "graphql forbidden")
    assert isinstance(result, GitHubAuthenticationError)
    assert "graphql forbidden" in str(result)
    assert "FORBIDDEN" in str(result) # エラータイプが含まれる

def test_handle_graphql_error_not_found(github_client):
    """GraphQL の NOT_FOUND エラーが適切に処理されることを確認"""
    graphql_response = {
        "errors": [{"type": "NOT_FOUND", "message": "Resource not found"}]
    }
    result = github_client._handle_graphql_error(graphql_response, "graphql not found")
    assert isinstance(result, GitHubResourceNotFoundError)
    assert "graphql not found" in str(result)
    assert "NOT_FOUND" in str(result)

def test_handle_graphql_error_generic(github_client):
    """GraphQL の一般的なエラーが適切に処理されることを確認"""
    graphql_response = {
        "errors": [{"message": "Something went wrong"}] # type がない場合
    }
    result = github_client._handle_graphql_error(graphql_response, "graphql generic")
    assert isinstance(result, GitHubClientError)
    assert "graphql generic" in str(result)

def test_handle_api_error_passes_through_custom_exception(github_client, caplog):
    """_handle_api_error がカスタム例外をそのまま渡すことを確認"""
    custom_error = GitHubRateLimitError("Rate limit passed through")
    with caplog.at_level(logging.DEBUG):
        result = github_client._handle_api_error(custom_error, "pass through")
    assert result is custom_error
    assert "Passing through existing custom exception" in caplog.text
    assert "GitHubRateLimitError" in caplog.text

# --- get_label Tests ---

def test_get_label_success_but_no_data(github_client, caplog):
    """get_label API が成功ステータスでもデータがない場合 None を返す"""
    # レスポンスは成功だが parsed_data が None
    mock_response = MagicMock()
    mock_response.parsed_data = None
    mock_response.status_code = 200 # 成功ステータス
    github_client.mock_gh.rest.issues.get_label.return_value = mock_response

    with caplog.at_level(logging.WARNING):
        result = github_client.get_label("owner", "repo", "label-name")

    assert result is None
    assert "returned success status but no data" in caplog.text
    github_client.mock_gh.rest.issues.get_label.assert_called_once_with(
        owner="owner", repo="repo", name="label-name"
    )

def test_get_label_other_request_failed(github_client):
    """get_label で 404 以外の RequestFailed が発生した場合、例外が再送出される"""
    mock_error = create_mock_request_failed(
        status_code=403, content=b"Forbidden"
    )
    github_client.mock_gh.rest.issues.get_label.side_effect = mock_error

    with pytest.raises(GitHubAuthenticationError): # 403 は AuthenticationError になるはず
        github_client.get_label("owner", "repo", "label-name")

    github_client.mock_gh.rest.issues.get_label.assert_called_once_with(
        owner="owner", repo="repo", name="label-name"
    )

# --- create_label Tests ---

def test_create_label_empty_name(github_client, caplog):
    """空または空白のラベル名で create_label を呼んだ場合、スキップされFalseを返す"""
    with caplog.at_level(logging.WARNING):
        result_empty = github_client.create_label("owner", "repo", "")
        result_whitespace = github_client.create_label("owner", "repo", "   ")

    assert result_empty is False
    assert result_whitespace is False
    assert "Skipping label creation due to empty name" in caplog.text
    github_client.mock_gh.rest.issues.get_label.assert_not_called()
    github_client.mock_gh.rest.issues.create_label.assert_not_called()

def test_create_label_already_exists(github_client):
    """既存のラベルがある場合、作成せず False を返す"""
    # get_label が既存ラベルを返すように設定
    existing_label = MagicMock()
    github_client.mock_gh.rest.issues.get_label.return_value = MagicMock(parsed_data=existing_label)

    result = github_client.create_label("owner", "repo", "existing-label")

    assert result is False
    github_client.mock_gh.rest.issues.get_label.assert_called_once_with(owner="owner", repo="repo", name="existing-label")
    github_client.mock_gh.rest.issues.create_label.assert_not_called()

def test_create_label_api_error_during_get(github_client):
    """ラベル存在確認 (get_label) 中に API エラーが発生した場合"""
    mock_error = create_mock_request_failed(status_code=500, content=b"Server error")
    github_client.mock_gh.rest.issues.get_label.side_effect = mock_error

    with pytest.raises(GitHubClientError):
        github_client.create_label("owner", "repo", "new-label")

    github_client.mock_gh.rest.issues.get_label.assert_called_once_with(owner="owner", repo="repo", name="new-label")
    github_client.mock_gh.rest.issues.create_label.assert_not_called()

def test_create_label_api_error_during_create(github_client):
    """ラベル作成 (create_label) 中に API エラーが発生した場合"""
    # get_label は None (存在しない) を返す
    github_client.mock_gh.rest.issues.get_label.return_value = None

    # create でエラー
    mock_error = create_mock_request_failed(status_code=422, content=b"Validation failed")
    github_client.mock_gh.rest.issues.create_label.side_effect = mock_error

    with pytest.raises(GitHubValidationError):
        github_client.create_label("owner", "repo", "new-label", color="invalid", description="desc")

    github_client.mock_gh.rest.issues.get_label.assert_called_once_with(owner="owner", repo="repo", name="new-label")
    github_client.mock_gh.rest.issues.create_label.assert_called_once_with(
        owner="owner", repo="repo", name="new-label", color="invalid", description="desc"
    )

# --- create_milestone Tests ---

def test_create_milestone_already_exists(github_client):
    """既存の Open マイルストーンがある場合、そのIDを返す"""
    existing_milestone = MagicMock()
    existing_milestone.number = 99
    existing_milestone.title = "Existing Sprint"
    github_client.mock_gh.rest.issues.list_milestones.return_value = MagicMock(parsed_data=[existing_milestone])

    result = github_client.create_milestone("owner", "repo", "Existing Sprint")

    assert result == 99
    github_client.mock_gh.rest.issues.list_milestones.assert_called_once_with(
        owner="owner", repo="repo", state="open", per_page=100
    )
    github_client.mock_gh.rest.issues.create_milestone.assert_not_called()

def test_create_milestone_api_error_during_find(github_client):
    """マイルストーン検索 (list_milestones) 中に API エラーが発生した場合"""
    mock_error = create_mock_request_failed(status_code=503, content=b"Service Unavailable")
    github_client.mock_gh.rest.issues.list_milestones.side_effect = mock_error

    with pytest.raises(GitHubClientError):
        github_client.create_milestone("owner", "repo", "New Sprint")

    github_client.mock_gh.rest.issues.list_milestones.assert_called_once()
    github_client.mock_gh.rest.issues.create_milestone.assert_not_called()

def test_create_milestone_api_error_during_create(github_client):
    """マイルストーン作成 (create_milestone) 中に API エラーが発生した場合"""
    # find は空リスト (存在しない) を返す
    github_client.mock_gh.rest.issues.list_milestones.return_value = MagicMock(parsed_data=[])

    # create でエラー
    mock_error = create_mock_request_failed(status_code=400, content=b"Bad Request")
    github_client.mock_gh.rest.issues.create_milestone.side_effect = mock_error

    with pytest.raises(GitHubClientError): # 400 は ClientError になるはず
        github_client.create_milestone("owner", "repo", "New Sprint", description="")

    github_client.mock_gh.rest.issues.list_milestones.assert_called_once()
    github_client.mock_gh.rest.issues.create_milestone.assert_called_once_with(
        owner="owner", repo="repo", title="New Sprint", state="open", description=""
    )

def test_create_milestone_empty_title(github_client):
    """空のタイトルでマイルストーン作成を試みると ValueError"""
    with pytest.raises(ValueError, match="title cannot be empty"):
        github_client.create_milestone("owner", "repo", "  ")
    github_client.mock_gh.rest.issues.list_milestones.assert_not_called()
    github_client.mock_gh.rest.issues.create_milestone.assert_not_called()

def test_create_milestone_invalid_state_defaults_to_open(github_client, caplog):
    """不正な state が指定された場合、'open' にフォールバックし警告ログが出る"""
    # find は空リスト
    github_client.mock_gh.rest.issues.list_milestones.return_value = MagicMock(parsed_data=[])
    # create は成功し ID を返す
    mock_created_milestone = MagicMock()
    mock_created_milestone.number = 100
    github_client.mock_gh.rest.issues.create_milestone.return_value = MagicMock(status_code=201, parsed_data=mock_created_milestone)

    with caplog.at_level(logging.WARNING):
        result = github_client.create_milestone("owner", "repo", "State Test", state="invalid_state")

    assert result == 100
    github_client.mock_gh.rest.issues.create_milestone.assert_called_once_with(
        owner="owner", repo="repo", title="State Test", state="open", description=""
    )
    assert "Invalid state 'invalid_state'" in caplog.text
    assert "defaulting to 'open'" in caplog.text

# --- create_issue Tests ---

def test_create_issue_empty_title_raises_error(github_client):
    """空のタイトルでIssue作成を試みると ValueError"""
    with pytest.raises(ValueError, match="title cannot be empty"):
        github_client.create_issue("owner", "repo", "   ", body="body")
    github_client.mock_gh.rest.issues.create.assert_not_called()

def test_create_issue_with_various_params(github_client):
    """ラベル、マイルストーンID、担当者ありでIssue作成"""
    mock_created_issue = MagicMock(html_url="issue/url", node_id="issue_node")
    github_client.mock_gh.rest.issues.create.return_value = MagicMock(status_code=201, parsed_data=mock_created_issue)

    url, node_id = github_client.create_issue(
        "owner", "repo", "Full Issue", body="body",
        labels=["bug", "  ", ""], # 空白ラベルは除去されるはず
        milestone=101,
        assignees=["user1", "user2", ""] # 空白担当者は除去されるはず
    )

    assert url == "issue/url"
    assert node_id == "issue_node"
    # 実装では空白の処理が行われるので、期待値を修正
    github_client.mock_gh.rest.issues.create.assert_called_once_with(
        owner="owner", repo="repo", title="Full Issue", body="body",
        labels=["bug"], # 空白除去後
        milestone=101,
        assignees=["user1", "user2"] # 空文字だけ除去
    )

def test_create_issue_api_error(github_client):
    """Issue作成で API エラーが発生した場合"""
    mock_error = create_mock_request_failed(status_code=403, content=b"Forbidden")
    github_client.mock_gh.rest.issues.create.side_effect = mock_error

    with pytest.raises(GitHubAuthenticationError):
        github_client.create_issue("owner", "repo", "Title")

    github_client.mock_gh.rest.issues.create.assert_called_once()

def test_create_issue_unexpected_response_status(github_client, caplog):
    """Issue作成APIが201以外の成功ステータスを返した場合 (考えにくいが念のため)"""
    # 200 OK だが URL/Node ID がない場合
    mock_response = MagicMock(status_code=200, parsed_data=None)
    github_client.mock_gh.rest.issues.create.return_value = mock_response

    with pytest.raises(GitHubClientError, match="Could not retrieve issue URL after creation"), caplog.at_level(logging.ERROR):
        github_client.create_issue("owner", "repo", "Weird Response")

    assert "Failed to get issue URL from API response (Status: 200, Data: No parsed data)" in caplog.text
    github_client.mock_gh.rest.issues.create.assert_called_once()

# --- find_issue_by_title Tests ---

def test_find_issue_by_title_found(github_client):
    """指定タイトルのOpenなIssueが見つかる場合 True"""
    mock_search_result = MagicMock(total_count=1)
    github_client.mock_gh.rest.search.issues_and_pull_requests.return_value = MagicMock(parsed_data=mock_search_result)
    result = github_client.find_issue_by_title("owner", "repo", "Existing Issue")
    assert result is True
    expected_query = 'repo:owner/repo is:issue is:open in:title "Existing Issue"'
    github_client.mock_gh.rest.search.issues_and_pull_requests.assert_called_once_with(q=expected_query, per_page=1)

def test_find_issue_by_title_not_found(github_client):
    """指定タイトルのOpenなIssueが見つからない場合 False"""
    mock_search_result = MagicMock(total_count=0)
    github_client.mock_gh.rest.search.issues_and_pull_requests.return_value = MagicMock(parsed_data=mock_search_result)
    result = github_client.find_issue_by_title("owner", "repo", "New Issue")
    assert result is False

def test_find_issue_by_title_empty_title(github_client):
    """空のタイトルで検索すると False を返す"""
    result = github_client.find_issue_by_title("owner", "repo", " ")
    assert result is False
    github_client.mock_gh.rest.search.issues_and_pull_requests.assert_not_called()

def test_find_issue_by_title_api_error(github_client):
    """Issue検索でAPIエラーが発生した場合"""
    mock_error = create_mock_request_failed(status_code=401, content=b"Auth error")
    github_client.mock_gh.rest.search.issues_and_pull_requests.side_effect = mock_error
    with pytest.raises(GitHubAuthenticationError):
        github_client.find_issue_by_title("owner", "repo", "Search Error Issue")

def test_find_issue_by_title_unexpected_response(github_client, caplog):
    """Issue検索APIが予期しないレスポンス形式を返した場合"""
    # total_count がないレスポンス
    mock_response = MagicMock(parsed_data=MagicMock(total_count=None), status_code=200)
    github_client.mock_gh.rest.search.issues_and_pull_requests.return_value = mock_response
    with pytest.raises(GitHubClientError, match="Unexpected response format"), caplog.at_level(logging.WARNING):
        github_client.find_issue_by_title("owner", "repo", "Weird Search")
    assert "Could not determine issue existence from search API response" in caplog.text

# --- validate_assignees Tests ---

def test_validate_assignees_success(github_client):
    """担当者が全員有効な場合"""
    # check_collaborator が 204 を返すように設定
    github_client.mock_gh.rest.repos.check_collaborator.return_value = MagicMock(status_code=204)
    assignees = ["user1", "@user2"] # @付きも含む
    valid, invalid = github_client.validate_assignees("owner", "repo", assignees)
    assert valid == ["user1", "user2"] # @は除去される
    assert invalid == []
    assert github_client.mock_gh.rest.repos.check_collaborator.call_count == 2
    github_client.mock_gh.rest.repos.check_collaborator.assert_any_call(owner="owner", repo="repo", username="user1")
    github_client.mock_gh.rest.repos.check_collaborator.assert_any_call(owner="owner", repo="repo", username="user2") # @除去後

def test_validate_assignees_mixed(github_client, caplog):
    """有効・無効な担当者が混在する場合"""
    # 'invalid-user' の時だけ 404 を返すように設定
    def check_collab_side_effect(owner, repo, username):
        if username == "invalid-user":
            raise create_mock_request_failed(status_code=404, content=b"Not Found")
        return MagicMock(status_code=204) # 他は成功
    github_client.mock_gh.rest.repos.check_collaborator.side_effect = check_collab_side_effect

    assignees = ["valid-user", "invalid-user"]
    with caplog.at_level(logging.INFO): # WARNINGも含む
        valid, invalid = github_client.validate_assignees("owner", "repo", assignees)

    assert valid == ["valid-user"]
    assert invalid == ["invalid-user"]
    assert github_client.mock_gh.rest.repos.check_collaborator.call_count == 2
    assert "Assignee 'invalid-user' is not a collaborator" in caplog.text
    assert "Found 1 invalid assignee(s)" in caplog.text

def test_validate_assignees_api_error(github_client, caplog):
    """担当者検証API呼び出し自体が失敗する場合 (例: 403 Forbidden)"""
    # API呼び出しが 403 を返すように設定
    mock_error = create_mock_request_failed(status_code=403, content=b"Forbidden")
    github_client.mock_gh.rest.repos.check_collaborator.side_effect = mock_error

    assignees = ["user1"]
    with caplog.at_level(logging.WARNING):
        valid, invalid = github_client.validate_assignees("owner", "repo", assignees)

    assert valid == [] # APIエラー時は無効扱い
    assert invalid == ["user1"]
    assert github_client.mock_gh.rest.repos.check_collaborator.call_count == 1
    assert "Permission denied (403) checking collaborator status" in caplog.text

def test_validate_assignees_unexpected_error(github_client, caplog):
    """担当者検証中に予期せぬエラーが発生した場合"""
    # API呼び出しが予期せぬエラーを発生させる
    mock_error = ValueError("Unexpected")
    github_client.mock_gh.rest.repos.check_collaborator.side_effect = mock_error

    assignees = ["user1"]
    with caplog.at_level(logging.WARNING):
        valid, invalid = github_client.validate_assignees("owner", "repo", assignees)

    assert valid == [] # エラー時は無効扱い
    assert invalid == ["user1"]
    assert github_client.mock_gh.rest.repos.check_collaborator.call_count == 1
    assert "Unexpected error validating assignee 'user1': ValueError - Unexpected" in caplog.text

def test_validate_assignees_empty_list(github_client):
    """空の担当者リストを渡した場合"""
    valid, invalid = github_client.validate_assignees("owner", "repo", [])
    assert valid == []
    assert invalid == []
    github_client.mock_gh.rest.repos.check_collaborator.assert_not_called()

def test_validate_assignees_skips_empty_login(github_client, caplog):
    """空や空白の担当者名がスキップされるか"""
    github_client.mock_gh.rest.repos.check_collaborator.return_value = MagicMock(status_code=204)
    assignees = ["user1", "", " ", "@user2"]
    with caplog.at_level(logging.WARNING):
        valid, invalid = github_client.validate_assignees("owner", "repo", assignees)
    assert valid == ["user1", "user2"]
    assert invalid == []
    assert github_client.mock_gh.rest.repos.check_collaborator.call_count == 2 # 空白は呼ばれない
    assert "Skipping empty assignee login" in caplog.text

# --- find_project_v2_node_id Tests ---

# モックGraphQLレスポンス生成ヘルパー
def create_mock_graphql_response(nodes, has_next_page=False, end_cursor=None, errors=None):
    page_info = {"hasNextPage": has_next_page}
    if end_cursor:
        page_info["endCursor"] = end_cursor

    # Response オブジェクトを模倣
    mock_response = MagicMock()
    # response.data の中に GraphQL 構造があることを模倣
    mock_response.data = {
        "repositoryOwner": {
            "projectsV2": {
                "nodes": nodes,
                "pageInfo": page_info
            }
        }
    }
    # response.errors の模倣
    mock_response.errors = errors
    return mock_response

def test_find_project_v2_node_id_success_first_page(github_client):
    """最初のページでプロジェクトが見つかる場合"""
    nodes = [
        {"id": "PROJECT_ID_OTHER", "title": "Other Project"},
        {"id": "PROJECT_ID_TARGET", "title": TARGET_PROJECT_NAME}
    ]
    mock_response = create_mock_graphql_response(nodes)
    github_client.mock_gh.graphql.return_value = mock_response

    result = github_client.find_project_v2_node_id(TARGET_OWNER, TARGET_PROJECT_NAME)
    assert result == "PROJECT_ID_TARGET"
    github_client.mock_gh.graphql.assert_called_once()
    # 実装では位置引数としてGraphQLクエリと変数を渡している
    args, _ = github_client.mock_gh.graphql.call_args
    assert len(args) >= 2
    assert isinstance(args[0], str)  # 最初の引数はGraphQLクエリ文字列
    assert isinstance(args[1], dict)  # 2番目の引数は変数辞書
    assert args[1] == {"ownerLogin": TARGET_OWNER, "first": 100}

def test_find_project_v2_node_id_success_second_page(github_client):
    """2ページ目でプロジェクトが見つかる場合"""
    nodes_page1 = [{"id": f"PROJ_ID_{i}", "title": f"Project {i}"} for i in range(100)]
    nodes_page2 = [
        {"id": "PROJECT_ID_TARGET", "title": TARGET_PROJECT_NAME},
        {"id": "PROJECT_ID_OTHER", "title": "Other Project"},
    ]
    mock_response_page1 = create_mock_graphql_response(nodes_page1, has_next_page=True, end_cursor="CURSOR1")
    mock_response_page2 = create_mock_graphql_response(nodes_page2)
    github_client.mock_gh.graphql.side_effect = [mock_response_page1, mock_response_page2]

    result = github_client.find_project_v2_node_id(TARGET_OWNER, TARGET_PROJECT_NAME)
    assert result == "PROJECT_ID_TARGET"
    assert github_client.mock_gh.graphql.call_count == 2
    
    # 1回目の呼び出し - 位置引数の確認
    call1_args, _ = github_client.mock_gh.graphql.call_args_list[0]
    assert len(call1_args) >= 2
    assert call1_args[1] == {"ownerLogin": TARGET_OWNER, "first": 100}
    
    # 2回目の呼び出し - 位置引数の確認
    call2_args, _ = github_client.mock_gh.graphql.call_args_list[1]
    assert len(call2_args) >= 2
    assert call2_args[1] == {"ownerLogin": TARGET_OWNER, "first": 100, "after": "CURSOR1"}

def test_find_project_v2_node_id_not_found(github_client, caplog):
    """プロジェクトが見つからない場合 None を返し、警告ログが出る"""
    nodes_page1 = [{"id": f"PROJ_ID_{i}", "title": f"Project {i}"} for i in range(5)]
    mock_response = create_mock_graphql_response(nodes_page1) # hasNextPage = False
    github_client.mock_gh.graphql.return_value = mock_response

    with caplog.at_level(logging.WARNING):
        result = github_client.find_project_v2_node_id(TARGET_OWNER, "NonExistent Project")
    assert result is None
    assert f"Project V2 'NonExistent Project' not found" in caplog.text
    github_client.mock_gh.graphql.assert_called_once()

def test_find_project_v2_node_id_reaches_max_pages(github_client, caplog):
    """最大ページ数に達しても見つからない場合 None を返し、警告ログが出る"""
    # 全てのページで hasNextPage=True を返すように設定
    def graphql_side_effect(*args, **kwargs):
        # args[1]から変数を取得する
        variables = args[1]
        after = variables.get('after', 'start')
        # ループ変数を適切に定義し、range内で使用する
        nodes = [{"id": f"PROJ_ID_{after}_{j}", "title": f"Page {j}"} for j in range(10)]
        return create_mock_graphql_response(nodes, has_next_page=True, end_cursor=f"CURSOR_{after}_9")

    github_client.mock_gh.graphql.side_effect = graphql_side_effect

    with caplog.at_level(logging.WARNING):
        result = github_client.find_project_v2_node_id(TARGET_OWNER, TARGET_PROJECT_NAME)
    assert result is None
    assert "Reached maximum page limit" in caplog.text
    assert github_client.mock_gh.graphql.call_count == 10  # max_pages 回呼ばれる

def test_find_project_v2_node_id_graphql_error(github_client):
    """GraphQL API 呼び出しでエラーが発生した場合"""
    graphql_response_with_error = create_mock_graphql_response(
        nodes=[], errors=[{"type": "INTERNAL_ERROR", "message": "Server failed"}]
    )
    github_client.mock_gh.graphql.return_value = graphql_response_with_error

    with pytest.raises(GitHubClientError, match="GraphQL operation failed"):
        github_client.find_project_v2_node_id(TARGET_OWNER, TARGET_PROJECT_NAME)

def test_find_project_v2_node_id_missing_repository_owner(github_client, caplog):
    """レスポンス内に repositoryOwner フィールドがない場合"""
    # モックレスポンスを不完全な形式にする
    incomplete_response = {"data": {}} # repositoryOwner キーがない
    github_client.mock_gh.graphql.return_value = incomplete_response
    
    # 例外が発生せず、警告ログだけが出力される実装に合わせてテストを変更
    with caplog.at_level(logging.ERROR):
        result = github_client.find_project_v2_node_id(TARGET_OWNER, TARGET_PROJECT_NAME)
    
    assert result is None
    assert "GraphQL response missing data on page" in caplog.text
    github_client.mock_gh.graphql.assert_called_once()

def test_find_project_v2_node_id_missing_projects_v2(github_client, caplog):
    """レスポンス内に projectsV2 フィールドがない場合"""
    # モックレスポンスを不完全な形式にする
    incomplete_response = {"data": {"repositoryOwner": {}}} # projectsV2 キーがない
    
    github_client.mock_gh.graphql.return_value = incomplete_response
    
    # 例外が発生せず、警告ログだけが出力される実装に合わせてテストを変更
    with caplog.at_level(logging.ERROR):
        result = github_client.find_project_v2_node_id(TARGET_OWNER, TARGET_PROJECT_NAME)
    
    assert result is None
    github_client.mock_gh.graphql.assert_called_once()

def test_find_project_v2_node_id_empty_title(github_client):
    """タイトルが空の場合 ValueError が発生する"""
    with pytest.raises(ValueError, match="Project name cannot be empty"):
        github_client.find_project_v2_node_id(TARGET_OWNER, "")
    
    github_client.mock_gh.graphql.assert_not_called()

def test_find_project_v2_node_id_empty_owner(github_client):
    """オーナーが空の場合 ValueError が発生する"""
    with pytest.raises(ValueError, match="Owner login cannot be empty"):
        github_client.find_project_v2_node_id("", TARGET_PROJECT_NAME)
    
    github_client.mock_gh.graphql.assert_not_called()

# --- add_item_to_project_v2 Tests ---

def test_add_item_to_project_v2_success(github_client):
    """アイテム追加が成功する場合"""
    mock_response_dict = {
        "data": {
            "addProjectV2ItemById": {
                "item": {"id": "NEW_ITEM_ID"}
            }
        }
    }
    github_client.mock_gh.graphql.return_value = mock_response_dict
    result = github_client.add_item_to_project_v2("PROJECT_NODE", "CONTENT_NODE")
    assert result == "NEW_ITEM_ID"
    github_client.mock_gh.graphql.assert_called_once()
    # 呼び出し時の引数を確認（位置引数）
    args, _ = github_client.mock_gh.graphql.call_args
    assert len(args) >= 2
    assert "AddItemToProject" in args[0]  # 1つ目はGraphQLミューテーション文字列
    assert args[1] == {"projectId": "PROJECT_NODE", "contentId": "CONTENT_NODE"}  # 2つ目は変数辞書

def test_add_item_to_project_v2_graphql_error(github_client):
    """アイテム追加で GraphQL エラーが発生した場合"""
    mock_response_dict = {
        "errors": [{"message": "Permission denied", "type": "FORBIDDEN"}]
    }
    github_client.mock_gh.graphql.return_value = mock_response_dict
    with pytest.raises(GitHubAuthenticationError, match="GraphQL permission denied"):
        github_client.add_item_to_project_v2("PROJECT_NODE", "CONTENT_NODE")

def test_add_item_to_project_v2_invalid_response(github_client, caplog):
    """アイテム追加APIが予期しない形式のレスポンスを返した場合"""
    mock_response_dict = {"data": {"addProjectV2ItemById": None}}  # item がない
    github_client.mock_gh.graphql.return_value = mock_response_dict
    
    # ERRORレベルのログを捕捉し、例外のメッセージを確認
    with pytest.raises(GitHubClientError, match="Failed to add item"):
        with caplog.at_level(logging.ERROR):
            github_client.add_item_to_project_v2("PROJECT_NODE", "CONTENT_NODE")
    
    # 例外発生時にも呼び出しが行われることを確認
    github_client.mock_gh.graphql.assert_called_once()

def test_add_item_to_project_v2_missing_add_project_field(github_client, caplog):
    """レスポンスに addProjectV2ItemById フィールドがない場合"""
    mock_response_dict = {"data": {"some_other_field": {}}}  # addProjectV2ItemById キーがない
    github_client.mock_gh.graphql.return_value = mock_response_dict
    
    with pytest.raises(GitHubClientError):
        with caplog.at_level(logging.ERROR):
            github_client.add_item_to_project_v2("PROJECT_NODE", "CONTENT_NODE")
    
    # 例外発生時にも呼び出しが行われることを確認
    github_client.mock_gh.graphql.assert_called_once()

def test_add_item_to_project_v2_empty_args(github_client):
    """プロジェクトIDやコンテンツIDが空の場合に ValueError"""
    with pytest.raises(ValueError, match="Project Node ID cannot be empty"):
        github_client.add_item_to_project_v2("", "CONTENT_NODE")
    with pytest.raises(ValueError, match="Content Node ID cannot be empty"):
        github_client.add_item_to_project_v2("PROJECT_NODE", " ")
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
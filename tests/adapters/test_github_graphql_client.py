# tests/adapters/test_github_graphql_client.py

import pytest
from unittest.mock import MagicMock, patch
import logging
import json

from github_automation_tool.adapters.github_graphql_client import GitHubGraphQLClient
from github_automation_tool.domain.exceptions import (
    GitHubClientError, GitHubAuthenticationError, GitHubRateLimitError,
    GitHubResourceNotFoundError, GitHubValidationError
)

from githubkit import GitHub
from githubkit.exception import RequestFailed, RequestError, RequestTimeout

# グローバル定数
TARGET_OWNER = "test-owner"
TARGET_PROJECT_NAME = "Test Project"

# GraphQLレスポンスのモック作成ヘルパー関数
def create_mock_graphql_response(nodes, has_next_page=False, end_cursor=None, errors=None):
    """GraphQLレスポンスオブジェクトのモックを作成"""
    page_info = {"hasNextPage": has_next_page}
    if end_cursor:
        page_info["endCursor"] = end_cursor

    # Response オブジェクトを模倣
    mock_response = {
        "data": {
            "repositoryOwner": {
                "projectsV2": {
                    "nodes": nodes,
                    "pageInfo": page_info
                }
            }
        }
    }
    
    # エラーがある場合は追加
    if errors:
        mock_response["errors"] = errors
        # data部分を削除して、エラー状態を再現
        mock_response.pop("data", None)
        
    return mock_response

# テスト全体で使用するフィクスチャ
@pytest.fixture
def mock_github():
    """githubkit.GitHub のモックインスタンスを返すフィクスチャ"""
    mock_gh = MagicMock(spec=GitHub)
    mock_gh.graphql = MagicMock()  # GraphQL エンドポイント
    return mock_gh

@pytest.fixture
def graphql_client(mock_github):
    """テスト用のGitHubGraphQLClientインスタンスを返す"""
    client = GitHubGraphQLClient(mock_github)
    # 内部のGitHubインスタンスにアクセスしやすくするためのプロパティを設定
    client.mock_gh = mock_github
    return client


# __init__ テスト

def test_init_with_valid_instance():
    """有効なGitHubインスタンスで初期化できることを確認"""
    mock_github_instance = MagicMock(spec=GitHub)
    client = GitHubGraphQLClient(mock_github_instance)
    assert client.gh is mock_github_instance

def test_init_with_invalid_instance_type():
    """GitHubインスタンス以外で初期化するとエラーになることを確認"""
    with pytest.raises(TypeError, match="must be a valid githubkit.GitHub instance"):
        GitHubGraphQLClient("not-a-github-instance")

def test_init_with_none():
    """Noneで初期化するとエラーになることを確認"""
    with pytest.raises(TypeError):
        GitHubGraphQLClient(None)


# find_project_v2_node_id テスト

def test_find_project_v2_node_id_success_first_page(graphql_client):
    """最初のページでプロジェクトが見つかる場合"""
    nodes = [
        {"id": "PROJECT_ID_OTHER", "title": "Other Project"},
        {"id": "PROJECT_ID_TARGET", "title": TARGET_PROJECT_NAME}
    ]
    mock_response = create_mock_graphql_response(nodes)
    graphql_client.mock_gh.graphql.return_value = mock_response

    result = graphql_client.find_project_v2_node_id(TARGET_OWNER, TARGET_PROJECT_NAME)
    assert result == "PROJECT_ID_TARGET"
    graphql_client.mock_gh.graphql.assert_called_once()
    # 実装では位置引数としてGraphQLクエリと変数を渡している
    args, _ = graphql_client.mock_gh.graphql.call_args
    assert len(args) >= 2
    assert isinstance(args[0], str)  # 最初の引数はGraphQLクエリ文字列
    assert isinstance(args[1], dict)  # 2番目の引数は変数辞書
    assert args[1] == {"ownerLogin": TARGET_OWNER, "first": 100}

def test_find_project_v2_node_id_success_second_page(graphql_client):
    """2ページ目でプロジェクトが見つかる場合"""
    nodes_page1 = [{"id": f"PROJ_ID_{i}", "title": f"Project {i}"} for i in range(100)]
    nodes_page2 = [
        {"id": "PROJECT_ID_TARGET", "title": TARGET_PROJECT_NAME},
        {"id": "PROJECT_ID_OTHER", "title": "Other Project"},
    ]
    mock_response_page1 = create_mock_graphql_response(nodes_page1, has_next_page=True, end_cursor="CURSOR1")
    mock_response_page2 = create_mock_graphql_response(nodes_page2)
    graphql_client.mock_gh.graphql.side_effect = [mock_response_page1, mock_response_page2]

    result = graphql_client.find_project_v2_node_id(TARGET_OWNER, TARGET_PROJECT_NAME)
    assert result == "PROJECT_ID_TARGET"
    assert graphql_client.mock_gh.graphql.call_count == 2
    
    # 1回目の呼び出し - 位置引数の確認
    call1_args, _ = graphql_client.mock_gh.graphql.call_args_list[0]
    assert len(call1_args) >= 2
    assert call1_args[1] == {"ownerLogin": TARGET_OWNER, "first": 100}
    
    # 2回目の呼び出し - 位置引数の確認
    call2_args, _ = graphql_client.mock_gh.graphql.call_args_list[1]
    assert len(call2_args) >= 2
    assert call2_args[1] == {"ownerLogin": TARGET_OWNER, "first": 100, "after": "CURSOR1"}

def test_find_project_v2_node_id_not_found(graphql_client, caplog):
    """プロジェクトが見つからない場合 None を返し、警告ログが出る"""
    nodes_page1 = [{"id": f"PROJ_ID_{i}", "title": f"Project {i}"} for i in range(5)]
    mock_response = create_mock_graphql_response(nodes_page1) # hasNextPage = False
    graphql_client.mock_gh.graphql.return_value = mock_response

    with caplog.at_level(logging.WARNING):
        result = graphql_client.find_project_v2_node_id(TARGET_OWNER, "NonExistent Project")
    assert result is None
    assert "not found" in caplog.text.lower()
    graphql_client.mock_gh.graphql.assert_called_once()

def test_find_project_v2_node_id_reaches_max_pages(graphql_client, caplog):
    """最大ページ数に達しても見つからない場合 None を返し、警告ログが出る"""
    # 各ページに異なるプロジェクト（全て対象と名前が異なる）がある状況をモック
    mock_responses = []
    for i in range(10):  # max_pages=10
        nodes = [{"id": f"PROJ_ID_{i}_{j}", "title": f"Project {i}_{j}"} for j in range(2)]
        mock_response = create_mock_graphql_response(
            nodes, has_next_page=(i < 9), end_cursor=f"CURSOR{i}")
        mock_responses.append(mock_response)
    
    graphql_client.mock_gh.graphql.side_effect = mock_responses

    with caplog.at_level(logging.WARNING):
        result = graphql_client.find_project_v2_node_id(TARGET_OWNER, "NonExistent Project")
    
    assert result is None
    assert graphql_client.mock_gh.graphql.call_count == 10
    assert "Reached maximum page limit" in caplog.text

def test_find_project_v2_node_id_graphql_error(graphql_client):
    """GraphQL API 呼び出しでエラーが発生した場合"""
    # GraphQL エラーレスポンスを作成
    graphql_response_with_error = {
        "errors": [{"type": "INTERNAL_ERROR", "message": "Server failed"}]
    }
    
    # graphql呼び出しが例外を発生させるようにモック
    graphql_client.mock_gh.graphql.side_effect = GitHubClientError(
        f"GraphQL operation failed during finding Project V2: {graphql_response_with_error['errors']}"
    )
    
    # デコレータによって GitHubClientError が送出されるはず
    with pytest.raises(GitHubClientError, match="GraphQL operation failed"):
        graphql_client.find_project_v2_node_id(TARGET_OWNER, TARGET_PROJECT_NAME)

def test_find_project_v2_node_id_missing_repository_owner(graphql_client, caplog):
    """レスポンス内に repositoryOwner フィールドがない場合"""
    # 不完全なレスポンス形式
    incomplete_response = {"data": {}} # repositoryOwner キーがない
    
    graphql_client.mock_gh.graphql.return_value = incomplete_response
    
    # None を返すはず
    with caplog.at_level(logging.WARNING):
        result = graphql_client.find_project_v2_node_id(TARGET_OWNER, TARGET_PROJECT_NAME)
    
    assert result is None
    # 新しいエラーメッセージの文字列の一部を検証
    assert "empty data" in caplog.text.lower() or "not found" in caplog.text.lower()
    graphql_client.mock_gh.graphql.assert_called_once()

def test_find_project_v2_node_id_missing_projects_v2(graphql_client, caplog):
    """レスポンス内に projectsV2 フィールドがない場合"""
    # モックレスポンスを不完全な形式にする
    incomplete_response = {"data": {"repositoryOwner": {}}} # projectsV2 キーがない
    
    graphql_client.mock_gh.graphql.return_value = incomplete_response
    
    # None を返すはず
    with caplog.at_level(logging.WARNING):
        result = graphql_client.find_project_v2_node_id(TARGET_OWNER, TARGET_PROJECT_NAME)
    
    assert result is None
    assert "not found or has no projects" in caplog.text.lower() or "no projectsv2 data found" in caplog.text.lower()
    graphql_client.mock_gh.graphql.assert_called_once()

def test_find_project_v2_node_id_empty_title(graphql_client):
    """タイトルが空の場合のテスト"""
    # 空文字は許容されるが、内部でトリムされる
    # モックレスポンスも設定しておく
    mock_response = create_mock_graphql_response([])
    graphql_client.mock_gh.graphql.return_value = mock_response
    
    result = graphql_client.find_project_v2_node_id(TARGET_OWNER, "  ")
    # デコレータによってNoneが返されるはず
    assert result is None
    graphql_client.mock_gh.graphql.assert_called_once()

def test_find_project_v2_node_id_empty_owner(graphql_client):
    """オーナーが空の場合のテスト"""
    # 空文字は許容されるが、内部でトリムされる
    # モックレスポンスも設定しておく
    mock_response = create_mock_graphql_response([])
    graphql_client.mock_gh.graphql.return_value = mock_response
    
    result = graphql_client.find_project_v2_node_id("  ", TARGET_PROJECT_NAME)
    # デコレータによってNoneが返されるはず
    assert result is None
    graphql_client.mock_gh.graphql.assert_called_once()


# --- add_item_to_project_v2 Tests ---

def test_add_item_to_project_v2_success(graphql_client):
    """アイテム追加が成功する場合"""
    mock_response_dict = {
        "data": {
            "addProjectV2ItemById": {
                "item": {"id": "NEW_ITEM_ID"}
            }
        }
    }
    graphql_client.mock_gh.graphql.return_value = mock_response_dict
    result = graphql_client.add_item_to_project_v2("PROJECT_NODE", "CONTENT_NODE")
    assert result == "NEW_ITEM_ID"
    graphql_client.mock_gh.graphql.assert_called_once()
    # 呼び出し時の引数を確認（位置引数）
    args, _ = graphql_client.mock_gh.graphql.call_args
    assert len(args) >= 2
    assert "AddItemToProject" in args[0]  # 1つ目はGraphQLミューテーション文字列
    assert args[1] == {"projectId": "PROJECT_NODE", "contentId": "CONTENT_NODE"}  # 2つ目は変数辞書

def test_add_item_to_project_v2_graphql_error(graphql_client):
    """アイテム追加で GraphQL エラーが発生した場合"""
    # GraphQLエラーのモック - errorsのみを含む形式
    mock_response_dict = {
        "errors": [{"message": "Permission denied", "type": "FORBIDDEN"}]
    }
    
    # 権限エラーとしてモック
    graphql_client.mock_gh.graphql.side_effect = GitHubAuthenticationError(
        f"GraphQL permission denied during adding item: {mock_response_dict['errors']}"
    )
    
    # デコレータが GitHubAuthenticationError を送出するはず
    with pytest.raises(GitHubAuthenticationError, match="permission denied"):
        graphql_client.add_item_to_project_v2("PROJECT_NODE", "CONTENT_NODE")

def test_add_item_to_project_v2_invalid_response(graphql_client, caplog):
    """アイテム追加APIが予期しない形式のレスポンスを返した場合"""
    mock_response_dict = {"data": {"addProjectV2ItemById": None}}  # item がない
    graphql_client.mock_gh.graphql.return_value = mock_response_dict
    
    # ERRORレベルのログを捕捉し、例外のメッセージを確認
    with pytest.raises(GitHubClientError, match="Failed to add item"):
        with caplog.at_level(logging.ERROR):
            graphql_client.add_item_to_project_v2("PROJECT_NODE", "CONTENT_NODE")
    
    # 例外発生時にも呼び出しが行われることを確認
    graphql_client.mock_gh.graphql.assert_called_once()

def test_add_item_to_project_v2_missing_add_project_field(graphql_client, caplog):
    """レスポンスに addProjectV2ItemById フィールドがない場合"""
    mock_response_dict = {"data": {"some_other_field": {}}}  # addProjectV2ItemById キーがない
    graphql_client.mock_gh.graphql.return_value = mock_response_dict
    
    with pytest.raises(GitHubClientError):
        with caplog.at_level(logging.ERROR):
            graphql_client.add_item_to_project_v2("PROJECT_NODE", "CONTENT_NODE")
    
    # 例外発生時にも呼び出しが行われることを確認
    graphql_client.mock_gh.graphql.assert_called_once()

def test_add_item_to_project_v2_empty_args():
    """プロジェクトIDやコンテンツIDが空の場合に ValueError"""
    # デコレータのパッチを回避し、直接クラスメソッドを修正する
    with patch.object(GitHubGraphQLClient, 'add_item_to_project_v2', GitHubGraphQLClient.add_item_to_project_v2.__wrapped__):
        client = GitHubGraphQLClient(MagicMock(spec=GitHub))
        
        with pytest.raises(ValueError, match="Project Node ID and Content Node ID cannot be empty"):
            client.add_item_to_project_v2("", "CONTENT_NODE")
            
        with pytest.raises(ValueError, match="Project Node ID and Content Node ID cannot be empty"):
            client.add_item_to_project_v2("PROJECT_NODE", "  ")

def test_add_item_to_project_v2_trims_input(graphql_client):
    """入力値のトリムが正しく行われることを確認"""
    mock_response_dict = {
        "data": {
            "addProjectV2ItemById": {
                "item": {"id": "NEW_ITEM_ID"}
            }
        }
    }
    graphql_client.mock_gh.graphql.return_value = mock_response_dict
    
    # スペースを含むIDでメソッドを呼び出し
    result = graphql_client.add_item_to_project_v2("  PROJECT_NODE  ", "  CONTENT_NODE  ")
    assert result == "NEW_ITEM_ID"
    
    # 呼び出し時の引数を確認 - トリムされた値で呼ばれることを確認
    args, _ = graphql_client.mock_gh.graphql.call_args
    assert args[1] == {"projectId": "PROJECT_NODE", "contentId": "CONTENT_NODE"}
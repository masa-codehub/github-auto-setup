# tests/adapters/test_assignee_validator.py

import pytest
from unittest.mock import MagicMock, patch
import logging

from core_logic.adapters.assignee_validator import AssigneeValidator
from core_logic.adapters.github_rest_client import GitHubRestClient
from core_logic.domain.exceptions import GitHubClientError


@pytest.fixture
def mock_rest_client():
    """GitHubRestClientのモックを返すフィクスチャ"""
    mock = MagicMock(spec=GitHubRestClient)
    return mock


def test_init_with_invalid_client():
    """不正なタイプのクライアントで初期化するとTypeErrorが発生することを確認"""
    with pytest.raises(TypeError):
        AssigneeValidator("not_a_rest_client")  # 文字列は無効なクライアント


def test_validate_assignees_empty_list(mock_rest_client):
    """空のリストを渡した場合は空のタプル（[], []）が返されることを確認"""
    validator = AssigneeValidator(mock_rest_client)
    valid, invalid = validator.validate_assignees("owner", "repo", [])

    assert valid == []
    assert invalid == []
    # APIは呼ばれないことを確認
    mock_rest_client.check_collaborator.assert_not_called()


def test_validate_assignees_whitespace_and_empty(mock_rest_client, caplog):
    """空文字や空白のみの担当者名がスキップされることを確認"""
    validator = AssigneeValidator(mock_rest_client)
    with caplog.at_level(logging.DEBUG):
        valid, invalid = validator.validate_assignees(
            "owner", "repo", ["", " ", None])

    assert valid == []
    assert invalid == []
    # APIは呼ばれないことを確認
    mock_rest_client.check_collaborator.assert_not_called()
    assert "No valid assignee logins found after cleanup" in caplog.text


def test_validate_assignees_all_valid(mock_rest_client):
    """全ての担当者が有効な場合のテスト"""
    mock_rest_client.check_collaborator.return_value = True
    validator = AssigneeValidator(mock_rest_client)
    valid, invalid = validator.validate_assignees(
        "owner", "repo", ["user1", "@user2"])

    # 順序に依存しない比較に修正
    assert set(valid) == set(["user1", "user2"])  # @は削除される
    assert invalid == []
    # APIが各担当者で呼ばれたことを確認
    assert mock_rest_client.check_collaborator.call_count == 2
    mock_rest_client.check_collaborator.assert_any_call(
        "owner", "repo", "user1")
    mock_rest_client.check_collaborator.assert_any_call(
        "owner", "repo", "user2")


def test_validate_assignees_all_invalid(mock_rest_client, caplog):
    """全ての担当者が無効な場合のテスト"""
    mock_rest_client.check_collaborator.return_value = False
    validator = AssigneeValidator(mock_rest_client)
    with caplog.at_level(logging.WARNING):
        valid, invalid = validator.validate_assignees(
            "owner", "repo", ["invalid1", "invalid2"])

    assert valid == []
    # 順序に依存しない比較に修正
    assert set(invalid) == set(["invalid1", "invalid2"])
    assert mock_rest_client.check_collaborator.call_count == 2
    assert "is not a collaborator or could not be verified" in caplog.text
    assert "Invalid/Unverified: 2/2" in caplog.text


def test_validate_assignees_mixed(mock_rest_client, caplog):
    """有効・無効な担当者が混在する場合のテスト"""
    # check_collaborator がユーザー名に応じて異なる値を返すようにする
    def check_collab_side_effect(owner, repo, username):
        return username == "valid-user"

    mock_rest_client.check_collaborator.side_effect = check_collab_side_effect
    validator = AssigneeValidator(mock_rest_client)
    with caplog.at_level(logging.WARNING):
        valid, invalid = validator.validate_assignees(
            "owner", "repo", ["valid-user", "invalid-user"])

    assert valid == ["valid-user"]
    assert invalid == ["invalid-user"]
    assert mock_rest_client.check_collaborator.call_count == 2
    assert "Assignee 'invalid-user' is not a collaborator" in caplog.text


def test_validate_assignees_api_error(mock_rest_client, caplog):
    """API呼び出しでエラーが発生した場合のテスト"""
    mock_rest_client.check_collaborator.side_effect = GitHubClientError(
        "API Error")
    validator = AssigneeValidator(mock_rest_client)
    with caplog.at_level(logging.WARNING):
        valid, invalid = validator.validate_assignees(
            "owner", "repo", ["user1"])

    assert valid == []
    assert invalid == ["user1"]  # エラー時は無効扱い
    assert "API error validating assignee 'user1'" in caplog.text


def test_validate_assignees_unexpected_error(mock_rest_client, caplog):
    """予期せぬエラーが発生した場合のテスト"""
    mock_rest_client.check_collaborator.side_effect = ValueError(
        "Unexpected Error")
    validator = AssigneeValidator(mock_rest_client)
    with caplog.at_level(logging.ERROR):
        valid, invalid = validator.validate_assignees(
            "owner", "repo", ["user1"])

    assert valid == []
    assert invalid == ["user1"]  # エラー時は無効扱い
    assert "Unexpected error validating assignee 'user1'" in caplog.text
    assert "ValueError - Unexpected Error" in caplog.text


def test_validate_assignees_deduplication(mock_rest_client):
    """重複する担当者名がユニーク化されるか確認するテスト"""
    mock_rest_client.check_collaborator.return_value = True
    validator = AssigneeValidator(mock_rest_client)
    valid, invalid = validator.validate_assignees(
        "owner", "repo", ["user1", "user1", "@user1"])

    assert valid == ["user1"]  # 重複は除去され、@も削除される
    assert invalid == []
    # APIは1回だけ呼ばれる（重複は排除される）
    mock_rest_client.check_collaborator.assert_called_once_with(
        "owner", "repo", "user1")

import pytest
from unittest.mock import MagicMock  # GitHubAppClient をモック化するために使用

# テスト対象の UseCase と、それが依存する Client、発生しうる例外をインポート
from github_automation_tool.use_cases.create_repository import CreateRepositoryUseCase
from github_automation_tool.adapters.github_client import GitHubAppClient  # モックの spec に使う
from github_automation_tool.domain.exceptions import (
    GitHubValidationError, GitHubAuthenticationError, GitHubClientError
)

# --- Fixtures ---


@pytest.fixture
def mock_github_client() -> MagicMock:
    """GitHubAppClient のモックインスタンスを作成するフィクスチャ"""
    # spec=GitHubAppClient を指定すると、存在しないメソッドを呼んだ場合にエラーになる
    mock = MagicMock(spec=GitHubAppClient)
    return mock


@pytest.fixture
def create_repo_use_case(mock_github_client: MagicMock) -> CreateRepositoryUseCase:
    """テスト対象の UseCase インスタンスを作成（モッククライアントを注入）"""
    return CreateRepositoryUseCase(github_client=mock_github_client)

# --- Test Cases ---


def test_execute_success(create_repo_use_case: CreateRepositoryUseCase, mock_github_client: MagicMock):
    """リポジトリ作成が成功し、正しいURLが返されることをテスト"""
    repo_name = "my-awesome-repo"
    expected_url = f"https://github.com/user/{repo_name}"

    # モックの設定: client.create_repository が呼ばれたら expected_url を返す
    mock_github_client.create_repository.return_value = expected_url

    # UseCase を実行
    actual_url = create_repo_use_case.execute(repo_name)

    # 検証
    assert actual_url == expected_url
    # 依存する client のメソッドが正しい引数で1回呼ばれたことを確認
    mock_github_client.create_repository.assert_called_once_with(repo_name)


def test_execute_raises_validation_error_when_client_does(
    create_repo_use_case: CreateRepositoryUseCase, mock_github_client: MagicMock
):
    """GitHubクライアントが GitHubValidationError を送出した場合、UseCaseもそれを送出するか"""
    repo_name = "existing-repo"
    # モックの設定: client.create_repository が GitHubValidationError を送出する
    mock_exception = GitHubValidationError(
        f"Repository '{repo_name}' already exists.", status_code=422)
    mock_github_client.create_repository.side_effect = mock_exception

    # UseCase を実行し、期待する例外が発生するか検証
    with pytest.raises(GitHubValidationError, match=f"Repository '{repo_name}' already exists.") as excinfo:
        create_repo_use_case.execute(repo_name)

    # (オプション) 送出された例外がモックしたものと同じ内容か確認
    assert excinfo.value.status_code == 422
    # mock_github_client.create_repository が呼ばれたことを確認
    mock_github_client.create_repository.assert_called_once_with(repo_name)


def test_execute_raises_auth_error_when_client_does(
    create_repo_use_case: CreateRepositoryUseCase, mock_github_client: MagicMock
):
    """GitHubクライアントが GitHubAuthenticationError を送出した場合、UseCaseもそれを送出するか"""
    repo_name = "forbidden-repo"
    mock_exception = GitHubAuthenticationError(
        "Permission denied.", status_code=403)
    mock_github_client.create_repository.side_effect = mock_exception

    with pytest.raises(GitHubAuthenticationError, match="Permission denied.") as excinfo:
        create_repo_use_case.execute(repo_name)

    assert excinfo.value.status_code == 403
    mock_github_client.create_repository.assert_called_once_with(repo_name)


def test_execute_raises_client_error_when_client_does(
    create_repo_use_case: CreateRepositoryUseCase, mock_github_client: MagicMock
):
    """GitHubクライアントが GitHubClientError を送出した場合、UseCaseもそれを送出するか"""
    repo_name = "error-repo"
    mock_exception = GitHubClientError("Network error.")
    mock_github_client.create_repository.side_effect = mock_exception

    with pytest.raises(GitHubClientError, match="Network error."):
        create_repo_use_case.execute(repo_name)

    mock_github_client.create_repository.assert_called_once_with(repo_name)


def test_execute_raises_value_error_for_invalid_repo_name(
    create_repo_use_case: CreateRepositoryUseCase, mock_github_client: MagicMock
):
    """不正なリポジトリ名（スラッシュを含む）の場合に ValueError が発生するか"""
    invalid_repo_name = "owner/repo"

    with pytest.raises(ValueError, match="Invalid repository name"):
        create_repo_use_case.execute(invalid_repo_name)

    # GitHubクライアントは呼ばれないはず
    mock_github_client.create_repository.assert_not_called()

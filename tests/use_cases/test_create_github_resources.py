import pytest
from unittest.mock import MagicMock, patch, call, ANY
from pathlib import Path

# テスト対象 UseCase と依存コンポーネント、データモデル、例外をインポート
from github_automation_tool.use_cases.create_github_resources import CreateGitHubResourcesUseCase
# 不要な依存関係のインポートを削除
# from github_automation_tool.infrastructure.config import Settings
from github_automation_tool.adapters.github_client import GitHubAppClient
from github_automation_tool.use_cases.create_repository import CreateRepositoryUseCase
from github_automation_tool.use_cases.create_issues import CreateIssuesUseCase
# CLI Reporterは不要になったため削除
# from github_automation_tool.adapters.cli_reporter import CliReporter
from github_automation_tool.domain.models import ParsedRequirementData, IssueData, CreateIssuesResult, CreateGitHubResourcesResult
from github_automation_tool.domain.exceptions import (
    GitHubClientError, GitHubValidationError, GitHubAuthenticationError, GitHubResourceNotFoundError
)

# --- Fixtures ---
# 不要なフィクスチャを削除
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
    
    # ラベル、マイルストーン、プロジェクト連携用のメソッドモックを追加
    mock.create_label = MagicMock(return_value=True)  # デフォルトは成功(新規作成)
    mock.create_milestone = MagicMock(return_value=123)  # デフォルトは成功(ID 123)
    mock.find_project_v2_node_id = MagicMock(return_value="PROJECT_NODE_ID")  # デフォルトは成功
    mock.add_item_to_project_v2 = MagicMock(return_value="PROJECT_ITEM_ID")  # デフォルトは成功
    
    return mock

@pytest.fixture
def mock_create_repo_uc() -> MagicMock:
    mock = MagicMock(spec=CreateRepositoryUseCase)
    mock.execute = MagicMock(return_value="https://github.com/test-owner/test-repo")  # デフォルトは成功
    return mock

@pytest.fixture
def mock_create_issues_uc() -> MagicMock:
    mock = MagicMock(spec=CreateIssuesUseCase)
    # デフォルトの戻り値を設定 (Issueが1つ作成されたと仮定)
    mock_issue_result = CreateIssuesResult(
        created_issue_details=[("https://github.com/test-owner/test-repo/issues/1", "ISSUE_NODE_ID_1")]
    )
    mock.execute = MagicMock(return_value=mock_issue_result)
    return mock

@pytest.fixture
def create_resources_use_case(
    mock_github_client: MagicMock, 
    mock_create_repo_uc: MagicMock, 
    mock_create_issues_uc: MagicMock
) -> CreateGitHubResourcesUseCase:
    """テスト対象 UseCase (依存を修正)"""
    return CreateGitHubResourcesUseCase(
        github_client=mock_github_client,
        create_repo_uc=mock_create_repo_uc,
        create_issues_uc=mock_create_issues_uc
    )

# --- Test Data ---
DUMMY_FILE_PATH = Path("dummy/requirements.md")
DUMMY_REPO_NAME_FULL = "test-owner/test-repo"
DUMMY_REPO_NAME_ONLY = "test-repo-only"
DUMMY_PROJECT_NAME = "Test Project"
DUMMY_MARKDOWN_CONTENT = "# Test Markdown Content"
DUMMY_ISSUE_WITH_DETAILS_1 = IssueData(
    title="Issue 1", body="Body 1", labels=["bug", "feature"], milestone="Sprint 1", assignees=["userA"]
)
DUMMY_ISSUE_WITH_DETAILS_2 = IssueData(
    title="Issue 2", body="Body 2", labels=["bug", "urgent"], milestone="Sprint 1"  # 担当者なし
)
DUMMY_ISSUE_NO_DETAILS = IssueData(title="Issue 3", body="Body 3")  # ラベル等なし
DUMMY_PARSED_DATA_WITH_DETAILS = ParsedRequirementData(
    issues=[DUMMY_ISSUE_WITH_DETAILS_1, DUMMY_ISSUE_WITH_DETAILS_2, DUMMY_ISSUE_NO_DETAILS]
)
DUMMY_PARSED_DATA_NO_ISSUES = ParsedRequirementData(issues=[])
DUMMY_REPO_URL = f"https://github.com/{DUMMY_REPO_NAME_FULL}"
DUMMY_ISSUE_RESULT = CreateIssuesResult(
    created_issue_details=[
        ("https://github.com/test-owner/test-repo/issues/1", "NODE_ID_1"),
        ("https://github.com/test-owner/test-repo/issues/2", "NODE_ID_2"),
    ],
    skipped_issue_titles=[],
    failed_issue_titles=[],
    errors=[]
)
EXPECTED_OWNER = "test-owner"
EXPECTED_REPO = "test-repo"
EXPECTED_AUTH_USER = "test-auth-user"

# --- Test Cases ---

def test_execute_success_full_repo_name(create_resources_use_case: CreateGitHubResourcesUseCase, mock_create_repo_uc, mock_create_issues_uc, mock_github_client):
    """正常系: owner/repo形式のリポジトリ名で全ステップ成功"""
    # Arrange: 各ステップのモックの戻り値を設定
    mock_create_repo_uc.execute.return_value = DUMMY_REPO_URL
    mock_create_issues_uc.execute.return_value = DUMMY_ISSUE_RESULT

    # Act: ParsedRequirementDataを直接渡すようになった
    result = create_resources_use_case.execute(
        parsed_data=DUMMY_PARSED_DATA_WITH_DETAILS,
        repo_name_input=DUMMY_REPO_NAME_FULL,
        project_name=DUMMY_PROJECT_NAME
    )

    # Assert: 結果オブジェクトの検証
    assert isinstance(result, CreateGitHubResourcesResult)
    assert result.repository_url == DUMMY_REPO_URL
    assert result.project_name == DUMMY_PROJECT_NAME
    assert result.project_node_id == "PROJECT_NODE_ID"
    assert result.fatal_error is None
    # ラベル (重複排除、順不同なのでsetで比較)
    assert set(result.created_labels) == {"bug", "feature", "urgent"}
    assert result.failed_labels == []
    # マイルストーン
    assert result.milestone_name == "Sprint 1"
    assert result.milestone_id == 123
    assert result.milestone_creation_error is None
    # Issue結果
    assert result.issue_result == DUMMY_ISSUE_RESULT
    # プロジェクト連携結果
    assert result.project_items_added_count == 2
    assert result.project_items_failed == []

    # Assert: 各依存コンポーネントが期待通り呼ばれたか検証
    mock_github_client.gh.rest.users.get_authenticated.assert_not_called()  # owner指定ありなので呼ばれない
    mock_create_repo_uc.execute.assert_called_once_with(EXPECTED_REPO)  # repo名のみ渡す
    
    # ラベル作成呼び出し (順不同でOK)
    mock_github_client.create_label.assert_has_calls([
        call(EXPECTED_OWNER, EXPECTED_REPO, "bug"),
        call(EXPECTED_OWNER, EXPECTED_REPO, "feature"),
        call(EXPECTED_OWNER, EXPECTED_REPO, "urgent"),
    ], any_order=True)
    assert mock_github_client.create_label.call_count == 3
    
    # マイルストーン作成呼び出し
    mock_github_client.create_milestone.assert_called_once_with(EXPECTED_OWNER, EXPECTED_REPO, "Sprint 1")
    
    # プロジェクト検索呼び出し
    mock_github_client.find_project_v2_node_id.assert_called_once_with(EXPECTED_OWNER, DUMMY_PROJECT_NAME)
    
    # Issue作成Use Case呼び出し
    mock_create_issues_uc.execute.assert_called_once_with(DUMMY_PARSED_DATA_WITH_DETAILS, EXPECTED_OWNER, EXPECTED_REPO)
    
    # プロジェクト追加呼び出し
    mock_github_client.add_item_to_project_v2.assert_has_calls([
        call("PROJECT_NODE_ID", "NODE_ID_1"),
        call("PROJECT_NODE_ID", "NODE_ID_2"),
    ])
    assert mock_github_client.add_item_to_project_v2.call_count == 2

def test_execute_success_repo_name_only(create_resources_use_case: CreateGitHubResourcesUseCase, mock_github_client, mock_create_repo_uc, mock_create_issues_uc):
    """正常系: repo名のみ指定され、ownerをAPIで取得して成功"""
    # Arrange: モックの設定
    expected_repo_url = f"https://github.com/{EXPECTED_AUTH_USER}/{DUMMY_REPO_NAME_ONLY}"
    mock_create_repo_uc.execute.return_value = expected_repo_url
    mock_create_issues_uc.execute.return_value = DUMMY_ISSUE_RESULT

    # Act: ParsedRequirementDataを直接渡す
    result = create_resources_use_case.execute(
        parsed_data=DUMMY_PARSED_DATA_WITH_DETAILS,
        repo_name_input=DUMMY_REPO_NAME_ONLY,
        project_name=DUMMY_PROJECT_NAME
    )

    # 結果オブジェクトの検証
    assert isinstance(result, CreateGitHubResourcesResult)
    assert result.repository_url == expected_repo_url
    
    # 依存コンポーネントの検証
    mock_github_client.gh.rest.users.get_authenticated.assert_called_once()  # owner取得のために呼ばれる
    mock_create_repo_uc.execute.assert_called_once_with(DUMMY_REPO_NAME_ONLY)
    mock_create_issues_uc.execute.assert_called_once_with(DUMMY_PARSED_DATA_WITH_DETAILS, EXPECTED_AUTH_USER, DUMMY_REPO_NAME_ONLY)
    
    # ラベル作成呼び出し
    mock_github_client.create_label.assert_has_calls([
        call(EXPECTED_AUTH_USER, DUMMY_REPO_NAME_ONLY, "bug"),
        call(EXPECTED_AUTH_USER, DUMMY_REPO_NAME_ONLY, "feature"),
        call(EXPECTED_AUTH_USER, DUMMY_REPO_NAME_ONLY, "urgent"),
    ], any_order=True)

def test_execute_dry_run(create_resources_use_case: CreateGitHubResourcesUseCase, mock_github_client, mock_create_repo_uc, mock_create_issues_uc):
    """Dry run モードの場合、GitHub操作とIssue作成UseCaseが呼ばれない"""
    # Act: dry_run=Trueを指定
    result = create_resources_use_case.execute(
        parsed_data=DUMMY_PARSED_DATA_WITH_DETAILS,
        repo_name_input=DUMMY_REPO_NAME_FULL,
        project_name=DUMMY_PROJECT_NAME,
        dry_run=True
    )

    # 結果オブジェクトの検証
    assert isinstance(result, CreateGitHubResourcesResult)
    assert "Dry Run" in result.repository_url
    assert result.project_name == DUMMY_PROJECT_NAME
    # Dry Run結果の検証
    assert set(result.created_labels) == {"bug", "feature", "urgent"}
    assert result.milestone_name == "Sprint 1"
    assert result.issue_result is not None
    assert len(result.issue_result.created_issue_details) == 3  # すべてのIssueがDry Run表示用に作られている
    
    # 依存コンポーネントの検証
    mock_github_client.gh.rest.users.get_authenticated.assert_not_called()  # owner指定あり
    # GitHub操作は行われない
    mock_create_repo_uc.execute.assert_not_called()
    mock_create_issues_uc.execute.assert_not_called()
    mock_github_client.create_label.assert_not_called()
    mock_github_client.create_milestone.assert_not_called()
    mock_github_client.find_project_v2_node_id.assert_not_called()
    mock_github_client.add_item_to_project_v2.assert_not_called()

def test_execute_label_creation_fails(create_resources_use_case: CreateGitHubResourcesUseCase, mock_github_client, mock_create_repo_uc, mock_create_issues_uc):
    """ラベル作成で一部失敗した場合、記録され、処理は続行する"""
    mock_create_repo_uc.execute.return_value = DUMMY_REPO_URL
    
    # "feature" ラベルの作成だけ失敗させる
    mock_label_error = GitHubClientError("Label creation failed")
    def create_label_side_effect(owner, repo, name):
        if name == "feature":
            raise mock_label_error
        return True  # 他は成功
    mock_github_client.create_label.side_effect = create_label_side_effect

    result = create_resources_use_case.execute(
        parsed_data=DUMMY_PARSED_DATA_WITH_DETAILS,
        repo_name_input=DUMMY_REPO_NAME_FULL,
        project_name=DUMMY_PROJECT_NAME
    )

    # 結果オブジェクトの検証
    assert result.fatal_error is None
    assert set(result.created_labels) == {"bug", "urgent"}  # 成功したものだけ
    assert result.failed_labels == [("feature", str(mock_label_error))]
    
    # 後続の処理が実行されていることを確認
    mock_github_client.create_milestone.assert_called()
    mock_create_issues_uc.execute.assert_called()
    mock_github_client.find_project_v2_node_id.assert_called()
    mock_github_client.add_item_to_project_v2.assert_called()  # Issueが作成されていれば呼ばれる

def test_execute_milestone_creation_fails(create_resources_use_case: CreateGitHubResourcesUseCase, mock_github_client, mock_create_repo_uc, mock_create_issues_uc):
    """マイルストーン作成で失敗した場合、記録され、処理は続行する"""
    mock_create_repo_uc.execute.return_value = DUMMY_REPO_URL
    
    # マイルストーン作成を失敗させる
    mock_milestone_error = GitHubClientError("Milestone creation failed")
    mock_github_client.create_milestone.side_effect = mock_milestone_error

    result = create_resources_use_case.execute(
        parsed_data=DUMMY_PARSED_DATA_WITH_DETAILS,
        repo_name_input=DUMMY_REPO_NAME_FULL,
        project_name=DUMMY_PROJECT_NAME
    )

    # 結果オブジェクトの検証
    assert result.fatal_error is None
    assert result.milestone_name == "Sprint 1"
    assert result.milestone_id is None
    assert result.milestone_creation_error == str(mock_milestone_error)
    
    # 後続の処理が実行されていることを確認
    mock_create_issues_uc.execute.assert_called()
    mock_github_client.find_project_v2_node_id.assert_called()

def test_execute_project_not_found(create_resources_use_case: CreateGitHubResourcesUseCase, mock_github_client, mock_create_repo_uc, mock_create_issues_uc):
    """プロジェクトが見つからない場合、記録され、アイテム追加はスキップされる"""
    mock_create_repo_uc.execute.return_value = DUMMY_REPO_URL
    mock_github_client.find_project_v2_node_id.return_value = None  # プロジェクトが見つからない

    result = create_resources_use_case.execute(
        parsed_data=DUMMY_PARSED_DATA_WITH_DETAILS,
        repo_name_input=DUMMY_REPO_NAME_FULL,
        project_name=DUMMY_PROJECT_NAME
    )

    # 結果オブジェクトの検証
    assert result.fatal_error is None
    assert result.project_name == DUMMY_PROJECT_NAME
    assert result.project_node_id is None
    assert result.project_items_added_count == 0
    
    # アイテム追加が呼ばれていないことを確認
    mock_github_client.add_item_to_project_v2.assert_not_called()
    # 他の処理は実行される
    assert result.repository_url is not None
    assert len(result.created_labels) > 0
    assert result.issue_result is not None

def test_execute_project_find_error(create_resources_use_case: CreateGitHubResourcesUseCase, mock_github_client, mock_create_repo_uc, mock_create_issues_uc):
    """プロジェクト検索でエラーが発生した場合、処理は続行する"""
    mock_create_repo_uc.execute.return_value = DUMMY_REPO_URL
    
    # プロジェクト検索でエラーが発生
    mock_project_error = GitHubClientError("Project search failed")
    mock_github_client.find_project_v2_node_id.side_effect = mock_project_error

    result = create_resources_use_case.execute(
        parsed_data=DUMMY_PARSED_DATA_WITH_DETAILS,
        repo_name_input=DUMMY_REPO_NAME_FULL,
        project_name=DUMMY_PROJECT_NAME
    )

    # 結果オブジェクトの検証
    assert result.fatal_error is None
    assert result.project_name == DUMMY_PROJECT_NAME
    assert result.project_node_id is None
    assert result.project_items_added_count == 0
    
    # アイテム追加が呼ばれていないことを確認
    mock_github_client.add_item_to_project_v2.assert_not_called()
    # 他の処理は実行される
    assert result.repository_url is not None
    assert len(result.created_labels) > 0
    assert result.issue_result is not None

def test_execute_add_item_fails(create_resources_use_case: CreateGitHubResourcesUseCase, mock_github_client, mock_create_repo_uc, mock_create_issues_uc):
    """プロジェクトへのアイテム追加で一部失敗した場合、記録される"""
    mock_create_repo_uc.execute.return_value = DUMMY_REPO_URL
    
    # Issue作成結果を設定
    mock_issue_result = CreateIssuesResult(
        created_issue_details=[("url/1", "NODE_ID_1"), ("url/2", "NODE_ID_2")]
    )
    mock_create_issues_uc.execute.return_value = mock_issue_result
    
    # 2番目のアイテム追加だけ失敗させる
    mock_add_error = GitHubResourceNotFoundError("Item not found")
    mock_github_client.add_item_to_project_v2.side_effect = ["ITEM_ID_1", mock_add_error]

    result = create_resources_use_case.execute(
        parsed_data=DUMMY_PARSED_DATA_WITH_DETAILS,
        repo_name_input=DUMMY_REPO_NAME_FULL,
        project_name=DUMMY_PROJECT_NAME
    )

    # 結果オブジェクトの検証
    assert result.fatal_error is None
    assert result.project_items_added_count == 1  # 1件は成功
    assert result.project_items_failed == [("NODE_ID_2", str(mock_add_error))]
    assert mock_github_client.add_item_to_project_v2.call_count == 2

def test_execute_no_project_specified(create_resources_use_case: CreateGitHubResourcesUseCase, mock_github_client, mock_create_repo_uc, mock_create_issues_uc):
    """プロジェクト名が指定されなかった場合、プロジェクト関連処理はスキップされる"""
    mock_create_repo_uc.execute.return_value = DUMMY_REPO_URL

    result = create_resources_use_case.execute(
        parsed_data=DUMMY_PARSED_DATA_WITH_DETAILS,
        repo_name_input=DUMMY_REPO_NAME_FULL,
        project_name=None  # プロジェクト名なし
    )

    # 結果オブジェクトの検証
    assert result.fatal_error is None
    assert result.project_name is None
    assert result.project_node_id is None
    assert result.project_items_added_count == 0
    assert result.project_items_failed == []
    
    # プロジェクト関連のAPIが呼ばれないことを確認
    mock_github_client.find_project_v2_node_id.assert_not_called()
    mock_github_client.add_item_to_project_v2.assert_not_called()
    # 他の処理は実行される
    assert result.repository_url is not None
    assert len(result.created_labels) > 0
    assert result.issue_result is not None

def test_execute_no_labels_in_issues(create_resources_use_case: CreateGitHubResourcesUseCase, mock_github_client, mock_create_repo_uc, mock_create_issues_uc):
    """Issueにラベルが含まれない場合、ラベル作成処理はスキップされる"""
    # ラベル・マイルストーンなしのIssueデータを準備
    mock_parsed_data = ParsedRequirementData(
        issues=[IssueData(title="Issue No Label", body="Body")]
    )
    mock_create_repo_uc.execute.return_value = DUMMY_REPO_URL

    result = create_resources_use_case.execute(
        parsed_data=mock_parsed_data, 
        repo_name_input=DUMMY_REPO_NAME_FULL
    )

    # ラベル作成が呼ばれないことを確認
    mock_github_client.create_label.assert_not_called()
    # マイルストーン作成が呼ばれないことを確認
    mock_github_client.create_milestone.assert_not_called()
    # 他の処理は実行される
    assert result.repository_url is not None
    assert result.created_labels == []
    assert result.milestone_name is None
    assert result.issue_result is not None

def test_execute_repo_creation_error(create_resources_use_case: CreateGitHubResourcesUseCase, mock_create_repo_uc, mock_create_issues_uc):
    """リポジトリ作成でエラーが発生した場合、処理が中断し例外が送出される"""
    # リポジトリ作成エラー
    mock_error = GitHubValidationError("Repo exists")
    mock_create_repo_uc.execute.side_effect = mock_error

    with pytest.raises(GitHubValidationError):
        result = create_resources_use_case.execute(
            parsed_data=DUMMY_PARSED_DATA_WITH_DETAILS,
            repo_name_input=DUMMY_REPO_NAME_FULL, 
            project_name=DUMMY_PROJECT_NAME
        )
        assert result.fatal_error is not None

    mock_create_repo_uc.execute.assert_called_once()  # Repo作成は試みられる
    mock_create_issues_uc.execute.assert_not_called()  # Issue作成は呼ばれない

def test_execute_issue_creation_error(create_resources_use_case: CreateGitHubResourcesUseCase, mock_create_repo_uc, mock_create_issues_uc):
    """Issue作成UseCaseでエラーが発生した場合、例外が送出される"""
    mock_create_repo_uc.execute.return_value = DUMMY_REPO_URL
    mock_error = GitHubClientError("Issue creation failed")
    mock_create_issues_uc.execute.side_effect = mock_error

    with pytest.raises(GitHubClientError):
        result = create_resources_use_case.execute(
            parsed_data=DUMMY_PARSED_DATA_WITH_DETAILS,
            repo_name_input=DUMMY_REPO_NAME_FULL, 
            project_name=DUMMY_PROJECT_NAME
        )
        assert result.fatal_error is not None

    mock_create_repo_uc.execute.assert_called_once()  # Repo作成は試みられる
    mock_create_issues_uc.execute.assert_called_once()  # Issue作成は試みられる

def test_get_owner_repo_invalid_format(create_resources_use_case: CreateGitHubResourcesUseCase):
    """_get_owner_repo が不正な形式を弾くか"""
    with pytest.raises(ValueError, match="Invalid repository name format"):
        create_resources_use_case._get_owner_repo("owner/")  # repo名がない
    with pytest.raises(ValueError, match="Invalid repository name format"):
        create_resources_use_case._get_owner_repo("/repo")  # owner名がない

def test_get_owner_repo_api_fails(create_resources_use_case: CreateGitHubResourcesUseCase, mock_github_client):
    """認証ユーザー取得APIが失敗した場合にエラーになるか"""
    # モック設定: get_authenticated がエラーを送出
    mock_api_error = GitHubAuthenticationError("API Failed")
    mock_github_client.gh.rest.users.get_authenticated.side_effect = mock_api_error

    with pytest.raises(GitHubAuthenticationError):
         # repo名のみを指定して _get_owner_repo が内部で呼ばれる execute を実行
         create_resources_use_case.execute(
             parsed_data=DUMMY_PARSED_DATA_WITH_DETAILS,
             repo_name_input=DUMMY_REPO_NAME_ONLY, 
             project_name=DUMMY_PROJECT_NAME
         )
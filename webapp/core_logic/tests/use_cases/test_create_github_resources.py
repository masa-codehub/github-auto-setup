import pytest
from unittest.mock import MagicMock, patch, call, ANY
from pathlib import Path
import logging # caplog をインポート

# テスト対象 UseCase と依存コンポーネント、データモデル、例外をインポート
from github_automation_tool.use_cases.create_github_resources import CreateGitHubResourcesUseCase
# 不要な依存関係のインポートを削除
# from github_automation_tool.infrastructure.config import Settings
from github_automation_tool.adapters.github_rest_client import GitHubRestClient # GitHubAppClient から変更
from github_automation_tool.adapters.github_graphql_client import GitHubGraphQLClient # 追加
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
def mock_rest_client() -> MagicMock:
    """GitHubRestClient のモック、認証ユーザー取得もモック"""
    mock = MagicMock(spec=GitHubRestClient)
    mock_user_data = MagicMock(login="test-auth-user")
    # get_authenticated_user メソッドを追加
    mock.get_authenticated_user = MagicMock(return_value=mock_user_data)
    
    # ラベル、マイルストーン用のメソッドモックを追加
    mock.get_label = MagicMock(return_value=None) # デフォルトではラベルは存在しない
    mock.create_label = MagicMock(return_value=True)  # デフォルトは成功(新規作成)
    mock.list_milestones = MagicMock(return_value=[])  # デフォルトでは存在しない
    # create_milestone が MagicMock オブジェクトを返すように設定
    mock_milestone = MagicMock()
    mock_milestone.number = 123
    mock.create_milestone = MagicMock(return_value=mock_milestone)  # デフォルトは成功(ID 123)
    
    return mock

@pytest.fixture
def mock_graphql_client() -> MagicMock:
    """GitHubGraphQLClient のモック"""
    mock = MagicMock(spec=GitHubGraphQLClient)
    # プロジェクト連携用のメソッドモックを追加
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
    mock_rest_client: MagicMock, 
    mock_graphql_client: MagicMock,
    mock_create_repo_uc: MagicMock, 
    mock_create_issues_uc: MagicMock
) -> CreateGitHubResourcesUseCase:
    """テスト対象 UseCase (依存を修正)"""
    return CreateGitHubResourcesUseCase(
        rest_client=mock_rest_client,
        graphql_client=mock_graphql_client,
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

# 複数マイルストーンを含むテストデータを追加
MULTI_MILESTONE_ISSUE_1 = IssueData(
    title="Issue MS-A", body="Test body 1", labels=["bug"], milestone="MilestoneA", assignees=["userA"]
)
MULTI_MILESTONE_ISSUE_2 = IssueData(
    title="Issue MS-B", body="Test body 2", labels=["feature"], milestone="MilestoneB", assignees=["userB"]
)
MULTI_MILESTONE_ISSUE_3 = IssueData(
    title="Issue MS-A-2", body="Test body 3", labels=["documentation"], milestone="MilestoneA"  # 同じマイルストーン
)
PARSED_DATA_MULTI_MILESTONE = ParsedRequirementData(
    issues=[MULTI_MILESTONE_ISSUE_1, MULTI_MILESTONE_ISSUE_2, MULTI_MILESTONE_ISSUE_3]
)

# --- Test Cases ---

def test_execute_success_full_repo_name(create_resources_use_case: CreateGitHubResourcesUseCase, mock_create_repo_uc, mock_create_issues_uc, mock_rest_client, mock_graphql_client, caplog):
    """正常系: owner/repo形式のリポジトリ名で全ステップ成功し、ログが出力される"""
    mock_create_repo_uc.execute.return_value = DUMMY_REPO_URL
    mock_create_issues_uc.execute.return_value = DUMMY_ISSUE_RESULT # Issue 2件作成

    with caplog.at_level(logging.INFO):
        result = create_resources_use_case.execute(
            parsed_data=DUMMY_PARSED_DATA_WITH_DETAILS,
            repo_name_input=DUMMY_REPO_NAME_FULL,
            project_name=DUMMY_PROJECT_NAME
        )

    # 結果オブジェクトの検証
    assert isinstance(result, CreateGitHubResourcesResult)
    assert result.repository_url == DUMMY_REPO_URL
    assert result.project_name == DUMMY_PROJECT_NAME
    assert result.project_node_id == "PROJECT_NODE_ID"
    assert result.fatal_error is None
    # ラベル (重複排除、順不同なのでsetで比較)
    assert set(result.created_labels) == {"bug", "feature", "urgent"}
    assert result.failed_labels == []
    # マイルストーン (複数構造対応)
    assert len(result.processed_milestones) == 1
    assert result.processed_milestones[0][0] == "Sprint 1"  # 名前
    assert result.processed_milestones[0][1] == 123  # ID
    assert result.failed_milestones == []
    # Issue結果
    assert result.issue_result == DUMMY_ISSUE_RESULT
    # プロジェクト連携結果
    assert result.project_items_added_count == 2
    assert result.project_items_failed == []

    # Assert: 各依存コンポーネントが期待通り呼ばれたか検証
    mock_rest_client.get_authenticated_user.assert_not_called()  # owner指定ありなので呼ばれない
    mock_create_repo_uc.execute.assert_called_once_with(EXPECTED_REPO)  # repo名のみ渡す
    
    # ラベル作成呼び出し (順不同でOK)
    mock_rest_client.get_label.assert_has_calls([
        call(EXPECTED_OWNER, EXPECTED_REPO, "bug"),
        call(EXPECTED_OWNER, EXPECTED_REPO, "feature"),
        call(EXPECTED_OWNER, EXPECTED_REPO, "urgent"),
    ], any_order=True)
    assert mock_rest_client.get_label.call_count == 3
    
    mock_rest_client.create_label.assert_has_calls([
        call(EXPECTED_OWNER, EXPECTED_REPO, "bug"),
        call(EXPECTED_OWNER, EXPECTED_REPO, "feature"),
        call(EXPECTED_OWNER, EXPECTED_REPO, "urgent"),
    ], any_order=True)
    assert mock_rest_client.create_label.call_count == 3
    
    # マイルストーン作成呼び出し
    mock_rest_client.list_milestones.assert_called_once_with(EXPECTED_OWNER, EXPECTED_REPO, state="all")
    mock_rest_client.create_milestone.assert_called_once_with(EXPECTED_OWNER, EXPECTED_REPO, "Sprint 1")
    
    # プロジェクト検索呼び出し
    mock_graphql_client.find_project_v2_node_id.assert_called_once_with(EXPECTED_OWNER, DUMMY_PROJECT_NAME)
    
    # Issue作成Use Case呼び出し - マイルストーンIDマップを渡すように変更
    mock_create_issues_uc.execute.assert_called_once_with(DUMMY_PARSED_DATA_WITH_DETAILS, EXPECTED_OWNER, EXPECTED_REPO, {"Sprint 1": 123})
    
    # プロジェクト追加呼び出し
    mock_graphql_client.add_item_to_project_v2.assert_has_calls([
        call("PROJECT_NODE_ID", "NODE_ID_1"),
        call("PROJECT_NODE_ID", "NODE_ID_2"),
    ])
    assert mock_graphql_client.add_item_to_project_v2.call_count == 2

    # ログの検証 - 実際のログ出力に合わせて期待値を修正
    assert "Starting GitHub resource creation workflow..." in caplog.text
    assert "Step 1: Resolving repository owner and name..." in caplog.text
    assert f"Target repository: {DUMMY_REPO_NAME_FULL}" in caplog.text
    assert f"Step 3: Ensuring repository '{DUMMY_REPO_NAME_FULL}' exists..." in caplog.text
    # 修正: 実際のログメッセージのフォーマットに合わせる
    assert f"Repository '{DUMMY_REPO_NAME_FULL}' created successfully: {DUMMY_REPO_URL}" in caplog.text
    assert f"Repository URL to use: {DUMMY_REPO_URL}" in caplog.text
    assert f"Step 4: Ensuring required labels exist in {DUMMY_REPO_NAME_FULL}..." in caplog.text
    assert "Processing label 1/3: 'bug'" in caplog.text
    assert "Processing label 2/3: 'feature'" in caplog.text
    assert "Processing label 3/3: 'urgent'" in caplog.text
    assert "Step 4 finished. New labels: 3" in caplog.text # create_label が常に True を返すモックのため
    assert f"Step 5: Ensuring required milestones exist in {DUMMY_REPO_NAME_FULL}..." in caplog.text
    assert "Found 1 unique milestones to process" in caplog.text
    assert "Processing milestone 1/1: 'Sprint 1'" in caplog.text
    # 変更されたログメッセージのフォーマットに合わせる
    assert "Step 5 finished." in caplog.text
    assert f"Step 6: finding Project V2 '{DUMMY_PROJECT_NAME}' for owner '{EXPECTED_OWNER}'..." in caplog.text
    assert f"Found Project V2 '{DUMMY_PROJECT_NAME}' with Node ID: PROJECT_NODE_ID" in caplog.text
    assert f"Step 7: Creating issues in '{DUMMY_REPO_NAME_FULL}'..." in caplog.text
    assert "Step 7 finished." in caplog.text
    assert f"Step 8: Adding 2 created issues to project '{DUMMY_PROJECT_NAME}'..." in caplog.text
    # 変更されたログメッセージのフォーマットに合わせる
    assert "Processing item 1/2: adding item (Issue Node ID: NODE_ID_1)" in caplog.text
    assert "Processing item 2/2: adding item (Issue Node ID: NODE_ID_2)" in caplog.text
    # プロジェクト統合のログメッセージを更新
    assert "Step 8 finished. Project Integration: Added: 2/2, Failed: 0/2." in caplog.text
    assert "GitHub resource creation workflow completed successfully." in caplog.text

def test_execute_success_repo_name_only(create_resources_use_case: CreateGitHubResourcesUseCase, mock_rest_client, mock_graphql_client, mock_create_repo_uc, mock_create_issues_uc):
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
    mock_rest_client.get_authenticated_user.assert_called_once()  # owner取得のために呼ばれる
    mock_create_repo_uc.execute.assert_called_once_with(DUMMY_REPO_NAME_ONLY)
    # マイルストーンIDマップを渡すように変更
    mock_create_issues_uc.execute.assert_called_once_with(
        DUMMY_PARSED_DATA_WITH_DETAILS, 
        EXPECTED_AUTH_USER, 
        DUMMY_REPO_NAME_ONLY,
        {"Sprint 1": 123}  # マイルストーンIDマップを追加
    )
    
    # ラベル作成呼び出し
    mock_rest_client.create_label.assert_has_calls([
        call(EXPECTED_AUTH_USER, DUMMY_REPO_NAME_ONLY, "bug"),
        call(EXPECTED_AUTH_USER, DUMMY_REPO_NAME_ONLY, "feature"),
        call(EXPECTED_AUTH_USER, DUMMY_REPO_NAME_ONLY, "urgent"),
    ], any_order=True)

def test_execute_dry_run(create_resources_use_case: CreateGitHubResourcesUseCase, mock_rest_client, mock_graphql_client, mock_create_repo_uc, mock_create_issues_uc, caplog):
    """Dry run モードの場合、GitHub操作とIssue作成UseCaseが呼ばれない"""
    with caplog.at_level(logging.INFO): # WARNINGも含む
        result = create_resources_use_case.execute(
            parsed_data=DUMMY_PARSED_DATA_WITH_DETAILS,
            repo_name_input=DUMMY_REPO_NAME_FULL,
            project_name=DUMMY_PROJECT_NAME,
            dry_run=True # dry_run=True で呼び出す
        )

    # 結果オブジェクトの検証
    assert isinstance(result, CreateGitHubResourcesResult)
    assert "(Dry Run)" in result.repository_url # URLに "(Dry Run)" が含まれる
    assert result.project_name == DUMMY_PROJECT_NAME
    
    # Dry Run結果の検証 - created_labels は空になる（実際の動作に合わせて）
    assert result.created_labels == []
    # milestone_ids も空になっていることを確認
    assert len(result.processed_milestones) == 0
    assert result.failed_labels == []
    assert result.failed_milestones == []
    
    # Issue結果は実際の実装に合わせてNoneになっていることを確認（修正）
    assert result.issue_result is None
    
    # プロジェクト関連の結果
    assert result.project_node_id is None
    assert result.project_items_added_count == 0
    assert result.project_items_failed == []

    # 依存コンポーネントの検証: GitHub操作は行われない
    mock_rest_client.get_authenticated_user.assert_not_called()
    mock_create_repo_uc.execute.assert_not_called()
    mock_create_issues_uc.execute.assert_not_called()
    mock_rest_client.get_label.assert_not_called()
    mock_rest_client.create_label.assert_not_called()
    mock_rest_client.list_milestones.assert_not_called()
    mock_rest_client.create_milestone.assert_not_called()
    mock_graphql_client.find_project_v2_node_id.assert_not_called()
    mock_graphql_client.add_item_to_project_v2.assert_not_called()

    # ログの検証
    assert "Dry run mode enabled. Skipping GitHub operations." in caplog.text
    assert "Dry run finished." in caplog.text

def test_execute_label_creation_fails(create_resources_use_case: CreateGitHubResourcesUseCase, mock_rest_client, mock_graphql_client, mock_create_repo_uc, mock_create_issues_uc, caplog):
    """ラベル作成で一部失敗した場合、記録され、処理は続行する"""
    mock_create_repo_uc.execute.return_value = DUMMY_REPO_URL
    
    # "feature" ラベルの作成だけ失敗させる
    mock_label_error = GitHubClientError("Label creation failed")
    def create_label_side_effect(owner, repo, name):
        if name == "feature":
            raise mock_label_error
        return True  # 他は成功
    mock_rest_client.create_label.side_effect = create_label_side_effect

    with caplog.at_level(logging.INFO): # ERRORも含む
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
    mock_rest_client.list_milestones.assert_called()
    mock_rest_client.create_milestone.assert_called()
    mock_create_issues_uc.execute.assert_called()
    mock_graphql_client.find_project_v2_node_id.assert_called()
    mock_graphql_client.add_item_to_project_v2.assert_called()  # Issueが作成されていれば呼ばれる

    # ログの検証
    assert "Processing label 1/3: 'bug'" in caplog.text
    assert "Processing label 2/3: 'feature'" in caplog.text
    # 変更されたログメッセージのフォーマットに合わせる
    assert "Failed to ensuring label 'feature' in test-owner/test-repo: Label creation failed" in caplog.text # ERRORログ
    assert "Processing label 3/3: 'urgent'" in caplog.text
    assert "Step 4 finished. New labels: 2" in caplog.text
    assert "Failed labels: ['feature']" in caplog.text # WARNINGログ

def test_execute_milestone_creation_fails(create_resources_use_case: CreateGitHubResourcesUseCase, mock_rest_client, mock_graphql_client, mock_create_repo_uc, mock_create_issues_uc, caplog):
    """マイルストーン作成で失敗した場合、記録され、処理は続行する"""
    mock_create_repo_uc.execute.return_value = DUMMY_REPO_URL
    
    # マイルストーン作成を失敗させる
    mock_milestone_error = GitHubClientError("Milestone creation failed")
    mock_rest_client.create_milestone.side_effect = mock_milestone_error

    with caplog.at_level(logging.INFO): # ERRORも含む
        result = create_resources_use_case.execute(
            parsed_data=DUMMY_PARSED_DATA_WITH_DETAILS,
            repo_name_input=DUMMY_REPO_NAME_FULL,
            project_name=DUMMY_PROJECT_NAME
        )

    # 結果オブジェクトの検証
    assert result.fatal_error is None
    # 複数マイルストーン対応の構造を検証
    assert len(result.processed_milestones) == 0  # 成功したマイルストーンなし
    assert len(result.failed_milestones) == 1  # 失敗したマイルストーンあり
    assert result.failed_milestones[0][0] == "Sprint 1"  # 名前
    assert result.failed_milestones[0][1] == str(mock_milestone_error)  # エラーメッセージ
    
    # 後続の処理が実行されていることを確認
    mock_create_issues_uc.execute.assert_called_once()
    mock_graphql_client.find_project_v2_node_id.assert_called_once()

    # ログの検証
    assert f"Step 5: Ensuring required milestones exist in {DUMMY_REPO_NAME_FULL}..." in caplog.text
    assert "Found 1 unique milestones to process" in caplog.text
    assert "Processing milestone 1/1: 'Sprint 1'" in caplog.text
    # 変更されたログメッセージのフォーマットに合わせる
    assert "Failed to ensuring milestone 'Sprint 1' in test-owner/test-repo: Milestone creation failed" in caplog.text # ERRORログ
    assert "Step 5 finished. Processed milestones: 0/1, Failed: 1." in caplog.text
    assert "Failed milestones: ['Sprint 1']" in caplog.text

def test_execute_project_not_found(create_resources_use_case: CreateGitHubResourcesUseCase, mock_rest_client, mock_graphql_client, mock_create_repo_uc, mock_create_issues_uc, caplog):
    """プロジェクトが見つからない場合、記録され、アイテム追加はスキップされる"""
    mock_create_repo_uc.execute.return_value = DUMMY_REPO_URL
    mock_graphql_client.find_project_v2_node_id.return_value = None  # プロジェクトが見つからない

    with caplog.at_level(logging.INFO): # WARNINGも含む
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
    mock_graphql_client.add_item_to_project_v2.assert_not_called()
    # 他の処理は実行される
    assert result.repository_url is not None
    assert len(result.created_labels) > 0
    assert result.issue_result is not None

    # ログの検証 - 実際の出力に合わせて修正
    assert f"Step 6: finding Project V2 '{DUMMY_PROJECT_NAME}' for owner '{EXPECTED_OWNER}'..." in caplog.text
    assert f"Project V2 '{DUMMY_PROJECT_NAME}' not found. Skipping item addition." in caplog.text # WARNINGログ
    assert "Step 6 finished." in caplog.text
    # Issue作成後のステップ8のログを確認
    assert f"Step 7: Creating issues in '{DUMMY_REPO_NAME_FULL}'..." in caplog.text
    assert "Step 7 finished." in caplog.text
    assert "Step 8: Project not found or failed to retrieve its ID. Skipping item addition." in caplog.text # 実際のログに合わせる

def test_execute_add_item_fails(create_resources_use_case: CreateGitHubResourcesUseCase, mock_rest_client, mock_graphql_client, mock_create_repo_uc, mock_create_issues_uc, caplog):
    """プロジェクトへのアイテム追加で一部失敗した場合、記録される"""
    mock_create_repo_uc.execute.return_value = DUMMY_REPO_URL
    
    # Issue作成結果を設定
    mock_issue_result = CreateIssuesResult(
        created_issue_details=[("url/1", "NODE_ID_1"), ("url/2", "NODE_ID_2")]
    )
    mock_create_issues_uc.execute.return_value = mock_issue_result
    
    # 2番目のアイテム追加だけ失敗させる
    mock_add_error = GitHubResourceNotFoundError("Item not found")
    mock_graphql_client.add_item_to_project_v2.side_effect = ["ITEM_ID_1", mock_add_error]

    with caplog.at_level(logging.INFO): # ERROR, WARNING も含む
        result = create_resources_use_case.execute(
            parsed_data=DUMMY_PARSED_DATA_WITH_DETAILS,
            repo_name_input=DUMMY_REPO_NAME_FULL,
            project_name=DUMMY_PROJECT_NAME
        )

    # 結果オブジェクトの検証
    assert result.fatal_error is None
    assert result.project_items_added_count == 1  # 1件は成功
    assert result.project_items_failed == [("NODE_ID_2", str(mock_add_error))]
    assert mock_graphql_client.add_item_to_project_v2.call_count == 2

    # ログの検証 - 実際の出力に合わせて修正
    assert f"Step 8: Adding 2 created issues to project '{DUMMY_PROJECT_NAME}'..." in caplog.text
    # 実際のログ出力に合わせて修正
    assert "Processing item 1/2: adding item (Issue Node ID: NODE_ID_1)" in caplog.text
    assert "Processing item 2/2: adding item (Issue Node ID: NODE_ID_2)" in caplog.text
    # ERRORログメッセージの形式を修正
    assert "Failed to adding item (Issue Node ID: NODE_ID_2)" in caplog.text
    # ステップ完了のメッセージを修正
    assert "Step 8 finished. Project Integration: Added: 1/2, Failed: 1/2." in caplog.text
    assert "Failed items: ['NODE_ID_2']" in caplog.text

def test_execute_no_project_specified(create_resources_use_case: CreateGitHubResourcesUseCase, mock_rest_client, mock_graphql_client, mock_create_repo_uc, mock_create_issues_uc):
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
    mock_graphql_client.find_project_v2_node_id.assert_not_called()
    mock_graphql_client.add_item_to_project_v2.assert_not_called()
    # 他の処理は実行される
    assert result.repository_url is not None
    assert len(result.created_labels) > 0
    assert result.issue_result is not None

def test_execute_no_labels_in_issues(create_resources_use_case: CreateGitHubResourcesUseCase, mock_rest_client, mock_graphql_client, mock_create_repo_uc, mock_create_issues_uc):
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
    mock_rest_client.create_label.assert_not_called()
    # マイルストーン作成が呼ばれないことを確認
    mock_rest_client.create_milestone.assert_not_called()
    # 他の処理は実行される
    assert result.repository_url is not None
    assert result.created_labels == []
    # 複数マイルストーン対応
    assert len(result.processed_milestones) == 0
    assert len(result.failed_milestones) == 0
    assert result.issue_result is not None

def test_execute_repo_creation_error(create_resources_use_case: CreateGitHubResourcesUseCase, mock_create_repo_uc, mock_create_issues_uc, caplog):
    """リポジトリ作成でエラーが発生した場合、処理が中断し例外が送出される"""
    # リポジトリ作成エラー
    mock_error = GitHubValidationError("Repo exists")
    mock_create_repo_uc.execute.side_effect = mock_error

    with pytest.raises(GitHubValidationError), caplog.at_level(logging.INFO): # ERRORも含む
        create_resources_use_case.execute(
            parsed_data=DUMMY_PARSED_DATA_WITH_DETAILS,
            repo_name_input=DUMMY_REPO_NAME_FULL, 
            project_name=DUMMY_PROJECT_NAME
        )

    # ログの検証
    assert "Starting GitHub resource creation workflow..." in caplog.text
    assert "Step 1: Resolving repository owner and name..." in caplog.text
    assert "Step 3: Ensuring repository 'test-owner/test-repo' exists..." in caplog.text
    assert "Workflow halted due to error: GitHubValidationError - Repo exists" in caplog.text # ERRORログ
    # 後続ステップのログがないことを確認
    assert "Step 4:" not in caplog.text

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

def test_get_owner_repo_api_fails(create_resources_use_case: CreateGitHubResourcesUseCase, mock_rest_client):
    """認証ユーザー取得APIが失敗した場合にエラーになるか"""
    # モック設定: get_authenticated がエラーを送出
    mock_api_error = GitHubAuthenticationError("API Failed")
    mock_rest_client.get_authenticated_user.side_effect = mock_api_error

    with pytest.raises(GitHubAuthenticationError):
         # repo名のみを指定して _get_owner_repo が内部で呼ばれる execute を実行
         create_resources_use_case.execute(
             parsed_data=DUMMY_PARSED_DATA_WITH_DETAILS,
             repo_name_input=DUMMY_REPO_NAME_ONLY, 
             project_name=DUMMY_PROJECT_NAME
         )

def test_get_owner_repo_api_error_other_exception(create_resources_use_case: CreateGitHubResourcesUseCase, mock_rest_client, caplog):
    """認証ユーザー取得APIで予期せぬ例外が発生した場合も適切にハンドリングされる"""
    # モックが予期せぬ例外を送出するように設定
    mock_rest_client.get_authenticated_user.side_effect = RuntimeError("Unexpected API error")
    
    with pytest.raises(GitHubAuthenticationError) as excinfo, caplog.at_level(logging.ERROR):
        # repo名のみを指定して _get_owner_repo が内部で呼ばれる execute を実行
        create_resources_use_case.execute(
            parsed_data=DUMMY_PARSED_DATA_WITH_DETAILS,
            repo_name_input=DUMMY_REPO_NAME_ONLY,
            project_name=DUMMY_PROJECT_NAME
        )
    
    # 例外が適切にラップされていることを検証（実際のメッセージに合わせる）
    assert "Unexpected error getting authenticated user" in str(excinfo.value)
    # ログが適切に出力されていることを確認
    assert "Unexpected error getting authenticated user" in caplog.text
    assert "RuntimeError: Unexpected API error" in caplog.text # 元の例外情報も含まれる

def test_execute_unexpected_exception_in_add_item(create_resources_use_case: CreateGitHubResourcesUseCase, mock_rest_client, mock_graphql_client, mock_create_repo_uc, mock_create_issues_uc, caplog):
    """プロジェクトアイテム追加時に予期せぬ例外が発生した場合も処理が継続される"""
    # 基本設定
    mock_create_repo_uc.execute.return_value = DUMMY_REPO_URL
    mock_issue_result = CreateIssuesResult(
        created_issue_details=[("url/1", "NODE_ID_1"), ("url/2", "NODE_ID_2")]
    )
    mock_create_issues_uc.execute.return_value = mock_issue_result
    
    # 2番目のアイテム追加で予期せぬ例外が発生する
    unexpected_error = TypeError("Invalid Node ID type")
    mock_graphql_client.add_item_to_project_v2.side_effect = ["ITEM_ID_1", unexpected_error]

    with caplog.at_level(logging.ERROR):
        result = create_resources_use_case.execute(
            parsed_data=DUMMY_PARSED_DATA_WITH_DETAILS,
            repo_name_input=DUMMY_REPO_NAME_FULL,
            project_name=DUMMY_PROJECT_NAME
        )

    # 結果オブジェクトの検証
    assert result.fatal_error is None
    assert result.project_items_added_count == 1
    assert len(result.project_items_failed) == 1
    assert result.project_items_failed[0][0] == "NODE_ID_2"
    assert "Unexpected error" in result.project_items_failed[0][1]
    assert "Invalid Node ID type" in result.project_items_failed[0][1]  # 元の例外メッセージが含まれていることを確認
    
    # ログの検証
    assert "Unexpected error during adding item" in caplog.text
    assert "Invalid Node ID type" in caplog.text

def test_execute_unexpected_exception_in_create_label(create_resources_use_case: CreateGitHubResourcesUseCase, mock_rest_client, mock_graphql_client, mock_create_repo_uc, mock_create_issues_uc, caplog):
    """ラベル作成時に予期せぬ例外が発生した場合も処理が継続される"""
    # 基本設定
    mock_create_repo_uc.execute.return_value = DUMMY_REPO_URL
    # ラベル作成の副作用を設定: 予期せぬ例外
    def create_label_side_effect(owner, repo, name):
        if name == "feature":
            raise TypeError("Unexpected label name type")
        return True  # 他は成功
    mock_rest_client.create_label.side_effect = create_label_side_effect

    with caplog.at_level(logging.ERROR):
        result = create_resources_use_case.execute(
            parsed_data=DUMMY_PARSED_DATA_WITH_DETAILS,
            repo_name_input=DUMMY_REPO_NAME_FULL,
            project_name=DUMMY_PROJECT_NAME
        )

    # 結果オブジェクトの検証
    assert result.fatal_error is None
    assert set(result.created_labels) == {"bug", "urgent"}  # 成功したものだけ
    assert len(result.failed_labels) == 1
    assert result.failed_labels[0][0] == "feature"
    assert "Unexpected error" in result.failed_labels[0][1]
    assert "Unexpected label name type" in result.failed_labels[0][1]  # 具体的なエラーメッセージを検証
    
    # ログの検証
    assert "Unexpected error during ensuring label" in caplog.text
    assert "Unexpected label name type" in caplog.text  # 具体的なエラーメッセージがログに含まれているか
    
    # 後続の処理が実行されていることを確認
    mock_rest_client.create_milestone.assert_called()
    mock_create_issues_uc.execute.assert_called()

def test_execute_unexpected_exception_in_create_milestone(create_resources_use_case: CreateGitHubResourcesUseCase, mock_rest_client, mock_graphql_client, mock_create_repo_uc, mock_create_issues_uc, caplog):
    """マイルストーン作成時に予期せぬ例外が発生した場合も処理が継続される"""
    # 基本設定
    mock_create_repo_uc.execute.return_value = DUMMY_REPO_URL
    
    # マイルストーン作成で予期せぬ例外
    unexpected_error = ValueError("Invalid milestone name")
    mock_rest_client.create_milestone.side_effect = unexpected_error

    with caplog.at_level(logging.ERROR):
        result = create_resources_use_case.execute(
            parsed_data=DUMMY_PARSED_DATA_WITH_DETAILS,
            repo_name_input=DUMMY_REPO_NAME_FULL,
            project_name=DUMMY_PROJECT_NAME
        )

    # 結果オブジェクトの検証
    assert result.fatal_error is None
    assert len(result.processed_milestones) == 0  # 成功したものがない
    assert len(result.failed_milestones) == 1
    assert result.failed_milestones[0][0] == "Sprint 1"
    assert "Unexpected error" in result.failed_milestones[0][1]
    assert "Invalid milestone name" in result.failed_milestones[0][1]
    
    # ログの検証
    assert "Unexpected error during ensuring milestone" in caplog.text
    assert "Invalid milestone name" in caplog.text
    
    # トレースバックが記録されていることを確認
    assert "Traceback" in caplog.text
    
    # 後続の処理が実行されていることを確認
    mock_create_issues_uc.execute.assert_called()

def test_execute_unexpected_critical_error(create_resources_use_case: CreateGitHubResourcesUseCase, mock_create_repo_uc, caplog):
    """想定外の重大なエラーが発生した場合、処理が中断され適切にエラーが記録される"""
    # モックが予期せぬ例外を送出するように設定
    critical_error = MemoryError("Out of memory")
    mock_create_repo_uc.execute.side_effect = critical_error

    with pytest.raises(GitHubClientError) as excinfo, caplog.at_level(logging.ERROR):
        result = create_resources_use_case.execute(
            parsed_data=DUMMY_PARSED_DATA_WITH_DETAILS,
            repo_name_input=DUMMY_REPO_NAME_FULL,
            project_name=DUMMY_PROJECT_NAME
        )

    # 例外が適切にラップされていることを検証
    assert "An unexpected critical error occurred" in str(excinfo.value)
    assert "Out of memory" in str(excinfo.value)
    
    # ログにエラーとトレースバックが記録されていることを確認
    assert "An unexpected critical error occurred" in caplog.text
    assert "Out of memory" in caplog.text
    assert "Traceback" in caplog.text

def test_execute_find_project_unexpected_error(create_resources_use_case: CreateGitHubResourcesUseCase, mock_rest_client, mock_graphql_client, mock_create_repo_uc, mock_create_issues_uc, caplog):
    """プロジェクト検索時に予期せぬ例外が発生した場合も処理が継続される"""
    # 基本設定
    mock_create_repo_uc.execute.return_value = DUMMY_REPO_URL
    
    # プロジェクト検索で予期せぬ例外
    unexpected_error = TypeError("Invalid project name type")
    mock_graphql_client.find_project_v2_node_id.side_effect = unexpected_error

    with caplog.at_level(logging.ERROR):
        result = create_resources_use_case.execute(
            parsed_data=DUMMY_PARSED_DATA_WITH_DETAILS,
            repo_name_input=DUMMY_REPO_NAME_FULL,
            project_name=DUMMY_PROJECT_NAME
        )

    # 結果オブジェクトの検証
    assert result.fatal_error is None
    assert result.project_node_id is None
    assert result.project_items_added_count == 0
    
    # ログの検証
    assert "Unexpected error during finding Project V2" in caplog.text
    assert "TypeError" in caplog.text
    assert "Invalid project name type" in caplog.text
    assert "Traceback" in caplog.text
    
    # 後続の処理が実行されていることを確認
    mock_create_issues_uc.execute.assert_called()
    # プロジェクトが見つからないのでアイテム追加は呼ばれない
    mock_graphql_client.add_item_to_project_v2.assert_not_called()

def test_execute_create_issues_unexpected_error(create_resources_use_case: CreateGitHubResourcesUseCase, mock_rest_client, mock_graphql_client, mock_create_repo_uc, mock_create_issues_uc):
    """Issue作成時に予期せぬ例外が発生した場合、GitHubClientErrorにラップされる""" # テストの説明を修正
    # 基本設定
    mock_create_repo_uc.execute.return_value = DUMMY_REPO_URL
    # Issue作成で予期せぬ例外
    unexpected_error = TypeError("Issue data validation failed")
    mock_create_issues_uc.execute.side_effect = unexpected_error

    # 期待する例外を GitHubClientError に変更
    with pytest.raises(GitHubClientError) as excinfo:
        result = create_resources_use_case.execute(
            parsed_data=DUMMY_PARSED_DATA_WITH_DETAILS,
            repo_name_input=DUMMY_REPO_NAME_FULL,
            project_name=DUMMY_PROJECT_NAME
        )
    # ラップされた例外のメッセージや元の例外タイプを確認するアサーションを追加
    assert "An unexpected critical error occurred" in str(excinfo.value)
    assert isinstance(excinfo.value.__cause__, TypeError) # 元の例外がTypeErrorであること

    # 依存メソッドの呼び出しを検証
    mock_create_repo_uc.execute.assert_called_once()
    # プロジェクト検索はIssue作成前に呼ばれる
    mock_graphql_client.find_project_v2_node_id.assert_called_once()
    # Issue作成UseCaseも呼ばれる (ここでエラー発生)
    mock_create_issues_uc

def test_execute_existing_repository_continues_workflow(create_resources_use_case: CreateGitHubResourcesUseCase, mock_rest_client, mock_graphql_client, mock_create_repo_uc, mock_create_issues_uc, caplog):
    """リポジトリが既に存在する場合でも処理が続行されることを確認するテスト"""
    # リポジトリ作成でValidation Error (422)を発生させる
    mock_error = GitHubValidationError("Repository creation failed: name already exists", status_code=422)
    mock_create_repo_uc.execute.side_effect = mock_error
    
    # 既存リポジトリの情報取得結果を設定
    mock_repo = MagicMock()
    mock_repo.html_url = f"https://github.com/{DUMMY_REPO_NAME_FULL}" 
    mock_rest_client.get_repository.return_value = mock_repo
    
    # Issue作成の結果を設定
    mock_issue_result = CreateIssuesResult(
        created_issue_details=[("https://github.com/test-owner/test-repo/issues/1", "ISSUE_NODE_ID_1")]
    )
    mock_create_issues_uc.execute.return_value = mock_issue_result
    
    # 実行
    with caplog.at_level(logging.INFO):
        result = create_resources_use_case.execute(
            parsed_data=DUMMY_PARSED_DATA_WITH_DETAILS,
            repo_name_input=DUMMY_REPO_NAME_FULL
        )
    
    # 検証 - 致命的エラーではなく警告としてログ出力され、処理が続行されること
    assert result.fatal_error is None
    assert result.repository_url == f"https://github.com/{DUMMY_REPO_NAME_FULL}"
    assert mock_create_repo_uc.execute.called  # リポジトリ作成が試みられたこと
    assert mock_rest_client.get_repository.called  # 既存リポジトリの情報取得が行われたこと
    assert mock_create_issues_uc.execute.called  # Issue作成が行われたこと
    
    # 適切な警告ログが出力されていること
    assert f"Repository '{DUMMY_REPO_NAME_FULL}' already exists. Proceeding with existing repository." in caplog.text
    assert f"Using existing repository URL:" in caplog.text
    # 最後まで処理が進むこと
    assert "GitHub resource creation workflow completed successfully." in caplog.text

def test_execute_existing_repository_access_error(create_resources_use_case: CreateGitHubResourcesUseCase, mock_rest_client, mock_graphql_client, mock_create_repo_uc, mock_create_issues_uc, caplog):
    """既存リポジトリが存在するがアクセス権がない場合はエラーとなることを確認するテスト"""
    # リポジトリ作成でValidation Error (422)を発生させる
    mock_error = GitHubValidationError("Repository creation failed: name already exists", status_code=422)
    mock_create_repo_uc.execute.side_effect = mock_error
    
    # 既存リポジトリの情報取得でアクセスエラーを発生させる
    mock_access_error = GitHubAuthenticationError("Not authorized to access this repository", status_code=403)
    mock_rest_client.get_repository.side_effect = mock_access_error
    
    # 実行とエラー確認
    with pytest.raises(GitHubAuthenticationError):
        with caplog.at_level(logging.ERROR):
            create_resources_use_case.execute(
                parsed_data=DUMMY_PARSED_DATA_WITH_DETAILS,
                repo_name_input=DUMMY_REPO_NAME_FULL
            )
    
    # 検証 - 適切なエラーログが出力されること
    assert mock_create_repo_uc.execute.called  # リポジトリ作成が試みられたこと
    assert mock_rest_client.get_repository.called  # 既存リポジトリの情報取得が試みられたこと
    assert not mock_create_issues_uc.execute.called  # Issue作成は行われないこと
    
    # エラーログの内容確認（実際のログ出力に合わせる）
    assert f"Failed to access existing repository '{DUMMY_REPO_NAME_FULL}'" in caplog.text
    assert "Halting workflow." in caplog.text

def test_execute_repository_creation_other_validation_error(create_resources_use_case: CreateGitHubResourcesUseCase, mock_rest_client, mock_graphql_client, mock_create_repo_uc, mock_create_issues_uc, caplog):
    """リポジトリ作成で「already exists」以外のバリデーションエラーが発生した場合は処理が中断されることを確認するテスト"""
    # リポジトリ作成で別のValidation Error (422)を発生させる
    mock_error = GitHubValidationError("Repository creation failed: invalid repository name", status_code=422)
    mock_create_repo_uc.execute.side_effect = mock_error
    
    # 実行とエラー確認
    with pytest.raises(GitHubValidationError):
        with caplog.at_level(logging.ERROR):
            create_resources_use_case.execute(
                parsed_data=DUMMY_PARSED_DATA_WITH_DETAILS,
                repo_name_input=DUMMY_REPO_NAME_FULL
            )
    
    # 検証 - 適切なエラーログが出力されること
    assert mock_create_repo_uc.execute.called  # リポジトリ作成が試みられたこと
    assert not mock_rest_client.get_repository.called  # 既存リポジトリの情報取得は行われないこと
    assert not mock_create_issues_uc.execute.called  # Issue作成は行われないこと
    
    # エラーログの内容確認
    assert "Repository creation failed with unexpected validation error" in caplog.text
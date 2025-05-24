import pytest
from unittest.mock import MagicMock, call, patch # patch を追加
import logging # caplog を使うためにインポート
import copy # deep copy用に追加

# テスト対象 UseCase, データモデル, 依存 Client, 例外をインポート
from github_automation_tool.use_cases.create_issues import CreateIssuesUseCase
from github_automation_tool.domain.models import ParsedRequirementData, IssueData, CreateIssuesResult
from github_automation_tool.adapters.github_rest_client import GitHubRestClient # GitHubAppClient から変更
from github_automation_tool.adapters.assignee_validator import AssigneeValidator # 追加
from github_automation_tool.domain.exceptions import GitHubClientError, GitHubValidationError # テスト用例外

# --- Fixtures ---
@pytest.fixture
def mock_github_client() -> MagicMock:
    """GitHubRestClient のモックインスタンスを作成するフィクスチャ"""
    mock = MagicMock(spec=GitHubRestClient)
    # 実際のメソッド名に合わせてモックメソッドを追加
    mock.search_issues_and_pull_requests = MagicMock()
    mock.create_issue = MagicMock()
    return mock

@pytest.fixture
def mock_assignee_validator() -> MagicMock:
    """AssigneeValidator のモックインスタンスを作成するフィクスチャ"""
    mock = MagicMock(spec=AssigneeValidator)
    # メソッドもモック化しておく
    def validate_assignees(owner, repo, assignee_logins):
        valid = []
        invalid = []
        for login in assignee_logins:
            if login == "invalid-user" or login == "@invalid-user":
                invalid.append(login)
            else:
                # @記号は削除して有効なユーザーとして返す
                valid.append(login.lstrip('@'))
        return valid, invalid
    
    mock.validate_assignees = MagicMock(side_effect=validate_assignees)
    return mock

@pytest.fixture
def create_issues_use_case(mock_github_client: MagicMock, mock_assignee_validator: MagicMock) -> CreateIssuesUseCase:
    """テスト対象の UseCase インスタンスを作成（モッククライアントを注入）"""
    return CreateIssuesUseCase(
        rest_client=mock_github_client,
        assignee_validator=mock_assignee_validator
    )

# --- Test Data ---
TEST_OWNER = "test-owner"
TEST_REPO = "test-repo"
ISSUE1_DATA = IssueData(title="New Issue 1", description="Body 1")
ISSUE2_DATA = IssueData(title="Existing Issue 2", description="Body 2")
ISSUE3_DATA = IssueData(title="New Issue 3", description="Body 3")
ISSUE4_DATA = IssueData(title="Error Issue 4", description="Body 4")
# 空のタイトルを持つ辞書（実際のオブジェクトではなく）
EMPTY_TITLE_DICT = {"title": "", "description": "Body for empty title"}

# 担当者付きのIssueデータ
ISSUE_WITH_VALID_ASSIGNEES = IssueData(
    title="Issue with Valid Assignees",
    description="Issue with valid assignees",
    assignees=["valid-user1", "valid-user2"]
)

ISSUE_WITH_INVALID_ASSIGNEES = IssueData(
    title="Issue with Invalid Assignees",
    description="Issue with invalid assignees",
    assignees=["valid-user", "invalid-user"]
)

ISSUE_WITH_AT_ASSIGNEES = IssueData(
    title="Issue with @ Assignees",
    description="Issue with @ in assignees",
    assignees=["@valid-user", "@invalid-user"]
)

PARSED_DATA_ALL_NEW = ParsedRequirementData(issues=[ISSUE1_DATA, ISSUE3_DATA])
PARSED_DATA_ALL_EXISTING = ParsedRequirementData(issues=[ISSUE2_DATA])
PARSED_DATA_MIXED = ParsedRequirementData(issues=[ISSUE1_DATA, ISSUE2_DATA, ISSUE3_DATA])
PARSED_DATA_WITH_ERROR = ParsedRequirementData(issues=[ISSUE1_DATA, ISSUE4_DATA, ISSUE3_DATA])
PARSED_DATA_EMPTY_ISSUES = ParsedRequirementData(issues=[])
PARSED_DATA_WITH_ASSIGNEES = ParsedRequirementData(
    issues=[ISSUE_WITH_VALID_ASSIGNEES, ISSUE_WITH_INVALID_ASSIGNEES, ISSUE_WITH_AT_ASSIGNEES]
)

# Issue戻り値用のヘルパー関数
def create_mock_issue(url, node_id):
    """Issue戻り値用のモックオブジェクトを作成するヘルパー関数"""
    mock_issue = MagicMock()
    mock_issue.html_url = url
    mock_issue.node_id = node_id
    return mock_issue

# --- Test Cases ---

def test_execute_all_new_issues(create_issues_use_case: CreateIssuesUseCase, mock_github_client: MagicMock, caplog):
    """全てのIssueが新規の場合、全て作成され、進捗ログが出力されることをテスト"""
    # モックの検索結果を整数値で直接モック化
    mock_search_result = MagicMock()
    mock_search_result.total_count = 0  # 整数値をセット
    mock_github_client.search_issues_and_pull_requests.return_value = mock_search_result
    
    # create_issue がオブジェクトを返すように設定
    mock_issue1 = create_mock_issue("url/1", "node_id_1")
    mock_issue3 = create_mock_issue("url/3", "node_id_3")
    mock_github_client.create_issue.side_effect = [mock_issue1, mock_issue3]

    with caplog.at_level(logging.INFO): # INFOレベルのログをキャプチャ
        result = create_issues_use_case.execute(PARSED_DATA_ALL_NEW, TEST_OWNER, TEST_REPO)

    assert isinstance(result, CreateIssuesResult)
    assert result.created_issue_details == [("url/1", "node_id_1"), ("url/3", "node_id_3")]
    assert result.skipped_issue_titles == []
    assert result.failed_issue_titles == []
    assert result.errors == []
    # search_issues と create_issue が期待通り呼ばれたか
    assert mock_github_client.search_issues_and_pull_requests.call_count == 2
    # callsのアサーションを修正
    expected_query1 = f'repo:{TEST_OWNER}/{TEST_REPO} is:issue is:open in:title "{ISSUE1_DATA.title}"'
    expected_query3 = f'repo:{TEST_OWNER}/{TEST_REPO} is:issue is:open in:title "{ISSUE3_DATA.title}"'
    mock_github_client.search_issues_and_pull_requests.assert_any_call(q=expected_query1, per_page=1)
    mock_github_client.search_issues_and_pull_requests.assert_any_call(q=expected_query3, per_page=1)
    
    assert mock_github_client.create_issue.call_count == 2
    mock_github_client.create_issue.assert_has_calls([
        call(owner=TEST_OWNER, repo=TEST_REPO, title=ISSUE1_DATA.title, body=ISSUE1_DATA.description, labels=None, milestone=None, assignees=[]),
        call(owner=TEST_OWNER, repo=TEST_REPO, title=ISSUE3_DATA.title, body=ISSUE3_DATA.description, labels=None, milestone=None, assignees=[])
    ])
    # ログの検証
    assert f"Executing CreateIssuesUseCase for {TEST_OWNER}/{TEST_REPO} with 2 potential issues." in caplog.text
    assert f"Processing issue 1/2: '{ISSUE1_DATA.title}'" in caplog.text
    assert f"Issue '{ISSUE1_DATA.title}' does not exist. Attempting creation..." in caplog.text
    assert f"Processing issue 2/2: '{ISSUE3_DATA.title}'" in caplog.text
    assert f"Issue '{ISSUE3_DATA.title}' does not exist. Attempting creation..." in caplog.text
    assert "CreateIssuesUseCase finished" in caplog.text

def test_execute_all_existing_issues(create_issues_use_case: CreateIssuesUseCase, mock_github_client: MagicMock, caplog):
    """全てのIssueが既存の場合、全てスキップされ、進捗ログが出力されることをテスト"""
    # モック設定: 存在確認は常にTrue
    mock_search_result = MagicMock()
    mock_search_result.total_count = 1  # 1件以上あれば既存と判断される
    mock_github_client.search_issues_and_pull_requests.return_value = mock_search_result

    with caplog.at_level(logging.INFO):
        result = create_issues_use_case.execute(PARSED_DATA_ALL_EXISTING, TEST_OWNER, TEST_REPO)

    assert result.created_issue_details == []
    assert result.skipped_issue_titles == [ISSUE2_DATA.title]
    assert result.failed_issue_titles == []
    assert result.errors == []
    # APIメソッドの呼び出し検証
    expected_query = f'repo:{TEST_OWNER}/{TEST_REPO} is:issue is:open in:title "{ISSUE2_DATA.title}"'
    mock_github_client.search_issues_and_pull_requests.assert_called_once_with(q=expected_query, per_page=1)
    mock_github_client.create_issue.assert_not_called() # 作成は呼ばれない
    # ログの検証
    assert f"Executing CreateIssuesUseCase for {TEST_OWNER}/{TEST_REPO} with 1 potential issues." in caplog.text
    assert f"Processing issue 1/1: '{ISSUE2_DATA.title}'" in caplog.text
    assert f"Issue '{ISSUE2_DATA.title}' already exists. Skipping creation." in caplog.text
    assert "CreateIssuesUseCase finished" in caplog.text

def test_execute_mixed_issues(create_issues_use_case: CreateIssuesUseCase, mock_github_client: MagicMock, caplog):
    """新規と既存が混在する場合のテスト"""
    # モック設定: ISSUE2_DATA のみ find で True を返す
    def find_side_effect(q, per_page):
        mock_result = MagicMock()
        if ISSUE2_DATA.title in q:
            mock_result.total_count = 1  # 既存のIssue
        else:
            mock_result.total_count = 0  # 新規のIssue
        return mock_result
    mock_github_client.search_issues_and_pull_requests.side_effect = find_side_effect
    
    # create は2回呼ばれる想定
    mock_issue1 = create_mock_issue("url/1", "node_id_1")
    mock_issue3 = create_mock_issue("url/3", "node_id_3")
    mock_github_client.create_issue.side_effect = [mock_issue1, mock_issue3]

    with caplog.at_level(logging.INFO):
        result = create_issues_use_case.execute(PARSED_DATA_MIXED, TEST_OWNER, TEST_REPO)

    assert result.created_issue_details == [("url/1", "node_id_1"), ("url/3", "node_id_3")]
    assert result.skipped_issue_titles == [ISSUE2_DATA.title]
    assert result.failed_issue_titles == []
    assert result.errors == []
    assert mock_github_client.search_issues_and_pull_requests.call_count == 3
    assert mock_github_client.create_issue.call_count == 2
    # ログの検証 (一部抜粋)
    assert f"Processing issue 1/3: '{ISSUE1_DATA.title}'" in caplog.text
    assert f"Issue '{ISSUE1_DATA.title}' does not exist." in caplog.text
    assert f"Processing issue 2/3: '{ISSUE2_DATA.title}'" in caplog.text
    assert f"Issue '{ISSUE2_DATA.title}' already exists." in caplog.text
    assert f"Processing issue 3/3: '{ISSUE3_DATA.title}'" in caplog.text
    assert f"Issue '{ISSUE3_DATA.title}' does not exist." in caplog.text
    assert "CreateIssuesUseCase finished" in caplog.text

def test_execute_find_issue_api_error(create_issues_use_case: CreateIssuesUseCase, mock_github_client: MagicMock, caplog):
    """存在確認中にAPIエラーが発生しても処理が継続され、ログが出力されるかテスト"""
    mock_error = GitHubClientError("Find API Error")
    
    # 2番目と3番目のsearch_issuesの結果を設定
    mock_search_result2 = MagicMock()
    mock_search_result2.total_count = 0  # 見つからない
    mock_search_result3 = MagicMock()
    mock_search_result3.total_count = 1  # 見つかる
    
    # モック設定: 最初の find でエラー、次は空リスト、最後は存在するリスト
    mock_github_client.search_issues_and_pull_requests.side_effect = [mock_error, mock_search_result2, mock_search_result3]
    # create_issue は2番目の find が False (ISSUE2) なので1回だけ呼ばれる想定
    mock_issue2 = create_mock_issue("url/for_issue2", "node_for_issue2")
    mock_github_client.create_issue.return_value = mock_issue2

    with caplog.at_level(logging.INFO): # INFO以上をキャプチャ (ERRORも含む)
        result = create_issues_use_case.execute(PARSED_DATA_MIXED, TEST_OWNER, TEST_REPO)

    assert result.created_issue_details == [("url/for_issue2", "node_for_issue2")] # 2番目のIssueが作成される
    assert result.skipped_issue_titles == [ISSUE3_DATA.title]  # 3番目のIssueがスキップされる
    assert result.failed_issue_titles == [ISSUE1_DATA.title] # 1番目のIssueは find で失敗
    assert len(result.errors) == 1
    assert "Find API Error" in result.errors[0] # またはより具体的なエラーメッセージ
    # エラータイプも正しく記録されていることを検証
    assert "GitHubClientError" in result.errors[0]

    # モック呼び出し回数の確認
    assert mock_github_client.search_issues_and_pull_requests.call_count == 3
    assert mock_github_client.create_issue.call_count == 1 # 2番目のIssue作成時のみ呼ばれる
    # create_issue が正しい引数で呼ばれたか確認
    mock_github_client.create_issue.assert_called_once_with(
        owner=TEST_OWNER, repo=TEST_REPO, title=ISSUE2_DATA.title, body=ISSUE2_DATA.description, labels=None, milestone=None, assignees=[]
    )
    # ログの検証
    assert f"Processing issue 1/3: '{ISSUE1_DATA.title}'" in caplog.text
    assert f"Failed to process issue '{ISSUE1_DATA.title}': GitHubClientError - Find API Error" in caplog.text # エラーログ
    assert f"Processing issue 2/3: '{ISSUE2_DATA.title}'" in caplog.text
    assert f"Issue '{ISSUE2_DATA.title}' does not exist. Attempting creation..." in caplog.text
    assert f"Processing issue 3/3: '{ISSUE3_DATA.title}'" in caplog.text
    assert f"Issue '{ISSUE3_DATA.title}' already exists. Skipping creation." in caplog.text
    assert "CreateIssuesUseCase finished" in caplog.text

def test_execute_create_issue_api_error(create_issues_use_case: CreateIssuesUseCase, mock_github_client: MagicMock, caplog):
    """Issue作成中にAPIエラーが発生しても処理が継続され、ログが出力されるかテスト"""
    mock_error = GitHubValidationError("Create API Error", status_code=422)
    
    # search_issues の結果を設定
    mock_search_result = MagicMock()
    mock_search_result.total_count = 0  # 見つからない
    mock_github_client.search_issues_and_pull_requests.return_value = mock_search_result
    
    # モック設定: find は全て空リスト、create の2番目 (ISSUE4) でエラー
    mock_issue1 = create_mock_issue("url/1", "node1")
    mock_issue3 = create_mock_issue("url/3", "node3")
    mock_github_client.create_issue.side_effect = [mock_issue1, mock_error, mock_issue3]

    with caplog.at_level(logging.INFO):
        result = create_issues_use_case.execute(PARSED_DATA_WITH_ERROR, TEST_OWNER, TEST_REPO)

    assert result.created_issue_details == [("url/1", "node1"), ("url/3", "node3")] # 1, 3番目は成功
    assert result.skipped_issue_titles == []
    assert result.failed_issue_titles == [ISSUE4_DATA.title] # 4番目は create で失敗
    assert len(result.errors) == 1
    assert "Create API Error" in result.errors[0]
    # エラータイプも正しく記録されていることを検証
    assert "GitHubValidationError" in result.errors[0]
    assert mock_github_client.search_issues_and_pull_requests.call_count == 3
    assert mock_github_client.create_issue.call_count == 3 # 3回呼ばれるが2回目はエラー
    # ログの検証
    assert f"Processing issue 1/3: '{ISSUE1_DATA.title}'" in caplog.text # 成功
    assert f"Processing issue 2/3: '{ISSUE4_DATA.title}'" in caplog.text
    assert f"Issue '{ISSUE4_DATA.title}' does not exist. Attempting creation..." in caplog.text
    assert f"Failed to process issue '{ISSUE4_DATA.title}': GitHubValidationError - Create API Error" in caplog.text # エラーログ
    assert f"Processing issue 3/3: '{ISSUE3_DATA.title}'" in caplog.text # 成功
    assert "CreateIssuesUseCase finished" in caplog.text

def test_execute_empty_issue_list(create_issues_use_case: CreateIssuesUseCase, mock_github_client: MagicMock, caplog):
    """Issueリストが空の場合、何も処理されず、適切なログが出力されることをテスト"""
    with caplog.at_level(logging.INFO):
        result = create_issues_use_case.execute(PARSED_DATA_EMPTY_ISSUES, TEST_OWNER, TEST_REPO)

    assert result.created_issue_details == []
    assert result.skipped_issue_titles == []
    assert result.failed_issue_titles == []
    assert result.errors == []
    mock_github_client.search_issues_and_pull_requests.assert_not_called()
    mock_github_client.create_issue.assert_not_called()
    assert f"Executing CreateIssuesUseCase for {TEST_OWNER}/{TEST_REPO} with 0 potential issues." in caplog.text
    assert "No issues found in parsed data. Nothing to create." in caplog.text

def test_execute_with_empty_title(create_issues_use_case: CreateIssuesUseCase, mock_github_client: MagicMock, caplog):
    """空タイトルのIssueが正しく処理されるかテスト（直接カスタムIssueDataを使用）"""
    # モック設定
    mock_search_result = MagicMock()
    mock_search_result.total_count = 0  # 見つからない
    mock_github_client.search_issues_and_pull_requests.return_value = mock_search_result
    mock_issue1 = create_mock_issue("url/1", "node_id_1")
    mock_issue3 = create_mock_issue("url/3", "node_id_3")
    mock_github_client.create_issue.side_effect = [mock_issue1, mock_issue3]
    
    # 直接テスト用のデータを作成（ParsedRequirementDataのバリデーションをバイパスする）
    parsed_data = MagicMock(spec=ParsedRequirementData)
    
    # 3つのIssueを含むように設定、2つ目は空タイトル
    valid_issue1 = ISSUE1_DATA
    empty_title_issue = MagicMock(spec=IssueData)
    empty_title_issue.title = ""  # 空タイトル
    empty_title_issue.description = "Body for empty title"
    valid_issue3 = ISSUE3_DATA
    
    parsed_data.issues = [valid_issue1, empty_title_issue, valid_issue3]
    
    with caplog.at_level(logging.INFO):
        result = create_issues_use_case.execute(parsed_data, TEST_OWNER, TEST_REPO)
    
    # 結果の検証
    assert len(result.created_issue_details) == 2  # 1番目と3番目のIssueは成功
    assert "(Empty Title)" in result.failed_issue_titles  # 2番目のIssueは失敗
    assert len(result.errors) == 1
    assert "empty title" in result.errors[0].lower()  # エラーメッセージに「empty title」が含まれる
    
    # find_issue_by_title と create_issue の呼び出し回数の検証
    assert mock_github_client.search_issues_and_pull_requests.call_count == 2  # 空タイトルのチェックはスキップ
    assert mock_github_client.create_issue.call_count == 2  # 空タイトル以外のみ作成
    
    # ログの検証
    assert "Executing CreateIssuesUseCase" in caplog.text
    assert "Skipping issue data with empty title" in caplog.text

def test_execute_with_assignees_validation(create_issues_use_case: CreateIssuesUseCase, mock_github_client: MagicMock, mock_assignee_validator: MagicMock, caplog):
    """担当者の検証機能が正しく動作するかテスト"""
    # モック設定: search_issues は常に空リストを返す
    mock_search_result = MagicMock()
    mock_search_result.total_count = 0  # 見つからない
    mock_github_client.search_issues_and_pull_requests.return_value = mock_search_result
    
    # create_issue の戻り値を設定
    mock_issue_valid = create_mock_issue("url/valid", "node_valid") 
    mock_issue_invalid = create_mock_issue("url/invalid", "node_invalid")
    mock_issue_at = create_mock_issue("url/at", "node_at")
    mock_github_client.create_issue.side_effect = [
        mock_issue_valid,
        mock_issue_invalid,
        mock_issue_at
    ]
    
    with caplog.at_level(logging.INFO):
        result = create_issues_use_case.execute(PARSED_DATA_WITH_ASSIGNEES, TEST_OWNER, TEST_REPO)
    
    # 結果の検証
    assert len(result.created_issue_details) == 3
    assert len(result.validation_failed_assignees) == 2
    # 無効な担当者情報が記録されていることを確認
    assert any(title == ISSUE_WITH_INVALID_ASSIGNEES.title for title, _ in result.validation_failed_assignees)
    assert any(title == ISSUE_WITH_AT_ASSIGNEES.title for title, _ in result.validation_failed_assignees)
    
    # validate_assignees が正しく呼び出されたことを確認
    assert mock_assignee_validator.validate_assignees.call_count == 3
    mock_assignee_validator.validate_assignees.assert_any_call(
        TEST_OWNER, TEST_REPO, ISSUE_WITH_VALID_ASSIGNEES.assignees
    )
    mock_assignee_validator.validate_assignees.assert_any_call(
        TEST_OWNER, TEST_REPO, ISSUE_WITH_INVALID_ASSIGNEES.assignees
    )
    mock_assignee_validator.validate_assignees.assert_any_call(
        TEST_OWNER, TEST_REPO, ISSUE_WITH_AT_ASSIGNEES.assignees
    )
    
    # create_issue が有効な担当者リストで呼び出されたことを確認
    assert mock_github_client.create_issue.call_count == 3
    # 最初のIssueは全員有効
    mock_github_client.create_issue.assert_any_call(
        owner=TEST_OWNER, repo=TEST_REPO,
        title=ISSUE_WITH_VALID_ASSIGNEES.title,
        body=ISSUE_WITH_VALID_ASSIGNEES.description,
        labels=None, milestone=None,
        assignees=["valid-user1", "valid-user2"]  # 全員有効
    )
    # 2番目のIssueは一部無効
    mock_github_client.create_issue.assert_any_call(
        owner=TEST_OWNER, repo=TEST_REPO,
        title=ISSUE_WITH_INVALID_ASSIGNEES.title,
        body=ISSUE_WITH_INVALID_ASSIGNEES.description,
        labels=None, milestone=None,
        assignees=["valid-user"]  # 有効な担当者のみ
    )
    # 3番目のIssueは@が削除される
    mock_github_client.create_issue.assert_any_call(
        owner=TEST_OWNER, repo=TEST_REPO,
        title=ISSUE_WITH_AT_ASSIGNEES.title,
        body=ISSUE_WITH_AT_ASSIGNEES.description,
        labels=None, milestone=None,
        assignees=["valid-user"]  # @が削除され、無効な担当者は除外
    )
    
    # ログにも検証失敗情報が含まれていることを確認
    assert "Found 1 invalid assignee(s) for issue" in caplog.text
    assert "Issues with invalid assignees: 2" in caplog.text

def test_execute_with_unexpected_error(create_issues_use_case: CreateIssuesUseCase, mock_github_client: MagicMock, caplog):
    """予期せぬエラーが発生した場合のエラーハンドリングをテスト"""
    # モックの設定
    mock_search_result1 = MagicMock()
    mock_search_result1.total_count = 0  # 見つからない
    
    mock_search_result3 = MagicMock()
    mock_search_result3.total_count = 0  # 見つからない
    
    # search_issues は2回目で予期せぬエラーを発生させる
    mock_github_client.search_issues_and_pull_requests.side_effect = [mock_search_result1, Exception("Unexpected server error"), mock_search_result3]
    mock_issue1 = create_mock_issue("url/1", "node_id_1")
    mock_issue3 = create_mock_issue("url/3", "node_id_3")
    mock_github_client.create_issue.side_effect = [mock_issue1, mock_issue3]
    
    with caplog.at_level(logging.INFO):
        result = create_issues_use_case.execute(PARSED_DATA_MIXED, TEST_OWNER, TEST_REPO)
    
    # 結果の検証
    assert len(result.created_issue_details) == 2  # ISSUE1 と ISSUE3 は作成される
    assert result.failed_issue_titles == [ISSUE2_DATA.title]  # 2番目のIssueは失敗
    assert len(result.errors) == 1
    assert "Unexpected error" in result.errors[0]  # エラーメッセージに「Unexpected error」が含まれる
    assert "Exception - Unexpected server error" in result.errors[0]  # 具体的なエラー内容も含まれる
    
    # ログの検証
    assert f"Processing issue 1/3: '{ISSUE1_DATA.title}'" in caplog.text
    assert f"Processing issue 2/3: '{ISSUE2_DATA.title}'" in caplog.text
    assert f"Unexpected error processing issue '{ISSUE2_DATA.title}': Exception - Unexpected server error" in caplog.text
    assert f"Processing issue 3/3: '{ISSUE3_DATA.title}'" in caplog.text

def test_create_issue_returns_none_values(create_issues_use_case: CreateIssuesUseCase, mock_github_client: MagicMock, caplog):
    """create_issue が None の値を返した場合のエラー処理をテスト"""
    # モックの設定
    mock_search_result = MagicMock()
    mock_search_result.total_count = 0  # 見つからない
    mock_github_client.search_issues_and_pull_requests.return_value = mock_search_result
    
    # 1回目は正常、2回目はURL=None、3回目は両方Noneを返す
    mock_issue1 = create_mock_issue("url/1", "node_id_1")
    mock_issue2 = create_mock_issue(None, "node_id_2")  # URLがNone
    mock_issue3 = create_mock_issue(None, None)  # 両方None
    mock_github_client.create_issue.side_effect = [
        mock_issue1, 
        mock_issue2,
        mock_issue3
    ]
    
    # カスタムテストデータを作成
    test_data = ParsedRequirementData(issues=[ISSUE1_DATA, ISSUE2_DATA, ISSUE3_DATA])
    
    with caplog.at_level(logging.INFO):
        result = create_issues_use_case.execute(test_data, TEST_OWNER, TEST_REPO)
    
    # 結果の検証
    assert len(result.created_issue_details) == 1  # 1番目のIssueのみ成功
    assert result.failed_issue_titles == [ISSUE2_DATA.title, ISSUE3_DATA.title]  # 2,3番目は失敗
    assert len(result.errors) == 2
    assert "Failed to get URL or Node ID" in result.errors[0]
    assert "Failed to get URL or Node ID" in result.errors[1]
    
    # ログの検証
    assert "Failed to get URL or Node ID after attempting to create issue" in caplog.text
    assert "CreateIssuesUseCase finished" in caplog.text
    assert "Encountered 2 error(s)" in caplog.text

def test_execute_with_milestone_mapping(create_issues_use_case: CreateIssuesUseCase, mock_github_client: MagicMock):
    """マイルストーンIDマッピングが正しく使用されるかテスト"""
    # マイルストーンを含むIssueデータを作成
    issue_with_milestone = IssueData(title="Issue with Milestone", description="Body", milestone="Sprint 1")
    parsed_data = ParsedRequirementData(issues=[issue_with_milestone])
    
    # モック設定
    mock_search_result = MagicMock()
    mock_search_result.total_count = 0  # 見つからない
    mock_github_client.search_issues_and_pull_requests.return_value = mock_search_result
    mock_issue = create_mock_issue("url/milestone", "node_id_milestone")
    mock_github_client.create_issue.return_value = mock_issue
    
    # マイルストーンIDマップ
    milestone_id_map = {"Sprint 1": 101, "Sprint 2": 102}
    
    # 実行
    result = create_issues_use_case.execute(parsed_data, TEST_OWNER, TEST_REPO, milestone_id_map)
    
    # 検証
    assert len(result.created_issue_details) == 1
    mock_github_client.create_issue.assert_called_once_with(
        owner=TEST_OWNER,
        repo=TEST_REPO,
        title=issue_with_milestone.title,
        body=issue_with_milestone.description,
        labels=None,
        milestone=101,  # マイルストーンIDが正しく渡されているか
        assignees=[]  # Noneではなく空リストに修正
    )

def test_execute_with_missing_milestone_id(create_issues_use_case: CreateIssuesUseCase, mock_github_client: MagicMock, caplog):
    """マイルストーン名が指定されているがIDが見つからない場合のテスト"""
    # マイルストーンを含むIssueデータを作成
    issue_with_milestone = IssueData(title="Issue with Unknown Milestone", description="Body", milestone="Unknown Sprint")
    parsed_data = ParsedRequirementData(issues=[issue_with_milestone])
    
    # モック設定
    mock_search_result = MagicMock()
    mock_search_result.total_count = 0  # 見つからない
    mock_github_client.search_issues_and_pull_requests.return_value = mock_search_result
    mock_issue = create_mock_issue("url/milestone", "node_id_milestone")
    mock_github_client.create_issue.return_value = mock_issue
    
    # マイルストーンIDマップ - 対象のマイルストーン名は含まれていない
    milestone_id_map = {"Sprint 1": 101, "Sprint 2": 102}
    
    with caplog.at_level(logging.INFO):
        result = create_issues_use_case.execute(parsed_data, TEST_OWNER, TEST_REPO, milestone_id_map)
    
    # 検証
    assert len(result.created_issue_details) == 1
    mock_github_client.create_issue.assert_called_once_with(
        owner=TEST_OWNER,
        repo=TEST_REPO,
        title=issue_with_milestone.title,
        body=issue_with_milestone.description,
        labels=None,
        milestone=None,  # IDが見つからないのでNone
        assignees=[]  # Noneではなく空リストに修正
    )
    
    # 警告ログの検証
    assert "No milestone ID found for milestone 'Unknown Sprint'" in caplog.text
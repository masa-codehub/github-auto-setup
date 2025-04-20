import pytest
from unittest.mock import MagicMock, call # call をインポート
import logging # caplog を使うためにインポート

# テスト対象 UseCase, データモデル, 依存 Client, 例外をインポート
from github_automation_tool.use_cases.create_issues import CreateIssuesUseCase
from github_automation_tool.domain.models import ParsedRequirementData, IssueData, CreateIssuesResult
from github_automation_tool.adapters.github_client import GitHubAppClient # モックの spec に使う
from github_automation_tool.domain.exceptions import GitHubClientError, GitHubValidationError # テスト用例外

# --- Fixtures ---
@pytest.fixture
def mock_github_client() -> MagicMock:
    """GitHubAppClient のモックインスタンスを作成するフィクスチャ"""
    mock = MagicMock(spec=GitHubAppClient)
    # メソッドもモック化しておく
    mock.find_issue_by_title = MagicMock()
    # create_issue がタプル (url, node_id) を返すようにモック
    mock.create_issue = MagicMock(return_value=("default_url", "default_node_id"))
    return mock

@pytest.fixture
def create_issues_use_case(mock_github_client: MagicMock) -> CreateIssuesUseCase:
    """テスト対象の UseCase インスタンスを作成（モッククライアントを注入）"""
    return CreateIssuesUseCase(github_client=mock_github_client)

# --- Test Data ---
TEST_OWNER = "test-owner"
TEST_REPO = "test-repo"
ISSUE1_DATA = IssueData(title="New Issue 1", description="Body 1")
ISSUE2_DATA = IssueData(title="Existing Issue 2", description="Body 2")
ISSUE3_DATA = IssueData(title="New Issue 3", description="Body 3")
ISSUE4_DATA = IssueData(title="Error Issue 4", description="Body 4")
ISSUE_EMPTY_TITLE = IssueData(title="", description="Body for empty title")

PARSED_DATA_ALL_NEW = ParsedRequirementData(issues=[ISSUE1_DATA, ISSUE3_DATA])
PARSED_DATA_ALL_EXISTING = ParsedRequirementData(issues=[ISSUE2_DATA])
PARSED_DATA_MIXED = ParsedRequirementData(issues=[ISSUE1_DATA, ISSUE2_DATA, ISSUE3_DATA])
PARSED_DATA_WITH_ERROR = ParsedRequirementData(issues=[ISSUE1_DATA, ISSUE4_DATA, ISSUE3_DATA])
PARSED_DATA_EMPTY_ISSUES = ParsedRequirementData(issues=[])
PARSED_DATA_WITH_EMPTY_TITLE = ParsedRequirementData(issues=[ISSUE1_DATA, ISSUE_EMPTY_TITLE])

# --- Test Cases ---

def test_execute_all_new_issues(create_issues_use_case: CreateIssuesUseCase, mock_github_client: MagicMock, caplog):
    """全てのIssueが新規の場合、全て作成され、進捗ログが出力されることをテスト"""
    # モック設定: 存在確認は常にFalse、作成は成功しURLを返す
    mock_github_client.find_issue_by_title.return_value = False
    # create_issue は URL,node_id タプルを返すように設定
    mock_github_client.create_issue.side_effect = [("url/1", "node_id_1"), ("url/3", "node_id_3")]

    with caplog.at_level(logging.INFO): # INFOレベルのログをキャプチャ
        result = create_issues_use_case.execute(PARSED_DATA_ALL_NEW, TEST_OWNER, TEST_REPO)

    assert isinstance(result, CreateIssuesResult)
    assert result.created_issue_details == [("url/1", "node_id_1"), ("url/3", "node_id_3")]
    assert result.skipped_issue_titles == []
    assert result.failed_issue_titles == []
    assert result.errors == []
    # find_issue_by_title と create_issue が期待通り呼ばれたか
    assert mock_github_client.find_issue_by_title.call_count == 2
    mock_github_client.find_issue_by_title.assert_has_calls([
        call(TEST_OWNER, TEST_REPO, ISSUE1_DATA.title),
        call(TEST_OWNER, TEST_REPO, ISSUE3_DATA.title)
    ])
    assert mock_github_client.create_issue.call_count == 2
    mock_github_client.create_issue.assert_has_calls([
        call(owner=TEST_OWNER, repo=TEST_REPO, title=ISSUE1_DATA.title, body=ISSUE1_DATA.description, labels=None, milestone=None, assignees=None),
        call(owner=TEST_OWNER, repo=TEST_REPO, title=ISSUE3_DATA.title, body=ISSUE3_DATA.description, labels=None, milestone=None, assignees=None)
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
    mock_github_client.find_issue_by_title.return_value = True

    with caplog.at_level(logging.INFO):
        result = create_issues_use_case.execute(PARSED_DATA_ALL_EXISTING, TEST_OWNER, TEST_REPO)

    assert result.created_issue_details == []
    assert result.skipped_issue_titles == [ISSUE2_DATA.title]
    assert result.failed_issue_titles == []
    assert result.errors == []
    mock_github_client.find_issue_by_title.assert_called_once_with(TEST_OWNER, TEST_REPO, ISSUE2_DATA.title)
    mock_github_client.create_issue.assert_not_called() # 作成は呼ばれない
    # ログの検証
    assert f"Executing CreateIssuesUseCase for {TEST_OWNER}/{TEST_REPO} with 1 potential issues." in caplog.text
    assert f"Processing issue 1/1: '{ISSUE2_DATA.title}'" in caplog.text
    assert f"Issue '{ISSUE2_DATA.title}' already exists. Skipping creation." in caplog.text
    assert "CreateIssuesUseCase finished" in caplog.text

def test_execute_mixed_issues(create_issues_use_case: CreateIssuesUseCase, mock_github_client: MagicMock, caplog):
    """新規と既存が混在する場合のテスト"""
    # モック設定: ISSUE2_DATA のみ find で True を返す
    def find_side_effect(owner, repo, title):
        return title == ISSUE2_DATA.title
    mock_github_client.find_issue_by_title.side_effect = find_side_effect
    # create は2回呼ばれる想定
    mock_github_client.create_issue.side_effect = [("url/1", "node_id_1"), ("url/3", "node_id_3")]

    with caplog.at_level(logging.INFO):
        result = create_issues_use_case.execute(PARSED_DATA_MIXED, TEST_OWNER, TEST_REPO)

    assert result.created_issue_details == [("url/1", "node_id_1"), ("url/3", "node_id_3")]
    assert result.skipped_issue_titles == [ISSUE2_DATA.title]
    assert result.failed_issue_titles == []
    assert result.errors == []
    assert mock_github_client.find_issue_by_title.call_count == 3
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
    # モック設定: 最初の find でエラー、次は False、最後は True
    mock_github_client.find_issue_by_title.side_effect = [mock_error, False, True]
    # create_issue は2回目の find が False (ISSUE2) なので1回だけ呼ばれる想定
    mock_github_client.create_issue.return_value = ("url/for_issue2", "node_for_issue2")

    with caplog.at_level(logging.INFO): # INFO以上をキャプチャ (ERRORも含む)
        result = create_issues_use_case.execute(PARSED_DATA_MIXED, TEST_OWNER, TEST_REPO)

    assert result.created_issue_details == [("url/for_issue2", "node_for_issue2")] # 2番目のIssueが作成される
    assert result.skipped_issue_titles == [ISSUE3_DATA.title]  # 3番目のIssueがスキップされる
    assert result.failed_issue_titles == [ISSUE1_DATA.title] # 1番目のIssueは find で失敗
    assert len(result.errors) == 1
    assert "Find API Error" in result.errors[0] # またはより具体的なエラーメッセージ

    # モック呼び出し回数の確認
    assert mock_github_client.find_issue_by_title.call_count == 3
    assert mock_github_client.create_issue.call_count == 1 # 2番目のIssue作成時のみ呼ばれる
    # create_issue が正しい引数で呼ばれたか確認
    mock_github_client.create_issue.assert_called_once_with(
        owner=TEST_OWNER, repo=TEST_REPO, title=ISSUE2_DATA.title, body=ISSUE2_DATA.description, labels=None, milestone=None, assignees=None
    )
    # ログの検証
    assert f"Processing issue 1/3: '{ISSUE1_DATA.title}'" in caplog.text
    assert f"Failed to process issue '{ISSUE1_DATA.title}': GitHubClientError - Find API Error" in caplog.text # エラーログ
    assert f"Processing issue 2/3: '{ISSUE2_DATA.title}'" in caplog.text
    assert f"Issue '{ISSUE2_DATA.title}' does not exist." in caplog.text # 作成試行
    assert f"Processing issue 3/3: '{ISSUE3_DATA.title}'" in caplog.text
    assert f"Issue '{ISSUE3_DATA.title}' already exists." in caplog.text # スキップ
    assert "CreateIssuesUseCase finished" in caplog.text

def test_execute_create_issue_api_error(create_issues_use_case: CreateIssuesUseCase, mock_github_client: MagicMock, caplog):
    """Issue作成中にAPIエラーが発生しても処理が継続され、ログが出力されるかテスト"""
    mock_error = GitHubValidationError("Create API Error", status_code=422)
    # モック設定: find は全て False、create の2番目 (ISSUE4) でエラー
    mock_github_client.find_issue_by_title.return_value = False
    mock_github_client.create_issue.side_effect = [("url/1", "node1"), mock_error, ("url/3", "node3")]

    with caplog.at_level(logging.INFO):
        result = create_issues_use_case.execute(PARSED_DATA_WITH_ERROR, TEST_OWNER, TEST_REPO)

    assert result.created_issue_details == [("url/1", "node1"), ("url/3", "node3")] # 1, 3番目は成功
    assert result.skipped_issue_titles == []
    assert result.failed_issue_titles == [ISSUE4_DATA.title] # 4番目は create で失敗
    assert len(result.errors) == 1
    assert "Create API Error" in result.errors[0]
    assert mock_github_client.find_issue_by_title.call_count == 3
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
    mock_github_client.find_issue_by_title.assert_not_called()
    mock_github_client.create_issue.assert_not_called()
    assert f"Executing CreateIssuesUseCase for {TEST_OWNER}/{TEST_REPO} with 0 potential issues." in caplog.text
    assert "No issues found in parsed data. Nothing to create." in caplog.text

def test_execute_with_empty_title(create_issues_use_case: CreateIssuesUseCase, mock_github_client: MagicMock, caplog):
    """タイトルが空のIssueデータが含まれている場合、スキップされログが出力されるかテスト"""
    # モック設定: find は False, create は成功する想定
    mock_github_client.find_issue_by_title.return_value = False
    mock_github_client.create_issue.return_value = ("url/1", "node_id_1")

    with caplog.at_level(logging.INFO): # WARNING も含む
        result = create_issues_use_case.execute(PARSED_DATA_WITH_EMPTY_TITLE, TEST_OWNER, TEST_REPO)

    assert result.created_issue_details == [("url/1", "node_id_1")] # ISSUE1のみ作成
    assert result.skipped_issue_titles == []
    assert result.failed_issue_titles == ["(Empty Title)"] # タイトル無しは失敗扱い
    assert len(result.errors) == 1
    assert "empty title" in result.errors[0]
    assert mock_github_client.find_issue_by_title.call_count == 1 # ISSUE1のみfindが呼ばれる
    mock_github_client.find_issue_by_title.assert_called_once_with(TEST_OWNER, TEST_REPO, ISSUE1_DATA.title)
    assert mock_github_client.create_issue.call_count == 1 # ISSUE1のみcreateが呼ばれる
    mock_github_client.create_issue.assert_called_once_with(
        owner=TEST_OWNER, repo=TEST_REPO,
        title=ISSUE1_DATA.title, body=ISSUE1_DATA.description,
        labels=ISSUE1_DATA.labels, milestone=ISSUE1_DATA.milestone, assignees=ISSUE1_DATA.assignees
    )
    # ログの検証
    assert f"Processing issue 1/2: '{ISSUE1_DATA.title}'" in caplog.text
    assert f"Processing issue 2/2: '(Empty Title)'" in caplog.text
    assert "Skipping issue data with empty title." in caplog.text # WARNINGログ
    assert "CreateIssuesUseCase finished" in caplog.text
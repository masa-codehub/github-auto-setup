import pytest
import logging # caplog を使うために必要

# テスト対象とデータモデル、テスト用例外をインポート
from github_automation_tool.adapters.cli_reporter import CliReporter
from github_automation_tool.domain.models import CreateIssuesResult, CreateGitHubResourcesResult
from github_automation_tool.domain.exceptions import GitHubValidationError, GitHubClientError

# --- Fixtures ---
@pytest.fixture
def reporter() -> CliReporter:
    """テスト対象の CliReporter インスタンス"""
    return CliReporter()

# --- Test Cases ---

def test_display_issue_creation_success_only(reporter: CliReporter, caplog):
    """Issue作成がすべて成功した場合のログ出力テスト"""
    result = CreateIssuesResult(created_issue_details=[("https://github.com/test/repo/issues/1", "node_id_1"), ("https://github.com/test/repo/issues/2", "node_id_2")])
    # テスト実行中のログレベルをINFO以上に設定してキャプチャ
    with caplog.at_level(logging.INFO):
        reporter.display_issue_creation_result(result, "owner/repo")

    # caplog.text にキャプチャされた全ログが含まれる
    assert "Issue Creation Summary for repository 'owner/repo'" in caplog.text
    # ---- 修正箇所 ----
    # 新しいサマリー形式を検証
    assert "Total processed: 2" in caplog.text
    assert "Created: 2" in caplog.text
    assert "Skipped: 0" in caplog.text
    assert "Failed: 0" in caplog.text
    # -----------------
    assert "[Created Issues]" in caplog.text
    assert "- https://github.com/test/repo/issues/1" in caplog.text
    assert "- https://github.com/test/repo/issues/2" in caplog.text
    assert "[Skipped Issues" not in caplog.text # スキップがないことを確認
    assert "[Failed Issues" not in caplog.text  # 失敗がないことを確認

def test_display_issue_creation_skipped_only(reporter: CliReporter, caplog):
    """Issue作成がすべてスキップされた場合のログ出力テスト"""
    result = CreateIssuesResult(skipped_issue_titles=["Existing Issue 1", "Existing Issue 2"])
    with caplog.at_level(logging.INFO): # INFOレベル以上をキャプチャするように変更
        reporter.display_issue_creation_result(result) # リポジトリ名なし

    assert "Issue Creation Summary" in caplog.text
    # ---- 修正箇所 ----
    # 新しいサマリー形式を検証
    assert "Total processed: 2" in caplog.text # created + skipped + failed = 0 + 2 + 0
    assert "Created: 0" in caplog.text
    assert "Skipped: 2" in caplog.text
    assert "Failed: 0" in caplog.text
    # -----------------
    assert "[Skipped Issues (Already Exist)]" in caplog.text
    assert "- 'Existing Issue 1'" in caplog.text
    assert "- 'Existing Issue 2'" in caplog.text
    assert "[Failed Issues]" not in caplog.text
    assert "[Created Issues]" not in caplog.text

def test_display_issue_creation_failed_only(reporter: CliReporter, caplog):
    """Issue作成がすべて失敗した場合のログ出力テスト"""
    result = CreateIssuesResult(
        failed_issue_titles=["Failed Issue 1", "Failed Issue 2"],
        errors=["GitHubClientError - Network error", "ValidationError - Invalid input\nDetails here"]
    )
    with caplog.at_level(logging.INFO): # INFOレベル以上をキャプチャするように変更
        reporter.display_issue_creation_result(result, "o/r")

    assert "Issue Creation Summary for repository 'o/r'" in caplog.text # INFOだがERRORも出すので見えるはず
    # ---- 修正箇所 ----
    # 新しいサマリー形式を検証
    assert "Total processed: 2" in caplog.text # 0 + 0 + 2
    assert "Created: 0" in caplog.text
    assert "Skipped: 0" in caplog.text
    assert "Failed: 2" in caplog.text
    # -----------------
    assert "[Failed Issues]" in caplog.text
    assert "- 'Failed Issue 1': GitHubClientError - Network error" in caplog.text
    # 改行がスペースに置換されているか確認
    assert "- 'Failed Issue 2': ValidationError - Invalid input Details here" in caplog.text
    assert "[Created Issues]" not in caplog.text
    assert "[Skipped Issues" not in caplog.text

def test_display_issue_creation_mixed(reporter: CliReporter, caplog):
    """成功・スキップ・失敗が混在する場合のログ出力テスト"""
    result = CreateIssuesResult(
        created_issue_details=[("https://good.url/1", "node_good")],
        skipped_issue_titles=["Already There"],
        failed_issue_titles=["Bad One"],
        errors=["API Error 500"],
        validation_failed_assignees=[("Bad One", ["invalid-user"])] # 検証失敗も追加
    )
    with caplog.at_level(logging.INFO): # INFO以上をキャプチャ
        reporter.display_issue_creation_result(result, "mix/repo")

    assert "Issue Creation Summary for repository 'mix/repo'" in caplog.text
    # ---- 修正箇所 ----
    # 新しいサマリー形式を検証
    assert "Total processed: 3" in caplog.text # 1 + 1 + 1
    assert "Created: 1" in caplog.text
    assert "Skipped: 1" in caplog.text
    assert "Failed: 1" in caplog.text
    assert "Issues with invalid assignees: 1" in caplog.text # 検証失敗情報もサマリーに追加
    # -----------------
    assert "[Created Issues]" in caplog.text
    assert "- https://good.url/1" in caplog.text
    assert "[Skipped Issues (Already Exist)]" in caplog.text
    assert "- 'Already There'" in caplog.text
    assert "[Failed Issues]" in caplog.text
    assert "- 'Bad One': API Error 500" in caplog.text
    assert "[Issues with Invalid Assignees]" in caplog.text
    assert "- 'Bad One': Invalid assignees: invalid-user" in caplog.text

def test_display_repository_creation_success(reporter: CliReporter, caplog):
    """リポジトリ作成成功時のログテスト"""
    with caplog.at_level(logging.INFO):
        reporter.display_repository_creation_result("http://new.repo/url", "new-repo")
    assert "[Success] Repository created: http://new.repo/url" in caplog.text
    assert "[Skipped]" not in caplog.text
    assert "[Failed]" not in caplog.text

def test_display_repository_creation_skipped(reporter: CliReporter, caplog):
    """リポジトリ作成スキップ時のログテスト"""
    # "already exists" を含む ValidationError を作成
    err = GitHubValidationError("Repository 'old-repo' already exists.", status_code=422)
    with caplog.at_level(logging.WARNING): # WARNING以上
        reporter.display_repository_creation_result(None, "old-repo", error=err)
    assert "[Skipped] Repository 'old-repo' already exists." in caplog.text
    assert "[Success]" not in caplog.text
    assert "[Failed]" not in caplog.text

def test_display_repository_creation_failed(reporter: CliReporter, caplog):
    """リポジトリ作成失敗時のログテスト"""
    err = GitHubClientError("Some other API error")
    with caplog.at_level(logging.ERROR): # ERROR以上
        reporter.display_repository_creation_result(None, "fail-repo", error=err)
    assert "[Failed] Could not create repository 'fail-repo': GitHubClientError - Some other API error" in caplog.text
    assert "[Success]" not in caplog.text
    assert "[Skipped]" not in caplog.text

def test_display_general_error(reporter: CliReporter, caplog):
    """汎用エラー表示のログテスト"""
    try:
        1 / 0 # ZeroDivisionError を発生させる
    except Exception as e:
        # CRITICALレベル以上をキャプチャ
        with caplog.at_level(logging.CRITICAL):
            reporter.display_general_error(e, context="during calculation")

    assert "--- Critical Error during calculation ---" in caplog.text
    assert "An unexpected error occurred: ZeroDivisionError - division by zero" in caplog.text
    assert "Traceback" in caplog.text # exc_info=True でトレースバックが出力される
    assert "Processing halted." in caplog.text

# --- 新しい結果表示メソッド用のテストを追加 ---

def test_display_create_github_resources_result_success(reporter: CliReporter, caplog):
    """総合結果表示メソッドの正常系テスト"""
    # テストデータ準備
    issue_result = CreateIssuesResult(
        created_issue_details=[("https://github.com/o/r/issues/1", "id1"), ("https://github.com/o/r/issues/2", "id2")],
        skipped_issue_titles=["skipped"],
        failed_issue_titles=["failed"],
        errors=["Some error"]
    )
    overall_result = CreateGitHubResourcesResult(
        repository_url="https://github.com/o/r",
        project_name="My Project",
        project_node_id="proj_id",
        created_labels=["bug", "feature"],
        failed_labels=[("invalid", "Validation Error")],
        processed_milestones=[("Sprint 1", 1)],  # 新しい構造
        issue_result=issue_result,
        project_items_added_count=2,
        project_items_failed=[("failed_issue_id", "Permission Denied")]
    )

    with caplog.at_level(logging.INFO):
        reporter.display_create_github_resources_result(overall_result)

    # リポジトリ情報の確認
    assert "GITHUB RESOURCE CREATION SUMMARY" in caplog.text
    assert "[Repository]" in caplog.text
    assert "https://github.com/o/r" in caplog.text
    
    # ラベル情報の確認
    assert "[Labels]" in caplog.text
    assert "Successful: 2" in caplog.text
    assert "Failed: 1" in caplog.text
    assert "Created/Existing Labels: bug, feature" in caplog.text
    assert "Failed Labels:" in caplog.text
    assert "'invalid': Validation Error" in caplog.text
    
    # マイルストーン情報の確認
    assert "[Milestones]" in caplog.text
    assert "Successful: 1" in caplog.text
    assert "'Sprint 1' (ID: 1)" in caplog.text
    
    # プロジェクト情報の確認
    assert "[Project] Found 'My Project'" in caplog.text
    # ---- 修正: 新しいフォーマットに合わせる ----
    assert "Project Integration: Added: 2/2" in caplog.text
    assert "Failed: 1/2" in caplog.text
    # --------------------------------------
    assert "Failed to add items to project:" in caplog.text
    assert "Issue (Node ID: failed_issue_id): Permission Denied" in caplog.text
    
    # Issue作成情報（ネストされた呼び出し）の確認
    assert "Issue Creation Summary" in caplog.text
    # ---- 修正: 新しいサマリーフォーマットに合わせる ----
    assert "Total processed:" in caplog.text
    assert "Created: 2" in caplog.text
    assert "Skipped: 1" in caplog.text
    assert "Failed: 1" in caplog.text
    # --------------------------------------

def test_display_create_github_resources_result_fatal_error(reporter: CliReporter, caplog):
    """総合結果表示メソッドの致命的エラーテスト"""
    overall_result = CreateGitHubResourcesResult(
        fatal_error="Critical: Repository creation failed due to auth error."
    )

    with caplog.at_level(logging.CRITICAL):  # 致命的エラーはCRITICAL以上で出る想定
        reporter.display_create_github_resources_result(overall_result)
    
    assert "[FATAL ERROR]" in caplog.text
    assert "Critical: Repository creation failed due to auth error." in caplog.text
    # 他の結果は表示されないことを確認
    assert "[Repository]" not in caplog.text
    assert "[Labels]" not in caplog.text

def test_display_create_github_resources_result_dry_run(reporter: CliReporter, caplog):
    """Dry Runモード時の表示テスト"""
    # Dry Run用の結果を作成
    issue_result = CreateIssuesResult(
        created_issue_details=[
            ("https://github.com/o/r/issues/X (Dry Run)", "DUMMY_ID_1"),
            ("https://github.com/o/r/issues/X (Dry Run)", "DUMMY_ID_2")
        ]
    )
    overall_result = CreateGitHubResourcesResult(
        repository_url="https://github.com/o/r (Dry Run)",
        project_name="My Project",
        created_labels=["bug", "feature"],
        processed_milestones=[("Sprint 1", 1000)],  # 新しい構造
        issue_result=issue_result,
        project_node_id="DUMMY_PROJECT_ID (Dry Run)",
        project_items_added_count=2
    )

    with caplog.at_level(logging.INFO):
        reporter.display_create_github_resources_result(overall_result)

    # Dry Runモードであることを表示
    assert "[DRY RUN MODE]" in caplog.text
    assert "No actual GitHub operations were performed" in caplog.text
    # 各要素が表示されることを確認
    assert "[Repository]: https://github.com/o/r (Dry Run)" in caplog.text
    assert "[Labels]: Would create: bug, feature" in caplog.text
    assert "[Milestones]: Would create: Sprint 1" in caplog.text
    assert "[Project]: Would add 2 issues to My Project" in caplog.text

def test_display_create_github_resources_result_multiple_milestones_success(reporter: CliReporter, caplog):
    """複数のマイルストーンが成功した場合の表示テスト"""
    issue_result = CreateIssuesResult(created_issue_details=[("https://github.com/o/r/issues/1", "id1")])
    overall_result = CreateGitHubResourcesResult(
        repository_url="https://github.com/o/r",
        project_name="My Project",
        project_node_id="proj_id",
        created_labels=["bug"],
        # 複数のマイルストーンが成功
        processed_milestones=[
            ("Sprint 1", 101),
            ("Sprint 2", 102),
            ("Feature Release", 103)
        ],
        issue_result=issue_result,
        project_items_added_count=1
    )

    with caplog.at_level(logging.INFO):
        reporter.display_create_github_resources_result(overall_result)

    # マイルストーン情報の確認
    assert "[Milestones]" in caplog.text
    assert "Successful: 3" in caplog.text
    assert "Failed: 0" in caplog.text
    # 各マイルストーンがログに含まれることを確認
    assert "'Sprint 1' (ID: 101)" in caplog.text
    assert "'Sprint 2' (ID: 102)" in caplog.text
    assert "'Feature Release' (ID: 103)" in caplog.text

def test_display_create_github_resources_result_with_failed_milestones(reporter: CliReporter, caplog):
    """マイルストーン作成が失敗した場合の表示テスト"""
    issue_result = CreateIssuesResult(created_issue_details=[("https://github.com/o/r/issues/1", "id1")])
    overall_result = CreateGitHubResourcesResult(
        repository_url="https://github.com/o/r",
        project_name="My Project",
        project_node_id="proj_id",
        created_labels=["bug"],
        # 失敗したマイルストーンのみ
        processed_milestones=[],
        failed_milestones=[
            ("Sprint 1", "GitHubClientError - API rate limit exceeded"),
            ("Sprint 2", "GitHubValidationError - Invalid milestone name")
        ],
        issue_result=issue_result,
        project_items_added_count=1
    )

    with caplog.at_level(logging.INFO):
        reporter.display_create_github_resources_result(overall_result)

    # マイルストーン情報の確認
    assert "[Milestones]" in caplog.text
    assert "Successful: 0" in caplog.text
    assert "Failed: 2" in caplog.text
    # 失敗したマイルストーンの情報
    assert "Failed Milestones:" in caplog.text
    assert "'Sprint 1': GitHubClientError - API rate limit exceeded" in caplog.text
    assert "'Sprint 2': GitHubValidationError - Invalid milestone name" in caplog.text

def test_display_create_github_resources_result_mixed_milestones(reporter: CliReporter, caplog):
    """成功と失敗が混在するマイルストーンの表示テスト"""
    issue_result = CreateIssuesResult(created_issue_details=[("https://github.com/o/r/issues/1", "id1")])
    overall_result = CreateGitHubResourcesResult(
        repository_url="https://github.com/o/r",
        project_name="My Project",
        project_node_id="proj_id",
        created_labels=["bug"],
        # 成功したマイルストーン
        processed_milestones=[
            ("Sprint 1", 101),
            ("Feature Release", 103)
        ],
        # 失敗したマイルストーン
        failed_milestones=[
            ("Sprint 2", "GitHubClientError - Milestone already exists with different parameters")
        ],
        issue_result=issue_result,
        project_items_added_count=1
    )

    with caplog.at_level(logging.INFO):
        reporter.display_create_github_resources_result(overall_result)

    # マイルストーン情報の確認
    assert "[Milestones]" in caplog.text
    assert "Successful: 2" in caplog.text
    assert "Failed: 1" in caplog.text
    # 成功したマイルストーンの情報
    assert "'Sprint 1' (ID: 101)" in caplog.text
    assert "'Feature Release' (ID: 103)" in caplog.text
    # 失敗したマイルストーンの情報
    assert "Failed Milestones:" in caplog.text
    assert "'Sprint 2': GitHubClientError - Milestone already exists with different parameters" in caplog.text

def test_display_create_github_resources_result_no_milestones(reporter: CliReporter, caplog):
    """マイルストーンが一つもないケースの表示テスト"""
    issue_result = CreateIssuesResult(created_issue_details=[("https://github.com/o/r/issues/1", "id1")])
    overall_result = CreateGitHubResourcesResult(
        repository_url="https://github.com/o/r",
        project_name="My Project",
        project_node_id="proj_id",
        created_labels=["bug"],
        processed_milestones=[],  # 空のリスト
        failed_milestones=[],     # 空のリスト
        issue_result=issue_result,
        project_items_added_count=1
    )

    with caplog.at_level(logging.INFO):
        reporter.display_create_github_resources_result(overall_result)

    # マイルストーン情報の確認
    assert "[Milestones]" in caplog.text
    assert "No milestones processed" in caplog.text
    
    # マイルストーンセクションには成功/失敗のカウントメッセージがないことを確認
    # ログの中からマイルストーンのセクションだけを抽出して検証
    milestone_line = ""
    for line in caplog.text.splitlines():
        if "[Milestones]" in line:
            milestone_line = line
            break
    
    assert "Successful:" not in milestone_line
    assert "Failed:" not in milestone_line

def test_display_create_github_resources_result_with_multiline_errors(reporter: CliReporter, caplog):
    """改行を含むエラーメッセージが適切に整形されるかのテスト"""
    # 複数行のエラーメッセージを含む結果を作成
    issue_result = CreateIssuesResult(
        created_issue_details=[("https://github.com/o/r/issues/1", "id1")],
        failed_issue_titles=["Failed Issue"],
        errors=["Error with\nmultiple lines\nof text"]
    )
    overall_result = CreateGitHubResourcesResult(
        repository_url="https://github.com/o/r",
        created_labels=["bug"],
        failed_labels=[("complex-label", "Validation Error with\nnewlines in\nthe message")],
        processed_milestones=[("Sprint 1", 101)],
        failed_milestones=[("Complex Sprint", "Error with\nmultiple\nlines")],
        issue_result=issue_result,
        project_node_id="proj_id",
        project_name="Test Project",
        project_items_added_count=1,
        project_items_failed=[("failed_node", "GraphQL error with\nmultiple lines")]
    )

    with caplog.at_level(logging.INFO):
        reporter.display_create_github_resources_result(overall_result)

    # 各エラーメッセージで改行が空白に置換されていることを確認
    assert "'complex-label': Validation Error with newlines in the message" in caplog.text
    assert "'Complex Sprint': Error with multiple lines" in caplog.text
    assert "Issue (Node ID: failed_node): GraphQL error with multiple lines" in caplog.text
    
    # Issue作成結果の表示でも改行が置換されている
    assert "- 'Failed Issue': Error with multiple lines of text" in caplog.text

def test_display_create_github_resources_result_with_no_issues(reporter: CliReporter, caplog):
    """Issueが作成されなかった場合のプロジェクト連携メッセージのテスト"""
    # issue_result がNoneの場合と空の場合の両方をテスト
    
    # 1. issue_result が None のケース
    result_with_null_issues = CreateGitHubResourcesResult(
        repository_url="https://github.com/o/r",
        project_name="My Project",
        project_node_id="proj_id",
        created_labels=["bug"],
        processed_milestones=[("Sprint 1", 101)],
        issue_result=None  # None に設定
    )

    with caplog.at_level(logging.INFO):
        caplog.clear()  # 前のテストのログをクリア
        reporter.display_create_github_resources_result(result_with_null_issues)
    
    # プロジェクト統合メッセージを確認
    assert "Project Integration: No issues were created to add" in caplog.text
    
    # 2. issue_result が空のケース
    empty_issue_result = CreateIssuesResult(
        created_issue_details=[],
        skipped_issue_titles=[],
        failed_issue_titles=[]
    )
    
    result_with_empty_issues = CreateGitHubResourcesResult(
        repository_url="https://github.com/o/r",
        project_name="My Project",
        project_node_id="proj_id",
        created_labels=["bug"],
        processed_milestones=[("Sprint 1", 101)],
        issue_result=empty_issue_result  # 空のIssueResultに設定
    )

    with caplog.at_level(logging.INFO):
        caplog.clear()  # 前のテストのログをクリア
        reporter.display_create_github_resources_result(result_with_empty_issues)
    
    # プロジェクト統合メッセージを確認
    assert "Project Integration: No issues were created to add" in caplog.text

def test_display_improved_project_integration_summary(reporter: CliReporter, caplog):
    """改善されたプロジェクト連携サマリー表示をテスト"""
    # 一部の連携が成功し、一部が失敗するケース
    issue_result = CreateIssuesResult(
        created_issue_details=[
            ("https://github.com/o/r/issues/1", "id1"),
            ("https://github.com/o/r/issues/2", "id2"),
            ("https://github.com/o/r/issues/3", "id3"),
            ("https://github.com/o/r/issues/4", "id4")
        ]
    )
    
    result = CreateGitHubResourcesResult(
        repository_url="https://github.com/o/r",
        project_name="My Project",
        project_node_id="proj_id",
        issue_result=issue_result,
        project_items_added_count=2,  # 4件中2件が成功
        project_items_failed=[
            ("id3", "Permission Error"),
            ("id4", "Timeout Error")
        ]
    )
    
    with caplog.at_level(logging.INFO):
        reporter.display_create_github_resources_result(result)
    
    # 改善された表示形式を検証
    assert "Project Integration: Added: 2/4, Failed: 2/4" in caplog.text
    
    # 失敗したアイテムの詳細もフォーマットされていることを確認
    assert "Issue (Node ID: id3): Permission Error" in caplog.text
    assert "Issue (Node ID: id4): Timeout Error" in caplog.text
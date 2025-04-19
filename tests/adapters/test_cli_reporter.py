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
    assert "Created: 2" in caplog.text # サマリー部分
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
    assert "Skipped: 2" in caplog.text
    assert "[Skipped Issues (Already Exist)]" in caplog.text
    assert "- 'Existing Issue 1'" in caplog.text
    assert "- 'Existing Issue 2'" in caplog.text
    assert "[Failed Issues]" not in caplog.text

def test_display_issue_creation_failed_only(reporter: CliReporter, caplog):
    """Issue作成がすべて失敗した場合のログ出力テスト"""
    result = CreateIssuesResult(
        failed_issue_titles=["Failed Issue 1", "Failed Issue 2"],
        errors=["GitHubClientError - Network error", "ValidationError - Invalid input\nDetails here"]
    )
    with caplog.at_level(logging.INFO): # INFOレベル以上をキャプチャするように変更
        reporter.display_issue_creation_result(result, "o/r")

    assert "Issue Creation Summary for repository 'o/r'" in caplog.text # INFOだがERRORも出すので見えるはず
    assert "Failed: 2" in caplog.text
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
        errors=["API Error 500"]
    )
    with caplog.at_level(logging.INFO): # INFO以上をキャプチャ
        reporter.display_issue_creation_result(result, "mix/repo")

    assert "Issue Creation Summary for repository 'mix/repo'" in caplog.text
    assert "Created: 1, Skipped: 1, Failed: 1" in caplog.text
    assert "[Created Issues]" in caplog.text
    assert "- https://good.url/1" in caplog.text
    assert "[Skipped Issues (Already Exist)]" in caplog.text
    assert "- 'Already There'" in caplog.text
    assert "[Failed Issues]" in caplog.text
    assert "- 'Bad One': API Error 500" in caplog.text

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
        milestone_name="Sprint 1",
        milestone_id=1,
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
    assert "[Milestone]" in caplog.text
    assert "'Sprint 1' (ID: 1)" in caplog.text
    
    # プロジェクト情報の確認
    assert "[Project] Found 'My Project'" in caplog.text
    assert "Project Integration: Added 2/2 issues" in caplog.text
    assert "Failed to add 1 issues to project:" in caplog.text
    assert "Issue (Node ID: failed_issue_id): Permission Denied" in caplog.text
    
    # Issue作成情報（ネストされた呼び出し）の確認
    assert "Issue Creation Summary" in caplog.text
    assert "Created: 2, Skipped: 1, Failed: 1" in caplog.text

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
        milestone_name="Sprint 1",
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
    assert "[Milestone]: Would create: Sprint 1" in caplog.text
    assert "[Project]: Would add 2 issues to My Project" in caplog.text
import pytest
from pydantic import ValidationError

from core_logic.domain.models import IssueData, ParsedRequirementData, CreateIssuesResult


class TestIssueData:
    def test_valid_issue_data(self):
        """最小限の有効なデータでIssueDataが作成できることを確認"""
        issue = IssueData(title="テストタイトル", description="テスト説明")
        assert issue.title == "テストタイトル"
        assert issue.description == "テスト説明"
        assert issue.body == "テスト説明"  # body プロパティが description を返すか確認
        assert isinstance(issue.tasks, list)
        assert len(issue.tasks) == 0  # デフォルトは空リスト

    def test_body_alias(self):
        """body エイリアスで正しく初期化できることを確認"""
        issue = IssueData(title="テストタイトル", body="テスト本文")
        assert issue.description == "テスト本文"
        assert issue.body == "テスト本文"

    def test_empty_title_validation(self):
        """空のタイトルが検証エラーを発生させることを確認"""
        with pytest.raises(ValidationError) as excinfo:
            IssueData(title="", description="テスト説明")

        # エラーメッセージに期待されるテキストが含まれているかを確認
        error_message = str(excinfo.value)
        assert "Issue title cannot be empty" in error_message

    def test_whitespace_only_title_validation(self):
        """空白のみのタイトルが検証エラーを発生させることを確認"""
        with pytest.raises(ValidationError) as excinfo:
            IssueData(title="   ", description="テスト説明")

        # エラーメッセージに期待されるテキストが含まれているかを確認
        error_message = str(excinfo.value)
        assert "Issue title cannot be empty" in error_message

    def test_full_issue_data(self):
        """全てのフィールドを持つIssueDataが作成できることを確認"""
        issue = IssueData(
            title="テストタイトル",
            description="テスト説明",
            tasks=["タスク1", "タスク2"],
            relational_definition=["要件1", "要件2"],
            relational_issues=["#1", "#2"],
            acceptance=["基準1", "基準2"],
            labels=["bug", "enhancement"],
            milestone="v1.0",
            assignees=["@user1", "@user2"]
        )
        assert issue.title == "テストタイトル"
        assert issue.description == "テスト説明"
        assert len(issue.tasks) == 2
        assert issue.tasks[0] == "タスク1"
        assert len(issue.relational_definition) == 2
        assert issue.relational_definition[0] == "要件1"
        assert len(issue.relational_issues) == 2
        assert issue.relational_issues[0] == "#1"
        assert len(issue.acceptance) == 2
        assert issue.acceptance[0] == "基準1"
        assert len(issue.labels) == 2
        assert issue.labels[0] == "bug"
        assert issue.milestone == "v1.0"
        assert len(issue.assignees) == 2
        assert issue.assignees[0] == "@user1"


class TestParsedRequirementData:
    def test_parsed_requirement_data(self):
        """ParsedRequirementDataが正しく作成できることを確認"""
        issue1 = IssueData(title="タイトル1", description="説明1")
        issue2 = IssueData(title="タイトル2", description="説明2")

        parsed_data = ParsedRequirementData(issues=[issue1, issue2])

        assert len(parsed_data.issues) == 2
        assert parsed_data.issues[0].title == "タイトル1"
        assert parsed_data.issues[1].title == "タイトル2"

    def test_empty_parsed_data(self):
        """空のissuesリストを持つParsedRequirementDataが作成できることを確認"""
        parsed_data = ParsedRequirementData(issues=[])
        assert len(parsed_data.issues) == 0


class TestCreateIssuesResult:
    def test_create_issues_result_default(self):
        """デフォルト値でCreateIssuesResultが作成できることを確認"""
        result = CreateIssuesResult()
        assert len(result.created_issue_details) == 0
        assert len(result.skipped_issue_titles) == 0
        assert len(result.failed_issue_titles) == 0
        assert len(result.errors) == 0
        assert len(result.validation_failed_assignees) == 0

    def test_create_issues_result_with_data(self):
        """データ付きでCreateIssuesResultが作成できることを確認"""
        result = CreateIssuesResult(
            created_issue_details=[
                ("url/1", "node_id_1"), ("url/2", "node_id_2")],
            skipped_issue_titles=["既存Issue1", "既存Issue2"],
            failed_issue_titles=["失敗Issue1"],
            errors=["エラーメッセージ1"],
            validation_failed_assignees=[("Issue1", ["無効ユーザー1", "無効ユーザー2"])]
        )

        assert len(result.created_issue_details) == 2
        assert result.created_issue_details[0][0] == "url/1"
        assert result.created_issue_details[0][1] == "node_id_1"

        assert len(result.skipped_issue_titles) == 2
        assert "既存Issue1" in result.skipped_issue_titles

        assert len(result.failed_issue_titles) == 1
        assert "失敗Issue1" in result.failed_issue_titles

        assert len(result.errors) == 1
        assert "エラーメッセージ1" in result.errors

        assert len(result.validation_failed_assignees) == 1
        assert result.validation_failed_assignees[0][0] == "Issue1"
        assert len(result.validation_failed_assignees[0][1]) == 2
        assert "無効ユーザー1" in result.validation_failed_assignees[0][1]

from pydantic import BaseModel, Field, ConfigDict


class IssueData(BaseModel):
    """AIによって抽出された単一のIssue情報"""
    # Allow population of 'description' field via alias 'body' to support existing tests
    model_config = ConfigDict(populate_by_name=True)
    title: str = Field(description="抽出されたGitHub issueのタイトル")
    description: str = Field(alias="body", description="抽出されたGitHub issueの説明（概要、目的、背景など）")
    tasks: list = Field(
        default_factory=list,
        description="抽出されたGitHub issueのタスク（例: 'タスク1', 'タスク2'など）"
    )
    relational_definition: list[str] = Field(
        default_factory=list,
        description="抽出されたGitHub issueの関連要件（例: '要件1', '要件2'など）"
    )
    relational_issues: list[str] = Field(
        default_factory=list,
        description="抽出されたGitHub issueの関連Issue（例: 'issue #1', 'issue #2'など）"
    )
    acceptance: list[str] = Field(
        default_factory=list,
        description="抽出されたGitHub issueの受け入れ基準（例: '受け入れ基準1', '受け入れ基準2'など）"
    )
    labels: list[str] | None = Field(default=None, description="抽出されたラベル名のリスト")
    milestone: str | None = Field(default=None, description="抽出されたマイルストーン名")
    assignees: list[str] | None = Field(
        default=None, description="抽出された担当者名のリスト (例: '@username')")

    @property
    def body(self) -> str:
        """Alias for description to support code referencing issue_data.body"""
        return self.description


class ParsedRequirementData(BaseModel):
    """Markdownファイル全体から抽出されたIssueデータのリスト"""
    issues: list[IssueData] = Field(description="ファイルから抽出されたIssueデータのリスト")
    # --- 以下は今後のIssueで追加予定 ---
    # labels_to_create: Optional[list[str]] = Field(default=None, description="ファイル全体で定義された共通ラベル等")
    # milestone_to_create: Optional[str] = Field(default=None, description="ファイル全体で定義された共通マイルストーン等")


class CreateIssuesResult(BaseModel):
    """
    CreateIssuesUseCase の実行結果を格納するデータクラス。
    どのIssueが作成され、スキップされ、失敗したかの情報を持つ。
    """
    created_issue_urls: list[str] = Field(
        default_factory=list,  # デフォルト値を空リストにする
        description="正常に作成されたIssueのGitHub URLリスト"
    )
    skipped_issue_titles: list[str] = Field(
        default_factory=list,
        description="既に存在していたため作成がスキップされたIssueのタイトルリスト"
    )
    failed_issue_titles: list[str] = Field(
        default_factory=list,
        description="作成中にエラーが発生したIssueのタイトルリスト"
    )
    errors: list[str] = Field(
        default_factory=list,
        description="発生したエラーの詳細メッセージ（failed_issue_titlesに対応）のリスト"
    )

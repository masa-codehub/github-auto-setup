from pydantic import BaseModel, Field, ConfigDict
# Removed typing imports; using built-in generics for Python 3.13


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
    created_issue_details: list[tuple[str, str]] = Field(
        default_factory=list,
        description="正常に作成されたIssueの (GitHub URL, Node ID) タプルのリスト"
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


class CreateGitHubResourcesResult(BaseModel):
    """
    CreateGitHubResourcesUseCase の全体的な実行結果を格納するデータクラス。
    リポジトリ、ラベル、マイルストーン、Issue作成、プロジェクト連携の結果を包括的に管理する。
    """
    repository_url: str | None = Field(default=None, description="作成/確認されたリポジトリのURL")
    project_node_id: str | None = Field(default=None, description="対象プロジェクトのNode ID (見つかった場合)")
    project_name: str | None = Field(default=None, description="対象プロジェクト名")

    created_labels: list[str] = Field(default_factory=list, description="正常に作成された(または既存だった)ラベル名のリスト")
    failed_labels: list[tuple[str, str]] = Field(default_factory=list, description="作成に失敗したラベルとそのエラーメッセージのタプルのリスト")

    # マイルストーン名は一つと仮定（仕様に応じて変更）
    milestone_name: str | None = Field(default=None, description="処理対象のマイルストーン名")
    milestone_id: int | None = Field(default=None, description="作成/確認されたマイルストーンのID")
    milestone_creation_error: str | None = Field(default=None, description="マイルストーン作成/確認時のエラー")

    # Issue作成の結果は既存のモデルで保持
    issue_result: CreateIssuesResult | None = Field(default=None, description="Issue作成処理の結果")

    # プロジェクト連携の結果
    project_items_added_count: int = Field(default=0, description="プロジェクトに正常に追加されたアイテム数")
    project_items_failed: list[tuple[str, str]] = Field(default_factory=list, description="プロジェクトへの追加に失敗したIssue Node IDとそのエラーメッセージのタプルのリスト")

    # 全体的な致命的エラー
    fatal_error: str | None = Field(default=None, description="処理を中断させた致命的なエラーメッセージ")

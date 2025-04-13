from pydantic import BaseModel, Field
from typing import List, Optional


class IssueData(BaseModel):
    """AIによって抽出された単一のIssue情報"""
    title: str = Field(description="抽出されたGitHub issueのタイトル")
    body: str = Field(
        description="抽出されたGitHub issueの本文（Description, タスク, 受け入れ基準など全てを含む）")
    # --- 以下は今後のIssueで追加予定 ---
    # labels: Optional[List[str]] = Field(default=None, description="抽出されたラベル名のリスト")
    # milestone: Optional[str] = Field(default=None, description="抽出されたマイルストーン名")
    # assignees: Optional[List[str]] = Field(default=None, description="抽出された担当者名のリスト (例: '@username')")


class ParsedRequirementData(BaseModel):
    """Markdownファイル全体から抽出されたIssueデータのリスト"""
    issues: List[IssueData] = Field(description="ファイルから抽出されたIssueデータのリスト")
    # --- 以下は今後のIssueで追加予定 ---
    # labels_to_create: Optional[List[str]] = Field(default=None, description="ファイル全体で定義された共通ラベル等")
    # milestone_to_create: Optional[str] = Field(default=None, description="ファイル全体で定義された共通マイルストーン等")

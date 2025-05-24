# src/github_automation_tool/adapters/__init__.py
import logging
from typing import Optional, List, Tuple, Any, Dict
from githubkit import GitHub
from githubkit.versions.latest.models import (
    Label, Issue, Milestone, Repository, SimpleUser as User
)

from .github_rest_client import GitHubRestClient
from .github_graphql_client import GitHubGraphQLClient
from .assignee_validator import AssigneeValidator
from .ai_parser import AIParser
from .cli_reporter import CliReporter
from .cli import Cli
from . import github_utils
from ..domain.exceptions import GitHubClientError, GitHubResourceNotFoundError, GitHubValidationError, GitHubAuthenticationError

logger = logging.getLogger(__name__)

class GitHubAppClient:
    """
    RESTとGraphQLクライアントを統合し、認証済みGitHubインスタンスを管理するクライアント。
    UseCase層はこのクライアントを通じてGitHub APIと対話します。
    """
    def __init__(self, github_instance: GitHub, assignee_validator: Optional[AssigneeValidator] = None):
        """
        Args:
            github_instance: 認証済みの githubkit.GitHub インスタンス。
            assignee_validator: 担当者検証を行うための AssigneeValidator インスタンス (オプション)。
        """
        if not isinstance(github_instance, GitHub):
            raise TypeError("github_instance must be a valid githubkit.GitHub instance.")
        self.gh = github_instance # 認証済みインスタンスを保持
        self.rest = GitHubRestClient(github_instance)
        self.graphql = GitHubGraphQLClient(github_instance)
        self.assignee_validator = assignee_validator
        logger.info("GitHubAppClient initialized with REST and GraphQL clients.")

    # --- Repository ---
    def create_repository(self, repo_name: str) -> str:
        """新しいリポジトリを作成し、そのURLを返します。"""
        logger.debug(f"GitHubAppClient: Delegating repository creation for '{repo_name}' to REST client.")
        try:
            repo_data: Repository = self.rest.create_repository(repo_name)
            if not repo_data or not repo_data.html_url:
                 raise GitHubClientError(f"Repository '{repo_name}' created but URL is missing in response.")
            logger.info(f"Repository '{repo_name}' created successfully: {repo_data.html_url}")
            return repo_data.html_url
        except (GitHubValidationError, GitHubAuthenticationError, GitHubClientError) as e:
             logger.error(f"Error creating repository '{repo_name}': {e}")
             raise # 例外をそのまま再送出
        except Exception as e:
             logger.exception(f"Unexpected error creating repository '{repo_name}': {e}")
             raise GitHubClientError(f"Unexpected error: {e}", original_exception=e) from e

    # --- Authenticated User ---
    def get_authenticated_user(self) -> User:
        """認証されたユーザー情報を取得します。"""
        logger.debug("GitHubAppClient: Delegating get_authenticated_user to REST client.")
        try:
            user: User = self.rest.get_authenticated_user()
            if not user or not user.login:
                 raise GitHubClientError("Failed to get valid authenticated user data.")
            logger.debug(f"Authenticated user retrieved: {user.login}")
            return user
        except (GitHubAuthenticationError, GitHubClientError) as e:
             logger.error(f"Error getting authenticated user: {e}")
             raise
        except Exception as e:
             logger.exception(f"Unexpected error getting authenticated user: {e}")
             raise GitHubClientError(f"Unexpected error: {e}", original_exception=e) from e

    # --- Labels ---
    def get_or_create_label(self, owner: str, repo: str, label_name: str, color: Optional[str] = None, description: Optional[str] = "") -> Label:
        """
        ラベルが存在すれば取得し、存在しなければ作成します。
        成功した場合、Labelオブジェクトを返します。
        """
        logger.debug(f"GitHubAppClient: Getting or creating label '{label_name}' in {owner}/{repo}.")
        try:
            # 1. ラベル存在確認 (REST) - 404はエラーとしない
            existing_label = self.rest.get_label(owner, repo, label_name)
            if existing_label:
                logger.info(f"Label '{label_name}' already exists in {owner}/{repo}.")
                return existing_label

            # 2. ラベル作成 (REST)
            logger.info(f"Label '{label_name}' not found, creating it...")
            new_label = self.rest.create_label(owner, repo, label_name, color, description)
            if not new_label:
                 raise GitHubClientError(f"Label '{label_name}' creation seemed successful but no data returned.")
            logger.info(f"Label '{label_name}' created successfully.")
            return new_label
        except (GitHubValidationError, GitHubAuthenticationError, GitHubClientError) as e:
             logger.error(f"Error getting or creating label '{label_name}': {e}")
             raise
        except Exception as e:
             logger.exception(f"Unexpected error getting or creating label '{label_name}': {e}")
             raise GitHubClientError(f"Unexpected error: {e}", original_exception=e) from e

    # --- Milestones ---
    def get_or_create_milestone(self, owner: str, repo: str, title: str, state: str = "open", description: Optional[str] = "") -> Tuple[str, int]:
        """
        指定されたタイトルのマイルストーンが存在すればそのIDを、
        存在しなければ作成してそのIDを返します。

        Returns:
            Tuple[str, int]: (マイルストーン名, マイルストーンID)
        """
        logger.debug(f"GitHubAppClient: Getting or creating milestone '{title}' in {owner}/{repo}.")
        try:
            # 1. 既存のマイルストーンをリスト (REST)
            #    パフォーマンスのため、キャッシュ機構を検討する価値あり
            existing_milestones = self.rest.list_milestones(owner, repo, state="all") # open/closed両方取得
            found_milestone: Optional[Milestone] = None
            for ms in existing_milestones:
                if ms.title == title:
                    found_milestone = ms
                    break

            if found_milestone:
                if found_milestone.number is None: # numberがないことは通常ありえないはず
                     raise GitHubClientError(f"Found milestone '{title}' but it has no ID.")
                logger.info(f"Milestone '{title}' already exists with ID: {found_milestone.number}.")
                # 状態が異なる場合は更新を試みる (オプション)
                if found_milestone.state != state:
                     logger.warning(f"Milestone '{title}' exists but state is '{found_milestone.state}', requested '{state}'. Update not implemented.")
                     # TODO: 必要であれば update_milestone を実装
                return title, found_milestone.number

            # 2. マイルストーン作成 (REST)
            logger.info(f"Milestone '{title}' not found, creating it...")
            new_milestone = self.rest.create_milestone(owner, repo, title, state, description)
            if not new_milestone or new_milestone.number is None:
                 raise GitHubClientError(f"Milestone '{title}' creation seemed successful but no valid data returned.")
            logger.info(f"Milestone '{title}' created successfully with ID: {new_milestone.number}.")
            return title, new_milestone.number
        except (GitHubValidationError, GitHubAuthenticationError, GitHubClientError) as e:
             logger.error(f"Error getting or creating milestone '{title}': {e}")
             raise
        except Exception as e:
             logger.exception(f"Unexpected error getting or creating milestone '{title}': {e}")
             raise GitHubClientError(f"Unexpected error: {e}", original_exception=e) from e

    # --- Issues ---
    def find_issue_by_title(self, owner: str, repo: str, title: str) -> Optional[Issue]:
        """指定されたタイトルのIssueを検索し、見つかればIssueオブジェクトを返します。"""
        logger.debug(f"GitHubAppClient: Delegating issue search for title '{title}' to REST client.")
        try:
            # RESTクライアントの検索メソッドを呼び出す
            issue: Optional[Issue] = self.rest.search_issue_by_title(owner, repo, title)
            if issue:
                 logger.debug(f"Found existing issue '{title}' with ID: {issue.number}")
            else:
                 logger.debug(f"No issue found with title '{title}'.")
            return issue
        except GitHubClientError as e:
             # 検索時のエラーはログに記録し、Noneを返す（存在しない扱い）
             logger.warning(f"Error searching for issue '{title}': {e}. Treating as not found.")
             return None
        except Exception as e:
             logger.exception(f"Unexpected error searching for issue '{title}': {e}")
             # 予期せぬエラーもNoneを返す
             return None

    def create_issue(self, owner: str, repo: str, title: str,
                     body: Optional[str] = None,
                     labels: Optional[List[str]] = None,
                     milestone_id: Optional[int] = None, # IDで受け取る
                     assignees: Optional[List[str]] = None) -> Tuple[str, str]:
        """
        新しいIssueを作成し、そのURLとNode IDのタプルを返します。
        担当者の検証も行います。
        """
        logger.debug(f"GitHubAppClient: Creating issue '{title}' in {owner}/{repo}.")

        valid_assignees: List[str] = []
        invalid_assignees: List[str] = []

        # 担当者検証 (AssigneeValidatorが設定されている場合)
        if assignees and self.assignee_validator:
            logger.debug(f"Validating assignees: {assignees}")
            validation_result = self.assignee_validator.validate_assignees(owner, repo, assignees)
            valid_assignees = validation_result.valid_assignees
            invalid_assignees = validation_result.invalid_assignees
            if invalid_assignees:
                logger.warning(f"Invalid assignees found for issue '{title}': {invalid_assignees}. They will be omitted.")
        elif assignees:
            # AssigneeValidatorがない場合はそのまま使う (検証スキップ)
            valid_assignees = assignees
            logger.debug("Assignee validator not configured, using provided assignees directly.")


        try:
            # RESTクライアントでIssueを作成
            created_issue: Issue = self.rest.create_issue(
                owner=owner,
                repo=repo,
                title=title,
                body=body,
                labels=labels,
                milestone=milestone_id, # IDを渡す
                assignees=valid_assignees # 検証済みの担当者のみ渡す
            )
            if not created_issue or not created_issue.html_url or not created_issue.node_id:
                 raise GitHubClientError(f"Issue '{title}' creation seemed successful but URL or Node ID is missing.")

            logger.info(f"Issue '{title}' created successfully: {created_issue.html_url}")
            # 作成成功時はURLとNode IDを返す
            return created_issue.html_url, created_issue.node_id
        except (GitHubValidationError, GitHubAuthenticationError, GitHubClientError) as e:
             logger.error(f"Error creating issue '{title}': {e}")
             raise # 例外をそのまま再送出
        except Exception as e:
             logger.exception(f"Unexpected error creating issue '{title}': {e}")
             raise GitHubClientError(f"Unexpected error: {e}", original_exception=e) from e

    # --- ProjectsV2 ---
    def find_project_v2_node_id(self, owner: str, project_name: str) -> Optional[str]:
        """指定されたプロジェクト名のProject V2 Node IDを検索します。"""
        logger.debug(f"GitHubAppClient: Delegating Project V2 search for '{project_name}' to GraphQL client.")
        try:
            node_id: Optional[str] = self.graphql.find_project_v2_node_id(owner, project_name)
            if node_id:
                 logger.debug(f"Found Project V2 '{project_name}' with Node ID: {node_id}")
            else:
                 logger.warning(f"Project V2 '{project_name}' not found for owner '{owner}'.")
            return node_id
        except GitHubClientError as e:
             # GraphQLクライアントからのエラーはログに記録し、Noneを返す
             logger.error(f"Error finding Project V2 '{project_name}': {e}")
             return None
        except Exception as e:
             logger.exception(f"Unexpected error finding Project V2 '{project_name}': {e}")
             return None # 予期せぬエラーもNone

    def add_item_to_project_v2(self, project_node_id: str, content_node_id: str) -> Optional[str]:
        """IssueまたはPull RequestをProject V2に追加し、追加されたアイテムのNode IDを返します。"""
        logger.debug(f"GitHubAppClient: Delegating add item '{content_node_id}' to project '{project_node_id}' to GraphQL client.")
        try:
            item_id: str = self.graphql.add_item_to_project_v2(project_node_id, content_node_id)
            logger.info(f"Successfully added item '{content_node_id}' to project '{project_node_id}'. New item ID: {item_id}")
            return item_id
        except GitHubClientError as e:
             logger.error(f"Error adding item '{content_node_id}' to project '{project_node_id}': {e}")
             # エラー時は None を返すか、例外を再送出するか検討 -> UseCase側でハンドリングしやすいようにNoneを返す
             return None
        except Exception as e:
             logger.exception(f"Unexpected error adding item '{content_node_id}' to project '{project_node_id}': {e}")
             return None # 予期せぬエラーもNone

    # --- Collaborators (Permissions) ---
    def check_collaborator_permission(self, owner: str, repo: str, username: str, permission: str = 'push') -> bool:
        """指定されたユーザーがリポジトリに対して特定の権限を持っているか確認します。"""
        logger.debug(f"GitHubAppClient: Delegating collaborator permission check for '{username}' on {owner}/{repo} (permission: {permission}) to REST client.")
        try:
            has_permission: bool = self.rest.check_collaborator_permission(owner, repo, username, permission)
            logger.debug(f"User '{username}' has '{permission}' permission on {owner}/{repo}: {has_permission}")
            return has_permission
        except GitHubResourceNotFoundError:
             # リポジトリが見つからない、またはユーザーがコラボレーターでない場合はFalse
             logger.warning(f"Repository {owner}/{repo} not found or '{username}' is not a collaborator.")
             return False
        except GitHubClientError as e:
             logger.error(f"Error checking collaborator permission for '{username}' on {owner}/{repo}: {e}")
             return False # APIエラーの場合も権限なしとみなす
        except Exception as e:
             logger.exception(f"Unexpected error checking collaborator permission for '{username}' on {owner}/{repo}: {e}")
             return False # 予期せぬエラーも権限なし

# 他のアダプタークラスも必要に応じてここからエクスポートできます
__all__ = [
    "GitHubAppClient",
    "GitHubRestClient",
    "GitHubGraphQLClient",
    "AssigneeValidator",
    "AIParser", # AIParserも公開する場合
    "CliReporter", # CliReporterも公開する場合
    "Cli", # Cliも公開する場合
    "github_utils" # github_utilsも公開する場合
]

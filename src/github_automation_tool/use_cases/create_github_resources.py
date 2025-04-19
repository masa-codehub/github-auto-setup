import logging
from typing import Optional, Tuple, List
from collections.abc import Callable

# 依存コンポーネントとデータモデル、例外をインポート
from github_automation_tool.adapters.github_client import GitHubAppClient
from github_automation_tool.use_cases.create_repository import CreateRepositoryUseCase
from github_automation_tool.use_cases.create_issues import CreateIssuesUseCase
from github_automation_tool.domain.models import ParsedRequirementData, CreateIssuesResult, CreateGitHubResourcesResult
from github_automation_tool.domain.exceptions import (
    GitHubClientError, GitHubAuthenticationError, GitHubValidationError, GitHubResourceNotFoundError
)

logger = logging.getLogger(__name__)


class CreateGitHubResourcesUseCase:
    """
    GitHub リソース（リポジトリ、ラベル、マイルストーン、Issue、プロジェクト連携）の
    作成ワークフローを実行するUseCase。単一責任の原則に基づき、ファイル読み込みや
    AI解析は行わず、ParsedRequirementDataを受け取って処理します。
    """

    def __init__(self,
                 github_client: GitHubAppClient,
                 create_repo_uc: CreateRepositoryUseCase,
                 create_issues_uc: CreateIssuesUseCase):
        """UseCaseを初期化し、依存コンポーネントを注入します。"""
        self.github_client = github_client
        self.create_repo_uc = create_repo_uc
        self.create_issues_uc = create_issues_uc
        logger.debug("CreateGitHubResourcesUseCase initialized.")

    def _get_owner_repo(self, repo_name_input: str) -> Tuple[str, str]:
        """入力リポジトリ名から owner と repo を抽出 (owner省略時は認証ユーザー)"""
        logger.debug(f"Parsing repository name input: {repo_name_input}")
        if '/' in repo_name_input:
            parts = repo_name_input.split('/', 1)
            if len(parts) == 2 and parts[0] and parts[1]:
                owner, repo = parts
                logger.debug(f"Parsed owner={owner}, repo={repo}")
                return owner, repo
            else:
                raise ValueError(
                    f"Invalid repository name format: '{repo_name_input}'. Expected 'owner/repo'.")
        else:
            logger.info(
                "Owner not specified in repo name, attempting to get authenticated user.")
            try:
                user_response = self.github_client.gh.rest.users.get_authenticated()
                owner = getattr(user_response.parsed_data, 'login', None)
                if not owner:
                    logger.error(
                        "Could not retrieve login name for authenticated user.")
                    raise GitHubClientError(
                        "Could not retrieve authenticated user login name.")
                logger.info(f"Using authenticated user as owner: {owner}")
                return owner, repo_name_input
            except Exception as e:
                logger.error(
                    f"Failed to get authenticated user: {e}", exc_info=True)
                raise GitHubAuthenticationError(
                    f"Failed to get authenticated user: {e}", original_exception=e) from e

    def execute(self, parsed_data: ParsedRequirementData, repo_name_input: str, 
                project_name: Optional[str] = None, dry_run: bool = False) -> CreateGitHubResourcesResult:
        """
        GitHub リソース作成のワークフローを実行します。
        
        Args:
            parsed_data: 事前にAI解析された要件データ
            repo_name_input: リポジトリ名（owner/repoの形式も可）
            project_name: Issueを追加するプロジェクト名（オプション）
            dry_run: True の場合、GitHub操作を行わずシミュレーションのみ

        Returns:
            CreateGitHubResourcesResult: 各処理ステップの結果を含む総合的な結果オブジェクト
        
        Raises:
            様々な例外: GitHubAPI関連のエラーなど
        """
        logger.info("Starting GitHub resource creation workflow...")
        
        # 結果オブジェクトを初期化
        result = CreateGitHubResourcesResult(project_name=project_name)
        repo_owner, repo_name, repo_full_name = "", "", ""

        try:
            # --- ステップ 1: リポジトリ名解析 ---
            repo_owner, repo_name = self._get_owner_repo(repo_name_input)
            repo_full_name = f"{repo_owner}/{repo_name}"
            logger.info(f"Target repository identified: {repo_full_name}")

            # --- ステップ 2: Dry Run モード ---
            if dry_run:
                logger.warning(
                    "Dry run mode enabled. Skipping GitHub operations.")
                # Dry Run用の結果を設定
                result.repository_url = f"https://github.com/{repo_full_name} (Dry Run)"
                
                # ラベル情報をDry Runで表示
                unique_labels = set()
                unique_milestones = set()
                unique_assignees = set()
                
                if parsed_data.issues:
                    for issue in parsed_data.issues:
                        if issue.labels:
                            unique_labels.update(lbl for lbl in issue.labels if lbl and lbl.strip())
                        if issue.milestone:
                            unique_milestones.add(issue.milestone)
                        if issue.assignees:
                            unique_assignees.update(a for a in issue.assignees if a and a.strip())
                
                # 収集した情報を結果に格納
                result.created_labels = list(unique_labels)
                if unique_milestones:
                    result.milestone_name = next(iter(unique_milestones))  # 最初のものを使用
                
                # Dry Run用のIssue結果を作成
                dummy_issues_result = CreateIssuesResult()
                dummy_issues_result.created_issue_details = [
                    (f"https://github.com/{repo_full_name}/issues/X (Dry Run)", f"DUMMY_NODE_ID_{i}")
                    for i, issue in enumerate(parsed_data.issues, 1)
                ]
                result.issue_result = dummy_issues_result
                
                if project_name:
                    result.project_node_id = f"DUMMY_PROJECT_NODE_ID (Dry Run)"
                    result.project_items_added_count = len(dummy_issues_result.created_issue_details)
                
                # Dry Run用のロギング
                logger.info(f"[Dry Run] Would create/use repository: {repo_full_name}")
                logger.info(f"[Dry Run] Would ensure {len(unique_labels)} labels exist: {sorted(list(unique_labels))}")
                if unique_milestones:
                    logger.info(f"[Dry Run] Would ensure milestone '{result.milestone_name}' exists")
                logger.info(f"[Dry Run] Would create {len(parsed_data.issues)} issues")
                if project_name:
                    logger.info(f"[Dry Run] Would add {result.project_items_added_count} issues to project '{project_name}'")
                    
                logger.warning("Dry run finished.")
                return result

            # --- ステップ 3: リポジトリ作成 ---
            logger.info(
                f"Executing CreateRepositoryUseCase for '{repo_name}'...")
            repo_url = self.create_repo_uc.execute(repo_name)
            result.repository_url = repo_url

            # --- ステップ 4: ラベル作成/確認 ---
            logger.info(
                f"Ensuring required labels exist in {repo_full_name}...")
            # まずファイル全体からユニークなラベル名を集める
            unique_labels_in_file = set()
            if parsed_data.issues:
                for issue in parsed_data.issues:
                    if issue.labels:  # labels フィールドが None でなくリストの場合
                        # 空文字列やNoneをフィルタリング（念のため）
                        valid_labels = [
                            lbl for lbl in issue.labels if lbl and lbl.strip()]
                        unique_labels_in_file.update(valid_labels)
            # (将来的に parsed_data.labels_to_create があればここで update)

            created_labels_count = 0
            skipped_labels_count = 0
            # 結果オブジェクトのラベル関連フィールドを初期化
            result.created_labels = []
            result.failed_labels = []
            
            if unique_labels_in_file:
                logger.debug(
                    f"Unique labels found in file: {unique_labels_in_file}")
                # 各ラベルについて存在確認・作成を行う
                for label_name in sorted(list(unique_labels_in_file)):
                    try:
                        # GitHubクライアントのラベル作成メソッド呼び出し (冪等性あり)
                        # 色や説明は指定しない (GitHubデフォルト)
                        created = self.github_client.create_label(
                            repo_owner, repo_name, label_name)
                        if created:
                            created_labels_count += 1
                        else:
                            skipped_labels_count += 1
                        # 成功したラベル名を結果に追加（作成もスキップも同じリストに入れる）
                        result.created_labels.append(label_name)
                    except GitHubClientError as e:  # create_label で発生しうる想定内エラー
                        logger.error(
                            f"Failed to ensure label '{label_name}': {e}")
                        # 失敗したラベル名とエラーメッセージを結果に追加
                        result.failed_labels.append((label_name, str(e)))
                        # エラーが発生しても処理を継続する
                    except Exception as e:  # 予期せぬエラー
                        logger.exception(
                            f"Unexpected error ensuring label '{label_name}': {e}")
                        # 同様に失敗情報を結果に追加
                        result.failed_labels.append((label_name, f"Unexpected error: {e}"))
                        # 予期せぬエラーでも処理を継続する
            else:
                logger.info("No valid labels found in parsed data to ensure.")

            # ラベル処理結果のログ出力
            log_label_summary = (
                f"Label ensuring finished. New: {created_labels_count}, "
                f"Existing/Skipped: {skipped_labels_count}, Failed: {len(result.failed_labels)}."
            )
            if result.failed_labels:
                logger.warning(log_label_summary +
                               f" Failed labels: {[l[0] for l in result.failed_labels]}")
            else:
                logger.info(log_label_summary)

            # --- ステップ 5: マイルストーン作成/確認 ---
            logger.info(f"Checking for milestones in {repo_full_name}...")
            # ファイル全体から全てのマイルストーン名を収集
            unique_milestones_in_file = set()
            if parsed_data.issues:
                for issue in parsed_data.issues:
                    if issue.milestone and issue.milestone.strip():
                        unique_milestones_in_file.add(issue.milestone.strip())
            
            # マイルストーン処理（現状は最初の1つのみ対応）
            if unique_milestones_in_file:
                if len(unique_milestones_in_file) > 1:
                    logger.warning(f"Multiple milestones found: {sorted(list(unique_milestones_in_file))}. Only processing the first one.")
                
                target_milestone = next(iter(sorted(unique_milestones_in_file)))  # 最初のものをソートして使用
                result.milestone_name = target_milestone
                logger.info(f"Processing milestone: '{target_milestone}'")
                
                try:
                    milestone_id = self.github_client.create_milestone(repo_owner, repo_name, target_milestone)
                    result.milestone_id = milestone_id
                    logger.info(f"Successfully ensured milestone '{target_milestone}' exists with ID: {milestone_id}")
                except GitHubClientError as e:
                    logger.error(f"Failed to create/ensure milestone '{target_milestone}': {e}")
                    result.milestone_creation_error = str(e)
                except Exception as e:
                    logger.exception(f"Unexpected error creating milestone '{target_milestone}': {e}")
                    result.milestone_creation_error = f"Unexpected error: {e}"
            else:
                logger.info("No milestones found in parsed data.")

            # --- ステップ 6: プロジェクト検索（指定されていれば） ---
            project_node_id = None
            if project_name:
                logger.info(f"Finding Project V2 '{project_name}' for owner '{repo_owner}'...")
                try:
                    project_node_id = self.github_client.find_project_v2_node_id(repo_owner, project_name)
                    if project_node_id:
                        result.project_node_id = project_node_id
                        logger.info(f"Found Project V2 '{project_name}' with Node ID: {project_node_id}")
                    else:
                        logger.warning(f"Project V2 '{project_name}' not found for owner '{repo_owner}'")
                except GitHubResourceNotFoundError as e:
                    logger.warning(f"Project '{project_name}' not found: {e}")
                except GitHubClientError as e:
                    logger.error(f"Error finding project '{project_name}': {e}")
                    # プロジェクト検索エラーでも処理は続行
            else:
                logger.info("No project name specified, skipping project integration.")

            # --- ステップ 7: Issue 作成 ---
            logger.info(
                f"Executing CreateIssuesUseCase for '{repo_full_name}'...")
            issue_result: CreateIssuesResult = self.create_issues_uc.execute(
                parsed_data, repo_owner, repo_name)
            result.issue_result = issue_result

            # --- ステップ 8: Issueをプロジェクトに追加 ---
            if project_node_id and issue_result.created_issue_details:
                logger.info(f"Adding {len(issue_result.created_issue_details)} issues to project '{project_name}'...")
                result.project_items_failed = []  # 初期化
                
                for issue_url, issue_node_id in issue_result.created_issue_details:
                    try:
                        item_id = self.github_client.add_item_to_project_v2(project_node_id, issue_node_id)
                        if item_id:
                            result.project_items_added_count += 1
                            logger.info(f"Added issue (Node ID: {issue_node_id}) to project, new item ID: {item_id}")
                        else:
                            # 通常はここには到達しないが念のため
                            result.project_items_failed.append((issue_node_id, "Failed to get project item ID after adding"))
                            logger.error(f"Failed to get project item ID after adding issue (Node ID: {issue_node_id})")
                    except GitHubClientError as e:
                        result.project_items_failed.append((issue_node_id, str(e)))
                        logger.error(f"Failed to add issue (Node ID: {issue_node_id}) to project: {e}")
                    except Exception as e:
                        result.project_items_failed.append((issue_node_id, f"Unexpected error: {str(e)}"))
                        logger.exception(f"Unexpected error adding issue (Node ID: {issue_node_id}) to project: {e}")
                
                # プロジェクト連携結果をログ出力
                logger.info(f"Project integration complete. Added {result.project_items_added_count} issues to project, Failed: {len(result.project_items_failed)}")
            elif project_node_id:
                logger.info("No issues were created or all were skipped, no issues to add to project.")
            elif project_name:
                logger.info("Project not found, skipping adding issues to project.")
            
            logger.info(
                "GitHub resource creation process completed successfully.")

        # --- エラーハンドリング ---
        except (ValueError, GitHubValidationError, GitHubAuthenticationError, GitHubClientError) as e:
            logger.error(
                f"Workflow error during resource creation: {type(e).__name__} - {e}")
            result.fatal_error = f"{type(e).__name__}: {e}"
            raise
        except Exception as e:
            logger.exception(
                f"An unexpected critical error occurred during resource creation workflow: {e}")
            result.fatal_error = f"An unexpected critical error occurred: {type(e).__name__} - {e}"
            raise GitHubClientError(
                f"An unexpected critical error occurred: {e}", original_exception=e) from e

        return result

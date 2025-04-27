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
                # エラーをラップして再送出
                raise GitHubAuthenticationError(
                    f"Failed to get authenticated user due to API error: {e}", original_exception=e) from e

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
        logger.info(f"Starting GitHub resource creation workflow... (Dry Run: {dry_run})") # Dry Runモードかも表示

        # 結果オブジェクトを初期化
        result = CreateGitHubResourcesResult(project_name=project_name)
        repo_owner, repo_name, repo_full_name = "", "", ""

        try:
            # --- ステップ 1: リポジトリ名解析 ---
            logger.info("Step 1: Resolving repository owner and name...")
            repo_owner, repo_name = self._get_owner_repo(repo_name_input)
            repo_full_name = f"{repo_owner}/{repo_name}"
            logger.info(f"Step 1 finished. Target repository: {repo_full_name}")

            # --- ステップ 2: Dry Run モード ---
            if dry_run:
                # Dry Run モードの処理を複数マイルストーン対応に修正
                logger.warning(
                    "Dry run mode enabled. Skipping GitHub operations.")
                result.repository_url = f"https://github.com/{repo_full_name} (Dry Run)"
                unique_labels = set()
                unique_milestones = set()
                if parsed_data.issues:
                    for issue in parsed_data.issues:
                        if issue.labels:
                            unique_labels.update(lbl for lbl in issue.labels if lbl and lbl.strip())
                        if issue.milestone:
                            unique_milestones.add(issue.milestone.strip())
                result.created_labels = sorted(list(unique_labels))
                
                # 複数マイルストーン対応
                milestone_id_map = {}
                milestone_id_counter = 1000
                for milestone_name in sorted(unique_milestones):
                    milestone_id = milestone_id_counter
                    milestone_id_counter += 1
                    result.processed_milestones.append((milestone_name, milestone_id))
                    milestone_id_map[milestone_name] = milestone_id
                
                dummy_issues_result = CreateIssuesResult()
                dummy_issues_result.created_issue_details = [
                    (f"https://github.com/{repo_full_name}/issues/X{i} (Dry Run)", f"DUMMY_NODE_ID_{i}")
                    for i, issue in enumerate(parsed_data.issues, 1)
                ]
                result.issue_result = dummy_issues_result
                if project_name:
                    result.project_node_id = f"DUMMY_PROJECT_NODE_ID (Dry Run)"
                    result.project_items_added_count = len(dummy_issues_result.created_issue_details)

                logger.info(f"[Dry Run] Would ensure repository: {repo_full_name}")
                logger.info(f"[Dry Run] Would ensure {len(unique_labels)} labels exist: {result.created_labels}")
                if unique_milestones:
                    logger.info(f"[Dry Run] Would ensure {len(unique_milestones)} milestones exist: {sorted(unique_milestones)}")
                if project_name:
                    logger.info(f"[Dry Run] Would search for project '{project_name}'")
                logger.info(f"[Dry Run] Would process {len(parsed_data.issues)} issues")
                if project_name:
                    logger.info(f"[Dry Run] Would add {result.project_items_added_count} items to project '{project_name}'")

                logger.warning("Dry run finished.")
                return result

            # --- ステップ 3: リポジトリ作成 ---
            logger.info(f"Step 3: Ensuring repository '{repo_full_name}' exists...")
            # execute内でエラーが発生した場合、ここで捕捉される
            repo_url = self.create_repo_uc.execute(repo_name) # Owner名は渡さない
            result.repository_url = repo_url
            logger.info(f"Step 3 finished. Repository URL: {repo_url}")

            # --- ステップ 4: ラベル作成/確認 ---
            logger.info(f"Step 4: Ensuring required labels exist in {repo_full_name}...")
            unique_labels_in_file = set()
            if parsed_data.issues:
                for issue in parsed_data.issues:
                    if issue.labels:
                        valid_labels = [
                            lbl for lbl in issue.labels if lbl and lbl.strip()]
                        unique_labels_in_file.update(valid_labels)

            # ---- 修正: 失敗時のログと結果記録を改善 ----
            created_labels_count = 0
            skipped_labels_count = 0
            result.created_labels = []
            result.failed_labels = [] # (名前, エラーメッセージ) のタプルリスト
            sorted_labels = sorted(list(unique_labels_in_file))
            total_labels = len(sorted_labels)

            if total_labels > 0:
                logger.debug(f"Found {total_labels} unique labels in file: {sorted_labels}")
                for i, label_name in enumerate(sorted_labels):
                    context = f"ensuring label '{label_name}' in {repo_full_name}" # コンテキストを定義
                    logger.info(f"Processing label {i+1}/{total_labels}: '{label_name}'")
                    try:
                        created = self.github_client.create_label(repo_owner, repo_name, label_name)
                        if created: created_labels_count += 1
                        else: skipped_labels_count += 1
                        result.created_labels.append(label_name)
                    except GitHubClientError as e:
                        # 失敗したラベル名とエラーメッセージを記録
                        error_msg = f"Failed to {context}: {e}"
                        logger.error(error_msg)
                        result.failed_labels.append((label_name, str(e))) # エラーメッセージのみ記録
                    except Exception as e:
                        # 予期せぬエラーも同様に記録
                        error_msg = f"Unexpected error during {context}: {e}"
                        logger.exception(error_msg) # トレースバックも記録
                        result.failed_labels.append((label_name, f"Unexpected error: {e}"))
            # --------------------------------------------
            else:
                logger.info("No valid labels found in parsed data to ensure.")

            log_label_summary = (
                f"Step 4 finished. New labels: {created_labels_count}, "
                f"Existing/Skipped: {skipped_labels_count}, Failed: {len(result.failed_labels)}."
            )
            if result.failed_labels:
                logger.warning(log_label_summary +
                               f" Failed labels: {[l[0] for l in result.failed_labels]}")
            else:
                logger.info(log_label_summary)

            # --- ステップ 5: マイルストーン作成/確認 (複数対応) ---
            logger.info(f"Step 5: Ensuring required milestones exist in {repo_full_name}...")
            # 全ての一意なマイルストーン名を収集
            unique_milestones_in_file = set()
            if parsed_data.issues:
                for issue in parsed_data.issues:
                    if issue.milestone and issue.milestone.strip():
                        unique_milestones_in_file.add(issue.milestone.strip())

            # ---- 修正: 失敗時のログと結果記録を改善 ----
            milestone_id_map = {}
            total_milestones = len(unique_milestones_in_file)
            result.processed_milestones = [] # (名前, ID) のタプルリスト
            result.failed_milestones = []   # (名前, エラーメッセージ) のタプルリスト

            if total_milestones > 0:
                logger.info(f"Found {total_milestones} unique milestones to process")
                for i, milestone_name in enumerate(sorted(unique_milestones_in_file)):
                    context = f"ensuring milestone '{milestone_name}' in {repo_full_name}" # コンテキスト
                    logger.info(f"Processing milestone {i+1}/{total_milestones}: '{milestone_name}'")
                    try:
                        milestone_id = self.github_client.create_milestone(repo_owner, repo_name, milestone_name)
                        milestone_id_map[milestone_name] = milestone_id
                        result.processed_milestones.append((milestone_name, milestone_id))
                        # logger.info 内で ID が表示されるので成功ログは省略可
                    except GitHubClientError as e:
                        error_msg = f"Failed to {context}: {e}"
                        logger.error(error_msg)
                        result.failed_milestones.append((milestone_name, str(e)))
                    except Exception as e:
                        error_msg = f"Unexpected error during {context}: {e}"
                        logger.exception(error_msg)
                        result.failed_milestones.append((milestone_name, f"Unexpected error: {e}"))
            # --------------------------------------------
            else:
                logger.info("No milestones found in parsed data.")

            # マイルストーン処理のサマリーをログ出力
            log_milestone_summary = (
                f"Step 5 finished. Processed milestones: {len(result.processed_milestones)}/{total_milestones}, "
                f"Failed: {len(result.failed_milestones)}."
            )
            if result.failed_milestones:
                logger.warning(log_milestone_summary + 
                               f" Failed milestones: {[m[0] for m in result.failed_milestones]}")
            else:
                logger.info(log_milestone_summary)

            # --- ステップ 6: プロジェクト検索 ---
            project_node_id = None
            if project_name:
                context = f"finding Project V2 '{project_name}' for owner '{repo_owner}'" # コンテキスト
                logger.info(f"Step 6: {context}...")
                try:
                    project_node_id = self.github_client.find_project_v2_node_id(repo_owner, project_name)
                    if project_node_id:
                        result.project_node_id = project_node_id
                        logger.info(f"Found Project V2 '{project_name}' with Node ID: {project_node_id}")
                    else:
                        logger.warning(f"Project V2 '{project_name}' not found. Skipping item addition.") # context 不要
                except (GitHubResourceNotFoundError, GitHubClientError) as e: # まとめて捕捉
                    # ---- 修正: ログメッセージ改善 ----
                    logger.warning(f"Could not find project during {context}: {e}. Skipping item addition.")
                    # --------------------------------
                except Exception as e:
                    logger.exception(f"Unexpected error during {context}: {e}. Skipping item addition.")
                logger.info("Step 6 finished.")
            else:
                logger.info("Step 6: No project name specified, skipping.") # メッセージ修正

            # --- ステップ 7: Issue 作成 (マイルストーンマップを渡す) ---
            logger.info(f"Step 7: Creating issues in '{repo_full_name}'...")
            # マイルストーンIDのマップを渡すように修正
            issue_result: CreateIssuesResult = self.create_issues_uc.execute(
                parsed_data, repo_owner, repo_name, milestone_id_map)
            result.issue_result = issue_result
            logger.info("Step 7 finished.")

            # --- ステップ 8: Issueをプロジェクトに追加 ---
            if project_node_id and issue_result and issue_result.created_issue_details:
                total_issues_to_add = len(issue_result.created_issue_details)
                logger.info(f"Step 8: Adding {total_issues_to_add} created issues to project '{project_name}'...")
                result.project_items_failed = []

                for i, (issue_url, issue_node_id) in enumerate(issue_result.created_issue_details):
                    # ---- 修正: コンテキスト定義とログ改善 ----
                    context = f"adding item (Issue Node ID: {issue_node_id}) to project '{project_name}' (Project Node ID: {project_node_id})"
                    logger.info(f"Processing item {i+1}/{total_issues_to_add}: {context}")
                    try:
                        item_id = self.github_client.add_item_to_project_v2(project_node_id, issue_node_id)
                        if item_id: result.project_items_added_count += 1
                        else:
                             # item_id が None 等で返るケースは API Client 側で例外を投げる想定
                             error_msg = f"Failed to {context}: Did not receive valid item ID."
                             logger.error(error_msg)
                             result.project_items_failed.append((issue_node_id, "Did not receive valid item ID"))
                    except GitHubClientError as e:
                        error_msg = f"Failed to {context}: {e}"
                        logger.error(error_msg)
                        result.project_items_failed.append((issue_node_id, str(e)))
                    except Exception as e:
                        error_msg = f"Unexpected error during {context}: {e}"
                        logger.exception(error_msg)
                        result.project_items_failed.append((issue_node_id, f"Unexpected error: {e}"))
                    # --------------------------------------------

                # ---- 修正: サマリー表示改善 ----
                log_proj_summary = (
                    f"Step 8 finished. Project Integration: Added: {result.project_items_added_count}/{total_issues_to_add}, "
                    f"Failed: {len(result.project_items_failed)}/{total_issues_to_add}."
                )
                if result.project_items_failed:
                     logger.warning(log_proj_summary + f" Failed items: {[f[0] for f in result.project_items_failed]}")
                else:
                     logger.info(log_proj_summary)
            # ---- 修正: Issueがない場合などの表示 ----
            elif project_node_id and project_name:
                logger.info("Step 8: Project found, but no issues were created to add.")
            elif project_name:
                logger.info("Step 8: Project not found or failed to retrieve its ID. Skipping item addition.")
            # -----------------------------------
            else:
                logger.info("Step 8: No project integration specified.")

            logger.info(
                "GitHub resource creation workflow completed successfully.")

        # --- エラーハンドリング ---
        except (ValueError, GitHubValidationError, GitHubAuthenticationError, GitHubClientError) as e:
            # 致命的なエラー（リポジトリ名解決、リポジトリ作成など）
            error_message = f"Workflow halted due to error: {type(e).__name__} - {e}"
            logger.error(error_message)
            result.fatal_error = error_message
            # main.py に処理を委ねるため、ここでは再送出しない方がよい場合もあるが、
            # UseCase としてエラーを通知するために raise する
            raise
        except Exception as e:
            # 予期しないその他のエラー
            error_message = f"An unexpected critical error occurred during resource creation workflow: {e}"
            logger.exception(error_message) # トレースバックを出力
            result.fatal_error = error_message
            # 予期せぬエラーは GitHubClientError でラップして再送出
            raise GitHubClientError(error_message, original_exception=e) from e

        return result

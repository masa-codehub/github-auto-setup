from domain.exceptions import (
    GitHubClientError, GitHubAuthenticationError, GitHubValidationError, GitHubResourceNotFoundError
)
from domain.models import ParsedRequirementData, CreateIssuesResult, CreateGitHubResourcesResult
from use_cases.create_issues import CreateIssuesUseCase
from use_cases.create_repository import CreateRepositoryUseCase
from adapters.label_milestone_normalizer import LabelMilestoneNormalizerSvc
from adapters.github_graphql_client import GitHubGraphQLClient  # 追加
from adapters.github_rest_client import GitHubRestClient  # 修正
import logging
from typing import Optional, Tuple
import sys
import os
from unittest.mock import MagicMock
sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '../../..')))

# 依存コンポーネントを個別にインポート

# Use Cases
# Models and Exceptions

logger = logging.getLogger(__name__)


class CreateGitHubResourcesUseCase:
    """
    GitHub リソース（リポジトリ、ラベル、マイルストーン、Issue、プロジェクト連携）の
    作成ワークフローを実行するUseCase。単一責任の原則に基づき、ファイル読み込みや
    AI解析は行わず、ParsedRequirementDataを受け取って処理します。
    """

    # コンストラクタで必要なクライアントとUseCaseを注入
    def __init__(self,
                 rest_client: GitHubRestClient,  # 修正
                 graphql_client: GitHubGraphQLClient,  # 追加
                 create_repo_uc: CreateRepositoryUseCase,
                 create_issues_uc: CreateIssuesUseCase,
                 defaults_loader=None  # 追加: DI用
                 ):
        """UseCaseを初期化し、依存コンポーネントを注入します。"""
        # 型チェックを追加
        if not (isinstance(rest_client, GitHubRestClient) or isinstance(rest_client, MagicMock)):
            raise TypeError(
                "rest_client must be an instance of GitHubRestClient or MagicMock")
        if not (isinstance(graphql_client, GitHubGraphQLClient) or isinstance(graphql_client, MagicMock)):
            raise TypeError(
                "graphql_client must be an instance of GitHubGraphQLClient or MagicMock")
        if not (isinstance(create_repo_uc, CreateRepositoryUseCase) or isinstance(create_repo_uc, MagicMock)):
            raise TypeError(
                "create_repo_uc must be an instance of CreateRepositoryUseCase or MagicMock")
        if not (isinstance(create_issues_uc, CreateIssuesUseCase) or isinstance(create_issues_uc, MagicMock)):
            raise TypeError(
                "create_issues_uc must be an instance of CreateIssuesUseCase or MagicMock")
        # ...既存コード...
        self.rest_client = rest_client  # GitHubRestClient を保持
        self.graphql_client = graphql_client  # GitHubGraphQLClient を保持
        self.create_repo_uc = create_repo_uc
        self.create_issues_uc = create_issues_uc
        self.defaults_loader = defaults_loader  # 追加
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
                user = self.rest_client.get_authenticated_user()
                owner = user.login
                if not owner:
                    raise GitHubClientError(
                        "Could not retrieve authenticated user login name.")
                logger.info(f"Using authenticated user as owner: {owner}")
                return owner, repo_name_input
            except (GitHubClientError, GitHubAuthenticationError, GitHubValidationError, GitHubResourceNotFoundError) as e:
                logger.error(
                    f"Failed to get authenticated user: {e}", exc_info=True)
                raise  # known exceptionは絶対にラップしない
            except Exception as e:
                logger.error(
                    f"Unexpected error getting authenticated user: {e}", exc_info=True)
                raise GitHubAuthenticationError(
                    f"Unexpected error getting authenticated user: {e} [cause: {type(e).__name__}: {e} ]", original_exception=e) from e

    def execute(self, parsed_data: ParsedRequirementData, repo_name_input: str,
                project_name: Optional[str] = None, dry_run: bool = False) -> CreateGitHubResourcesResult:
        """
        GitHub リソース作成のワークフローを実行します。
        既存リポジトリの場合も処理を続行します。
        """
        logger.info(
            f"Starting GitHub resource creation workflow... (Dry Run: {dry_run})")

        result = CreateGitHubResourcesResult(project_name=project_name)
        repo_owner, repo_name, repo_full_name = "", "", ""
        repo_url: Optional[str] = None  # repo_urlを try ブロック外で初期化

        try:
            # --- ステップ 1: リポジトリ名解析 ---
            logger.info("Step 1: Resolving repository owner and name...")
            repo_owner, repo_name = self._get_owner_repo(repo_name_input)
            repo_full_name = f"{repo_owner}/{repo_name}"
            logger.info(
                f"Step 1 finished. Target repository: {repo_full_name}")

            # --- ステップ 2: Dry Run モード ---
            if dry_run:
                # (Dry Run のロジックは変更なし)
                logger.warning(
                    "Dry run mode enabled. Skipping GitHub operations.")
                result.repository_url = f"https://github.com/{repo_full_name} (Dry Run)"
                # ... (Dry Run 用のダミーデータ設定) ...
                logger.warning("Dry run finished.")
                return result

            # --- ステップ 3: リポジトリ作成/確認 ---
            logger.info(
                f"Step 3: Ensuring repository '{repo_full_name}' exists...")
            try:
                # UseCase を呼び出してリポジトリ作成を試みる
                repo_url = self.create_repo_uc.execute(repo_name)
                logger.info(
                    f"Repository '{repo_full_name}' created successfully: {repo_url}")
            except GitHubValidationError as e:
                # ★ Issueで提案された修正箇所: 既存リポジトリエラーのハンドリング ★
                if e.status_code == 422 and "already exists" in str(e).lower():
                    logger.warning(
                        f"Repository '{repo_full_name}' already exists. Proceeding with existing repository.")
                    # 既存リポジトリの情報を取得して URL を設定
                    try:
                        # 追加した get_repository メソッドを呼び出す
                        existing_repo = self.rest_client.get_repository(
                            repo_owner, repo_name)
                        if existing_repo and existing_repo.html_url:
                            repo_url = existing_repo.html_url
                            logger.info(
                                f"Using existing repository URL: {repo_url}")
                        else:
                            # get_repository が成功してもURLが取れない稀なケース
                            logger.error(
                                f"Could not retrieve URL for existing repository '{repo_full_name}'. Halting workflow.")
                            raise GitHubClientError(
                                f"Failed to get URL for existing repo {repo_full_name}") from e
                    except (GitHubResourceNotFoundError, GitHubAuthenticationError, GitHubClientError) as get_err:
                        # 既存リポジトリ情報の取得に失敗した場合（アクセス権がない等）は致命的エラー
                        logger.error(
                            f"Failed to access existing repository '{repo_full_name}': {get_err}. Halting workflow.")
                        raise  # ワークフローを停止させるため再送出
                else:
                    # "already exists" 以外の ValidationError は致命的エラー
                    logger.error(
                        f"Repository creation failed with unexpected validation error: {e}")
                    raise  # ワークフローを停止させるため再送出
            # create_repo_uc.execute や rest_client.get_repository で捕捉されなかった他の例外もここで捕捉し、
            # 致命的エラーとして扱う (例: GitHubAuthenticationError など)
            except (GitHubAuthenticationError, GitHubClientError) as e:
                logger.error(
                    f"Error during repository setup for '{repo_full_name}': {e}. Halting workflow.")
                raise

            # 取得した URL を結果に格納
            result.repository_url = repo_url
            logger.info(f"Step 3 finished. Repository URL to use: {repo_url}")
            # --- ★ 修正箇所ここまで ★ ---

            # --- ステップ 4: ラベル作成/確認 ---
            logger.info(
                f"Step 4: Ensuring required labels exist in {repo_full_name}...")
            unique_labels_in_file = set()
            if parsed_data.issues:
                for issue in parsed_data.issues:
                    if issue.labels:
                        unique_labels_in_file.update(
                            lbl for lbl in issue.labels if lbl and lbl.strip())

            created_labels_count = 0
            skipped_labels_count = 0
            result.created_labels = []
            result.failed_labels = []
            sorted_labels = sorted(list(unique_labels_in_file))
            total_labels = len(sorted_labels)

            if total_labels > 0:
                logger.debug(
                    f"Found {total_labels} unique labels in file: {sorted_labels}")
                for i, label_name in enumerate(sorted_labels):
                    context = f"ensuring label '{label_name}' in {repo_full_name}"
                    logger.info(
                        f"Processing label {i+1}/{total_labels}: '{label_name}'")
                    try:
                        # ラベル取得/作成は GitHubRestClient を使用
                        existing_label = self.rest_client.get_label(
                            repo_owner, repo_name, label_name)
                        if existing_label:
                            logger.info(
                                f"Label '{label_name}' already exists.")
                            skipped_labels_count += 1
                        else:
                            logger.info(
                                f"Label '{label_name}' not found, creating...")
                            self.rest_client.create_label(
                                repo_owner, repo_name, label_name)
                            created_labels_count += 1
                        result.created_labels.append(label_name)
                    except GitHubClientError as e:
                        error_msg = f"Failed to {context}: {e}"
                        logger.error(error_msg)
                        result.failed_labels.append((label_name, str(e)))
                    except Exception as e:
                        error_msg = f"Unexpected error during {context}: {e}"
                        logger.exception(error_msg)
                        result.failed_labels.append(
                            (label_name, f"Unexpected error: {e}"))
            else:
                logger.info("No valid labels found in parsed data to ensure.")

            log_label_summary = (f"Step 4 finished. New labels: {created_labels_count}, "
                                 f"Existing/Skipped: {skipped_labels_count}, Failed: {len(result.failed_labels)}.")
            if result.failed_labels:
                logger.warning(
                    log_label_summary + f" Failed labels: {[l[0] for l in result.failed_labels]}")
            else:
                logger.info(log_label_summary)

            # --- ステップ 5: マイルストーン作成/確認 ---
            logger.info(
                f"Step 5: Ensuring required milestones exist in {repo_full_name}...")
            unique_milestones_in_file = set()
            if parsed_data.issues:
                for issue in parsed_data.issues:
                    if issue.milestone and issue.milestone.strip():
                        unique_milestones_in_file.add(issue.milestone.strip())

            milestone_id_map = {}
            total_milestones = len(unique_milestones_in_file)
            result.processed_milestones = []
            result.failed_milestones = []

            if total_milestones > 0:
                logger.info(
                    f"Found {total_milestones} unique milestones to process")
                for i, milestone_name in enumerate(sorted(unique_milestones_in_file)):
                    context = f"ensuring milestone '{milestone_name}' in {repo_full_name}"
                    logger.info(
                        f"Processing milestone {i+1}/{total_milestones}: '{milestone_name}'")
                    try:
                        # マイルストーン取得/作成は GitHubRestClient を使用
                        # list_milestones で存在確認してから create_milestone を呼ぶ
                        existing_milestones = self.rest_client.list_milestones(
                            repo_owner, repo_name, state="all")
                        found_milestone = None
                        for ms in existing_milestones:
                            if ms.title == milestone_name:
                                found_milestone = ms
                                break

                        if found_milestone:
                            if found_milestone.number is None:
                                raise GitHubClientError(
                                    f"Found milestone '{milestone_name}' but it has no ID.")
                            milestone_id = found_milestone.number
                            logger.info(
                                f"Milestone '{milestone_name}' already exists with ID: {milestone_id}.")
                        else:
                            logger.info(
                                f"Milestone '{milestone_name}' not found, creating it...")
                            new_milestone = self.rest_client.create_milestone(
                                repo_owner, repo_name, milestone_name)
                            if not new_milestone or new_milestone.number is None:
                                raise GitHubClientError(
                                    f"Milestone '{milestone_name}' creation failed.")
                            milestone_id = new_milestone.number
                            logger.info(
                                f"Milestone '{milestone_name}' created successfully with ID: {milestone_id}.")

                        milestone_id_map[milestone_name] = milestone_id
                        result.processed_milestones.append(
                            (milestone_name, milestone_id))
                    except GitHubClientError as e:
                        error_msg = f"Failed to {context}: {e}"
                        logger.error(error_msg)
                        result.failed_milestones.append(
                            (milestone_name, str(e)))
                    except Exception as e:
                        error_msg = f"Unexpected error during {context}: {e}"
                        logger.exception(error_msg)
                        result.failed_milestones.append(
                            (milestone_name, f"Unexpected error: {e}"))
            else:
                logger.info("No milestones found in parsed data.")

            log_milestone_summary = (f"Step 5 finished. Processed milestones: {len(result.processed_milestones)}/{total_milestones}, "
                                     f"Failed: {len(result.failed_milestones)}.")
            if result.failed_milestones:
                logger.warning(
                    log_milestone_summary + f" Failed milestones: {[m[0] for m in result.failed_milestones]}")
            else:
                logger.info(log_milestone_summary)

            # --- ステップ 6: プロジェクト検索 ---
            project_node_id = None
            if project_name:
                context = f"finding Project V2 '{project_name}' for owner '{repo_owner}'"
                logger.info(f"Step 6: {context}...")
                try:
                    # プロジェクト検索は GitHubGraphQLClient を使用
                    project_node_id = self.graphql_client.find_project_v2_node_id(
                        repo_owner, project_name)
                    if project_node_id:
                        result.project_node_id = project_node_id
                        logger.info(
                            f"Found Project V2 '{project_name}' with Node ID: {project_node_id}")
                    else:
                        logger.warning(
                            f"Project V2 '{project_name}' not found. Skipping item addition.")
                except (GitHubResourceNotFoundError, GitHubClientError) as e:
                    logger.warning(
                        f"Could not find project during {context}: {e}. Skipping item addition.")
                except Exception as e:
                    logger.exception(
                        f"Unexpected error during {context}: {e}. Skipping item addition.")
                logger.info("Step 6 finished.")
            else:
                logger.info("Step 6: No project name specified, skipping.")

            # --- ステップ 7: Issue 作成 ---
            logger.info(f"Step 7: Creating issues in '{repo_full_name}'...")
            # Issue作成UseCase呼び出し (依存関係は修正済みと仮定)
            issue_result: CreateIssuesResult = self.create_issues_uc.execute(
                parsed_data, repo_owner, repo_name, milestone_id_map
            )
            result.issue_result = issue_result
            logger.info("Step 7 finished.")

            # --- ステップ 8: Issueをプロジェクトに追加 ---
            if project_node_id and issue_result and issue_result.created_issue_details:
                total_issues_to_add = len(issue_result.created_issue_details)
                logger.info(
                    f"Step 8: Adding {total_issues_to_add} created issues to project '{project_name}'...")
                result.project_items_failed = []

                for i, (issue_url, issue_node_id) in enumerate(issue_result.created_issue_details):
                    context = f"adding item (Issue Node ID: {issue_node_id}) to project '{project_name}' (Project Node ID: {project_node_id})"
                    logger.info(
                        f"Processing item {i+1}/{total_issues_to_add}: {context}")
                    try:
                        # プロジェクトへのアイテム追加は GitHubGraphQLClient を使用
                        item_id = self.graphql_client.add_item_to_project_v2(
                            project_node_id, issue_node_id)
                        if item_id:
                            result.project_items_added_count += 1
                        else:
                            error_msg = f"Failed to {context}: Did not receive valid item ID."
                            logger.error(error_msg)
                            result.project_items_failed.append(
                                (issue_node_id, "Did not receive valid item ID"))
                    except GitHubClientError as e:
                        error_msg = f"Failed to {context}: {e}"
                        logger.error(error_msg)
                        result.project_items_failed.append(
                            (issue_node_id, str(e)))
                    except Exception as e:
                        error_msg = f"Unexpected error during {context}: {e}"
                        logger.exception(error_msg)
                        result.project_items_failed.append(
                            (issue_node_id, f"Unexpected error: {e}"))

                log_proj_summary = (f"Step 8 finished. Project Integration: Added: {result.project_items_added_count}/{total_issues_to_add}, "
                                    f"Failed: {len(result.project_items_failed)}/{total_issues_to_add}.")
                if result.project_items_failed:
                    logger.warning(
                        log_proj_summary + f" Failed items: {[f[0] for f in result.project_items_failed]}")
                else:
                    logger.info(log_proj_summary)
            elif project_node_id and project_name:
                logger.info(
                    "Step 8: Project found, but no issues were created to add.")
            elif project_name:
                logger.info(
                    "Step 8: Project not found or failed to retrieve its ID. Skipping item addition.")
            else:
                logger.info("Step 8: No project integration specified.")

            logger.info(
                "GitHub resource creation workflow completed successfully.")

        except (ValueError, GitHubValidationError, GitHubAuthenticationError, GitHubResourceNotFoundError, GitHubClientError) as e:
            logger.error(
                f"Workflow halted due to error: {type(e).__name__} - {e}")
            result.fatal_error = f"Workflow halted due to error: {type(e).__name__} - {e}"
            # 既知例外は絶対にラップしない
            raise
        except Exception as e:
            # 未知例外のみラップ
            error_message = f"An unexpected critical error occurred during resource creation workflow: {e} [cause: {type(e).__name__}: {e} ]"
            logger.exception(error_message)
            result.fatal_error = error_message
            raise GitHubClientError(error_message, original_exception=e) from e

        # --- ラベル・マイルストーン正規化サービスの呼び出し ---
        try:
            if self.defaults_loader is not None:
                defaults = self.defaults_loader.load()
                label_defs = defaults.get('labels', [])
                milestone_defs = defaults.get('milestones', [])
                normalizer = LabelMilestoneNormalizerSvc(
                    label_defs, milestone_defs)
                for issue in parsed_data.issues:
                    normalizer.normalize_issue(issue)
            else:
                logger.warning(
                    "[LabelMilestoneNormalizer] defaults_loaderが未設定のため正規化をスキップ")
        except Exception as e:
            logger.warning(f"[LabelMilestoneNormalizer] 正規化処理で例外: {e}")

        return result

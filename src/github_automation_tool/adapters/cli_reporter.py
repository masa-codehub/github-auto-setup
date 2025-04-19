import logging
from typing import List, Optional, Tuple

# domain/models.py から結果用データクラスをインポートすることを想定
# (CreateIssuesResult は前回定義済み)
from github_automation_tool.domain.models import CreateIssuesResult, CreateGitHubResourcesResult
# GitHubクライアントが返す例外もインポート (リポジトリ作成結果表示で使用)
from github_automation_tool.domain.exceptions import GitHubValidationError, GitHubClientError

# このモジュール用のロガーを取得
logger = logging.getLogger(__name__)

class CliReporter:
    """
    処理結果を整形してコンソール (ロガー経由) に表示するクラス。
    """

    def display_issue_creation_result(self, result: CreateIssuesResult, repo_full_name: Optional[str] = None):
        """
        Issue作成ユースケースの実行結果を表示します。

        Args:
            result: CreateIssuesUseCase から返された CreateIssuesResult オブジェクト。
            repo_full_name: 対象リポジトリのフルネーム (例: 'owner/repo')。表示に含める場合。
        """
        repo_info = f" for repository '{repo_full_name}'" if repo_full_name else ""
        # --- 結果のサマリーを INFO レベルで表示 ---
        logger.info(f"--- Issue Creation Summary{repo_info} ---")
        created_count = len(result.created_issue_details)
        skipped_count = len(result.skipped_issue_titles)
        failed_count = len(result.failed_issue_titles)
        summary = (
            f"Total processed: {created_count + skipped_count + failed_count}, "
            f"Created: {created_count}, "
            f"Skipped: {skipped_count}, "
            f"Failed: {failed_count}"
        )
        logger.info(summary)

        # --- 各詳細情報を適切なログレベルで表示 ---
        if result.created_issue_details:
            logger.info("[Created Issues]")
            for url, node_id in result.created_issue_details:
                logger.info(f"- {url}")

        if result.skipped_issue_titles:
            logger.warning("[Skipped Issues (Already Exist)]") # スキップは警告レベルが適切かも
            for title in result.skipped_issue_titles:
                logger.warning(f"- '{title}'")

        if result.failed_issue_titles:
            logger.error("[Failed Issues]") # 失敗はエラーレベル
            for title, error_msg in zip(result.failed_issue_titles, result.errors):
                # エラーメッセージの改行はスペースに置換して見やすくする
                formatted_error = str(error_msg).replace('\n', ' ')
                logger.error(f"- '{title}': {formatted_error}")

        logger.info("-" * 40) # 区切り線

    def display_repository_creation_result(self, repo_url: Optional[str], repo_name: str, error: Optional[Exception] = None):
        """
        リポジトリ作成ユースケースの実行結果を表示します。

        Args:
            repo_url: 作成成功した場合のリポジトリURL。
            repo_name: 作成しようとしたリポジトリ名。
            error: 作成中に発生した例外 (任意)。
        """
        logger.info(f"--- Repository Creation Summary for '{repo_name}' ---")
        if repo_url:
            logger.info(f"[Success] Repository created: {repo_url}")
        # エラーが「既に存在する」ことによる ValidationError かどうかを判定
        elif isinstance(error, GitHubValidationError) and error.status_code == 422 and "already exists" in str(error).lower():
            logger.warning(f"[Skipped] Repository '{repo_name}' already exists.")
        elif error:
            logger.error(f"[Failed] Could not create repository '{repo_name}': {type(error).__name__} - {error}")
        else:
            # URLもエラーもない異常事態 (通常は起こらないはず)
            logger.error(f"[Failed] Repository creation failed for '{repo_name}' with unknown error.")
        logger.info("-" * 40)

    def display_general_error(self, error: Exception, context: str = "during processing"):
        """
        処理全体が中断するような予期せぬエラーを表示します。

        Args:
            error: 発生した例外。
            context: エラーが発生した状況を示す文字列。
        """
        logger.critical(f"--- Critical Error {context} ---") # 重大なエラーは CRITICAL レベル
        logger.critical(f"An unexpected error occurred: {type(error).__name__} - {error}", exc_info=True) # トレースバックも出力
        logger.critical("Processing halted.")
        logger.info("-" * 40)
    
    def display_create_github_resources_result(self, result: CreateGitHubResourcesResult):
        """
        CreateGitHubResourcesUseCase の実行結果を総合的に表示します。

        Args:
            result: UseCaseから返された総合的な結果オブジェクト。
        """
        logger.info("=" * 60)
        logger.info("     GITHUB RESOURCE CREATION SUMMARY     ")
        logger.info("=" * 60)
        
        # 致命的エラーがあれば最初に表示
        if result.fatal_error:
            logger.critical(f"[FATAL ERROR] {result.fatal_error}")
            logger.info("-" * 60)
            return
        
        # Dry Runモードかどうかを確認（リポジトリURLに "Dry Run" が含まれているかで判断）
        is_dry_run = result.repository_url and "(Dry Run)" in result.repository_url
        if is_dry_run:
            logger.info("[DRY RUN MODE] No actual GitHub operations were performed")
            
        # リポジトリ情報
        if result.repository_url:
            logger.info(f"[Repository]: {result.repository_url}")
        else:
            logger.warning("[Repository] No repository URL available")
            
        # ラベル情報
        if result.created_labels or result.failed_labels:
            if is_dry_run:
                logger.info(f"[Labels]: Would create: {', '.join(result.created_labels)}")
            else:
                label_summary = (
                    f"[Labels] Successful: {len(result.created_labels)}, "
                    f"Failed: {len(result.failed_labels)}"
                )
                logger.info(label_summary)
                
                if result.created_labels:
                    logger.info(f"  Created/Existing Labels: {', '.join(result.created_labels)}")
                    
                if result.failed_labels:
                    logger.warning("  Failed Labels:")
                    for label_name, error_msg in result.failed_labels:
                        logger.warning(f"  - '{label_name}': {error_msg}")
        else:
            logger.info("[Labels] No labels processed")
            
        # マイルストーン情報
        if result.milestone_name:
            if is_dry_run:
                logger.info(f"[Milestone]: Would create: {result.milestone_name}")
            elif result.milestone_id is not None:
                logger.info(f"[Milestone] '{result.milestone_name}' (ID: {result.milestone_id})")
            elif result.milestone_creation_error:
                logger.error(f"[Milestone] Failed to create '{result.milestone_name}': {result.milestone_creation_error}")
            else:
                logger.warning(f"[Milestone] '{result.milestone_name}' processing result unknown")
        else:
            logger.info("[Milestone] No milestone processed")
            
        # プロジェクト情報
        if result.project_name:
            if is_dry_run:
                logger.info(f"[Project]: Would add {result.project_items_added_count} issues to {result.project_name}")
            elif result.project_node_id:
                logger.info(f"[Project] Found '{result.project_name}' (Node ID: {result.project_node_id})")
                
                # プロジェクト連携の結果
                if result.issue_result and result.issue_result.created_issue_details:
                    total_issues = len(result.issue_result.created_issue_details)
                    logger.info(f"  Project Integration: Added {result.project_items_added_count}/{total_issues} issues")
                    
                    if result.project_items_failed:
                        logger.warning(f"  Failed to add {len(result.project_items_failed)} issues to project:")
                        for node_id, error in result.project_items_failed:
                            logger.warning(f"  - Issue (Node ID: {node_id}): {error}")
            else:
                logger.warning(f"[Project] Project '{result.project_name}' not found or failed to retrieve its ID")
        else:
            logger.info("[Project] No project integration specified")
            
        # Issue作成結果
        if result.issue_result:
            logger.info("-" * 60)
            self.display_issue_creation_result(result.issue_result)
        else:
            logger.info("[Issues] No issue results available")
            
        logger.info("=" * 60)

    # --- 今後実装する他のリソースに関する表示メソッド ---
    # def display_label_creation_result(...)
    # def display_milestone_creation_result(...)
    # def display_project_creation_result(...)
    # def display_project_linking_result(...)
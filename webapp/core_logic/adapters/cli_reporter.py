import logging
from typing import List, Optional, Tuple

# domain/models.py から結果用データクラスをインポートすることを想定
# (CreateIssuesResult は前回定義済み)
from core_logic.domain.models import CreateIssuesResult, CreateGitHubResourcesResult
from core_logic.domain.exceptions import GitHubValidationError, GitHubClientError

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
        validation_failed_count = len(result.validation_failed_assignees)

        # ---- 修正箇所 ----
        # サマリー表示を修正し、各項目を明確に区切って表示
        summary_parts = [
            f"Total processed: {created_count + skipped_count + failed_count}",
            f"Created: {created_count}",
            f"Skipped: {skipped_count}",  # スキップ数を明示的に表示
            f"Failed: {failed_count}"
        ]
        if validation_failed_count > 0:
            summary_parts.append(
                f"Issues with invalid assignees: {validation_failed_count}")

        logger.info(", ".join(summary_parts))  # カンマ区切りで結合して表示
        # -----------------

        # --- 各詳細情報を適切なログレベルで表示 ---
        if result.created_issue_details:
            logger.info("[Created Issues]")
            for url, node_id in result.created_issue_details:
                logger.info(f"- {url}")

        if result.skipped_issue_titles:
            logger.warning("[Skipped Issues (Already Exist)]")  # スキップは警告レベルが適切
            for title in result.skipped_issue_titles:
                logger.warning(f"- '{title}'")

        if result.failed_issue_titles:
            logger.error("[Failed Issues]")  # 失敗はエラーレベル
            for title, error_msg in zip(result.failed_issue_titles, result.errors):
                # エラーメッセージの改行はスペースに置換して見やすくする
                formatted_error = str(error_msg).replace('\n', ' ')
                logger.error(f"- '{title}': {formatted_error}")

        # 検証に失敗した担当者情報の表示を追加
        if result.validation_failed_assignees:
            logger.warning("[Issues with Invalid Assignees]")
            for title, invalid_assignees in result.validation_failed_assignees:
                logger.warning(
                    f"- '{title}': Invalid assignees: {', '.join(invalid_assignees)}")

        logger.info("-" * 40)  # 区切り線

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
            logger.warning(
                f"[Skipped] Repository '{repo_name}' already exists.")
        elif error:
            logger.error(
                f"[Failed] Could not create repository '{repo_name}': {type(error).__name__} - {error}")
        else:
            # URLもエラーもない異常事態 (通常は起こらないはず)
            logger.error(
                f"[Failed] Repository creation failed for '{repo_name}' with unknown error.")
        logger.info("-" * 40)

    def display_general_error(self, error: Exception, context: str = "during processing"):
        """
        処理全体が中断するような予期せぬエラーを表示します。

        Args:
            error: 発生した例外。
            context: エラーが発生した状況を示す文字列。
        """
        logger.critical(
            f"--- Critical Error {context} ---")  # 重大なエラーは CRITICAL レベル
        logger.critical(
            # トレースバックも出力
            f"An unexpected error occurred: {type(error).__name__} - {error}", exc_info=True)
        logger.critical("Processing halted.")
        logger.info("-" * 40)

    def display_create_github_resources_result(self, result: CreateGitHubResourcesResult):
        """CreateGitHubResourcesUseCase の実行結果を総合的に表示します。"""
        logger.info("=" * 60)
        logger.info("     GITHUB RESOURCE CREATION SUMMARY     ")
        logger.info("=" * 60)

        if result.fatal_error:
            logger.critical(f"[FATAL ERROR] {result.fatal_error}")
            logger.info("-" * 60)
            return

        # --- Dry Run モードの判定と表示 --- # 修正
        is_dry_run = result.repository_url and "(Dry Run)" in result.repository_url
        if is_dry_run:
            logger.info(
                "[DRY RUN MODE] No actual GitHub operations were performed")
        # -----------------------------------

        if result.repository_url:
            logger.info(f"[Repository]: {result.repository_url}")
        else:
            logger.warning("[Repository] No repository URL available")

        # --- ラベル情報 ---
        if result.created_labels or result.failed_labels:
            # --- Dry Run モードの表示 --- # 修正
            if is_dry_run:
                logger.info(
                    f"[Labels]: Would ensure {len(result.created_labels)} labels exist: {', '.join(result.created_labels)}")
            # ---------------------------
            else:
                logger.info(
                    f"[Labels] Successful: {len(result.created_labels)}, Failed: {len(result.failed_labels)}")
                if result.created_labels:
                    logger.info(
                        f"  Created/Existing Labels: {', '.join(result.created_labels)}")
                if result.failed_labels:
                    logger.warning("  Failed Labels:")
                    # ---- 修正: エラーメッセージを整形して表示 ----
                    for label_name, error_msg in result.failed_labels:
                        formatted_error = str(error_msg).replace(
                            '\n', ' ')  # 改行をスペースに
                        logger.warning(
                            f"  - '{label_name}': {formatted_error}")
                    # --------------------------------------------
        else:
            logger.info("[Labels] No labels processed")

        # --- マイルストーン情報 ---
        if result.processed_milestones or result.failed_milestones:
            # --- Dry Run モードの表示 --- # 修正
            if is_dry_run:
                milestone_names = [name for name,
                                   _ in result.processed_milestones]
                logger.info(
                    f"[Milestones]: Would ensure {len(milestone_names)} milestones exist: {', '.join(milestone_names)}")
            # ---------------------------
            else:
                logger.info(
                    f"[Milestones] Successful: {len(result.processed_milestones)}, Failed: {len(result.failed_milestones)}")
                if result.processed_milestones:
                    milestone_info = [
                        f"'{name}' (ID: {id})" for name, id in result.processed_milestones]
                    logger.info(
                        f"  Created/Existing Milestones: {', '.join(milestone_info)}")
                if result.failed_milestones:
                    logger.warning("  Failed Milestones:")
                    # ---- 修正: エラーメッセージを整形して表示 ----
                    for milestone_name, error_msg in result.failed_milestones:
                        formatted_error = str(error_msg).replace('\n', ' ')
                        logger.warning(
                            f"  - '{milestone_name}': {formatted_error}")
                    # --------------------------------------------
        else:
            logger.info("[Milestones] No milestones processed")

        # --- プロジェクト情報 ---
        if result.project_name:
            # --- Dry Run モードの表示 --- # 修正
            if is_dry_run:
                logger.info(
                    f"[Project]: Would add {result.project_items_added_count} items to project '{result.project_name}'")
            # ---------------------------
            elif result.project_node_id:
                logger.info(
                    f"[Project] Found '{result.project_name}' (Node ID: {result.project_node_id})")
                if result.issue_result and result.issue_result.created_issue_details:
                    total_issues = len(
                        result.issue_result.created_issue_details)  # 作成されたIssue数
                    added_count = result.project_items_added_count
                    failed_count = len(result.project_items_failed)
                    # ---- 修正: サマリー表示改善 ----
                    logger.info(
                        f"  Project Integration: Added: {added_count}/{total_issues}, Failed: {failed_count}/{total_issues}")
                    # -----------------------------
                    if result.project_items_failed:
                        logger.warning(f"  Failed to add items to project:")
                        # ---- 修正: エラーメッセージを整形して表示 ----
                        for node_id, error_msg in result.project_items_failed:
                            formatted_error = str(error_msg).replace('\n', ' ')
                            logger.warning(
                                f"  - Issue (Node ID: {node_id}): {formatted_error}")
                        # --------------------------------------------
                # ---- 修正: Issueがない場合などの表示 ----
                elif result.issue_result is None or not result.issue_result.created_issue_details:
                    logger.info(
                        "  Project Integration: No issues were created to add.")
                # -----------------------------------
            else:  # project_node_id がない場合
                logger.warning(
                    f"[Project] Project '{result.project_name}' not found or failed to retrieve its ID.")
        else:
            logger.info("[Project] No project integration specified.")

        # --- Issue作成結果 ---
        if result.issue_result:
            logger.info("-" * 60)
            # --- Dry Run モードの表示 --- # 修正
            if is_dry_run:
                logger.info("--- Issue Creation Summary (Dry Run) ---")
                logger.info(
                    f"Would process {len(result.issue_result.created_issue_details)} issues.")
                for url, _ in result.issue_result.created_issue_details:
                    logger.info(f"- Would create issue: {url}")
            # ---------------------------
            else:
                self.display_issue_creation_result(result.issue_result)
        else:
            logger.info("[Issues] No issue results available")

        logger.info("=" * 60)

    # --- 今後実装する他のリソースに関する表示メソッド ---
    # def display_label_creation_result(...)
    # def display_milestone_creation_result(...)
    # def display_project_creation_result(...)
    # def display_project_linking_result(...)

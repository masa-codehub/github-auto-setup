import logging
from typing import List, Optional, Tuple

# domain/models.py から結果用データクラスをインポートすることを想定
# (CreateIssuesResult は前回定義済み)
from github_automation_tool.domain.models import CreateIssuesResult
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

    # --- 今後実装する他のリソースに関する表示メソッド ---
    # def display_label_creation_result(...)
    # def display_milestone_creation_result(...)
    # def display_project_creation_result(...)
    # def display_project_linking_result(...)
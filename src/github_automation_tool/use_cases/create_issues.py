import logging
from github_automation_tool.adapters.github_client import GitHubAppClient
from github_automation_tool.domain.models import ParsedRequirementData, IssueData, CreateIssuesResult
from github_automation_tool.domain.exceptions import GitHubClientError # 必要に応じて他の例外も

logger = logging.getLogger(__name__)

class CreateIssuesUseCase:
    """
    解析されたデータに基づいてGitHub Issueを作成するユースケース（重複スキップ機能付き）。
    """
    def __init__(self, github_client: GitHubAppClient):
        """
        UseCaseを初期化します。

        Args:
            github_client: GitHub APIと対話するためのクライアントインスタンス。
        """
        if not isinstance(github_client, GitHubAppClient):
            raise TypeError("github_client must be an instance of GitHubAppClient")
        self.github_client = github_client

    def execute(self, parsed_data: ParsedRequirementData, owner: str, repo: str) -> CreateIssuesResult:
        """
        解析データ内の各Issueについて、存在確認を行い、存在しなければ作成します。
        エラーが発生しても、他のIssueの処理は続行します。

        Args:
            parsed_data: AIによって解析された ParsedRequirementData オブジェクト。
            owner: 対象リポジトリのオーナー名。
            repo: 対象リポジトリ名。

        Returns:
            CreateIssuesResult オブジェクト（作成成功URL、スキップタイトル、失敗タイトル、エラーリスト）。
        """
        logger.info(f"Executing CreateIssuesUseCase for {owner}/{repo} with {len(parsed_data.issues)} potential issues.")
        result = CreateIssuesResult() # 結果を格納するオブジェクト

        if not parsed_data.issues:
            logger.info("No issues found in parsed data. Nothing to create.")
            return result

        for issue_data in parsed_data.issues:
            issue_title = issue_data.title
            if not issue_title: # タイトルがないデータはスキップ (またはエラー)
                logger.warning("Skipping issue data with empty title.")
                result.failed_issue_titles.append("(Empty Title)")
                result.errors.append("Skipped issue due to empty title.")
                continue

            logger.debug(f"Processing issue: '{issue_title}'")
            try:
                # 1. Issue 存在確認
                logger.debug(f"Checking if issue '{issue_title}' already exists...")
                exists = self.github_client.find_issue_by_title(owner, repo, issue_title)

                if exists:
                    # 2a. 存在する場合: スキップ
                    logger.info(f"Issue '{issue_title}' already exists. Skipping creation.")
                    result.skipped_issue_titles.append(issue_title)
                else:
                    # 2b. 存在しない場合: 作成
                    logger.debug(f"Issue '{issue_title}' does not exist. Attempting creation...")
                    created_url = self.github_client.create_issue(
                        owner=owner,
                        repo=repo,
                        title=issue_title,
                        body=issue_data.body # models.pyでデフォルトがNoneなら or "" は不要かも
                    )
                    # create_issue が成功したら URL が返る想定
                    result.created_issue_urls.append(created_url)
                    logger.info(f"Successfully created issue '{issue_title}': {created_url}")

            # エラーハンドリング: 例外が発生してもループは止めずに記録する
            except GitHubClientError as e:
                error_msg = f"Failed to process issue '{issue_title}': {type(e).__name__} - {e}"
                logger.error(error_msg, exc_info=False) # トレースバックは冗長になる可能性があるのでFalseに
                result.failed_issue_titles.append(issue_title)
                result.errors.append(error_msg)
            except Exception as e: # 予期せぬその他のエラー
                error_msg = f"Unexpected error processing issue '{issue_title}': {type(e).__name__} - {e}"
                logger.exception(error_msg) # 予期せぬエラーなのでトレースバックも記録
                result.failed_issue_titles.append(issue_title)
                result.errors.append(error_msg)

        # ループ完了後に最終結果をログ出力
        log_summary = (
            f"CreateIssuesUseCase finished for {owner}/{repo}. "
            f"Created: {len(result.created_issue_urls)}, "
            f"Skipped: {len(result.skipped_issue_titles)}, "
            f"Failed: {len(result.failed_issue_titles)}."
        )
        if result.errors:
            logger.warning(log_summary + f" Encountered {len(result.errors)} error(s). Check results and logs for details.")
        else:
            logger.info(log_summary)

        return result
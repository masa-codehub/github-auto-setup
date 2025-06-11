import logging
# 依存関係を修正
from core_logic.adapters.github_rest_client import GitHubRestClient
from core_logic.adapters.assignee_validator import AssigneeValidator
from core_logic.adapters.label_milestone_normalizer import LabelMilestoneNormalizerSvc
from core_logic.domain.models import ParsedRequirementData, IssueData, CreateIssuesResult
from core_logic.domain.exceptions import GitHubClientError
from core_logic.adapters.github_graphql_client import GitHubGraphQLClient
from core_logic.use_cases.create_repository import CreateRepositoryUseCase

logger = logging.getLogger(__name__)


class CreateIssuesUseCase:
    """
    解析されたデータに基づいてGitHub Issueを作成するユースケース（重複スキップ機能付き）。
    """
    # コンストラクタで GitHubRestClient と AssigneeValidator を受け取る

    def __init__(self, rest_client: GitHubRestClient, assignee_validator: AssigneeValidator):
        """
        UseCaseを初期化します。

        Args:
            rest_client: GitHub APIと対話するためのクライアントインスタンス。
            assignee_validator: 担当者の検証を行うバリデータインスタンス。
        """
        if not isinstance(rest_client, GitHubRestClient):
            raise TypeError(
                "rest_client must be an instance of GitHubRestClient")
        if not isinstance(assignee_validator, AssigneeValidator):
            raise TypeError(
                "assignee_validator must be an instance of AssigneeValidator")
        self.rest_client = rest_client
        self.assignee_validator = assignee_validator  # AssigneeValidator を保持

    def execute(self, parsed_data: ParsedRequirementData, owner: str, repo: str,
                milestone_id_map: dict[str, int] = None) -> CreateIssuesResult:
        """
        解析データ内の各Issueについて、存在確認を行い、存在しなければ作成します。
        エラーが発生しても、他のIssueの処理は続行します。

        Args:
            parsed_data: AIによって解析された ParsedRequirementData オブジェクト。
            owner: 対象リポジトリのオーナー名。
            repo: 対象リポジトリ名。
            milestone_id_map: マイルストーン名からIDへのマッピング辞書（オプション）。

        Returns:
            CreateIssuesResult オブジェクト（作成成功URL、スキップタイトル、失敗タイトル、エラーリスト、検証失敗担当者情報）。
        """
        total_issues = len(parsed_data.issues)
        logger.info(
            f"Executing CreateIssuesUseCase for {owner}/{repo} with {total_issues} potential issues.")
        result = CreateIssuesResult()  # 結果を格納するオブジェクト

        if not parsed_data.issues:
            logger.info("No issues found in parsed data. Nothing to create.")
            return result

        # マイルストーンIDマップが指定されていない場合は空の辞書を使用
        if milestone_id_map is None:
            milestone_id_map = {}

        # enumerate を使ってインデックスを取得し、進捗を表示
        for i, issue_data in enumerate(parsed_data.issues):
            issue_title = issue_data.title
            logger.info(
                # 進捗ログ
                f"Processing issue {i+1}/{total_issues}: '{issue_title if issue_title else '(Empty Title)'}'")

            if not issue_title:  # タイトルがないデータはスキップ (またはエラー)
                logger.warning("Skipping issue data with empty title.")
                result.failed_issue_titles.append("(Empty Title)")
                result.errors.append("Skipped issue due to empty title.")
                continue

            try:
                # 存在確認は GitHubRestClient を使用
                logger.debug(
                    f"Checking if issue '{issue_title}' already exists...")
                # find_issue_by_title は GitHubRestClient には無いので、search_issues_and_pull_requests を使うか、
                # または GitHubRestClient に find_issue_by_title を実装する必要がある。
                # ここでは仮に search_issues_and_pull_requests を使う例とする。
                # 注意: 検索APIはレート制限が厳しい場合がある
                query = f'repo:{owner}/{repo} is:issue is:open in:title "{issue_title}"'
                search_results = self.rest_client.search_issues_and_pull_requests(
                    q=query, per_page=1)
                exists = search_results.total_count > 0 if search_results else False

                if exists:
                    # 2a. 存在する場合: スキップ
                    logger.info(
                        f"Issue '{issue_title}' already exists. Skipping creation.")
                    result.skipped_issue_titles.append(issue_title)
                else:
                    # 2b. 存在しない場合: 作成
                    # INFOレベルに変更
                    logger.info(
                        f"Issue '{issue_title}' does not exist. Attempting creation...")

                    # マイルストーン名からIDへの変換
                    milestone_id = None
                    if issue_data.milestone and issue_data.milestone.strip():
                        milestone_name = issue_data.milestone.strip()
                        milestone_id = milestone_id_map.get(milestone_name)
                        if milestone_id:
                            logger.debug(
                                f"Using milestone ID {milestone_id} for milestone '{milestone_name}'")
                        else:
                            logger.warning(
                                f"No milestone ID found for milestone '{milestone_name}', using name only")

                    # Issue本文の構築（description、tasks、relational_definition、relational_issues、acceptanceを結合）
                    body_parts = []

                    # 説明文を追加
                    if issue_data.description:
                        body_parts.append(issue_data.description)

                    # タスクリストを追加
                    tasks = [t for t in (issue_data.tasks or []) if t]
                    if tasks:
                        body_parts.append("\n## タスク\n")
                        body_parts.extend(f"- [ ] {task}" for task in tasks)

                    # 関連要件を追加
                    reqs = [r for r in (
                        issue_data.relational_definition or []) if r]
                    if reqs:
                        body_parts.append("\n## 関連要件\n")
                        body_parts.extend(f"- {req}" for req in reqs)

                    # 関連Issueを追加
                    issues = [i for i in (
                        issue_data.relational_issues or []) if i]
                    if issues:
                        body_parts.append("\n## 関連Issue\n")
                        body_parts.extend(
                            f"- {issue_ref}" for issue_ref in issues)

                    # 受け入れ基準を追加
                    accs = [a for a in (issue_data.acceptance or []) if a]
                    if accs:
                        body_parts.append("\n## 受け入れ基準\n")
                        body_parts.extend(
                            f"- [ ] {criteria}" for criteria in accs)

                    # 全体をNewlineで結合
                    constructed_body = "\n".join(body_parts)

                    # 担当者が指定されている場合、検証処理を行う
                    valid_assignees = []
                    invalid_assignees_for_issue = []
                    if issue_data.assignees:
                        logger.info(
                            f"Validating {len(issue_data.assignees)} assignee(s) for issue '{issue_title}'")
                        # AssigneeValidator を使用
                        valid_assignees, invalid_assignees_for_issue = self.assignee_validator.validate_assignees(
                            owner, repo, issue_data.assignees
                        )
                        if invalid_assignees_for_issue:
                            logger.warning(
                                f"Found {len(invalid_assignees_for_issue)} invalid assignee(s) for issue '{issue_title}': {invalid_assignees_for_issue}")
                            result.validation_failed_assignees.append(
                                (issue_title, invalid_assignees_for_issue))

                    # Issue作成は GitHubRestClient を使用
                    created_issue = self.rest_client.create_issue(
                        owner=owner,
                        repo=repo,
                        title=issue_title,
                        body=constructed_body,
                        labels=issue_data.labels,
                        milestone=milestone_id,
                        assignees=valid_assignees  # 検証済みのみ
                    )
                    # create_issue は Issue オブジェクトを返すので、URLとNode IDを抽出
                    if created_issue and created_issue.html_url and created_issue.node_id:
                        result.created_issue_details.append(
                            (created_issue.html_url, created_issue.node_id))
                    else:
                        error_msg = f"Failed to get URL or Node ID after attempting to create issue '{issue_title}'."
                        logger.error(error_msg)
                        result.failed_issue_titles.append(issue_title)
                        result.errors.append(error_msg)

            # エラーハンドリング: 例外が発生してもループは止めずに記録する
            except GitHubClientError as e:
                error_msg = f"Failed to process issue '{issue_title}': {type(e).__name__} - {e}"
                # トレースバックは冗長になる可能性があるのでFalseに
                logger.error(error_msg, exc_info=False)
                result.failed_issue_titles.append(issue_title)
                result.errors.append(error_msg)
            except Exception as e:  # 予期せぬその他のエラー
                error_msg = f"Unexpected error processing issue '{issue_title}': {type(e).__name__} - {e}"
                logger.exception(error_msg)  # 予期せぬエラーなのでトレースバックも記録
                result.failed_issue_titles.append(issue_title)
                result.errors.append(error_msg)

        # ループ完了後に最終結果をログ出力
        log_summary = (
            f"CreateIssuesUseCase finished for {owner}/{repo}. "
            f"Created: {len(result.created_issue_details)}, "
            f"Skipped: {len(result.skipped_issue_titles)}, "
            f"Failed: {len(result.failed_issue_titles)}."
        )

        # 検証失敗担当者情報を含める
        if result.validation_failed_assignees:
            log_summary += f" Issues with invalid assignees: {len(result.validation_failed_assignees)}."

        if result.errors:
            logger.warning(
                log_summary + f" Encountered {len(result.errors)} error(s). Check results and logs for details.")
        else:
            logger.info(log_summary)

        return result

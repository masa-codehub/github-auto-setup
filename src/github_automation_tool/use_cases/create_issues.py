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
        logger.info(f"Executing CreateIssuesUseCase for {owner}/{repo} with {total_issues} potential issues.")
        result = CreateIssuesResult() # 結果を格納するオブジェクト

        if not parsed_data.issues:
            logger.info("No issues found in parsed data. Nothing to create.")
            return result

        # マイルストーンIDマップが指定されていない場合は空の辞書を使用
        if milestone_id_map is None:
            milestone_id_map = {}

        # enumerate を使ってインデックスを取得し、進捗を表示
        for i, issue_data in enumerate(parsed_data.issues):
            issue_title = issue_data.title
            logger.info(f"Processing issue {i+1}/{total_issues}: '{issue_title if issue_title else '(Empty Title)'}'") # 進捗ログ

            if not issue_title: # タイトルがないデータはスキップ (またはエラー)
                logger.warning("Skipping issue data with empty title.")
                result.failed_issue_titles.append("(Empty Title)")
                result.errors.append("Skipped issue due to empty title.")
                continue

            # logger.debug(f"Processing issue: '{issue_title}'") # より詳細なので DEBUG レベルに変更 or 削除
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
                    logger.info(f"Issue '{issue_title}' does not exist. Attempting creation...") # INFOレベルに変更
                    
                    # マイルストーン名からIDへの変換
                    milestone_id = None
                    if issue_data.milestone and issue_data.milestone.strip():
                        milestone_name = issue_data.milestone.strip()
                        milestone_id = milestone_id_map.get(milestone_name)
                        if milestone_id:
                            logger.debug(f"Using milestone ID {milestone_id} for milestone '{milestone_name}'")
                        else:
                            logger.warning(f"No milestone ID found for milestone '{milestone_name}', using name only")
                    
                    # Issue本文の構築（description、tasks、relational_definition、relational_issues、acceptanceを結合）
                    body_parts = []
                    
                    # 説明文を追加
                    if issue_data.description:
                        body_parts.append(issue_data.description)
                    
                    # タスクリストを追加
                    if issue_data.tasks:
                        body_parts.append("\n## タスク\n")
                        for task in issue_data.tasks:
                            body_parts.append(f"- [ ] {task}")
                    
                    # 関連要件を追加
                    if issue_data.relational_definition:
                        body_parts.append("\n## 関連要件\n")
                        for req in issue_data.relational_definition:
                            body_parts.append(f"- {req}")
                    
                    # 関連Issueを追加
                    if issue_data.relational_issues:
                        body_parts.append("\n## 関連Issue\n")
                        for issue_ref in issue_data.relational_issues:
                            body_parts.append(f"- {issue_ref}")
                    
                    # 受け入れ基準を追加
                    if issue_data.acceptance:
                        body_parts.append("\n## 受け入れ基準\n")
                        for criteria in issue_data.acceptance:
                            body_parts.append(f"- [ ] {criteria}")
                    
                    # 全体をNewlineで結合
                    constructed_body = "\n".join(body_parts)
                    logger.debug(f"Constructed issue body with {len(body_parts)} sections")
                    
                    # 担当者検証処理のための変数を初期化
                    valid_assignees = None
                    
                    # 担当者が指定されている場合、検証処理を行う
                    if issue_data.assignees:
                        logger.info(f"Validating {len(issue_data.assignees)} assignee(s) for issue '{issue_title}'")
                        # 担当者検証処理を追加
                        original_assignees = issue_data.assignees.copy()
                        valid_assignees, invalid_assignees = self.github_client.validate_assignees(owner, repo, original_assignees)
                        
                        # 一部もしくは全員が検証に失敗した場合の処理
                        if invalid_assignees:
                            # 無効な担当者のリストを正規化（@マークを削除）
                            normalized_invalid_assignees = [a[1:] if a.startswith('@') else a for a in invalid_assignees if a.strip()]
                            
                            # 警告ログを出力
                            logger.warning(f"Found {len(invalid_assignees)} invalid assignee(s) for issue '{issue_title}': {normalized_invalid_assignees}")
                            
                            # 検証失敗した担当者情報を記録
                            result.validation_failed_assignees.append((issue_title, normalized_invalid_assignees))
                    
                    # create_issue の戻り値として (URL, Node ID) を受け取る
                    created_url, created_node_id = self.github_client.create_issue(
                        owner=owner,
                        repo=repo,
                        title=issue_title,
                        body=constructed_body,  # 構築した本文を使用
                        labels=issue_data.labels,
                        milestone=milestone_id,  # ID が見つからなかった場合は None を渡す
                        assignees=valid_assignees  # 検証済みの担当者リストを使用
                    )
                    # 正常に URL と Node ID が取得できた場合のみ result に追加
                    if created_url and created_node_id:
                        # 成功ログは create_issue 内にあるのでここでは省略しても良いかも
                        result.created_issue_details.append((created_url, created_node_id))
                    else:
                        # create_issue が成功しても URL/NodeID が返らないケース (通常は考えにくい)
                        error_msg = f"Failed to get URL or Node ID after attempting to create issue '{issue_title}'."
                        logger.error(error_msg)
                        result.failed_issue_titles.append(issue_title)
                        result.errors.append(error_msg)

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
            f"Created: {len(result.created_issue_details)}, "
            f"Skipped: {len(result.skipped_issue_titles)}, "
            f"Failed: {len(result.failed_issue_titles)}."
        )
        
        # 検証失敗担当者情報を含める
        if result.validation_failed_assignees:
            log_summary += f" Issues with invalid assignees: {len(result.validation_failed_assignees)}."
            
        if result.errors:
            logger.warning(log_summary + f" Encountered {len(result.errors)} error(s). Check results and logs for details.")
        else:
            logger.info(log_summary)

        return result
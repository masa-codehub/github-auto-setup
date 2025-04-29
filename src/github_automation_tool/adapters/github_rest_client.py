# src/github_automation_tool/adapters/github_rest_client.py
# GitHubのREST APIを扱うためのクライアントクラス

import logging
from typing import List, Optional, Dict, Any, Tuple, cast
from githubkit import GitHub, Response
# 必要なモデルを githubkit からインポート
from githubkit.versions.latest.models import (
    Label, Issue, Milestone, Repository, SimpleUser as User
)
from githubkit.exception import RequestFailed # 404ハンドリング用

# 作成したエラーハンドリングデコレータとドメイン例外をインポート
from github_automation_tool.adapters.github_utils import github_api_error_handler
from github_automation_tool.domain.exceptions import GitHubClientError, GitHubResourceNotFoundError

logger = logging.getLogger(__name__)

class GitHubRestClient:
    """
    githubkit の REST API v3 を使用して GitHub と対話するクライアント。
    エラーハンドリングはデコレータ @github_api_error_handler に委譲します。
    冪等性のチェック（存在確認）はこのクラスの責務外とし、
    各メソッドは原則としてGitHub APIの操作を直接実行します。
    """

    def __init__(self, github_instance: GitHub):
        """
        Args:
            github_instance: 認証済みの githubkit.GitHub インスタンス。
        """
        if not isinstance(github_instance, GitHub):
             # 初期化時の型チェックを追加
             raise TypeError("github_instance must be a valid githubkit.GitHub instance.")
        self.gh = github_instance
        logger.info("GitHubRestClient initialized.")

    # --- Context Generators for Decorator ---
    # デコレータに渡すコンテキスト生成メソッド (private) - **kwargs削除
    def _create_repo_context(self, repo_name: str) -> str:
        return f"creating repository '{repo_name}'"
    
    def _get_auth_user_context(self) -> str:
        return "getting authenticated user"
    
    def _get_label_context(self, owner: str, repo: str, label_name: str) -> str:
        return f"getting label '{label_name}' in {owner}/{repo}"
    
    def _create_label_context(self, owner: str, repo: str, label_name: str, **_) -> str: # color, descを受け取っても無視
        return f"creating label '{label_name}' in {owner}/{repo}"
    
    def _list_milestones_context(self, owner: str, repo: str, **_) -> str: # state, per_pageを受け取っても無視
        return f"listing milestones for {owner}/{repo}"
    
    def _create_milestone_context(self, owner: str, repo: str, title: str, **_) -> str: # state, descを受け取っても無視
        return f"creating milestone '{title}' in {owner}/{repo}"
    
    def _create_issue_context(self, owner: str, repo: str, title: str, **_) -> str: # body etc を受け取っても無視
        return f"creating issue '{title}' in {owner}/{repo}"
    
    def _search_issues_context(self, q: str, **_) -> str: # per_pageを受け取っても無視
        return f"searching issues with query '{q}'"
    
    def _check_collaborator_context(self, owner: str, repo: str, username: str) -> str:
        return f"checking collaborator status for '{username}' in {owner}/{repo}"

    # --- Repository ---
    @github_api_error_handler(_create_repo_context)
    def create_repository(self, repo_name: str) -> Repository:
        """
        新しい Private リポジトリを作成します。
        成功した場合、作成されたリポジトリの情報を含むRepositoryオブジェクトを返します。
        注意: このメソッドは冪等ではありません。リポジトリが既に存在するとエラーになります。
              (GitHubValidationError が送出されます)
        """
        # UseCase側でリポジトリ名のバリデーションは行う想定
        logger.info(f"Attempting to create private repository: {repo_name}")
        response: Response[Repository] = self.gh.rest.repos.create_for_authenticated_user(
            name=repo_name, private=True, auto_init=True # auto_init=True を維持
        )
        # デコレータがエラーをハンドルするので、ここでは成功時のチェックのみ
        if not response or not response.parsed_data:
            # 通常、APIが201を返せばparsed_dataは存在するはず
            raise GitHubClientError(f"Repository creation for '{repo_name}' seemed successful but response data is missing.")
        logger.debug(f"Successfully created repository: {response.parsed_data.html_url}") # INFO -> DEBUG
        return response.parsed_data

    # --- Authenticated User ---
    @github_api_error_handler(_get_auth_user_context)
    def get_authenticated_user(self) -> User:
        """認証されたユーザーの情報を取得します。"""
        logger.debug("Attempting to get authenticated user info...")
        response: Response[User] = self.gh.rest.users.get_authenticated()
        if not response or not response.parsed_data or not response.parsed_data.login:
            raise GitHubClientError("Could not retrieve valid authenticated user data from response.")
        logger.debug(f"Successfully retrieved authenticated user: {response.parsed_data.login}")
        return response.parsed_data

    # --- Labels ---
    # ignore_not_found=True をデコレータに指定し、404の場合はNoneを返すようにする
    @github_api_error_handler(_get_label_context, ignore_not_found=True)
    def get_label(self, owner: str, repo: str, label_name: str) -> Optional[Label]:
        """
        指定されたラベルが存在するか確認し、存在すればLabelオブジェクトを、
        存在しなければNoneを返します (404 Not Foundはエラーとしない)。
        """
        logger.debug(f"Getting label '{label_name}' for {owner}/{repo}")
        response: Response[Label] = self.gh.rest.issues.get_label(
            owner=owner, repo=repo, name=label_name
        )
        # 404の場合はデコレータがNoneを返す
        # 200 OK で parsed_data がない異常ケースは念のためチェック
        if response and response.status_code == 200 and not response.parsed_data:
             logger.warning(f"get_label for '{label_name}' returned 200 OK but no data.")
             return None
        # parsed_dataがあればそれを返す (Noneの場合もそのまま返す) - castを追加
        return cast(Optional[Label], response.parsed_data) if response else None

    @github_api_error_handler(_create_label_context)
    def create_label(self, owner: str, repo: str, label_name: str,
                     color: Optional[str] = None, description: Optional[str] = "") -> Label:
        """
        リポジトリに新しいラベルを作成します。
        成功した場合、作成されたラベルの情報を含むLabelオブジェクトを返します。
        注意: このメソッドは冪等ではありません。ラベルが既に存在するとエラーになります。
              (GitHubValidationError が送出される可能性があります)
        """
        # UseCase側で名前のバリデーションは行う想定
        trimmed_label_name = label_name.strip()
        logger.info(f"Attempting to create label '{trimmed_label_name}' in {owner}/{repo}")
        payload: Dict[str, Any] = {"name": trimmed_label_name}
        if color: payload["color"] = color.lstrip('#')
        # descriptionは空文字列でもAPIは受け付けるため、Noneチェックのみ
        if description is not None: payload["description"] = description

        response: Response[Label] = self.gh.rest.issues.create_label(
            owner=owner, repo=repo, **payload
        )
        if not response or not response.parsed_data:
            raise GitHubClientError(f"Label creation for '{trimmed_label_name}' seemed successful but response data is missing.")
        logger.debug(f"Successfully created label '{trimmed_label_name}'.") # INFO -> DEBUG
        return response.parsed_data

    # --- Milestones ---
    @github_api_error_handler(_list_milestones_context)
    def list_milestones(self, owner: str, repo: str, state: str = "open", per_page: int = 100) -> List[Milestone]:
        """指定された状態のマイルストーンをリストします。"""
        logger.debug(f"Listing {state} milestones for {owner}/{repo} (per_page={per_page})")
        response: Response[List[Milestone]] = self.gh.rest.issues.list_milestones(
            owner=owner, repo=repo, state=state, per_page=per_page
        )
        # parsed_dataがNoneや空リストの場合もそのまま返す
        return response.parsed_data if response and response.parsed_data else []

    @github_api_error_handler(_create_milestone_context)
    def create_milestone(self, owner: str, repo: str, title: str,
                         state: str = "open", description: Optional[str] = "") -> Milestone:
        """
        新しいマイルストーンを作成します。
        成功した場合、作成されたマイルストーンの情報を含むMilestoneオブジェクトを返します。
        注意: このメソッドは冪等ではありません。同名のマイルストーンが既に存在するとエラーになる可能性があります。
              (GitHubValidationError が送出される可能性があります)
        """
        # UseCase側でタイトルのバリデーションは行う想定
        trimmed_title = title.strip()
        logger.info(f"Attempting to create milestone '{trimmed_title}' in {owner}/{repo}")
        payload: Dict[str, Any] = {"title": trimmed_title}
        # stateは 'open' または 'closed' のみ許容、それ以外は 'open' にフォールバック
        payload["state"] = state if state in ("open", "closed") else "open"
        if state not in ("open", "closed"):
             logger.warning(f"Invalid state '{state}' provided for milestone '{trimmed_title}', defaulting to 'open'.")
        # descriptionは空文字列でもAPIは受け付ける
        if description is not None: payload["description"] = description

        response: Response[Milestone] = self.gh.rest.issues.create_milestone(
            owner=owner, repo=repo, **payload
        )
        if not response or not response.parsed_data or response.parsed_data.number is None:
            raise GitHubClientError(f"Milestone creation for '{trimmed_title}' seemed successful but response data is missing or invalid.")
        logger.debug(f"Successfully created milestone '{trimmed_title}' with ID {response.parsed_data.number}.") # INFO -> DEBUG
        return response.parsed_data

    # --- Issues ---
    @github_api_error_handler(_create_issue_context)
    def create_issue(self, owner: str, repo: str, title: str,
                     body: Optional[str] = None,
                     labels: Optional[List[str]] = None,
                     milestone: Optional[int] = None, # マイルストーンは数値IDで受け取る
                     assignees: Optional[List[str]] = None) -> Issue:
        """
        新しい Issue を作成します。
        成功した場合、作成されたIssueの情報を含むIssueオブジェクトを返します。
        注意: このメソッドは冪等ではありません。
        """
        # UseCase側でタイトルのバリデーションは行う想定
        trimmed_title = title.strip()
        logger.info(f"Attempting to create issue '{trimmed_title}' in {owner}/{repo}")
        payload: Dict[str, Any] = {"owner": owner, "repo": repo, "title": trimmed_title}
        if body is not None: payload["body"] = body
        # リストが渡された場合のみ、空要素を除去して設定
        if labels is not None: payload["labels"] = [lbl for lbl in labels if lbl and lbl.strip()]
        if milestone is not None: payload["milestone"] = milestone
        if assignees is not None: payload["assignees"] = [a for a in assignees if a and a.strip()]

        response: Response[Issue] = self.gh.rest.issues.create(**payload)
        if not response or not response.parsed_data or not response.parsed_data.html_url:
             raise GitHubClientError(f"Issue creation for '{trimmed_title}' seemed successful but response data is missing.")
        logger.debug(f"Successfully created issue '{trimmed_title}': {response.parsed_data.html_url}") # INFO -> DEBUG
        return response.parsed_data

    # --- Search ---
    @github_api_error_handler(_search_issues_context)
    def search_issues_and_pull_requests(self, q: str, per_page: int = 1) -> Any:
        """
        Issue と Pull Request を検索します。
        成功した場合、検索結果オブジェクトを返します。
        注意: githubkitのバージョンによって型が異なるため、Any型を使用しています。
              返却値には total_count プロパティと items プロパティが含まれることを想定します。
        """
        logger.debug(f"Searching issues/PRs with query: {q} (per_page={per_page})")
        response = self.gh.rest.search.issues_and_pull_requests(
            q=q, per_page=per_page
        )
        # parsed_dataとtotal_countの存在を確認
        if not response or not response.parsed_data or not hasattr(response.parsed_data, 'total_count') or response.parsed_data.total_count is None:
            raise GitHubClientError(f"Search for '{q}' seemed successful but response data is missing or invalid.")
        logger.debug(f"Search for '{q}' returned {response.parsed_data.total_count} total results.")
        return response.parsed_data

    # --- Collaborators ---
    # ignore_not_found=True を指定し、404の場合は False を返すようにする
    @github_api_error_handler(_check_collaborator_context, ignore_not_found=True)
    def check_collaborator(self, owner: str, repo: str, username: str) -> bool:
        """
        ユーザーがリポジトリのコラボレーターであるかを確認します。
        コラボレーターであれば True、そうでなければ False を返します (404含む)。
        APIエラー発生時は例外を送出します。
        """
        logger.debug(f"Checking collaborator status for '{username}' on {owner}/{repo}")
        # 成功時は status_code 204 が返り、parsed_data は None
        response: Optional[Response[None]] = self.gh.rest.repos.check_collaborator(
            owner=owner, repo=repo, username=username
        )
        
        # 404エラー時はデコレータによって処理され、responseがNoneになる
        if response is None:
            logger.debug(f"User '{username}' is not a collaborator on {owner}/{repo} (404 Not Found)")
            return False
            
        # 204 No Content が返された場合はコラボレーター
        is_collaborator = response.status_code == 204
        logger.debug(f"User '{username}' is{'' if is_collaborator else ' not'} a collaborator on {owner}/{repo}")
        return is_collaborator
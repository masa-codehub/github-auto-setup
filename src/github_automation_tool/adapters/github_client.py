# src/github_automation_tool/adapters/github_client.py

import logging
import json
from githubkit import GitHub, Response # Response をインポート
# モデルの推奨インポートパスに変更 (Milestone も追加)
from githubkit.versions.latest.models import Label, Issue, Milestone, Repository # Repositoryもインポート（エラーハンドリング用）
from githubkit.exception import RequestError, RequestTimeout, RequestFailed
from pydantic import SecretStr
# typing からのインポートは不要 (list, dict, any, | None を使用)
from githubkit.graphql import GraphQLResponse

# ドメイン例外をインポート
from github_automation_tool.domain.exceptions import (
    GitHubClientError, GitHubAuthenticationError, GitHubRateLimitError,
    GitHubResourceNotFoundError, GitHubValidationError
)

logger = logging.getLogger(__name__)


class GitHubAppClient:
    """
    githubkit v0.12.9 を使用して GitHub API と対話するクライアント。
    エラーハンドリングと基本的なリソース作成・検索・設定機能を提供します。
    """

    def __init__(self, auth_token: SecretStr):
        """クライアントを初期化し、認証を行います。"""
        if not auth_token or not auth_token.get_secret_value():
            raise GitHubAuthenticationError("GitHub PAT is missing or empty.")
        try:
            self.gh = GitHub(auth_token.get_secret_value())
            logger.info("GitHub client initialized successfully.")
            # self._perform_connection_test() # 必要なら有効化
        except Exception as e:
            logger.error(
                f"Failed to initialize GitHub client: {e}", exc_info=True)
            raise GitHubClientError(
                f"Failed to initialize GitHub client: {e}", original_exception=e) from e

    def _perform_connection_test(self):
        """初期化時に簡単なAPI呼び出しで接続を確認（オプション）"""
        try:
            self.gh.rest.users.get_authenticated()
            logger.debug("GitHub API connection test successful during init.")
        except RequestFailed as rf_err:
            logger.warning(f"GitHub API connection test failed: {rf_err}")
            response = getattr(rf_err, 'response', None)
            status_code = getattr(response, 'status_code', None)
            if status_code in (401, 403):
                raise GitHubAuthenticationError("Initial connection test failed (invalid PAT or insufficient scope?).",
                                                status_code=status_code, original_exception=rf_err) from rf_err
        except Exception as e:
            logger.warning(
                f"Unexpected error during GitHub API connection test: {e}")
            pass # 初期化時のテスト失敗は警告に留める場合

    def _handle_request_failed(self, error: RequestFailed, context: str) -> GitHubClientError:
        """RequestFailed 例外を解析し、適切なカスタム例外にラップします。"""
        response = getattr(error, 'response', None)
        status_code = getattr(response, 'status_code', None)
        headers = getattr(response, 'headers', {})
        error_content_bytes = getattr(response, 'content', b'')
        try:
            error_content_str = error_content_bytes.decode(
                'utf-8', errors='replace')
        except Exception:
            error_content_str = "[Could not decode error content]"

        message = f"GitHub API RequestFailed during {context} (Status: {status_code}): {error} - Response: {error_content_str}"
        logger.warning(message) # 失敗時は Warning レベル

        if status_code == 401:
            return GitHubAuthenticationError("Authentication failed (401). Check your GitHub PAT.", status_code=status_code, original_exception=error)
        elif status_code == 403:
            remaining = headers.get("X-RateLimit-Remaining")
            if remaining == "0":
                return GitHubRateLimitError("GitHub API rate limit exceeded.", status_code=status_code, original_exception=error)
            else:
                # 権限不足の可能性が高い
                return GitHubAuthenticationError("Permission denied (403). Check PAT scope.", status_code=status_code, original_exception=error)
        elif status_code == 404:
            return GitHubResourceNotFoundError(f"GitHub resource not found during {context}.", status_code=status_code, original_exception=error)
        elif status_code == 422:
             # repo 作成時の重複エラーを特別に扱う
            if "repository" in context and "name already exists" in error_content_str.lower():
                 logger.warning(f"Repository validation failed (422): Name already exists. {context}")
                 # この場合、エラーメッセージをより具体的にして返す
                 return GitHubValidationError(f"Repository name already exists: {error_content_str}", status_code=status_code, original_exception=error)
            else:
                 logger.warning(f"Validation failed (422): {error_content_str}. {context}")
                 return GitHubValidationError(f"Validation failed (422): {error_content_str}", status_code=status_code, original_exception=error)
        else:
            # その他のHTTPエラー
            logger.error(f"Unhandled GitHub API HTTP error (Status: {status_code}) during {context}: {error}")
            return GitHubClientError(f"Unhandled GitHub API HTTP error (Status: {status_code}): {error}", status_code=status_code, original_exception=error)

    def _handle_other_error(self, error: Exception, context: str) -> GitHubClientError:
        """RequestFailed 以外の例外 (ネットワークエラー等) を処理します。"""
        if isinstance(error, (RequestError, RequestTimeout)):
            logger.warning(
                f"GitHub API request/network error during {context}: {error}")
            return GitHubClientError(f"Network/Request error during {context}: {error}", original_exception=error)
        else:
            logger.error(
                f"Unexpected non-API error during {context}: {error}", exc_info=True)
            return GitHubClientError(f"Unexpected error during {context}: {error}", original_exception=error)

    def _handle_graphql_error(self, error: GraphQLResponse | Exception, context: str) -> GitHubClientError:
        """GraphQL API 呼び出しのエラーを処理します。"""
        error_message = f"GraphQL error during {context}: {error}"
        errors_list = []
        
        if isinstance(error, GraphQLResponse) and getattr(error, 'errors', None):
            errors_list = error.errors
            error_message = f"GraphQL response contained errors during {context}: {error.errors}"
            
            # エラータイプの抽出を追加（テスト対応のため）
            error_types = []
            for err in errors_list:
                if isinstance(err, dict):
                    err_type = err.get('type', '').upper()
                    if err_type:
                        error_types.append(err_type)
                    
            # テストケースのエラータイプ対応
            if 'FORBIDDEN' in error_types:
                return GitHubAuthenticationError(f"GraphQL permission denied during {context}: {errors_list}", 
                    original_exception=error if isinstance(error, Exception) else None)
            if 'NOT_FOUND' in error_types:
                return GitHubResourceNotFoundError(f"GraphQL resource not found during {context}: {errors_list}", 
                    original_exception=error if isinstance(error, Exception) else None)
            
        logger.warning(error_message)
        msg_lower = error_message.lower()
        
        if "not found" in msg_lower:
            return GitHubResourceNotFoundError(f"GraphQL resource not found during {context}: {errors_list}", 
                original_exception=error if isinstance(error, Exception) else None)
        elif "permission denied" in msg_lower or "forbidden" in msg_lower:
            return GitHubAuthenticationError(f"GraphQL permission denied during {context}: {errors_list}", 
                original_exception=error if isinstance(error, Exception) else None)
        else:
            return GitHubClientError(f"GraphQL operation failed during {context}: {errors_list}", 
                original_exception=error if isinstance(error, Exception) else None)

    def _handle_api_error(self, error: Exception, context: str) -> GitHubClientError:
        """API呼び出し中のエラーを処理し、適切な例外にラップします。すでに適切なカスタム例外の場合はそのまま返します。"""
        # すでにカスタム例外の場合はそのまま返す
        if isinstance(error, GitHubClientError):
            logger.debug(f"Passing through existing custom exception: {type(error).__name__} during {context}")
            return error
        elif isinstance(error, RequestFailed):
            return self._handle_request_failed(error, context)
        elif isinstance(error, GraphQLResponse):
            return self._handle_graphql_error(error, context)
        else:
            return self._handle_other_error(error, context)

    def create_repository(self, repo_name: str) -> str:
        """新しい Private リポジトリを作成します。"""
        context = f"creating repository '{repo_name}'"
        logger.info(f"Attempting to {context}")
        try:
            # response: Response[Repository]
            response = self.gh.rest.repos.create_for_authenticated_user(
                name=repo_name, private=True, auto_init=True
            )
            if response and response.parsed_data and hasattr(response.parsed_data, 'html_url'):
                repo_url = response.parsed_data.html_url
                logger.info(f"Successfully created repository: {repo_url}")
                return repo_url
            else:
                # これは予期しない成功レスポンス
                logger.error(f"Could not get repository URL from successful API response during {context}.")
                raise GitHubClientError(
                    "Could not retrieve repository URL after creation.")
        except Exception as e:
             # 例外をラップして再送出
             raise self._handle_api_error(e, context)

    def get_label(self, owner: str, repo: str, label_name: str) -> Label | None:
        """指定されたラベルが存在するか確認し、存在すればその情報をLabelオブジェクトとして返します。"""
        context = f"getting label '{label_name}' in {owner}/{repo}"
        logger.debug(f"Checking if label exists: {context}")
        try:
            # response: Response[Label]
            response = self.gh.rest.issues.get_label(
                owner=owner, repo=repo, name=label_name)
            if response and response.parsed_data:
                logger.debug(f"Label '{label_name}' found.")
                return response.parsed_data
            else:
                logger.warning(
                    f"get_label returned success status but no data during {context}.")
                return None
        except RequestFailed as e:
            response = getattr(e, 'response', None)
            status_code = getattr(response, 'status_code', None)
            if status_code == 404:
                logger.debug(f"Label '{label_name}' not found (404).")
                return None
            else:
                 # 404以外のRequestFailedはそのまま例外を上げる
                 raise self._handle_request_failed(e, context)
        except Exception as e:
             raise self._handle_other_error(e, context)

    def create_label(self, owner: str, repo: str, label_name: str,
                     color: str | None = None, description: str | None = "") -> bool:
        """リポジトリに新しいラベルを作成します。同名のラベルが既に存在する場合はFalseを返します。"""
        if not label_name or not label_name.strip(): # 空白のみもチェック
            logger.warning("Skipping label creation due to empty name.")
            return False

        trimmed_label_name = label_name.strip()
        context = f"ensuring label '{trimmed_label_name}' in {owner}/{repo}"
        logger.info(context + "...")
        try:
            existing_label = self.get_label(owner, repo, trimmed_label_name)
            if existing_label is not None:
                logger.info(
                    f"Label '{trimmed_label_name}' already exists. Skipping creation.")
                return False  # 存在したので False

            logger.info(f"Label '{trimmed_label_name}' not found. Creating...")
            payload: dict[str, any] = {"name": trimmed_label_name}
            if color:
                payload["color"] = color.lstrip('#')
            if description:
                payload["description"] = description

            # response: Response[Label]
            response = self.gh.rest.issues.create_label(
                owner=owner, repo=repo, **payload)

            if response and response.status_code == 201:
                logger.info(f"Successfully created label '{trimmed_label_name}'.")
                return True  # 新規作成された
            else:
                # これは予期しない成功ステータス以外の場合
                status_code = getattr(response, 'status_code', 'N/A')
                logger.error(
                    f"Label creation API call returned unexpected status: {status_code} during {context}")
                # このケースは RequestFailed で捕捉されることが多いが、念のため
                raise GitHubClientError(
                    f"Unexpected status ({status_code}) during label creation for '{trimmed_label_name}'.")
        except Exception as e:
            raise self._handle_api_error(e, context)

    # --- Milestone Methods ---

    def find_milestone_by_title(self, owner: str, repo: str, title: str, state: str = "open") -> Milestone | None:
        """
        指定されたタイトルのマイルストーンを検索し、Milestoneオブジェクトを返します。
        効率のため、まずタイトルでフィルタリングできる `list_milestones` を使用します。
        完全一致で検索します。

        Args:
            owner: リポジトリのオーナー名。
            repo: リポジトリ名。
            title: 検索するマイルストーンのタイトル。
            state: マイルストーンの状態 ('open', 'closed', 'all')。デフォルトは 'open'。

        Returns:
            見つかった Milestone オブジェクト、または見つからない場合は None。

        Raises:
            GitHubClientError: API呼び出し中にエラーが発生した場合。
        """
        if not title or not title.strip():
            logger.warning("Milestone title cannot be empty or whitespace for searching.")
            return None

        trimmed_title = title.strip()
        context = f"searching for {state} milestone titled '{trimmed_title}' in {owner}/{repo}"
        logger.debug(context)
        try:
            # list_milestones は Response[list[Milestone]] を返す
            # per_page を適切に設定（デフォルトは30。十分大きい値を設定するか、ページネーションを実装）
            response: Response[list[Milestone]] = self.gh.rest.issues.list_milestones(
                owner=owner, repo=repo, state=state, per_page=100 # 100件まで取得 (必要なら調整)
            )

            if response and response.parsed_data:
                for milestone in response.parsed_data:
                    # 完全一致で比較
                    if milestone.title == trimmed_title:
                        logger.info(f"Milestone '{trimmed_title}' found with ID {milestone.number}.")
                        return milestone
                # ループ完了後、見つからなかった場合
                logger.info(f"Milestone '{trimmed_title}' not found in {owner}/{repo} (state={state}).")
                return None
            else:
                # レスポンスは成功したがデータがない場合 (200 OK だが空リストなど)
                logger.info(f"No milestones found or empty list returned for {owner}/{repo} (state={state}).")
                return None
        except Exception as e:
            raise self._handle_api_error(e, context)

    def create_milestone(self, owner: str, repo: str, title: str,
                         state: str | None = "open", description: str | None = "") -> int | None:
        """
        新しいマイルストーンを作成します。同名の open なマイルストーンが既に存在する場合は、
        そのIDを返します（冪等性）。

        Args:
            owner: リポジトリのオーナー名。
            repo: リポジトリ名。
            title: 作成するマイルストーンのタイトル。
            state: マイルストーンの状態 ('open' or 'closed')。デフォルトは 'open'。
            description: マイルストーンの説明。

        Returns:
            作成された、または既存のマイルストーンの番号 (ID)。エラー時は None を返すことはなく例外を送出。

        Raises:
            GitHubClientError: API呼び出し中にエラーが発生した場合。
            ValueError: title が空または空白の場合。
        """
        if not title or not title.strip():
            logger.error("Milestone title cannot be empty or whitespace for creation.")
            raise ValueError("Milestone title cannot be empty or whitespace.")

        trimmed_title = title.strip()
        context = f"ensuring milestone '{trimmed_title}' in {owner}/{repo}"
        logger.info(context + "...")
        try:
            # まず同名の Open なマイルストーンが存在するか確認
            existing_milestone = self.find_milestone_by_title(owner, repo, trimmed_title, state="open")
            if existing_milestone and existing_milestone.number is not None: # numberが存在することも確認
                logger.info(f"Open milestone '{trimmed_title}' already exists with ID {existing_milestone.number}. Returning existing ID.")
                return existing_milestone.number # 既存のIDを返す

            # 存在しない場合のみ作成
            logger.info(f"Milestone '{trimmed_title}' not found or has no ID. Creating...")
            payload: dict[str, any] = {"title": trimmed_title}
            if state in ("open", "closed"): # state は 'open' か 'closed' のみ許容
                payload["state"] = state
            else:
                payload["state"] = "open" # 不正な値なら open にフォールバック
                logger.warning(f"Invalid state '{state}' provided for milestone '{trimmed_title}', defaulting to 'open'.")

            if description:
                payload["description"] = description

            # response: Response[Milestone]
            response = self.gh.rest.issues.create_milestone(owner=owner, repo=repo, **payload)

            # ステータスコード 201 (Created) で、かつ ID が取得できることを確認
            if response and response.status_code == 201 and response.parsed_data and hasattr(response.parsed_data, 'number') and response.parsed_data.number is not None:
                new_id = response.parsed_data.number
                logger.info(f"Successfully created milestone '{trimmed_title}' with ID {new_id}.")
                return new_id
            else:
                status_code = getattr(response, 'status_code', 'N/A')
                parsed_data_info = "No parsed data" if not response or not response.parsed_data else "Parsed data available but no 'number'"
                logger.error(f"Could not get valid milestone ID from API response (Status: {status_code}, Data: {parsed_data_info}) during {context}.")
                # この状況は通常APIエラーとして捕捉されるはずだが、念のためエラーを投げる
                raise GitHubClientError(
                    f"Failed to create milestone '{trimmed_title}' or retrieve its ID (Status: {status_code}).")

        except Exception as e:
            # find_milestone_by_title 内のエラーもここで捕捉される
            raise self._handle_api_error(e, context)


    # --- Issue Creation & Search ---

    def create_issue(self, owner: str, repo: str, title: str,
                     body: str | None = None,
                     labels: list[str] | None = None,
                     milestone: int | str | None = None,
                     assignees: list[str] | None = None
                     ) -> tuple[str | None, str | None]:
        """
        指定されたリポジトリに新しい Issue を作成し、関連情報を設定します。
        Milestone は数値IDまたはタイトル文字列で指定可能です。
        タイトルで指定された場合、対応する Open な Milestone の ID を検索して設定します。
        見つからない場合や検索エラー時は、警告を出力しマイルストーンなしで作成します。
        """
        if not title or not title.strip():
             # UseCase 層でバリデーションされるべきだが、念のためチェック
             logger.error("Issue title cannot be empty or whitespace.")
             raise ValueError("Issue title cannot be empty or whitespace.")

        trimmed_title = title.strip()
        context = f"creating issue '{trimmed_title}' in {owner}/{repo}"
        logger.info(f"Attempting to {context} with labels: {labels}, milestone: {milestone}, assignees: {assignees}")

        milestone_id_to_set: int | None = None # APIに渡す最終的なID

        # --- Milestone 処理 ---
        if isinstance(milestone, int):
            # 整数IDが直接指定された場合
            milestone_id_to_set = milestone
            logger.debug(f"Using provided integer milestone ID: {milestone_id_to_set} for issue '{trimmed_title}'.")
        elif isinstance(milestone, str) and milestone.strip():
            # 文字列タイトルが指定された場合、IDを検索
            milestone_title = milestone.strip()
            logger.debug(f"Milestone title '{milestone_title}' provided for issue '{trimmed_title}'. Searching for its ID...")
            try:
                # Openなマイルストーンのみ検索
                found_milestone = self.find_milestone_by_title(owner, repo, milestone_title, state="open")
                if found_milestone and found_milestone.number is not None:
                    milestone_id_to_set = found_milestone.number
                    logger.info(f"Found milestone ID {milestone_id_to_set} for title '{milestone_title}'.")
                else:
                    # 見つからなかった場合: 警告ログを出し、milestoneは設定しない
                    logger.warning(f"Open milestone with title '{milestone_title}' not found in {owner}/{repo}. Issue '{trimmed_title}' will be created without a milestone.")
            except GitHubClientError as e:
                # ID検索中にエラーが発生した場合: 警告ログを出し、milestoneは設定しない
                logger.warning(f"Could not find milestone ID for title '{milestone_title}' due to an error: {e}. Issue '{trimmed_title}' will be created without a milestone.")
        elif milestone is not None:
            # None でも int でも str でもない、または空文字列の場合
             logger.warning(f"Invalid milestone format provided: '{milestone}' for issue '{trimmed_title}'. Ignoring milestone setting.")
        # --- Milestone 処理ここまで ---

        try:
            payload: dict[str, any] = {
                "owner": owner, "repo": repo, "title": trimmed_title, "body": body or ""
            }
            if labels:
                # ラベル名のリストであることを確認（空リストは許容）
                if isinstance(labels, list):
                     payload["labels"] = [lbl for lbl in labels if isinstance(lbl, str) and lbl.strip()] # 空白ラベルを除去
                else:
                     logger.warning(f"Invalid format for labels: {labels}. Expected list[str]. Ignoring labels.")

            if milestone_id_to_set is not None: # 検索または指定されたIDを使用
                payload["milestone"] = milestone_id_to_set

            if assignees:
                 # 担当者名のリストであることを確認（空リストは許容）
                 if isinstance(assignees, list):
                      payload["assignees"] = [a for a in assignees if isinstance(a, str) and a.strip()] # 空白担当者を除去
                 else:
                      logger.warning(f"Invalid format for assignees: {assignees}. Expected list[str]. Ignoring assignees.")


            # response: Response[Issue]
            response = self.gh.rest.issues.create(**payload)

            # ステータスコード 201 (Created) で、かつ URL が取得できることを確認
            if response and response.status_code == 201 and response.parsed_data:
                issue_data = response.parsed_data
                issue_url = getattr(issue_data, 'html_url', None)
                issue_node_id = getattr(issue_data, 'node_id', None)
                if issue_url and issue_node_id:
                    logger.info(f"Successfully created issue '{trimmed_title}' (Node ID: {issue_node_id}): {issue_url}")
                    return issue_url, issue_node_id
                else:
                    logger.error(f"Could not retrieve issue URL or Node ID after creation during {context}.")
                    raise GitHubClientError("Could not retrieve issue URL or Node ID after creation.")
            else:
                status_code = getattr(response, 'status_code', 'N/A')
                parsed_data_info = "No parsed data" if not response or not response.parsed_data else "Parsed data available but no 'html_url'"
                logger.error(f"Failed to get issue URL from API response (Status: {status_code}, Data: {parsed_data_info}) during {context}.")
                raise GitHubClientError(
                    f"Could not retrieve issue URL after creation (Status: {status_code}).")
        except Exception as e:
            raise self._handle_api_error(e, context)

    def find_issue_by_title(self, owner: str, repo: str, title: str) -> bool:
        """指定されたタイトルの Open な Issue がリポジトリに存在するか確認します。"""
        if not title or not title.strip():
             logger.warning("Issue title cannot be empty or whitespace for searching.")
             return False # タイトルがないIssueは「存在しない」扱い

        trimmed_title = title.strip()
        context = f"searching for open issue titled '{trimmed_title}' in {owner}/{repo}"
        logger.debug(context)
        # GitHubの検索クエリではタイトル内の特殊文字をエスケープする必要がある場合がある
        # ここでは単純な引用符で囲むだけとする
        # 複雑なクエリは githubkit がエスケープしてくれることを期待
        query = f'repo:{owner}/{repo} is:issue is:open in:title "{trimmed_title}"'
        try:
            # Call search API and rely on parsed_data.total_count without explicit model import
            response = self.gh.rest.search.issues_and_pull_requests(q=query, per_page=1) # 1件見つかれば十分
            # レスポンスとパースされたデータ、total_count属性の存在を確認
            if response and response.parsed_data and hasattr(response.parsed_data, 'total_count') and response.parsed_data.total_count is not None:
                issue_exists = response.parsed_data.total_count > 0
                logger.debug(
                    f"Issue search result for '{trimmed_title}': {'Found' if issue_exists else 'Not found'} ({response.parsed_data.total_count} total)")
                return issue_exists
            else:
                # APIは成功したが予期しないレスポンス形式
                logger.warning(f"Could not determine issue existence from search API response during {context}. Response status: {getattr(response, 'status_code', 'N/A')}")
                # この場合、見つからなかったとして扱うか、エラーとするか？ -> API異常なのでエラーが良い
                raise GitHubClientError(
                    f"Unexpected response format from issue search API during {context}.")
        except Exception as e:
             raise self._handle_api_error(e, context)

    def find_project_v2_node_id(self, owner: str, project_name: str) -> str | None:
        if not owner or not owner.strip():
            raise ValueError("Owner login cannot be empty.")
        if not project_name or not project_name.strip():
            raise ValueError("Project name cannot be empty.")
        trimmed_owner = owner.strip()
        trimmed_name = project_name.strip()
        context = f"finding Project V2 Node ID for '{trimmed_name}' owned by '{trimmed_owner}'"
        logger.info(f"Attempting to {context}...")
        query = """
        query GetProjectV2Id($ownerLogin: String!, $projectName: String!) {
          repositoryOwner(login: $ownerLogin) {
            ... on ProjectV2Owner {
              projectsV2(query: $projectName, first: 1) {
                nodes { id title }
              }
            }
          }
        }
        """
        variables = {"ownerLogin": trimmed_owner, "projectName": trimmed_name}
        try:
            response = self.gh.graphql(query, variables)
            
            # GraphQL レベルのエラー確認を改善
            errors_list = getattr(response, 'errors', None)
            if errors_list and isinstance(errors_list, list) and len(errors_list) > 0:
                error_messages = [error.get('message', '') for error in errors_list if isinstance(error, dict)]
                error_message = ' '.join(error_messages).lower() if error_messages else ''
                
                # エラータイプの抽出
                error_types = []
                for err in errors_list:
                    if isinstance(err, dict) and 'type' in err:
                        err_type = err.get('type', '').upper()
                        if err_type:
                            error_types.append(err_type)
                            
                # エラータイプに基づく例外
                if 'FORBIDDEN' in error_types or 'permission denied' in error_message or 'forbidden' in error_message:
                    # 権限エラーは401/403に相当するエラー
                    raise GitHubAuthenticationError(f"GraphQL permission denied during {context}: {errors_list}")
                elif 'NOT_FOUND' in error_types or 'not found' in error_message:
                    # リソースが見つからないエラーは404に相当するエラー
                    raise GitHubResourceNotFoundError(f"GraphQL resource not found during {context}: {errors_list}")
                else:
                    # その他のエラー
                    raise GitHubClientError(f"GraphQL operation failed during {context}: {errors_list}")
                    
            # 正常なレスポンスを処理
            if response and hasattr(response, 'data') and response.data:
                owner_data = response.data.get("repositoryOwner")
                if owner_data:
                    projects_v2 = owner_data.get("projectsV2", {})
                    if projects_v2:
                        nodes = projects_v2.get("nodes", [])
                        if nodes and len(nodes) > 0:
                            proj = nodes[0]
                            proj_id = proj.get("id")
                            if proj_id:
                                logger.info(f"Found project '{proj.get('title')}' Node ID: {proj_id}")
                                return proj_id
            
            logger.warning(f"Project V2 '{trimmed_name}' not found for owner '{trimmed_owner}'.")
            return None
        except Exception as e:
            # Wrap all exceptions, including GraphQLResponse, into appropriate GitHubClientError
            raise self._handle_api_error(e, context)

    def add_item_to_project_v2(self, project_node_id: str, content_node_id: str) -> str | None:
        if not project_node_id or not project_node_id.strip():
            raise ValueError("Project Node ID cannot be empty.")
        if not content_node_id or not content_node_id.strip():
            raise ValueError("Content Node ID cannot be empty.")
        p_id, c_id = project_node_id.strip(), content_node_id.strip()
        context = f"adding item '{c_id}' to project '{p_id}'"
        logger.info(f"Attempting to {context}...")
        mutation = """
        mutation AddItemToProject($projectId: ID!, $contentId: ID!) {
          addProjectV2ItemById(input: {projectId: $projectId, contentId: $contentId}) { item { id } }
        }
        """
        variables = {"projectId": p_id, "contentId": c_id}
        try:
            response = self.gh.graphql(mutation, variables)
            
            # GraphQL レベルのエラー確認を改善
            errors_list = getattr(response, 'errors', None)
            if errors_list and isinstance(errors_list, list) and len(errors_list) > 0:
                error_messages = [error.get('message', '') for error in errors_list if isinstance(error, dict)]
                error_message = ' '.join(error_messages).lower() if error_messages else ''
                
                # エラータイプの抽出
                error_types = []
                for err in errors_list:
                    if isinstance(err, dict) and 'type' in err:
                        err_type = err.get('type', '').upper()
                        if err_type:
                            error_types.append(err_type)
                            
                # エラータイプに基づく例外
                if 'FORBIDDEN' in error_types or 'permission denied' in error_message or 'forbidden' in error_message:
                    # 権限エラーは401/403に相当するエラー
                    raise GitHubAuthenticationError(f"GraphQL permission denied during {context}: {errors_list}")
                elif 'NOT_FOUND' in error_types or 'not found' in error_message:
                    # リソースが見つからないエラーは404に相当するエラー
                    raise GitHubResourceNotFoundError(f"GraphQL resource not found during {context}: {errors_list}")
                else:
                    # その他のエラー
                    raise GitHubClientError(f"GraphQL operation failed during {context}: {errors_list}")
                    
            # 正常なレスポンスを処理
            if response and hasattr(response, 'data') and response.data:
                add_item_response = response.data.get("addProjectV2ItemById")
                if add_item_response:
                    item = add_item_response.get("item")
                    if item and "id" in item:
                        item_id = item["id"]
                        logger.info(f"Added item '{c_id}' to project '{p_id}', new item ID: {item_id}")
                        return item_id
                        
            # 有効な項目IDが取得できない場合
            raise GitHubClientError(f"Failed to add item to project V2: Invalid response format or missing item ID during {context}")
        except Exception as e:
            # Wrap all exceptions, including GraphQLResponse, into appropriate GitHubClientError
            raise self._handle_api_error(e, context)
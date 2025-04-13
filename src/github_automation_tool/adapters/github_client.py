import logging
import json  # 422エラーのレスポンス解析用 (現在は未使用だが将来のために残す)
from githubkit import GitHub
# RequestFailed を使う
from githubkit.exception import RequestError, RequestTimeout, RequestFailed
from pydantic import SecretStr
from typing import Optional

# ドメイン例外をインポート
from github_automation_tool.domain.exceptions import (
    GitHubClientError, GitHubAuthenticationError, GitHubRateLimitError,
    GitHubResourceNotFoundError, GitHubValidationError
)

logger = logging.getLogger(__name__)


class GitHubAppClient:
    """
    githubkit v0.12.9 を使用して GitHub API と対話するクライアント。
    エラーハンドリングと基本的なリソース作成・検索機能を提供します。
    """

    def __init__(self, auth_token: SecretStr):
        """
        クライアントを初期化し、認証を行います。

        Args:
            auth_token: GitHub Personal Access Token (PAT).

        Raises:
            GitHubAuthenticationError: トークンが無効または空の場合。
            GitHubClientError: その他の初期化エラー。
        """
        if not auth_token or not auth_token.get_secret_value():
            # 初期化時に直接カスタム例外を送出
            raise GitHubAuthenticationError("GitHub PAT is missing or empty.")
        try:
            self.gh = GitHub(auth_token.get_secret_value())
            logger.info("GitHub client initialized successfully.")
            # 簡単な接続テスト（オプション）
            # self._perform_connection_test()
        except Exception as e:
            # 初期化時の予期せぬエラー
            logger.error(
                f"Failed to initialize GitHub client: {e}", exc_info=True)
            raise GitHubClientError(
                f"Failed to initialize GitHub client: {e}", original_exception=e) from e

    def _perform_connection_test(self):
        """初期化時に簡単なAPI呼び出しで接続を確認（オプション）"""
        try:
            # 認証されたユーザー情報を取得するAPIを試す
            self.gh.rest.users.get_authenticated()
            logger.debug("GitHub API connection test successful during init.")
        except RequestFailed as rf_err:
            # 認証エラーならここで検知できる
            logger.warning(f"GitHub API connection test failed: {rf_err}")
            response = getattr(rf_err, 'response', None)
            status_code = getattr(response, 'status_code', None)
            if status_code in (401, 403):
                raise GitHubAuthenticationError("Initial connection test failed (invalid PAT or insufficient scope?).",
                                                status_code=status_code, original_exception=rf_err) from rf_err
            # 他のエラーは無視するか、GitHubClientError を raise するか選択
        except Exception as e:
            logger.warning(
                f"Unexpected error during GitHub API connection test: {e}")
            pass  # 接続テスト失敗はクリティカルではないかもしれないのでログ警告に留める

    def _handle_request_failed(self, error: RequestFailed, context: str) -> GitHubClientError:
        """
        RequestFailed 例外を解析し、適切なカスタム例外にラップします。

        Args:
            error: 発生した RequestFailed 例外。
            context: エラーが発生した操作のコンテキスト（ログ用）。

        Returns:
            ラップされたカスタム例外インスタンス。
        """
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
        logger.warning(message)  # 失敗の詳細をログに残す

        if status_code == 401:  # Unauthorized
            logger.error(
                "GitHub API Authentication Error (401). Check your PAT.")
            return GitHubAuthenticationError("Authentication failed (401).", status_code=status_code, original_exception=error)
        elif status_code == 403:  # Forbidden
            remaining = headers.get("X-RateLimit-Remaining")
            if remaining == "0":
                logger.error("GitHub API rate limit exceeded (403).")
                return GitHubRateLimitError("GitHub API rate limit exceeded.", status_code=status_code, original_exception=error)
            else:
                logger.error(
                    "GitHub API Permission Error (403). Check PAT scopes or resource permissions.")
                return GitHubAuthenticationError("Permission denied (403).", status_code=status_code, original_exception=error)
        elif status_code == 404:  # Not Found
            logger.warning(
                f"GitHub resource not found during {context} (404).")
            return GitHubResourceNotFoundError("GitHub resource not found.", status_code=status_code, original_exception=error)
        elif status_code == 422:  # Unprocessable Entity
            logger.warning(
                f"GitHub validation failed during {context} (422): {error_content_str}")
            # ここでは汎用的なValidationErrorを返す。具体的な判定は呼び出し元で行う。
            return GitHubValidationError(f"Validation failed (422): {error_content_str}", status_code=status_code, original_exception=error)
        else:
            # その他の 4xx, 5xx エラー
            logger.error(
                f"Unhandled GitHub API HTTP error during {context} (Status: {status_code}).")
            return GitHubClientError(f"Unhandled GitHub API HTTP error (Status: {status_code}): {error}", status_code=status_code, original_exception=error)

    def _handle_other_error(self, error: Exception, context: str) -> GitHubClientError:
        """
        RequestFailed 以外の例外 (ネットワークエラー等) を処理します。

        Args:
            error: 発生した元の例外。
            context: エラーが発生した操作のコンテキスト。

        Returns:
            ラップされた GitHubClientError インスタンス。
        """
        if isinstance(error, (RequestError, RequestTimeout)):
            logger.warning(
                f"GitHub API request/network error during {context}: {error}")
            return GitHubClientError(f"Network/Request error during {context}: {error}", original_exception=error)
        else:
            # 予期しないその他の例外
            logger.error(
                f"Unexpected non-API error during {context}: {error}", exc_info=True)
            return GitHubClientError(f"Unexpected error during {context}: {error}", original_exception=error)

    def create_repository(self, repo_name: str) -> str:
        """
        新しい Private リポジトリを作成します。

        Args:
            repo_name: 作成するリポジトリの名前。

        Returns:
            作成されたリポジトリのHTML URL。

        Raises:
            GitHubValidationError: リポジトリが既に存在する場合、または他のバリデーションエラー。
            GitHubAuthenticationError: 認証エラーまたは権限不足。
            GitHubRateLimitError: APIレート制限超過。
            GitHubClientError: その他のAPIエラーまたは予期せぬエラー。
        """
        logger.info(f"Attempting to create private repository: {repo_name}")
        try:
            response = self.gh.rest.repos.create_for_authenticated_user(
                name=repo_name,
                private=True,
                auto_init=True  # READMEを含めて初期化
            )
            # 成功時のレスポンスデータを確認
            if response and response.parsed_data and hasattr(response.parsed_data, 'html_url'):
                repo_url = response.parsed_data.html_url
                logger.info(f"Successfully created repository: {repo_url}")
                return repo_url
            else:
                logger.error(
                    "Could not get repository URL from successful API response.")
                raise GitHubClientError(
                    "Could not retrieve repository URL after creation.")
        # RequestFailed を明示的に捕捉
        except RequestFailed as e:
            processed_error = self._handle_request_failed(
                e, f"creating repository '{repo_name}'")
            # ★ 422 エラーの場合、レスポンス内容を解析して判定するロジックに変更
            if isinstance(processed_error, GitHubValidationError) and processed_error.status_code == 422:
                original_exception = processed_error.original_exception
                response = getattr(original_exception, 'response', None)
                content_bytes = getattr(response, 'content', b'')
                try:
                    # レスポンスボディをJSONとしてデコード試行
                    error_details = json.loads(content_bytes.decode('utf-8'))
                    # GitHub APIの標準的なエラー形式を想定してチェック
                    error_message = error_details.get('message', '').lower()
                    error_in_errors_list = False
                    if 'errors' in error_details and isinstance(error_details['errors'], list):
                        error_in_errors_list = any("already exists" in err.get(
                            'message', '').lower() for err in error_details['errors'])

                    if "name already exists" in error_message or error_in_errors_list:
                        logger.warning(
                            f"Repository '{repo_name}' already exists (detected via response content).")
                        # より具体的なメッセージで再raise
                        raise GitHubValidationError(
                            f"Repository '{repo_name}' already exists.", status_code=422, original_exception=original_exception) from e
                except (json.JSONDecodeError, AttributeError, TypeError, KeyError):
                    # JSONパース失敗など、詳細不明の場合はそのまま進む (元のValidationErrorがraiseされる)
                    logger.warning(
                        "Could not parse 422 error details, raising generic validation error.")
                    pass
            # 処理された例外をraise
            raise processed_error from e
        # その他の例外 (ネットワークエラー等) を捕捉
        except Exception as e:
            raise self._handle_other_error(
                e, f"creating repository '{repo_name}'")

    def find_issue_by_title(self, owner: str, repo: str, title: str) -> bool:
        """
        指定されたタイトルの Open な Issue がリポジトリに存在するか確認します。

        Args:
            owner: リポジトリのオーナー名。
            repo: リポジトリ名。
            title: 検索するIssueの完全なタイトル。

        Returns:
            Issueが存在すれば True、存在しなければ False。

        Raises:
            GitHubAuthenticationError: 認証エラーまたは権限不足。
            GitHubRateLimitError: APIレート制限超過。
            GitHubClientError: その他のAPIエラーまたは予期せぬエラー。
        """
        logger.debug(
            f"Searching for open issue titled '{title}' in {owner}/{repo}")
        query = f'repo:{owner}/{repo} is:issue is:open in:title "{title}"'
        try:
            response = self.gh.rest.search.issues_and_pull_requests(
                q=query, per_page=1)
            # 検索結果の total_count を安全に確認
            if response and response.parsed_data and hasattr(response.parsed_data, 'total_count'):
                issue_exists = response.parsed_data.total_count > 0
                logger.debug(
                    f"Issue search result for '{title}': {'Found' if issue_exists else 'Not found'} ({response.parsed_data.total_count} total)")
                return issue_exists
            else:
                logger.warning(
                    "Could not determine issue existence from search API response.")
                raise GitHubClientError(
                    "Unexpected response from issue search API.")
        # RequestFailed を明示的に捕捉
        except RequestFailed as e:
            raise self._handle_request_failed(e, f"searching issue '{title}'")
        # その他の例外 (ネットワークエラー等) を捕捉
        except Exception as e:
            raise self._handle_other_error(e, f"searching issue '{title}'")

    def create_issue(self, owner: str, repo: str, title: str, body: Optional[str] = None) -> str:
        """
        指定されたリポジトリに新しい Issue を作成します。

        Args:
            owner: リポジトリのオーナー名。
            repo: リポジトリ名。
            title: 作成する Issue のタイトル。
            body: 作成する Issue の本文 (任意)。

        Returns:
            作成された Issue の HTML URL。

        Raises:
            GitHubResourceNotFoundError: リポジトリが見つからない場合 (404)。
            GitHubValidationError: Issue作成のバリデーションエラー (422)。
            GitHubAuthenticationError: 認証エラーまたは権限不足 (403)。
            GitHubRateLimitError: APIレート制限超過 (403 with header)。
            GitHubClientError: その他のAPIエラーまたは予期せぬエラー。
        """
        logger.info(f"Attempting to create issue '{title}' in {owner}/{repo}")
        try:
            response = self.gh.rest.issues.create(
                owner=owner, repo=repo, title=title, body=body or ""
            )
            if response and response.parsed_data and hasattr(response.parsed_data, 'html_url'):
                issue_url = response.parsed_data.html_url
                logger.info(f"Successfully created issue: {issue_url}")
                return issue_url
            else:
                logger.error(
                    "Failed to get issue URL from successful API response.")
                raise GitHubClientError(
                    "Could not retrieve issue URL after creation.")
        # RequestFailed を明示的に捕捉
        except RequestFailed as e:
            raise self._handle_request_failed(e, f"creating issue '{title}'")
        # その他の例外 (ネットワークエラー等) を捕捉
        except Exception as e:
            raise self._handle_other_error(e, f"creating issue '{title}'")

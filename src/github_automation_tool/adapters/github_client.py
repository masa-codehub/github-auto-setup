import logging
import json
from githubkit import GitHub
from githubkit.exception import RequestError, RequestTimeout, RequestFailed
# ★ モデルの推奨インポートパスに変更
from githubkit.versions.latest.models import Label, Issue  # Response は直接使わないので削除
from pydantic import SecretStr
# ★ typing からのインポートは不要 (list, dict, any, | None を使用)

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
            pass

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
        logger.warning(message)

        if status_code == 401:
            return GitHubAuthenticationError("Authentication failed (401).", status_code=status_code, original_exception=error)
        elif status_code == 403:
            remaining = headers.get("X-RateLimit-Remaining")
            if remaining == "0":
                return GitHubRateLimitError("GitHub API rate limit exceeded.", status_code=status_code, original_exception=error)
            else:
                return GitHubAuthenticationError("Permission denied (403).", status_code=status_code, original_exception=error)
        elif status_code == 404:
            return GitHubResourceNotFoundError("GitHub resource not found.", status_code=status_code, original_exception=error)
        elif status_code == 422:
            return GitHubValidationError(f"Validation failed (422): {error_content_str}", status_code=status_code, original_exception=error)
        else:
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

    def create_repository(self, repo_name: str) -> str:
        """新しい Private リポジトリを作成します。"""
        logger.info(f"Attempting to create private repository: {repo_name}")
        try:
            # APIからのレスポンス型は Response[Repository] (versions.latest.models から)
            # from githubkit.versions.latest.models import Repository
            # response: Response[Repository] = self.gh.rest.repos.create_for_authenticated_user(...)
            response = self.gh.rest.repos.create_for_authenticated_user(
                name=repo_name, private=True, auto_init=True
            )
            if response and response.parsed_data and hasattr(response.parsed_data, 'html_url'):
                repo_url = response.parsed_data.html_url
                logger.info(f"Successfully created repository: {repo_url}")
                return repo_url
            else:
                logger.error(
                    "Could not get repository URL from successful API response.")
                raise GitHubClientError(
                    "Could not retrieve repository URL after creation.")
        except RequestFailed as e:
            processed_error = self._handle_request_failed(
                e, f"creating repository '{repo_name}'")
            if isinstance(processed_error, GitHubValidationError) and processed_error.status_code == 422:
                if "name already exists" in str(e).lower():
                    logger.warning(
                        f"Repository '{repo_name}' already exists (detected via string).")
                    raise GitHubValidationError(
                        f"Repository '{repo_name}' already exists.", status_code=422, original_exception=e) from e
            raise processed_error from e
        except Exception as e:
            raise self._handle_other_error(
                e, f"creating repository '{repo_name}'")

    # ★ get_label の戻り値型ヒントを修正 (Label | None)
    def get_label(self, owner: str, repo: str, label_name: str) -> Label | None:
        """指定されたラベルが存在するか確認し、存在すればその情報をLabelオブジェクトとして返します。"""
        logger.debug(
            f"Checking if label '{label_name}' exists in {owner}/{repo}")
        try:
            # response: Response[Label]
            response = self.gh.rest.issues.get_label(
                owner=owner, repo=repo, name=label_name)
            if response and response.parsed_data:
                logger.debug(f"Label '{label_name}' found.")
                return response.parsed_data
            else:
                logger.warning(
                    f"get_label returned success status but no data for '{label_name}'.")
                return None
        except RequestFailed as e:
            response = getattr(e, 'response', None)
            status_code = getattr(response, 'status_code', None)
            if status_code == 404:
                logger.debug(f"Label '{label_name}' not found (404).")
                return None
            else:
                raise self._handle_request_failed(
                    e, f"getting label '{label_name}'")
        except Exception as e:
            raise self._handle_other_error(e, f"getting label '{label_name}'")

    # ★ create_label の引数と戻り値型ヒントを修正
    def create_label(self, owner: str, repo: str, label_name: str,
                     color: str | None = None, description: str | None = "") -> bool:
        """リポジトリに新しいラベルを作成します。同名のラベルが既に存在する場合は何もしません。"""
        if not label_name:
            logger.warning("Skipping label creation due to empty name.")
            return False
        context = f"ensuring label '{label_name}' in {owner}/{repo}"
        logger.info(context + "...")
        try:
            existing_label = self.get_label(owner, repo, label_name)
            if existing_label is not None:
                logger.info(
                    f"Label '{label_name}' already exists. Skipping creation.")
                return False  # 存在したので False

            logger.info(f"Label '{label_name}' not found. Creating...")
            # ★ dict, any に変更
            payload: dict[str, any] = {"name": label_name}
            if color:
                payload["color"] = color.lstrip('#')
            if description:
                payload["description"] = description

            # response: Response[Label]
            response = self.gh.rest.issues.create_label(
                owner=owner, repo=repo, **payload)

            if response and response.status_code == 201:
                logger.info(f"Successfully created label '{label_name}'.")
                return True  # 新規作成された
            else:
                logger.error(
                    f"Label creation API call returned unexpected status: {getattr(response, 'status_code', 'N/A')}")
                raise GitHubClientError(
                    f"Unexpected status during label creation for '{label_name}'.")
        except RequestFailed as e:
            raise self._handle_request_failed(
                e, f"creating label '{label_name}'")
        except Exception as e:
            raise self._handle_other_error(e, context)

    # ★ create_issue の引数型ヒントを修正
    def create_issue(self, owner: str, repo: str, title: str,
                     body: str | None = None,
                     labels: list[str] | None = None,
                     milestone: int | str | None = None,
                     assignees: list[str] | None = None
                     ) -> str:
        """指定されたリポジトリに新しい Issue を作成し、関連情報を設定します。"""
        logger.info(
            f"Attempting to create issue '{title}' in {owner}/{repo}' with labels: {labels}, milestone: {milestone}, assignees: {assignees}")
        try:
            # ★ dict, any に変更
            payload: dict[str, any] = {
                "owner": owner, "repo": repo, "title": title, "body": body or ""
            }
            if labels:
                payload["labels"] = labels
            if milestone is not None:
                if isinstance(milestone, int):
                    payload["milestone"] = milestone
                else:
                    logger.warning(
                        f"Milestone '{milestone}' ignored (must be integer ID).")
            if assignees:
                payload["assignees"] = assignees

            # response: Response[Issue]
            response = self.gh.rest.issues.create(**payload)

            if response and response.parsed_data and hasattr(response.parsed_data, 'html_url'):
                issue_url = response.parsed_data.html_url
                logger.info(
                    f"Successfully created issue '{title}': {issue_url}")
                return issue_url
            else:
                logger.error(
                    "Failed to get issue URL from successful API response.")
                raise GitHubClientError(
                    "Could not retrieve issue URL after creation.")
        except Exception as e:
            raise self._handle_api_error(
                e, f"creating issue '{title}'")  # エラーハンドラを共通化

    def find_issue_by_title(self, owner: str, repo: str, title: str) -> bool:
        """指定されたタイトルの Open な Issue がリポジトリに存在するか確認します。"""
        logger.debug(
            f"Searching for open issue titled '{title}' in {owner}/{repo}")
        query = f'repo:{owner}/{repo} is:issue is:open in:title "{title}"'
        try:
            # response: Response[SearchIssuesAndPullRequestsGetResponse200]
            response = self.gh.rest.search.issues_and_pull_requests(
                q=query, per_page=1)
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
        except RequestFailed as e:
            raise self._handle_request_failed(e, f"searching issue '{title}'")
        except Exception as e:
            raise self._handle_other_error(e, f"searching issue '{title}'")

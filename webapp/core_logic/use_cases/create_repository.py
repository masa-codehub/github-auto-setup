import logging
from adapters.github_rest_client import GitHubRestClient
from domain.exceptions import (
    GitHubClientError, GitHubValidationError, GitHubAuthenticationError
)

logger = logging.getLogger(__name__)


class CreateRepositoryUseCase:
    """
    指定された情報に基づいて新しいGitHubリポジトリを作成するユースケース。
    """

    # 型ヒントを GitHubRestClient に変更
    def __init__(self, github_client: GitHubRestClient):
        """
        UseCaseを初期化します。

        Args:
            github_client: GitHub APIと対話するためのクライアントインスタンス。
                           依存性注入により外部から渡されます。
        """
        # 型チェックも GitHubRestClient に変更
        if not isinstance(github_client, GitHubRestClient):
            # このエラーは通常、開発中の設定ミスで発生する
            raise TypeError(
                "github_client must be an instance of GitHubRestClient")  # エラーメッセージも修正
        self.github_client = github_client

    def execute(self, repo_name: str) -> str:
        """
        ユースケースを実行し、リポジトリを作成します。

        Args:
            repo_name: 作成するリポジトリの名前 (例: "my-new-awesome-repo")。

        Returns:
            作成されたリポジトリのHTML URL。

        Raises:
            ValueError: リポジトリ名が無効な場合。
            GitHubValidationError: リポジトリが既に存在する場合など。
            GitHubAuthenticationError: GitHubの認証/権限に問題がある場合。
            GitHubClientError: その他のGitHub API関連エラー。
        """
        # --- 1. 入力値のバリデーション (オプションだが推奨) ---
        # ユーザーリポジトリ名にスラッシュは通常含まれない
        if not repo_name or '/' in repo_name:
            logger.error(f"Invalid repository name provided: '{repo_name}'")
            raise ValueError(
                f"Invalid repository name: '{repo_name}'. Name cannot be empty or contain '/'.")

        logger.info(
            f"Executing CreateRepositoryUseCase for repository: '{repo_name}'")

        # --- 2. 依存コンポーネント (Adapter) のメソッド呼び出し ---
        try:
            # GitHubRestClient の create_repository を呼び出す
            repo_data = self.github_client.create_repository(repo_name)
            # URL を返すように修正
            if not repo_data or not repo_data.html_url:
                raise GitHubClientError(
                    f"Repository '{repo_name}' created but URL is missing in response.")
            logger.info(
                f"Repository successfully created by client: {repo_data.html_url}")
            # --- 3. 結果を返す ---
            return repo_data.html_url  # URL を返す
        except (GitHubValidationError, GitHubAuthenticationError, GitHubClientError) as e:
            # GitHubクライアントから送出されたカスタム例外はログに記録し、そのまま再送出
            # 必要なら exc_info=True
            logger.error(
                f"GitHub client error during repository creation for '{repo_name}': {e}", exc_info=False)
            raise  # 上位の呼び出し元 (例: main.py) で最終的なハンドリングを行う
        except Exception as e:
            # 予期しないその他のエラーが発生した場合
            logger.exception(
                # トレースバックも記録
                f"Unexpected error during repository creation for '{repo_name}': {e}")
            # より汎用的なエラーでラップして再送出
            raise GitHubClientError(
                f"An unexpected error occurred during repository creation: {e}", original_exception=e) from e

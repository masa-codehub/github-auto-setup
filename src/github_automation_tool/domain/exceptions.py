class GitHubClientError(Exception):
    """GitHubクライアント操作中の汎用エラー"""

    def __init__(self, message: str, status_code: int | None = None, original_exception: Exception | None = None):
        self.message = message
        self.status_code = status_code
        self.original_exception = original_exception
        super().__init__(message)


class GitHubAuthenticationError(GitHubClientError):
    """認証失敗または権限不足エラー"""
    pass


class GitHubRateLimitError(GitHubClientError):
    """APIレート制限超過エラー"""
    pass


class GitHubResourceNotFoundError(GitHubClientError):
    """リソースが見つからないエラー (404)"""
    pass


class GitHubValidationError(GitHubClientError):
    """入力値が無効、またはリソース重複エラー (422)"""
    pass

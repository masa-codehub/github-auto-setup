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

# --- ★ AI Parser 関連の例外クラス ★ ---


class AiParserError(Exception):
    """
    AI パーサー (LangChain連携含む) の処理中に発生したエラーの基底クラス。
    """

    def __init__(self, message: str, original_exception: Exception | None = None):
        """
        AiParserError を初期化します。

        Args:
            message: エラーの内容を示すメッセージ。
            original_exception: 補足した元の例外 (オプション)。デバッグ情報として保持します。
        """
        self.message = message
        self.original_exception = original_exception
        # 元の例外があれば、例外チェーン (__cause__) に設定します。
        # これにより、トレースバックで元のエラー箇所も追いやすくなります。
        if original_exception:
            self.__cause__ = original_exception
        super().__init__(message)

# --- (オプション) より具体的なAI関連エラーが必要な場合 ---
# 必要であれば、AiParserError を継承して、
# より具体的なエラー状況を示すサブクラスを定義することもできます。
# 例:
# class AiApiCallError(AiParserError):
#     """AI API呼び出し自体 (認証、レート制限、タイムアウト等) が失敗した場合のエラー"""
#     pass
#
# class AiOutputParsingError(AiParserError):
#     """AIモデルの出力内容を期待した形式 (JSONやPydanticモデル) にパースできなかった場合のエラー"""
#     pass
#
# class PromptTemplateError(AiParserError):
#      """プロンプトテンプレートの生成やバリデーションでエラーが発生した場合"""
#      pass

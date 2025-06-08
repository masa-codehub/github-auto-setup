"""GitHub API エラーハンドリングユーティリティのテスト"""

import unittest
import logging
from typing import Optional, Dict, Any, List
from unittest.mock import patch, MagicMock

# テスト対象のモジュールをインポート
from core_logic.adapters.github_utils import github_api_error_handler, _process_graphql_errors
from core_logic.domain.exceptions import (
    GitHubClientError, GitHubResourceNotFoundError, GitHubAuthenticationError, GitHubRateLimitError, GitHubValidationError
)

# githubkit の例外クラスをインポート
from githubkit.exception import RequestFailed, RequestError, RequestTimeout

# GraphQLResponseのインポート
try:
    from githubkit.response import GraphQLResponse
except ImportError:
    try:
        from githubkit.graphql import GraphQLResponse
    except ImportError:
        GraphQLResponse = None


class TestGithubApiErrorHandler(unittest.TestCase):
    """GitHub API エラーハンドリングデコレータのテスト"""

    def setUp(self):
        # ロギングを抑制
        logging.disable(logging.CRITICAL)

        # モックレスポンス作成のヘルパー
        self.graphql_setup_done = False

    def tearDown(self):
        # ロギング設定を元に戻す
        logging.disable(logging.NOTSET)

    def create_mock_response(
        self,
        status_code: int = 200,
        content: bytes = b'{}',
        headers: Optional[Dict[str, str]] = None
    ) -> MagicMock:
        """
        RequestFailedエラー用のモックレスポンスを作成するヘルパーメソッド

        Args:
            status_code: HTTPステータスコード
            content: レスポンス本文バイト列
            headers: レスポンスヘッダー辞書

        Returns:
            設定済みのMockレスポンスオブジェクト
        """
        mock_response = MagicMock()
        mock_response.status_code = status_code
        mock_response.content = content
        mock_response.headers = headers or {}
        return mock_response

    def create_request_failed(
        self,
        status_code: int = 500,
        content: bytes = b'{"message": "Server Error"}',
        headers: Optional[Dict[str, str]] = None
    ) -> RequestFailed:
        """
        RequestFailed例外を作成するヘルパーメソッド

        Args:
            status_code: HTTPステータスコード
            content: エラーレスポンスの本文
            headers: レスポンスヘッダー

        Returns:
            設定済みのRequestFailed例外オブジェクト
        """
        mock_response = self.create_mock_response(
            status_code, content, headers)
        return RequestFailed(response=mock_response)

    def create_graphql_error_dict(
        self,
        error_type: str = "",
        message: str = "GraphQL Error",
        path: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        GraphQLエラー構造を持つ辞書を作成するヘルパーメソッド

        Args:
            error_type: エラータイプ ("NOT_FOUND", "FORBIDDEN" など)
            message: エラーメッセージ
            path: GraphQLクエリのパス

        Returns:
            GraphQLエラー構造を持つ辞書
        """
        error_dict = {
            "errors": [
                {
                    "message": message
                }
            ]
        }

        # typeフィールドがある場合のみ追加
        if error_type:
            error_dict["errors"][0]["type"] = error_type

        # pathフィールドがある場合のみ追加
        if path:
            error_dict["errors"][0]["path"] = path

        return error_dict

    def test_successful_api_call(self):
        """正常なAPI呼び出しが成功することを確認"""
        # コンテキスト関数を定義

        def context_func(self, test_arg, *args, **kwargs):
            return f"test context with {test_arg}"

        # デコレータを適用したテスト関数
        @github_api_error_handler(context_func)
        def test_function(self, test_arg):
            return f"success: {test_arg}"

        # テスト実行
        result = test_function(self, "test_value")
        self.assertEqual(result, "success: test_value")

    def test_already_wrapped_error(self):
        """既にカスタム例外でラップされたエラーがそのまま再送出されることを確認"""
        # コンテキスト関数

        def context_func(self, *args, **kwargs):
            return "test context"

        # デコレータを適用したテスト関数
        @github_api_error_handler(context_func)
        def test_function(self):
            # GitHubClientErrorを継承したカスタム例外を送出
            raise GitHubAuthenticationError("Already wrapped error")

        # テスト実行
        with self.assertRaises(GitHubAuthenticationError) as context:
            test_function(self)

        self.assertEqual(str(context.exception), "Already wrapped error")

    def test_request_failed_401(self):
        """RequestFailed 401エラーがGitHubAuthenticationErrorに変換されることを確認"""
        # RequestFailed例外を作成
        request_failed_error = self.create_request_failed(
            status_code=401,
            content=b'{"message": "Bad credentials"}',
            headers={}
        )

        # コンテキスト関数
        def context_func(self, *args, **kwargs):
            return "authentication test context"

        # デコレータを適用したテスト関数
        @github_api_error_handler(context_func)
        def test_function(self):
            raise request_failed_error

        # テスト実行
        with self.assertRaises(GitHubAuthenticationError) as context:
            test_function(self)

        # エラーメッセージと例外の検証
        self.assertIn("authentication test context", str(context.exception))
        self.assertEqual(context.exception.status_code, 401)
        self.assertEqual(context.exception.original_exception,
                         request_failed_error)

    def test_request_failed_403_rate_limit(self):
        """レート制限の403エラーがGitHubRateLimitErrorに変換されることを確認"""
        # RequestFailed例外を作成
        request_failed_error = self.create_request_failed(
            status_code=403,
            content=b'{"message": "API rate limit exceeded"}',
            headers={"X-RateLimit-Remaining": "0"}
        )

        # コンテキスト関数
        def context_func(self, *args, **kwargs):
            return "rate limit test context"

        # デコレータを適用したテスト関数
        @github_api_error_handler(context_func)
        def test_function(self):
            raise request_failed_error

        # テスト実行
        with self.assertRaises(GitHubRateLimitError) as context:
            test_function(self)

        # エラーメッセージと例外の検証
        self.assertIn("rate limit test context", str(context.exception))
        self.assertEqual(context.exception.status_code, 403)
        self.assertEqual(context.exception.original_exception,
                         request_failed_error)

    def test_request_failed_403_permission_denied(self):
        """権限不足の403エラーがGitHubAuthenticationErrorに変換されることを確認"""
        # RequestFailed例外を作成
        request_failed_error = self.create_request_failed(
            status_code=403,
            content=b'{"message": "Resource not accessible"}',
            headers={"X-RateLimit-Remaining": "5000"}  # レート制限ではない
        )

        # コンテキスト関数
        def context_func(self, *args, **kwargs):
            return "permission denied test context"

        # デコレータを適用したテスト関数
        @github_api_error_handler(context_func)
        def test_function(self):
            raise request_failed_error

        # テスト実行
        with self.assertRaises(GitHubAuthenticationError) as context:
            test_function(self)

        # エラーメッセージと例外の検証
        self.assertIn("permission denied test context", str(context.exception))
        self.assertEqual(context.exception.status_code, 403)
        self.assertEqual(context.exception.original_exception,
                         request_failed_error)

    def test_request_failed_404(self):
        """404エラーがGitHubResourceNotFoundErrorに変換されることを確認"""
        # RequestFailed例外を作成
        request_failed_error = self.create_request_failed(
            status_code=404,
            content=b'{"message": "Not Found"}',
            headers={}
        )

        # コンテキスト関数
        def context_func(self, *args, **kwargs):
            return "not found test context"

        # デコレータを適用したテスト関数
        @github_api_error_handler(context_func)
        def test_function(self):
            raise request_failed_error

        # テスト実行
        with self.assertRaises(GitHubResourceNotFoundError) as context:
            test_function(self)

        # エラーメッセージと例外の検証
        self.assertIn("not found test context", str(context.exception))
        self.assertEqual(context.exception.status_code, 404)
        self.assertEqual(context.exception.original_exception,
                         request_failed_error)

    def test_request_failed_404_ignore_not_found(self):
        """ignore_not_found=Trueの場合、404エラーがNoneを返すことを確認"""
        # RequestFailed例外を作成
        request_failed_error = self.create_request_failed(
            status_code=404,
            content=b'{"message": "Not Found"}',
            headers={}
        )

        # コンテキスト関数
        def context_func(self, *args, **kwargs):
            return "ignore 404 test context"

        # デコレータを適用したテスト関数 (ignore_not_found=True)
        @github_api_error_handler(context_func, ignore_not_found=True)
        def test_function(self):
            raise request_failed_error

        # テスト実行 - エラーではなくNoneが返されることを確認
        result = test_function(self)
        self.assertIsNone(result)

    def test_request_failed_422_repository_exists(self):
        """リポジトリ重複の422エラーがGitHubValidationErrorに変換されることを確認"""
        # RequestFailed例外を作成
        request_failed_error = self.create_request_failed(
            status_code=422,
            content=b'{"message": "Repository name already exists"}',
            headers={}
        )

        # コンテキスト関数 (リポジトリコンテキストを含む)
        def context_func(self, *args, **kwargs):
            return "creating repository 'test-repo'"

        # デコレータを適用したテスト関数
        @github_api_error_handler(context_func)
        def test_function(self):
            raise request_failed_error

        # テスト実行
        with self.assertRaises(GitHubValidationError) as context:
            test_function(self)

        # エラーメッセージと例外の検証
        self.assertIn("Repository name already exists", str(context.exception))
        self.assertEqual(context.exception.status_code, 422)
        self.assertEqual(context.exception.original_exception,
                         request_failed_error)

    def test_request_failed_422_other_validation(self):
        """その他の422エラーがGitHubValidationErrorに変換されることを確認"""
        # RequestFailed例外を作成
        request_failed_error = self.create_request_failed(
            status_code=422,
            content=b'{"message": "Validation failed"}',
            headers={}
        )

        # コンテキスト関数
        def context_func(self, *args, **kwargs):
            return "validation test context"

        # デコレータを適用したテスト関数
        @github_api_error_handler(context_func)
        def test_function(self):
            raise request_failed_error

        # テスト実行
        with self.assertRaises(GitHubValidationError) as context:
            test_function(self)

        # エラーメッセージと例外の検証
        self.assertIn("validation test context", str(context.exception))
        self.assertEqual(context.exception.status_code, 422)
        self.assertEqual(context.exception.original_exception,
                         request_failed_error)

    def test_request_failed_500(self):
        """500エラーがGitHubClientErrorに変換されることを確認"""
        # RequestFailed例外を作成
        request_failed_error = self.create_request_failed(
            status_code=500,
            content=b'{"message": "Internal Server Error"}',
            headers={}
        )

        # コンテキスト関数
        def context_func(self, *args, **kwargs):
            return "server error test context"

        # デコレータを適用したテスト関数
        @github_api_error_handler(context_func)
        def test_function(self):
            raise request_failed_error

        # テスト実行
        with self.assertRaises(GitHubClientError) as context:
            test_function(self)

        # エラーメッセージと例外の検証
        self.assertIn("server error test context", str(context.exception))
        self.assertEqual(context.exception.status_code, 500)
        self.assertEqual(context.exception.original_exception,
                         request_failed_error)

    def test_request_error(self):
        """RequestErrorがGitHubClientErrorに変換されることを確認"""
        # RequestError例外を作成
        request_error = RequestError("Connection failed")

        # コンテキスト関数
        def context_func(self, *args, **kwargs):
            return "network error test context"

        # デコレータを適用したテスト関数
        @github_api_error_handler(context_func)
        def test_function(self):
            raise request_error

        # テスト実行
        with self.assertRaises(GitHubClientError) as context:
            test_function(self)

        # エラーメッセージと例外の検証
        self.assertIn("network error test context", str(context.exception))
        self.assertEqual(context.exception.original_exception, request_error)

    def test_request_timeout(self):
        """RequestTimeoutがGitHubClientErrorに変換されることを確認"""
        # RequestTimeout例外を作成
        request_timeout = RequestTimeout("Request timed out")

        # コンテキスト関数
        def context_func(self, *args, **kwargs):
            return "timeout test context"

        # デコレータを適用したテスト関数
        @github_api_error_handler(context_func)
        def test_function(self):
            raise request_timeout

        # テスト実行
        with self.assertRaises(GitHubClientError) as context:
            test_function(self)

        # エラーメッセージと例外の検証
        self.assertIn("timeout test context", str(context.exception))
        self.assertEqual(context.exception.original_exception, request_timeout)

    def test_graphql_error_not_found(self):
        """GraphQLエラー (Not Found) がGitHubResourceNotFoundErrorに変換されることを確認"""
        # GraphQLエラーを作成
        graphql_error = self.create_graphql_error_dict(
            error_type="NOT_FOUND",
            message="Resource could not be found"
        )

        # コンテキスト関数
        def context_func(self, *args, **kwargs):
            return "graphql not found test context"

        # デコレータを適用したテスト関数
        @github_api_error_handler(context_func)
        def test_function(self):
            # Exception内に辞書を含めることで、GraphQLエラーと同様の処理がされるようにする
            raise Exception(graphql_error)

        # テスト実行
        with self.assertRaises(GitHubResourceNotFoundError) as context:
            test_function(self)

        # エラーメッセージを検証
        self.assertIn("graphql not found test context", str(context.exception))

    def test_graphql_error_not_found_ignore_not_found(self):
        """ignore_not_found=TrueのGraphQLエラー (Not Found) がNoneを返すことを確認"""
        # GraphQLエラーを作成
        graphql_error = self.create_graphql_error_dict(
            error_type="NOT_FOUND",
            message="Resource could not be found"
        )

        # コンテキスト関数
        def context_func(self, *args, **kwargs):
            return "graphql ignore not found test context"

        # デコレータを適用したテスト関数
        @github_api_error_handler(context_func, ignore_not_found=True)
        def test_function(self):
            raise Exception(graphql_error)

        # テスト実行 - エラーではなくNoneが返されることを確認
        result = test_function(self)
        self.assertIsNone(result)

    def test_graphql_error_forbidden(self):
        """GraphQLエラー (Forbidden) がGitHubAuthenticationErrorに変換されることを確認"""
        # GraphQLエラーを作成
        graphql_error = self.create_graphql_error_dict(
            error_type="FORBIDDEN",
            message="Permission denied"
        )

        # コンテキスト関数
        def context_func(self, *args, **kwargs):
            return "graphql forbidden test context"

        # デコレータを適用したテスト関数
        @github_api_error_handler(context_func)
        def test_function(self):
            raise Exception(graphql_error)

        # テスト実行
        with self.assertRaises(GitHubAuthenticationError) as context:
            test_function(self)

        # エラーメッセージを検証
        self.assertIn("graphql forbidden test context", str(context.exception))

    def test_graphql_error_permission_message(self):
        """GraphQLエラー (メッセージに 'permission denied' を含む) がGitHubAuthenticationErrorに変換されることを確認"""
        # GraphQLエラーを作成 (typeなしでメッセージのみ)
        graphql_error = self.create_graphql_error_dict(
            message="You don't have permission to access this resource"
        )

        # コンテキスト関数
        def context_func(self, *args, **kwargs):
            return "graphql permission message test context"

        # デコレータを適用したテスト関数
        @github_api_error_handler(context_func)
        def test_function(self):
            raise Exception(graphql_error)

        # テスト実行
        with self.assertRaises(GitHubAuthenticationError) as context:
            test_function(self)

        # エラーメッセージを検証
        self.assertIn("graphql permission message test context",
                      str(context.exception))

    def test_unexpected_error(self):
        """予期しない例外がGitHubClientErrorに変換されることを確認"""
        # 予期しない例外
        unexpected_error = ValueError("Something went wrong")

        # コンテキスト関数
        def context_func(self, *args, **kwargs):
            return "unexpected error test context"

        # デコレータを適用したテスト関数
        @github_api_error_handler(context_func)
        def test_function(self):
            raise unexpected_error

        # テスト実行
        with self.assertRaises(GitHubClientError) as context:
            test_function(self)

        # エラーメッセージと例外の検証
        self.assertIn("unexpected error test context", str(context.exception))
        self.assertEqual(context.exception.original_exception,
                         unexpected_error)

    def test_no_context_function(self):
        """コンテキスト関数が渡されない場合もデフォルトコンテキストが使用されることを確認"""
        # コンテキスト関数なしでデコレータを適用
        @github_api_error_handler()  # 引数なし
        def test_function(self):
            raise ValueError("Test error")

        # テスト実行
        with self.assertRaises(GitHubClientError) as context:
            test_function(self)

        # デフォルトコンテキスト (関数名) が使用されていることを確認
        self.assertIn("test_function operation", str(context.exception))

    def test_context_func_none(self):
        """context_funcがNoneでも動作することを確認"""
        # Noneを明示的に指定
        @github_api_error_handler(None)
        def test_function(self):
            raise ValueError("Test error with None context")

        # テスト実行
        with self.assertRaises(GitHubClientError) as context:
            test_function(self)

        # デフォルトコンテキスト (関数名) が使用されていることを確認
        self.assertIn("test_function operation", str(context.exception))

    # --- 新しく追加されたGraphQLエラー処理のテスト ---
    def test_graphql_error_in_response_not_found(self):
        """レスポンス内にGraphQLエラー(Not Found)が含まれる場合、エラーになることを確認"""
        graphql_error = self.create_graphql_error_dict(
            error_type="NOT_FOUND", message="Resource not found")

        def context_func(self, *args, **kwargs):
            return "graphql response not found test"

        @github_api_error_handler(context_func, ignore_not_found=False)
        def test_function(self):
            # 正常レスポンスだが errors を含むデータを返す
            return graphql_error

        with self.assertRaises(GitHubResourceNotFoundError) as cm:
            test_function(self)
        self.assertIn("graphql response not found test", str(cm.exception))
        self.assertTrue(getattr(cm.exception, 'is_graphql_not_found',
                        False), "is_graphql_not_found flag should be set")

    def test_graphql_error_in_response_not_found_ignored(self):
        """レスポンス内のGraphQLエラー(Not Found)が ignore_not_found=True で無視されることを確認"""
        graphql_error = self.create_graphql_error_dict(
            error_type="NOT_FOUND", message="Resource not found")

        def context_func(self, *args, **kwargs):
            return "graphql response ignore not found test"

        @github_api_error_handler(context_func, ignore_not_found=True)
        def test_function(self):
            return graphql_error

        # 例外が発生せず、Noneが返ることを確認
        result = test_function(self)
        self.assertIsNone(result)

    def test_graphql_error_in_response_forbidden(self):
        """レスポンス内にGraphQLエラー(Forbidden)が含まれる場合、エラーになることを確認"""
        graphql_error = self.create_graphql_error_dict(
            error_type="FORBIDDEN", message="Permission denied")

        def context_func(self, *args, **kwargs):
            return "graphql response forbidden test"

        @github_api_error_handler(context_func)
        def test_function(self):
            return graphql_error

        with self.assertRaises(GitHubAuthenticationError) as cm:
            test_function(self)
        self.assertIn("graphql response forbidden test", str(cm.exception))

    def test_graphql_error_in_response_generic(self):
        """レスポンス内にその他のGraphQLエラーが含まれる場合、エラーになることを確認"""
        graphql_error = self.create_graphql_error_dict(
            error_type="INTERNAL_ERROR", message="Something went wrong")

        def context_func(self, *args, **kwargs):
            return "graphql response generic test"

        @github_api_error_handler(context_func)
        def test_function(self):
            return graphql_error

        with self.assertRaises(GitHubClientError) as cm:
            test_function(self)
        self.assertNotIsInstance(
            cm.exception, (GitHubAuthenticationError, GitHubResourceNotFoundError))
        self.assertIn("graphql response generic test", str(cm.exception))

    def test_process_graphql_errors_not_found(self):
        """_process_graphql_errors が NOT_FOUND エラーを正しく処理することを確認"""
        errors = [{"type": "NOT_FOUND", "message": "Resource not found"}]

        with self.assertRaises(GitHubResourceNotFoundError) as cm:
            _process_graphql_errors(errors, "test context", False)

        self.assertIn("test context", str(cm.exception))
        self.assertTrue(hasattr(cm.exception, 'is_graphql_not_found'),
                        "is_graphql_not_found flag should exist")

    def test_process_graphql_errors_forbidden(self):
        """_process_graphql_errors が FORBIDDEN エラーを正しく処理することを確認"""
        errors = [{"type": "FORBIDDEN", "message": "Permission denied"}]

        with self.assertRaises(GitHubAuthenticationError) as cm:
            _process_graphql_errors(errors, "test context", False)

        self.assertIn("test context", str(cm.exception))

    def test_response_with_attributes(self):
        """errorsプロパティを持つオブジェクトが正しく処理されることを確認"""
        # errorsプロパティを持つモックオブジェクト
        mock_response = MagicMock()
        mock_response.errors = [
            {"type": "NOT_FOUND", "message": "Resource not found"}]

        def context_func(self, *args, **kwargs):
            return "response with attributes test"

        @github_api_error_handler(context_func)
        def test_function(self):
            return mock_response

        with self.assertRaises(GitHubResourceNotFoundError):
            test_function(self)

    def test_graphql_response_object_with_errors(self):
        """GraphQLResponseオブジェクトのエラーが検出されることを確認"""
        # GraphQLResponseクラスが利用可能な場合のみテスト
        if GraphQLResponse is None:
            self.skipTest(
                "GraphQLResponse is not available in this environment")

        # GraphQLResponseに似た構造を持つモックオブジェクト
        class MockGraphQLResponse:
            def __init__(self, errors):
                self.errors = errors

        mock_response = MockGraphQLResponse(
            [{"type": "FORBIDDEN", "message": "Permission denied"}])

        def context_func(self, *args, **kwargs):
            return "graphql response object test"

        @github_api_error_handler(context_func)
        def test_function(self):
            return mock_response

        with self.assertRaises(GitHubAuthenticationError):
            test_function(self)


if __name__ == '__main__':
    unittest.main()

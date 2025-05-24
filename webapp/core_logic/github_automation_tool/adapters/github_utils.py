# src/github_automation_tool/adapters/github_utils.py
# GitHub API 呼び出しのエラーハンドリングユーティリティ

import functools
import logging
from typing import Optional, Callable, TypeVar, Any, cast, List, Dict
from githubkit import GitHub
from githubkit.exception import RequestFailed, RequestError, RequestTimeout

# GraphQLResponseのインポート
# githubkitのバージョンによって適切な方法でGraphQLエラー関連の型をインポート
try:
    # githubkit v1.0.0+
    from githubkit.response import GraphQLResponse
    HAS_NEW_GRAPHQL_RESPONSE = True
except ImportError:
    try:
        # githubkit v0.12.x
        from githubkit.graphql import GraphQLResponse
        HAS_NEW_GRAPHQL_RESPONSE = False
    except ImportError:
        # どちらのインポートも失敗した場合、Noneを設定
        GraphQLResponse = None
        HAS_NEW_GRAPHQL_RESPONSE = False

# ドメイン例外をインポート
from github_automation_tool.domain.exceptions import (
    GitHubClientError, GitHubAuthenticationError, GitHubRateLimitError,
    GitHubResourceNotFoundError, GitHubValidationError
)

logger = logging.getLogger(__name__)

# 型変数の定義（デコレータの型ヒントを改善するため）
T = TypeVar('T')
R = TypeVar('R')

# --- GraphQLエラー処理用のヘルパー関数 ---
def _process_graphql_errors(errors: List[Dict[str, Any]], context: str, ignore_not_found: bool) -> None:
    """
    GraphQLエラーリストを処理し、適切なドメイン例外を送出するか、
    ignore_not_found=True かつ NOT_FOUND エラーの場合は None を返す準備をする。
    
    Args:
        errors: GraphQLレスポンスに含まれるエラーリスト
        context: 操作コンテキスト（エラーメッセージ生成用）
        ignore_not_found: NOT_FOUNDエラーを無視するフラグ
    """
    error_types = []
    error_messages = []
    is_not_found_error = False
    is_forbidden_error = False

    for err in errors:
        if isinstance(err, dict):
            err_type = err.get("type", "").upper()
            err_msg = err.get("message", "").lower()
            if err_type: 
                error_types.append(err_type)
            if err_msg: 
                error_messages.append(err_msg)

            # エラータイプとメッセージに基づき、主要なエラー種別を判定
            if err_type == 'NOT_FOUND' or 'not found' in err_msg:
                is_not_found_error = True
            if err_type == 'FORBIDDEN' or any(keyword in err_msg for keyword in 
                                            ['permission denied', 'permission', 'forbidden', 
                                             'access denied', 'unauthorized']):
                is_forbidden_error = True
        else:
            # 予期しないエラー形式
            error_messages.append(str(err))

    logger.warning(f"GraphQL errors detected during {context}: {errors}")

    # 例外の送出 (優先度: Forbidden > Not Found > Generic)
    if is_forbidden_error:
        raise GitHubAuthenticationError(f"GraphQL permission denied during {context}: {errors}")
    elif is_not_found_error:
        # NotFoundエラーの場合は常にis_graphql_not_found=Trueを設定
        if ignore_not_found:
            # ignore_not_found=True の場合は特別なログを出力
            logger.debug(f"GraphQL resource not found during {context} - preparing to return None as requested")
        raise GitHubResourceNotFoundError(f"GraphQL resource not found during {context}: {errors}", 
                                          is_graphql_not_found=True)
    else:
        # その他のGraphQLエラー
        raise GitHubClientError(f"GraphQL operation failed during {context}: {errors}")

def github_api_error_handler(
    context_func: Optional[Callable[..., str]] = None, 
    ignore_not_found: bool = False
) -> Callable[[Callable[..., R]], Callable[..., Optional[R]]]:
    """
    GitHub API呼び出しのエラーを処理し、適切なカスタム例外にラップするデコレータ。
    GraphQL APIの場合、戻り値のレスポンスにエラーが含まれているかもチェックします。

    Args:
        context_func: メソッド呼び出し時のコンテキスト文字列を生成する関数 (self, *args を受け取る)。
                     コンテキストはログ出力とエラーメッセージに使用されます。
                     省略した場合、デコレートされる関数名が使用されます。
        ignore_not_found: Trueの場合、404 Not Foundエラーを無視し、Noneを返します。
                         デフォルトはFalseで、GitHubResourceNotFoundErrorとして例外を送出します。
                         get_label()やcheck_collaborator()など、存在チェック系のメソッドで有用です。

    Returns:
        デコレータ関数。

    Examples:
        ```python
        def get_repo_context(self, owner, repo): 
            return f"get repo {owner}/{repo}"

        @github_api_error_handler(get_repo_context)
        def get_repository(self, owner, repo):
            # 実装...
            pass
            
        # 404を無視する例
        @github_api_error_handler(ignore_not_found=True)
        def get_label(self, owner, repo, name):
            # 実装...
            # 404の場合はNoneを返す
            pass
        ```
    """
    def decorator(func: Callable[..., R]) -> Callable[..., Optional[R]]:
        @functools.wraps(func)
        def wrapper(self: Any, *args: Any, **kwargs: Any) -> Optional[R]:
            # メソッド呼び出し前にコンテキスト文字列を生成
            context = context_func(self, *args, **kwargs) if context_func else f"{func.__name__} operation"
            try:
                logger.debug(f"Executing GitHub API call: {context}")
                # 元のメソッドを実行
                result = func(self, *args, **kwargs)
                
                # GraphQLレスポンス内のエラーチェック（例外ではなくレスポンスにエラーが含まれる場合）
                if result is not None:
                    errors = None
                    # GraphQLレスポンスからエラーを抽出
                    if isinstance(result, dict) and "errors" in result:
                        errors = result["errors"]
                    elif hasattr(result, "errors") and result.errors:
                        errors = result.errors
                    # GraphQLResponse型のインスタンスの場合もチェック
                    elif GraphQLResponse is not None and isinstance(result, GraphQLResponse) and hasattr(result, "errors") and result.errors:
                        errors = result.errors
                    
                    if errors:
                        # エラー処理ヘルパーを呼び出す（例外が発生する可能性がある）
                        _process_graphql_errors(errors, context, ignore_not_found)
                
                # エラーがなければ結果を返す
                return result
                
            except GitHubClientError as e:
                # 既にカスタム例外にラップされている場合の処理
                # ignore_not_found と is_graphql_not_found フラグをチェック
                if ignore_not_found and isinstance(e, GitHubResourceNotFoundError) and getattr(e, 'is_graphql_not_found', False):
                    logger.debug(f"GraphQL resource not found during {context} - returning None as requested")
                    return None
                # 既にカスタム例外にラップされている場合はそのまま再送出
                logger.debug(f"Passing through existing custom exception: {type(e).__name__} during {context}")
                raise
            except RequestFailed as e:
                # githubkit の RequestFailed 例外を処理 (主にREST API)
                response = getattr(e, 'response', None)
                status_code = getattr(response, 'status_code', None)
                headers = getattr(response, 'headers', {})
                error_content_bytes = getattr(response, 'content', b'')
                try:
                    error_content_str = error_content_bytes.decode('utf-8', errors='replace')
                except Exception:
                    error_content_str = "[Could not decode error content]"

                msg = f"GitHub REST API RequestFailed during {context} (Status: {status_code}): {e} - Response: {error_content_str}"
                logger.warning(msg) # 失敗時はWarningレベル

                # ステータスコードに基づいて適切なドメイン例外に変換
                if status_code == 401:
                    raise GitHubAuthenticationError(f"Authentication failed (401) during {context}. Check PAT.", 
                                                   status_code=status_code, original_exception=e) from e
                elif status_code == 403:
                    remaining = headers.get("X-RateLimit-Remaining")
                    if remaining == "0":
                        raise GitHubRateLimitError(f"Rate limit exceeded during {context}", 
                                                 status_code=status_code, original_exception=e) from e
                    else:
                        raise GitHubAuthenticationError(f"Permission denied (403) during {context}. Check PAT scope.", 
                                                      status_code=status_code, original_exception=e) from e
                elif status_code == 404:
                    # ignore_not_foundフラグが指定されている場合は、404を無視してNoneを返す
                    if ignore_not_found:
                        logger.debug(f"REST resource not found (404) during {context} - returning None as requested")
                        return None
                    # そうでなければResourceNotFoundErrorを送出
                    else:
                        raise GitHubResourceNotFoundError(f"Resource not found (404) during {context}", 
                                                        status_code=status_code, original_exception=e) from e
                elif status_code == 422:
                    # リポジトリ作成時の重複エラーなどをより具体的に判定
                    if "repository" in context and "name already exists" in error_content_str.lower():
                        logger.warning(f"Repository validation failed (422): Name already exists during {context}")
                        raise GitHubValidationError(f"Repository name already exists during {context}: {error_content_str}", 
                                                  status_code=status_code, original_exception=e) from e
                    else:
                        raise GitHubValidationError(f"Validation failed (422) during {context}: {error_content_str}", 
                                                  status_code=status_code, original_exception=e) from e
                else: # その他の4xx, 5xxエラー
                    raise GitHubClientError(f"Unhandled HTTP error (Status: {status_code}) during {context}: {e}", 
                                          status_code=status_code, original_exception=e) from e

            except (RequestError, RequestTimeout) as e:
                # githubkit のネットワーク関連エラー
                logger.warning(f"GitHub API request/network error during {context}: {e}")
                raise GitHubClientError(f"Network/Request error during {context}: {e}", original_exception=e) from e

            except Exception as e:
                # 予期しないその他の例外
                logger.error(f"Unexpected error during {context}: {type(e).__name__} - {e}", exc_info=True)
                
                # 例外の中にGraphQLエラーが含まれているかヒューリスティックにチェック
                graphql_errors = None
                error_str = str(e)
                
                # 例外の文字列表現にJSONっぽいGraphQLエラーが含まれているか確認
                if "'errors':" in error_str or '"errors":' in error_str:
                    try:
                        # 文字列からエラーを抽出する試み
                        error_dict = eval(error_str)
                        if isinstance(error_dict, dict) and 'errors' in error_dict:
                            graphql_errors = error_dict['errors']
                    except (SyntaxError, NameError, TypeError):
                        # 評価できない場合は予期せぬエラーとして処理
                        pass
                        
                # GraphQLエラーが検出された場合は専用のエラー処理
                if graphql_errors:
                    logger.debug(f"GraphQL error detected in exception during {context}: {graphql_errors}")
                    try:
                        _process_graphql_errors(graphql_errors, context, ignore_not_found)
                        return None  # 正常にエラー処理された場合（ここには到達しない）
                    except GitHubResourceNotFoundError as not_found_err:
                        # ignore_not_foundフラグがあればNoneを返す
                        if ignore_not_found:
                            logger.debug(f"GraphQL resource not found from exception during {context} - returning None")
                            return None
                        raise  # それ以外は再送出
                    except GitHubClientError:
                        # その他のカスタムエラーは再送出
                        raise
                
                # 予期しないエラーとして処理
                raise GitHubClientError(f"Unexpected error during {context}: {e}", original_exception=e) from e
                
        return wrapper
    return decorator
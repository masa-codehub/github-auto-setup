import os
import logging
import json
from pydantic import SecretStr
from githubkit import GitHub
# エラー処理のために例外もインポート
from github_automation_tool.domain.exceptions import (
    GitHubClientError, GitHubAuthenticationError, GitHubResourceNotFoundError
)
# GraphQLResponse もインポートしておく
from githubkit.graphql import GraphQLResponse

# --- 基本的なロギング設定 ---
logging.basicConfig(
    level=logging.DEBUG, # デバッグ情報を表示
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("find_project_sample")

# --- 設定 ---
# 環境変数から PAT を読み込む
# 事前に export GITHUB_PAT="ghp_..." のように設定してください
try:
    pat_token = SecretStr(os.environ["GITHUB_PAT"])
    if not pat_token.get_secret_value():
        raise ValueError("GITHUB_PAT environment variable is set but empty.")
except KeyError:
    logger.error("ERROR: GITHUB_PAT environment variable not set.")
    exit(1)
except ValueError as e:
     logger.error(f"ERROR: {e}")
     exit(1)

# --- 検索対象 ---
# ここを実際のオーナー名とプロジェクト名に変更してください
TARGET_OWNER = "masa-codehub"
TARGET_PROJECT_NAME = "Test Project"

# --- GitHub クライアント初期化 ---
try:
    gh = GitHub(pat_token.get_secret_value())
    logger.info("GitHub client initialized.")
except Exception as e:
    logger.error(f"Failed to initialize GitHub client: {e}", exc_info=True)
    exit(1)

# --- GraphQL クエリ (リスト取得 + ページネーション) ---
query = """
query GetProjectsList($ownerLogin: String!, $first: Int!, $after: String) {
  repositoryOwner(login: $ownerLogin) {
    ... on ProjectV2Owner {
      projectsV2(first: $first, after: $after) {
        nodes {
          id
          title
        }
        pageInfo {
          endCursor
          hasNextPage
        }
      }
    }
  }
}
"""

# --- 検索実行 ---
after_cursor = None
has_next_page = True
page_count = 0
max_pages = 10 # 念のため最大ページ制限
found_project_id = None

logger.info(f"Searching for Project V2 '{TARGET_PROJECT_NAME}' owned by '{TARGET_OWNER}'...")

try:
    while has_next_page and page_count < max_pages:
        page_count += 1
        variables = {
            "ownerLogin": TARGET_OWNER,
            "first": 100
        }
        if after_cursor:
            variables["after"] = after_cursor

        logger.debug(f"Querying page {page_count}, cursor: {after_cursor}")
        response = gh.graphql(query, variables)
        
        # レスポンスオブジェクトの詳細調査のためのデバッグログを追加
        logger.debug(f"Investigating response object:")
        logger.debug(f"  Type: {type(response)}")
        logger.debug(f"  Dir: {dir(response)}")  # 持っている属性やメソッドを表示
        logger.debug(f"  Representation: {repr(response)}")  # オブジェクトの文字列表現
        
        # 辞書としてアクセス可能か試す
        try:
            if isinstance(response, dict):
                logger.debug(f"  Keys: {list(response.keys())}")
            elif hasattr(response, "__dict__"):
                logger.debug(f"  __dict__: {response.__dict__}")
        except Exception as e:
            logger.debug(f"  Cannot access as dictionary: {e}")
        
        # エラーチェック
        if isinstance(response, dict) and response.get('errors'):
            errors_list = response.get('errors')
            logger.error(f"GraphQL errors on page {page_count}: {errors_list}")
        elif hasattr(response, 'errors') and response.errors:
            errors_list = response.errors
            logger.error(f"GraphQL errors on page {page_count}: {errors_list}")

        # データ処理 - responseオブジェクトが直接データである場合の対応
        # 直接responseをデータとして扱う
        if isinstance(response, dict):
            # GraphQLの応答がトップレベルでデータを返す場合
            if "repositoryOwner" in response:
                data = response  # responseそのものがデータ
                logger.debug("Response itself contains top-level data")
            else:
                # 標準的なGraphQL応答構造（dataフィールド内にデータがある場合）
                data = response.get("data")
                logger.debug("Accessing standard GraphQL response structure with data field")
        else:
            # オブジェクトの場合は属性としてdataにアクセス
            data = getattr(response, 'data', None)
            logger.debug("Accessing response as object with .data attribute")

        # dataがどのような形かをログに出力
        logger.debug(f"  Data type: {type(data)}")
        logger.debug(f"  Data content: {data}")
        
        if not data:
            logger.error(f"GraphQL response missing data on page {page_count}.")
            break # データがないならループ終了

        # repositoryOwnerにアクセス
        owner_data = None
        if isinstance(data, dict):
            if "repositoryOwner" in data:
                owner_data = data.get("repositoryOwner")
            elif data.get("data") and isinstance(data.get("data"), dict):
                # 入れ子になっている可能性もチェック
                owner_data = data.get("data").get("repositoryOwner")
        
        if not owner_data:
            logger.warning(f"Repository owner '{TARGET_OWNER}' not found or has no projects (response on page {page_count}).")
            break

        projects_v2 = owner_data.get("projectsV2")
        if not projects_v2:
            logger.warning(f"No projectsV2 data found for owner '{TARGET_OWNER}' (response on page {page_count}).")
            break

        nodes = projects_v2.get("nodes", [])
        page_info = projects_v2.get("pageInfo", {})

        if nodes is None or page_info is None:
             logger.error(f"GraphQL response missing 'nodes' or 'pageInfo' on page {page_count}.")
             break # 不正な形式ならループ終了

        # クライアント側フィルタリング
        logger.debug(f"Checking {len(nodes)} nodes on page {page_count}...")
        for node in nodes:
            if node and isinstance(node, dict):
                 node_title = node.get("title")
                 logger.debug(f" Checking node: title='{node_title}'") # 各タイトルをログ出力
                 if node_title == TARGET_PROJECT_NAME:
                     found_project_id = node.get("id")
                     logger.info(f"FOUND project '{TARGET_PROJECT_NAME}' with ID: {found_project_id}")
                     has_next_page = False # 見つかったのでループ終了
                     break # inner loop break

        if found_project_id:
            break # outer loop break

        # ページネーション更新
        if not has_next_page: # found_project_id が見つかってループを抜ける前に has_next_page が更新される
             break
             
        has_next_page = page_info.get("hasNextPage", False)
        if has_next_page:
            after_cursor = page_info.get("endCursor")
            if not after_cursor:
                logger.warning(f"hasNextPage is True but endCursor is missing on page {page_count}, stopping pagination.")
                has_next_page = False

    # --- 結果表示 ---
    if found_project_id:
        print(f"\nSUCCESS: Found Project '{TARGET_PROJECT_NAME}' with Node ID: {found_project_id}")
    else:
        if page_count >= max_pages:
            print(f"\nNOT FOUND: Reached maximum page limit ({max_pages}) while searching for project '{TARGET_PROJECT_NAME}'.")
        else:
            print(f"\nNOT FOUND: Project '{TARGET_PROJECT_NAME}' was not found for owner '{TARGET_OWNER}' after searching {page_count} page(s).")
        exit(1) # 見つからなかった場合はエラーコードで終了

except Exception as e:
    # ここで _handle_api_error を模倣するか、シンプルにエラー表示
    logger.error(f"An error occurred: {type(e).__name__} - {e}", exc_info=True)
    print(f"\nERROR: An unexpected error occurred during the search. Check logs.")
    exit(1)
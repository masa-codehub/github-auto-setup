# src/github_automation_tool/adapters/github_graphql_client.py

import logging
from typing import Optional, Dict, Any

from githubkit import GitHub

# GraphQLResponse のインポート元を修正 (githubkit v1.0.0 以降を想定)
try:
    # githubkit v1.0+
    from githubkit.response import GraphQLResponse as GraphQLResponseData
except ImportError:
    # Older versions might have it elsewhere or handle errors differently
    try:
        from githubkit.graphql import GraphQLResponse as GraphQLResponseData
    except ImportError:
        GraphQLResponseData = dict  # Fallback

# エラーハンドリングデコレータとドメイン例外をインポート
from github_automation_tool.adapters.github_utils import github_api_error_handler
from github_automation_tool.domain.exceptions import (
    GitHubClientError, GitHubResourceNotFoundError, GitHubAuthenticationError
)

logger = logging.getLogger(__name__)

class GitHubGraphQLClient:
    """
    githubkit を使用して GitHub GraphQL API v4 と対話するクライアント。
    エラーハンドリングはデコレータ @github_api_error_handler に委譲します。
    """

    def __init__(self, github_instance: GitHub):
        """
        Args:
            github_instance: 認証済みの githubkit.GitHub インスタンス。
        """
        if not isinstance(github_instance, GitHub):
            raise TypeError("github_instance must be a valid githubkit.GitHub instance.")
        self.gh = github_instance
        logger.info("GitHubGraphQLClient initialized.")

    # --- Context Generators for Decorator ---
    def _find_project_context(self, owner: str, project_name: str) -> str:
        return f"finding Project V2 '{project_name}' for owner '{owner}'"

    def _add_item_context(self, project_node_id: str, content_node_id: str) -> str:
        return f"adding item '{content_node_id}' to project '{project_node_id}'"

    # --- ProjectsV2 ---
    @github_api_error_handler(_find_project_context, ignore_not_found=True)
    def find_project_v2_node_id(self, owner: str, project_name: str) -> Optional[str]:
        """
        指定されたプロジェクト名のProject V2 Node IDをGraphQL APIで検索します。
        プロジェクトリストを取得し、クライアント側でタイトルが完全一致するものを探します。
        見つからない、またはレスポンスデータが不完全な場合は None を返します。

        Args:
            owner: プロジェクト所有者のログイン名
            project_name: 検索するプロジェクト名（完全一致）

        Returns:
            見つかった場合はProject V2のノードID文字列、見つからない場合やデータ欠損時はNone
        """
        # UseCase側で引数のバリデーションを行う想定
        trimmed_owner = owner.strip()
        trimmed_name = project_name.strip()
        if not trimmed_owner or not trimmed_name:
            logger.warning("Owner or project name is empty after trimming. Returning None.")
            return None # 空の場合は検索しない

        logger.info(f"Attempting to find Project V2 '{trimmed_name}' for owner '{trimmed_owner}'...")

        query = """
        query GetProjectsList($ownerLogin: String!, $first: Int!, $after: String) {
          repositoryOwner(login: $ownerLogin) {
            ... on ProjectV2Owner {
              projectsV2(first: $first, after: $after) {
                nodes { id title }
                pageInfo { endCursor hasNextPage }
              } } } }
        """
        after_cursor = None
        has_next_page = True
        page_count = 0
        max_pages = 10 # Safety limit
        found_project_id: Optional[str] = None

        while has_next_page and page_count < max_pages:
            page_count += 1
            variables = {"ownerLogin": trimmed_owner, "first": 100}
            if after_cursor: variables["after"] = after_cursor

            logger.debug(f"Querying page {page_count} of projects for '{trimmed_owner}', cursor: {after_cursor}")

            response = self.gh.graphql(query, variables) # type: ignore

            # デコレータが Not Found (404等) を処理した場合、Noneが返るのでチェック
            if response is None:
                logger.debug(f"GraphQL query handled by decorator (e.g., 404 Not Found) during project search (page {page_count}). Returning None.")
                return None

            # --- ★ Issueで提案された修正箇所を反映 ★ ---
            data = response.get("data") if isinstance(response, dict) else getattr(response, 'data', None)

            # data が None や空の場合も None を返す (堅牢性向上)
            if data is None:
                # 以前はエラーにしていたが、警告ログを出力して None を返すように変更
                logger.warning(f"GraphQL response missing 'data' field on page {page_count}. Treating as not found.")
                return None
            if isinstance(data, dict) and not data:
                logger.warning(f"GraphQL response has empty 'data' object on page {page_count}. Treating as not found.")
                return None

            owner_data = data.get("repositoryOwner")
            # owner_data が None や空の場合も None を返す (堅牢性向上)
            if not owner_data: # None または空辞書の場合
                logger.warning(f"Repository owner '{trimmed_owner}' not found or response missing 'repositoryOwner' field on page {page_count}. Returning None.")
                return None

            projects_v2 = owner_data.get("projectsV2")
            # projects_v2 が None や空の場合も None を返す (堅牢性向上)
            if not projects_v2: # None または空辞書の場合
                logger.warning(f"No projectsV2 data found for owner '{trimmed_owner}' on page {page_count}. Returning None.")
                return None

            nodes = projects_v2.get("nodes") # デフォルト値([])を使わず、None チェックを行う
            page_info = projects_v2.get("pageInfo")

            # nodes や pageInfo が None の場合も None を返す (堅牢性向上)
            if nodes is None or page_info is None:
                # 以前はエラーにしていたが、警告ログを出力して None を返すように変更
                logger.warning(f"GraphQL response missing 'nodes' or 'pageInfo' on page {page_count}. Treating as not found.")
                return None
            # --- ★ 修正箇所ここまで ★ ---

            logger.debug(f"Checking {len(nodes)} nodes on page {page_count}...")
            for node in nodes:
                if node and isinstance(node, dict):
                     node_title = node.get("title")
                     node_id = node.get("id")
                     logger.debug(f" Checking node: title='{node_title}', id='{node_id}'")
                     if node_title == trimmed_name:
                         if node_id:
                             found_project_id = node_id
                             logger.info(f"FOUND project '{trimmed_name}' with ID: {found_project_id}")
                             has_next_page = False # 見つかったらループ終了フラグ
                             break # inner loop break
                         else:
                              logger.warning(f"Found project '{trimmed_name}' but it has no ID. Skipping.")

            if found_project_id:
                break # outer loop break

            # ページネーション更新 (ループ終了フラグが立っていない場合のみ)
            if not has_next_page:
                 break

            has_next_page = page_info.get("hasNextPage", False)
            if has_next_page:
                after_cursor = page_info.get("endCursor")
                if not after_cursor:
                    logger.warning(f"hasNextPage is True but endCursor is missing on page {page_count}, stopping pagination.")
                    has_next_page = False
        # --- End While Loop ---

        if found_project_id:
            return found_project_id
        else:
            if page_count >= max_pages:
                logger.warning(f"Reached maximum page limit ({max_pages}) while searching for project '{trimmed_name}'. Project not found.")
            else:
                 logger.warning(f"Project V2 '{trimmed_name}' not found for owner '{trimmed_owner}' after searching {page_count} page(s).")
            return None # 見つからなかった

    @github_api_error_handler(_add_item_context)
    def add_item_to_project_v2(self, project_node_id: str, content_node_id: str) -> str:
        """
        指定された Issue (content_node_id) を ProjectV2 にアイテムとして追加します。
        成功した場合、追加されたアイテムの Node ID を返します。

        Args:
            project_node_id: 追加先のプロジェクトの Node ID。
            content_node_id: 追加する Issue または Pull Request の Node ID。

        Returns:
            追加された Project V2 アイテムの Node ID。

        Raises:
            GitHubClientError: APIエラーまたはレスポンス形式エラーの場合。
            ValueError: 引数が空の場合 (UseCase側でチェック推奨)。
        """
        # UseCase側で引数のバリデーションを行う想定
        p_id, c_id = project_node_id.strip(), content_node_id.strip()
        if not p_id or not c_id:
             raise ValueError("Project Node ID and Content Node ID cannot be empty.")

        logger.info(f"Attempting to add item '{c_id}' to project '{p_id}'...")
        mutation = """
        mutation AddItemToProject($projectId: ID!, $contentId: ID!) {
          addProjectV2ItemById(input: {projectId: $projectId, contentId: $contentId}) { item { id } }
        }
        """
        variables = {"projectId": p_id, "contentId": c_id}

        # GraphQL APIを呼び出し
        response = self.gh.graphql(mutation, variables) # type: ignore
        
        # レスポンスがNoneの場合（デコレータがエラー処理した場合）
        if response is None:
            logger.warning(f"GraphQL mutation failed or returned None during item addition for project {p_id} (handled by decorator?).")
            raise GitHubClientError(f"Failed to add item to project {p_id}.")

        # --- Data Extraction (Simplified) ---
        data = response.get("data") if isinstance(response, dict) else getattr(response, 'data', None)
        if not data:
            # エラー処理を戻す - dataがない場合は例外を送出
            raise GitHubClientError(f"GraphQL response missing 'data' during item addition for project {p_id}.")

        add_item_response = data.get("addProjectV2ItemById")
        if add_item_response:
            item = add_item_response.get("item")
            # Optional Chaining の代わりに get を使用
            if item and isinstance(item, dict):
                 item_id = item.get("id")
                 if item_id and isinstance(item_id, str):
                      logger.info(f"Successfully added item '{c_id}' to project '{p_id}', new item ID: {item_id}") # DEBUGからINFOに変更
                      return item_id

        # If we reach here, the expected data structure was missing
        raise GitHubClientError(f"Failed to add item to project {p_id} or retrieve item ID from response. Response data: {data}")
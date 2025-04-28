# src/github_automation_tool/adapters/github_graphql_client.py

import logging
from typing import Optional, Dict, Any, cast, TypeVar
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

# 戻り値の型アノテーション用
R = TypeVar('R')

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
        見つからない場合は None を返します (404 Not Foundはエラーとしない)。

        Args:
            owner: プロジェクト所有者のログイン名
            project_name: 検索するプロジェクト名（完全一致）

        Returns:
            見つかった場合はProject V2のノードID文字列、見つからない場合はNone
        """
        # UseCase側で引数のバリデーションを行う想定
        trimmed_owner = owner.strip()
        trimmed_name = project_name.strip()
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

        while has_next_page and page_count < max_pages:
            page_count += 1
            variables = {"ownerLogin": trimmed_owner, "first": 100}
            if after_cursor: variables["after"] = after_cursor

            logger.debug(f"Querying page {page_count} of projects for '{trimmed_owner}', cursor: {after_cursor}")

            # GraphQL APIを呼び出し
            response = self.gh.graphql(query, variables) # type: ignore # Ignore complex response type
            
            # 404 Not Found はデコレータが処理して None を返すはず。
            # errorsフィールドがある場合もデコレータが処理するので、ここでは対処不要

            # --- Data Extraction ---
            # レスポンスがNoneの場合（デコレータがエラー処理した場合）
            if response is None:
                logger.warning(f"Project V2 '{trimmed_name}' not found for owner '{trimmed_owner}' (handled as None).")
                return None

            data = response.get("data") if isinstance(response, dict) else getattr(response, 'data', None)
            if not data:
                logger.warning(f"GraphQL response has empty data on page {page_count} for project search. This might indicate an issue.")
                return None  # データがない場合はNoneを返す

            owner_data = data.get("repositoryOwner")
            if not owner_data:
                # Ownerが見つからない場合はNoneを返す
                logger.warning(f"Repository owner '{trimmed_owner}' not found or has no projects (page {page_count}). Returning None.")
                return None

            projects_v2 = owner_data.get("projectsV2")
            if not projects_v2:
                logger.warning(f"No projectsV2 data found for owner '{trimmed_owner}' (page {page_count}). Returning None.")
                return None # projectsV2 field がない場合も Not Found 扱い

            nodes = projects_v2.get("nodes", [])
            page_info = projects_v2.get("pageInfo", {})
            if nodes is None or page_info is None:
                logger.error(f"GraphQL response missing 'nodes' or 'pageInfo' on page {page_count}.")
                return None  # エラーの場合もNoneを返す

            for node in nodes:
                if node and isinstance(node, dict) and node.get("title") == trimmed_name:
                    found_project_id = node.get("id")
                    if found_project_id:
                        logger.info(f"Found project '{trimmed_name}' with Node ID: {found_project_id}")
                        return found_project_id # 発見

            # Pagination update
            has_next_page = page_info.get("hasNextPage", False)
            if has_next_page:
                after_cursor = page_info.get("endCursor")
                if not after_cursor:
                    logger.warning(f"hasNextPage is True but endCursor is missing on page {page_count}, stopping pagination.")
                    has_next_page = False
        # --- End While Loop ---

        if page_count >= max_pages:
            logger.warning(f"Reached maximum page limit ({max_pages}) while searching for project '{trimmed_name}'. Project not found.")
        else:
             # ループが正常に終了したが、見つからなかった場合
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
            logger.warning(f"Failed to add item to project {p_id} (handled by decorator).")
            raise GitHubClientError(f"Failed to add item to project {p_id}.")

        # --- Data Extraction (Simplified) ---
        data = response.get("data") if isinstance(response, dict) else getattr(response, 'data', None)
        if not data:
            # ここではエラーが発生しません - デコレータがGraphQLエラーを検出して処理するため
            # テスト用に条件文だけ残し、pass処理を追加
            pass

        add_item_response = data.get("addProjectV2ItemById") if data else None
        if add_item_response:
            item = add_item_response.get("item")
            # Optional Chaining の代わりに get を使用
            if item and isinstance(item, dict):
                 item_id = item.get("id")
                 if item_id and isinstance(item_id, str):
                      logger.info(f"Successfully added item '{c_id}' to project '{p_id}', new item ID: {item_id}")
                      return item_id

        # If we reach here, the expected data structure was missing
        raise GitHubClientError(f"Failed to add item to project {p_id} or retrieve item ID from response. Response data: {data}")
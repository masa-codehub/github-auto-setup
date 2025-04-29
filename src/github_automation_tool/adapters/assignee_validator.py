# ファイル名: src/github_automation_tool/adapters/assignee_validator.py
# 新規作成

import logging
from typing import List, Tuple

# 依存する GitHubRestClient とドメイン例外をインポート
from github_automation_tool.adapters.github_rest_client import GitHubRestClient
from github_automation_tool.domain.exceptions import GitHubClientError

logger = logging.getLogger(__name__)

class AssigneeValidator:
    """
    GitHub担当者の有効性（リポジトリのコラボレーターであるか）を検証するクラス。
    """

    def __init__(self, rest_client: GitHubRestClient):
        """
        Args:
            rest_client: コラボレーター確認API(`check_collaborator`)を呼び出すための GitHubRestClient インスタンス。
        """
        if not isinstance(rest_client, GitHubRestClient):
            raise TypeError("rest_client must be an instance of GitHubRestClient.")
        self.rest_client = rest_client
        logger.info("AssigneeValidator initialized.")

    def validate_assignees(self, owner: str, repo: str, assignee_logins: List[str]) -> Tuple[List[str], List[str]]:
        """
        担当者のリストを検証し、有効なログイン名リストと無効（または検証不可）なログイン名リストを返します。
        '@' プレフィックスは除去されます。空や空白のログイン名は無視されます。

        Args:
            owner: リポジトリのオーナー名。
            repo: リポジトリ名。
            assignee_logins: 検証する担当者ログイン名のリスト (例: ["user1", "@user2", "invalid-user"])。

        Returns:
            (有効な担当者ログイン名リスト, 無効または検証不可の担当者ログイン名リスト) のタプル。
            APIエラー発生時、検証対象の担当者は無効リストに含まれます。
        """
        if not assignee_logins:
            return [], []

        valid_assignees: List[str] = []
        invalid_assignees: List[str] = []

        # 重複を排除し、空や@を除去したログイン名のセットを作成
        unique_logins_to_check = {
            login.strip().lstrip('@') for login in assignee_logins if login and login.strip()
        }

        if not unique_logins_to_check:
             logger.debug("No valid assignee logins found after cleanup.")
             return [], []

        logger.info(f"Validating {len(unique_logins_to_check)} unique assignee(s) for {owner}/{repo}...")

        for login in unique_logins_to_check:
            is_valid = False # Assume invalid initially
            try:
                # GitHubRestClient の check_collaborator を使用
                # このメソッドはコラボレーターならTrue、そうでなければ(404含む)Falseを返す
                # APIエラーの場合は例外を送出する
                is_valid = self.rest_client.check_collaborator(owner, repo, login)

                if is_valid:
                    logger.debug(f"Assignee '{login}' is valid for {owner}/{repo}.")
                    valid_assignees.append(login)
                else:
                     # check_collaborator が False を返した場合 (404 Not Found など)
                     logger.warning(f"Assignee '{login}' is not a collaborator or could not be verified for {owner}/{repo}.")
                     invalid_assignees.append(login)

            except GitHubClientError as e:
                # check_collaborator で 404 以外の API エラーが発生した場合
                # (例: 403 Forbidden, 500 Server Error)
                logger.warning(f"API error validating assignee '{login}' for {owner}/{repo}: {type(e).__name__} - {e}. Marking as invalid.")
                invalid_assignees.append(login)
            except Exception as e:
                 # その他の予期せぬエラー
                 logger.error(f"Unexpected error validating assignee '{login}' for {owner}/{repo}: {type(e).__name__} - {e}", exc_info=True)
                 invalid_assignees.append(login) # 予期せぬエラー時も無効扱い

        # --- Validation Summary Logging ---
        total_checked = len(unique_logins_to_check)
        if invalid_assignees:
            logger.warning(f"Assignee validation finished. Valid: {len(valid_assignees)}/{total_checked}, Invalid/Unverified: {len(invalid_assignees)}/{total_checked}. Invalid list: {invalid_assignees}")
        else:
             logger.info(f"Assignee validation finished. All {len(valid_assignees)}/{total_checked} assignee(s) are valid for {owner}/{repo}.")

        return valid_assignees, invalid_assignees
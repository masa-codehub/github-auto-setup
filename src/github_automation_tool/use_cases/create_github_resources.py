import logging
from pathlib import Path
from collections.abc import Callable  # Python 3.9+ for type hint
import json

# 依存コンポーネントとデータモデル、例外をインポート
from github_automation_tool.infrastructure.config import Settings
from github_automation_tool.infrastructure.file_reader import read_markdown_file
from github_automation_tool.adapters.ai_parser import AIParser
from github_automation_tool.adapters.github_client import GitHubAppClient
from github_automation_tool.use_cases.create_repository import CreateRepositoryUseCase
from github_automation_tool.use_cases.create_issues import CreateIssuesUseCase
from github_automation_tool.adapters.cli_reporter import CliReporter
from github_automation_tool.domain.models import ParsedRequirementData, CreateIssuesResult, IssueData  # IssueDataも使う
from github_automation_tool.domain.exceptions import (
    AiParserError, GitHubClientError, GitHubAuthenticationError, GitHubValidationError
)
import builtins  # FileNotFoundError など

logger = logging.getLogger(__name__)


class CreateGitHubResourcesUseCase:
    """
    ファイル読み込みからリポジトリ作成、ラベル作成、Issue作成までの主要なワークフローを実行するUseCase。
    """

    def __init__(self,
                 settings: Settings,
                 file_reader: Callable[[Path], str],
                 ai_parser: AIParser,
                 github_client: GitHubAppClient,
                 create_repo_uc: CreateRepositoryUseCase,
                 create_issues_uc: CreateIssuesUseCase,
                 reporter: CliReporter):
        """UseCaseを初期化し、依存コンポーネントを注入します。"""
        self.settings = settings
        self.file_reader = file_reader
        self.ai_parser = ai_parser
        self.github_client = github_client
        self.create_repo_uc = create_repo_uc
        self.create_issues_uc = create_issues_uc
        self.reporter = reporter
        logger.debug("CreateGitHubResourcesUseCase initialized.")

    def _get_owner_repo(self, repo_name_input: str) -> tuple[str, str]:
        """入力リポジトリ名から owner と repo を抽出 (owner省略時は認証ユーザー)"""
        logger.debug(f"Parsing repository name input: {repo_name_input}")
        if '/' in repo_name_input:
            parts = repo_name_input.split('/', 1)
            if len(parts) == 2 and parts[0] and parts[1]:
                owner, repo = parts
                logger.debug(f"Parsed owner={owner}, repo={repo}")
                return owner, repo
            else:
                raise ValueError(
                    f"Invalid repository name format: '{repo_name_input}'. Expected 'owner/repo'.")
        else:
            logger.info(
                "Owner not specified in repo name, attempting to get authenticated user.")
            try:
                user_response = self.github_client.gh.rest.users.get_authenticated()
                owner = getattr(user_response.parsed_data, 'login', None)
                if not owner:
                    logger.error(
                        "Could not retrieve login name for authenticated user.")
                    raise GitHubClientError(
                        "Could not retrieve authenticated user login name.")
                logger.info(f"Using authenticated user as owner: {owner}")
                return owner, repo_name_input
            except Exception as e:
                logger.error(
                    f"Failed to get authenticated user: {e}", exc_info=True)
                raise GitHubAuthenticationError(
                    f"Failed to get authenticated user: {e}", original_exception=e) from e

    def execute(self, file_path: Path, repo_name_input: str, project_name: str, dry_run: bool = False):
        """
        リソース作成のワークフローを実行します。
        エラーが発生した場合、処理を中断し例外を送出します。
        """
        logger.info(
            f"Starting GitHub resource creation workflow for file: '{file_path}'...")
        repo_owner, repo_name, repo_full_name = "", "", ""

        try:
            # --- ステップ 0: リポジトリ名解析 ---
            repo_owner, repo_name = self._get_owner_repo(repo_name_input)
            repo_full_name = f"{repo_owner}/{repo_name}"
            logger.info(f"Target repository identified: {repo_full_name}")

            # --- ステップ 1: ファイル読み込み ---
            logger.info(f"Reading file: {file_path}")
            markdown_content = self.file_reader(file_path)
            logger.info(
                f"File read successfully (length: {len(markdown_content)}).")

            # --- ステップ 2: AI パース ---
            logger.info("Parsing content with AI...")
            parsed_data: ParsedRequirementData = self.ai_parser.parse(
                markdown_content)
            logger.info(
                f"AI parsing complete. Found {len(parsed_data.issues)} potential issue(s).")

            # --- ステップ 3: Dry Run モード ---
            if dry_run:
                logger.warning(
                    "Dry run mode enabled. Skipping GitHub operations.")
                self.reporter.display_repository_creation_result(
                    f"https://github.com/{repo_full_name} (Dry Run)", repo_name)
                # Dry Run 用のラベル情報表示 (例)
                unique_labels = set()
                if parsed_data.issues:
                    for issue in parsed_data.issues:
                        if issue.labels:
                            unique_labels.update(issue.labels)
                logger.info(
                    f"[Dry Run] Would ensure {len(unique_labels)} labels exist: {sorted(list(unique_labels))}")
                # Dry Run 用のIssue結果表示
                dummy_issues_result = CreateIssuesResult(
                    created_issue_urls=[
                        f"URL for '{issue.title}' (Dry Run)" for issue in parsed_data.issues]
                )
                self.reporter.display_issue_creation_result(
                    dummy_issues_result, repo_full_name)
                logger.warning("Dry run finished.")
                return

            # --- ステップ 4: リポジトリ作成 ---
            logger.info(
                f"Executing CreateRepositoryUseCase for '{repo_name}'...")
            repo_url = self.create_repo_uc.execute(repo_name)
            self.reporter.display_repository_creation_result(
                repo_url, repo_name)

            # --- ★★★ ステップ 4.5: ラベル作成/確認 (追加) ★★★ ---
            logger.info(
                f"Ensuring required labels exist in {repo_full_name}...")
            # まずファイル全体からユニークなラベル名を集める
            unique_labels_in_file = set()
            if parsed_data.issues:
                for issue in parsed_data.issues:
                    if issue.labels:  # labels フィールドが None でなくリストの場合
                        # 空文字列やNoneをフィルタリング（念のため）
                        valid_labels = [
                            lbl for lbl in issue.labels if lbl and lbl.strip()]
                        unique_labels_in_file.update(valid_labels)
            # (将来的に parsed_data.labels_to_create があればここで update)

            created_labels_count = 0
            skipped_labels_count = 0
            failed_labels: list[str] = []  # 型ヒント list[str]
            if unique_labels_in_file:
                logger.debug(
                    f"Unique labels found in file: {unique_labels_in_file}")
                # 各ラベルについて存在確認・作成を行う
                for label_name in sorted(list(unique_labels_in_file)):
                    try:
                        # GitHubクライアントのラベル作成メソッド呼び出し (冪等性あり)
                        # 色や説明は指定しない (GitHubデフォルト)
                        created = self.github_client.create_label(
                            repo_owner, repo_name, label_name)
                        if created:
                            created_labels_count += 1
                        else:
                            skipped_labels_count += 1
                    except GitHubClientError as e:  # create_label で発生しうる想定内エラー
                        logger.error(
                            f"Failed to ensure label '{label_name}': {e}")
                        failed_labels.append(label_name)
                        # ★★★ エラーが発生しても処理を継続する ★★★
                    except Exception as e:  # 予期せぬエラー
                        logger.exception(
                            f"Unexpected error ensuring label '{label_name}': {e}")
                        failed_labels.append(label_name)
                        # ★★★ 予期せぬエラーでも処理を継続する (必要なら中断も検討) ★★★
            else:
                logger.info("No valid labels found in parsed data to ensure.")

            # ラベル処理結果のログ出力 (専用Reporterメソッド推奨だが今回はログのみ)
            log_label_summary = (
                f"Label ensuring finished. New: {created_labels_count}, "
                f"Existing/Skipped: {skipped_labels_count}, Failed: {len(failed_labels)}."
            )
            if failed_labels:
                logger.warning(log_label_summary +
                               f" Failed labels: {failed_labels}")
            else:
                logger.info(log_label_summary)
            # ★★★ ラベル作成ここまで ★★★

            # --- ステップ 5: Issue 作成 ---
            logger.info(
                f"Executing CreateIssuesUseCase for '{repo_full_name}'...")
            # ★ 注意: 現在の CreateIssuesUseCase はラベル情報を Issue 作成時に利用しません。
            #    Issue にラベルを設定するには、以下のいずれかが必要です。
            #    1. CreateIssuesUseCase を修正し、parsed_data からラベル情報を読み取り、
            #       github_client.create_issue に labels 引数を渡すようにする。
            #    2. ここで CreateIssuesUseCase を使わず、直接 github_client.create_issue を
            #       ループで呼び出し、各 IssueData からラベル情報を渡す。
            #    今回は既存のUseCaseを呼び出す形を維持します。
            issue_result: CreateIssuesResult = self.create_issues_uc.execute(
                parsed_data, repo_owner, repo_name)
            self.reporter.display_issue_creation_result(
                issue_result, repo_full_name)

            # --- ステップ 6: (将来の実装箇所: マイルストーン作成、プロジェクトへのIssue追加など) ---
            logger.info(
                "Milestone creation/setting and Project linking steps not yet implemented.")

            logger.info(
                "GitHub resource creation process completed successfully.")

        # --- エラーハンドリング (変更なし) ---
        except FileNotFoundError as e:
            logger.error(f"Input file error: {e}")
            raise
        except PermissionError as e:
            logger.error(f"Input file permission error: {e}")
            raise
        except IOError as e:
            logger.error(f"Input file read error: {e}")
            raise
        except (ValueError, AiParserError, GitHubValidationError, GitHubAuthenticationError, GitHubClientError) as e:
            logger.error(
                f"Workflow error during resource creation: {type(e).__name__} - {e}")
            raise
        except Exception as e:
            logger.exception(
                f"An unexpected critical error occurred during resource creation workflow: {e}")
            raise GitHubClientError(
                f"An unexpected critical error occurred: {e}", original_exception=e) from e

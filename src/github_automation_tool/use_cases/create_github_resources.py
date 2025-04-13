import logging
from pathlib import Path
from typing import Tuple, Callable # Callable をインポート

# 依存コンポーネントとデータモデル、例外をインポート
from github_automation_tool.infrastructure.config import Settings
# file_reader は関数なので直接インポートするか、パスで指定する
from github_automation_tool.infrastructure.file_reader import read_markdown_file
from github_automation_tool.adapters.ai_parser import AIParser
from github_automation_tool.adapters.github_client import GitHubAppClient
from github_automation_tool.use_cases.create_repository import CreateRepositoryUseCase
from github_automation_tool.use_cases.create_issues import CreateIssuesUseCase
from github_automation_tool.adapters.cli_reporter import CliReporter
from github_automation_tool.domain.models import ParsedRequirementData, CreateIssuesResult
from github_automation_tool.domain.exceptions import (
    FileProcessingError, AiParserError, GitHubClientError,
    GitHubAuthenticationError, GitHubValidationError # 必要に応じて追加
)

logger = logging.getLogger(__name__)

class CreateGitHubResourcesUseCase:
    """
    ファイル読み込みからリポジトリ作成、Issue作成までの主要なワークフローを実行するUseCase。
    MVPのコアロジックを担当します。
    """
    def __init__(self,
                 settings: Settings,
                 # file_reader は関数なので Callable 型ヒントを使用
                 file_reader: Callable[[Path], str],
                 ai_parser: AIParser,
                 github_client: GitHubAppClient, # owner取得用に必要
                 create_repo_uc: CreateRepositoryUseCase,
                 create_issues_uc: CreateIssuesUseCase,
                 reporter: CliReporter):
        self.settings = settings
        self.file_reader = file_reader
        self.ai_parser = ai_parser
        self.github_client = github_client
        self.create_repo_uc = create_repo_uc
        self.create_issues_uc = create_issues_uc
        self.reporter = reporter
        logger.debug("CreateGitHubResourcesUseCase initialized with dependencies.")

    def _get_owner_repo(self, repo_name_input: str) -> Tuple[str, str]:
        """
        入力されたリポジトリ名から owner と repo を抽出します。
        owner が省略された場合は認証ユーザー名を返します。

        Raises:
            ValueError: リポジトリ名の形式が無効な場合。
            GitHubAuthenticationError: 認証ユーザーの取得に失敗した場合。
        """
        logger.debug(f"Parsing repository name input: {repo_name_input}")
        if '/' in repo_name_input:
            parts = repo_name_input.split('/', 1)
            if len(parts) == 2 and parts[0] and parts[1]:
                owner, repo = parts
                logger.debug(f"Parsed owner={owner}, repo={repo}")
                return owner, repo
            else:
                raise ValueError(f"Invalid repository name format: '{repo_name_input}'. Expected 'owner/repo'.")
        else:
            # owner が省略された場合は認証ユーザーを取得
            logger.info("Owner not specified in repo name, attempting to get authenticated user.")
            try:
                # GitHubクライアントを使って認証ユーザー情報を取得
                # 注意: このAPI呼び出しはレートリミットを消費します
                user_response = self.github_client.gh.rest.users.get_authenticated()
                owner = getattr(user_response.parsed_data, 'login', None)
                if not owner:
                     logger.error("Could not retrieve login name for authenticated user.")
                     raise GitHubClientError("Could not retrieve authenticated user login name.")
                logger.info(f"Using authenticated user as owner: {owner}")
                return owner, repo_name_input
            except Exception as e:
                # GitHubClientError やその他のエラーを捕捉
                logger.error(f"Failed to get authenticated user to determine owner: {e}", exc_info=True)
                # より具体的な認証エラーとしてラップして送出
                raise GitHubAuthenticationError(f"Failed to get authenticated user: {e}", original_exception=e) from e

    def execute(self, file_path: Path, repo_name_input: str, project_name: str, dry_run: bool = False):
        """
        リソース作成のワークフローを実行します。
        エラーが発生した場合、処理を中断し例外を送出します。

        Args:
            file_path: 入力Markdownファイルのパス。
            repo_name_input: 作成/利用するリポジトリ名 ('owner/repo' or 'repo')。
            project_name: 利用するプロジェクト名。
            dry_run: Trueの場合、GitHubへの実際の変更を行わない。
        """
        logger.info(f"Starting GitHub resource creation process for file: {file_path}, repo_input: {repo_name_input}, project: {project_name}, dry_run: {dry_run}")
        repo_owner, repo_name = "", ""

        try:
            # --- ステップ 0: リポジトリ名解析 ---
            repo_owner, repo_name = self._get_owner_repo(repo_name_input)
            repo_full_name = f"{repo_owner}/{repo_name}"
            logger.info(f"Target repository identified: {repo_full_name}")

            # --- ステップ 1: ファイル読み込み ---
            logger.info(f"Reading file: {file_path}")
            markdown_content = self.file_reader(file_path)
            logger.info(f"File read successfully (length: {len(markdown_content)}).")

            # --- ステップ 2: AI パース ---
            logger.info("Parsing content with AI...")
            parsed_data: ParsedRequirementData = self.ai_parser.parse(markdown_content)
            logger.info(f"AI parsing complete. Found {len(parsed_data.issues)} potential issue(s).")

            # --- ステップ 3: Dry Run モードのチェック ---
            if dry_run:
                logger.warning("Dry run mode enabled. Skipping GitHub operations.")
                # Dry run 時のレポート表示 (例)
                self.reporter.display_repository_creation_result(f"https://github.com/{repo_full_name} (Dry Run)", repo_name)
                dummy_issues_result = CreateIssuesResult(
                    created_issue_urls=[f"URL for '{issue.title}' (Dry Run)" for issue in parsed_data.issues]
                )
                self.reporter.display_issue_creation_result(dummy_issues_result, repo_full_name)
                logger.warning("Dry run finished.")
                return # Dry run の場合はここで処理終了

            # --- ステップ 4: リポジトリ作成 ---
            logger.info(f"Executing CreateRepositoryUseCase for '{repo_name}'...")
            # CreateRepositoryUseCase は owner を必要としない想定
            repo_url = self.create_repo_uc.execute(repo_name)
            self.reporter.display_repository_creation_result(repo_url, repo_name) # 成功をレポート

            # --- ステップ 5: Issue 作成 ---
            logger.info(f"Executing CreateIssuesUseCase for '{repo_full_name}'...")
            issue_result: CreateIssuesResult = self.create_issues_uc.execute(parsed_data, repo_owner, repo_name)
            self.reporter.display_issue_creation_result(issue_result, repo_full_name) # 結果をレポート

            # --- ステップ 6: (将来の実装箇所) ---
            logger.info("Project linking and other resource steps not yet implemented.")

            logger.info("GitHub resource creation process completed successfully.")

        # ★ 各ステップで発生しうる想定内のエラーを捕捉 ★
        except (ValueError, FileProcessingError, AiParserError, GitHubClientError, GitHubValidationError, GitHubAuthenticationError) as e:
            # エラーが発生したらログに記録し、処理を中断して例外をそのまま上位に伝搬させる
            logger.error(f"Error during resource creation workflow: {type(e).__name__} - {e}")
            # display_general_error は main.py で呼ぶ想定なのでここでは呼ばない
            raise # 例外を再送出
        except Exception as e:
            # 予期しないその他のエラーも捕捉してログに記録し、ラップして伝搬
            logger.exception(f"An unexpected critical error occurred during resource creation workflow: {e}")
            raise GitHubClientError(f"An unexpected critical error occurred: {e}", original_exception=e) from e
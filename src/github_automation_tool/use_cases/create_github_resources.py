# src/github_automation_tool/use_cases/create_github_resources.py

import logging
from pathlib import Path
from typing import Tuple, Callable # Callable をインポート
import json # リポジトリ重複エラーの詳細判定用 (将来のため)

# 依存コンポーネントとデータモデル、例外をインポート
from github_automation_tool.infrastructure.config import Settings
# file_reader は関数なので直接インポートするか、パスで指定する
# from github_automation_tool.infrastructure.file_reader import read_markdown_file
from github_automation_tool.adapters.ai_parser import AIParser
from github_automation_tool.adapters.github_client import GitHubAppClient
from github_automation_tool.use_cases.create_repository import CreateRepositoryUseCase
from github_automation_tool.use_cases.create_issues import CreateIssuesUseCase
from github_automation_tool.adapters.cli_reporter import CliReporter
from github_automation_tool.domain.models import ParsedRequirementData, CreateIssuesResult
# ★ FileProcessingError の代わりに捕捉したい例外をインポート
from github_automation_tool.domain.exceptions import (
    AiParserError, GitHubClientError, GitHubAuthenticationError, GitHubValidationError
)
# ★ ファイル関連の標準例外もインポートしておくと except で使える
import builtins # FileNotFoundError はここ
# from io import UnsupportedOperation # IOError など

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
        """
        UseCaseを初期化し、依存コンポーネントを注入します。

        Args:
            settings: アプリケーション設定。
            file_reader: ファイル読み込み関数。
            ai_parser: AIパーサークラスのインスタンス。
            github_client: GitHubクライアントクラスのインスタンス。
            create_repo_uc: リポジトリ作成UseCaseのインスタンス。
            create_issues_uc: Issue作成UseCaseのインスタンス。
            reporter: 結果表示クラスのインスタンス。
        """
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

        Args:
            repo_name_input: CLIから入力されたリポジトリ名 ('owner/repo' or 'repo')。

        Returns:
            (owner名, repo名) のタプル。

        Raises:
            ValueError: リポジトリ名の形式が無効な場合。
            GitHubAuthenticationError: 認証ユーザーの取得に失敗した場合。
            GitHubClientError: 認証ユーザー取得時に予期せぬAPIエラーが発生した場合。
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
                # ログイン名を安全に取得
                owner = getattr(user_response.parsed_data, 'login', None)
                if not owner:
                     logger.error("Could not retrieve login name for authenticated user from API response.")
                     raise GitHubClientError("Could not retrieve authenticated user login name.")
                logger.info(f"Using authenticated user as owner: {owner}")
                return owner, repo_name_input
            except GitHubClientError as e: # GitHubClientError をそのままraise
                logger.error(f"Failed to get authenticated user due to client error: {e}")
                raise
            except Exception as e:
                # その他の予期せぬエラー (ネットワークエラーなど)
                logger.error(f"Failed to get authenticated user to determine owner: {e}", exc_info=True)
                # より具体的な認証関連エラーとしてラップして送出
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

        Raises:
            FileNotFoundError: 入力ファイルが見つからない場合。
            PermissionError: 入力ファイルの読み取り権限がない場合。
            IOError: その他のファイル読み込みエラー。
            ValueError: 不正なリポジトリ名形式の場合。
            AiParserError: AI解析エラー。
            GitHubValidationError: GitHubリソース作成時のバリデーションエラー（例：リポジトリ重複）。
            GitHubAuthenticationError: GitHub認証/権限エラー。
            GitHubClientError: その他のGitHub API関連エラーまたは予期せぬ内部エラー。
        """
        logger.info(f"Starting GitHub resource creation workflow for file: '{file_path}', repo_input: '{repo_name_input}', project: '{project_name}', dry_run: {dry_run}")
        repo_owner, repo_name, repo_full_name = "", "", ""

        # ★★★ execute メソッド全体を try で囲む ★★★
        try:
            # --- ステップ 0: リポジトリ名解析 ---
            repo_owner, repo_name = self._get_owner_repo(repo_name_input)
            repo_full_name = f"{repo_owner}/{repo_name}"
            logger.info(f"Target repository identified: {repo_full_name}")

            # --- ステップ 1: ファイル読み込み ---
            logger.info(f"Reading file: {file_path}")
            markdown_content = self.file_reader(file_path) # FileNotFoundError, PermissionError, IOErrorなど発生可能性
            logger.info(f"File read successfully (length: {len(markdown_content)}).")

            # --- ステップ 2: AI パース ---
            logger.info("Parsing content with AI...")
            parsed_data: ParsedRequirementData = self.ai_parser.parse(markdown_content) # AiParserError 発生可能性
            logger.info(f"AI parsing complete. Found {len(parsed_data.issues)} potential issue(s).")

            # --- ステップ 3: Dry Run モードのチェック ---
            if dry_run:
                logger.warning("Dry run mode enabled. Skipping GitHub operations.")
                # Dry run 時のレポート表示
                self.reporter.display_repository_creation_result(f"https://github.com/{repo_full_name} (Dry Run)", repo_name)
                # ダミーのIssue結果を作成して表示
                dummy_issues_result = CreateIssuesResult(
                    created_issue_urls=[f"URL for '{issue.title}' (Dry Run)" for issue in parsed_data.issues]
                )
                self.reporter.display_issue_creation_result(dummy_issues_result, repo_full_name)
                logger.warning("Dry run finished.")
                return # Dry run の場合はここで処理終了

            # --- ステップ 4: リポジトリ作成 ---
            logger.info(f"Executing CreateRepositoryUseCase for '{repo_name}'...")
            # CreateRepositoryUseCase は GitHubValidationError など発生可能性
            repo_url = self.create_repo_uc.execute(repo_name)
            self.reporter.display_repository_creation_result(repo_url, repo_name) # 成功をレポート

            # --- ステップ 5: Issue 作成 ---
            logger.info(f"Executing CreateIssuesUseCase for '{repo_full_name}'...")
            # CreateIssuesUseCase は内部でエラーを捕捉するが、予期せぬエラーの可能性も
            issue_result: CreateIssuesResult = self.create_issues_uc.execute(parsed_data, repo_owner, repo_name)
            self.reporter.display_issue_creation_result(issue_result, repo_full_name) # 結果をレポート

            # --- ステップ 6: (将来の実装箇所) ---
            logger.info("Project linking and other resource creation steps not yet implemented.")

            logger.info("GitHub resource creation process completed successfully.")

        # ★★★ except 節を整理 (具体性の高い順に) ★★★
        # 1. ファイル関連の標準例外を捕捉
        except FileNotFoundError as e:
             logger.error(f"Input file error: {e}")
             raise # そのまま再送出
        except PermissionError as e:
             logger.error(f"Input file permission error: {e}")
             raise
        except IOError as e: # UnicodeDecodeErrorなども含む可能性
             logger.error(f"Input file read error: {e}")
             raise
        # 2. アプリケーション内の想定されるカスタム例外を捕捉
        except (ValueError, AiParserError, GitHubValidationError, GitHubAuthenticationError, GitHubClientError) as e:
            # これらのエラーは内部で既にログが出ていることが多い
            logger.error(f"Workflow error during resource creation: {type(e).__name__} - {e}")
            raise # そのまま上位 (main.py) に伝搬させる
        # 3. その他の予期しない例外を捕捉
        except Exception as e:
            logger.exception(f"An unexpected critical error occurred during resource creation workflow: {e}")
            # 予期せぬエラーは GitHubClientError でラップして伝搬
            raise GitHubClientError(f"An unexpected critical error occurred: {e}", original_exception=e) from e